#!/usr/bin/env python3
"""Native checks for registry, helper and TLS identity across operation shards."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
from backend import compile_backend, compiler_flags
import native_shards

NATIVE = r'''
#include <cstdint>
#include <typeinfo>
#include "shared-input.h"
struct BqtRequest { uint32_t operation; intptr_t value; void *pointer; };
namespace bendqt {
static int initializations = 0;
struct Initializer { Initializer() { ++initializations; } };
static Initializer initializer;
static int registry_value = 0;
static thread_local int task_context = 0;
static void *registry_pointer = nullptr;
static void (*callback_identity)() = nullptr;
static void callback() {}
struct CrossShardBase { CrossShardBase(); virtual ~CrossShardBase(); };
struct CrossShardValue : CrossShardBase { CrossShardValue(); ~CrossShardValue() override; int value; };
CrossShardBase::CrossShardBase() {}
CrossShardBase::~CrossShardBase() {}
CrossShardValue::CrossShardValue() : value(63) {}
CrossShardValue::~CrossShardValue() {}
struct Marker { int value; };
static CrossShardBase *polymorphic = nullptr;
static void throw_marker() { throw Marker{77}; }
static void (*exception_callback)() = nullptr;
static int *local_identity() { static int local = 31; return &local; }
__attribute__((used, section(".bqt.proxy_traits"))) static const unsigned char bqt_proxy_traits[] = {1,0,1};
static bool __attribute__((noinline)) bqt_op_10(BqtRequest *r) {
    registry_value = INPUT_VALUE; task_context = 7;
    static CrossShardValue object; polymorphic = &object; exception_callback = &throw_marker;
    registry_pointer = local_identity(); callback_identity = &callback;
    r->pointer = registry_pointer; r->value = 1; return true;
}
static bool __attribute__((noinline)) bqt_op_11(BqtRequest *r) {
    r->value = registry_value == INPUT_VALUE && task_context == 7
        && r->pointer == local_identity() && registry_pointer == local_identity()
        && callback_identity == &callback && initializations == 1
        && dynamic_cast<CrossShardValue *>(polymorphic)
        && static_cast<CrossShardValue *>(polymorphic)->value == 63
        && typeid(*polymorphic) == typeid(CrossShardValue);
    try { exception_callback(); r->value = 0; }
    catch (const Marker &value) { r->value = r->value && value.value == 77; }
    return true;
}
static bool __attribute__((noinline)) bqt_op_12(BqtRequest *r) {
    r->value = task_context == 0 && registry_value == INPUT_VALUE
        && registry_pointer == local_identity() && callback_identity == &callback;
    task_context = 99; return true;
}
static bool __attribute__((noinline)) bqt_op_13(BqtRequest *r) {
    r->value = task_context == 7 && initializations == 1; return true;
}
static bool dispatch(BqtRequest *r) {
    switch(r->operation) {
    case 10:return bqt_op_10(r); case 11:return bqt_op_11(r);
    case 12:return bqt_op_12(r); case 13:return bqt_op_13(r);
    default:return false;
    }
}
}
struct BqtHost;
extern "C" __attribute__((visibility("default"))) void bqt_abi_call(BqtRequest *r) {
    if (!bendqt::dispatch(r)) r->value = 0;
}
extern "C" __attribute__((visibility("default"))) const char *bqt_abi_start(const BqtHost *) {
    return nullptr;
}
extern "C" __attribute__((visibility("default"))) int bqt_abi_stop(void) {
    return bendqt::initializations;
}
'''

CONSUMER = r'''
#define _GNU_SOURCE
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <pthread.h>
#include <dlfcn.h>
typedef struct BqtRequest { uint32_t operation; intptr_t value; void *pointer; } BqtRequest;
typedef struct BqtHost BqtHost;
@PAYLOAD@
static void *other_thread(void *unused) {
    BqtRequest r = {12,0,NULL};
    bqt_abi_call(&r);
    return (void *)(intptr_t)(r.value != 0);
}
int main(void) {
    const char *error = bqt_load_payload();
    if (error) { puts(error); return 125; }
    if (bqt_abi_start(NULL) || bqt_abi_stop() != 1) return 1;
    BqtRequest r = {10,0,NULL};
    bqt_abi_call(&r);
    if (!r.value) return 2;
    r.operation=11;r.value=0;
    bqt_abi_call(&r);
    if (!r.value) return 3;
    pthread_t thread;void *result;
    if(pthread_create(&thread,NULL,other_thread,NULL)||pthread_join(thread,&result)||(intptr_t)result!=1)return 4;
    r.operation=13;r.value=0;
    bqt_abi_call(&r);
    if(!r.value)return 5;
    puts("QT612_NATIVE_SHARDS_OK registry=1 local_static=1 callback_identity=1 tls=1 initialization_once=1 rtti=1 exceptions=1");
}
'''


def auxiliary_fixture():
    """Use the production typed property facade across separate native units."""
    facade = (ROOT / 'generator/templates/property_bindings.cpp').read_text()
    declarations, definitions = [], []
    for index in range(128):
        signature = ('std::shared_ptr<BendPropertyBindings::Storage> bqt_test_factory_' + str(index) +
                     '(QMetaType type, BendPropertyBindings::Read read, BendPropertyBindings::Write write)')
        declarations.append('extern ' + signature + ';')
        native = 'QString' if index == 1 else 'int'
        definitions.append(f'// BQT_AUXILIARY_BEGIN test_factories {index}\n' + signature + ' {\n' +
                           f'    return BendPropertyBindings::make<{native}>(type, std::move(read), std::move(write));\n' +
                           f'}}\n// BQT_AUXILIARY_END test_factories {index}\n')
    shared = facade + '\n' + '\n'.join(declarations) + '\n' + ''.join(definitions) + r'''
static int factory_source_value = 0;
static int factory_target_value = 0;
static QString factory_text_value;
static std::shared_ptr<BendPropertyBindings::Storage> factory_source, factory_text;
'''
    create = r'''
    factory_source = bqt_test_factory_0(QMetaType::fromType<int>(),
        [](bool) -> std::optional<QVariant> { return QVariant(factory_source_value); },
        [](QVariant value, bool) { factory_source_value = value.toInt(); return true; });
    factory_text = bqt_test_factory_1(QMetaType::fromType<QString>(),
        [](bool) -> std::optional<QVariant> { return QVariant(factory_text_value); },
        [](QVariant value, bool) { factory_text_value = value.toString(); return true; });
    QBindable<int>(factory_source->bindable(true)).setValue(43);
    QBindable<QString>(factory_text->bindable(true)).setValue(QStringLiteral("native factory"));
    r->value = factory_source_value == 43 && factory_text_value == QStringLiteral("native factory");
'''
    verify = r'''
    // The same out-of-line factory is called by two operation translation units.
    auto target = bqt_test_factory_0(QMetaType::fromType<int>(),
        [](bool) -> std::optional<QVariant> { return QVariant(factory_target_value); },
        [](QVariant value, bool) { factory_target_value = value.toInt(); return true; });
    QBindable<int> source_binding(factory_source->bindable(true));
    QBindable<int> target_binding(target->bindable(true));
    target_binding.setBinding(source_binding.makeBinding());
    r->value = r->value && factory_target_value == 43 && target_binding.value() == 43;
    factory_source_value = 77;
    factory_source->changed();
    r->value = r->value && target_binding.value() == 77 && factory_target_value == 77
        && QBindable<QString>(factory_text->bindable(false)).value() == QStringLiteral("native factory");
'''
    source = '#include <QtCore/QtCore>\n#include <memory>\n' + NATIVE
    source = source.replace('static int initializations = 0;', shared + '\nstatic int initializations = 0;')
    source = source.replace('r->pointer = registry_pointer; r->value = 1; return true;',
                            'r->pointer = registry_pointer;\n' + create + '\nreturn true;')
    source = source.replace('catch (const Marker &value) { r->value = r->value && value.value == 77; }',
                            'catch (const Marker &value) { r->value = r->value && value.value == 77; }\n' + verify)
    return source


def check_auxiliary_factories(work, qt):
    folder = work / 'auxiliary-factories'; folder.mkdir(exist_ok=True)
    source = folder / 'wrappers.cpp'; source.write_text(auxiliary_fixture())
    native_shards.write_changed(folder / 'shared-input.h', '#define INPUT_VALUE 47\n')
    previous_batch = os.environ.get('BQT_AUXILIARY_FUNCTIONS')
    os.environ['BQT_AUXILIARY_FUNCTIONS'] = '64'
    try:
        payload, _, first = compile_backend(source, qt, folder, 'clang++-19', ['QtCore'])
        if first['shards']['operation_shards'] != 4 or first['shards']['auxiliary_shards'] != 2 or first['shards']['auxiliary_functions'] != 128:
            raise RuntimeError('Auxiliary factories did not use bounded, separate translation units')
        shared = (folder / 'shards/shared.hpp').read_text()
        if 'return BendPropertyBindings::make<int>' in shared or 'return BendPropertyBindings::make<QString>' in shared:
            raise RuntimeError('Typed factory implementations leaked back into the shared PCH')
        consumer = folder / 'consumer.c'
        consumer.write_text(CONSUMER.replace('@PAYLOAD@', payload).replace('exceptions=1', 'exceptions=1 factories=1 typed_binding=1'))
        subprocess.run(['clang', str(consumer), '-ldl', '-pthread', '-o', str(folder / 'consumer')], check=True)
        environment = dict(os.environ)
        environment['LD_LIBRARY_PATH'] = str(qt / 'lib') + (':' + environment['LD_LIBRARY_PATH'] if environment.get('LD_LIBRARY_PATH') else '')
        tested = subprocess.run([str(folder / 'consumer')], text=True, capture_output=True, env=environment)
        if tested.returncode:
            raise RuntimeError('Typed auxiliary factory consumer failed: ' + tested.stdout + tested.stderr)
        original = source.read_text()
        source.write_text(original.replace(
            'return BendPropertyBindings::make<QString>(type, std::move(read), std::move(write));',
            'auto result = BendPropertyBindings::make<QString>(type, std::move(read), std::move(write)); return result;'))
        compile_backend(source, qt, folder, 'clang++-19', ['QtCore'])
        resources = json.loads((folder / 'native-resources.json').read_text())
        preserved = {'shared', 'operations-000', 'operations-001', 'operations-002', 'operations-003',
                     'auxiliary-test_factories-001', 'runtime'}
        compiled = {item['name'] for item in resources['shards']}
        if not preserved.issubset(resources['cached']) or 'auxiliary-test_factories-000' not in compiled or \
                not compiled.issubset({'auxiliary-test_factories-000', 'combined'}):
            raise RuntimeError('A single factory edit invalidated unrelated native units: ' + repr(resources))
        source.write_text(original)
        restored, _, _ = compile_backend(source, qt, folder, 'clang++-19', ['QtCore'])
        if restored != payload:
            raise RuntimeError('Restoring a factory did not restore the deterministic native payload')
        # Editing one factory must preserve the PCH, other factory batch and all
        # operation objects. The auxiliary body is covered by the checked cache.
        prior_stamp = (folder / 'native-compile-cache.json').read_bytes()
        source.write_text(source.read_text().replace('return BendPropertyBindings::make<QString>',
            'return missing_factory_expression + BendPropertyBindings::make<QString>'))
        try:
            compile_backend(source, qt, folder, 'clang++-19', ['QtCore'])
        except RuntimeError as error:
            if 'Native shard auxiliary-test_factories-000 failed' not in str(error):
                raise
        else:
            raise RuntimeError('A malformed auxiliary factory was packaged')
        if (folder / 'native-compile-cache.json').read_bytes() != prior_stamp:
            raise RuntimeError('A failed auxiliary factory replaced the checked outer cache')
        source.write_text(auxiliary_fixture())
        # A large helper inventory selects sharding even for this small source
        # when the maintainer has not explicitly selected operation sharding.
        previous_operations = os.environ.pop('BQT_SHARD_OPERATIONS', None)
        try:
            auto = folder / 'automatic'; auto.mkdir(exist_ok=True)
            _, _, automatic = compile_backend(source, qt, auto, 'clang++-19', ['QtCore'])
            if automatic['shards']['operation_shards'] != 1 or automatic['shards']['auxiliary_shards'] != 2:
                raise RuntimeError('A small source with many typed factories did not automatically select sharding')
        finally:
            if previous_operations is not None: os.environ['BQT_SHARD_OPERATIONS'] = previous_operations
        # Malformed marker pairs and duplicate identities must never disappear.
        for broken in ('// BQT_AUXILIARY_BEGIN bad 1\nint x;\n',
                       '// BQT_AUXILIARY_BEGIN bad 1\nint x;\n// BQT_AUXILIARY_END bad 2\n',
                       ('// BQT_AUXILIARY_BEGIN bad 1\nint x;\n// BQT_AUXILIARY_END bad 1\n' * 2)):
            try: native_shards.split_auxiliary(broken)
            except ValueError: pass
            else: raise RuntimeError('A malformed auxiliary boundary was accepted')
        return dict(passed=True, factories=128, batches=2, exact_native_binding_types=True,
                    called_from_distinct_operation_units=True, automatic_selection=True,
                    single_factory_edit_preserves_other_units=True, restored_payload_exact=True,
                    malformed_factory_rejected=True, marker_boundaries_checked=True,
                    template_sha256=hashlib.sha256((ROOT / 'generator/templates/property_bindings.cpp').read_bytes()).hexdigest(),
                    native_output=tested.stdout)
    finally:
        if previous_batch is None: os.environ.pop('BQT_AUXILIARY_FUNCTIONS', None)
        else: os.environ['BQT_AUXILIARY_FUNCTIONS'] = previous_batch


def qml_base_fixture():
    import re
    import qt_objects
    names = ['QQmlPropertyMap' if i == 2 else 'QmlFactoryBase' + str(i) for i in range(128)]
    fixture = SimpleNamespace(qt_object_bases=[dict(name=n) for n in names],
        ids={n: i + 1 for i, n in enumerate(names)}, profile={}, classes={},
        runtime_default_constructors={n: 70000 + i for i, n in enumerate(names) if i != 2},
        all_bases=lambda name: [])
    fixture.abi_cohort = dict(names={names[-1]}, headers=[], pattern=re.compile(r'\b' + names[-1] + r'\b'),
        proxies=set(), operations=set(), exact_helpers={})
    cases, declarations, definitions = qt_objects._base_info_parts(fixture)
    classes = ['static unsigned factory_parser_calls = 0;',
               'struct FactoryObserver { uintptr_t marker = 0xabc; };']
    for i, name in enumerate(names):
        body = []
        if i != 2:
            body += [f'class {name} : public QObject {{ public: {name}() = default; }};']
        parents = 'public FactoryObserver, public ' + name
        if i == 1: parents += ', public QQmlParserStatus'
        body += [f'class BqtProxy_{name} final : {parents} {{ public:']
        if i == 2:
            body += [f'explicit BqtProxy_{name}(int) : {name}(nullptr) {{}}']
        else:
            body += [f'BqtProxy_{name}() = default;',
                     f'static bool bqt_create_{70000 + i}(BqtRequest *r) {{ r->value = {i + 1}; return true; }}']
        if i == 1:
            body += ['void classBegin() override { ++factory_parser_calls; }',
                     'void componentComplete() override { ++factory_parser_calls; }']
        body += ['};']
        if i == 127: body = ['#if BQT_HAS_RHI', *body, '#endif']
        classes += body
    template = (ROOT / 'generator/templates/qt_objects.cpp').read_text()
    begin = template.index('struct BaseInfo {')
    end = template.index('static std::shared_ptr<BendPropertyBindings::Storage> binding_storage', begin)
    facade = template[begin:end].replace('@HAS_QML@', '1').replace('@BASE_DECLARATIONS@', '\n'.join(declarations)).replace('@BASE_CASES@', '\n'.join(cases))
    shared = '\n'.join(classes) + '\nnamespace RuntimeQtObjects {\n' + facade + '\n}\n' + ''.join(definitions) + r'''
static QObject *factory_object = nullptr;
static const std::type_info *factory_rtti = nullptr;
static bool (*factory_constructor)(BqtRequest *) = nullptr;
'''
    create = r'''
    const auto native = RuntimeQtObjects::base_info(2);
    factory_object = native.make();
    factory_rtti = &typeid(*factory_object); factory_constructor = native.constructor;
    r->value = factory_object && native.id == 2 && native.size == sizeof(BqtProxy_QmlFactoryBase1)
        && native.meta == &QmlFactoryBase1::staticMetaObject && native.parser >= 0;
'''
    verify = r'''
    const auto native = RuntimeQtObjects::base_info(2);
    auto *typed = dynamic_cast<BqtProxy_QmlFactoryBase1 *>(factory_object);
    r->value = r->value && typed && factory_rtti == &typeid(BqtProxy_QmlFactoryBase1)
        && factory_constructor == native.constructor && native.source == -1
        && native.interceptor == -1 && native.finalizer == -1;
    auto *parser = reinterpret_cast<QQmlParserStatus *>(reinterpret_cast<char *>(factory_object) + native.parser);
    r->value = r->value && parser == static_cast<QQmlParserStatus *>(typed);
    parser->classBegin(); parser->componentComplete();
    std::aligned_storage_t<sizeof(BqtProxy_QmlFactoryBase1), alignof(BqtProxy_QmlFactoryBase1)> storage;
    QObject *placed = native.place(&storage);
    r->value = r->value && typeid(*placed) == typeid(*factory_object) && factory_parser_calls == 2;
    static_cast<BqtProxy_QmlFactoryBase1 *>(placed)->~BqtProxy_QmlFactoryBase1();
    BqtRequest construction{}; native.constructor(&construction);
    r->value = r->value && construction.value == 2;
    const auto no_default = RuntimeQtObjects::base_info(3);
    r->value = r->value && no_default.id == 3 && !no_default.make && !no_default.place
        && !no_default.constructor && no_default.static_metadata && !no_default.extension_metadata
        && no_default.size == sizeof(BqtProxy_QQmlPropertyMap);
    const auto last = RuntimeQtObjects::base_info(128);
    r->value = r->value && last.id == (BQT_HAS_RHI ? 128 : 0);
    delete factory_object; factory_object = nullptr;
'''
    for i, name in enumerate(names):
        check = (f'{{ const auto all = RuntimeQtObjects::base_info({i + 1}); '
                 f'r->value = r->value && all.id == {i + 1} '
                 f'&& all.meta == &{name}::staticMetaObject '
                 f'&& all.size == sizeof(BqtProxy_{name}); }}\n')
        verify += ('\n#if BQT_HAS_RHI\n' + check + '#endif\n') if i == 127 else check
    source = ('#ifndef BQT_HAS_RHI\n#define BQT_HAS_RHI 1\n#endif\n'
              '#include <QtCore/QObject>\n#include <QtQml/qqmlprivate.h>\n#include <QtQml/QQmlParserStatus>\n'
              '#include <QtQml/QQmlPropertyMap>\n#include <type_traits>\n' + NATIVE)
    source = source.replace('static int initializations = 0;', shared + '\nstatic int initializations = 0;')
    source = source.replace('r->pointer = registry_pointer; r->value = 1; return true;',
                            'r->pointer = registry_pointer;\n' + create + '\nreturn true;')
    source = source.replace('catch (const Marker &value) { r->value = r->value && value.value == 77; }',
                            'catch (const Marker &value) { r->value = r->value && value.value == 77; }\n' + verify)
    return source


def check_qml_base_factories(work, qt):
    folder = work / 'qml-base-factories'; folder.mkdir(exist_ok=True)
    source = folder / 'wrappers.cpp'; source.write_text(qml_base_fixture())
    native_shards.write_changed(folder / 'shared-input.h', '#define INPUT_VALUE 47\n')
    previous = os.environ.get('BQT_AUXILIARY_FUNCTIONS')
    os.environ['BQT_AUXILIARY_FUNCTIONS'] = '64'
    try:
        payload, _, result = compile_backend(source, qt, folder, 'clang++-19', ['QtCore', 'QtQml'])
        if result['shards']['auxiliary_functions'] != 128 or result['shards']['auxiliary_shards'] != 2:
            raise RuntimeError('QObject base factories were not compiled in bounded auxiliary units')
        shared = (folder / 'shards/shared.hpp').read_text()
        if 'return base_info_for<BqtProxy_' in shared or 'RuntimeQtObjects::bqt_qml_base_info_factory_1() {' in shared:
            raise RuntimeError('QObject factory implementations leaked into the shared PCH')
        environment = dict(os.environ, LD_LIBRARY_PATH=str(qt / 'lib'))
        def consume(body, directory):
            consumer = directory / 'consumer.c'; consumer.write_text(CONSUMER.replace('@PAYLOAD@', body))
            subprocess.run(['clang', str(consumer), '-ldl', '-pthread', '-o', str(directory / 'consumer')], check=True)
            checked = subprocess.run([str(directory / 'consumer')], env=environment, text=True, capture_output=True)
            if checked.returncode: raise RuntimeError('QObject factory consumer failed: ' + checked.stdout + checked.stderr)
            return checked.stdout
        output = consume(payload, folder)
        baseline = folder / 'public'; baseline.mkdir(exist_ok=True)
        baseline_source = baseline / 'wrappers.cpp'
        baseline_source.write_text(source.read_text().replace('#define BQT_HAS_RHI 1', '#define BQT_HAS_RHI 0'))
        native_shards.write_changed(baseline / 'shared-input.h', '#define INPUT_VALUE 47\n')
        public, _, _ = compile_backend(baseline_source, qt, baseline, 'clang++-19', ['QtCore', 'QtQml'])
        consume(public, baseline)
        os.environ['BQT_AUXILIARY_FUNCTIONS'] = '128'
        flags = compiler_flags(qt, 'clang++-19', ['QtCore', 'QtQml'])
        syntax = native_shards.check_syntax(source, folder / 'batch128', flags, maximum_operations=1)
        if syntax['auxiliary_units'] != 1:
            raise RuntimeError('The requested 128-factory batch was not syntax checked')
        return dict(passed=True, factories=128, separate_batches=2, syntax_batch128=True,
                    default_and_nondefault_construction=True, placement_exact=True,
                    parser_interface_offset_exact=True, constructor_identity_and_rtti=True,
                    public_abi_guard=True, native_output=output,
                    template_sha256=hashlib.sha256((ROOT / 'generator/templates/qt_objects.cpp').read_bytes()).hexdigest(),
                    emitter_sha256=hashlib.sha256((ROOT / 'generator/qt_objects.py').read_bytes()).hexdigest())
    finally:
        if previous is None: os.environ.pop('BQT_AUXILIARY_FUNCTIONS', None)
        else: os.environ['BQT_AUXILIARY_FUNCTIONS'] = previous


def check_bounded_syntax(work, qt):
    folder = work / 'bounded-syntax'; folder.mkdir(exist_ok=True)
    source = folder / 'wrappers.cpp'; original = auxiliary_fixture(); source.write_text(original)
    native_shards.write_changed(folder / 'shared-input.h', '#define INPUT_VALUE 47\n')
    previous = os.environ.get('BQT_AUXILIARY_FUNCTIONS')
    os.environ['BQT_AUXILIARY_FUNCTIONS'] = '64'
    try:
        flags = compiler_flags(qt, 'clang++-19', ['QtCore'])
        checked = native_shards.check_syntax(source, folder, flags, maximum_operations=1)
        if checked['operation_units'] != 4 or checked['auxiliary_units'] != 2 or len(checked['checked_units']) != 7:
            raise RuntimeError('Bounded syntax checking omitted a generated unit')
        # The final helper is deliberately unreferenced by operations. Its body
        # still has to be checked, rather than hidden by the common PCH split.
        start = original.index('// BQT_AUXILIARY_BEGIN test_factories 127\n')
        source.write_text(original[:start] + original[start:].replace('return BendPropertyBindings::make<int>',
            'return syntax_negative_control + BendPropertyBindings::make<int>', 1))
        try:
            native_shards.check_syntax(source, folder / 'negative', flags, maximum_operations=1)
        except RuntimeError as error:
            if 'auxiliary-test_factories-001 failed' not in str(error): raise
        else:
            raise RuntimeError('An unreferenced malformed auxiliary factory passed syntax checking')
        return dict(passed=True, operation_units=4, auxiliary_units=2, dispatcher_units=1,
                    unreferenced_last_factory_rejected=True)
    finally:
        source.write_text(original)
        if previous is None: os.environ.pop('BQT_AUXILIARY_FUNCTIONS', None)
        else: os.environ['BQT_AUXILIARY_FUNCTIONS'] = previous


def check_keep_going(work, qt):
    import pickle
    failure = native_shards.NativeCompileFailure('operation', 1, work / 'failure.log')
    assert str(pickle.loads(pickle.dumps(failure))) == str(failure)
    folder = work / 'keep-going'; folder.mkdir(parents=True, exist_ok=True)
    source = folder / 'wrappers.cpp'; source.write_text(NATIVE)
    native_shards.write_changed(folder / 'shared-input.h', '#define INPUT_VALUE 47\n')
    flags = compiler_flags(qt, 'clang++-19', ['QtCore'])
    previous = os.environ.get('BQT_SHARD_KEEP_GOING')
    os.environ['BQT_SHARD_KEEP_GOING'] = '1'
    try:
        native_shards.compile_objects(source, folder, flags, maximum_operations=1)
        combined = hashlib.sha256((folder / 'wrappers.o').read_bytes()).hexdigest()
        changed = NATIVE.replace('registry_value = INPUT_VALUE;', 'missing_first_operation = 1; registry_value = INPUT_VALUE;', 1)
        changed = changed.replace('r->value = registry_value == INPUT_VALUE', 'missing_second_operation = 1; r->value = registry_value == INPUT_VALUE', 1)
        changed = changed.replace('r->value = task_context == 7 && initializations == 1;',
                                  'r->value = task_context == 7 && initializations == 1 && registry_value == INPUT_VALUE;', 1)
        source.write_text(changed)
        try:
            native_shards.compile_objects(source, folder, flags, maximum_operations=1)
        except RuntimeError as error:
            assert 'Native shard operations-000 failed' in str(error), str(error)
            assert 'Native shard operations-001 failed' in str(error), str(error)
        else:
            raise RuntimeError('Two invalid operations were packaged')
        report = json.loads((folder / 'native-build-progress.json').read_text())
        assert report['completed'] == report['total'] == 5, report
        assert {row['name'] for row in report['failures']} == {'operations-000', 'operations-001'}, report
        good = folder / 'shards/operations-003.cpp'
        cached = json.loads((folder / 'shards/operations-003-cache.json').read_text())
        assert cached['key']['source'] == hashlib.sha256(good.read_bytes()).hexdigest()
        assert hashlib.sha256((folder / 'wrappers.o').read_bytes()).hexdigest() == combined
        source.write_text(changed.replace('missing_first_operation = 1; ', '').replace('missing_second_operation = 1; ', ''))
        native_shards.compile_objects(source, folder, flags, maximum_operations=1)
        resumed = json.loads((folder / 'native-build-progress.json').read_text())
        assert not resumed['failures'] and 'operations-003' in resumed['cached'], resumed
        result = dict(passed=True, independent_errors_collected=2, later_valid_unit_cached=True,
                      failed_build_not_linked=True, successful_units_reused=True)
        (folder / 'receipt.json').write_text(json.dumps(result, indent=2) + '\n')
        return result
    finally:
        if previous is None: os.environ.pop('BQT_SHARD_KEEP_GOING', None)
        else: os.environ['BQT_SHARD_KEEP_GOING'] = previous


def _main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=ROOT / 'build/qt612/native-shards-test')
    parser.add_argument('--qt-root', type=Path, default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    parser.add_argument('--keep-going-only', action='store_true')
    args = parser.parse_args()
    work = args.work.resolve(); work.mkdir(parents=True, exist_ok=True)
    if args.keep_going_only:
        check_keep_going(work, args.qt_root)
        print('QT612_NATIVE_KEEP_GOING_OK errors=2 no_link=1 cache_reused=1')
        return
    source = work / 'wrappers.cpp'; source.write_text(NATIVE)
    header = work / 'shared-input.h'
    # Clang validates include timestamps when loading a PCH. Preserve them
    # when rerunning fixtures whose header contents have not changed.
    native_shards.write_changed(header, '#define INPUT_VALUE 47\n')
    os.environ['BQT_SHARD_OPERATIONS'] = '1'
    payload, _, first = compile_backend(Path(os.path.relpath(source)), args.qt_root, Path(os.path.relpath(work)), 'clang++-19', ['QtCore'])
    if first['proxy_constructibility'] != [True, False, True]:
        raise RuntimeError('Proxy constructibility section was duplicated or changed')
    if first['shards']['operation_shards'] != 4:
        raise RuntimeError('Test operations were not compiled in separate translation units')
    consumer = work / 'consumer.c'; consumer.write_text(CONSUMER.replace('@PAYLOAD@', payload))
    subprocess.run(['clang', str(consumer), '-ldl', '-pthread', '-o', str(work / 'consumer')], check=True)
    tested = subprocess.run([str(work / 'consumer')], text=True, capture_output=True, check=True)
    second_payload, _, second = compile_backend(source, args.qt_root, work, 'clang++-19', ['QtCore'])
    if not second['compile_cache_hit'] or second_payload != payload:
        raise RuntimeError('Unchanged sharded payload did not use its checked cache')
    # Model an installed header being replaced with identical bytes and a new
    # timestamp, plus caches written by the previous binary-PCH-key format.
    pch_hash = hashlib.sha256((work / 'shards/shared.pch').read_bytes()).hexdigest()
    for name in ('operations-000', 'operations-001', 'operations-002', 'operations-003', 'runtime'):
        stamp = work / 'shards' / (name + '-cache.json')
        record = json.loads(stamp.read_text())
        record['key'].pop('pch_inputs', None)
        record['key']['pch'] = pch_hash
        stamp.write_text(json.dumps(record, indent=2) + '\n')
    stat = header.stat()
    header.write_bytes(header.read_bytes())
    if header.stat().st_mtime_ns == stat.st_mtime_ns:
        raise RuntimeError('The timestamp fixture did not change the shared header timestamp')
    source.write_text(NATIVE.replace('task_context == 7 && initializations == 1;',
                                    'task_context == 7 && initializations == 1 && registry_value == INPUT_VALUE;'))
    compile_backend(source, args.qt_root, work, 'clang++-19', ['QtCore'])
    timestamp_report = json.loads((work / 'native-resources.json').read_text())
    if set(timestamp_report['cached']) != {'operations-000', 'operations-001', 'operations-002', 'runtime'}:
        raise RuntimeError('Timestamp-only PCH refresh discarded valid object caches: ' + repr(timestamp_report))
    if {item['name'] for item in timestamp_report['shards']} != {'shared', 'operations-003', 'combined'}:
        raise RuntimeError('Timestamp-only PCH refresh did not rebuild the PCH and edited operation')
    source.write_text(NATIVE)
    restored_timestamp_payload, _, _ = compile_backend(source, args.qt_root, work, 'clang++-19', ['QtCore'])
    if restored_timestamp_payload != payload:
        raise RuntimeError('Timestamp-only PCH refresh changed the original native payload')
    alternate = work / 'alternate-source'; alternate.mkdir(exist_ok=True)
    alternate_source = alternate / 'wrappers.cpp'; alternate_source.write_text(NATIVE)
    native_shards.write_changed(alternate / 'shared-input.h', '#define INPUT_VALUE 49\n')
    relocated_payload, _, relocated = compile_backend(alternate_source, args.qt_root, work, 'clang++-19', ['QtCore'])
    if relocated['compile_cache_hit'] or relocated_payload == payload:
        raise RuntimeError('Identical source in another directory reused the previous quoted include')
    restored_payload, _, restored = compile_backend(source, args.qt_root, work, 'clang++-19', ['QtCore'])
    if restored['compile_cache_hit'] or restored_payload != payload:
        raise RuntimeError('Returning to the original source directory did not restore its native include')
    header.write_text('#define INPUT_VALUE 48\n')
    changed_payload, _, changed = compile_backend(source, args.qt_root, work, 'clang++-19', ['QtCore'])
    if changed['compile_cache_hit'] or changed_payload == payload:
        raise RuntimeError('Changed shared header reused stale shards')
    if any(name.startswith('operations-') for name in json.loads((work / 'native-resources.json').read_text())['cached']):
        raise RuntimeError('Changed header contents reused stale operation objects')
    # Only one operation changes: the PCH, dispatcher and the other operation
    # objects must survive. A generated source hash alone would rebuild them.
    source.write_text(NATIVE.replace('task_context == 7 && initializations == 1;',
                                    'task_context == 7 && initializations == 1 && registry_value == INPUT_VALUE;'))
    _, _, edited = compile_backend(source, args.qt_root, work, 'clang++-19', ['QtCore'])
    resource_report = json.loads((work / 'native-resources.json').read_text())
    expected_cached = {'shared', 'operations-000', 'operations-001', 'operations-002', 'runtime'}
    if edited['compile_cache_hit'] or set(resource_report['cached']) != expected_cached:
        raise RuntimeError('Single-operation edit did not preserve unaffected native units: ' + repr(resource_report))
    if {item['name'] for item in resource_report['shards']} != {'operations-003', 'combined'}:
        raise RuntimeError('Single-operation edit compiled unexpected native units')
    # Deliberately invalid body must fail before packaging; the prior checked
    # payload and outer cache stamp remain valid only for their previous input.
    prior_stamp = (work / 'native-compile-cache.json').read_bytes()
    prior_payload = (work / 'native.so').read_bytes() if (work / 'native.so').exists() else None
    source.write_text(source.read_text().replace('r->value = task_context == 7', 'unknown_native_identifier = 1; r->value = task_context == 7'))
    try:
        compile_backend(source, args.qt_root, work, 'clang++-19', ['QtCore'])
    except RuntimeError as error:
        if 'Native shard operations-003 failed' not in str(error):
            raise
    else:
        raise RuntimeError('Invalid operation body was packaged')
    if (work / 'native-compile-cache.json').read_bytes() != prior_stamp:
        raise RuntimeError('Failed compilation replaced the checked outer cache stamp')
    if prior_payload is not None and (work / 'native.so').read_bytes() != prior_payload:
        raise RuntimeError('Failed compilation replaced the checked native payload')
    controls = []
    original_transform = native_shards.inline_runtime
    for label, before, after, expected in [
        ('duplicate_callback', b'inline void callback()', b'static void callback()', 3),
        ('duplicate_registry', b'inline int registry_value', b'static int registry_value', 3),
        ('duplicate_local_static', b'inline int *local_identity', b'static int *local_identity', 3),
        ('lost_thread_local', b'inline thread_local int task_context', b'inline int task_context', 4),
        ('duplicate_initialization', b'inline Initializer initializer', b'static Initializer initializer', 1),
    ]:
        variant = work / label; variant.mkdir(exist_ok=True)
        input_source = variant / 'wrappers.cpp'; input_source.write_text(NATIVE)
        native_shards.write_changed(variant / 'shared-input.h', '#define INPUT_VALUE 47\n')
        def altered(header, flags):
            text, facts = original_transform(header, flags)
            if text.count(before) != 1:
                raise RuntimeError('Mutation did not identify one intended declaration: ' + label)
            return text.replace(before, after, 1), facts
        native_shards.inline_runtime = altered
        try:
            broken, _, _ = compile_backend(input_source, args.qt_root, variant, 'clang++-19', ['QtCore'])
        finally:
            native_shards.inline_runtime = original_transform
        c_source = variant / 'consumer.c'; c_source.write_text(CONSUMER.replace('@PAYLOAD@', broken))
        subprocess.run(['clang', str(c_source), '-ldl', '-pthread', '-o', str(variant / 'consumer')], check=True)
        result = subprocess.run([str(variant / 'consumer')], text=True, capture_output=True)
        if result.returncode != expected:
            raise RuntimeError(f'Native shard negative control {label} returned {result.returncode}, expected {expected}')
        controls.append(dict(name=label, exit_code=result.returncode))
    auxiliary = check_auxiliary_factories(work, args.qt_root)
    qml_factories = check_qml_base_factories(work, args.qt_root)
    syntax = check_bounded_syntax(work, args.qt_root)
    keep_going = check_keep_going(work, args.qt_root)
    receipt = dict(passed=True, shards=first['shards'], native_output=tested.stdout,
                   cache_hit=True, source_directory_identity=True, proxy_traits_exact=True,
                   out_of_line_constructors_destructors_and_rtti=True,
                   timestamp_change_refreshes_pch=True, verified_legacy_object_cache_preserved=True,
                   changed_shared_header_invalidates=True, single_operation_cache=sorted(expected_cached),
                   malformed_unit_rejected=True, compiler_jobs=resource_report['compiler_jobs'],
                   negative_controls=controls, auxiliary_factories=auxiliary, qml_base_factories=qml_factories, bounded_syntax=syntax,
                   keep_going=keep_going,
                   relocations=first['payload']['relocations'],
                   native_exports=['bqt_abi_call', 'bqt_abi_start', 'bqt_abi_stop'])
    (work / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(tested.stdout, end='')


def main():
    # These controls deliberately rewrite private PCH/cache records and test
    # the historical layout. Relocation has its own enabled-workspace control.
    previous = os.environ.get('BQT_NATIVE_WORKSPACE')
    os.environ['BQT_NATIVE_WORKSPACE'] = 'off'
    try:
        return _main()
    finally:
        if previous is None:
            os.environ.pop('BQT_NATIVE_WORKSPACE', None)
        else:
            os.environ['BQT_NATIVE_WORKSPACE'] = previous


if __name__ == '__main__':
    main()
