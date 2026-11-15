#!/usr/bin/env python3
"""Check generated native codecs, bounded buffers and lifetime capabilities."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
from backend import compiler_flags


def codec(source, pattern, label):
    names = set(re.findall(pattern, source))
    if len(names) != 1:
        raise RuntimeError(f'Expected one generated {label} codec, found {sorted(names)}')
    return names.pop()


def future_operations(source):
    if 'new Future_QString()' not in source:
        return []
    functions = re.findall(r'static bool [^\n]*?(bqt_op_\d+)\(BqtRequest \*r\) \{\n(.*?)\n\}', source, re.S)
    selectors = {
        'BQT_FUTURE_NEW': ('new Future_QString()',),
        'BQT_FUTURE_CLONE': ('new Future_QString(*value)',),
        'BQT_FUTURE_RESULT': ('get<Future_QString>', 'auto returned = value->resultAt(index);'),
        'BQT_WATCHER_NEW': ('new FutureWatcher_QString()',),
        'BQT_WATCHER_SET': ('get<FutureWatcher_QString>', 'self->setFuture(*value);'),
        'BQT_FUTURE_AWAIT': ('get<Future_QString>', 'wait_until(r, [value] { return value->isFinished(); }'),
    }
    definitions = []
    for macro, fragments in selectors.items():
        matches = [name for name, body in functions if all(fragment in body for fragment in fragments)]
        if len(matches) != 1:
            raise RuntimeError(f'Expected one generated future operation {macro}, found {matches}')
        definitions.append('-D' + macro + '=' + matches[0])
    return definitions


def inout_operations(source):
    functions = re.findall(r'static bool [^\n]*?(bqt_op_\d+)\(BqtRequest \*r\) \{\n(.*?)\n\}', source, re.S)
    matches = [name for name, body in functions if 'QFileDialog::getOpenFileName(' in body and 'QString out4 = ' in body]
    if not matches:
        return []
    if len(matches) != 1:
        raise RuntimeError(f'Expected one native QFileDialog inout operation, found {matches}')
    return ['-DBQT_FILE_DIALOG_GET_OPEN=' + matches[0]]


def matrix_operations(source):
    functions = re.findall(r'static bool [^\n]*?(bqt_op_\d+)\(BqtRequest \*r\) \{\n(.*?)\n\}', source, re.S)
    matches = [(name, body) for name, body in functions if 'float buffer_matrix_1[2][2]' in body
               and 'static_cast<int>(int32_t(r->arguments[0].word))' in body]
    if not matches:
        return []
    if len(matches) != 1:
        raise RuntimeError('Expected one native 2x2 shader array operation')
    name, body = matches[0]
    identifier = re.search(r'get<QOpenGLShaderProgram>\(r, r->self, (\d+)', body)
    if identifier is None:
        raise RuntimeError('Shader array operation has no checked program receiver')
    definitions = ['-DBQT_SHADER_MATRIX_2=' + name, '-DBQT_SHADER_PROGRAM_TYPE=' + identifier[1]]
    attributes = [op for op, code in functions if 'buffer_tuple_1' in code
                  and 'setAttributeValue(static_cast<int>(int32_t(r->arguments[0].word))' in code]
    if len(attributes) > 1:
        raise RuntimeError('Expected one native bounded shader attribute operation')
    if attributes:
        definitions.append('-DBQT_SHADER_ATTRIBUTE_ARRAY=' + attributes[0])
    return definitions


def graphics_filter_operations(source):
    functions = re.findall(r'static bool [^\n]*?(bqt_op_\d+)\(BqtRequest \*r\) \{\n(.*?)\n\}', source, re.S)
    matches = [(name, body) for name, body in functions if 'available.majorVersion() < required.majorVersion()' in body]
    if not matches:
        return []
    if len(matches) != 2:
        raise RuntimeError('Expected both native graphics-filter comparison adapters')
    definitions = []
    for name, body in matches:
        suffix = 'NOT_EQUAL' if 'decltype(auto) returned = !(' in body else 'EQUAL'
        definitions.append('-DBQT_GRAPHICS_FILTER_' + suffix + '=' + name)
    identifier = re.search(r'get<Qt3DRender::QGraphicsApiFilter>\(r, r->self, (\d+)', matches[0][1])
    if identifier is None:
        raise RuntimeError('Graphics-filter adapter has no checked receiver')
    return definitions + ['-DBQT_GRAPHICS_FILTER_TYPE=' + identifier[1]]


def gl_buffer_operations(source):
    functions = re.findall(r'static bool [^\n]*?(bqt_op_\d+)\(BqtRequest \*r\) \{\n(.*?)\n\}', source, re.S)
    definitions = []
    for suffix, method in [('SHADER_QUERY', 'glGetShaderiv'), ('ATTRIBUTE_QUERY', 'glGetVertexAttribfv'),
                           ('ATTACHED_SHADERS', 'glGetAttachedShaders'), ('STATE_QUERY', 'glGetIntegerv'),
                           ('TEX_IMAGE_2D', 'glTexImage2D'), ('READ_PIXELS', 'glReadPixels'),
                           ('VERTEX_POINTER', 'glVertexAttribPointer'), ('DRAW_ELEMENTS', 'glDrawElements'),
                           ('COMPRESSED_UPLOAD', 'glCompressedTexImage2D'), ('SHADER_SOURCE', 'glShaderSource')]:
        matches = [(name, body) for name, body in functions if 'get<QOpenGLFunctions>' in body
                   and f'static_cast<QOpenGLFunctions *>(self)->{method}(' in body
                   and 'gl_pixel_offset(r,' not in body]
        if not matches:
            return []
        if len(matches) != 1:
            raise RuntimeError(f'Expected one generated GL buffer operation {method}')
        name, body = matches[0]
        definitions.append('-DBQT_GL_' + suffix + '=' + name)
    identifier = re.search(r'get<QOpenGLFunctions>\(r, r->self, (\d+)', body)
    if identifier is None:
        raise RuntimeError('GL buffer operation has no checked receiver')
    upload = next(body for _, body in functions if 'get<QOpenGLFunctions>' in body
                  and 'static_cast<QOpenGLFunctions *>(self)->glCompressedTexImage2D(' in body
                  and 'gl_pixel_offset(r,' not in body)
    byte_array = re.search(r'get<QByteArray>\(r, r->arguments\[7\].word, (\d+)', upload)
    if byte_array is None:
        raise RuntimeError('GL compressed upload has no checked host byte buffer')
    return definitions + ['-DBQT_GL_FUNCTIONS_TYPE=' + identifier[1], '-DBQT_GL_BYTE_ARRAY_TYPE=' + byte_array[1]]


def texture_operations(source):
    functions = re.findall(r'static bool [^\n]*?(bqt_op_\d+)\(BqtRequest \*r\) \{\n(.*?)\n\}', source, re.S)
    matches = [(name, body) for name, body in functions if 'get<QOpenGLTexture>' in body
               and 'pixel_options_2 = get<QOpenGLPixelTransferOptions>' in body
               and 'gl_texture_pixel_extent' in body and '->setData(' in body
               and 'gl_pixel_offset(r,' not in body]
    if not matches:
        return []
    if len(matches) != 1:
        raise RuntimeError('Expected one base texture pixel upload operation')
    name, body = matches[0]
    texture = re.search(r'get<QOpenGLTexture>\(r, r->self, (\d+)', body)
    options = re.search(r'get<QOpenGLPixelTransferOptions>\(r, r->arguments\[3\].word, (\d+)', body)
    if texture is None or options is None:
        raise RuntimeError('Texture upload operation has no checked texture/options handles')
    return ['-DBQT_TEXTURE_UPLOAD=' + name, '-DBQT_TEXTURE_TYPE=' + texture[1], '-DBQT_PIXEL_OPTIONS_TYPE=' + options[1]]


def sync_operations(source):
    functions = re.findall(r'static bool [^\n]*?(bqt_op_\d+)\(BqtRequest \*r\) \{\n(.*?)\n\}', source, re.S)
    definitions = []
    for suffix, fragment in [('FENCE', '->glFenceSync('), ('IS', '->glIsSync('),
                             ('DELETE', 'return delete_gl_sync('), ('WAIT', 'return wait_gl_sync(')]:
        matches = [(name, body) for name, body in functions if 'get<QOpenGLExtraFunctions>' in body and fragment in body]
        if not matches:
            return []
        if len(matches) != 1:
            raise RuntimeError(f'Expected one generated GL synchronization operation {suffix}')
        name, body = matches[0]
        definitions.append('-DBQT_GL_SYNC_' + suffix + '=' + name)
    identifier = re.search(r'get<QOpenGLExtraFunctions>\(r, r->self, (\d+)', body)
    return definitions + ['-DBQT_GL_EXTRA_FUNCTIONS_TYPE=' + identifier[1]]


def allocated_operations(source):
    functions = re.findall(r'static bool [^\n]*?(bqt_op_\d+)\(BqtRequest \*r\) \{\n(.*?)\n\}', source, re.S)
    matches = [(name, body) for name, body in functions if 'std::unique_ptr<char[]> allocated_guard' in body]
    if not matches:
        return []
    definitions = []
    for name, body in matches:
        suffix = 'UINT' if 'std::numeric_limits<uint>::max()' in body else 'STRING' if 'sequence_value(2)' in body else 'BYTES'
        definitions.append('-DBQT_STREAM_ALLOCATED_' + suffix + '=' + name)
    identifier = re.search(r'get<QDataStream>\(r, r->self, (\d+)', matches[0][1])
    return definitions + ['-DBQT_DATA_STREAM_TYPE=' + identifier[1]]


def interop_operations(source):
    functions = re.findall(r'static bool [^\n]*?(bqt_op_\d+)\(BqtRequest \*r\) \{\n(.*?)\n\}', source, re.S)
    selectors = {
        'LIBRARY_RESOLVE': ('get<QLibrary>(r, r->self', '->resolve('),
        'LIBRARY_UNLOAD': ('get<QLibrary>(r, r->self', '->unload('),
        'FUNCTION_ADDRESS': ('get<NativeFunction>', 'r->result = wide_value'),
        'FUNCTION_NULL': ('get<NativeFunction>', 'r->result.word = !'),
        'KEY_HANDLE': ('get<QSslKey>(r, r->self', 'new NativeSslKey{*source}'),
        'KEY_COPY': ('Native key copy requires', 'r->arguments[1].word'),
        'KEY_ADDRESS': ('get<NativeSslKey>', 'r->result = wide_value'),
        'CERT_HANDLE': ('get<QSslCertificate>(r, r->self', 'new NativeSslCertificate{*source}'),
        'CERT_ADDRESS': ('get<NativeSslCertificate>', 'r->result = wide_value'),
    }
    definitions = []
    for suffix, fragments in selectors.items():
        matches = [(name, body) for name, body in functions if all(part in body for part in fragments)]
        if not matches:
            return []
        if len(matches) != 1:
            raise RuntimeError(f'Expected one native interoperability operation {suffix}, found {matches}')
        name, body = matches[0]
        definitions.append('-DBQT_INTEROP_' + suffix + '=' + name)
        for kind, cls in [('LIBRARY_RESOLVE', 'QLibrary'), ('KEY_HANDLE', 'QSslKey'), ('CERT_HANDLE', 'QSslCertificate')]:
            if suffix == kind:
                identifier = re.search(r'get<' + cls + r'>\(r, r->self, (\d+)', body)
                definitions.append('-DBQT_INTEROP_' + cls.upper() + '_TYPE=' + identifier[1])
    return definitions


def legacy_operations(source):
    functions = re.findall(r'static bool [^\n]*?(bqt_op_\d+)\(BqtRequest \*r\) \{\n(.*?)\n\}', source, re.S)
    definitions = []
    for suffix, method in [('MATERIAL_SET', 'glMaterialfv'), ('MATERIAL_GET', 'glGetMaterialfv'),
                           ('MAP_SET', 'glMap1f'), ('MAP_GET', 'glGetMapfv'), ('STIPPLE_GET', 'glGetPolygonStipple')]:
        matches = [(name, body) for name, body in functions if 'get<QOpenGLFunctions_1_0>' in body
                   and f'static_cast<QOpenGLFunctions_1_0 *>(self)->{method}(' in body
                   and 'gl_pixel_offset(r,' not in body]
        if not matches:
            return []
        if len(matches) != 1:
            raise RuntimeError(f'Expected one native legacy GL operation {method}')
        name, body = matches[0]
        definitions.append('-DBQT_LEGACY_' + suffix + '=' + name)
    identifier = re.search(r'get<QOpenGLFunctions_1_0>\(r, r->self, (\d+)', body)
    return definitions + ['-DBQT_GL_LEGACY_FUNCTIONS_TYPE=' + identifier[1]]


def raw_mapping_operations(source):
    functions = re.findall(r'static bool [^\n]*?(bqt_op_\d+)\(BqtRequest \*r\) \{\n(.*?)\n\}', source, re.S)
    selectors = {
        'MAP': ('get<QOpenGLFunctions_3_2_Core>', 'return raw_gl_mapping_request', 'false, 1,'),
        'RANGE': ('get<QOpenGLFunctions_3_2_Core>', 'return raw_gl_mapping_request', 'false, 2,'),
        'GET': ('get<QOpenGLFunctions_3_2_Core>', 'return raw_gl_mapping_request', 'false, 0,'),
        'UNMAP': ('get<QOpenGLFunctions_3_2_Core>', '->glUnmapBuffer('),
        'DELETE': ('get<QOpenGLFunctions_3_2_Core>', '->glDeleteBuffers('),
        'READ': ('get<MemoryView>', 'Memory view read exceeds'),
        'WRITE': ('get<MemoryView>', 'Memory view write exceeds'),
        'SIZE': ('get<MemoryView>', 'r->result = wide_value(view->size)'),
    }
    definitions = []
    for suffix, fragments in selectors.items():
        matches = [(name, body) for name, body in functions if all(part in body for part in fragments)]
        if not matches:
            return []
        if len(matches) != 1:
            raise RuntimeError(f'Expected one checked raw GL mapping operation {suffix}')
        name, body = matches[0]
        definitions.append('-DBQT_RAW_MAPPING_' + suffix + '=' + name)
        if suffix == 'MAP':
            identifier = re.search(r'get<QOpenGLFunctions_3_2_Core>\(r, r->self, (\d+)', body)
            definitions.append('-DBQT_RAW_MAPPING_FUNCTIONS_TYPE=' + identifier[1])
        if suffix == 'SIZE':
            identifier = re.search(r'get<MemoryView>\(r, r->self, (\d+)', body)
            definitions.append('-DBQT_MEMORY_VIEW_TYPE=' + identifier[1])
    return definitions


def retained_gl_operations(source):
    functions = re.findall(r'static bool [^\n]*?(bqt_op_\d+)\(BqtRequest \*r\) \{\n(.*?)\n\}', source, re.S)
    selectors = {
        'FEEDBACK': ('get<QOpenGLFunctions_1_0>', 'self->glFeedbackBuffer('),
        'SELECTION': ('get<QOpenGLFunctions_1_0>', 'self->glSelectBuffer('),
        'FEEDBACK_READ': ('get<GLFeedbackBuffer>', 'OpenGL retained output exceeds'),
        'SELECTION_READ': ('get<GLSelectionBuffer>', 'OpenGL retained output exceeds'),
        'POINTER': ('get<QOpenGLFunctions_1_1>', 'self->glGetPointerv('),
        'VERTEX_POINTER': ('get<QOpenGLFunctions>', 'self->glGetVertexAttribPointerv('),
        'CALL_LISTS': ('get<QOpenGLFunctions_1_0>', '->glCallLists('),
    }
    definitions = []
    for suffix, fragments in selectors.items():
        matches = [(name, body) for name, body in functions if all(part in body for part in fragments)]
        if not matches:
            return []
        if len(matches) != 1:
            raise RuntimeError(f'Expected one retained GL operation {suffix}')
        name, body = matches[0]
        definitions.append('-DBQT_RETAINED_GL_' + suffix + '=' + name)
        if suffix == 'POINTER':
            identifier = re.search(r'get<QOpenGLFunctions_1_1>\(r, r->self, (\d+)', body)
            definitions.append('-DBQT_GL_POINTER_FUNCTIONS_TYPE=' + identifier[1])
    return definitions


def byte_iterator_operations(source):
    functions = re.findall(r'static bool [^\n]*?(bqt_op_\d+)\(BqtRequest \*r\) \{\n(.*?)\n\}', source, re.S)
    selectors = {
        'BEGIN': ('get<QByteArray>(r, r->self', 'new_byte_iterator(r, r->self, 0, true)'),
        'CONST_BEGIN': ('get<QByteArray>(r, r->self', 'new_byte_iterator(r, r->self, 0, false)'),
        'ERASE': ('get<QByteArray>(r, r->self', 'auto last = it1->offset;'),
        'ADVANCE': ('get<QByteArrayIterator>(r, r->self', 'iterator displacement exceeds'),
        'READ': ('get<QByteArrayIterator>(r, r->self', 'Cannot read the QByteArray end'),
        'WRITE': ('get<QByteArrayIterator>(r, r->self', 'iterator write exceeds'),
    }
    definitions = []
    for suffix, fragments in selectors.items():
        matches = [(name, body) for name, body in functions if all(part in body for part in fragments)]
        if not matches:
            return []
        # cbegin and begin() const share exactly the same checked native body.
        if len(matches) > 1 and suffix != 'CONST_BEGIN':
            raise RuntimeError(f'Expected one QByteArray iterator operation {suffix}')
        definitions.append('-DBQT_BYTE_ITERATOR_' + suffix + '=' + matches[0][0])
    return definitions


def volume_operations(source):
    functions = re.findall(r'static bool [^\n]*?(bqt_op_\d+)\(BqtRequest \*r\) \{\n(.*?)\n\}', source, re.S)
    selectors = {
        'SET': ('get<QCustom3DVolume>', 'auto data = std::make_unique<QList<uchar>>(*a0)'),
        'GET': ('get<QCustom3DVolume>', 'const auto *data = self->textureData();'),
        'IMAGES': ('get<QCustom3DVolume>', 'self->createTextureData(images)'),
        'SLICE': ('get<QCustom3DVolume>', 'volume_slice_extent(r, self', 'reinterpret_cast<const uchar *>(a2->constData())'),
        'SIGNAL': ('get<QCustom3DVolume>', '&QCustom3DVolume::textureDataChanged'),
    }
    definitions = []
    for suffix, fragments in selectors.items():
        matches = [(name, body) for name, body in functions if all(part in body for part in fragments)]
        if not matches:
            return []
        if len(matches) != 1:
            raise RuntimeError(f'Expected one volume-data operation {suffix}')
        name, body = matches[0]
        definitions.append('-DBQT_VOLUME_' + suffix + '=' + name)
        if suffix == 'GET':
            identifier = re.search(r'get<QCustom3DVolume>\(r, r->self, (\d+)', body)
            definitions.append('-DBQT_VOLUME_TYPE=' + identifier[1])
    image = re.search(r'get<QImage>\(r, v.word, (\d+)', source)
    return definitions + ['-DBQT_VOLUME_IMAGE_TYPE=' + image[1]]


def compressed_operations(source):
    functions = re.findall(r'static bool [^\n]*?(bqt_op_\d+)\(BqtRequest \*r\) \{\n(.*?)\n\}', source, re.S)
    matches = [(name, body) for name, body in functions if 'get<QOpenGLFunctions_3_2_Core>' in body
               and '->glGetCompressedTexImage(' in body and 'gl_pixel_offset(r,' not in body]
    if not matches:
        return []
    if len(matches) != 1:
        raise RuntimeError('Expected one desktop compressed texture readback')
    return ['-DBQT_GL_COMPRESSED_READ=' + matches[0][0]]


def pixel_offset_operations(source):
    functions = re.findall(r'static bool [^\n]*?(bqt_op_\d+)\(BqtRequest \*r\) \{\n(.*?)\n\}', source, re.S)
    definitions = []
    for suffix, cls, fragment in [
            ('UPLOAD', 'QOpenGLFunctions', '->glTexImage2D('),
            ('READ', 'QOpenGLFunctions', '->glReadPixels('),
            ('COMPRESSED', 'QOpenGLFunctions', '->glCompressedTexImage2D('),
            ('TEXTURE', 'QOpenGLTexture', 'pixel_options_2 = get<QOpenGLPixelTransferOptions>')]:
        matches = [(name, body) for name, body in functions if f'get<{cls}>' in body
                   and fragment in body and 'gl_pixel_offset(r,' in body
                   and (suffix != 'TEXTURE' or '->setData(' in body)]
        if not matches:
            return []
        if len(matches) != 1:
            raise RuntimeError(f'Expected one checked pixel-buffer alternative {suffix}')
        definitions.append('-DBQT_PIXEL_OFFSET_' + suffix + '=' + matches[0][0])
    return definitions


def text_output_operations(source):
    functions = re.findall(r'static bool [^\n]*?(bqt_op_\d+)\(BqtRequest \*r\) \{\n(.*?)\n\}', source, re.S)
    definitions = []
    for suffix, cls, fragment, type_suffix in [
            ('DECODER_APPEND', 'QStringDecoder', 'self->appendToBuffer(start, input)', 'DECODER'),
            ('ENCODER_APPEND', 'QStringEncoder', 'self->appendToBuffer(start, input)', 'ENCODER'),
            ('STREAM_WORD', 'QTextStream', '*self >> output_bytes;', 'STREAM'),
            ('INSTANCE_BUFFER', 'QQuick3DInstancing', '->instanceBuffer(&out0)', 'INSTANCER')]:
        matches = [(name, body) for name, body in functions if f'get<{cls}>' in body and fragment in body]
        if not matches:
            return []
        if len(matches) != 1:
            raise RuntimeError(f'Expected one owning text/output operation {suffix}')
        name, body = matches[0]
        definitions.append('-DBQT_TEXT_' + suffix + '=' + name)
        identifier = re.search(r'get<' + cls + r'>\(r, r->self, (\d+)', body)
        definitions.append('-DBQT_TEXT_' + type_suffix + '_TYPE=' + identifier[1])
    return definitions


def platform_operations(source):
    functions = re.findall(r'static bool [^\n]*?(bqt_op_\d+)\(BqtRequest \*r\) \{\n(.*?)\n\}', source, re.S)
    selectors = {
        'X11': ('platform_application_interface<QNativeInterface::QX11Application>',),
        'WAYLAND': ('platform_application_interface<QNativeInterface::QWaylandApplication>',),
        'X11_CONNECTION': ('get<QNativeInterface::QX11Application>(r, r->self', '->connection()'),
        'WAYLAND_DISPLAY': ('get<QNativeInterface::QWaylandApplication>(r, r->self', '->display()'),
        'X11_ADDRESS': ('get<NativePlatform_xcb_connection_t>', 'wide_value(value->pointer)'),
        'WAYLAND_ADDRESS': ('get<NativePlatform_wl_display>', 'wide_value(value->pointer)'),
        'SURFACE': ('get<QSurface>(r, r->self', '->surfaceHandle()'),
        'SURFACE_VALID': ('get<NativePlatform_QPlatformSurface>', 'r->result.word = platform_identity_valid'),
        'SURFACE_ADDRESS': ('get<NativePlatform_QPlatformSurface>', 'wide_value(value->pointer)'),
    }
    definitions = []
    for suffix, fragments in selectors.items():
        matches = [(name, body) for name, body in functions if all(fragment in body for fragment in fragments)]
        if not matches:
            return []
        if len(matches) != 1:
            raise RuntimeError(f'Expected one native platform capability operation {suffix}')
        definitions.append('-DBQT_PLATFORM_' + suffix + '=' + matches[0][0])
    for suffix, cls in [('APP', 'QGuiApplication'), ('WINDOW', 'QWindow')]:
        identifier = re.search(r'get<' + cls + r'>\(r, (?:r->self|r->arguments\[0\].word), (\d+)', source)
        definitions.append('-DBQT_PLATFORM_' + suffix + '_TYPE=' + identifier[1])
    return definitions


def fixed_array_codecs(source):
    read = re.findall(r'static std::optional<std::array<int,\s*4>> (read_wire_\w+)\(BqtRequest \*r, const BqtValue &v\)', source)
    write = re.findall(r'static BqtValue (write_wire_\w+)\(BqtRequest \*r, std::array<int,\s*4> const &value\)', source)
    if not read and not write:
        return []
    if len(read) != 1 or len(write) != 1:
        raise RuntimeError('Expected unique fixed-size native int[4] conversion functions')
    return ['-DBQT_READ_INT_ARRAY4=' + read[0], '-DBQT_WRITE_INT_ARRAY4=' + write[0]]


def qtest_operations(source):
    functions = re.findall(r'static bool [^\n]*?(bqt_op_\d+)\(BqtRequest \*r\) \{\n(.*?)\n\}', source, re.S)
    selectors = {
        'BQT_QTEST_FORMAT': 'auto value = qt_test_format(r,',
        'BQT_QTEST_ADD_COLUMN': 'qt_test_private_add_column(r,',
        'BQT_QTEST_ELEMENT_DATA': 'qt_test_private_data(r, qt_test_argument_0, qt_test_argument_1, false)',
        'BQT_QTEST_GLOBAL_DATA': 'qt_test_private_data(r, qt_test_argument_0, qt_test_argument_1, true)',
        'BQT_QTEST_TIMEOUT_GET': 'QTest::defaultTryTimeout.load()',
        'BQT_QTEST_TIMEOUT_SET': 'QTest::defaultTryTimeout.store(',
    }
    if not any(selectors['BQT_QTEST_FORMAT'] in body for _, body in functions):
        return []
    result = []
    for macro, fragment in selectors.items():
        names = [name for name, body in functions if fragment in body]
        if len(names) != 1:
            raise RuntimeError(f'Expected one generated QtTest operation {macro}: {names}')
        result.append('-D' + macro + '=' + names[0])
    return result


def fixed_integer_aliases(output):
    """Exercise the production scalar adapters at their native width boundaries."""
    from generate import Generator
    generator = object.__new__(Generator)
    generator.classes, generator.ids, generator.enums, generator.types = {}, {}, {}, {}
    lines = ['static void fixed_integer_alias_checks() {', 'using namespace bendqt;']
    for prefix in ('', 'std::'):
        for signed in (True, False):
            for width in (8, 16, 32, 64):
                native = prefix + ('int' if signed else 'uint') + str(width) + '_t'
                source = dict(name=native, cpp=native, pointers=0, reference=0, const=False,
                              enum=False, flags=False, instantiations=[])
                converted = generator.type(source)
                declarations, expression = generator.argument(converted, 0)
                lines += ['{', 'auto convert = [](BqtRequest *r) {', *declarations,
                          'if (r->error) return;', f'auto native = {expression};',
                          *generator.store_result(converted, 'native'), '};']
                minimum = -(1 << (width - 1)) if signed else 0
                maximum = (1 << (width - int(signed))) - 1
                for value in (minimum, maximum):
                    bits = value & ((1 << (64 if width == 64 else 32)) - 1)
                    assignment = f'r.arguments[0] = wide_value(UINT64_C({bits}));' if width == 64 else f'r.arguments[0].word = {bits}u;'
                    result = 'wide_bits(r.result)' if width == 64 else 'r.result.word'
                    lines += ['{ BqtRequest r{};', assignment, 'convert(&r);',
                              f'assert(!r.error && {result} == UINT64_C({bits})); }}']
                if width < 32:
                    for value in ((minimum - 1, maximum + 1) if signed else (maximum + 1,)):
                        lines += ['{ BqtRequest r{};', f'r.arguments[0].word = {value & 0xffffffff}u;',
                                  'convert(&r); assert(r.error == ERANGE); }']
                lines += ['}']
    lines += ['std::puts("QT612_NATIVE_FIXED_INTEGERS_OK exact_widths=1 signed_boundaries=1 unsigned_boundaries=1 narrow_overflow_rejected=1");', '}']
    (output / 'fixed-integer-aliases-native.h').write_text('\n'.join(lines) + '\n')


def descriptor_operations(source):
    functions = re.findall(r'static bool [^\n]*?(bqt_op_\d+)\(BqtRequest \*r\) \{\n(.*?)\n\}', source, re.S)
    result = []
    for owner, fragment, operation, type_macro in (
            ('QRhiVertexInputLayout', '->attributeAt(', 'BQT_RHI_ATTRIBUTE_AT', 'BQT_RHI_LAYOUT_TYPE'),
            ('QScxmlTableData', 'auto *names = self->dataNames(&count);', 'BQT_SCXML_DATA_NAMES', 'BQT_SCXML_TABLE_TYPE')):
        matching = [(name, body) for name, body in functions if fragment in body and 'get<' + owner + '>' in body]
        if not matching:
            continue
        if len(matching) != 1:
            raise RuntimeError(f'Expected one descriptor snapshot operation for {owner}')
        name, body = matching[0]
        identifier = re.search(r'get<' + owner + r'>\(r, r->self, (\d+)', body)
        if not identifier:
            raise RuntimeError(f'Descriptor snapshot {owner} has no checked receiver')
        result += ['-D' + operation + '=' + name, '-D' + type_macro + '=' + identifier[1]]
    return result


def rhi_native_operations(source):
    functions = re.findall(r'static bool [^\n]*?(bqt_op_\d+)\(BqtRequest \*r\) \{\n(.*?)\n\}', source, re.S)
    selectors = {'BQT_RHI_FULL_UPDATE': 'return rhi_full_buffer_update(r,',
                 'BQT_RHI_BUFFER_CREATE': 'rhi_buffer_allocation(r->self, self, returned);',
                 'BQT_RHI_ENUM_NULL': 'QRhi::enumerateAdapters(QRhi::Null, parameters)'}
    if not any(selectors['BQT_RHI_FULL_UPDATE'] in body for _, body in functions):
        return []
    result = []
    for macro, fragment in selectors.items():
        matches = [(name, body) for name, body in functions if fragment in body
                   and (macro != 'BQT_RHI_BUFFER_CREATE' or 'get<QRhiBuffer>' in body)]
        if macro == 'BQT_RHI_FULL_UPDATE' and len(matches) > 1 and len({body for _, body in matches}) == 1:
            matches = matches[:1]  # The native size=0 default has identical generated semantics.
        if len(matches) != 1: raise RuntimeError(f'Expected one native RHI operation {macro}: {[name for name, _ in matches]}')
        result += ['-D' + macro + '=' + matches[0][0]]
    for typ, macro in [('QRhi', 'BQT_RHI_ROOT_TYPE'), ('QRhiBuffer', 'BQT_RHI_BUFFER_TYPE'),
                       ('QByteArray', 'BQT_RHI_BYTES_TYPE'), ('QRhiNullInitParams', 'BQT_RHI_NULL_PARAMS_TYPE'),
                       ('QRhiCommandBuffer', 'BQT_RHI_COMMAND_TYPE')]:
        ids = set(re.findall(r'get<' + typ + r'>\(r, (?:r->self|r->arguments\[\d+\]\.word), (\d+)', source))
        if len(ids) != 1: raise RuntimeError(f'Expected native RHI type id for {typ}: {ids}')
        result += ['-D' + macro + '=' + ids.pop()]
    # PySide registers no Null backend record; it is used only if extracted.
    optional = {'BQT_RHI_GLES_HANDLES': 'new QRhiGles2NativeHandles(*native)',
                'BQT_RHI_NULL_HANDLES': 'new QRhiNullNativeHandles(*native)'}
    for macro, fragment in optional.items():
        matches = [name for name, body in functions if fragment in body]
        if len(matches) == 1: result += ['-D' + macro + '=' + matches[0]]
    destroy = [name for name, body in functions if 'rhi_buffer_clear(r->self);' in body and 'get<QRhiBuffer>' in body]
    if len(destroy) != 1: raise RuntimeError(f'Expected one native RHI buffer destroy operation: {destroy}')
    result += ['-DBQT_RHI_BUFFER_NATIVE_DESTROY=' + destroy[0]]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=ROOT / 'build/qt612')
    parser.add_argument('--coverage', type=Path, default=ROOT / 'packages/qt612/coverage.json')
    parser.add_argument('--qt-root', type=Path,
                        default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    parser.add_argument('--cxx', default='clang++-19')
    args = parser.parse_args()
    wrappers = (args.work / 'wrappers.cpp').resolve()
    source = wrappers.read_text()
    optional = codec(source, r'static std::optional<std::optional<quint64>>\s+(read_wire_\w+)\(', 'optional quint64 reader')
    array_list = codec(source, r'static BqtValue\s+(write_wire_\w+)\(BqtRequest \*r, QList<QByteArray> const &value\)', 'QByteArray list writer')
    modules = json.loads(args.coverage.read_text())['qt_modules']
    output = args.work / 'conversions-native-check'
    output.mkdir(parents=True, exist_ok=True)
    fixed_integer_aliases(output)
    executable = output / 'conversions-native'
    # The tested file uses assert; the backend's release NDEBUG is deliberately
    # removed here. O0 keeps this full-source diagnostic build practical; fresh
    # Hub consumers separately exercise the optimized packaged native payload.
    flags = [f for f in compiler_flags(args.qt_root, args.cxx, modules) if f not in ('-DNDEBUG', '-O1')]
    flags.append('-O0')
    test_operations = qtest_operations(source)
    if test_operations:
        moc = subprocess.run([str(args.qt_root / 'libexec/moc'), '-DBQT_QTEST_FORMAT=1',
            str(ROOT / 'examples/qt612/qtest-values-native.h'),
            '-o', str(output / 'qtest-values-native.moc')], text=True, capture_output=True)
        if moc.returncode:
            raise RuntimeError(f'QtTest fixture moc failed: {moc.stderr}')
    command = [*flags, '-Wno-deprecated-declarations',
               '-DBQT_GENERATED_WRAPPERS=' + json.dumps(str(wrappers)),
               '-DBQT_READ_OPTIONAL_U64=' + optional,
               '-DBQT_WRITE_BYTE_ARRAY_LIST=' + array_list,
               *future_operations(source),
               *inout_operations(source),
               *matrix_operations(source),
               *graphics_filter_operations(source),
               *gl_buffer_operations(source),
               *texture_operations(source),
               *sync_operations(source),
               *allocated_operations(source),
               *interop_operations(source),
               *legacy_operations(source),
               *raw_mapping_operations(source),
               *retained_gl_operations(source),
               *byte_iterator_operations(source),
               *volume_operations(source),
               *compressed_operations(source),
               *pixel_offset_operations(source),
               *text_output_operations(source),
               *platform_operations(source),
               *fixed_array_codecs(source),
               *test_operations, '-I' + str(output),
               *descriptor_operations(source),
               *rhi_native_operations(source),
               str(ROOT / 'examples/qt612/conversions-native.cpp'),
               '-L' + str(args.qt_root / 'lib'),
               *['-lQt6' + m.removeprefix('Qt') for m in reversed(modules)],
               '-o', str(executable)]
    compiled = subprocess.run(command, text=True, capture_output=True)
    (output / 'build.log').write_text(compiled.stdout + compiled.stderr)
    if compiled.returncode:
        raise RuntimeError(f'Native conversion fixture failed to compile; see {output / "build.log"}')
    env = dict(os.environ, LD_LIBRARY_PATH=str(args.qt_root / 'lib'), QT_QPA_PLATFORM='offscreen',
               QT_PLUGIN_PATH=str(args.qt_root / 'plugins'),
               QT_QPA_PLATFORM_PLUGIN_PATH=str(args.qt_root / 'plugins/platforms'))
    checked = subprocess.run([str(executable)], text=True, capture_output=True, env=env, timeout=30)
    (output / 'run.log').write_text(checked.stdout + checked.stderr)
    if checked.returncode or 'QT612_NATIVE_CONVERSIONS_OK' not in checked.stdout:
        raise RuntimeError(f'Native conversion fixture failed; see {output / "run.log"}')
    (output / 'receipt.json').write_text(json.dumps(dict(
        wrappers=str(wrappers), wrappers_sha256=hashlib.sha256(source.encode()).hexdigest(),
        qt_root=str(args.qt_root), modules=modules,
        markers=[line for line in checked.stdout.splitlines() if line.startswith('QT612_NATIVE_')],
        proof_boundary='Native integration checks; no native scheduling, lifetime or allocation theorem is claimed.'), indent=2) + '\n')
    print(checked.stdout.strip())


if __name__ == '__main__':
    main()
