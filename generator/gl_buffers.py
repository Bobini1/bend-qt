"""Synchronous OpenGL buffers with registry-defined extents.

The pinned registry describes element counts and byte sizes. Stateful COMPSIZE
expressions and pointers retained by GL need separate lifetime/state adapters.
"""
import json
from pathlib import Path
import re

REGISTRY = json.loads(Path(__file__).with_name('gl-array-lengths.json').read_text())['commands']
QUERIES = json.loads(Path(__file__).with_name('gl-query-lengths.json').read_text())['families']
LEGACY_QUERIES = json.loads(Path(__file__).with_name('gl-legacy-lengths.json').read_text())['families']
LEGACY_FAMILIES = ('fog', 'light', 'light_model', 'material', 'point', 'tex_env',
                   'tex_gen', 'color_table', 'convolution', 'histogram', 'minmax')

# These APIs retain client addresses beyond the call. A registry length cannot
# make a temporary conversion safe for them.
RETAINED = {'glFeedbackBuffer', 'glSelectBuffer', 'glVertexPointer', 'glNormalPointer',
            'glColorPointer', 'glIndexPointer', 'glTexCoordPointer', 'glEdgeFlagPointer',
            'glFogCoordPointer', 'glSecondaryColorPointer', 'glVertexAttribPointer',
            'glVertexAttribIPointer', 'glVertexAttribLPointer', 'glInterleavedArrays'}

# Every accepted query selector of these commands returns one scalar. Unlike
# glGetProgramiv/texture/uniform-block queries, none has a vector-valued case.
SCALAR_QUERIES = {'glGetBufferParameteriv', 'glGetFramebufferAttachmentParameteriv',
    'glGetFramebufferParameteriv', 'glGetProgramInterfaceiv', 'glGetProgramPipelineiv',
    'glGetQueryObjectuiv', 'glGetQueryiv', 'glGetRenderbufferParameteriv', 'glGetShaderiv',
    'glGetTexLevelParameterfv', 'glGetTexLevelParameteriv', 'glGetBufferParameteri64v',
    'glGetQueryObjectiv', 'glGetQueryObjecti64v', 'glGetQueryObjectui64v', 'glGetQueryIndexediv',
    'glGetNamedBufferParameteri64v', 'glGetNamedBufferParameteriv',
    'glGetNamedFramebufferAttachmentParameteriv', 'glGetNamedFramebufferParameteriv',
    'glGetNamedRenderbufferParameteriv', 'glGetTextureLevelParameterfv', 'glGetTextureLevelParameteriv',
    'glGetTransformFeedbacki64_v', 'glGetTransformFeedbacki_v', 'glGetTransformFeedbackiv',
    'glGetVertexArrayIndexed64iv', 'glGetVertexArrayIndexediv', 'glGetVertexArrayiv'}


