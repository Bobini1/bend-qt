#!/usr/bin/env python3
"""Check full module planning, automatic scopes and runtime ownership guards."""
import argparse
import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
from distribution_modules import plan, runtime_owners
from module_partitions import scoped_api
from qt_licenses import Inventory, allows
from runtime_selection import elf_dependencies
from runtime_assets import qml_imports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qt-root', type=Path, default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    parser.add_argument('--work', type=Path, default=ROOT / 'build/distribution-modules-check')
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    (args.work / 'receipt.json').write_text('{"verification_complete":false}\n')
    profile = json.loads((ROOT / 'generator/qt612/profile.json').read_text())
    groups = plan(profile, args.qt_root)
    assert profile['package_name'] == 'qt'
    assert {'Graphs', 'Charts', 'DataVisualization'} <= {row['name'] for row in groups}
    assert set().union(*(set(row['qt_modules']) for row in groups)) == set(profile['qt_modules'])
    inventory = Inventory(args.qt_root)
    assert all(allows(inventory.modules[name]['expression'], 'lgpl') is True for name in groups[0]['qt_modules'])
    restricted = {name for row in groups[1:] for name in row['qt_modules']}
    assert {'QtGraphs', 'QtCharts', 'QtDataVisualization', 'QtQuick3D'} <= restricted
    # A copied profile can narrow its module selection without pruning the
    # optional group catalogue by hand.
    small = plan(dict(profile, qt_modules=['QtCore', 'QtGui', 'QtWidgets', 'QtXml']), args.qt_root)
    assert len(small) == 1 and small[0]['qt_modules'] == ['QtCore', 'QtGui', 'QtWidgets', 'QtXml']
    api = json.loads((ROOT / 'build/qt612/api.json').read_text())
    own = {'PySide6.QtGraphs', 'PySide6.QtGraphsWidgets'}
    scoped = scoped_api(api, ['QtGraphs', 'QtGraphsWidgets'])
    expected = {row['name'] for row in api['classes'] if row.get('package') in own}
    names = {row['name'] for row in scoped['classes']}
    assert expected <= names and len(names) < len(api['classes'])
    assert {'QObject', 'QQuickItem'} <= names
    assert 'QWebEngineView' not in names
    parts = [SimpleNamespace(name='base', owned_modules=['QtCore']),
             SimpleNamespace(name='Graphs', owned_modules=['QtGraphs'])]
    files, dependencies = {}, {}

    def visit(path):
        real = path.resolve(); relative = real.relative_to(args.qt_root).as_posix()
        if relative in files:
            return
        evidence = inventory.files.get(relative)
        # ICU is outside Qt's installer SPDX file list. This control exercises
        # ownership with its known permissive classification; the release
        # gate independently requires its pinned supplemental notice/source.
        files[relative] = evidence or dict(expression='MIT')
        dependencies[relative] = []
        for name in elf_dependencies(real):
            child = args.qt_root / 'lib' / name
            if child.is_file():
                visit(child)
                dependencies[relative].append(child.resolve().relative_to(args.qt_root).as_posix())

    for name in ('QtCore', 'QtGraphs'):
        visit(args.qt_root / 'lib' / ('lib' + name.replace('Qt', 'Qt6', 1) + '.so.6'))
    prepared = dict(selection=dict(files=files, dependencies=dependencies),
                    files={name: args.qt_root / name for name in files}, manifest=dict(assets={}))
    owners = runtime_owners(prepared, parts, args.qt_root)
    graphs = (args.qt_root / 'lib/libQt6Graphs.so.6').resolve().relative_to(args.qt_root).as_posix()
    core = (args.qt_root / 'lib/libQt6Core.so.6').resolve().relative_to(args.qt_root).as_posix()
    assert owners[graphs] == {'Graphs'} and owners[core] == {'base', 'Graphs'}
    # A dependency-only GPL library can be required by an optional module.
    # Its plugin must follow that owner, while a shared Core dependency must
    # not make an ordinary base plugin optional.
    plugins = copy.deepcopy(prepared)
    dependency = 'lib/libQt6FixtureDependency.so.6'
    optional_plugin, base_plugin = 'qml/Fixture/liboptional.so', 'plugins/fixture/libbase.so'
    for name, expression, children in (
            (dependency, 'GPL-3.0-only', [core]),
            (optional_plugin, 'GPL-3.0-only', [dependency, core]),
            (base_plugin, 'LGPL-3.0-only', [core])):
        plugins['selection']['files'][name] = dict(expression=expression)
        plugins['selection']['dependencies'][name] = children
        plugins['files'][name] = Path('/unused-test-source')
    plugins['selection']['files'][optional_plugin]['evidence'] = inventory.modules['QtCore']['evidence']
    plugins['selection']['dependencies'][graphs].append(dependency)
    retained = runtime_owners(plugins, parts, args.qt_root)
    assert retained[dependency] == retained[optional_plugin] == {'Graphs'}
    assert retained[base_plugin] == {'base'}
    poisoned = copy.deepcopy(prepared)
    poisoned['selection']['dependencies'][core].append(graphs)
    try:
        runtime_owners(poisoned, parts, args.qt_root)
    except ValueError as error:
        assert 'Core-only consumer' in str(error)
    else:
        raise AssertionError('A transitive GPL dependency entered the shared module')
    data = copy.deepcopy(prepared)
    data['manifest']['assets']['qml/Restricted.qml'] = dict(expression='GPL-3.0-only', modules=['QtCore'])
    data['files']['qml/Restricted.qml'] = Path('/unused-test-source')
    try:
        runtime_owners(data, parts, args.qt_root)
    except ValueError as error:
        assert 'Core-only consumer' in str(error)
    else:
        raise AssertionError('GPL data was assigned to the shared module')
    data['manifest']['assets']['qml/Restricted.qml']['modules'] = ['QtGraphs']
    assert runtime_owners(data, parts, args.qt_root)['qml/Restricted.qml'] == {'Graphs'}
    # A QML import must retain the dependency's data independently of ELF
    # dependencies. Optional imports must not pull GPL code into Core.
    qml = copy.deepcopy(prepared)
    qml['manifest']['assets'] = {
        'qml/Base/qmldir': dict(expression='LGPL-3.0-only', modules=['QtCore'],
            provenance=dict(kind='generated-qmldir', uri='Base'), qml_imports=[dict(uri='Graph', optional=True)]),
        'qml/Graph/qmldir': dict(expression='GPL-3.0-only', modules=['QtGraphs'],
            provenance=dict(kind='generated-qmldir', uri='Graph'), qml_imports=[dict(uri='Base', optional=False)]),
        'qml/Base/Value.qml': dict(expression='LGPL-3.0-only', modules=['QtCore']),
    }
    qml['files'].update({name: Path('/unused-test-source') for name in qml['manifest']['assets']})
    retained = runtime_owners(qml, parts, args.qt_root)
    assert retained['qml/Base/Value.qml'] == {'base', 'Graphs'}
    assert retained['qml/Graph/qmldir'] == {'Graphs'}
    qml['manifest']['assets']['qml/Base/qmldir']['qml_imports'][0]['optional'] = False
    try:
        runtime_owners(qml, parts, args.qt_root)
    except ValueError as error:
        assert 'Core-only consumer' in str(error)
    else:
        raise AssertionError('A mandatory QML import bypassed the GPL guard')
    video = args.qt_root / 'qml/QtMultimedia/Video.qml'
    assert {row['uri'] for row in qml_imports(video)} == {'QtQuick', 'QtMultimedia'}
    (args.work / 'receipt.json').write_text(json.dumps(dict(verification_complete=True,
        plan=groups, scoped_classes=len(names), owned_classes=len(expected),
        unrelated_class_eliminated=True, transitive_gpl_rejected=True, gpl_data_guard=True,
        boundary='Full-profile planning and automatic ownership; complete native generation and canonical consumers remain separate gates'), indent=2) + '\n')
    print('QT_DISTRIBUTION_MODULES_OK automatic_scope=1 dependency_guard=1 data_guard=1')


if __name__ == '__main__':
    main()
