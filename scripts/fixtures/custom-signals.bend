import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def progressChanged() -> Qt.Signal:
  Qt.Signal.define("progressChanged", [Qt.int32(), Qt.string()])

def finished() -> Qt.Signal:
  Qt.Signal.define("finished", [])

def valuesChanged() -> Qt.Signal:
  Qt.Signal.define("valuesChanged", [Qt.bool(), Qt.u32(), Qt.f64(), Qt.string()])

def inherited() -> Qt.Signal:
  Qt.Signal.define("objectNameChanged", [Qt.string()])

def expect_error(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Unexpected custom signal error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected a custom signal error")

type State is Data:
  State{object: Qt.QObject, probe: Qt.QObject}

def completed(probe: Qt.QObject) -> Qt.Action(Unit):
  Qt.QObject.setObjectName(probe, "finished")

def progress(state: State, value: Qt.Int32, title: String) -> Qt.Action(Unit):
  match state:
    case State{object, +probe}:
      +label = title
      do Qt.Action<Unit>:
        require(U32.is_eq(Qt.Int32.word(value), 42) && String.eq(label, "Loading"), "Wrong signal arguments")
        Qt.QObject.setObjectName(probe, label)
        Qt.Signal.emit(~finished(), object)
        name: String <- Qt.QObject.objectName(probe)
        require(String.eq(name, "finished"), "Nested signal handler did not run synchronously")

def metadata(meta: Qt.QMetaObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    index: Qt.Int32 <- Qt.QMetaObject.indexOfSignal(meta, "progressChanged(int,QString)")
    require(U32.is_ne(Qt.Int32.word(index), 4294967295), "The declaration is not a real Qt signal")

def emit_once(+object: Qt.QObject, +probe: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QMetaObject.with(Unit, Qt.QObject.metaObject(object), metadata)
    Qt.Signal.emit(~progressChanged(), object, Qt.Int32{42}, "Loading")
    name: String <- Qt.QObject.objectName(probe)
    require(String.eq(name, "finished"), "Signal emission returned before its Bend handlers ran")

def connected(+object: Qt.QObject, +probe: Qt.QObject) -> Qt.Action(Unit):
  Qt.Connection.with(Unit,
    Qt.Signal.connect(~finished(), ~Qt.QObject, ~completed, object, probe), finished_connection =>
    Qt.Connection.with(Unit,
      Qt.Signal.connect(~progressChanged(), ~State, ~progress, object, State{object, probe}),
      progress_connection => emit_once(object, probe)))

def refused(code: U32, value: Qt.Int32, title: String) -> Qt.Action(Unit):
  Qt.Action.fail(Unit, code, "Intentional custom signal failure")

def rejected_emit(object: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    result: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit,
      Qt.Signal.emit(~progressChanged(), object, Qt.Int32{42}, "Loading"))
    expect_error(Unit, result, 44)

def failed_handler(+object: Qt.QObject) -> Qt.Action(Unit):
  Qt.Connection.with(Unit,
    Qt.Signal.connect(~progressChanged(), ~U32, ~refused, object, 44),
    connection => rejected_emit(object))

def primitive_values(state: Unit, flag: Bool, number: U32, value: Qt.F64, text: String) -> Qt.Action(Unit):
  +bits = value
  do Qt.Action<Unit>:
    require(flag && U32.is_eq(number, 4294967295) && U32.is_eq(Qt.F64.lo(bits), 0)
      && U32.is_eq(Qt.F64.hi(bits), 1072693248), "Primitive custom signal values changed")
    require(String.eq(text, "音符🎵"), "Signal string was not copied as UTF-8")

def primitive_demo(+object: Qt.QObject) -> Qt.Action(Unit):
  Qt.Connection.with(Unit,
    Qt.Signal.connect(~valuesChanged(), ~Unit, ~primitive_values, object, Unit{}),
    connection => Qt.Signal.emit(~valuesChanged(), object, True{}, 4294967295, Qt.F64{0, 1072693248}, "音符🎵"))

def record(probe: Qt.QObject, value: Qt.Int32, text: String) -> Qt.Action(Unit):
  Qt.QObject.setObjectName(probe, "unexpected")

def disconnected(+object: Qt.QObject, +probe: Qt.QObject, connection: Qt.Connection) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Connection.disconnect(connection)
    Qt.Signal.emit(~progressChanged(), object, Qt.Int32{42}, "Loading")
    name: String <- Qt.QObject.objectName(probe)
    require(String.eq(name, "unchanged"), "Disconnected custom signal handler ran")

def disconnect_demo(+object: Qt.QObject, +probe: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QObject.setObjectName(probe, "unchanged")
    Qt.Connection.with(Unit,
      Qt.Signal.connect(~progressChanged(), ~Qt.QObject, ~record, object, probe),
      connection => disconnected(object, probe, connection))

def noop(state: Unit) -> Qt.Action(Unit):
  Qt.Action.pure(Unit, Unit{})

def destroy_connected(+object: Qt.QObject) -> Qt.Action(Unit):
  Qt.Connection.with(Unit, Qt.Signal.connect(~finished(), ~Unit, ~noop, object, Unit{}),
    connection => Qt.QObject.destroy(object))

def self_removed(state: Unit) -> Qt.Action(Unit):
  Qt.CallbackProbe.customDisconnectSaved()

def disconnect_inside(+object: Qt.QObject) -> Qt.Action(Unit):
  Qt.Connection.with(Unit, Qt.Signal.connect(~finished(), ~Unit, ~self_removed, object, Unit{}),
    connection => do Qt.Action<Unit>:
      Qt.CallbackProbe.customRememberConnection(connection)
      Qt.Signal.emit(~finished(), object)
      Qt.Signal.emit(~finished(), object))

def worker_record(probe: Qt.QObject, value: Qt.Int32, text: String) -> Qt.Action(Unit):
  Qt.QObject.setObjectName(probe, text)

def worker_emit(object: Qt.QObject, probe: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    emitted: U32 <- Qt.CallbackProbe.customSignalFromWorker(object)
    name: String <- Qt.QObject.objectName(probe)
    require(U32.is_eq(emitted, 1) && String.eq(name, "Worker"), "Queued custom signal missed its Bend handler or copied storage")

def worker_demo(+object: Qt.QObject, +probe: Qt.QObject) -> Qt.Action(Unit):
  Qt.Connection.with(Unit,
    Qt.Signal.connect(~progressChanged(), ~Qt.QObject, ~worker_record, object, probe),
    connection => worker_emit(object, probe))

def malformed(+object: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    missing: Result<&1, &1, U32 & String, Qt.Connection> <- Qt.Action.attempt(Qt.Connection,
      Qt.Signal.connect(~valuesChanged(), ~Unit, ~primitive_values, object, Unit{}))
    expect_error(Qt.Connection, missing, 2)
    schema: Qt.Wire <- Qt.Signal.schema(progressChanged())
    bad_arity: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit,
      Qt.Signal.emit_raw(object, schema, Qt.WireSequence{Nil{}}))
    expect_error(Unit, bad_arity, 22)
    Qt.Signal.emit(~inherited(), object, "inherited emission")

def object_cases(+object: Qt.QObject, +probe: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    connected(object, probe)
    failed_handler(object)
    disconnect_demo(object, probe)
    malformed(object)
    worker_demo(object, probe)
    interop: U32 <- Qt.CallbackProbe.customSignalInterop(object)
    require(U32.is_eq(interop, 1), "Custom signals did not interoperate with Qt and QML")

def Shared() -> Qt.ObjectType:
  Qt.ObjectType.withSignals(Qt.QObject.define("SharedSignalSchema", []), [finished()])

def Conflicting() -> Qt.ObjectType:
  Qt.QObject.define("SharedSignalSchema", [Qt.Property.define("extra", Qt.string())])

def shared_namespace() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    first: Qt.QObject <- Qt.QObject.newWithSignals("SharedSignalSchema", [finished()])
    second: Qt.ObjectType.Instance(Shared()) <- Qt.ObjectType.new(~Shared())
    Qt.ObjectType.emit(~Shared(), ~finished(), second)
    conflict: Result<&1, &1, U32 & String, Qt.ObjectType.Instance(Conflicting())> <- Qt.Action.attempt(Qt.ObjectType.Instance(Conflicting()), Qt.ObjectType.new(~Conflicting()))
    expect_error(Qt.ObjectType.Instance(Conflicting()), conflict, 17)
    native_name: Result<&1, &1, U32 & String, Qt.QObject> <- Qt.Action.attempt(Qt.QObject, Qt.QObject.newWithSignals("QTimer", []))
    expect_error(Qt.QObject, native_name, 17)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QObject.with(Unit, Qt.QObject.new(), probe =>
      Qt.QObject.with(Unit,
        Qt.QObject.newWithSignals("Counter", [progressChanged(), finished()]),
        object => object_cases(object, probe)))
    Qt.QObject.with(Unit, Qt.QObject.newWithSignals("Values", [valuesChanged()]), object => primitive_demo(object))
    Qt.QObject.with(Unit, Qt.QObject.newWithSignals("Temporary", [finished()]), object => destroy_connected(object))
    Qt.QObject.with(Unit, Qt.QObject.newWithSignals("SelfDisconnect", [finished()]), object => disconnect_inside(object))
    invalid: Result<&1, &1, U32 & String, Qt.QObject> <- Qt.Action.attempt(Qt.QObject,
      Qt.QObject.newWithSignals("Invalid", [Qt.Signal.define("bad-name", [])]))
    expect_error(Qt.QObject, invalid, 22)
    duplicate: Result<&1, &1, U32 & String, Qt.QObject> <- Qt.Action.attempt(Qt.QObject,
      Qt.QObject.newWithSignals("Duplicate", [finished(), finished()]))
    expect_error(Qt.QObject, duplicate, 17)
    changed: Result<&1, &1, U32 & String, Qt.QObject> <- Qt.Action.attempt(Qt.QObject,
      Qt.QObject.newWithSignals("Counter", [finished()]))
    expect_error(Qt.QObject, changed, 17)
    Qt.scoped(Unit, shared_namespace())
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Custom signals leaked resources")
    Qt.Action.lift(Unit, IO.print("QT612_CUSTOM_SIGNAL_CONTRACTS_OK declared=1 typed=1 emitted=1 connected=1 qt_metadata=1 nested=1 objects=0 connections=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
