import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expected(-A: Type, result: Result<&1, &1, U32 & String, A>, code: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(actual, text)}: require(U32.is_eq(actual, code), text)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected signal connection rejection")

def fired() -> Qt.Signal:
  Qt.Signal.withRevision(Qt.Signal.withArgumentNames(Qt.Signal.define("fired", [Qt.bool()]), ["checked"]), 2)

def forwarded() -> Qt.Signal:
  Qt.Signal.withVersionRevision(Qt.Signal.withArgumentNames(Qt.Signal.define("forwarded", [Qt.bool()]), ["checked"]), 1, 3)

def events() -> Qt.Property:
  Qt.Property.define("events", Qt.u32())

def saved() -> Qt.Property:
  Qt.Property.define("saved", Qt.QByteArray.arg())

def rawData() -> Qt.Signal:
  Qt.Signal.define("rawData", [Qt.string(), Qt.QByteArray.arg(), Qt.variantMap(), Qt.variant()])

def Counter() -> Qt.QtObject:
  Qt.QtObject.withSignals(Qt.QObject.define("SignalConnectionCounter", [events(), saved()]), [fired(), forwarded(), rawData()])

def bump(self: Qt.QObject, checked: Bool) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +object: Qt.QObject = self
    count: U32 <- Qt.Property.get(~events(), object)
    Qt.Property.set(~events(), object, U32.add(count, 1))

def count(self: Qt.QObject, expected: U32) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    actual: U32 <- Qt.Property.get(~events(), self)
    require(U32.is_eq(actual, expected), "Signal delivery count differs")

