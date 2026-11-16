#!/usr/bin/env python3
"""Native lifetime fault injection in an isolated test-only BendHub package.

This is not a proof of native destruction. It tests allocation rollback and Qt
origin destruction, including deletion deliberately bypassing binding guards.
No test effect or injected allocator failure enters a consumer package.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
import callbacks
import native_objects
import representations
import qobject_interfaces
import qio_pipe
from backend import command, compile_backend
from generate import Generator
from lifetime import cpp_tables, evaluate_tables
from upstream import prepare


def inject(generator):
    unit = dict(kind='void', bend='Unit', raw='Unit')
    boolean = dict(kind='bool', bend='Bool', raw='U32')
    handle = lambda name: dict(kind='value', name=name, bend=name, raw='U32')
    operations = [
        ('collectionScheduling', [('stage', dict(kind='u32', bend='U32', raw='U32'))], boolean,
         f'''QCoreApplication::sendPostedEvents(application, QEvent::MetaCall);
         auto *native = new QSize(7, 9);
         uint32_t old = own(r, native, {generator.ids['QSize']});
         if (r->error) return true;
         bool completed = true;
         if (r->arguments[0].word == 1) {{
             test_collection_post_fault = 1;
             try {{ invalidate(old); }} catch (...) {{ completed = false; }}
             delete native;
             if (!completed || test_collection_post_fault || entry(old)) {{ r->result.word = 0; return true; }}
             uint32_t replacement = own(r, new QSize(11, 13), {generator.ids['QSize']});
             if (r->error) return true;
             if ((replacement & 65535u) != (old & 65535u) || replacement == old) {{ r->result.word = 0; return true; }}
             entry(replacement)->pending_release = true;
             schedule_collection();
             QCoreApplication::sendPostedEvents(application, QEvent::MetaCall);
             r->result.word = !entry(replacement);
         }} else {{
             entry(old)->pending_release = true;
             if (r->arguments[0].word == 2) test_collection_post_fault = 2;
             else test_collection_run_fault = true;
             schedule_collection();
             QCoreApplication::sendPostedEvents(application, QEvent::MetaCall);
             if (!entry(old) || test_collection_post_fault || test_collection_run_fault) {{ r->result.word = 0; return true; }}
             schedule_collection();
             QCoreApplication::sendPostedEvents(application, QEvent::MetaCall);
             r->result.word = !entry(old);
         }}'''),
        ('failNextGuardAssignment', [], unit, 'test_fail_value_assignment = true;'),
        ('failNextOwnedFinalization', [], unit, 'test_fail_owned_finalization = true;'),
        ('failQObjectRegistration', [('stage', dict(kind='u32', bend='U32', raw='U32')), ('derived', boolean)], handle('QObject'),
         f'''if (r->arguments[0].word < 1 || r->arguments[0].word > 3) return fail(r, EINVAL, "Unknown registration fault stage");
test_registration_deleted = 0;
test_registration_identity = 0;
auto *value = new TestRegistrationObject;
test_registration_object = value;
test_registration_stage = r->arguments[0].word;
if (r->arguments[1].word)
    r->result.word = own_derived<QObject, TestRegistrationObject>(r, value, {generator.ids['QObject']});
else
    r->result.word = own<QObject>(r, static_cast<QObject *>(value), {generator.ids['QObject']});'''),
        ('registrationRolledBack', [], boolean, '''bool clean = test_registration_deleted == 1 && test_registration_stage == 0;
for (const auto &e : entries)
    if (e.value && (e.value == test_registration_object || e.object == test_registration_object)) clean = false;
if (test_registration_identity && entry(test_registration_identity)) clean = false;
r->result.word = clean;'''),
        ('deleteDocument', [('self', handle('QTextDocument'))], unit,
         f'NativeCallScope scope; auto *value = get<QTextDocument>(r, r->self, {generator.ids["QTextDocument"]});\n'
         'if (r->error) return true; delete value;'),
        ('deleteTree', [('self', handle('QTreeWidget')), ('iterator', handle('QTreeWidgetItemIterator'))], boolean,
         f'NativeCallScope scope; auto *value = get<QTreeWidget>(r, r->self, {generator.ids["QTreeWidget"]});\n'
         'if (r->error) return true;\n'
         'QPointer<QAbstractItemModel> model = value->model(); bool observed = false;\n'
         'uint32_t iterator_id = r->arguments[0].word;\n'
         'QObject::connect(value, &QObject::destroyed, [model, iterator_id, &observed] { observed = model && !entry(iterator_id); });\n'
         'delete value; r->result.word = observed;'),
    ]
    for offset, (name, args, result, body) in enumerate(operations):
        operation = 0x7fff0123 + offset
        generator.cases.append(f'case {operation}: {{\n{body}\nreturn true;\n}}')
        generator.emit_effect('Test.' + name, args, result, operation, has_self=bool(args) and args[0][0] == 'self')


def inject_registration_failures(runtime):
    start = runtime.index('static uint32_t __attribute__((noinline)) insert(')
    end = runtime.index('template<class T> struct NativeTraits', start)
    original = runtime[start:end]
    registration = original
    sites = [
        ('alive = std::make_shared<std::atomic<bool>>(true);',
         'test_registration_fault(1, 0);\n        alive = std::make_shared<std::atomic<bool>>(true);'),
        ('            try {\n            native_pointer_publish(id);\n',
         '            try {\n            if (object) test_registration_fault(2, id);\n            native_pointer_publish(id);\n'),
        ('            if (!attach_graphics_context(r, id) || !attach_rhi_identity(r, id)) {',
         '            if (object) test_registration_fault(3, id);\n            if (!attach_graphics_context(r, id) || !attach_rhi_identity(r, id)) {'),
    ]
    for old, new in sites:
        if registration.count(old) != 1:
            raise RuntimeError('The QObject registration injection site changed: ' + old)
        registration = registration.replace(old, new, 1)
    runtime = runtime.replace(original, registration, 1)
    declarations = '''static unsigned test_registration_stage = 0;
static unsigned test_registration_deleted = 0;
static uint32_t test_registration_identity = 0;
static QObject *test_registration_object = nullptr;
class TestRegistrationObject : public QObject {
public:
    ~TestRegistrationObject() override { ++test_registration_deleted; }
};
static void test_registration_fault(unsigned stage, uint32_t identity) {
    if (test_registration_stage != stage) return;
    test_registration_stage = 0;
    test_registration_identity = identity;
    throw std::bad_alloc();
}
'''
    if runtime.count('static SlotTable<Entry> entries;') != 1:
        raise RuntimeError('The native registry declaration injection site changed')
    return runtime.replace('static SlotTable<Entry> entries;', declarations + 'static SlotTable<Entry> entries;', 1)


def inject_collection_failures(runtime, negative=False):
    start = runtime.index('static void schedule_collection() noexcept\n{')
    end = runtime.index('static void discard_value(BqtValue &value)', start)
    original = runtime[start:end]
    body = original
    if negative:
        body = '''static void schedule_collection()
{
    static bool scheduled = false;
    if (scheduled || !application) return;
    scheduled = true;
    QMetaObject::invokeMethod(application, [] {
        scheduled = false;
        reconcile_parents();
        reconcile_retentions();
        collect_pending();
    }, Qt::QueuedConnection);
}

'''
        runtime = runtime.replace('static void schedule_collection() noexcept;', 'static void schedule_collection();')
    invocation = 'QMetaObject::invokeMethod(application, '
    assert body.count(invocation) == 1
    body = body.replace(invocation, 'test_collection_post(')
    body = body.replace('}, Qt::QueuedConnection)', '})')
    assert body.count('reconcile_parents();') == 1
    body = body.replace('reconcile_parents();', '''if (test_collection_run_fault) {
                    test_collection_run_fault = false;
                    throw std::bad_alloc();
                }
                reconcile_parents();''')
    declarations = '''static unsigned test_collection_post_fault = 0;
static bool test_collection_run_fault = false;
template<class F> static bool test_collection_post(F &&function) {
    unsigned fault = test_collection_post_fault;
    test_collection_post_fault = 0;
    if (fault == 1) throw std::bad_alloc();
    if (fault == 2) return false;
    return QMetaObject::invokeMethod(application, std::forward<F>(function), Qt::QueuedConnection);
}
'''
    return runtime.replace(original, declarations + body, 1)


def main():
    cache = Path.home() / '.cache/bend-qt-generator'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qt-root', type=Path, default=cache / 'Qt/6.12.0/gcc_64')
    parser.add_argument('--extractor', type=Path, default=cache / 'build/bend-qt-extract')
    parser.add_argument('--pyside-source', type=Path, default=cache / 'pyside-setup')
    parser.add_argument('--work', type=Path, default=ROOT / 'build/qt612/check/value-lifetimes-native')
    parser.add_argument('--cxx', default='clang++-19')
    parser.add_argument('--runtime-only', action='store_true')
    parser.add_argument('--negative-collection', action='store_true')
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    source = (ROOT / 'scripts/fixtures/value-lifetime-faults.bend').read_text()
    if not args.runtime_only:
        profile = json.loads((ROOT / 'generator/qt612-core/profile.json').read_text())
        headers, typesystem, modules, environment, upstream = prepare(args.pyside_source, args.qt_root, profile['qt_modules'], args.work)
        logdir = args.work / 'extractor'
        logdir.mkdir(exist_ok=True)
        includes = [args.qt_root / 'include', args.qt_root / 'mkspecs/linux-g++'] + [args.qt_root / 'include' / module for module in modules]
        result = command([args.extractor, headers, typesystem, args.work / 'api.json', logdir, *includes], env=environment)
        (args.work / 'extraction.log').write_text(result.stdout + result.stderr)
        api = json.loads((args.work / 'api.json').read_text())
        qobject_interfaces.restore(api, args.work)
        qio_pipe.restore(api, args.work)
        native_objects.refine_traits(api, args.qt_root, modules, args.work, args.cxx)
        generator = Generator(api, profile)
        generator.collect()
        needed = set(re.findall(r'Qt\.([A-Za-z0-9_.]+)', source))
        generator.methods = [method for method in generator.methods if method['bend_name'] in needed]
        callbacks.prepare(generator)
        generator.callback_classes, generator.callback_methods = [], {}
        generator.callback_functions = []
        inject(generator)
        bend, effects, dispatch = generator.emit()
        dispatch = dispatch.replace('struct ValueGuard {', 'static bool test_fail_value_assignment = false;\nstruct ValueGuard {', 1)
        allocation = 'try {\n        auto guard = std::make_unique<ValueGuard>();'
        if allocation not in dispatch:
            raise RuntimeError('The native guard allocation injection site changed')
        dispatch = dispatch.replace(allocation, '''try {
        if (test_fail_value_assignment && id == r->self && native_call_scope && native_call_scope->value_origin) {
            test_fail_value_assignment = false;
            throw std::bad_alloc();
        }
        auto guard = std::make_unique<ValueGuard>();''', 1)
        (args.work / 'qt.bend').write_text(bend)
        abi = (ROOT / 'generator/templates/abi.h').read_text().replace('@ARGUMENT_CAPACITY@', str(generator.argument_capacity))
        aliases = ''.join(f'using {name} = {target};\n' for name, target in api['typedefs'].items() if name in generator.ids) + representations.aliases(generator)
        prefix, suffix = callbacks.qml_sources(generator, args.qt_root, args.work)
        runtime = (ROOT / 'generator/templates/runtime.cpp').read_text()
        # Inject after registration, before the first ownership hook. The
        # outermost hook changes when another origin policy is composed.
        # Scope the injection to own() and its finalization rollback block.
        # Registration has a separate catch for liveness allocation failures.
        own_start = runtime.index('template<class T> static uint32_t __attribute__((noinline)) own(')
        own_end = runtime.index('// Only constructors use this path.', own_start)
        owned_runtime = runtime[own_start:own_end]
        original_owned_runtime = owned_runtime
        if owned_runtime.count('id = insert(r, value, object, type, native_deleter<T>(), true, NativeTraits<T>::cast);') != 1:
            raise RuntimeError('The native owning registration site changed')
        allocation = re.compile(
            r'(\n    try \{\n)(?=\s*return finish_[A-Za-z0-9_]+\()')
        if len(list(allocation.finditer(owned_runtime))) != 1:
            raise RuntimeError('The native ownership rollback injection site changed')
        if 'if (auto *e = entry(id); e && e->owned && e->value == value)' not in runtime:
            raise RuntimeError('The native ownership rollback guard changed')
        runtime = runtime.replace('static SlotTable<Entry> entries;',
            'static bool test_fail_owned_finalization = false;\nstatic SlotTable<Entry> entries;', 1)
        owned_runtime = allocation.sub(lambda match: match[1] + '''
        if (test_fail_owned_finalization) {
            test_fail_owned_finalization = false;
            throw std::bad_alloc();
        }
''', owned_runtime, count=1)
        runtime = runtime.replace(original_owned_runtime, owned_runtime, 1)
        runtime = inject_registration_failures(runtime)
        runtime = inject_collection_failures(runtime, args.negative_collection)
        cpp = headers.read_text() + aliases + prefix + runtime + suffix
        for key, value in [('ABI', abi), ('LIFETIME', cpp_tables(evaluate_tables(args.work))), ('NATIVE_OBJECTS', native_objects.traits(generator)), ('DISPATCH', dispatch)]:
            cpp = cpp.replace('// @' + key + '@', value)
        wrapper = args.work / 'wrappers.cpp'
        wrapper.write_text(cpp)
        assembly, imports, metadata = compile_backend(wrapper, args.qt_root, args.work, args.cxx, modules)
        additional = [module for module in modules if module not in ('QtCore', 'QtGui', 'QtWidgets')]
        libraries = [f'    void *libraries[{len(additional) + 1}] = {{lib}};']
        for index, module in enumerate(additional, 1):
            libraries += [f'    libraries[{index}] = dlopen("libQt6{module[2:]}.so.6", RTLD_NOW | RTLD_LOCAL);', f'    if (!libraries[{index}]) return dlerror();']
        effect = (ROOT / 'generator/templates/effects.c').read_text()
        for key, value in [('ABI', abi), ('ASSEMBLY', assembly), ('IMPORTS', imports), ('LIBRARIES', '\n'.join(libraries)), ('EFFECTS', effects)]:
            effect = effect.replace('// @' + key + '@', value)
        (args.work / 'qt.c').write_text(effect)
    spec = importlib.util.spec_from_file_location('qt612_checks', ROOT / 'scripts/check-qt612.py')
    checks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checks)
    env = dict(os.environ, BENDRTS='', QT_QPA_PLATFORM='offscreen')
    for key in ('CC', 'LD_LIBRARY_PATH', 'LD_PRELOAD', 'BEND_QT_LIBRARY', 'QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH'):
        env.pop(key, None)
    receipt = checks.check_package(args.work, [('value-lifetime-faults', source, 'QT612_VALUE_LIFETIME_FAULTS_OK')], env, [args.qt_root], args.work / 'consumer', jobs=1)
    receipt['native_integration_only'] = True
    receipt['fault_injection_in_production'] = False
    receipt['collection_scheduling'] = {
        'invalidation_generation_survives_enqueue_failure': True,
        'failed_post_and_failed_callback_allow_retry': True,
        'cases': ['enqueue allocation failure', 'enqueue returns false', 'collection callback allocation failure'],
        'pending_entries_collected_after_retry': True,
    }
    receipt['qobject_registration_faults'] = {
        'owning_paths': ['own<QObject>', 'own_derived<QObject, TestRegistrationObject>'],
        'stages': ['before liveness allocation and registry slot', 'after slot assignment before QObject observers',
                   'after QObject observers before ownership attachment'],
        'assertions': ['ENOMEM', 'exactly one native destructor', 'no registered native pointer',
                       'no live failed token', 'zero live entries after each failure'],
    }
    (args.work / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    main()
