"""Prepare runtime data from exact source evidence and generated QML metadata.

Generated qmldir files are tied to the upstream module declaration and the
matching Qt CMake emitter. Their deployment/license boundary also includes the
owning Qt component; a code generator's license never substitutes for it.
"""
import hashlib
import json
from contextlib import ExitStack
from pathlib import Path
import re
import tarfile

from qt_licenses import Inventory, allows


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def cmake_sources(sources):
    result = []
    from source_licensing import Resolver
    with ExitStack() as stack:
      reuse = stack.enter_context(Resolver(sources))
      for location, source in sources.items():
        if digest(source['file']) != source['sha256']:
            raise ValueError('A metadata source archive changed: ' + location)
        with tarfile.open(source['file'], 'r|*') as archive:
            for member in archive:
                if not member.isfile() or not (member.name.endswith('/CMakeLists.txt')
                        or member.name.endswith(('.cmake', '.cmake.in'))):
                    continue
                raw = archive.extractfile(member).read()
                text = raw.decode('utf-8')
                if not re.search(r'\bURI\s+', text) and not member.name.endswith(
                        ('Qt6QmlMacros.cmake', 'Qt6qmldirTemplate.cmake.in')):
                    continue
                license = re.findall(r'SPDX-License-Identifier:\s*([^\r\n]+)', text)
                # Resolve only simple, local literal variables. Evaluating
                # arbitrary CMake is unnecessary for metadata provenance.
                literals = dict(re.findall(r'\bset\(\s*(\w+)\s+"([^"${};]*)"\s*\)', text))
                expanded = re.sub(r'\$\{(\w+)\}', lambda match: literals.get(match[1], match[0]), text)
                uris = re.findall(r'\bURI\s+"?([A-Za-z_][A-Za-z0-9_.]*)"?(?=\s|\))', expanded)
                relative = member.name.partition('/')[2]
                expression = license[0] if len(license) == 1 else None
                if not license and uris:
                    project_root, metadata = reuse.project(location)
                    expressions = sorted({str(value) for info in metadata.reuse_info_of(project_root / relative)
                                          for value in info.spdx_expressions})
                    expression = ' AND '.join('(' + value + ')' for value in expressions) if expressions else None
                result.append(dict(source=location, path=relative,
                    sha256=hashlib.sha256(raw).hexdigest(), expression=expression,
                    uris=uris))
    return result


def qmldir_uri(text):
    uri = None
    directives = {
        'module': r'[A-Za-z_][A-Za-z0-9_.]*',
        'linktarget': r'[A-Za-z_][A-Za-z0-9_:]*',
        'classname': r'[A-Za-z_][A-Za-z0-9_:]*',
        'typeinfo': r'[A-Za-z0-9_.-]+',
        'prefer': r':/[^\s]*',
        'plugin': r'[A-Za-z0-9_.-]+(?: [A-Za-z0-9_./-]+)?',
        'import': r'[A-Za-z_][A-Za-z0-9_.]*(?: (?:auto|[0-9]+(?:\.[0-9]+)?))?',
        'depends': r'[A-Za-z_][A-Za-z0-9_.]*(?: (?:auto|[0-9]+(?:\.[0-9]+)?))?',
    }
    for line in text.splitlines():
        if not line or line.startswith('#'):
            continue
        normalized = re.sub(r'^(?:optional|default) ', '', line)
        key, _, value = normalized.partition(' ')
        if key in directives and re.fullmatch(directives[key], value):
            if key == 'module':
                if uri is not None:
                    raise ValueError('Duplicate qmldir module declaration')
                uri = value
            continue
        if line in ('designersupported', 'static', 'system'):
            continue
        if re.fullmatch(r'(?:(?:singleton|internal) )?[A-Za-z_][A-Za-z0-9_]*(?: [0-9]+\.[0-9]+)? [A-Za-z0-9_./+-]+\.(?:qml|js|mjs)', line):
            continue
        raise ValueError('Unrecognized generated qmldir directive: ' + line)
    if uri is None:
        raise ValueError('Missing qmldir module declaration')
    return uri


def qml_imports(path):
    if path.name == 'qmldir':
        rows = re.findall(r'^(?:(optional|default) )?(?:depends|import) ([A-Za-z_][A-Za-z0-9_.]*)', path.read_text(), re.M)
        return [dict(uri=uri, optional=mode == 'optional') for mode, uri in rows]
    if path.suffix in ('.qml', '.js', '.mjs'):
        # Documentation examples and string literals are not QML imports.
        text = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`|//[^\n]*|/\*.*?\*/',
            lambda match: ('""' if match[0][0] in ('"', "'", '`') else '') + '\n' * match[0].count('\n'), path.read_text(), flags=re.S)
        return [dict(uri=uri, optional=False) for uri in sorted(set(re.findall(
            r'^\s*\.?import\s+([A-Za-z_][A-Za-z0-9_.]*)', text, re.M)))]
    return []