def queued(+self: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Property.set(~events(), self, 0)
    connection: Qt.Connection <- Qt.Signal.connectWith(~fired(), ~Qt.QObject, ~bump, self, Qt.Qt.ConnectionType.QueuedConnection(), self)
    Qt.Signal.emit(~fired(), self, True{})
    count(self, 0)
    Qt.QCoreApplication.processEvents()
    count(self, 1)

def single_shot(+self: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Property.set(~events(), self, 0)
    connection: Qt.Connection <- Qt.Signal.connectWith(~fired(), ~Qt.QObject, ~bump, self, Qt.Qt.ConnectionType.SingleShotConnection(), self)
    Qt.Signal.emit(~fired(), self, True{})
    Qt.Signal.emit(~fired(), self, False{})
    count(self, 1)
    closed: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.Connection.disconnect(connection))
    expected(Unit, closed, 116)

def blocking(+self: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    connection: Qt.Connection <- Qt.Signal.connectWith(~fired(), ~Qt.QObject, ~bump, self, Qt.Qt.ConnectionType.BlockingQueuedConnection(), self)
    failed: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.Signal.emit(~fired(), self, True{}))
    expected(Unit, failed, 35)

def invalid(+self: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    duplicate: Result<&1, &1, U32 & String, Qt.Connection> <- Qt.Action.attempt(Qt.Connection,
      Qt.Signal.connectWith(~fired(), ~Qt.QObject, ~bump, self, Qt.Qt.ConnectionType.UniqueConnection(), self))
    expected(Qt.Connection, duplicate, 22)
    invalid: Result<&1, &1, U32 & String, Qt.Connection> <- Qt.Action.attempt(Qt.Connection,
      Qt.Signal.connectWith(~fired(), ~Qt.QObject, ~bump, self, Qt.Qt.ConnectionType{4}, self))
    expected(Qt.Connection, invalid, 22)

def set_checked() -> Qt.Method:
  Qt.Method.define("setChecked", [Qt.bool()], Qt.unit())

def native_method(+self: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +button: Qt.QPushButton <- Qt.QPushButton.new()
    Qt.QPushButton.setCheckable(button, True{})
    connection: Qt.Connection <- Qt.Signal.connectMethodWith(~fired(), ~set_checked(), self,
      Qt.QPushButton.as_QObject(button), Qt.Qt.ConnectionType.UniqueConnection())
    duplicate: Result<&1, &1, U32 & String, Qt.Connection> <- Qt.Action.attempt(Qt.Connection,
      Qt.Signal.connectMethodWith(~fired(), ~set_checked(), self,
        Qt.QPushButton.as_QObject(button), Qt.Qt.ConnectionType.UniqueConnection()))
    expected(Qt.Connection, duplicate, 17)
    Qt.Signal.emit(~fired(), self, True{})
    checked: Bool <- Qt.QPushButton.isChecked(button)
    require(checked, "Native QObject method destination did not execute")

def signal_destination(+self: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Property.set(~events(), self, 0)
    observed: Qt.Connection <- Qt.Signal.connect(~forwarded(), ~Qt.QObject, ~bump, self, self)
    forwarded: Qt.Connection <- Qt.Signal.connectSignalWith(~fired(), ~forwarded(), self, self, Qt.Qt.ConnectionType.SingleShotConnection())
    Qt.Signal.emit(~fired(), self, True{})
    Qt.Signal.emit(~fired(), self, False{})
    count(self, 1)

def destroyed_signal() -> Qt.Signal:
  Qt.Signal.define("destroyed", [Qt.qobject()])

def start_timer() -> Qt.Method:
  Qt.Method.define("start", [], Qt.unit())

def terminal_destination() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +source: Qt.QObject <- Qt.QObject.new()
    +timer: Qt.QTimer <- Qt.QTimer.new()
    connection: Qt.Connection <- Qt.Signal.connectMethod(~destroyed_signal(), ~start_timer(),
      source, Qt.QTimer.as_QObject(timer))
    Qt.QObject.destroy(source)
    active: Bool <- Qt.QTimer.isActive(timer)
    require(active, "The native destroyed destination was disconnected before Qt delivered it")
    ended: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.Connection.disconnect(connection))
    expected(Unit, ended, 116)
    Qt.QTimer.stop(timer)

def names(values: List<&2, Qt.QByteArray>) -> Qt.Action(Unit):
  match values:
    case value <> Nil{}:
      do Qt.Action<Unit>:
        text: String <- Qt.QByteArray.utf8(value)
        require(String.eq(text, "checked"), "Signal argument name metadata changed")
    case _: Qt.Action.fail(Unit, 1, "Signal argument names have the wrong shape")

def metadata(+self: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +meta: Qt.QMetaObject <- Qt.QObject.metaObject(self)
    index: Qt.Int32 <- Qt.QMetaObject.indexOfSignal(meta, "fired(bool)")
    +method: Qt.QMetaMethod <- Qt.QMetaObject.method(meta, index)
    values: List<&2, Qt.QByteArray> <- Qt.QMetaMethod.parameterNames(method)
    names(values)
    revision: Qt.Int32 <- Qt.QMetaMethod.revision(method)
    require(U32.is_eq(Qt.Int32.word(revision), 65282), "Minor signal revision metadata changed")
    index: Qt.Int32 <- Qt.QMetaObject.indexOfSignal(meta, "forwarded(bool)")
    method: Qt.QMetaMethod <- Qt.QMetaObject.method(meta, index)
    revision: Qt.Int32 <- Qt.QMetaMethod.revision(method)
    require(U32.is_eq(Qt.Int32.word(revision), 259), "Version signal revision metadata changed")

def raw_mapping(values: List<&2, Qt.PairValue<String, Qt.QVariant>>) -> Qt.Action(Unit):
  match values:
    case Qt.PairValue{byte_key, byte_value} <> Qt.PairValue{text_key, text_value} <> Nil{}:
      do Qt.Action<Unit>:
        require(String.eq(byte_key, "bytes") && String.eq(text_key, "text"), "Snapshot map keys changed")
        bytes: Qt.QByteArray <- Qt.QVariant.to_QByteArray(byte_value)
        byte_text: String <- Qt.QByteArray.utf8(bytes)
        text: String <- Qt.QVariant.toString(text_value)
        require(String.eq(byte_text, "Raw") && String.eq(text, "Raw"), "Nested map retained fromRawData storage")
    case _: Qt.Action.fail(Unit, 1, "Snapshot map has the wrong shape")

def raw_received(self: Qt.QObject, text: String, bytes: Qt.QByteArray,
  mapping: List<&2, Qt.PairValue<String, Qt.QVariant>>, value: Qt.QVariant) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    byte_text: String <- Qt.QByteArray.utf8(bytes)
    require(String.eq(text, "Raw") && String.eq(byte_text, "Raw"), "Signal retained fromRawData storage")
    raw_mapping(mapping)
    document: Qt.QJsonDocument <- Qt.QJsonDocument.fromVariant(value)
    encoded: Qt.QByteArray <- Qt.QJsonDocument.toJson__QJsonDocument_JsonFormat(document, Qt.QJsonDocument.JsonFormat.Compact())
    text: String <- Qt.QByteArray.utf8(encoded)
    require(String.eq(text, "{\"values\":[\"Raw\",\"Raw\"]}"), "Nested QVariant retained fromRawData storage")
    bump(self, True{})

def raw_snapshots(+self: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Property.set(~events(), self, 0)
    connection: Qt.Connection <- Qt.Signal.connectWith(~rawData(), ~Qt.QObject, ~raw_received, self, Qt.Qt.ConnectionType.QueuedConnection(), self)
    emitted: U32 <- Qt.CallbackProbe.rawSnapshots(self)
    require(U32.is_eq(emitted, 1), "Raw-data snapshot producer failed")
    count(self, 1)
    bytes: Qt.QByteArray <- Qt.Property.get(~saved(), self)
    text: String <- Qt.QByteArray.utf8(bytes)
    require(String.eq(text, "Raw"), "Stored QByteArray retained fromRawData storage")

def objects() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    counter: Qt.QtObject.Instance(Counter()) <- Qt.QtObject.new(~Counter())
    +self: Qt.QObject = Qt.QtObject.as_QObject(~Counter(), counter)
    Qt.scoped(Unit, queued(self))
    Qt.scoped(Unit, single_shot(self))
    Qt.scoped(Unit, blocking(self))
    Qt.scoped(Unit, invalid(self))
    Qt.scoped(Unit, native_method(self))
    Qt.scoped(Unit, signal_destination(self))
    Qt.scoped(Unit, terminal_destination())
    Qt.scoped(Unit, metadata(self))
    Qt.scoped(Unit, raw_snapshots(self))

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, objects())
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Signal connection modes leaked resources")
    Qt.Action.lift(Unit, IO.print("QT612_SIGNAL_CONNECTION_MODES_OK queued=1 single_shot=1 unique=1 native_method=1 signal=1 terminal=1 metadata=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
