#!/usr/bin/env python3
"""Compile restored native declarations and exercise typed output/constant APIs."""
import argparse
import copy
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
import callbacks
import native_objects
import representations
import qobject_interfaces
import qio_pipe
import signature_restoration


FIXTURE = '''
#include <QtCore/QPromise>
static bool restoration_row_fail;
class RestorationItem : public QSpacerItem {
public:
    static inline unsigned live = 0;
    RestorationItem() : QSpacerItem(7, 11) { ++live; }
    ~RestorationItem() override { --live; }
};
class RestorationText final : public QAccessibleTextInterface {
public:
    void selection(int, int *start, int *end) const override { *start = 1; *end = 4; }
    int selectionCount() const override { return 1; }
    void addSelection(int, int) override {}
    void removeSelection(int) override {}
    void setSelection(int, int, int) override {}
    int cursorPosition() const override { return 2; }
    void setCursorPosition(int) override {}
    QString text(int start, int end) const override { return QStringLiteral("hello world").mid(start, end - start); }
    int characterCount() const override { return 11; }
    QRect characterRect(int) const override { return {}; }
    int offsetAtPoint(const QPoint &) const override { return 0; }
    void scrollToSubstring(int, int) override {}
    QString attributes(int, int *start, int *end) const override { *start = 2; *end = 9; return QStringLiteral("weight:bold"); }
};
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    cache = Path.home() / '.cache/bend-qt-generator'
    parser.add_argument('--qt-root', type=Path, default=cache / 'Qt/6.12.0/gcc_64')
    parser.add_argument('--work', type=Path, default=ROOT / 'build/qt612/check/restoration')
    parser.add_argument('--runtime-only', action='store_true')
    parser.add_argument('--reuse-model', action='store_true', help='Reuse this work directory extraction for focused generator iterations')
    parser.add_argument('--syntax-only', action='store_true')
    parser.add_argument('--only', action='append', help='Run only the named consumer fixture (generation still includes all fixtures)')
    args = parser.parse_args()
    work = args.work; work.mkdir(parents=True, exist_ok=True)
    programs = [(name, (ROOT / 'scripts/fixtures' / (name + '.bend')).read_text(), marker)
                for name, marker in [('restored-native', 'QT612_RESTORED_NATIVE_OK'),
                                     ('future-take', 'QT612_FUTURE_TAKE_OK'),
                                     ('taken-rows', 'QT612_TAKEN_ROWS_OK'),
                                     ('value-provenance', 'QT612_VALUE_PROVENANCE_OK'),
                                     ('js-exposure', 'QT612_JS_EXPOSURE_OK')]]
    if not args.runtime_only:
        profile = json.loads((ROOT / 'generator/qt612-core/profile.json').read_text())
        profile['qt_modules'] += ['QtSensors', 'QtStateMachine', 'QtHttpServer']
        headers, system, modules, env, _ = prepare(cache / 'pyside-setup', args.qt_root, profile['qt_modules'], work)
        profile['qt_modules'] = modules
        if not args.reuse_model:
            logs = work / 'extractor'; logs.mkdir(exist_ok=True)
            result = command([cache / 'build/bend-qt-extract', headers, system, work / 'api.json', logs,
                args.qt_root / 'include', args.qt_root / 'mkspecs/linux-g++',
                *[args.qt_root / 'include' / m for m in modules]], env=env)
            (work / 'extraction.log').write_text(result.stdout + result.stderr)
        api = json.loads((work / 'api.json').read_text())
        qobject_interfaces.restore(api, work)
        qio_pipe.restore(api, work)
        native_objects.refine_traits(api, args.qt_root, modules, work, 'clang++-19')
        restore = signature_restoration.restore_native
        try:
            signature_restoration.restore_native = lambda f: False
            original = Generator(copy.deepcopy(api), profile); original.collect()
        finally:
            signature_restoration.restore_native = restore
        g = Generator(api, profile); g.collect()
        names = {m['bend_name'] for m in g.methods}
        missing = sorted({m['bend_name'] for m in original.methods} - names)
        if missing:
            raise RuntimeError('Restoration renamed existing public API: ' + ', '.join(missing))
        needed = set(re.findall(r'Qt\.([A-Za-z0-9_.]+)', '\n'.join(source for _, source, _ in programs)))
        needed.add('QQmlContext.setContextProperties')
        restored = [m for m in g.methods if m['function'].get('bend_restored_native')]
        g.methods = [m for m in g.methods if m['bend_name'] in needed or
                     (m['function'].get('bend_restored_native') and m['class'] == m['function']['declaring_class'])]
        callbacks.prepare(g)
        g.callback_classes, g.callback_methods, g.callback_qml = [], {}, False
        g.callback_functions = []
        operation = g.next_id; g.next_id += 1
        g.emit_effect('Fixture.text', [], dict(kind='object', name='QAccessibleTextInterface',
                      bend='QAccessibleTextInterface', raw='U32'), operation)
        g.cases.append(f'''case {operation}: {{
            r->result.word = own(r, static_cast<QAccessibleTextInterface *>(new RestorationText), {g.ids['QAccessibleTextInterface']});
            r->result.owned_handle = r->result.word; return true;
}}''')
        for public, ret, body in [
            ('Fixture.item', dict(kind='object', name='QLayoutItem', bend='QLayoutItem', raw='U32'),
             f'r->result.word = own(r, static_cast<QLayoutItem *>(new NativeTracked<RestorationItem>), {g.ids["QLayoutItem"]}); mark_native_observed(r->result.word); r->result.owned_handle = r->result.word;'),
            ('Fixture.liveItems', dict(kind='u32', bend='U32', raw='U32'), 'r->result.word = RestorationItem::live;'),
            ('Fixture.failRowAllocation', dict(kind='void', bend='Unit', raw='Unit'), 'restoration_row_fail = true;')]:
            operation = g.next_id; g.next_id += 1
            g.emit_effect(public, [], ret, operation)
            g.cases.append(f'case {operation}: {{\n    {body}\n    return true;\n}}')
        operation = g.next_id; g.next_id += 1
        g.emit_effect('Fixture.future', [('mode', dict(kind='u32', bend='U32', raw='U32'))],
            dict(kind='value', name='Future_QHttpServerResponse', bend='Future_QHttpServerResponse', raw='U32'), operation)
        g.cases.append(f'''case {operation}: {{
    auto mode = r->arguments[0].word;
    if (mode > 3) return fail(r, EINVAL, "Unknown future fixture mode");
    auto promise = std::make_shared<QPromise<QHttpServerResponse>>();
    promise->start();
    if (mode != 2) {{
        promise->addResult(QHttpServerResponse(QByteArray("first")));
        promise->addResult(QHttpServerResponse(QByteArray("discarded")));
    }}
    if (mode == 1) QTimer::singleShot(500, application, [promise] {{ promise->finish(); }});
    else promise->finish();
    r->result.word = own(r, new Future_QHttpServerResponse(promise->future()), {g.ids['Future_QHttpServerResponse']});
    r->result.owned_handle = r->result.word;
    if (mode == 3) if (auto *e = entry(r->result.word)) e->read_only = true;
    return true;
}}''')
        for public, params, ret, body in [
            ('Fixture.unknownScript', [], dict(kind='value', name='QJSValue', bend='QJSValue', raw='U32'),
             f'QJSEngine engine; r->result.word = own(r, new QJSValue(engine.newObject()), {g.ids["QJSValue"]}); r->result.owned_handle = r->result.word;'),
            ('Fixture.deleteDocument', [('document', dict(kind='object', name='QTextDocument', bend='QTextDocument', raw='U32'))], dict(kind='void', bend='Unit', raw='Unit'),
             f'auto *document = get<QTextDocument>(r, r->arguments[0].word, {g.ids["QTextDocument"]}); if (r->error) return true; delete document;'),
            ('Fixture.deleteItem', [('item', dict(kind='object', name='QLayoutItem', bend='QLayoutItem', raw='U32'))], dict(kind='void', bend='Unit', raw='Unit'),
             f'auto *item = get<QLayoutItem>(r, r->arguments[0].word, {g.ids["QLayoutItem"]}); if (r->error) return true; delete item;'),
            ('Fixture.exposedVariant', [('object', dict(kind='object', name='QObject', bend='QObject', raw='U32'))], dict(kind='value', name='QVariant', bend='QVariant', raw='U32'),
             f'auto *object = get<QObject>(r, r->arguments[0].word, {g.ids["QObject"]}); if (r->error) return true; QVariantList nested{{QVariant::fromValue(object)}}; r->result.word = own(r, new QVariant(nested), {g.ids["QVariant"]}); r->result.owned_handle = r->result.word;'),
            ('Fixture.badExposedVariant', [('object', dict(kind='object', name='QObject', bend='QObject', raw='U32'))], dict(kind='value', name='QVariant', bend='QVariant', raw='U32'),
             f'auto *object = get<QObject>(r, r->arguments[0].word, {g.ids["QObject"]}); if (r->error) return true; QVariantList nested{{QVariant::fromValue(object), QVariant::fromValue(reinterpret_cast<QObject *>(uintptr_t(1)))}}; r->result.word = own(r, new QVariant(nested), {g.ids["QVariant"]}); r->result.owned_handle = r->result.word;')]:
            operation = g.next_id; g.next_id += 1
            g.emit_effect(public, params, ret, operation)
            g.cases.append(f'case {operation}: {{\n {body}\n return true;\n}}')
        script_value = dict(name='QJSValue', cpp='QJSValue', const=False, pointers=0, reference=0, enum=False, flags=False)
        script_list = g.conversions.container(dict(name='QList', cpp='QList<QJSValue>',
            pointers=0, reference=0, const=False, instantiations=[script_value]), True)
        operation = g.next_id; g.next_id += 1
        g.emit_effect('Fixture.scriptList', [('self', dict(kind='object', name='QJSEngine', bend='QJSEngine', raw='U32'))],
                      script_list, operation, has_self=True)
        # This fixture effect is registered before emit(), while its recursive
        # converter is emitted inside emit(). Keep the raw import in place and
        # append its public wrapper after those converter definitions.
        start = next(i for i, line in enumerate(g.bend) if line.startswith('def Fixture.scriptList('))
        list_wrapper = '\n'.join(g.bend[start:]) + '\n'
        del g.bend[start:]
        body = '\n'.join(g.store_result(script_list, 'values'))
        g.cases.append(f'''case {operation}: {{
    NativeCallScope scope;
    auto *engine = get<QJSEngine>(r, r->self, {g.ids['QJSEngine']});
    if (r->error) return true;
    QList<QJSValue> values{{engine->newObject(), engine->newArray()}};
    {body}
    return true;
}}''')
        bend, effects, dispatch = g.emit()
        bend += list_wrapper
        site = 'taking_row = &source;\n    return own(r, new QFormLayout::TakeRowResult(value),'
        if dispatch.count(site) != 1:
            raise RuntimeError('Taken row allocation fault site changed')
        dispatch = dispatch.replace(site, 'taking_row = &source;\n    if (restoration_row_fail) { restoration_row_fail = false; throw std::bad_alloc(); }\n    return own(r, new QFormLayout::TakeRowResult(value),')
        abi = (ROOT / 'generator/templates/abi.h').read_text().replace('@ARGUMENT_CAPACITY@', str(g.argument_capacity))
        aliases = ''.join(f'using {name} = {native};\n' for name, native in api['typedefs'].items() if name in g.ids) + representations.aliases(g)
        prefix, suffix = callbacks.qml_sources(g, args.qt_root, work)
        source_cpp = headers.read_text() + aliases + prefix + FIXTURE + (ROOT / 'generator/templates/runtime.cpp').read_text() + suffix
        for key, value in [('ABI', abi), ('LIFETIME', cpp_tables(evaluate_tables(work))),
                           ('NATIVE_OBJECTS', native_objects.traits(g)), ('DISPATCH', dispatch)]:
            source_cpp = source_cpp.replace('// @' + key + '@', value)
        native = work / 'wrappers.cpp'; native.write_text(source_cpp)
        (work / 'qt.bend').write_text(bend)
        (work / 'restored.json').write_text(json.dumps([dict(name=m['bend_name'], signature=m['function']['signature'],
            owner=m['function']['declaring_class']) for m in restored], indent=2))
        validate_backend(native, args.qt_root, work, 'clang++-19', modules)
        if args.syntax_only:
            print('QT612_RESTORATION_SYNTAX_OK'); return
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
    if args.only:
        unknown = set(args.only) - {name for name, _, _ in programs}
        if unknown: raise RuntimeError('Unknown restoration fixtures: ' + ', '.join(sorted(unknown)))
        programs = [program for program in programs if program[0] in args.only]
    receipt = checks.check_package(work, programs, os.environ.copy(), [args.qt_root], work / 'consumer')
    receipt['restoration_preserves_original_names'] = True
    receipt['native_integration_only'] = True
    (work / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    main()
