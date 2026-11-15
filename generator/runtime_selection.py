"""Select a relocatable runtime from actual ELF dependencies and SPDX evidence.

Module policy alone cannot filter deployment: Qt QML modules and plugins are
separate ELF objects with their own dependencies. Missing evidence is reported,
never replaced with the license of the nearest directory.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess

from qt_licenses import Inventory, allows


def elf_dependencies(path):
    result = subprocess.run(['readelf', '-d', str(path)], text=True, capture_output=True)
    if result.returncode:
        raise ValueError('Cannot inspect a runtime ELF: ' + str(path) + '\n' + result.stderr)
    return re.findall(r'\(NEEDED\).*\[(.*?)\]', result.stdout)


def select(qt, flavor, *, supplements=None):
    """Inventory runtime binaries, preloading order and unresolved evidence.

    A supplemental row must pin bytes, license, source and notice files. This
    accommodates Qt installer files omitted from its SPDX file inventory, while
    retaining an explicit, reviewable boundary for those exceptions.
    """
    qt = Path(qt).resolve(); inventory = Inventory(qt)
    supplements = supplements or {}
    records, aliases, excluded, unknown, system = {}, {}, [], [], set()
    # Installer ICU development/test libraries are not application runtimes.
    # Keep Qt libraries and actual plugin/backend entry points as roots, then
    # discover bundled third-party dependencies from their ELF metadata.
    roots = [*list((qt / 'lib').glob('libQt6*.so*')),
             *list((qt / 'lib').glob('libav*.so*')),
             *list((qt / 'lib').glob('libsw*.so*')),
             *list((qt / 'plugins').rglob('*.so')),
             *list((qt / 'qml').rglob('*.so')),
             *([qt / 'libexec/QtWebEngineProcess']
               if (qt / 'libexec/QtWebEngineProcess').exists() else [])]
    dependencies_seen, pending = set(), list(roots)
    while pending:
        path = pending.pop()
        if not path.is_file() or path.resolve() in dependencies_seen:
            continue
        dependencies_seen.add(path.resolve())
        for library in elf_dependencies(path):
            dependency = qt / 'lib' / library
            if dependency.is_file():
                pending.append(dependency)
    candidates = sorted(set([*list((qt / 'lib').glob('*.so*')),
                             *list((qt / 'plugins').rglob('*.so')),
                             *list((qt / 'qml').rglob('*.so')),
                             *([qt / 'libexec/QtWebEngineProcess']
                               if (qt / 'libexec/QtWebEngineProcess').exists() else [])]))
    for path in candidates:
        if not path.is_file():
            continue
        resolved = path.resolve()
        if resolved not in dependencies_seen:
            continue
        if not resolved.is_relative_to(qt):
            raise ValueError('A runtime binary escapes the installation: ' + str(path))
        relative = resolved.relative_to(qt).as_posix()
        alias = path.relative_to(qt).as_posix()
        if relative in records:
            if alias != relative:
                aliases[alias] = relative
            continue
        evidence = inventory.files.get(relative)
        if evidence:
            decision = allows(evidence['expression'], flavor)
            if decision is False:
                excluded.append(dict(path=relative, expression=evidence['expression'])); continue
            if decision is not True:
                unknown.append(dict(path=relative, reason='Unknown binary license expression', evidence=evidence)); continue
            row = inventory.binary(relative, flavor)
        else:
            row = supplements.get(relative)
            if not row:
                unknown.append(dict(path=relative, reason='No binary SPDX or reviewed supplemental evidence')); continue
            required = ('sha256', 'expression', 'source', 'notices')
            if any(not row.get(key) for key in required):
                raise ValueError('Incomplete runtime license supplement for ' + relative)
            if allows(row['expression'], flavor) is not True:
                excluded.append(dict(path=relative, expression=row['expression'])); continue
            if hashlib.sha256(resolved.read_bytes()).hexdigest() != row['sha256']:
                raise ValueError('Supplemental runtime binary changed: ' + relative)
            for notice in row['notices']:
                text = Path(notice['file']).read_bytes()
                if not text or hashlib.sha256(text).hexdigest() != notice['sha256']:
                    raise ValueError('Runtime license notice changed: ' + notice['file'])
            row = dict(row, path=relative, supplemental=True)
        records[relative] = row
        if alias != relative:
            aliases[alias] = relative
    # A SONAME alias can be discovered before its target. Keep only aliases
    # whose target survived policy; never retain an excluded module's alias.
    for path in candidates:
        if path.is_symlink() and path.resolve().is_relative_to(qt):
            target = path.resolve().relative_to(qt).as_posix()
            if target in records:
                aliases[path.relative_to(qt).as_posix()] = target
    missing, dependencies = [], {}
    rejected = {row['path'] for row in excluded}
    raw_dependencies = {name: elf_dependencies(qt / name) for name in records}
    # A permissively licensed adapter can still require a GPL-only module.
    # For example QtCanvas2D depends on QtCanvasPainter, and the QML spatial
    # audio adapter depends on Quick3D. Exclude that entire dependent closure.
    while True:
        dropped = []
        for name in records:
            denied = [library for library in raw_dependencies[name]
                      if (qt / 'lib' / library).exists()
                      and (qt / 'lib' / library).resolve().relative_to(qt).as_posix() in rejected]
            if denied:
                dropped.append(name)
                excluded.append(dict(path=name, expression=records[name]['expression'],
                                     reason='Depends on a license-excluded runtime', dependencies=denied))
        if not dropped:
            break
        for name in dropped:
            rejected.add(name); del records[name]
    aliases = {alias: target for alias, target in aliases.items() if target in records}
    for name in sorted(records):
        needed = raw_dependencies[name]
        dependencies[name] = []
        for library in needed:
            kit_path = qt / 'lib' / library
            if kit_path.exists():
                target = kit_path.resolve().relative_to(qt).as_posix()
                if target not in records:
                    missing.append(dict(file=name, library=library, target=target))
                else:
                    dependencies[name].append(target)
            elif library.startswith('libQt6'):
                missing.append(dict(file=name, library=library, reason='Qt dependency is absent from the kit'))
            else:
                system.add(library)
    order, active, visited = [], set(), set()

    def visit(name):
        if name in visited:
            return
        if name in active:
            raise ValueError('Cyclic runtime ELF dependencies: ' + name)
        active.add(name)
        for dependency in dependencies[name]:
            visit(dependency)
        active.remove(name); visited.add(name)
        # FFmpeg and its stubs are optional dlopen backends. Qt initializes
        # their external symbol resolvers before using them, so eager NOW
        # loading can fail even though normal Qt Multimedia loading works.
        if (name.startswith('lib/libQt6') and not name.startswith('lib/libQt6FFmpegStub')) or re.match(r'lib/libicu(?:data|i18n|uc)\.so', name):
            order.append(name)

    for name in sorted(records):
        visit(name)
    return dict(schema=1, flavor=flavor, files=records, aliases=aliases, dependencies=dependencies,
                excluded=list({row['path']: row for row in excluded}.values()),
                unknown=list({row['path']: row for row in unknown}.values()),
                unresolved_dependencies=missing, preload_order=order,
                system_dependencies=sorted(system), evidence_sha256=inventory.evidence,
                binary_selection_complete=not unknown and not missing,
                boundary='ELF runtime binaries only; QML source/resources, notices and corresponding source archives must also be selected before release')


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qt-root', type=Path, required=True)
    parser.add_argument('--flavor', choices=('lgpl', 'gpl'), required=True)
    parser.add_argument('--supplements', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    supplements = json.loads(args.supplements.read_text()) if args.supplements else None
    result = select(args.qt_root, args.flavor, supplements=supplements)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f'Runtime {args.flavor}: {len(result["files"])} binaries, '
          f'{len(result["excluded"])} excluded, {len(result["unknown"])} missing license evidence, '
          f'{len(result["unresolved_dependencies"])} unresolved dependencies')


if __name__ == '__main__':
    main()
