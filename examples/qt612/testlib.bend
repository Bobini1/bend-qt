import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def error(~A: Type, code: U32, result: Result<&1, &1, U32 & String, A>) -> Qt.Action(Unit):
  match result:
    case Fail{(actual, message)}: require(U32.is_eq(actual, code), "Wrong QtTest error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Invalid QtTest operation succeeded")

def bytes(+value: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    text: String <- Qt.QTest.toPrettyCString(value, Qt.Int64{3, 0})
    require(String.eq(text, "\"A\\x00Z\""), "QtTest did not preserve binary diagnostic text")
    invalid: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QTest.toPrettyCString(value, Qt.Int64{4, 0}))
    error(String, 34, invalid)

def missing_row(result: Result<&1, &1, U32 & String, Qt.MetaStorage>) -> Qt.Action(Unit):
  match result:
    case Fail{(+code, message)}: require(U32.is_eq(code, 61) || U32.is_eq(code, 95), "Wrong QtTest data-session error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "QtTest returned data outside a test session")

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes(65 <> 0 <> 90 <> Nil{}), value => bytes(value))
    formatted: String <- Qt.QTest.formatString("(", ")", "left" <> "right" <> Nil{})
    require(String.eq(formatted, "(left, right)"), "QtTest argument list formatting differs from native semantics")
    data: Result<&1, &1, U32 & String, Qt.MetaStorage> <- Qt.Action.attempt(Qt.MetaStorage, Qt.QTest.qElementData("missing", Qt.Int32{2}))
    missing_row(data)
    Qt.QTest.failOnWarning__String("Bend fixture warning")
    invalid: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QTest.failOnWarning__String("not\0terminated"))
    error(Unit, 22, invalid)
    absent: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QTest.qCaught__String_String_Int32("std::exception", "testlib.bend", Qt.Int32{1}))
    error(Unit, 1, absent)
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "QtTest output conversion leaked a handle")
    Qt.Action.lift(Unit, IO.print("QT612_TESTLIB_OK copied_cstrings=1 nul_rejected=1 allocated_output=1 binary_extent=1 native_exception_guard=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
