#!/usr/bin/env python3
"""Check outlined proxy constructor factories through full/public native ELF."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
import callbacks
import native_shards
from backend import compile_backend, compiler_flags


def shard_control():
    spec = importlib.util.spec_from_file_location('proxy_shard_control', ROOT / 'scripts/check-qt-native-shards.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture(control):
    proxy = 'BqtProxy_FactoryDomain__NativeBase'
    ordinary = ['FactoryScope scope;', f'auto value = std::make_unique<{proxy}>(int(r->value));',
                'if (r->value == 88) { r->value = 0; return true; }',
                'r->value = value->protectedValue();', 'r->pointer = value.get();',
                'factory_raw = value.release();',
                f'factory_delete = [](void *value) {{ delete static_cast<{proxy} *>(value); }};',
                'return true;']
    shared = ['FactoryScope scope;',
              f'auto value = QSharedPointer<{proxy}>::create(QString::number(r->value));',
              f'factory_shared = std::make_shared<QSharedPointer<{proxy}>>(value);',
              'r->pointer = value.data();', 'r->value = value->protectedValue();', 'return true;']
    placement = ['FactoryScope scope;', f'auto *value = new(r->pointer) {proxy}(int(r->value));',
                 'r->value = value->protectedValue();', 'return true;']
    factories = [(('bqt_create_shared_' if i % 2 else 'bqt_create_') + str(1000 + i),
                  placement if i == 4 else shared if i % 2 else ordinary) for i in range(128)]
    classes = [dict(name='FactoryDomain::NativeBase', virtuals=[], factories=factories),
               dict(name='NativeGuarded', virtuals=[], factories=[('bqt_create_1128',
                    ['RhiOnlyValue marker;', 'r->value = marker.value;', 'return true;'])])]
    generator = SimpleNamespace(callback_classes=classes, callback_functions=[], callback_qml=False,
        classes={c['name']: dict(qobject=False) for c in classes}, ids={}, profile={})
    generator.abi_cohort = dict(names={'RhiOnlyValue'}, headers=[], pattern=re.compile(r'\bRhiOnlyValue\b'),
        proxies=set(), operations=set(), exact_helpers={})
    generated = callbacks.cpp(generator)
    assert 'BqtProxy_NativeGuarded' in generator.abi_cohort['proxies'], 'Body-only ABI dependency lost'
    stripped, units = native_shards.split_auxiliary(generated)
    assert len(units) == 129 and all(row[0] == 'proxy_constructors' for row in units)
    assert [row[1] for row in units] == list(range(1000, 1129))
    assert all(f'static bool {name}(BqtRequest *r);' in stripped for name, _ in factories)
    assert 'std::make_unique<' not in stripped and 'QSharedPointer<' not in stripped
    assert units[-1][2].startswith('#if BQT_HAS_RHI\n')
    for c in classes:
        for name, body in c['factories']:
            definition = next(row[2] for row in units if row[1] == int(name.rsplit('_', 1)[1]))
            assert '\n'.join('    ' + line for line in body) in definition, 'Constructor body changed'
    preamble = r'''
static int factory_living = 0, factory_destroyed = 0, factory_scopes = 0;
static int factory_observed = 0, factory_proxy_destroyed = 0;
struct FactoryScope { FactoryScope() { ++factory_scopes; } ~FactoryScope() { --factory_scopes; } };
struct CallbackHandlers { bool (*accepts)(uint32_t) = nullptr; };
struct NativeDeletionObserver {
    template<class T> void observe(T *) { ++factory_observed; }
    void begin() {}
};
static void callback_proxy_destroyed(uint32_t, const std::shared_ptr<std::atomic<bool>> &alive, CallbackHandlers &) {
    alive->store(false); ++factory_proxy_destroyed;
}
namespace FactoryDomain {
class NativeBase {
protected:
    int value;
    explicit NativeBase(int number) : value(number) {
        if (number < 0) throw std::runtime_error("constructor rejected");
        ++factory_living;
    }
    explicit NativeBase(const QString &text) : value(1000 + text.size()) { ++factory_living; }
    virtual ~NativeBase() { --factory_living; ++factory_destroyed; }
    int protectedValue() const { return value * 3; }
public:
    virtual int serial() const { return value; }
};
}
class NativeGuarded { public: virtual ~NativeGuarded() = default; };
#if BQT_HAS_RHI
struct RhiOnlyValue { int value = 111; };
#endif
static void *factory_raw = nullptr;
static void (*factory_delete)(void *) = nullptr;
static std::shared_ptr<void> factory_shared;
static bool (*factory_constructor)(BqtRequest *) = nullptr;
static const std::type_info *factory_rtti = nullptr;
'''
    create = f'''
    BqtRequest made{{0,7,nullptr}};
    factory_constructor = &{proxy}::bqt_create_1000;
    factory_constructor(&made);
    factory_rtti = &typeid(*static_cast<{proxy} *>(made.pointer));
    r->value = r->value && made.value == 21 && factory_living == 1 && !factory_scopes;
'''
    verify = f'''
    auto *created = static_cast<{proxy} *>(factory_raw);
    r->value = r->value && dynamic_cast<{proxy} *>(static_cast<FactoryDomain::NativeBase *>(created))
        && factory_rtti == &typeid({proxy}) && created->serial() == 7
        && factory_constructor == &{proxy}::bqt_create_1000;
    BqtRequest shared{{0,42,nullptr}};
    {proxy}::bqt_create_shared_1001(&shared);
    r->value = r->value && shared.value == 3006 && factory_living == 2 && !factory_scopes;
    BqtRequest failed{{0,88,nullptr}};
    {proxy}::bqt_create_1002(&failed);
    r->value = r->value && !failed.value && factory_living == 2 && !factory_scopes;
    BqtRequest thrown{{0,-1,nullptr}};
    try {{ {proxy}::bqt_create_1000(&thrown); r->value = 0; }}
    catch (const std::runtime_error &) {{ r->value = r->value && factory_living == 2 && !factory_scopes; }}
    std::aligned_storage_t<sizeof({proxy}), alignof({proxy})> storage;
    BqtRequest placed{{0,9,&storage}};
    {proxy}::bqt_create_1004(&placed);
    auto *placed_value = reinterpret_cast<{proxy} *>(&storage);
    r->value = r->value && placed.value == 27 && factory_living == 3 && placed_value->serial() == 9;
    placed_value->~{proxy}();
#if BQT_HAS_RHI
    BqtRequest guarded{{}}; BqtProxy_NativeGuarded::bqt_create_1128(&guarded);
    r->value = r->value && guarded.value == 111;
#else
    r->value = r->value && std::is_abstract_v<BqtProxy_NativeGuarded>;
#endif
    factory_delete(factory_raw); factory_raw = nullptr; factory_shared.reset();
    r->value = r->value && !factory_living && !factory_scopes
        && factory_destroyed == 4 && factory_proxy_destroyed == 4 && factory_observed == 4;
'''
    native = control.NATIVE.replace('static int initializations = 0;', preamble + generated + '\nstatic int initializations = 0;')
    native = native.replace('__attribute__((used, section(".bqt.proxy_traits"))) static const unsigned char bqt_proxy_traits[] = {1,0,1};', '')
    native = native.replace('r->pointer = registry_pointer; r->value = 1; return true;',
                            'r->pointer = registry_pointer; r->value = 1;\n' + create + '\nreturn true;')
    native = native.replace('catch (const Marker &value) { r->value = r->value && value.value == 77; }',
                            'catch (const Marker &value) { r->value = r->value && value.value == 77; }\n' + verify)
    return ('#ifndef BQT_HAS_RHI\n#define BQT_HAS_RHI 1\n#endif\n'
            '#include <QtCore/QSharedPointer>\n#include <QtCore/QString>\n#include <atomic>\n'
            '#include <memory>\n#include <stdexcept>\n#include <type_traits>\n' + native)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qt-root', type=Path, default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    parser.add_argument('--work', type=Path, default=ROOT / 'build/qt612/proxy-constructor-shards-check')
    args = parser.parse_args()
    work = args.work.resolve(); work.mkdir(parents=True, exist_ok=True)
    qt = args.qt_root.resolve()
    files = [Path(__file__).resolve(), ROOT / 'generator/callbacks.py', ROOT / 'generator/abi_cohorts.py',
             ROOT / 'scripts/check-qt-native-shards.py']
    hashes = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    receipt = dict(passed=False, source_sha256=hashes)
    destination = work / 'receipt.json'; destination.write_text(json.dumps(receipt, indent=2) + '\n')
    control = shard_control(); original = fixture(control)
    # This control inspects private shard/header layout. Production compilation
    # independently exercises relocation; keep this deliberate internal view.
    previous = {key: os.environ.get(key) for key in ('BQT_SHARD_OPERATIONS', 'BQT_SHARD_JOBS', 'BQT_AUXILIARY_FUNCTIONS', 'BQT_NATIVE_WORKSPACE')}
    os.environ.update(BQT_SHARD_OPERATIONS='1', BQT_SHARD_JOBS='1', BQT_AUXILIARY_FUNCTIONS='64', BQT_NATIVE_WORKSPACE='off')
    try:
        results = {}
        for public in (False, True):
            folder = work / ('public' if public else 'full'); folder.mkdir(exist_ok=True)
            source = folder / 'wrappers.cpp'
            source.write_text(original.replace('#define BQT_HAS_RHI 1', '#define BQT_HAS_RHI 0') if public else original)
            native_shards.write_changed(folder / 'shared-input.h', '#define INPUT_VALUE 47\n')
            payload, _, result = compile_backend(source, qt, folder, 'clang++-19', ['QtCore'])
            assert result['shards']['auxiliary_functions'] == 129 and result['shards']['auxiliary_shards'] == 3
            assert result['shards']['operation_shards'] == 4
            assert result['proxy_constructibility'] == ([True, False] if public else [True, True])
            header = (folder / 'shards/shared.hpp').read_text()
            assert 'std::make_unique<BqtProxy_' not in header and 'QSharedPointer<BqtProxy_' not in header
            consumer = folder / 'consumer.c'; consumer.write_text(control.CONSUMER.replace('@PAYLOAD@', payload))
            subprocess.run(['clang', str(consumer), '-ldl', '-pthread', '-o', str(folder / 'consumer')], check=True)
            checked = subprocess.run([str(folder / 'consumer')], text=True, capture_output=True,
                                     env=dict(os.environ, LD_LIBRARY_PATH=str(qt / 'lib')))
            if checked.returncode:
                raise RuntimeError('Proxy factory native consumer failed: ' + str(checked.returncode) + checked.stdout + checked.stderr)
            results['public' if public else 'full'] = json.loads((folder / 'native-resources.json').read_text())
        # The outer class guard is insufficient once auxiliary extraction moves
        # the body. Prove the retained inner guard rejects that exact regression.
        negative = work / 'negative'; negative.mkdir(exist_ok=True)
        start = original.index('// BQT_AUXILIARY_BEGIN proxy_constructors 1128\n')
        end = original.index('// BQT_AUXILIARY_END proxy_constructors 1128\n', start)
        broken = original[start:end].replace('#if BQT_HAS_RHI\n', '', 1).replace('#endif\n', '', 1)
        bad = (original[:start] + broken + original[end:]).replace('#define BQT_HAS_RHI 1', '#define BQT_HAS_RHI 0')
        source = negative / 'wrappers.cpp'; source.write_text(bad)
        native_shards.write_changed(negative / 'shared-input.h', '#define INPUT_VALUE 47\n')
        try:
            native_shards.check_syntax(source, negative / 'syntax', compiler_flags(qt, 'clang++-19', ['QtCore']), maximum_operations=1)
        except RuntimeError as error:
            if 'auxiliary-proxy_constructors-' not in str(error):
                raise
        else:
            raise RuntimeError('Missing extracted constructor ABI guard was accepted')
        assert hashes == {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
        receipt.update(passed=True, factories=129, operation_units=4, auxiliary_batches=3,
                       normal_and_shared=True, protected_access_and_overloads=True, placement=True,
                       rtti_and_factory_identity=True, raii_and_exception_cleanup=True,
                       public_abi_body_dependency=True, missing_extracted_guard_rejected=True,
                       resources=results)
        destination.write_text(json.dumps(receipt, indent=2) + '\n')
        print('QT612_PROXY_CONSTRUCTOR_SHARDS_OK')
    finally:
        for key, value in previous.items():
            if value is None: os.environ.pop(key, None)
            else: os.environ[key] = value


if __name__ == '__main__':
    main()
