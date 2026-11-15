#!/usr/bin/env python3
"""Maintainer checks of an emitted signal connect through the real entry points.

This compiles the generator's actual signal wrapper and shared runtime with Qt
development files. Like the other native fixtures it emits a focused profile:
the complete package is one ~100 MB translation unit whose monolithic compile
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
OUT = ROOT / "build/qt612/check/signal-native"

DRIVER = r'''#include "@WRAPPERS@"
#include <thread>

static void require(bool condition, const char *message)
{
    if (!condition) {
        std::fprintf(stderr, "QT612_SIGNAL_NATIVE_FAIL %s\n", message);
        std::exit(1);
    }
}

// A host standing in for the Bend program: it records what Qt passes to the
// handler, as the program's handler would see it.
struct Seen {
    int calls = 0;
    bool main = false, live = false;
    uint32_t handler = 0, word = 0, borrowed = 0;
};
static Seen seen;
static QAction *expected_action;
static int releases;

static int invoke(uint32_t handler, const BqtValue *request, const char **)
{
    ++seen.calls;
    seen.handler = handler;
    seen.main = QThread::currentThread() == bendqt::main_thread;
    require(request->tag == 2 && request->count == 2, "handler request shape");
    const BqtValue &payload = request->items[1];
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

static uint32_t connect(uint32_t sender, uint32_t handler)
{
    BqtRequest request{};
    request.operation = @OPERATION@;
    request.self = sender;
    request.arguments[0].word = handler;
    bqt_abi_call(&request);
    require(!request.error && request.result.word, "actual generated QActionGroup.connect_triggered connect");
    return request.result.word;
}

static int disconnect(uint32_t connection)
{
    BqtRequest request{};
    request.operation = @DISCONNECT@;
    request.self = connection;
    bqt_abi_call(&request);
    return request.error;
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
    require(!bqt_abi_start(&host), "start Qt");
    auto *group = new QActionGroup(nullptr);
    auto *action = new QAction(nullptr);
    expected_action = action;
    BqtRequest registration{};
    uint32_t sender = bendqt::borrow(&registration, group, 0);
    require(!registration.error && sender, "register signal sender");
    uint32_t connection = connect(sender, 77);

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

    // Disconnecting gives the handler back once; a second disconnect is stale.
    require(!disconnect(connection), "disconnect");
    require(releases == 1, "disconnect did not release the handler once");
    group->triggered(action);
    require(seen.calls == 3, "a disconnected handler ran");
    require(disconnect(connection) == ESTALE, "a closed connection was not stale");

    // Destroying the sender ends its connections and releases their handlers.
    uint32_t ended = connect(sender, 78);
    delete group;
    require(releases == 2, "sender destruction did not release the handler");
    require(disconnect(ended) == ESTALE, "a connection outlived its sender");
    require(active_connections() == 0, "native fixture leaked connections");
    delete action;
    require(bqt_abi_stop() == 0, "stop Qt");
    std::puts("QT612_SIGNAL_NATIVE_OK null=1 live=1 other_thread=1 disconnect=1 sender_destroyed=1 connections=0");
}
'''


def run(command, env, timeout):
    result = subprocess.run([str(x) for x in command], cwd=ROOT, env=env,
                            text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{command}: {result.returncode}\n{result.stdout[-6000:]}\n{result.stderr[-6000:]}")
    return result


def check_connector_types():
    """Check the public handler contract, including rejected handler shapes."""
    bend = shutil.which('bend') or str(Path.home() / '.bend/bin/bend')
    package = os.path.relpath(ROOT / 'packages/qt612/qt.bend', OUT).replace(os.sep, '/')
    cases = {
        'bool': ('state: Unit, checked: Bool', 'Unit', 'Unit{}',
                 'QPushButton', 'connect_clicked', True),
        'no_arguments': ('state: Unit', 'Unit', 'Unit{}',
                         'QTimer', 'connect_timeout', True),
        'mutable_reply': ('state: Unit, reply: Qt.QNetworkReply, authenticator: Qt.QAuthenticator',
                          'Qt.SignalReply_QAuthenticator', 'Qt.SignalReply_QAuthenticator{authenticator}',
                          'QNetworkAccessManager', 'connect_authenticationRequired', True),
        'wrong_payload': ('state: Unit, checked: String', 'Unit', 'Unit{}',
                          'QPushButton', 'connect_clicked', False),
        'wrong_arity': ('state: Unit', 'Unit', 'Unit{}',
                        'QPushButton', 'connect_clicked', False),
        'wrong_state': ('state: String, checked: Bool', 'Unit', 'Unit{}',
                        'QPushButton', 'connect_clicked', False),
        'wrong_result': ('state: Unit, checked: Bool', 'Bool', 'False{}',
                         'QPushButton', 'connect_clicked', False),
        'missing_mutable_reply': ('state: Unit, reply: Qt.QNetworkReply, authenticator: Qt.QAuthenticator',
                                  'Unit', 'Unit{}', 'QNetworkAccessManager', 'connect_authenticationRequired', False),
    }
    results = {}
    for name, (parameters, result, value, owner, connector, valid) in cases.items():
        source = OUT / f'types-{name}.bend'
        source.write_text(f'''import Base
import {package} as Qt

def handler({parameters}) -> Qt.Action({result}):
  Qt.Action.pure({result}, {value})

def connect(object: Qt.{owner}) -> Qt.Action(Qt.Connection):
  Qt.{owner}.{connector}(~Unit, ~handler, object, Unit{{}})
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
    if [m["bend_name"] for m in coverage["generated"] if m["bend_name"] == "QActionGroup.connect_triggered"] != ["QActionGroup.connect_triggered"]:
        raise RuntimeError("Generate QObject-pointer signal support before running this check")
    OUT.mkdir(parents=True, exist_ok=True)
    connector_types = check_connector_types()
    profile = json.loads((ROOT / "generator/qt612/profile.json").read_text())
    profile["qt_modules"] = ["QtCore", "QtGui", "QtWidgets"]
    headers, system, modules, extraction_env, _ = prepare(cache / "pyside-setup", qt, profile["qt_modules"], OUT)
    profile["qt_modules"] = modules
    logs = OUT / "extractor"; logs.mkdir(exist_ok=True)
    extracted = command([args.extractor, headers, system, OUT / "api.json", logs, qt / "include",
                         qt / "mkspecs/linux-g++", *[qt / "include" / m for m in modules],
                         *versioned_include_paths(qt, modules)], env=extraction_env)
    (OUT / "extraction.log").write_text(extracted.stdout + extracted.stderr)
    api = json.loads((OUT / "api.json").read_text())
    native_objects.refine_traits(api, qt, modules, OUT, args.cxx)
    g = Generator(api, profile); g.collect()
    g.methods = [m for m in g.methods if m["bend_name"] == "QActionGroup.connect_triggered"]
    if len(g.methods) != 1:
        raise RuntimeError("Focused profile lost QActionGroup.connect_triggered")
    callbacks.prepare(g)
    g.callback_classes = []; g.callback_methods = {}; g.callback_qml = False
    bend, effects, dispatch = g.emit()
    operation = g.methods[0]["operation"]
    abi = (ROOT / "generator/templates/abi.h").read_text().replace("@ARGUMENT_CAPACITY@", str(g.argument_capacity))
    aliases = "".join(f"using {name} = {native};\n" for name, native in api["typedefs"].items() if name in g.ids)
    aliases += representations.aliases(g)
    native = headers.read_text() + aliases + (ROOT / "generator/templates/runtime.cpp").read_text()
    native = native.replace("// @ABI@", abi).replace("// @LIFETIME@", cpp_tables(evaluate_tables(OUT)))
    native = native.replace("// @NATIVE_OBJECTS@", native_objects.traits(g)).replace("// @DISPATCH@", dispatch)
    wrappers = OUT / "wrappers.cpp"
    wrappers.write_text(native)
    source = OUT / "signal-native.cpp"
    source.write_text(DRIVER.replace("@WRAPPERS@", wrappers.as_posix())
                     .replace("@OPERATION@", str(operation)).replace("@DISCONNECT@", "2"))
    executable = OUT / "signal-native"
    command_line = [args.cxx, "-std=c++17", "-O0", "-g0", "-fPIC", "-ffunction-sections",
                    "-fdata-sections", "-Wl,--gc-sections", "-pthread", source, "-o", executable,
                    "-I" + str(qt / "include"), "-I" + str(qt / "mkspecs/linux-g++"),
                    "-L" + str(qt / "lib"), "-Wl,-rpath," + str(qt / "lib"),
                    "-Wl,-rpath-link," + str(qt / "lib")]
    for module in modules:
        command_line.extend(["-I" + str(qt / "include" / module), "-lQt6" + module[2:]])
    command_line.extend("-I" + str(path) for path in versioned_include_paths(qt, modules))
    env = dict(os.environ, LD_LIBRARY_PATH=str(qt / "lib"), QT_QPA_PLATFORM="offscreen",
               QT_PLUGIN_PATH=str(qt / "plugins"),
               QT_QPA_PLATFORM_PLUGIN_PATH=str(qt / "plugins/platforms"))
    compiled = run(command_line, env, 1100)
    (OUT / "build.log").write_text(compiled.stdout + compiled.stderr)
    tested = run([executable], env, 30)
    (OUT / "run.log").write_text(tested.stdout + tested.stderr)
    if "QT612_SIGNAL_NATIVE_OK" not in tested.stdout:
        raise RuntimeError(tested.stdout + tested.stderr)
    receipt = {
        "maintainer_test": True,
        "connector_types": connector_types,
        "generated_signal": g.methods[0]["bend_name"],
        "profile_modules": modules,
        "operation": operation,
        "qt_prefix": str(qt),
        "compiler": run([args.cxx, "--version"], env, 10).stdout.splitlines()[0],
        "wrappers_sha256": hashlib.sha256(wrappers.read_bytes()).hexdigest(),
        "coverage_sha256": hashlib.sha256(coverage_path.read_bytes()).hexdigest(),
        "driver_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "marker": tested.stdout.strip(),
        "consumer_build_dependency": False,
    }
    (OUT / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print("PASS generated QObject-signal connect: null/live payloads, other-thread delivery, disconnect and sender destruction")


if __name__ == "__main__":
    main()
