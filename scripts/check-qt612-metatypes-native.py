#!/usr/bin/env python3
"""Fresh Hub imports for runtime values, metatypes, gadgets and future waits."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
from backend import command, compile_backend
from generate import Generator
from adapters import native_header_support
from lifetime import evaluate_tables, cpp_tables
from upstream import prepare
import callbacks
import native_objects
import representations
import qobject_interfaces
import qio_pipe


GADGET = '''#pragma once
#include <QtCore/QObject>
#include <QtCore/QString>
#include <QtCore/QMetaType>
#include <QtCore/QFutureInterface>
#include <chrono>
#include <map>
#include <stdexcept>
#include <thread>
// Threads producing the fixture's delayed future results.
inline std::map<QFutureInterfaceBase *, std::thread> &fixture_producers() {
    static std::map<QFutureInterfaceBase *, std::thread> producers;
    return producers;
}
class alignas(64) BendQtTestGadget {
    Q_GADGET
    Q_PROPERTY(QString text MEMBER text RESET resetText)
public:
    static inline int live = 0;
    QString text = QStringLiteral("initial");
    BendQtTestGadget() { ++live; }
    BendQtTestGadget(const BendQtTestGadget &other) : text(other.text) { ++live; }
    ~BendQtTestGadget() { --live; }
    void resetText() { text = QStringLiteral("reset"); }
    Q_INVOKABLE QString echo(QString suffix) { text += suffix; return text; }
    Q_INVOKABLE void mutate(QString &value) { value += QStringLiteral(" changed"); }
    Q_INVOKABLE void throwing(QString &value) { value = QStringLiteral("partial"); throw std::runtime_error("meta-call failed after a native write"); }
};
Q_DECLARE_METATYPE(BendQtTestGadget)
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    cache = Path.home() / '.cache/bend-qt-generator'
    parser.add_argument('--qt-root', type=Path, default=cache / 'Qt/6.12.0/gcc_64')
    parser.add_argument('--extractor', type=Path, default=cache / 'build/bend-qt-extract')
    args = parser.parse_args()
    qt = args.qt_root
    work = ROOT / 'build/qt612/check/metatypes-native'
    work.mkdir(parents=True, exist_ok=True)
    profile = json.loads((ROOT / 'generator/qt612-core/profile.json').read_text())
    profile['qt_modules'] += ['QtTest', 'QtRemoteObjects']
    headers, system, modules, env, _ = prepare(cache / 'pyside-setup', qt, profile['qt_modules'], work)
    profile['qt_modules'] = modules
    logs = work / 'extractor'; logs.mkdir(exist_ok=True)
    result = command([args.extractor, headers, system, work / 'api.json', logs,
                      qt / 'include', qt / 'mkspecs/linux-g++', *[qt / 'include' / m for m in modules]], env=env)
    (work / 'extraction.log').write_text(result.stdout + result.stderr)
    api = json.loads((work / 'api.json').read_text())
    qobject_interfaces.restore(api, work)
    qio_pipe.restore(api, work)
    native_objects.refine_traits(api, qt, modules, work, 'clang++-19')
    g = Generator(api, profile); g.collect()
    # Narrow native fixture, not a production class discovery policy.
    g.methods = [m for m in g.methods if m['class'] in ('QObject', 'QCoreApplication', 'QMetaType', 'QMetaProperty', 'QMetaObject', 'QMetaMethod', 'QGenericArgument', 'QGenericReturnArgument', 'QTimer', 'QVariant', 'QSize', 'QDataStream', 'QJSPrimitiveValue', 'QFutureInterfaceBase', 'QTest', 'QtRemoteObjects')]
    callbacks.prepare(g)
    g.callback_classes = []; g.callback_methods = {}; g.callback_functions = []; g.callback_qml = False
    operation = g.next_id; g.next_id += 1
    g.emit_effect('Fixture.liveGadgets', [], dict(kind='u32', bend='U32', raw='U32'), operation)
    g.cases.append(f'case {operation}: {{\n    r->result.word = BendQtTestGadget::live; return true;\n}}')
    operation = g.next_id; g.next_id += 1
    g.emit_effect('Fixture.future', [('mode', dict(kind='u32', bend='U32', raw='U32'))],
                  dict(kind='value', name='QFutureInterfaceBase', bend='QFutureInterfaceBase', raw='U32'), operation)
    g.cases.append(f'''case {operation}: {{
        unsigned mode = r->arguments[0].word;
        if (mode > 5) return fail(r, EINVAL, "Unknown future fixture mode");
        auto *promise = new QFutureInterface<int>();
        promise->reportStarted();
        // A delayed result comes from another thread: waiting blocks the main
        // thread, as it does in Qt. Destruction joins that thread first.
        auto id = insert(r, static_cast<QFutureInterfaceBase *>(promise), nullptr,
            {g.ids['QFutureInterfaceBase']}, [](void *p) {{
                auto *base = static_cast<QFutureInterfaceBase *>(p);
                auto found = fixture_producers().find(base);
                if (found != fixture_producers().end()) {{ found->second.join(); fixture_producers().erase(found); }}
                delete static_cast<QFutureInterface<int> *>(base);
            }}, true, NativeTraits<QFutureInterfaceBase>::cast);
        if (!id) return true;
        r->result.word = id; r->result.owned_handle = id;
        auto finish = [promise, mode] {{
            if (mode == 2) promise->reportException(std::make_exception_ptr(std::runtime_error("fixture future failed")));
            else if (mode != 3) promise->reportResult(17, 3);
            if (mode >= 4) promise->cancel();
            promise->reportFinished();
        }};
        if (mode == 0 || mode == 3 || mode == 4) finish();
        else fixture_producers().emplace(static_cast<QFutureInterfaceBase *>(promise), std::thread([finish] {{
            std::this_thread::sleep_for(std::chrono::milliseconds(30));
            finish();
        }}));
        return true;
}}''')
    operation = g.next_id; g.next_id += 1
    g.emit_effect('Fixture.nativeNext', [('future', dict(kind='value', name='QFutureInterfaceBase', bend='QFutureInterfaceBase', raw='U32'))],
                  dict(kind='bool', bend='Bool', raw='U32'), operation)
    g.cases.append(f'''case {operation}: {{
        NativeCallScope scope;
        auto *future = get<QFutureInterfaceBase>(r, r->arguments[0].word, {g.ids['QFutureInterfaceBase']}, false, false);
        if (r->error) return true;
        if (future->isRunning()) return fail(r, EBUSY, "Native oracle only accepts a stopped future");
        r->result.word = future->waitForNextResult();
        return true;
}}''')
    bend, effects, dispatch = g.emit()
    abi = (ROOT / 'generator/templates/abi.h').read_text().replace('@ARGUMENT_CAPACITY@', str(g.argument_capacity))
    aliases = ''.join(f'using {name} = {native};\n' for name, native in api['typedefs'].items() if name in g.ids) + representations.aliases(g)
    gadget = work / 'gadget.h'; gadget.write_text(GADGET)
    moc = command([qt / 'libexec/moc', gadget, '-I' + str(qt / 'include')]).stdout
    (work / 'gadget.moc.cpp').write_text(moc)
    prefix, suffix = callbacks.qml_sources(g, qt, work)
    # As in production, header-defined helpers some modules leave unexported.
    source = (headers.read_text() + native_header_support(profile['qt_modules']) + aliases + prefix
              + '#include "gadget.h"\n' + (ROOT / 'generator/templates/runtime.cpp').read_text() + suffix)
    source = source.replace('// @ABI@', abi).replace('// @LIFETIME@', cpp_tables(evaluate_tables(work)))
    source = source.replace('// @NATIVE_OBJECTS@', native_objects.traits(g)).replace('// @DISPATCH@', dispatch)
    # The payload loader must run this static registration before Bend starts.
    source += '\n#include "gadget.moc.cpp"\nstatic const int fixture_type = qRegisterMetaType<BendQtTestGadget>("BendQtTestGadget");\n'
    native = work / 'wrappers.cpp'; native.write_text(source)
    embedded, imports, backend = compile_backend(native, qt, work, 'clang++-19', modules)
    extra = [m for m in modules if m not in ('QtCore', 'QtGui', 'QtWidgets')]
    libraries = [f'    void *libraries[{len(extra) + 1}] = {{lib}};']
    for i, module in enumerate(extra, 1):
        libraries += [f'    libraries[{i}] = dlopen("libQt6{module[2:]}.so.6", RTLD_NOW | RTLD_LOCAL);',
                      f'    if (!libraries[{i}]) return dlerror();']
    c = (ROOT / 'generator/templates/effects.c').read_text()
    for key, value in [('ABI', abi), ('ASSEMBLY', embedded), ('IMPORTS', imports), ('LIBRARIES', '\n'.join(libraries)), ('EFFECTS', effects)]:
        c = c.replace('// @' + key + '@', value)
    (work / 'qt.bend').write_text(bend); (work / 'qt.c').write_text(c)
    spec = importlib.util.spec_from_file_location('checks', ROOT / 'scripts/check-qt612.py')
    checks = importlib.util.module_from_spec(spec); spec.loader.exec_module(checks)
    programs = [(name, (ROOT / 'examples/qt612' / (name + '.bend')).read_text(), marker)
                for name, marker in [('metatypes', 'QT612_METATYPES_OK'), ('variants', 'QT612_VARIANTS_OK'),
                                     ('metatype-gadget', 'QT612_METATYPE_GADGET_OK'),
                                     ('remote-properties', 'QT612_REMOTE_PROPERTIES_OK'),
                                     ('generic-invocation', 'QT612_GENERIC_INVOCATION_OK'),
                                     ('primitive-storage', 'QT612_PRIMITIVE_STORAGE_OK'),
                                     ('future-waits', 'QT612_FUTURE_WAITS_OK'),
                                     ('testlib', 'QT612_TESTLIB_OK')]]
    receipt = checks.check_package(work, programs, os.environ.copy(), [qt], work / 'consumer', jobs=2)
    receipt['native_payload'] = backend['payload']
    (work / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    main()
