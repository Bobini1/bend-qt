#!/usr/bin/env python3
"""Compile two independently transformed runtimes and exercise shared state."""
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
from shared_state import transform

SOURCE = r'''
#include "shared_runtime.h"
#include "shared_runtime.cpp"
#include <atomic>
#include <mutex>
#include <type_traits>
#include <vector>
#define API extern "C" __attribute__((visibility("default")))
namespace runtime {
static std::vector<int> entries{3};
static std::atomic<int> calls{0};
static thread_local int counter = 0;
static int array[3] = {2, 4, 6};
static const int module_constants[MODULE_CONSTANT] = {MODULE_CONSTANT};
struct Frame { static inline int current = 0; int entries = 9; };
static int &first() { static int head = 10; return head; }
static int many() { static int left = 1; static int right = 2; return ++left + ++right; }
static int lock(int seed) {
    static std::mutex mutex;
    static int initial = seed;
    std::lock_guard<std::mutex> guard(mutex);
    return ++initial;
}
static int shadow(int entries) { Frame frame; return entries + frame.entries; }
}
API int increment() {
    static_assert(std::is_same_v<decltype(runtime::Frame::current), int>);
    static_assert(std::is_same_v<decltype(runtime::entries), std::vector<int>>);
    ++runtime::calls;
    ++runtime::Frame::current;
    ++runtime::first();
    runtime::entries.push_back(5);
    return runtime::calls + runtime::Frame::current + runtime::first() + int(runtime::entries.size());
}
API int local_many() { return runtime::many(); }
API int local_lock(int value) { return runtime::lock(value); }
API int shadow() { return runtime::shadow(4) + runtime::array[1]; }
API int thread_count() { return ++runtime::counter; }
API int local_lambda() { static int value = 0; return [] { return ++value; }(); }
API int local_guard() {
    static bool active = false;
    if (active) return -1;
    struct Guard { ~Guard() { active = false; } } guard;
    active = true; return 42;
}
API int local_thread() { static thread_local int value = 0; return [] { return ++value; }(); }
API int module_constant() { return runtime::module_constants[0]; }
API int set_shared_array(int value) { return runtime::array[0] = value; }
API int get_shared_array() { return runtime::array[0]; }
'''

HOST = r'''
#include "shared_runtime.h"
#include "shared_runtime.c"
static BqtSharedStore store;
static BqtRuntimeServices services;
__attribute__((visibility("default"))) const BqtRuntimeServices *start(void) {
    return bqt_shared_store_init(&store, &services) ? &services : NULL;
}
__attribute__((visibility("default"))) int stop(void) { return bqt_shared_store_shutdown(&store); }
'''


def main():
    work = ROOT / 'build/partition-state-check'
    work.mkdir(parents=True, exist_ok=True)
    for name in ('shared_runtime.h', 'shared_runtime.c', 'shared_runtime.cpp'):
        (work / name).write_bytes((ROOT / 'generator/templates' / name).read_bytes())
    flags = ['-std=c++17', '-O1', '-fPIC', '-fvisibility=hidden', '-pthread']
    libraries, inventories = [], []
    for part, name in enumerate(('first', 'second'), 1):
        source = work / (name + '.cpp')
        source.write_text(SOURCE)
        part_flags = [*flags, '-DMODULE_CONSTANT=' + str(part)]
        rewritten, facts = transform(source, part_flags)
        source.write_text(rewritten)
        inventories.append(facts)
        attach = work / (name + '-attach.cpp')
        attach.write_text('#include "shared_runtime.h"\n#include "shared_runtime.cpp"\n'
            'extern "C" __attribute__((visibility("default"))) void attach(const BqtRuntimeServices *services) { bendqt::module_runtime_services = services; }\n')
        subprocess.run(['clang++-19', *part_flags, '-shared', source, attach, '-o', work / (name + '.so')], check=True)
        library = ctypes.CDLL(str(work / (name + '.so')), mode=os.RTLD_LOCAL | os.RTLD_NOW)
        library.attach.argtypes = [ctypes.c_void_p]
        libraries.append(library)
    assert inventories[0] == inventories[1], 'Keys and layouts must not depend on source filenames or offsets'
    host = work / 'host.c'; host.write_text(HOST)
    subprocess.run(['clang-19', '-std=c11', '-D_GNU_SOURCE', '-fPIC', '-shared', '-pthread', host,
                    '-o', work / 'host.so'], check=True)
    service = ctypes.CDLL(str(work / 'host.so'))
    service.start.restype = ctypes.c_void_p
    pointer = service.start(); assert pointer
    for library in libraries: library.attach(pointer)
    assert libraries[0].increment() == 15
    assert libraries[1].increment() == 19
    assert libraries[0].local_many() == 5 and libraries[1].local_many() == 7
    assert libraries[0].local_lock(20) == 21 and libraries[1].local_lock(50) == 22
    assert libraries[0].local_lambda() == 1 and libraries[1].local_lambda() == 2
    assert libraries[0].local_guard() == 42 and libraries[1].local_guard() == 42
    assert libraries[0].local_thread() == 1 and libraries[1].local_thread() == 2
    assert libraries[0].module_constant() == 1 and libraries[1].module_constant() == 2
    assert libraries[0].set_shared_array(42) == 42 and libraries[1].get_shared_array() == 42
    assert all(library.shadow() == 17 for library in libraries)
    assert libraries[0].thread_count() == 1 and libraries[1].thread_count() == 2
    observed = []
    for _ in range(16):
        worker = threading.Thread(target=lambda: observed.append((libraries[0].thread_count(), libraries[1].thread_count())))
        worker.start(); worker.join()
    assert observed == [(1, 2)] * 16
    local_observed = []
    worker = threading.Thread(target=lambda: local_observed.append((libraries[0].local_thread(), libraries[1].local_thread())))
    worker.start(); worker.join()
    assert local_observed == [(1, 2)]
    assert service.stop() == 1
    (work / 'receipt.json').write_text(json.dumps(dict(passed=True, declarations=inventories[0],
        boundary='Compiler-resolved native state sharing; complete generated Bend package validation remains separate'), indent=2) + '\n')
    print('QT612_PARTITION_STATE_OK shared=1 local_statics=1 shadowing=1 decltype=1 tls=1')


if __name__ == '__main__':
    main()
