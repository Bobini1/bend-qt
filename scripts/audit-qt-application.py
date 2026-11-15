#!/usr/bin/env python3
"""Inventory a C++/QML application's Qt call sites for native wrapper verification.

This is a source inventory, not proof that a class or feature works. It keeps
call sites, properties, virtuals and QML imports so the behavioral audit can
attach native consumer fixtures to concrete application requirements.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
LEXICAL = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', re.S)
MACROS = ('Q_OBJECT', 'Q_GADGET', 'Q_NAMESPACE', 'Q_ENUM', 'Q_FLAG', 'Q_INVOKABLE',
          'Q_PLUGIN_METADATA', 'Q_INTERFACES', 'QML_ELEMENT', 'QML_NAMED_ELEMENT',
          'QML_SINGLETON', 'QML_VALUE_TYPE', 'QML_ATTACHED', 'QML_EXTENDED', 'QML_FOREIGN')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/qt-application-audit/source-inventory.json')
    parser.add_argument('--qt-root', type=Path, default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    args = parser.parse_args()
    project = args.project.resolve()
    if not (project / 'CMakeLists.txt').is_file():
        raise ValueError('Point --project at a CMake application source checkout')
    sites = {key: defaultdict(list) for key in ('includes', 'types', 'static_calls', 'macros', 'virtuals', 'qml_imports')}
    properties, sources = [], {}
    import os
    paths = []
    for folder, directories, files in os.walk(project):
        directories[:] = [name for name in directories if name not in
                           ('.git', 'build', 'node_modules', '.cache', 'vcpkg_installed')]
        paths.extend(Path(folder) / name for name in files
                     if Path(name).suffix.lower() in ('.h', '.hpp', '.cpp', '.qml'))
    paths.sort()
    def add(category, name, relative, text, offset):
        sites[category][name].append(dict(file=relative, line=text.count('\n', 0, offset) + 1))
    for path in paths:
        data = path.read_bytes()
        text = data.decode('utf-8-sig', errors='replace')
        relative = path.relative_to(project).as_posix()
        sources[relative] = hashlib.sha256(data).hexdigest()
        code = LEXICAL.sub(lambda match: ''.join('\n' if char == '\n' else ' ' for char in match[0]), text)
        if path.suffix.lower() == '.qml':
            for match in re.finditer(r'^\s*import\s+(Qt[A-Za-z0-9_.]+)(?:\s+([0-9.]+))?', text, re.M):
                add('qml_imports', match[1], relative, text, match.start())
            continue
        for match in re.finditer(r'^\s*#\s*include\s*[<"]([^>"]+)[>"]', text, re.M):
            if match[1].startswith(('Q', 'q')):
                add('includes', match[1], relative, text, match.start())
        for match in re.finditer(r'\bQ[A-Z][A-Za-z0-9_]*\b', code):
            add('types', match[0], relative, code, match.start())
        for match in re.finditer(r'\b((?:Q[A-Za-z0-9_]+|Qt|QtConcurrent)(?:::[A-Za-z_][A-Za-z0-9_]*)*)::([A-Za-z_][A-Za-z0-9_]*)\s*\(', code):
            add('static_calls', match[1] + '::' + match[2], relative, code, match.start())
        for name in MACROS:
            for match in re.finditer(r'\b' + name + r'\b', code):
                add('macros', name, relative, code, match.start())
        for match in re.finditer(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*\([^;{}]*\)\s*(?:const\s*)?(?:noexcept\s*)?(?:->[^;{}]+)?\boverride\b', code):
            add('virtuals', match[1], relative, code, match.start())
        for match in re.finditer(r'\bQ_PROPERTY\s*\(', code):
            begin, depth, end = match.end(), 1, match.end()
            while depth and end < len(code):
                depth += (code[end] == '(') - (code[end] == ')')
                end += 1
            if depth:
                raise ValueError('Unclosed Q_PROPERTY in ' + relative)
            declaration = re.sub(r'\s+', ' ', code[begin:end - 1]).strip()
            properties.append(dict(file=relative, line=code.count('\n', 0, match.start()) + 1,
                declaration=declaration, attributes=re.findall(
                    r'\b(?:READ|WRITE|MEMBER|RESET|NOTIFY|REVISION|DESIGNABLE|SCRIPTABLE|STORED|USER|BINDABLE|CONSTANT|FINAL|REQUIRED)\b', declaration)))
    coverage_path = ROOT / 'packages/qt612/coverage.json'
    coverage = json.loads(coverage_path.read_text())
    classes = set(coverage['classes'])
    candidates = {name: dict(generated_class=name in classes, sites=rows)
                  for name, rows in sorted(sites['types'].items())}
    qml = {name: dict(installed_runtime_path=str(args.qt_root / 'qml' / name.replace('.', '/')),
                     installed=(args.qt_root / 'qml' / name.replace('.', '/')).is_dir(), sites=rows)
           for name, rows in sorted(sites['qml_imports'].items())}
    qt_version_file = args.qt_root / 'lib/cmake/Qt6Core/Qt6CoreConfigVersionImpl.cmake'
    version = re.search(r'set\(PACKAGE_VERSION "([^"]+)"\)', qt_version_file.read_text()) if qt_version_file.exists() else None
    revision = subprocess.run(['git', '-c', 'safe.directory=' + str(project), '-C', str(project),
                               'rev-parse', 'HEAD'], check=True, capture_output=True, text=True).stdout.strip()
    report = dict(schema=1, verification_complete=False,
        boundary='Source inventory and generated-name lookup only; each feature still needs behavioral review and native Bend integration evidence',
        project=str(project), revision=revision, configured_qt=version[1] if version else None,
        source_sha256=sources, generated_coverage_sha256=hashlib.sha256(coverage_path.read_bytes()).hexdigest(),
        generated_coverage_may_be_stale=True,
        source_files=len(sources), qt_types=candidates, properties=properties, qml_imports=qml,
        **{key: dict(sorted(value.items())) for key, value in sites.items() if key not in ('types', 'qml_imports')})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print('QT_APPLICATION_INVENTORY_WRITTEN verification_complete=false')


if __name__ == '__main__':
    main()