def policies(function):
    name = function['name']
    owner = function['declaring_class']
    if owner == 'QOpenGLTexture' and name in ('setData', 'setCompressedData'):
        args = function['arguments']
        by_name = {a['name']: i for i, a in enumerate(args)}
        if 'data' not in by_name:
            return {}
        options = by_name['options']
        policy = {'bytes': True, 'pixel_buffer': 'unpack', 'options_source': options}
        if name == 'setCompressedData':
            policy.update(count_source=by_name['dataSize'], compressed_layout=True, texture_compressed=True)
        else:
            policy.update(texture_layout=True, options_source=options,
                          format_source=by_name['sourceFormat'], pixel_type_source=by_name['sourceType'])
        for field, role in [('width', 'width'), ('height', 'height'), ('depth', 'depth'), ('layerCount', 'layer_count')]:
            if field in by_name:
                policy[role + '_source'] = by_name[field]
        if 'mipLevel' in by_name:
            policy['mip_source'] = by_name['mipLevel']
        return {by_name['data']: policy, options: {'value_pointer': True, 'nullable': True}}
    if owner == 'QOpenGLShaderProgram' and name == 'setAttributeArray':
        return {i: {'gpu_offset': True, 'gpu_target': 'GL_ARRAY_BUFFER',
                    'gpu_binding': 'GL_ARRAY_BUFFER_BINDING', 'gpu_extent': 0, 'gpu_alignment': 1}
                for i, argument in enumerate(function['arguments'])
                if argument['type']['pointers'] == 1 and argument['type']['name'] in ('float', 'void')}
    if not owner.startswith(('QOpenGLFunctions', 'QOpenGLExtraFunctions')):
        return {}
    arguments = function['arguments']
    if name == 'glCallLists':
        return {2: {'bytes': True, 'count_source': 0, 'list_type_source': 1}}
    if name in ('glShaderSource', 'glCreateShaderProgramv', 'glGetUniformIndices', 'glTransformFeedbackVaryings'):
        result = {2: {'string_array': True, 'count_source': 1}}
        if name == 'glShaderSource':
            result[2]['lengths_source'] = 3
            result[3] = {'count_source': 1}
        elif name == 'glGetUniformIndices':
            result[3] = {'count_source': 1, 'writable_array': True}
        return result
    if name in ('glMultiDrawElements', 'glMultiDrawElementsBaseVertex'):
        result = {1: {'count_source': 4}, 3: {'gpu_indices_array': True, 'count_source': 4,
                                            'counts_source': 1, 'index_type_source': 2}}
        if name.endswith('BaseVertex'):
            result[5] = {'count_source': 4}
        return result
    if name == 'glGetnSeparableFilter':
        return {4: {'bytes': True, 'writable': True, 'count_source': 3, 'pixel_buffer': 'pack'},
                6: {'bytes': True, 'writable': True, 'count_source': 5, 'pixel_buffer': 'pack'},
                7: {'ignored': True}}
    if name == 'glGetSeparableFilter':
        return {i: {'bytes': True, 'writable': True, 'pixel_buffer': 'pack', 'legacy_readback': 4,
                    'target_source': 0, 'format_source': 1, 'pixel_type_source': 2, 'readback_axis': i - 3}
                for i in (3, 4)} | {5: {'ignored': True}}
    if name == 'glSeparableFilter2D':
        return {i: {'bytes': True, 'pixel_layout': True, 'pixel_buffer': 'unpack',
                    'width_source': i - 4, 'format_source': 4, 'pixel_type_source': 5} for i in (6, 7)}
    if name in ('glObjectPtrLabel', 'glGetObjectPtrLabel'):
        result = {0: {'gl_sync': True}}
        if name == 'glObjectPtrLabel':
            result[2] = {'bytes': True, 'count_source': 1, 'negative_terminated': True}
        else:
            result[2] = {'output_pointer': True}
            result[3] = {'bytes': True, 'count_source': 1, 'writable': True}
        return result
    if name in ('glVertexAttribPointer', 'glVertexAttribIPointer', 'glVertexAttribLPointer'):
        return {len(arguments) - 1: {'gpu_offset': True, 'gpu_target': 'GL_ARRAY_BUFFER',
                    'gpu_binding': 'GL_ARRAY_BUFFER_BINDING', 'gpu_extent': 0, 'gpu_alignment': 1}}
    if name in RETAINED - {'glFeedbackBuffer', 'glSelectBuffer'}:
        return {len(arguments) - 1: {'gpu_offset': True, 'gpu_target': 'GL_ARRAY_BUFFER',
                    'gpu_binding': 'GL_ARRAY_BUFFER_BINDING', 'gpu_extent': 0, 'gpu_alignment': 1}}
    if name in RETAINED:
        return {}
    if name in ('glDrawArraysIndirect', 'glDrawElementsIndirect'):
        return {len(arguments) - 1: {'gpu_offset': True, 'gpu_target': 'GL_DRAW_INDIRECT_BUFFER',
                    'gpu_binding': 'GL_DRAW_INDIRECT_BUFFER_BINDING',
                    'gpu_extent': 16 if name == 'glDrawArraysIndirect' else 20, 'gpu_alignment': 4}}
    if name in ('glMultiDrawArraysIndirect', 'glMultiDrawElementsIndirect'):
        index = 1 if name == 'glMultiDrawArraysIndirect' else 2
        return {index: {'gpu_offset': True, 'gpu_target': 'GL_DRAW_INDIRECT_BUFFER',
                       'gpu_binding': 'GL_DRAW_INDIRECT_BUFFER_BINDING', 'gpu_extent': 16 if index == 1 else 20,
                       'gpu_alignment': 4, 'draw_count_source': index + 1, 'draw_stride_source': index + 2}}
    command = REGISTRY.get(name, {})
    result = {}
    if command and len(arguments) == len(command['parameters']):
        for text_index, length in command['lengths'].items():
            index = int(text_index)
            native = arguments[index]['type']
            if native['pointers'] != 1 or native['reference']:
                continue
            if native['name'] not in ('void', 'char', 'float', 'double', 'int', 'unsigned int',
                                      'uint', 'qint64', 'quint64', 'long', 'unsigned long',
                                      'short', 'unsigned short', 'uchar', 'unsigned char', 'signed char'):
                continue
            # NUL-terminated names already use String; length-tagged char data
            # is a binary buffer and may contain embedded NUL bytes.
            policy = {'bytes': True} if native['name'] in ('void', 'char') else {}
            if length.isdigit():
                if int(length) == 1 and not native['const'] and not policy:
                    policy = {'output_pointer': True}
                else:
                    policy['exact_size'] = int(length)
            else:
                match = re.fullmatch(r'([A-Za-z_][A-Za-z_0-9]*)(?:([*/])([0-9]+))?', length)
                if match is None or match[1] not in command['parameters']:
                    continue
                extent = command['parameters'].index(match[1])
                if arguments[extent]['type']['pointers']:
                    continue
                policy['count_source'] = extent
                if match[2]:
                    policy['multiplier' if match[2] == '*' else 'count_divisor'] = int(match[3])
            if not native['const'] and not policy.get('output_pointer'):
                policy['writable' if policy.get('bytes') else 'writable_array'] = True
            if name.startswith(('glCompressedTexImage', 'glCompressedTexSubImage')):
                policy['pixel_buffer'] = 'unpack'
                policy['compressed_layout'] = True
                policy['compressed_dimensions'] = 3 if name.endswith('3D') else 2 if name.endswith('2D') else 1
                for dimension in ('width', 'height', 'depth'):
                    if dimension in command['parameters']:
                        policy[dimension + '_source'] = command['parameters'].index(dimension)
            elif name.startswith(('glReadnPixels', 'glGetnTexImage', 'glGetnCompressedTexImage')):
                policy['pixel_buffer'] = 'pack'
            elif name.startswith(('glGetTextureImage', 'glGetTextureSubImage', 'glGetCompressedTextureImage',
                                  'glGetCompressedTextureSubImage', 'glGetnPolygonStipple')):
                policy['pixel_buffer'] = 'pack'
            elif name in ('glPixelMapfv', 'glPixelMapuiv', 'glPixelMapusv'):
                policy['pixel_buffer'] = 'unpack'
            result[index] = policy
    if name in SCALAR_QUERIES:
        for index, argument in enumerate(arguments):
            native = argument['type']
            if native['pointers'] == 1 and not native['const']:
                result[index] = {'output_pointer': True}
    if name == 'glGetMultisamplefv':
        result[2] = {'exact_size': 2, 'writable_array': True}
    if name == 'glGetActiveUniformsiv':
        result[4] = {'count_source': 1, 'writable_array': True}
    if name == 'glGetActiveAtomicCounterBufferiv':
        result[3] = {'gl_extent': 18, 'program_source': 0, 'block_source': 1,
                     'pname_source': 2, 'writable_array': True}
    if name == 'glGetActiveSubroutineUniformiv':
        result[4] = {'gl_extent': 19, 'program_source': 0, 'stage_source': 1,
                     'block_source': 2, 'pname_source': 3, 'writable_array': True}
    if name in ('glGetPixelMapfv', 'glGetPixelMapuiv', 'glGetPixelMapusv'):
        result[1] = {'gl_extent': 17, 'pname_source': 0, 'writable_array': True, 'pixel_buffer': 'pack'}
    if name in ('glGetMapdv', 'glGetMapfv', 'glGetMapiv'):
        result[2] = {'gl_evaluator_result': True, 'target_source': 0, 'query_source': 1, 'writable_array': True}
    if name in ('glMap1d', 'glMap1f'):
        result[5] = {'gl_evaluator_input': True, 'target_source': 0, 'ustride_source': 3, 'uorder_source': 4}
    if name in ('glMap2d', 'glMap2f'):
        result[9] = {'gl_evaluator_input': True, 'target_source': 0, 'ustride_source': 3, 'uorder_source': 4,
                     'vstride_source': 7, 'vorder_source': 8}
    if re.fullmatch(r'glGetn(?:Map(?:d|f|i)v|PixelMap(?:f|ui|us)v)', name):
        index = len(arguments) - 1
        native = arguments[index]['type']['name']
        divisor = {'double': 8, 'float': 4, 'int': 4, 'unsigned int': 4, 'unsigned short': 2}[native]
        result[index] = {'count_source': index - 1, 'count_divisor': divisor, 'writable_array': True}
        if 'PixelMap' in name:
            result[index]['pixel_buffer'] = 'pack'
    if name in ('glClearBufferData', 'glClearBufferSubData', 'glClearNamedBufferData', 'glClearNamedBufferSubData',
                'glClearTexImage', 'glClearTexSubImage'):
        index = len(arguments) - 1
        result[index] = {'bytes': True, 'pixel_layout': True, 'unit_pixel': True, 'nullable': True,
                         'format_source': index - 2, 'pixel_type_source': index - 1}
    if name in ('glGetTexImage', 'glGetCompressedTexImage'):
        index = len(arguments) - 1
        result[index] = {'bytes': True, 'writable': True, 'pixel_buffer': 'pack',
                         'texture_readback': True, 'target_source': 0, 'mip_source': 1,
                         'compressed_readback': name == 'glGetCompressedTexImage'}
        if name == 'glGetTexImage':
            result[index].update(format_source=2, pixel_type_source=3)
    if name in ('glGetColorTable', 'glGetConvolutionFilter', 'glGetHistogram', 'glGetMinmax'):
        index = len(arguments) - 1
        family = ('glGetColorTable', 'glGetConvolutionFilter', 'glGetHistogram', 'glGetMinmax').index(name)
        result[index] = {'bytes': True, 'writable': True, 'pixel_buffer': 'pack', 'legacy_readback': family,
                         'target_source': 0, 'format_source': index - 2, 'pixel_type_source': index - 1}
    if name in ('glPolygonStipple', 'glGetPolygonStipple'):
        result[0] = {'bytes': True, 'pixel_layout': True, 'pixel_buffer': 'pack' if name.startswith('glGet') else 'unpack',
                     'width_fixed': '32', 'height_fixed': '32', 'format_fixed': 'GL_COLOR_INDEX', 'pixel_type_fixed': 'GL_BITMAP',
                     'writable': name.startswith('glGet')}
    if name == 'glBitmap':
        result[6] = {'bytes': True, 'pixel_layout': True, 'pixel_buffer': 'unpack',
                     'width_source': 0, 'height_source': 1, 'format_fixed': 'GL_COLOR_INDEX', 'pixel_type_fixed': 'GL_BITMAP'}
    legacy = re.fullmatch(r'gl(?:Get)?(Fog|Light|LightModel|Material|PointParameter|TexEnv|TexGen|ColorTableParameter|ConvolutionParameter|HistogramParameter|MinmaxParameter)(?:d|f|i)v', name)
    if legacy:
        family = {'Fog': 'fog', 'Light': 'light', 'LightModel': 'light_model',
                  'Material': 'material', 'PointParameter': 'point', 'TexEnv': 'tex_env', 'TexGen': 'tex_gen',
                  'ColorTableParameter': 'color_table', 'ConvolutionParameter': 'convolution',
                  'HistogramParameter': 'histogram', 'MinmaxParameter': 'minmax'}[legacy[1]]
        result[len(arguments) - 1] = {'gl_extent': 6 + LEGACY_FAMILIES.index(family),
            'pname_source': len(arguments) - 2, 'writable_array': name.startswith('glGet')}
    state = name in ('glGetBooleanv', 'glGetFloatv', 'glGetDoublev', 'glGetIntegerv', 'glGetInteger64v',
                    'glGetBooleani_v', 'glGetIntegeri_v', 'glGetInteger64i_v', 'glGetFloati_v', 'glGetDoublei_v')
    if state:
        result[len(arguments) - 1] = {'gl_extent': 0, 'pname_source': 0, 'writable_array': True}
    elif name == 'glPatchParameterfv':
        result[1] = {'gl_extent': 0, 'pname_source': 0}
    elif name == 'glGetProgramiv':
        result[2] = {'gl_extent': 1, 'pname_source': 1, 'writable_array': True}
    elif name == 'glGetActiveUniformBlockiv':
        result[3] = {'gl_extent': 5, 'pname_source': 2, 'program_source': 0, 'block_source': 1, 'writable_array': True}
    elif re.fullmatch(r'gl(?:Get)?(?:Tex|Texture|Sampler)Parameter(?:Iiv|Iuiv|fv|iv)', name):
        result[2] = {'gl_extent': 3 if 'Sampler' in name else 2, 'pname_source': 1,
                     'writable_array': name.startswith('glGet')}
    elif name in ('glClearBufferfv', 'glClearBufferiv', 'glClearBufferuiv'):
        result[2] = {'gl_extent': 4, 'pname_source': 0}
    elif name in ('glClearNamedFramebufferfv', 'glClearNamedFramebufferiv', 'glClearNamedFramebufferuiv'):
        result[3] = {'gl_extent': 4, 'pname_source': 1}
    elif name in ('glGetUniformfv', 'glGetUniformiv', 'glGetUniformuiv', 'glGetUniformdv'):
        # Each location identifies one scalar/vector/matrix, including one
        # indexed array element. The largest GLSL value is a 4x4 matrix.
        result[2] = {'minimum_size': 16, 'writable_array': True}
    elif name == 'glGetVertexAttribLdv':
        result[2] = {'minimum_size': 4, 'writable_array': True}
    elif name in ('glDepthRangeArrayv', 'glScissorArrayv', 'glViewportArrayv'):
        result[2] = {'count_source': 1, 'multiplier': 2 if name == 'glDepthRangeArrayv' else 4}
    elif name == 'glVertexArrayVertexBuffers':
        result.update({i: {'count_source': 2} for i in (3, 4, 5)})
    pixels = {
        'glReadPixels': (2, 3, None, 4, 5, 6),
        'glDrawPixels': (0, 1, None, 2, 3, 4),
        'glTexImage1D': (3, None, None, 5, 6, 7),
        'glTexSubImage1D': (3, None, None, 4, 5, 6),
        'glTexImage2D': (3, 4, None, 6, 7, 8),
        'glTexSubImage2D': (4, 5, None, 6, 7, 8),
        'glTexImage3D': (3, 4, 5, 7, 8, 9),
        'glTexSubImage3D': (5, 6, 7, 8, 9, 10),
        'glTextureSubImage1D': (3, None, None, 4, 5, 6),
        'glTextureSubImage2D': (4, 5, None, 6, 7, 8),
        'glTextureSubImage3D': (5, 6, 7, 8, 9, 10),
        'glColorTable': (2, None, None, 3, 4, 5),
        'glColorSubTable': (2, None, None, 3, 4, 5),
        'glConvolutionFilter1D': (2, None, None, 3, 4, 5),
        'glConvolutionFilter2D': (2, 3, None, 4, 5, 6),
    }
    if name in pixels:
        width, height, depth, format, typ, data = pixels[name]
        policy = {'bytes': True, 'pixel_layout': True, 'pixel_buffer': 'pack' if name == 'glReadPixels' else 'unpack',
                  'width_source': width, 'format_source': format, 'pixel_type_source': typ,
                  'writable': name == 'glReadPixels', 'nullable': name in ('glTexImage1D', 'glTexImage2D', 'glTexImage3D')}
        if height is not None:
            policy['height_source'] = height
        if depth is not None:
            policy['depth_source'] = depth
        result[data] = policy
    if name.startswith(('glDrawElements', 'glDrawRangeElements')) and 'Indirect' not in name:
        count, typ, data = (3, 4, 5) if name.startswith('glDrawRangeElements') else (1, 2, 3)
        result[data] = {'bytes': True, 'client_indices': True, 'index_count_source': count, 'index_type_source': typ}
    return result


