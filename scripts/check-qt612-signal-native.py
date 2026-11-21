#!/usr/bin/env python3
"""Maintainer checks of native Qt signals through the real Signal entry points.

Native signals are Signal declarations (see generator/signals.py): the shared
runtime finds them by name and argument types in the sender's meta-object.
This compiles that runtime with Qt development files for a focused profile
and drives the generic connect and emit operations with native signals:
QObject pointer payloads, delivery from another thread, disconnection, sender
destruction, QObject references, a QAuthenticator borrowed in place for
authenticationRequired, and emission of a signal the runtime observes.
The complete package is one ~100 MB translation unit whose monolithic compile
does not fit the bounded build. Consumer builds remain covered separately by
check-qt612.py and need no Qt SDK.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
from backend import command, versioned_include_paths
from generate import Generator
from lifetime import cpp_tables, evaluate_tables
from upstream import prepare
import callbacks
import native_objects
import representations
import qobject_interfaces
import qio_pipe
import native_linker
OUT = ROOT / "build/qt612/check/signal-native"
SIGNALS = ('QActionGroup.triggered', 'QNetworkAccessManager.authenticationRequired')

# A QObject passed by reference has no public Qt signal this profile can emit.
SENDER = r'''#include <QtCore/QObject>
class ReferenceSender : public QObject {
    Q_OBJECT
public:
    using QObject::QObject;
signals:
    void ready(QObject &object, QObject *nullable);
};
'''

DRIVER = r'''#include "@WRAPPERS@"
#include "@SENDER@"
#include <QtNetwork/QAuthenticator>
#include <QtNetwork/QNetworkAccessManager>
#include <memory>
#include <thread>
#include <vector>

static void require(bool condition, const char *message)
{
    if (!condition) {
        std::fprintf(stderr, "QT612_SIGNAL_NATIVE_FAIL %s\n", message);
        std::exit(1);
    }
}

// Declarations and values as Bend's Signal.schema and codecs encode them.
struct Wires {
    std::vector<std::unique_ptr<QByteArray>> texts;
    std::vector<std::unique_ptr<BqtValue[]>> arrays;
    BqtValue text(const char *value) {
        texts.push_back(std::make_unique<QByteArray>(value));
        BqtValue result{};
        result.tag = 1; result.text = texts.back()->data(); result.size = size_t(texts.back()->size());
        return result;
    }
    BqtValue sequence(const std::vector<BqtValue> &items) {
        arrays.push_back(std::make_unique<BqtValue[]>(items.size() + 1));
        for (size_t i = 0; i < items.size(); ++i) arrays.back()[i] = items[i];
        BqtValue result{};
        result.tag = 2; result.items = arrays.back().get(); result.count = items.size();
        return result;
    }
    BqtValue declaration(const char *name, std::vector<const char *> types) {
        std::vector<BqtValue> arguments;
        for (const char *type : types) arguments.push_back(text(type));
        return sequence({text(name), sequence(arguments)});
    }
    BqtValue word(uint32_t value) { BqtValue result{}; result.word = value; return result; }
};
static Wires wires;

// A host standing in for the Bend program: it records what Qt passes to the
// handler, as the program's handler would see it.
struct Seen {
    int calls = 0;
    bool main = false, live = false;
    uint32_t handler = 0, word = 0, borrowed = 0;
};
static Seen seen;
static QAction *expected_action;
static QObject *expected_reference;
static QAuthenticator *expected_authenticator;
static uint32_t authenticator_handle;
static bool authenticator_borrowed, reference_live;
static int releases;

static int invoke(uint32_t handler, const BqtValue *request, const char **)
{
    require(request->tag == 2 && request->count == 2, "handler request shape");
    const BqtValue &payload = request->items[1];
    if (handler == 79) {
        // authenticationRequired(QNetworkReply *, QAuthenticator *): the
        // handler fills in Qt's own authenticator, as a PySide slot does.
        require(payload.tag == 2 && payload.count == 2 && !payload.items[0].word, "authenticationRequired payload");
        authenticator_handle = payload.items[1].word;
        auto *e = authenticator_handle ? bendqt::entry(authenticator_handle) : nullptr;
        authenticator_borrowed = e && e->value == expected_authenticator && !e->owned;
        if (authenticator_borrowed) static_cast<QAuthenticator *>(e->value)->setUser(QStringLiteral("bend"));
        return BQT_HANDLER_DONE;
    }
    if (handler == 80) {
        require(payload.tag == 2 && payload.count == 2, "reference payload");
        auto *e = payload.items[0].word ? bendqt::entry(payload.items[0].word) : nullptr;
        reference_live = e && e->object == expected_reference && !payload.items[1].word;
        return BQT_HANDLER_DONE;
    }
    ++seen.calls;
    seen.handler = handler;
    seen.main = QThread::currentThread() == bendqt::main_thread;
    const BqtValue &value = payload.tag == 2 && payload.count == 1 ? payload.items[0] : payload;
    seen.word = value.word;
    seen.borrowed = value.borrowed_handle;
    auto *e = value.word ? bendqt::entry(value.word) : nullptr;
    seen.live = e && e->object == expected_action && !e->owned;
    return BQT_HANDLER_DONE;
}

static void release(uint32_t) { ++releases; }
static size_t sources(BqtSource *, size_t, int64_t *wait_ms) { *wait_ms = -1; return 0; }
static int runnable() { return 0; }
static void run() {}
static void flush() {}

static int connect_error(uint32_t sender, BqtValue declaration, uint32_t handler, uint32_t *connection)
{
    BqtRequest request{};
    request.operation = @CONNECT@;
    request.self = sender;
    request.arguments[0] = declaration;
    request.arguments[1].word = handler;
    bqt_abi_call(&request);
    if (request.error) std::fprintf(stderr, "connect: %s\n", request.message ? request.message : "");
    if (connection) *connection = request.result.word;
    return request.error;
}

static uint32_t connect(uint32_t sender, BqtValue declaration, uint32_t handler)
{
    uint32_t connection = 0;
    require(!connect_error(sender, declaration, handler, &connection) && connection, "connect a native signal declaration");
    return connection;
}

static int emit_request(uint32_t sender, BqtValue declaration, const std::vector<BqtValue> &values)
{
    BqtRequest request{};
    request.operation = @EMIT@;
    request.self = sender;
    request.arguments[0] = declaration;
    request.arguments[1] = wires.sequence(values);
    bqt_abi_call(&request);
    return request.error;
}

static int disconnect(uint32_t connection)
{
    BqtRequest request{};
    request.operation = @DISCONNECT@;
    request.self = connection;
    bqt_abi_call(&request);
    return request.error;
}

static uint32_t borrowed(QObject *object)
{
    BqtRequest registration{};
    uint32_t handle = bendqt::borrow(&registration, object, 0);
    require(!registration.error && handle, "register a QObject handle");
    return handle;
}

static uint32_t active_connections()
{
    uint32_t count = 0;
    for (const auto &c : bendqt::connections) if (c.active) ++count;
    return count;
}

int main(int argc, char **argv)
{
    BqtHost host{argc, argv, invoke, release, sources, runnable, run, flush};
    require(!bqt_abi_start(&host) && !bendqt::construct_application(2), "start Qt");
    auto *group = new QActionGroup(nullptr);
    auto *action = new QAction(nullptr);
    expected_action = action;
    const uint32_t sender = borrowed(group);
    const BqtValue triggered = wires.declaration("triggered", {"QAction*"});
    uint32_t connection = connect(sender, triggered, 77);

    // Qt runs the handler during the emission, on the main thread.
    group->triggered(nullptr);
    require(seen.calls == 1 && seen.main && seen.handler == 77 && !seen.word && !seen.borrowed,
            "null payload");
    group->triggered(action);
    require(seen.calls == 2 && seen.live && seen.word && seen.word == seen.borrowed,
            "live payload lacks its borrowed guard");

    // An emission on another thread reaches the handler through Qt's queued
    // delivery, on the main thread.
    std::thread emitter([&] { group->triggered(action); });
    emitter.join();
    require(seen.calls == 2, "another thread ran the handler");
    QCoreApplication::sendPostedEvents();
    require(seen.calls == 3 && seen.main && seen.live, "queued emission was not delivered on the main thread");

    // Signal.emit activates the native signal through the meta-object.
    require(!emit_request(sender, triggered, {wires.word(borrowed(action))}), "emit a native signal");
    require(seen.calls == 4 && seen.live, "an emitted native signal did not reach its handler");
    // The runtime observes QObject.destroyed; Bend cannot emit it.
    require(emit_request(sender, wires.declaration("destroyed", {"QObject*"}), {wires.word(0)}) == EPERM,
            "an observed signal was emitted");
    uint32_t refused = 0;
    require(connect_error(sender, wires.declaration("destroyed", {"QObject*"}), 81, &refused) == ENOTSUP && !refused,
            "destroyed connected without its ObjectIdentity declaration");

    // Disconnecting gives the handler back once; a second disconnect is stale.
    require(!disconnect(connection), "disconnect");
    require(releases == 1, "disconnect did not release the handler once");
    group->triggered(action);
    require(seen.calls == 4, "a disconnected handler ran");
    require(disconnect(connection) == ESTALE, "a closed connection was not stale");

    // A QObject reference parameter arrives as the object's handle.
    auto *references = new ReferenceSender;
    QObject referenced;
    expected_reference = &referenced;
    const uint32_t ready = connect(borrowed(references), wires.declaration("ready", {"QObject&", "QObject*"}), 80);
    references->ready(referenced, nullptr);
    require(reference_live, "a QObject reference lost its identity");
    require(!disconnect(ready), "disconnect the reference signal");
    delete references;

    // authenticationRequired passes Qt's authenticator, borrowed for the call.
    auto *manager = new QNetworkAccessManager;
    QAuthenticator authenticator;
    expected_authenticator = &authenticator;
    const uint32_t authentication = connect(borrowed(manager),
        wires.declaration("authenticationRequired", {"QNetworkReply*", "QAuthenticator*"}), 79);
    manager->authenticationRequired(nullptr, &authenticator);
    require(authenticator_borrowed && authenticator.user() == QStringLiteral("bend"),
            "the handler did not fill in Qt's own authenticator");
    require(!bendqt::entry(authenticator_handle), "a borrowed authenticator outlived its call");
    require(!disconnect(authentication), "disconnect authenticationRequired");
    delete manager;

    // Destroying the sender ends its connections and releases their handlers.
    uint32_t ended = connect(sender, triggered, 78);
    delete group;
    require(releases == 4, "sender destruction did not release the handler");
    require(disconnect(ended) == ESTALE, "a connection outlived its sender");
    require(active_connections() == 0, "native fixture leaked connections");
    delete action;
    require(bqt_abi_stop() == 0, "stop Qt");
    std::puts("QT612_SIGNAL_NATIVE_OK null=1 live=1 other_thread=1 emit=1 observed_emit=0 disconnect=1 "
              "reference=1 borrowed_in_place=1 sender_destroyed=1 connections=0");
}
'''


def run(command, env, timeout):
    result = subprocess.run([str(x) for x in command], cwd=ROOT, env=env,
                            text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{command}: {result.returncode}\n{result.stdout[-6000:]}\n{result.stderr[-6000:]}")
    return result


def check_connector_types():
    """Check the public handler and sender contract, including rejected shapes."""
    bend = shutil.which('bend') or str(Path.home() / '.bend/bin/bend')
    package = os.path.relpath(ROOT / 'packages/qt612/qt.bend', OUT).replace(os.sep, '/')
    cases = {
        'bool': ('state: Unit, checked: Bool', 'Unit', 'QPushButton', 'QPushButton', 'clicked', True),
        'no_arguments': ('state: Unit', 'Unit', 'QTimer', 'QTimer', 'timeout', True),
        'borrowed_in_place': ('state: Unit, reply: Qt.QNetworkReply, authenticator: Qt.QAuthenticator', 'Unit',
                              'QNetworkAccessManager', 'QNetworkAccessManager', 'authenticationRequired', True),
        'destroyed_identity': ('state: Unit, gone: Qt.ObjectIdentity', 'Unit', 'QTimer', 'QTimer', 'destroyed', True),
        'wrong_payload': ('state: Unit, checked: String', 'Unit', 'QPushButton', 'QPushButton', 'clicked', False),
        'wrong_arity': ('state: Unit', 'Unit', 'QPushButton', 'QPushButton', 'clicked', False),
        'wrong_state': ('state: String, checked: Bool', 'Unit', 'QPushButton', 'QPushButton', 'clicked', False),
        'wrong_result': ('state: Unit, checked: Bool', 'Bool', 'QPushButton', 'QPushButton', 'clicked', False),
        'wrong_sender': ('state: Unit, checked: Bool', 'Unit', 'QTimer', 'QPushButton', 'clicked', False),
    }
    results = {}
    for name, (parameters, result, sender, owner, signal, valid) in cases.items():
        source = OUT / f'types-{name}.bend'
        value = 'Unit{}' if result == 'Unit' else 'False{}'
        source.write_text(f'''import Base
import {package} as Qt

def handler({parameters}) -> Qt.Action({result}):
  Qt.Action.pure({result}, {value})

def connect(object: Qt.{sender}) -> Qt.Action(Qt.Connection):
  Qt.Signal.connect(~Qt.{owner}.{signal}(), ~Unit, ~handler, object, Unit{{}})
''')
        checked = subprocess.run([bend, str(source), '--check-only'], cwd=ROOT,
                                 text=True, capture_output=True, timeout=120)
        diagnostic = (checked.stdout + checked.stderr).strip()
        (OUT / f'types-{name}.log').write_text(diagnostic + '\n')
        if valid:
            expected = bool(re.fullmatch(
                r'SOME PROOFS FAIL\nError: \d+ defs rely on unsafe or foreign code:\n'
                r'defs that depend on foreign effects: [A-Za-z0-9_./, \n]+', diagnostic))
        else:
            expected = all(marker in diagnostic for marker in
                           ('- expected :', '- observed :', 'Location: connect'))
        if checked.returncode != 1 or not expected:
            raise RuntimeError(f'Unexpected connector type-check result for {name}: {diagnostic[:2000]}')
        results[name] = 'typed' if valid else 'rejected'
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qt-prefix", type=Path,
                        default=Path.home() / ".cache/bend-qt-generator/Qt/6.12.0/gcc_64")
    parser.add_argument("--cxx", default="clang++-19")
    parser.add_argument("--extractor", type=Path,
                        default=Path.home() / ".cache/bend-qt-generator/build/bend-qt-extract")
    args = parser.parse_args()
    qt = args.qt_prefix.resolve()
    cache = Path.home() / ".cache/bend-qt-generator"
    coverage_path = ROOT / "packages/qt612/coverage.json"
    coverage = json.loads(coverage_path.read_text())
    declared = {m["bend_name"] for m in coverage["generated"] if "signal" in m}
    if not set(SIGNALS) <= declared:
        raise RuntimeError("Generate the native signal declarations before running this check")
    OUT.mkdir(parents=True, exist_ok=True)
    connector_types = check_connector_types()
    profile = json.loads((ROOT / "generator/qt612/profile.json").read_text())
    profile["qt_modules"] = ["QtCore", "QtGui", "QtWidgets", "QtNetwork"]
    headers, system, modules, extraction_env, _ = prepare(cache / "pyside-setup", qt, profile["qt_modules"], OUT)
    profile["qt_modules"] = modules
    logs = OUT / "extractor"; logs.mkdir(exist_ok=True)
    extracted = command([args.extractor, headers, system, OUT / "api.json", logs, qt / "include",
                         qt / "mkspecs/linux-g++", *[qt / "include" / m for m in modules],
                         *versioned_include_paths(qt, modules)], env=extraction_env)
    (OUT / "extraction.log").write_text(extracted.stdout + extracted.stderr)
    api = json.loads((OUT / "api.json").read_text())
    qobject_interfaces.restore(api, OUT)
    qio_pipe.restore(api, OUT)
    native_objects.refine_traits(api, qt, modules, OUT, args.cxx)
    g = Generator(api, profile); g.collect()
    # The declarations' argument types are registered with the runtime.
    g.methods = [m for m in g.methods if m["bend_name"] in SIGNALS]
    if sorted(m["bend_name"] for m in g.methods) != sorted(SIGNALS):
        raise RuntimeError("Focused profile lost a native signal declaration")
    callbacks.prepare(g)
    g.callback_classes = []; g.callback_methods = {}; g.callback_functions = []; g.callback_qml = False
    bend, effects, dispatch = g.emit()
    operations = g.custom_signal_operations
    abi = (ROOT / "generator/templates/abi.h").read_text().replace("@ARGUMENT_CAPACITY@", str(g.argument_capacity))
    aliases = "".join(f"using {name} = {native};\n" for name, native in api["typedefs"].items() if name in g.ids)
    aliases += representations.aliases(g)
    prefix, suffix = callbacks.qml_sources(g, qt, OUT)
    native = headers.read_text() + aliases + prefix + (ROOT / "generator/templates/runtime.cpp").read_text() + suffix
    native = native.replace("// @ABI@", abi).replace("// @LIFETIME@", cpp_tables(evaluate_tables(OUT)))
    native = native.replace("// @NATIVE_OBJECTS@", native_objects.traits(g)).replace("// @DISPATCH@", dispatch)
    wrappers = OUT / "wrappers.cpp"
    wrappers.write_text(native)
    sender = OUT / "reference-sender.h"
    sender.write_text(SENDER)
    includes = ["-I" + str(qt / "include"), "-I" + str(qt / "mkspecs/linux-g++")]
    includes += ["-I" + str(qt / "include" / module) for module in modules]
    includes += ["-I" + str(path) for path in versioned_include_paths(qt, modules)]
    moc = OUT / "moc-reference-sender.cpp"
    run([qt / "libexec/moc", *includes, sender, "-o", moc], dict(os.environ), 120)
    source = OUT / "signal-native.cpp"
    source.write_text(DRIVER.replace("@WRAPPERS@", wrappers.as_posix()).replace("@SENDER@", sender.as_posix())
                      .replace("@CONNECT@", str(operations["connect"])).replace("@EMIT@", str(operations["emit"]))
                      .replace("@DISCONNECT@", "2"))
    executable = OUT / "signal-native"
    command_line = [args.cxx, "-std=c++17", "-O0", "-g0", "-fPIC", "-ffunction-sections",
                    "-fdata-sections", "-Wl,--gc-sections", "-pthread", source, moc, "-o", executable,
                    *includes, "-L" + str(qt / "lib"), "-Wl,-rpath," + str(qt / "lib"),
                    "-Wl,-rpath-link," + str(qt / "lib")]
    command_line.extend("-lQt6" + module[2:] for module in modules)
    env = dict(os.environ, LD_LIBRARY_PATH=str(qt / "lib"), QT_QPA_PLATFORM="offscreen",
               QT_PLUGIN_PATH=str(qt / "plugins"),
               QT_QPA_PLATFORM_PLUGIN_PATH=str(qt / "plugins/platforms"))
    compiler = run([args.cxx, '--version'], env, 10).stdout
    linker = native_linker.select(args.cxx) if 'clang' in compiler.lower() else None
    if linker:
        command_line[1:1] = linker['flags']
    compiled = run(command_line, env, 1100)
    (OUT / "build.log").write_text(compiled.stdout + compiled.stderr)
    tested = run([executable], env, 30)
    (OUT / "run.log").write_text(tested.stdout + tested.stderr)
    if "QT612_SIGNAL_NATIVE_OK" not in tested.stdout:
        raise RuntimeError(tested.stdout + tested.stderr)
    receipt = {
        "maintainer_test": True,
        "connector_types": connector_types,
        "declared_signals": list(SIGNALS),
        "profile_modules": modules,
        "operations": operations,
        "qt_prefix": str(qt),
        "compiler": compiler.splitlines()[0],
        "linker": linker,
        "wrappers_sha256": hashlib.sha256(wrappers.read_bytes()).hexdigest(),
        "coverage_sha256": hashlib.sha256(coverage_path.read_bytes()).hexdigest(),
        "driver_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "marker": tested.stdout.strip(),
        "consumer_build_dependency": False,
    }
    (OUT / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print("PASS native signal declarations: payloads, other-thread delivery, emission, observed-signal refusal, "
          "disconnect, QObject references, in-place borrowed values and sender destruction")


if __name__ == "__main__":
    main()
