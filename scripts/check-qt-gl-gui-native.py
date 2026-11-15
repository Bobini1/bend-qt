#!/usr/bin/env python3
"""Exercise generated QtGui GL mappings with no QtOpenGL module selected."""
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


def verify_dependencies(executable, env, output):
    dynamic = subprocess.run(['readelf', '-d', str(executable)], text=True, capture_output=True, check=True)
    linked = subprocess.run(['ldd', str(executable)], env=env, text=True, capture_output=True, check=True)
    (output / 'dynamic-dependencies.log').write_text(dynamic.stdout + linked.stdout + linked.stderr)
    needed = re.findall(r'\(NEEDED\).*?\[([^]]+)\]', dynamic.stdout)
    if 'libQt6OpenGL' in dynamic.stdout + linked.stdout:
        raise RuntimeError('QtGui-only GL fixture unexpectedly depends on Qt6OpenGL')
    if 'not found' in linked.stdout:
        raise RuntimeError('QtGui-only GL fixture has an unresolved native dependency')
    return dict(direct_needed=needed, qt_opengl_absent_from_transitive_dependencies=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--qt-root', type=Path, default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    args = parser.parse_args()
    source = args.work / 'wrappers.cpp'
    text = source.read_text()
    if 'NativeTraits<QOpenGLBuffer>' in text:
        raise RuntimeError('This fixture requires a profile without QtOpenGL/QOpenGLBuffer')
    functions = re.findall(r'static bool [^\n]*?(bqt_op_\d+)\(BqtRequest \*r\) \{\n(.*?)\n\}', text, re.S)
    selectors = {
        'RANGE': ('get<QOpenGLExtraFunctions>', 'return raw_gl_mapping_request', 'false, 2,'),
        'GET': ('get<QOpenGLExtraFunctions>', 'return raw_gl_mapping_request', 'false, 0,'),
        'UNMAP': ('get<QOpenGLExtraFunctions>', '->glUnmapBuffer('),
        'DELETE': ('get<QOpenGLExtraFunctions>', '->glDeleteBuffers('),
        'READ': ('get<MemoryView>', 'Memory view read exceeds'),
        'WRITE': ('get<MemoryView>', 'Memory view write exceeds'),
        'SIZE': ('get<MemoryView>', 'r->result = wide_value(view->size)'),
    }
    definitions = []
    for name, fragments in selectors.items():
        matches = [function for function, body in functions if all(fragment in body for fragment in fragments)]
        if len(matches) != 1:
            raise RuntimeError(f'Expected one QtGui raw mapping operation {name}: {matches}')
        definitions += ['-DBQT_GL_GUI_' + name + '=' + matches[0]]
    for name, macro in [('QOpenGLExtraFunctions', 'FUNCTIONS'), ('QByteArray', 'BYTES')]:
        ids = set(re.findall(r'get<' + name + r'>\(r, (?:r->self|r->arguments\[\d+\]\.word), (\d+)', text))
        if len(ids) != 1:
            raise RuntimeError(f'Expected one generated type identifier for {name}: {ids}')
        definitions += ['-DBQT_GL_GUI_' + macro + '_TYPE=' + ids.pop()]
    output = args.work / 'gui-gl-native-check'; output.mkdir(exist_ok=True)
    modules = ['QtCore', 'QtGui', 'QtWidgets', 'QtXml']
    flags = [flag for flag in compiler_flags(args.qt_root, 'clang++-19', modules) if flag not in ('-O1', '-DNDEBUG')]
    executable = output / 'native-check'
    command = [*flags, '-O0', '-Wno-deprecated-declarations', *definitions,
               '-DBQT_GENERATED_WRAPPERS=' + json.dumps(str(source.resolve())),
               str(ROOT / 'examples/qt612/gl-gui-profile-native.cpp'),
               '-L' + str(args.qt_root / 'lib'), *['-lQt6' + module[2:] for module in reversed(modules)],
               '-o', str(executable)]
    compiled = subprocess.run(command, text=True, capture_output=True)
    (output / 'build.log').write_text(compiled.stdout + compiled.stderr)
    if compiled.returncode:
        raise RuntimeError(f'QtGui raw mapping fixture failed to compile: {output / "build.log"}')
    env = dict(os.environ, LD_LIBRARY_PATH=str(args.qt_root / 'lib'), QT_QPA_PLATFORM='offscreen',
               QT_PLUGIN_PATH=str(args.qt_root / 'plugins'), QT_QPA_PLATFORM_PLUGIN_PATH=str(args.qt_root / 'plugins/platforms'))
    dependencies = verify_dependencies(executable, env, output)
    result = subprocess.run([str(executable)], env=env, text=True, capture_output=True, timeout=30)
    (output / 'run.log').write_text(result.stdout + result.stderr)
    if result.returncode or 'QT612_GUI_ONLY_RAW_GL_OK' not in result.stdout:
        raise RuntimeError(f'QtGui raw mapping fixture failed: {output / "run.log"}')
    (output / 'receipt.json').write_text(json.dumps(dict(wrappers_sha256=hashlib.sha256(text.encode()).hexdigest(),
        qt_modules=modules, dependencies=dependencies, passed=True, stdout=result.stdout.strip()), indent=2) + '\n')
    print(result.stdout.strip())


if __name__ == '__main__':
    main()
