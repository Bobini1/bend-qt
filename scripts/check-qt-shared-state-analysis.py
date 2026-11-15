#!/usr/bin/env python3
"""Compare bounded semantic rewrites with whole-source Clang and run both."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
from shared_state import transform

SOURCE = r'''
#include <cassert>
#include "service.hpp"
struct BqtRequest { unsigned operation; int value; };
namespace bendqt {
static int registry = 1;
static thread_local int task = 2;
static int values[2] = {3, 4};
static int &reference = registry;
static const int immutable = 23;
struct OverloadedAddress { int value=2; int *operator&() const { return nullptr; } };
static OverloadedAddress overloaded;
struct MetaProvider { const int *operator&() const { return nullptr; } };
struct MetaProxy { static inline const MetaProvider staticMetaObject; };
static int helper();
// BQT_AUXILIARY_BEGIN test_helper 1
static int helper() {
    static int local = 7;
    auto value = [] { return local; };
    return value();
}
// BQT_AUXILIARY_END test_helper 1
static bool __attribute__((noinline)) bqt_op_10(BqtRequest *r) {
    assert(overloaded.value == 2 && &overloaded == nullptr);
    assert(external_meta<MetaProxy>() == nullptr);
    registry += helper(); ++task;
    r->value = registry + task + values[0] + reference;
    return true;
}
static bool __attribute__((noinline)) bqt_op_11(BqtRequest *r) {
    int registry = 20;
    struct Shadow { int registry = 31; } shadow;
    static int local = 9;
    auto read = [] { return local; };
    decltype(::bendqt::registry) result = registry + shadow.registry + read();
    r->value = result;
    return true;
}
static bool dispatch(BqtRequest *r) {
    switch (r->operation) {
    case 10: return bqt_op_10(r);
    case 11: return bqt_op_11(r);
    default: return false;
    }
}
}
int main() {
    BqtRequest r{10,0}; assert(bendqt::dispatch(&r)); assert(r.value == 22);
    r.operation=11; assert(bendqt::dispatch(&r)); assert(r.value == 60);
}
'''
SERVICE = r'''
#include <new>
#include <memory>
#include <rules.hpp>
template<class T> auto external_meta() { return &T::staticMetaObject; }
#define BQT_RUNTIME_THREAD_LOCAL 1
namespace bendqt {
template<class T, class Initialize>
T &runtime_shared_state_init(const char *, unsigned, Initialize initialize) {
    static T *value = nullptr;
    if (!value) { value = static_cast<T*>(::operator new(sizeof(T))); initialize(value); }
    return *value;
}
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=ROOT / 'build/shared-state-analysis-check')
    args = parser.parse_args()
    work = args.work.resolve(); work.mkdir(parents=True, exist_ok=True)
    (work / 'service.hpp').write_text(SERVICE)
    (work / 'rules.hpp').write_text('// original include\n')
    shadow = work / 'earlier-include'; shadow.mkdir(exist_ok=True)
    # Each invocation starts with the same include ordering control.
    (shadow / 'rules.hpp').unlink(missing_ok=True)
    source = work / 'original.cpp'; source.write_text(SOURCE)
    flags = ['-std=c++17', '-I' + str(shadow), '-I' + str(work)]
    previous = os.environ.get('BQT_STATE_SOURCE_BYTES')
    try:
        os.environ['BQT_STATE_SOURCE_BYTES'] = '8000000'
        plain, plain_facts = transform(source, flags)
        os.environ['BQT_STATE_SOURCE_BYTES'] = '0'
        bounded, bounded_facts = transform(source, flags)
        if sorted(plain_facts, key=lambda row: row['key']) != sorted(bounded_facts, key=lambda row: row['key']):
            raise RuntimeError('Whole-source and bounded analyses disagree about mutable storage')
        if re.sub(r'\s+', ' ', plain).strip() != re.sub(r'\s+', ' ', bounded).strip():
            (work / 'plain.cpp').write_text(plain); (work / 'bounded.cpp').write_text(bounded)
            raise RuntimeError('Whole-source and bounded analyses produce different C++ tokens')
        cache = work / 'shared-state-analysis/cache.json'
        stamp = cache.read_bytes()
        repeated, repeated_facts = transform(source, flags)
        if repeated != bounded or repeated_facts != bounded_facts or cache.read_bytes() != stamp:
            raise RuntimeError('The checked semantic cache changed the result')
        (work / 'service.hpp').write_text(SERVICE + '\n// changed header\n')
        transform(source, flags)
        changed = json.loads(cache.read_text())
        if changed['inputs'] == json.loads(stamp)['inputs']:
            raise RuntimeError('A changed transitive header reused semantic analysis')
        (shadow / 'rules.hpp').write_text('// original include\n')
        transform(source, flags)
        shadowed = json.loads(cache.read_text())
        if shadowed['inputs'] == changed['inputs'] or str(shadow / 'rules.hpp') not in shadowed['inputs']['dependencies']:
            raise RuntimeError('A newly shadowing header reused semantic analysis')
        cached_output = work / 'shared-state-analysis/transformed.cpp'
        cached_output.write_text('corrupt cached result\n')
        repaired, _ = transform(source, flags)
        if repaired != bounded or cached_output.read_text() != bounded:
            raise RuntimeError('A corrupted semantic result was reused')
        for name, output in [('plain', plain), ('bounded', bounded)]:
            cpp = work / (name + '.cpp'); cpp.write_text(output)
            subprocess.run(['clang++-19', *flags, str(cpp), '-o', str(work / name)], check=True)
            subprocess.run([str(work / name)], check=True)
        source.write_text(SOURCE.replace('return value();', 'return value() + later;').replace(
            '// BQT_AUXILIARY_END test_helper 1', '// BQT_AUXILIARY_END test_helper 1\nstatic int later=5;'))
        try:
            transform(source, flags)
        except RuntimeError as error:
            if 'after its original position' not in str(error): raise
        else:
            raise RuntimeError('A body incorrectly acquired visibility of a later declaration')
        source.write_text(SOURCE.replace('registry += helper();', 'registry += missing();'))
        try:
            transform(source, flags)
        except RuntimeError as error:
            if 'undeclared identifier' not in str(error): raise
        else:
            raise RuntimeError('A malformed native body escaped semantic checking')
    finally:
        if previous is None: os.environ.pop('BQT_STATE_SOURCE_BYTES', None)
        else: os.environ['BQT_STATE_SOURCE_BYTES'] = previous
    (work / 'receipt.json').write_text(json.dumps(dict(passed=True, same_rewrites=True,
        storage=plain_facts, native_runs=2, later_declaration_rejected=True,
        malformed_body_rejected=True), indent=2) + '\n')
    print('QT_SHARED_STATE_ANALYSIS_OK same_rewrites=1 shadowing=1 static_locals=1 tls=1 decltype=1 overloaded_address=1 external_const_meta=1 native_runs=2 checked_cache=1 changed_header=1 include_shadow=1 corrupt_cache=1 negative_controls=2')


if __name__ == '__main__':
    main()
