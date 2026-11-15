#!/usr/bin/env python3
"""Real Qt native-event dispatch to a Bend handler, scoped messages and result writeback."""
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
from lifetime import cpp_tables, evaluate_tables
from upstream import prepare
import callbacks
import native_objects
import representations

PROGRAM = '''import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def reply(out: Maybe<&2, Qt.Int64>) -> Qt.@REPLY@:
  match out:
    case None{}: Qt.@REPLY@{True{}, None{}}
    case Some{value}: Qt.@REPLY@{True{}, Some{Qt.Int64{42, 0}}}

def forwarded(value: Qt.Outputs_Bool_Int64) -> Qt.Action(Unit):
  match value:
    case Qt.Outputs_Bool_Int64{accepted, number}:
      require(accepted && U32.is_eq(Qt.Int64.lo(number), 42), "Native event forwarding lost result output")

def forward(+event: Qt.NativeEvent, event_type: Qt.QByteArray, oracle: Qt.QAbstractNativeEventFilter) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    result: Qt.Outputs_Bool_Int64 <- Qt.QAbstractNativeEventFilter.nativeEventFilter(oracle, event_type, event)
    forwarded(result)

def header(+value: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    length: Qt.Int64 <- Qt.QByteArray.size(value)
    require(U32.is_eq(Qt.Int64.lo(length), 32), "XCB snapshot extent changed")
    first: Qt.Int32 <- Qt.QByteArray.at(value, Qt.Int64{0, 0})
    require(U32.is_eq(Qt.Int32.word(first), 77), "XCB snapshot lost message data")

# Qt runs the handler inside Fixture.dispatch. It records the event's handle
# word in the timer's interval, so the program can show that the handle
# expires with the call.
def filtered(+record: Qt.QTimer, +event_type: Qt.QByteArray, +event: Qt.NativeEvent, out: Maybe<&2, Qt.Int64>) -> Qt.Action(Qt.@REPLY@):
  do Qt.Action<Qt.@REPLY@>:
    null: Bool <- Qt.NativeEvent.isNull(event)
    require(Bool.not(null), "Native event pointer disappeared during the handler")
    Qt.QByteArray.with(Unit, Qt.NativeEvent.xcbHeader(event), value => header(value))
    Qt.QAbstractNativeEventFilter.with(Unit, Qt.Fixture.oracle(), oracle => forward(event, event_type, oracle))
    Qt.QTimer.setInterval__Int32(record, Qt.Int32{Qt.NativeEvent.word(event)})
    return reply(out)

def handler(record: Qt.QTimer, event_type: Qt.QByteArray, event: Qt.NativeEvent, out: Maybe<&2, Qt.Int64>) -> Qt.Action(Qt.@REPLY@):
  filtered(record, event_type, event, out)

def expired(result: Result<&1, &1, U32 & String, Bool>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 116), "Wrong expired event error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Native event escaped its handler call")

def stale(+record: Qt.QTimer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +token: Qt.Int32 <- Qt.QTimer.interval(record)
    require(U32.is_ne(Qt.Int32.word(token), 0), "The handler did not record its event")
    result: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.NativeEvent.isNull(Qt.NativeEvent{Qt.Int32.word(token)}))
    expired(result)
    Qt.QTimer.setInterval__Int32(record, Qt.Int32{0})

def dispatch(+record: Qt.QTimer, +filter: Qt.QAbstractNativeEventFilter) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.@VIRTUAL@.handle(~Qt.QTimer, ~handler, filter, record)
    accepted: Bool <- Qt.Fixture.dispatch(filter, True{})
    require(accepted, "Qt dispatcher lost the handler result")
    stale(record)
    accepted_null: Bool <- Qt.Fixture.dispatch(filter, False{})
    require(accepted_null, "Null native output pointer did not round trip")
    stale(record)

def filtering(+record: Qt.QTimer) -> Qt.Action(Unit):
  Qt.QAbstractNativeEventFilter.with(Unit, Qt.QAbstractNativeEventFilter.newOverride(), filter => dispatch(record, filter))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QTimer.with(Unit, Qt.QTimer.new(), record => filtering(record))
    objects: U32 <- Qt.Runtime.liveObjects()
    pins: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(pins, 0), "Native event handler leaked handles")
    Qt.Action.lift(Unit, IO.print("QT612_NATIVE_EVENTS_OK real_dispatch=1 forward=1 result=1 null_output=1 xcb_snapshot=1 expired=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    cache = Path.home() / '.cache/bend-qt-generator'
    parser.add_argument('--qt-root', type=Path, default=cache / 'Qt/6.12.0/gcc_64')
    parser.add_argument('--extractor', type=Path, default=cache / 'build/bend-qt-extract')
    args = parser.parse_args()
    qt = args.qt_root
    work = ROOT / 'build/qt612/check/native-events'; work.mkdir(parents=True, exist_ok=True)
    profile = json.loads((ROOT / 'generator/qt612-core/profile.json').read_text())
    headers, system, modules, env, _ = prepare(cache / 'pyside-setup', qt, profile['qt_modules'], work)
    profile['qt_modules'] = modules
    logs = work / 'extractor'; logs.mkdir(exist_ok=True)
    extracted = command([args.extractor, headers, system, work / 'api.json', logs,
                         qt / 'include', qt / 'mkspecs/linux-g++', *[qt / 'include' / m for m in modules]], env=env)
    (work / 'extraction.log').write_text(extracted.stdout + extracted.stderr)
    api = json.loads((work / 'api.json').read_text())
    native_objects.refine_traits(api, qt, modules, work, 'clang++-19')
    g = Generator(api, profile); g.collect()
    g.methods = [m for m in g.methods if m['class'] in ('QAbstractNativeEventFilter', 'QAbstractEventDispatcher', 'QByteArray', 'QTimer', 'QObject')]
    callbacks.prepare(g)
    g.callback_classes = [c for c in g.callback_classes if c['name'] == 'QAbstractNativeEventFilter']
    g.callback_methods = {m['method_id']: m for c in g.callback_classes for m in c['virtuals']}
    g.callback_qml = False
    virtual = next(m for m in g.callback_methods.values() if m['function']['name'] == 'nativeEventFilter')
    program = PROGRAM.replace('@VIRTUAL@', virtual['public']).replace('@ARGS@', virtual['payload']['bend']).replace('@REPLY@', virtual['result']['bend'])
    (work / 'main.bend').write_text(program)
    event_filter = dict(kind='object', name='QAbstractNativeEventFilter', cpp='QAbstractNativeEventFilter *', bend='QAbstractNativeEventFilter', raw='U32', pointer=True, owned=True)
    operation = g.next_id; g.next_id += 1
    g.emit_effect('Fixture.oracle', [], event_filter, operation)
    g.cases.append(f'''case {operation}: {{
        struct Echo final : QAbstractNativeEventFilter {{
            bool nativeEventFilter(const QByteArray &type, void *message, qintptr *result) override {{
                if (result) *result = 42;
                return type == "xcb_generic_event_t" && message && *static_cast<unsigned char *>(message) == 77;
            }}
        }};
        r->result.word = own<QAbstractNativeEventFilter>(r, new Echo, {g.ids['QAbstractNativeEventFilter']});
        r->result.owned_handle = r->result.word; return true;
}}''')
    operation = g.next_id; g.next_id += 1
    g.emit_effect('Fixture.dispatch', [('filter', event_filter), ('output', dict(kind='bool', bend='Bool', raw='U32'))], dict(kind='bool', bend='Bool', raw='U32'), operation)
    g.cases.append(f'''case {operation}: {{
        NativeCallScope scope;
        auto *filter = get<QAbstractNativeEventFilter>(r, r->arguments[0].word, {g.ids['QAbstractNativeEventFilter']});
        if (r->error) return true;
        auto *dispatcher = QAbstractEventDispatcher::instance();
        dispatcher->installNativeEventFilter(filter);
        struct Remove {{ QAbstractEventDispatcher *dispatcher; QAbstractNativeEventFilter *filter;
            ~Remove() {{ dispatcher->removeNativeEventFilter(filter); }} }} remove{{dispatcher, filter}};
        alignas(8) unsigned char message[32]{{77}};
        qintptr result = 0;
        bool accepted = dispatcher->filterNativeEvent("xcb_generic_event_t", message, r->arguments[1].word ? &result : nullptr);
        r->result.word = accepted && (!r->arguments[1].word || result == 42);
        return true;
}}''')
    bend, effects, dispatch = g.emit()
    abi = (ROOT / 'generator/templates/abi.h').read_text().replace('@ARGUMENT_CAPACITY@', str(g.argument_capacity))
    aliases = ''.join(f'using {name} = {native};\n' for name, native in api['typedefs'].items() if name in g.ids) + representations.aliases(g)
    source = headers.read_text() + aliases + (ROOT / 'generator/templates/runtime.cpp').read_text()
    source = source.replace('// @ABI@', abi).replace('// @LIFETIME@', cpp_tables(evaluate_tables(work)))
    source = source.replace('// @NATIVE_OBJECTS@', native_objects.traits(g)).replace('// @DISPATCH@', dispatch)
    native = work / 'wrappers.cpp'; native.write_text(source)
    payload, loader, metadata = compile_backend(native, qt, work, 'clang++-19', modules)
    extra = [m for m in modules if m not in ('QtCore', 'QtGui', 'QtWidgets')]
    libraries = [f'    void *libraries[{len(extra) + 1}] = {{lib}};']
    for i, module in enumerate(extra, 1):
        libraries += [f'    libraries[{i}] = dlopen("libQt6{module[2:]}.so.6", RTLD_NOW | RTLD_LOCAL);', f'    if (!libraries[{i}]) return dlerror();']
    c = (ROOT / 'generator/templates/effects.c').read_text()
    for key, value in [('ABI', abi), ('ASSEMBLY', payload), ('IMPORTS', loader), ('LIBRARIES', '\n'.join(libraries)), ('EFFECTS', effects)]:
        c = c.replace('// @' + key + '@', value)
    (work / 'qt.bend').write_text(bend); (work / 'qt.c').write_text(c)
    spec = importlib.util.spec_from_file_location('checks', ROOT / 'scripts/check-qt612.py')
    checks = importlib.util.module_from_spec(spec); spec.loader.exec_module(checks)
    receipt = checks.check_package(work, [('native-events', program, 'QT612_NATIVE_EVENTS_OK')], os.environ.copy(), [qt], work / 'consumer', jobs=1)
    receipt['native_payload'] = metadata['payload']
    (work / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    main()
