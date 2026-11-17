import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def number(expected: U32, value: Qt.QJSPrimitiveValue) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    actual: Qt.Int32 <- Qt.QJSPrimitiveValue.toInteger(value)
    require(U32.is_eq(Qt.Int32.word(actual), expected), "Increment operator lost its prefix/postfix behavior")

def increment(+value: Qt.QJSPrimitiveValue) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QJSPrimitiveValue.with(Unit, Qt.QJSPrimitiveValue.op_increment(value), result => number(43, result))
    Qt.QJSPrimitiveValue.with(Unit, Qt.QJSPrimitiveValue.op_increment__Int32(value, Qt.Int32{0}), result => number(43, result))
    number(44, value)
    Qt.QJSPrimitiveValue.with(Unit, Qt.QJSPrimitiveValue.op_decrement(value), result => number(43, result))
    number(43, value)

def key(value: Qt.QKeyCombination) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    combined: Qt.Int32 <- Qt.QKeyCombination.toCombined(value)
    require(U32.is_eq(Qt.Int32.word(combined), 0), "Empty key sequence element changed")

def key_error(result: Result<&1, &1, U32 & String, Qt.QKeyCombination>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 34), "Wrong key sequence bound error")
    case Done{value}: Qt.Action.finally(Unit, Qt.Action.fail(Unit, 1, "Invalid key sequence index succeeded"), Qt.QKeyCombination.release(value))

def sequence(+value: Qt.QKeySequence) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QKeyCombination.with(Unit, Qt.QKeySequence.op_at(value, 3), key)
    bad: Result<&1, &1, U32 & String, Qt.QKeyCombination> <- Qt.Action.attempt(Qt.QKeyCombination, Qt.QKeySequence.op_at(value, 4))
    key_error(bad)

def missing_cbor(value: Qt.QCborValue) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    missing: Bool <- Qt.QCborValue.isUndefined(value)
    require(missing, "Missing negative CBOR key did not produce undefined")

def map(value: Qt.QCborMap) -> Qt.Action(Unit):
  Qt.QCborValue.with(Unit, Qt.QCborMap.op_at__Int64(value, Qt.Int64{4294967295, 4294967295}), missing_cbor)

def missing_json(value: Qt.QJsonValue) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    missing: Bool <- Qt.QJsonValue.isUndefined(value)
    require(missing, "JSON index miss did not preserve native undefined semantics")

def json(value: Qt.QJsonValue) -> Qt.Action(Unit):
  Qt.QJsonValue.with(Unit, Qt.QJsonValue.op_at__Int64(value, Qt.Int64{4294967295, 4294967295}), missing_json)

def matrix_data(+matrix: Qt.QMatrix4x4, +view: Qt.ArrayView_float) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +count: Qt.UInt64 <- Qt.ArrayView_float.size(view)
    require(U32.is_eq(Qt.UInt64.lo(count), 16) && U32.is_eq(Qt.UInt64.hi(count), 0), "Matrix storage has the wrong extent")
    Qt.ArrayView_float.set(view, Qt.UInt64{5, 0}, Qt.F64{0, 1073741824})
    element: Qt.F64 <- Qt.QMatrix4x4.op_call(matrix, Qt.Int32{1}, Qt.Int32{1})
    equal: Bool <- Qt.F64.equal(element, Qt.F64{0, 1073741824})
    require(equal, "Mutable matrix data did not update the native value")

def matrix(+value: Qt.QMatrix4x4) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    first: Qt.F64 <- Qt.QMatrix4x4.op_call(value, Qt.Int32{0}, Qt.Int32{0})
    equal: Bool <- Qt.F64.equal(first, Qt.F64{0, 1072693248})
    require(equal, "Call operator source signature was not preserved")
    Qt.ArrayView_float.with(Unit, Qt.QMatrix4x4.data(value), view => matrix_data(value, view))

def compare(value: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    equal: Bool <- Qt.QByteArray.op_equal__String(value, "copied text")
    require(equal, "Const pointer reference comparison changed its string")

def log(value: Qt.QMessageLogger) -> Qt.Action(Unit):
  Qt.QMessageLogger.warning__String(value, "QT612_LITERAL_LOG %s %n %08x")

def timed_out(code: U32) -> Qt.Action(Unit):
  Qt.QCoreApplication.exit__Int32(Qt.Int32{code})

# The deferred slot starts the timer inside the event loop; its timeout ends
# the loop.
def wait_timer(+timer: Qt.QTimer, connection: Qt.Connection) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QTimer.singleShot__Int32_QObject_String(Qt.Int32{0}, Qt.QTimer.as_QObject(timer), "1" ++ "start()")
    code: Qt.Int32 <- Qt.QCoreApplication.exec()
    require(U32.is_eq(Qt.Int32.word(code), 6), "The deferred slot did not start the timer")

def timer(+value: Qt.QTimer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QTimer.setSingleShot(value, True{})
    Qt.QTimer.setInterval__Int32(value, Qt.Int32{5})
    Qt.Connection.with(Unit, Qt.QTimer.connect_timeout(~U32, ~timed_out, value, 6), connection => wait_timer(value, connection))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QJSPrimitiveValue.with(Unit, Qt.QJSPrimitiveValue.new__Int32(Qt.Int32{42}), value => increment(value))
    Qt.QKeySequence.with(Unit, Qt.QKeySequence.new(), value => sequence(value))
    Qt.QCborMap.with(Unit, Qt.QCborMap.new(), map)
    Qt.QJsonValue.with(Unit, Qt.QJsonValue.new(), json)
    Qt.QMatrix4x4.with(Unit, Qt.QMatrix4x4.new(), value => matrix(value))
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromUtf8("copied text"), compare)
    Qt.QMessageLogger.with(Unit, Qt.QMessageLogger.new(), log)
    Qt.QTimer.with(Unit, Qt.QTimer.new(), value => timer(value))
    count: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(count, 0) && U32.is_eq(connections, 0), "Text or indexing conversion leaked native handles")
    Qt.Action.lift(Unit, IO.print("QT612_TEXT_INDEXING_OK prefix_postfix=1 bounded_index=1 numeric_key=1 undefined_index=1 call_operator=1 const_pointer_ref=1 literal_log=1 deferred_slot=1 objects=0 connections=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