def before_call(g, method):
    f = method['function']
    if f['declaring_class'].startswith(('QOpenGLFunctions', 'QOpenGLExtraFunctions')) and f['name'].startswith('gl'):
        return ['if (!initialize_gl_functions(r, self)) return true;']
    return []


def cpp(g):
    policies = [t.get('buffer', {}) for m in g.methods for t in m['args']]
    extra = Path(__file__).with_name('templates').joinpath('gl_buffers.cpp').read_text() if any(
        any(key in p for key in ('pixel_layout', 'texture_layout', 'compressed_layout', 'client_indices', 'gpu_offset',
                                'gl_evaluator_result', 'gl_evaluator_input', 'texture_readback', 'legacy_readback', 'gpu_indices_array')) for p in policies) else ''
    if any(p.get('gl_evaluator_result') or p.get('gl_evaluator_input') for p in policies):
        extra += Path(__file__).with_name('templates').joinpath('gl_evaluators.cpp').read_text()
    if any(p.get('texture_readback') or 'legacy_readback' in p for p in policies):
        extra += Path(__file__).with_name('templates').joinpath('gl_readbacks.cpp').read_text()
    if any(before_call(g, method) for method in g.methods):
        extra = '''template<class T> static bool initialize_gl_functions(BqtRequest *r, T *functions) {
    if (!check_graphics_context(r)) return false;
    if constexpr (std::is_same_v<decltype(functions->T::initializeOpenGLFunctions()), bool>) {
        if (!functions->T::initializeOpenGLFunctions()) {
            fail(r, ENOTSUP, "Current context does not support this OpenGL function version"); return false;
        }
    } else functions->T::initializeOpenGLFunctions();
    return true;
}
''' + extra
    if any(p.get('texture_layout') or p.get('texture_compressed') for p in policies):
        extra += Path(__file__).with_name('templates').joinpath('gl_texture_buffers.cpp').read_text()
    if not any('gl_extent' in p for p in policies):
        return extra
    lines = ['static qsizetype gl_buffer_extent(BqtRequest *r, int family, GLenum pname, GLuint program = 0, GLuint block = 0, GLenum stage = 0) {',
             '    if (!check_graphics_context(r)) return -1;', '    switch (family) {']
    for number, family in enumerate(('state', 'program', 'texture', 'sampler')):
        lines += [f'    case {number}: switch (pname) {{']
        emitted = set()
        for name, item in sorted(QUERIES[family].items()):
            value = item['enum']
            if value in emitted:
                continue
            emitted.add(value)
            length = item['length']
            lines += [f'        case {value}u: // {name}']
            if isinstance(length, int):
                lines += [f'            return {length};']
            else:
                lines += ['        { GLint count = 0;',
                          f'          QOpenGLContext::currentContext()->functions()->glGetIntegerv({item["count_enum"]}u, &count);',
                          '          if (count < 0) { fail(r, ERANGE, "OpenGL returned a negative state array size"); return -1; }',
                          '          return count; }']
        lines += ['        default: break;', '        } break;']
    for number, family in enumerate(LEGACY_FAMILIES, 6):
        lines += [f'    case {number}: switch (pname) {{']
        for name, item in sorted(LEGACY_QUERIES[family].items()):
            lines += [f'        case {item["enum"]}u: return {item["length"]}; // {name}']
        lines += ['        default: break;', '        } break;']
    lines += ['    case 4: switch (pname) {', '        case GL_COLOR: return 4;',
              '        case GL_DEPTH: case GL_STENCIL: return 1;', '        default: break;', '        } break;',
              '    case 5: switch (pname) {',
              '        case GL_UNIFORM_BLOCK_ACTIVE_UNIFORM_INDICES: {',
              '            GLint count = 0;',
              '            QOpenGLContext::currentContext()->extraFunctions()->glGetActiveUniformBlockiv(program, block, GL_UNIFORM_BLOCK_ACTIVE_UNIFORMS, &count);',
              '            if (count < 0) { fail(r, ERANGE, "Uniform block has a negative active-uniform count"); return -1; }',
              '            return count; }',
              '        case GL_UNIFORM_BLOCK_BINDING: case GL_UNIFORM_BLOCK_DATA_SIZE: case GL_UNIFORM_BLOCK_NAME_LENGTH:',
              '        case GL_UNIFORM_BLOCK_ACTIVE_UNIFORMS: case GL_UNIFORM_BLOCK_REFERENCED_BY_VERTEX_SHADER:',
              '        case GL_UNIFORM_BLOCK_REFERENCED_BY_TESS_CONTROL_SHADER: case GL_UNIFORM_BLOCK_REFERENCED_BY_TESS_EVALUATION_SHADER:',
              '        case GL_UNIFORM_BLOCK_REFERENCED_BY_GEOMETRY_SHADER: case GL_UNIFORM_BLOCK_REFERENCED_BY_FRAGMENT_SHADER:',
              '        case GL_UNIFORM_BLOCK_REFERENCED_BY_COMPUTE_SHADER: return 1;',
              '        default: break;', '        } break;',
              '    case 17: { GLenum size = 0; switch (pname) {']
    for suffix in ('I_TO_I', 'S_TO_S', 'I_TO_R', 'I_TO_G', 'I_TO_B', 'I_TO_A', 'R_TO_R', 'G_TO_G', 'B_TO_B', 'A_TO_A'):
        lines.append(f'        case GL_PIXEL_MAP_{suffix}: size = GL_PIXEL_MAP_{suffix}_SIZE; break;')
    lines += ['        default: return fail(r, EINVAL, "Unknown OpenGL pixel map"), -1;', '        }',
              '        GLint count = 0; QOpenGLContext::currentContext()->functions()->glGetIntegerv(size, &count);',
              '        if (count < 0) return fail(r, ERANGE, "Negative OpenGL pixel map size"), -1;',
              '        return count;', '    }',
              '    case 18: switch (pname) {',
              '        case GL_ATOMIC_COUNTER_BUFFER_BINDING: case GL_ATOMIC_COUNTER_BUFFER_DATA_SIZE:',
              '        case GL_ATOMIC_COUNTER_BUFFER_ACTIVE_ATOMIC_COUNTERS:',
              '        case GL_ATOMIC_COUNTER_BUFFER_REFERENCED_BY_VERTEX_SHADER:',
              '        case GL_ATOMIC_COUNTER_BUFFER_REFERENCED_BY_TESS_CONTROL_SHADER:',
              '        case GL_ATOMIC_COUNTER_BUFFER_REFERENCED_BY_TESS_EVALUATION_SHADER:',
              '        case GL_ATOMIC_COUNTER_BUFFER_REFERENCED_BY_GEOMETRY_SHADER:',
              '        case GL_ATOMIC_COUNTER_BUFFER_REFERENCED_BY_FRAGMENT_SHADER:',
              '        case GL_ATOMIC_COUNTER_BUFFER_REFERENCED_BY_COMPUTE_SHADER: return 1;',
              '        case GL_ATOMIC_COUNTER_BUFFER_ACTIVE_ATOMIC_COUNTER_INDICES: {',
              '            const auto query = reinterpret_cast<void (*)(GLuint, GLuint, GLenum, GLint *)>(QOpenGLContext::currentContext()->getProcAddress("glGetActiveAtomicCounterBufferiv"));',
              '            if (!query) return fail(r, ENOTSUP, "Context has no atomic-counter buffer queries"), -1;',
              '            GLint count = 0; query(program, block, GL_ATOMIC_COUNTER_BUFFER_ACTIVE_ATOMIC_COUNTERS, &count);',
              '            if (count < 0) return fail(r, ERANGE, "Negative active atomic-counter count"), -1;',
              '            return count; }',
              '        default: break;', '        } break;',
              '    case 19: switch (pname) {',
              '        case GL_NUM_COMPATIBLE_SUBROUTINES: case GL_UNIFORM_SIZE: case GL_UNIFORM_NAME_LENGTH: return 1;',
              '        case GL_COMPATIBLE_SUBROUTINES: {',
              '            const auto query = reinterpret_cast<void (*)(GLuint, GLenum, GLuint, GLenum, GLint *)>(QOpenGLContext::currentContext()->getProcAddress("glGetActiveSubroutineUniformiv"));',
              '            if (!query) return fail(r, ENOTSUP, "Context has no shader subroutine queries"), -1;',
              '            GLint count = 0; query(program, stage, block, GL_NUM_COMPATIBLE_SUBROUTINES, &count);',
              '            if (count < 0) return fail(r, ERANGE, "Negative compatible shader-subroutine count"), -1;',
              '            return count; }',
              '        default: break;', '        } break;',
              '    }', '    fail(r, ENOTSUP, "OpenGL selector has no audited buffer extent");',
              '    return -1;', '}']
    return extra + '\n'.join(lines) + '\n'
