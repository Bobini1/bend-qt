#!/usr/bin/env python3
"""Exercise production partition emission with pinned Charts/Graphs fixtures.

The fixture narrows common classes to keep the native control bounded. Module
discovery and public naming in the production generator remain unrestricted.
"""
import argparse
import copy
import hashlib
import json
import importlib.util
import os
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
from generate import native_source, coverage_report
from backend import compiler_flags, compile_backend
from lifetime import evaluate_tables
from module_partitions import prepare_generators, merge_bend, effects, package, selective_package, scoped_api
from overload_names import NameLock
from shared_state import transform
from native_objects import refine_traits

COMMON = {'QObject', 'QEvent', 'QByteArray', 'QVariant', 'QMetaType', 'QPointF', 'QColor',
          'QPen', 'QUrl', 'QQmlEngine', 'QQmlComponent', 'QQuickItem', 'QQmlContext',
          'QJSEngine', 'QJSValue', 'QCoreApplication', 'QGuiApplication', 'QApplication'}
COMMON.update({'QGenericArgument', 'QGenericReturnArgument', 'QMetaObject', 'QMetaEnum', 'QMetaMethod', 'QMetaProperty'})
COMMON.update({'QPointerEvent', 'QEventPoint', 'QMetaClassInfo', 'QQmlListReference',
               'QQmlIncubationController', 'QQmlIncubator'})
COMMON.update({'QTextBlock', 'QTextFragment', 'QTextTableCell', 'QTextBlock::iterator',
               'QTextFrame::iterator', 'QTreeWidgetItemIterator', 'QTextDocument', 'QTreeWidget',
               'QTreeWidgetItem', 'QModelIndex', 'QPersistentModelIndex', 'QAbstractItemModel'})
COMMON.update({'QLoggingCategory', 'QOpenGLContext', 'QTextBoundaryFinder', 'QGraphicsScene'})
FAMILY_TYPES = {'QLineSeries', 'QXYSeries', 'QAbstractSeries', 'QChart',
                'QScatterDataItem', 'QScatterDataProxy', 'QAbstractDataProxy', 'QScatter3DSeries'}
ACTIVE_COMMON = {'QObject', 'QByteArray', 'QVariant', 'QMetaType', 'QPointF', 'QColor',
                 'QPen', 'QUrl', 'QQmlEngine', 'QQmlComponent', 'QQuickItem', 'QQmlContext',
                 'QJSEngine', 'QJSValue', 'QCoreApplication'}