def prepare(qt, profile, sources, audit):
    qt = Path(qt).resolve()
    inventory = Inventory(qt)
    for name, expected in audit['evidence_sha256'].items():
        if digest(name) != expected:
            raise ValueError('Runtime asset audit evidence changed: ' + name)
    selected = set(profile['qt_modules'])
    modules, expressions, runtime_expressions = {}, {}, {}
    for module, row in inventory.modules.items():
        for root in inventory.repositories.get(row['evidence'], []):
            location = root['downloadLocation']
            if module in selected:
                modules.setdefault(location, set()).add(module)
                expressions.setdefault(location, set()).add(row['expression'])
            elif (qt / 'lib' / ('libQt6' + module[2:] + '.so.6')).is_file():
                runtime_expressions.setdefault(location, set()).add(row['expression'])
    for location, values in runtime_expressions.items():
        expressions.setdefault(location, values)
    assets, exclusions = {}, {}
    generated = cmake_sources(sources)
    tool_uris = {uri for row in generated if row['path'].startswith('tools/') for uri in row['uris']}
    tool_directories = [path.parent for path in (qt / 'qml').rglob('qmldir')
                        if qmldir_uri(path.read_text()) in tool_uris]

    def excluded(path):
        if any(path.is_relative_to(directory) for directory in tool_directories):
            return 'QML assets for a standalone Qt developer tool; its application registers the required tool-specific types'
        if path.suffix in ('.o', '.a', '.prl', '.cmake'):
            return 'Maintainer or static-link development file; not loaded by the dynamic application runtime'
        if path.suffix == '.qmltypes':
            return 'QML tooling type description; runtime resolves native types through their plugins and metaobjects'
        if 'designer' in path.relative_to(qt).parts:
            return 'Qt Quick Designer metadata and assets; not consumed by the application QML runtime'
        return None

    def add(name, origins, expression, provenance):
        missing = set(origins) - set(sources)
        if missing or not origins:
            raise ValueError('Missing runtime asset source snapshots: ' + repr(missing or name))
        if allows(expression, profile['license_flavor']) is not True:
            raise ValueError('No permitted runtime asset license: ' + name)
        ownership = sorted(set().union(*(modules.get(location, set()) for location in origins)))
        assets[name] = dict(file=str(qt / name), sha256=digest(qt / name),
            expression=expression, source=origins[0], sources=origins, modules=ownership,
            qml_imports=qml_imports(qt / name), provenance=provenance)

    for row in audit['included']:
        name = row['path']; path = qt / name
        if reason := excluded(path):
            exclusions[name] = dict(sha256=digest(path), reason=reason)
            continue
        if 'evidence' in row:
            evidence = row['evidence']
            if digest(path) != evidence['sha256']:
                raise ValueError('An audited installed asset changed: ' + name)
            origins = sorted({root['downloadLocation'] for root in evidence['repositories']})
            expression = evidence['expression']
        else:
            evidence = row['source']
            if digest(path) != evidence['sha256']:
                raise ValueError('An audited source asset changed: ' + name)
            candidates = evidence['candidates']
            if not candidates or any(item.get('allowed') is not True for item in candidates):
                raise ValueError('Unresolved source asset evidence: ' + name)
            origins = sorted({root['downloadLocation'] for item in candidates for root in item['repositories']})
            expression = ' AND '.join('(' + value + ')' for value in sorted({item['expression'] for item in candidates}))
        add(name, origins, expression, evidence)
    for row in [*audit['excluded'], *audit['unknown']]:
        name = row['path']; path = qt / name
        if reason := excluded(path):
            exclusions[name] = dict(sha256=digest(path), reason=reason)
            continue
        if path.name != 'qmldir':
            raise ValueError('Unresolved runtime asset: ' + name)
        uri = qmldir_uri(path.read_text())
        declarations = [item for item in generated if uri in item['uris']]
        if not declarations or len({item['sha256'] for item in declarations}) != 1:
            raise ValueError('Missing or ambiguous upstream QML module declaration: ' + uri)
        emitters = [item for item in generated if item['path'] in (
            'src/qml/Qt6QmlMacros.cmake', 'src/qml/Qt6qmldirTemplate.cmake.in')]
        if len(emitters) != 2 or not any(item['expression'] == 'BSD-3-Clause' for item in emitters):
            raise ValueError('Missing pinned Qt QML CMake emitter')
        origins = sorted({item['source'] for item in declarations})
        licenses = {item['expression'] for item in declarations}
        licenses.update(value for location in origins for value in expressions.get(location, ()))
        licenses.add('BSD-3-Clause')
        if None in licenses:
            raise ValueError('A QML module declaration lacks license evidence: ' + uri)
        add(name, origins, ' AND '.join('(' + value + ')' for value in sorted(licenses)),
            dict(kind='generated-qmldir', uri=uri, declarations=declarations, emitters=emitters,
                 installed_sha256=digest(path)))
    for top in ('qml', 'resources', 'translations'):
        for path in sorted((qt / top).rglob('*')):
            if path.is_file() and (reason := excluded(path)):
                name = path.relative_to(qt).as_posix()
                exclusions.setdefault(name, dict(sha256=digest(path), reason=reason))
    return dict(schema=1, assets=assets, excluded_assets=exclusions,
        boundary='Byte-pinned installed data, original source/REUSE expressions and generated metadata provenance; native behavior and complete release validation remain separate gates')


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qt-root', type=Path, required=True)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.qt_root, json.loads(args.profile.read_text()),
        json.loads(args.sources.read_text())['sources'], json.loads(args.audit.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print('QT_RUNTIME_DATA_PREPARED assets=' + str(len(result['assets'])) + ' excluded=' + str(len(result['excluded_assets'])))


if __name__ == '__main__':
    main()
