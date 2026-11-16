#!/usr/bin/env python3
"""Exercise copy-aware aggregate field provenance through stock Bend consumers."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
from backend import command, compile_backend, validate_backend
from generate import Generator
from lifetime import cpp_tables, evaluate_tables
from upstream import prepare
import aggregate_fields
import callbacks
import native_objects
import representations
import public_records
import durations

FIXTURE = """
static unsigned aggregate_test_fail_after;
static QWidget *aggregate_test_widget;
"""

def main():
    duration = dict(name='std::chrono::duration', cpp='std::chrono::duration<long, std::ratio<1, 1000000000>>')
    assert durations.normalize(duration)['name'] == 'std::chrono::nanoseconds'
    for unsupported in (dict(duration, pointers=1), dict(duration, array=True),
                        dict(duration, cpp='std::chrono::duration<unsigned long, std::ratio<1, 1000000000>>'),
                        dict(duration, cpp='std::chrono::duration<double, std::ratio<1, 1000000000>>')):
        assert durations.normalize(unsupported) is None
    parser = argparse.ArgumentParser(description=__doc__)
    cache = Path.home() / '.cache/bend-qt-generator'
    parser.add_argument('--qt-root', type=Path, default=cache / 'Qt/6.12.0/gcc_64')
    parser.add_argument('--work', type=Path, default=ROOT / 'build/dependent-fields')
    parser.add_argument('--model-work', type=Path, default=ROOT / 'build/qt612',
                        help='Maintainer extraction directory containing api.json and native-traits.json')
    parser.add_argument('--runtime-only', action='store_true')
    parser.add_argument('--syntax-only', action='store_true')
    parser.add_argument('--emit-only', action='store_true')
    parser.add_argument('--records', action='store_true')
    parser.add_argument('--only', action='append')
    parser.add_argument('--trace', action='store_true')
    args = parser.parse_args()
    work = args.work; work.mkdir(parents=True, exist_ok=True)
    programs = [('dependent-fields', (ROOT / 'scripts/fixtures/dependent-fields.bend').read_text(), 'QT612_DEPENDENT_FIELDS_OK')]
    programs.append(('metadata-fields', (ROOT / 'scripts/fixtures/metadata-fields.bend').read_text(), 'QT612_METADATA_FIELDS_OK'))
    programs.append(('model-index-fields', (ROOT / 'scripts/fixtures/model-index-fields.bend').read_text(), 'QT612_MODEL_INDEX_FIELDS_OK'))
    programs.append(('lazy-strings', (ROOT / 'scripts/fixtures/lazy-strings.bend').read_text(), 'QT612_LAZY_STRINGS_OK'))
    if args.records:
        programs.append(('public-records', (ROOT / 'scripts/fixtures/public-records.bend').read_text(), 'QT612_PUBLIC_RECORDS_OK'))
    if not args.runtime_only:
        profile = json.loads((ROOT / 'generator/qt612-core/profile.json').read_text())
        profile['qt_modules'] += ['QtSerialBus', 'Qt3DCore']
        headers, system, modules, env, _ = prepare(cache / 'pyside-setup', args.qt_root, profile['qt_modules'], work)
        profile['qt_modules'] = modules
        api = json.loads((args.model_work / 'api.json').read_text())
        api['classes'] = [c for c in api['classes'] if c.get('package', '').removeprefix('PySide6.') in modules and '/rhi/' not in c.get('source_file', '')]
        api['global_functions'] = []
        traits = json.loads((args.model_work / 'native-traits.json').read_text())
        for c in api['classes']:
            if c['name'] in traits:
                c.update(traits[c['name']]); c['native_copyable'] = traits[c['name']]['copyable']; c['native_movable'] = traits[c['name']]['movable']
            c['generate'] = c['generate'] and c.get('package', '').removeprefix('PySide6.') in modules
        if args.records:
            record_header = work / 'record-headers.h'
            record_header.write_text('#include <QtCore/QJsonParseError>\n#include <QtGui/QQuaternion>\n#include <QtCore/QXmlStreamAttributes>\n')
            record_data = public_records.scan(record_header,
                ['-x','c++','-std=c++17','-fPIC','-I'+str(args.qt_root/'include'),
                 '-I'+str(args.qt_root/'include/QtCore'),'-I'+str(args.qt_root/'include/QtGui'),
                 '-I'+str(args.qt_root/'mkspecs/linux-g++')],
                {'QJsonParseError','QQuaternion','QXmlStreamAttributes'} | {c['name'] for c in api['classes'] if c['name'].startswith('QMatrix')})
            # A full generation saves its extraction with records merged. The
            # records scanned here are merged again from this scan.
            api['classes'] = [c for c in api['classes'] if c.get('bend_public_record') not in record_data]
            summary = public_records.merge(api, record_data)
            (work / 'public-records.json').write_text(json.dumps(summary,indent=2))
            trait_dir = work / 'record-traits'; trait_dir.mkdir(exist_ok=True)
            (trait_dir / 'headers.h').write_text(record_header.read_text())
            native_objects.refine_traits(dict(api, classes=[c for c in api['classes'] if c['name'] in summary['classes']]),
                args.qt_root, ['QtCore','QtGui'], trait_dir, 'clang++-19')
        g = Generator(api, profile); g.collect()
        needed = set(re.findall(r'Qt\.([A-Za-z0-9_.]+)', '\n'.join(source for _, source, _ in programs)))
        (work / 'methods.json').write_text(json.dumps([m['bend_name'] for m in g.methods],indent=2))
        g.methods = [m for m in g.methods if m['bend_name'] in needed]
        callbacks.prepare(g)
        g.callback_classes, g.callback_methods, g.callback_qml = [], {}, False
        g.callback_functions = []
        for public, params, ret, body in [
            ('Fixture.newIndexModel', [], dict(kind='object', name='QAbstractItemModel', bend='QAbstractItemModel', raw='U32'),
             f'r->result.word = own(r, new QStandardItemModel(2, 1), {g.ids["QStandardItemModel"]}); r->result.owned_handle = r->result.word;'),
            ('Fixture.index', [('model', dict(kind='object', name='QAbstractItemModel', bend='QAbstractItemModel', raw='U32'))], dict(kind='value', name='QModelIndex', bend='QModelIndex', raw='U32'),
             f'NativeCallScope scope; auto *model = get<QAbstractItemModel>(r, r->arguments[0].word, {g.ids["QAbstractItemModel"]}); if (r->error) return true; '
             f'r->result.word = own(r, new QModelIndex(model->index(0, 0)), {g.ids["QModelIndex"]}); r->result.owned_handle = r->result.word;'),
            ('Fixture.mutateIndexModel', [('model', dict(kind='object', name='QAbstractItemModel', bend='QAbstractItemModel', raw='U32')), ('mode', dict(kind='u32', bend='U32', raw='U32'))], dict(kind='void', bend='Unit', raw='Unit'),
             f'auto *model = get<QStandardItemModel>(r, r->arguments[0].word, {g.ids["QStandardItemModel"]}); if (r->error) return true; '
             'if (r->arguments[1].word == 0) model->clear(); else if (r->arguments[1].word == 1) model->removeRow(0); else delete model;'),
            ('Fixture.deleteDocument', [('document', dict(kind='object', name='QTextDocument', bend='QTextDocument', raw='U32'))], dict(kind='void', bend='Unit', raw='Unit'),
             f'auto *document = get<QTextDocument>(r, r->arguments[0].word, {g.ids["QTextDocument"]}); if (r->error) return true; delete document;'),
            ('Fixture.failAfter', [('count', dict(kind='u32', bend='U32', raw='U32'))], dict(kind='void', bend='Unit', raw='Unit'),
             'aggregate_test_fail_after = r->arguments[0].word;'),
            ('Fixture.nativeStyle', [], dict(kind='value', name='QStyleOptionViewItem', bend='QStyleOptionViewItem', raw='U32'),
             'auto widget = std::make_unique<QWidget>(); QStyleOptionViewItem option; option.initFrom(widget.get()); option.widget = widget.get(); '
             'NativeAggregateInputScope native_input(r); '
             f'r->result.word = own(r, new QStyleOptionViewItem(option), {g.ids["QStyleOptionViewItem"]}); '
             'r->result.owned_handle = r->result.word; if (r->error) return true; aggregate_test_widget = widget.release();'),
            ('Fixture.unobservedStyle', [], dict(kind='value', name='QStyleOptionViewItem', bend='QStyleOptionViewItem', raw='U32'),
             'auto widget = std::make_unique<QWidget>(); QStyleOptionViewItem option; option.initFrom(widget.get()); option.widget = widget.get(); '
             f'r->result.word = own(r, new QStyleOptionViewItem(option), {g.ids["QStyleOptionViewItem"]}); r->result.owned_handle = r->result.word;'),
            ('Fixture.deleteStyleWidget', [], dict(kind='void', bend='Unit', raw='Unit'),
             'delete aggregate_test_widget; aggregate_test_widget = nullptr;'),
            ('Fixture.namespaceMetadata', [], dict(kind='object', name='QMetaObject', bend='QMetaObject', raw='U32'),
             'r->result = observe_metadata_field(r, &Qt::staticMetaObject);')]:
            operation = g.next_id; g.next_id += 1
            g.emit_effect(public, params, ret, operation)
            g.cases.append(f'case {operation}: {{\n {body}\n return true;\n}}')
        bend, effects, dispatch = g.emit()
        site = 'copies.push_back(id);'
        if dispatch.count(site) != 1: raise RuntimeError('Aggregate allocation fault site changed')
        dispatch = dispatch.replace(site, 'if (aggregate_test_fail_after && !--aggregate_test_fail_after) throw std::bad_alloc();\n        ' + site)
        site = 'auto backing = std::make_shared<typename Traits::Backing>(input.data(), input.size());'
        if dispatch.count(site) != 1: raise RuntimeError('Deferred input allocation fault site changed')
        dispatch = dispatch.replace(site, 'if (aggregate_test_fail_after && !--aggregate_test_fail_after) throw std::bad_alloc();\n    ' + site)
        abi = (ROOT / 'generator/templates/abi.h').read_text().replace('@ARGUMENT_CAPACITY@', str(g.argument_capacity))
        aliases = ''.join(f'using {name} = {native};\n' for name, native in api['typedefs'].items() if name in g.ids) + representations.aliases(g)
        prefix, suffix = callbacks.qml_sources(g, args.qt_root, work)
        source_cpp = headers.read_text() + aliases + prefix + FIXTURE + (ROOT / 'generator/templates/runtime.cpp').read_text() + suffix
        for key, value in [('ABI', abi), ('LIFETIME', cpp_tables(evaluate_tables(work))),
                           ('NATIVE_OBJECTS', native_objects.traits(g)), ('DISPATCH', dispatch)]:
            source_cpp = source_cpp.replace('// @' + key + '@', value)
        if args.trace:
            source_cpp = source_cpp.replace('static uint32_t finish_aggregate_ownership(BqtRequest *r, uint32_t id) try {',
                'static uint32_t finish_aggregate_ownership(BqtRequest *r, uint32_t id) try { std::fprintf(stderr, "AGG own %u\\n", id);')
            source_cpp = source_cpp.replace('static bool aggregate_validate(BqtRequest *r, uint32_t id) {',
                'static bool aggregate_validate(BqtRequest *r, uint32_t id) { std::fprintf(stderr, "AGG get %u\\n", id);')
            source_cpp = source_cpp.replace('auto *old = aggregate_record(id);', 'std::fprintf(stderr, "AGG update start %u\\n", id); auto *old = aggregate_record(id); std::fprintf(stderr, "AGG old %p\\n", static_cast<void *>(old));')
            source_cpp = source_cpp.replace('std::vector<uint32_t> copies;\n        NativeCallScope scope;', 'std::fprintf(stderr, "AGG capture %u\\n", slot); std::vector<uint32_t> copies;\n        NativeCallScope scope;')
            source_cpp = source_cpp.replace('ConversionValueGuard wire(write());', 'std::fprintf(stderr, "AGG writing\\n"); ConversionValueGuard wire(write()); std::fprintf(stderr, "AGG wrote %u\\n", wire.value.word);')
            source_cpp = source_cpp.replace('auto source = native_call_scope && native_call_scope->value_origin ?', 'std::fprintf(stderr, "AGG source %u\\n", slot); auto source = native_call_scope && native_call_scope->value_origin ?')
        native = work / 'wrappers.cpp'; native.write_text(source_cpp)
        (work / 'qt.bend').write_text(bend)
        (work / 'aggregate-fields.json').write_text(json.dumps(g.aggregate_fields, indent=2))
        if args.emit_only: print('QT612_DEPENDENT_FIELDS_EMIT_OK'); return
        validate_backend(native, args.qt_root, work, 'clang++-19', modules)
        if args.syntax_only: print('QT612_DEPENDENT_FIELDS_SYNTAX_OK'); return
        assembly, imports, backend = compile_backend(native, args.qt_root, work, 'clang++-19', modules)
        extra = [m for m in modules if m not in ('QtCore', 'QtGui', 'QtWidgets')]
        libraries = [f'    void *libraries[{len(extra) + 1}] = {{lib}};']
        for i, module in enumerate(extra, 1):
            libraries += [f'    libraries[{i}] = dlopen("libQt6{module[2:]}.so.6", RTLD_NOW | RTLD_LOCAL);',
                          f'    if (!libraries[{i}]) return dlerror();']
        effect = (ROOT / 'generator/templates/effects.c').read_text()
        for key, value in [('ABI', abi), ('ASSEMBLY', assembly), ('IMPORTS', imports),
                           ('LIBRARIES', '\n'.join(libraries)), ('EFFECTS', effects)]:
            effect = effect.replace('// @' + key + '@', value)
        (work / 'qt.c').write_text(effect)
    spec = importlib.util.spec_from_file_location('checks', ROOT / 'scripts/check-qt612.py')
    checks = importlib.util.module_from_spec(spec); spec.loader.exec_module(checks)
    if args.only: programs = [item for item in programs if item[0] in args.only]
    receipt = checks.check_package(work, programs, os.environ.copy(), [args.qt_root], work / 'consumer')
    receipt['native_integration_only'] = True
    (work / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')

if __name__ == '__main__': main()