def fixture(paths, families):
    # The first path is the primary extraction. Families whose headers cannot
    # share it come from their production group extractions, and replace the
    # primary's classes of the same name: QtCharts and QtGraphs both declare
    # QLineSeries, which is why they are extracted separately.
    api = json.loads(paths[0].read_text())
    for path in paths[1:]:
        added = [cls for cls in json.loads(path.read_text())['classes'] if cls.get('package') in families]
        names = {cls['name'] for cls in added}
        api['classes'] = [cls for cls in api['classes'] if cls['name'] not in names] + added
    classes = {cls['name']: cls for cls in api['classes']}
    selected = set(COMMON) | {cls['name'] for cls in api['classes']
        if cls.get('package') in families and cls['name'] in FAMILY_TYPES}
    pending = list(selected)
    while pending:
        for base in classes.get(pending.pop(), {}).get('bases', []):
            if base not in selected:
                selected.add(base); pending.append(base)
    api['classes'] = [cls for cls in api['classes'] if cls['name'] in selected
        or (cls.get('namespace') and cls['name'] == 'Qt')]
    for cls in api['classes']:
        if cls['name'] not in ACTIVE_COMMON and cls.get('package') not in families:
            cls['functions'] = []
    api['global_functions'] = []
    return api


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=ROOT / 'build/module-partitions-check')
    parser.add_argument('--qt-root', type=Path, default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    parser.add_argument('--native', action='store_true', help='Also compile and package both emitted native partitions')
    parser.add_argument('--run', action='store_true', help='Compile both native partitions and exercise their combined Hub package')
    parser.add_argument('--selective', action='store_true', help='Retain native modules separately and check a Core-only consumer')
    parser.add_argument('--bundle-runtime', action='store_true', help='Also bundle module-owned Qt dependencies with conflicting system search paths')
    parser.add_argument('--public-only', action='store_true', help='Emit the Bend interface without native source analysis or compilation')
    parser.add_argument('--consumer-only', action='store_true', help='Reuse native payloads only when freshly emitted native source is identical')
    parser.add_argument('--report-only', action='store_true', help='Check production coverage reports against existing native fixtures without rerunning consumers')
    parser.add_argument('--value-metatypes', action='store_true', help='Include cross-family QVariant value and container rejection checks')
    parser.add_argument('--scoped', action='store_true', help='Use production module ownership and automatic type dependency selection')
    parser.add_argument('--qml', action='store_true', help='Also check authored native subclasses and qualified QObject/value sequences in QML')
    parser.add_argument('--qml-imports', action='store_true', help='Also instantiate all three chart-family QML plugins in one engine')
    args = parser.parse_args()
    if args.report_only:
        args.run = args.consumer_only = True
    if args.qml_imports:
        args.qml = True
    if args.bundle_runtime and not (args.selective and args.run):
        parser.error('--bundle-runtime requires --selective --run')
    if args.consumer_only and not args.run:
        parser.error('--consumer-only requires --run')
    work = args.work.resolve(); work.mkdir(parents=True, exist_ok=True)
    if not args.report_only:
        (work / 'emission.json').write_text(json.dumps(dict(verification_complete=False, stage='partition emission/native integration')) + '\n')
    base_modules = ['QtCore', 'QtGui', 'QtWidgets', 'QtQml', 'QtQuick', 'QtNetwork', 'QtOpenGL']
    records = []
    production = ROOT / 'build/qt612'
    specifications = [
        ('modern', ['QtGraphs', 'QtGraphsWidgets'], {'PySide6.QtGraphs', 'PySide6.QtGraphsWidgets'}, {},
         [production / 'api.json']),
        ('legacy', ['QtCharts', 'QtDataVisualization'], {'PySide6.QtCharts', 'PySide6.QtDataVisualization'},
         {'PySide6.QtCharts': 'Charts', 'PySide6.QtDataVisualization': 'DataVisualization'},
         [production / 'api.json', production / 'modules/Charts/api.json',
          production / 'modules/DataVisualization/api.json']),
    ]
    if args.selective:
        specifications.insert(0, ('base', [], set(), {}, [production / 'api.json']))
    for name, modules, families, namespaces, api_path in specifications:
        part_work = work / name; part_work.mkdir(exist_ok=True)
        headers = part_work / 'headers.h'
        headers.write_text(''.join('#include <' + module + '/' + module + '>\n' for module in base_modules + modules))
        api = fixture(api_path, families)
        if args.scoped:
            api = scoped_api(api, base_modules if name == 'base' else modules, root=name == 'base')
        refine_traits(api, args.qt_root, base_modules + modules, part_work, 'clang++-19')
        records.append(SimpleNamespace(name=name, api=api, namespaces=namespaces,
            profile=dict(minimum_qt='6.12.0', qt_modules=base_modules + modules, exclude_methods={}),
            work=part_work, headers=headers))
    parts = prepare_generators(records, NameLock.load(ROOT / 'generator/qt612/names.lock.json'), selective=args.selective)
    if args.public_only:
        (work / 'qt.bend').write_text(merge_bend([part.bend for part in parts]))
        print('QT_MODULE_PUBLIC_INTERFACE_EMITTED', flush=True)
        return
    capacity = max(part.generator.argument_capacity for part in parts)
    abi = (ROOT / 'generator/templates/abi.h').read_text().replace('@ARGUMENT_CAPACITY@', str(capacity))
    prefix = '#define BQT_NATIVE_PARTITIONS 1\n' + ''.join(
        '#include "' + str(ROOT / 'generator/templates' / name) + '"\n'
        for name in ('shared_runtime.h', 'shared_runtime.cpp'))
    policy = evaluate_tables(work)
    for part in parts:
        source = part.work / 'unshared-wrappers.cpp'
        emitted = prefix + native_source(part.generator, part.generator.api, part.headers,
            args.qt_root, part.work, abi, policy).replace('// @DISPATCH@', part.native)
        if args.consumer_only:
            if not source.is_file() or source.read_text() != emitted:
                raise RuntimeError('Native source changed; rebuild the ' + part.name + ' payload')
            part.embedded = (part.work / 'payload.generated.c').read_text()
            continue
        source.write_text(emitted)
        print(f'Analysing {part.name}: {len(part.generator.selected)} types, {source.stat().st_size} source bytes', flush=True)
        rewritten, state = transform(source, compiler_flags(args.qt_root, 'clang++-19', part.profile['qt_modules'])[1:])
        (part.work / 'wrappers.cpp').write_text(rewritten)
        (part.work / 'shared-state.json').write_text(json.dumps(state, indent=2) + '\n')
        print(f'Emitted {part.name}: {len(state)} shared storage declarations', flush=True)
    native = []
    if (args.native or args.run) and not args.consumer_only:
        for part in parts:
            print('Compiling native partition: ' + part.name, flush=True)
            embedded, imports, metadata = compile_backend(part.work / 'wrappers.cpp', args.qt_root,
                part.work, 'clang++-19', part.profile['qt_modules'])
            (part.work / 'payload.generated.c').write_text(embedded)
            (part.work / 'imports.generated.c').write_text(imports)
            (part.work / 'backend.json').write_text(json.dumps(metadata, indent=2) + '\n')
            native.append(dict(name=part.name, payload=metadata['payload']))
            part.embedded = embedded
    if args.native or args.run:
        reports = []
        for part in parts:
            metadata = json.loads((part.work / 'backend.json').read_text())
            report = coverage_report(part.generator, part.generator.api, part.profile,
                None, None, policy, metadata, None, part.profile['qt_modules'], {}, [])
            if report['argument_capacity'] != part.generator.argument_capacity:
                raise RuntimeError('Coverage lost the module argument capacity: ' + part.name)
            (part.work / 'coverage-report.json').write_text(json.dumps(report, indent=2) + '\n')
            reports.append(dict(name=part.name, argument_capacity=report['argument_capacity'],
                generated_count=report['generated_count']))
        (work / 'coverage-report-receipt.json').write_text(json.dumps(dict(
            passed=True, reports=reports, native_source_identity_checked=args.consumer_only,
            boundary='Production report generation from focused module inventories and native metadata'), indent=2) + '\n')
        print('QT_MODULE_COVERAGE_REPORTS_OK', flush=True)
    if args.report_only:
        return
    integration = None
    if args.run:
        runtime = fixture_runtime(parts, args.qt_root, work, qml_imports=args.qml_imports) if args.bundle_runtime else None
        if args.selective:
            emitted = selective_package(parts, abi, runtime=runtime)
            bend, c = emitted['bend'], emitted['c']
            for name, text in emitted['assets'].items():
                (work / name).write_text(text)
            bend += '\ndef Runtime.loadedLibraries() -> IO(String):\n  import "./module-check.c"\n'
            (work / 'module-check.c').write_text((ROOT / 'scripts/fixtures/module-libraries.c').read_text())
        else:
            bend, c = package(parts, abi)
        (work / 'qt.bend').write_text(bend); (work / 'qt.c').write_text(c)
        if runtime:
            (work / 'coverage.json').write_text('{"bundled_runtime":true}\n')
        spec = importlib.util.spec_from_file_location('qt_package_check', ROOT / 'scripts/check-qt612.py')
        checker = importlib.util.module_from_spec(spec); spec.loader.exec_module(checker)
        source = (ROOT / 'scripts/fixtures/module-partitions.bend').read_text()
        programs = [('module-partitions', source, 'QT_MODULE_PARTITIONS_OK')]
        if args.selective:
            # Value-metatype isolation has its own stronger control. This
            # fixture checks foreign-C retention, lazy loading and callbacks.
            if not args.value_metatypes:
                begin = source.index('    +graph_variant:')
                end = source.index('\ndef checks()', begin)
                source = source[:begin] + '\n' + source[end:]
            if not args.qml:
                source = source.replace('    Qt.scoped(Unit, qml_families())\n', '')
            if args.qml_imports:
                source = source.replace('Qt.QByteArray.fromUtf8(qml_source())', 'Qt.QByteArray.fromUtf8(qml_imports_source())')
            source = source.replace('    Qt.Action.lift(Unit, IO.print("QT_MODULE_PARTITIONS_OK"))',
                '    Qt.Action.lift(Unit, RuntimeMaps())\n    Qt.Action.lift(Unit, IO.print("QT_MODULE_PARTITIONS_OK"))')
            source = source.replace('\ndef checks()', '\ndef RuntimeMaps() -> IO(Unit):\n  do IO<Unit>:\n'
                '    maps: String <- Qt.Runtime.loadedLibraries()\n    IO.print(maps)\n\ndef checks()')
            core = (ROOT / 'scripts/fixtures/module-core-only.bend').read_text()
            metadata = (ROOT / 'scripts/fixtures/module-metadata-only.bend').read_text()
            programs = [('module-core-only', core, 'QT_MODULE_CORE_ONLY_OK'),
                        ('module-metadata-only', metadata, 'QT_MODULE_METADATA_ONLY_OK'),
                        ('module-partitions', source, 'QT_MODULE_PARTITIONS_OK')]
        environment = dict(os.environ, BEND_NO_TELEMETRY='1')
        overrides = None
        if runtime:
            cache = Path.home() / '.cache/bend-qt-generator/selective-modules-runtime'
            environment['XDG_CACHE_HOME'] = str(cache)
            conflicting = dict(LD_LIBRARY_PATH='/usr/lib/x86_64-linux-gnu',
                QT_PLUGIN_PATH='/usr/lib/x86_64-linux-gnu/qt6/plugins',
                QML_IMPORT_PATH='/usr/lib/x86_64-linux-gnu/qt6/qml')
            overrides = {name: conflicting for name, _, _ in programs}
        integration = checker.check_package(work, programs,
            environment, [args.qt_root], work / 'hub', jobs=1, runtime_overrides=overrides)
        if args.selective:
            integration['selective_modules'] = check_retention(parts, work)
            if runtime:
                integration['selective_runtime_assets'] = check_runtime_retention(runtime['bundle'], work)
        (work / 'integration.json').write_text(json.dumps(integration, indent=2) + '\n')
    if not args.run:
        (work / 'qt.bend').write_text(merge_bend([part.bend for part in parts]))
    (work / 'effects.generated.c').write_text(effects(parts))
    (work / 'abi.h').write_text(abi)
    receipt = dict(emission_complete=True, verification_complete=bool(args.run),
        native_compilation_complete=bool(args.native or args.run), native=native, integration=integration,
        boundary=('Focused selected Graphs/Charts/DataVisualization native integration; full module inventories, QML and value-metatype isolation remain required' if args.run else
                  'Generated native source and shared-state analysis; native Bend/QML execution remains required'),
        parts=[dict(name=part.name, classes=len(part.generator.selected), operation_begin=part.operation_begin,
            operation_end=part.operation_end, source_sha256=hashlib.sha256((part.work / 'wrappers.cpp').read_bytes()).hexdigest())
            for part in parts])
    (work / 'emission.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('QT612_MODULE_PARTITIONS_EMITTED')


def check_retention(parts, work):
    import re
    core = (work / 'hub/module-core-only').read_bytes()
    combined = (work / 'hub/module-partitions').read_bytes()
    metadata_path = work / 'hub/module-metadata-only'
    metadata = metadata_path.read_bytes() if metadata_path.is_file() else None
    retained = []
    for index, part in enumerate(parts):
        encoded = part.embedded.partition('static const char bqt_payload[] =')[2].partition(';')[0]
        payload = ''.join(re.findall(r'"([A-Za-z0-9+/=]+)"', encoded)).encode()
        if not payload or payload not in combined:
            raise RuntimeError('Combined consumer did not retain native payload: ' + part.name)
        if (payload in core) != (index == 0):
            raise RuntimeError('Core consumer retained the wrong native payload: ' + part.name)
        if metadata is not None and (payload in metadata) != (index == 0 or part.name == 'legacy'):
            raise RuntimeError('Metadata-only consumer retained the wrong native payload: ' + part.name)
        retained.append(dict(name=part.name, core_retained=index == 0,
                             mixed_retained=True, payload_sha256=hashlib.sha256(payload).hexdigest()))
    logs = list((work / 'hub').glob('module-core-only-*.log'))
    if not logs:
        raise RuntimeError('Missing Core runtime library snapshot')
    text = '\n'.join(path.read_text() for path in logs)
    libraries = sorted(set(re.findall(r'/[^\s]*libQt6[^\s]*', text)))
    if not any('/libQt6Core.so' in path for path in libraries):
        raise RuntimeError('Core runtime map did not capture QtCore')
    forbidden = ('Graphs', 'Charts', 'DataVisualization', 'CanvasPainter', 'HttpServer', 'NetworkAuth', 'Quick3D')
    if any('libQt6' + name in path for path in libraries for name in forbidden):
        raise RuntimeError('Core consumer loaded a GPL-only Qt module: ' + repr(libraries))
    metadata_libraries = []
    if metadata is not None:
        text = '\n'.join(path.read_text() for path in (work / 'hub').glob('module-metadata-only-*.log'))
        metadata_libraries = sorted(set(re.findall(r'/[^\s]*libQt6[^\s]*', text)))
        if (not any('libQt6DataVisualization.so' in path for path in metadata_libraries)
                or any('libQt6Graphs' in path for path in metadata_libraries)):
            raise RuntimeError('A metadata declaration did not retain its native module independently')
    return dict(payloads=retained, core_loaded_qt_libraries=libraries, metadata_loaded_qt_libraries=metadata_libraries,
                evidence='Exact compressed payload presence in ELF and /proc/self/maps inside the consumer')


def fixture_runtime(parts, qt, work, *, qml_imports=False):
    """Exact real-Qt fixture closure, separate from the release source gate."""
    from qt_licenses import Inventory
    from runtime_selection import elf_dependencies
    from runtime_bundle import embed
    qt = qt.resolve(); inventory = Inventory(qt)
    files, owners, order, visited = {}, {}, [], set()
    dependencies = {}

    def visit(path, module):
        real = path.resolve()
        if (real, module) in visited:
            return
        visited.add((real, module))
        relative = real.relative_to(qt).as_posix()
        if real.name.startswith('libicu'):
            if real.name not in {'libicudata.so.73.2', 'libicui18n.so.73.2', 'libicuuc.so.73.2'}:
                raise ValueError('Unexpected fixture dependency: ' + str(real))
        else:
            inventory.binary(path, 'gpl')
        dependencies[relative] = []
        for name in elf_dependencies(real):
            if (qt / 'lib' / name).is_file():
                dependencies[relative].append((qt / 'lib' / name).resolve().relative_to(qt).as_posix())
                visit(qt / 'lib' / name, module)
        if relative not in files and relative.startswith('lib/'):
            order.append(relative)
        files[relative] = real
        owners.setdefault(relative, set()).add(module)

    for part in parts:
        for module in part.profile['qt_modules']:
            visit(qt / 'lib' / ('lib' + module.replace('Qt', 'Qt6', 1) + '.so.6'), part.name)
    visit(qt / 'plugins/platforms/libqoffscreen.so', parts[0].name)
    for directory in (qt / 'qml/QML', qt / 'qml/QtQml'):
        for path in directory.rglob('*'):
            if not path.is_file() or path.suffix == '.qmltypes':
                continue
            if path.suffix == '.so':
                visit(path, parts[0].name)
            else:
                relative = path.relative_to(qt).as_posix()
                files[relative] = path
                owners.setdefault(relative, set()).add(parts[0].name)
    if qml_imports:
        from runtime_assets import qmldir_uri, qml_imports as imports
        declarations = {path.parent: qmldir_uri(path.read_text()) for path in (qt / 'qml').rglob('qmldir')}
        module_files = {uri: [] for uri in declarations.values()}
        for path in (qt / 'qml').rglob('*'):
            if (not path.is_file() or path.suffix in ('.qmltypes', '.o', '.a')
                    or 'designer' in path.relative_to(qt).parts):
                continue
            directory = path.parent
            while directory != qt:
                if directory in declarations:
                    module_files[declarations[directory]].append(path)
                    break
                directory = directory.parent
        pending = [(uri, part.name) for part in parts for uri in (
            ['QML', 'QtQml'] if part.name == 'base' else ['QtGraphs'] if part.name == 'modern'
            else ['QtCharts', 'QtDataVisualization'])]
        included = set()
        while pending:
            uri, module = pending.pop()
            if (uri, module) in included:
                continue
            included.add((uri, module))
            if uri not in module_files:
                library = qt / 'lib' / ('libQt6' + uri[2:] + '.so.6')
                if uri.startswith('Qt') and library.is_file():
                    visit(library, module)
                    continue
                raise ValueError('Missing fixture QML dependency: ' + uri)
            for path in module_files[uri]:
                if path.suffix == '.so':
                    visit(path, module)
                else:
                    relative = path.relative_to(qt).as_posix()
                    files[relative] = path; owners.setdefault(relative, set()).add(module)
                    pending.extend((dependency['uri'], module) for dependency in imports(path))
    aliases = {path.relative_to(qt).as_posix(): path.resolve().relative_to(qt).as_posix()
               for path in (qt / 'lib').glob('*.so*') if path.is_symlink()
               and path.resolve().relative_to(qt).as_posix() in files}
    bundle = embed(files, aliases=aliases, owners=owners, base_module=parts[0].name,
                   context=dict(test='selective native Qt modules, not a release distribution'))
    (work / 'runtime-manifest.json').write_text(json.dumps(bundle['manifest'], indent=2) + '\n')
    return dict(bundle=bundle, selection=dict(files=files, aliases=aliases, preload_order=order,
                                            dependencies=dependencies))


def check_runtime_retention(bundle, work):
    import re
    consumers = [('module-core-only', {'base'}), ('module-partitions', {'base', 'modern', 'legacy'})]
    if (work / 'hub/module-metadata-only').is_file():
        consumers.append(('module-metadata-only', {'base', 'legacy'}))
    results = []
    for consumer, selected in consumers:
        executable = (work / 'hub' / consumer).read_bytes()
        retained = []
        for name, source in bundle['assets'].items():
            if name.startswith('qt-runtime-module-'):
                continue
            effect = 'native_Runtime_piece_' + str(int(name.removeprefix('qt-runtime-').removesuffix('.c')))
            needed = any('FID(' + effect + ')' in bundle['assets']['qt-runtime-module-' + module + '.c']
                         for module in selected)
            first = source.partition('static const char ')[2].partition(';')[0]
            encoded = ''.join(re.findall(r'"([A-Za-z0-9+/=]+)"', first)).encode()
            if not encoded or (encoded in executable) != needed:
                raise RuntimeError('Wrong embedded Qt runtime retention: ' + consumer + '/' + name)
            if needed:
                retained.append(name)
        default_log = work / 'hub' / (consumer + '-' + hashlib.sha256(b'None').hexdigest()[:8] + '.log')
        paths = re.findall(r'(/[^\s]*/bend-qt/[a-f0-9]{64})/lib/libQt6Core\.so', default_log.read_text())
        if not paths:
            raise RuntimeError('The consumer did not load QtCore from its selected bundled cache')
        runtime = Path(paths[0])
        expected = {row['path'] for row in bundle['manifest']['files'] if selected.intersection(row['modules'])}
        expected.update(alias for alias, target in bundle['manifest']['aliases'].items() if target in expected)
        actual = {path.relative_to(runtime).as_posix() for path in runtime.rglob('*') if path.is_file()}
        if actual != expected | {'.lock'}:
            raise RuntimeError('The selected Qt cache contains the wrong module files: ' + consumer)
        results.append(dict(consumer=consumer, selected_modules=sorted(selected),
                            runtime=str(runtime), retained_asset_pieces=retained, extracted_files=sorted(actual)))
    return dict(verification_complete=True, consumers=results,
                boundary='Real Qt file and payload retention; release source/notices and full module inventories remain separate gates')


if __name__ == '__main__':
    main()
