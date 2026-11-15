#!/usr/bin/env python3
"""Check shared native storage across isolated Charts and Graphs payloads."""
import argparse
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
COMMON = r'''
#include "shared_runtime.h"
#include "shared_runtime.cpp"
#include <QtCore/QObject>
#include <vector>
struct SharedEntry { QObject *object; unsigned family; };
static std::vector<SharedEntry> &registry() {
    return bendqt::runtime_shared_state<std::vector<SharedEntry>>("test.registry", 0, [] {
        ++bendqt::runtime_shared_state<int>("test.registry.initializations", 0, [] { return 0; });
        return std::vector<SharedEntry>{{nullptr, 0}};
    });
}
'''
PLUGIN = r'''
#include <@MODULE@/QLineSeries>
#include <QtGui/QPen>
#include "common.h"
#define API extern "C" __attribute__((visibility("default")))
API void attach(const BqtRuntimeServices *services) { bendqt::module_runtime_services = services; }
API unsigned make() {
    auto *value = new QLineSeries;
    unsigned id = unsigned(registry().size());
    registry().push_back({value, @FAMILY@});
    QObject::connect(value, &QObject::destroyed, [id] { registry().at(id).object = nullptr; });
    return id;
}
API int check(unsigned id) {
    auto *series = qobject_cast<QLineSeries *>(registry().at(id).object);
    if (!series) return 0;
    @CHECK@
}
API unsigned count() { return unsigned(registry().size()); }
API QObject *object(unsigned id) { return registry().at(id).object; }
API int qt_cast(unsigned id) { return qobject_cast<QLineSeries *>(object(id)) != nullptr; }
API int tls_increment() {
    return ++bendqt::runtime_shared_state<int>("test.thread.counter", BQT_RUNTIME_THREAD_LOCAL, [] { return 0; });
}
API void append(unsigned id) {
    auto *series = qobject_cast<QLineSeries *>(object(id));
    if (!series) throw std::runtime_error("Wrong native graph family");
    QObject::connect(series, &QXYSeries::pointAdded, series, [](auto) {
        ++bendqt::runtime_shared_state<int>("test.signals", 0, [] { return 0; });
    });
    series->append(1, 2);
}
API void clear() {
    // QObject destruction dispatches through the actual native object's vtable.
    for (auto &entry : registry()) { delete entry.object; entry.object = nullptr; }
}
'''
MAIN = r'''
#include <QtWidgets/QApplication>
#include <atomic>
#include <cassert>
#include <cstdio>
#include <dlfcn.h>
#include <thread>
#include "shared_runtime.h"
#include "shared_runtime.c"
#include "shared_runtime.cpp"
struct Module {
    void *handle;
    void (*attach)(const BqtRuntimeServices *);
    unsigned (*make)();
    int (*check)(unsigned);
    unsigned (*count)();
    QObject *(*object)(unsigned);
    int (*qt_cast)(unsigned);
    int (*tls_increment)();
    void (*append)(unsigned);
    void (*clear)();
    Module(const char *name, const BqtRuntimeServices *services) {
        handle = dlopen(name, RTLD_NOW | RTLD_LOCAL);
        if (!handle) { std::fprintf(stderr, "%s\n", dlerror()); std::abort(); }
#define LOAD(member) member = reinterpret_cast<decltype(member)>(dlsym(handle, #member)); assert(member)
        LOAD(attach); LOAD(make); LOAD(check); LOAD(count); LOAD(object);
        LOAD(qt_cast); LOAD(tls_increment); LOAD(append); LOAD(clear);
#undef LOAD
        attach(services);
    }
};
struct Dependency {
    std::vector<int> *events;
    bool alive = true;
    ~Dependency() { alive = false; events->push_back(2); }
};
struct Dependent {
    Dependency *dependency;
    ~Dependent() { assert(dependency->alive); dependency->events->push_back(1); }
};
int main(int argc, char **argv) {
    QApplication application(argc, argv);
    BqtSharedStore store;
    BqtRuntimeServices services;
    assert(bqt_shared_store_init(&store, &services));
    bendqt::module_runtime_services = &services;
    Module first(argv[1], &services), second(argv[2], &services);
    unsigned one = first.make(), two = second.make();
    assert(one == 1 && two == 2 && first.count() == 3 && second.count() == 3);
    assert(first.check(one) && second.check(two));
    assert(!first.qt_cast(two) && !second.qt_cast(one));
    first.append(one); second.append(two);
    assert(bendqt::runtime_shared_state<int>("test.signals", 0, [] { return 0; }) == 2);
    assert(bendqt::runtime_shared_state<int>("test.registry.initializations", 0, [] { return 0; }) == 1);
    assert(first.tls_increment() == 1 && second.tls_increment() == 2);
    for (unsigned i = 0; i != 32; ++i) {
        std::thread worker([&] { assert(first.tls_increment() == 1 && second.tls_increment() == 2); });
        worker.join();
    }
    assert(first.tls_increment() == 3);
    unsigned threads = 0;
    for (auto *thread = store.threads; thread; thread = thread->next) ++threads;
    assert(threads == 1);
    bool mismatch = false;
    try { bendqt::runtime_shared_state<double>("test.signals", 0, [] { return 0.; }); }
    catch (const std::runtime_error &) { mismatch = true; }
    assert(mismatch);
    bool recursive = false;
    try {
        bendqt::runtime_shared_state<int>("test.recursive", 0, [] {
            return bendqt::runtime_shared_state<int>("test.recursive", 0, [] { return 0; });
        });
    } catch (const std::runtime_error &) { recursive = true; }
    assert(recursive);
    std::vector<int> destruction;
    bendqt::runtime_shared_state<Dependent>("test.dependent", 0, [&] {
        auto &dependency = bendqt::runtime_shared_state<Dependency>("test.dependency", 0,
            [&] { return Dependency{&destruction}; });
        return Dependent{&dependency};
    });
    // A parent made through one module owns a child made through the other.
    second.object(two)->setParent(first.object(one));
    first.clear();
    assert(!first.object(one) && !second.object(two));
    std::atomic<bool> ready{false}, finish{false};
    std::thread active([&] {
        assert(second.tls_increment() == 1);
        ready.store(true);
        while (!finish.load()) std::this_thread::yield();
        assert(first.tls_increment() == 2);
    });
    while (!ready.load()) std::this_thread::yield();
    assert(!bqt_shared_store_shutdown(&store));
    finish.store(true); active.join();
    assert(bqt_shared_store_shutdown(&store));
    assert((destruction == std::vector<int>{1, 2}));
    dlclose(second.handle); dlclose(first.handle);
    std::puts("QT612_SHARED_RUNTIME_OK registry=1 families=2 signals=1 tls=1 thread_reuse=1 layout_guard=1 recursion_guard=1 destruction_order=1 worker_shutdown=1");
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qt-root', type=Path, default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    parser.add_argument('--work', type=Path, default=ROOT / 'build/shared-runtime-check')
    args = parser.parse_args()
    work, qt = args.work.resolve(), args.qt_root.resolve()
    work.mkdir(parents=True, exist_ok=True)
    for name in ('shared_runtime.h', 'shared_runtime.c', 'shared_runtime.cpp'):
        (work / name).write_bytes((ROOT / 'generator/templates' / name).read_bytes())
    host = work / 'host.c'
    host.write_text('#include "shared_runtime.h"\n#include "shared_runtime.c"\n')
    subprocess.run(['clang-19', '-std=c11', '-D_GNU_SOURCE', '-Werror', '-c', str(host),
                    '-o', str(work / 'host.o')], check=True)
    (work / 'common.h').write_text(COMMON)
    flags = ['clang++-19', '-std=c++17', '-O1', '-fPIC', '-fvisibility=hidden',
             '-I' + str(qt / 'include'), '-L' + str(qt / 'lib')]
    for module, family, check in (
        ('QtGraphs', 1, 'series->setWidth(7); return series->width() == 7;'),
        ('QtCharts', 2, 'series->setPen(QPen(Qt::red)); return series->pen().color() == Qt::red;'),
    ):
        source = work / (module + '.cpp')
        source.write_text(PLUGIN.replace('@MODULE@', module).replace('@FAMILY@', str(family)).replace('@CHECK@', check))
        subprocess.run([*flags, '-shared', str(source), '-lQt6' + module[2:], '-lQt6Gui', '-lQt6Core',
                        '-pthread', '-o', str(work / (module + '.so'))], check=True)
    source = work / 'main.cpp'; source.write_text(MAIN)
    executable = work / 'main'
    subprocess.run([*flags, str(source), '-lQt6Widgets', '-lQt6Gui', '-lQt6Core', '-ldl', '-pthread',
                    '-o', str(executable)], check=True)
    environment = dict(os.environ, LD_LIBRARY_PATH=str(qt / 'lib'), QT_QPA_PLATFORM='offscreen')
    runs = []
    for modules in (('QtGraphs', 'QtCharts'), ('QtCharts', 'QtGraphs')):
        tested = subprocess.run([str(executable), *(str(work / (module + '.so')) for module in modules)],
                                env=environment, capture_output=True, text=True, check=True)
        runs.append(dict(load_order=modules, output=tested.stdout.strip()))
    receipt = dict(passed=True, boundary='Shared storage and native module isolation; complete Bend runtime integration is separate', runs=runs)
    (work / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(runs[0]['output'])


if __name__ == '__main__':
    main()
