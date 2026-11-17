import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def checked(-A: Type, result: Result<&1, &1, U32 & String, A>) -> Qt.Action(Unit):
  match result:
    case Done{unit}: Qt.Action.fail(Unit, 1, "Native Qt exception was not reported")
    case Fail{(code, message)}: require(U32.is_eq(code, 14), "Native Qt exception has the wrong error")

def raised(+future: Qt.Future_QString) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    waited: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.Future_QString.await(future))
    checked(Unit, waited)
    result: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.Future_QString.resultAt(future, Qt.Int32{0}))
    checked(String, result)

def recovered(future: Qt.Future_QString) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    result: String <- Qt.Future_QString.resultAt(future, Qt.Int32{0})
    require(String.eq(result, "Qt still works after a native exception"), "Future did not recover after native failure")

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Future_QString.with(Unit, Qt.Future_QString.fromError("Native future failure"), future => raised(future))
    live: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(live, 0) && U32.is_eq(connections, 0), "Native exception bypassed scoped cleanup")
    Qt.Future_QString.with(Unit, Qt.Future_QString.fromResult("Qt still works after a native exception"), recovered)
    Qt.Action.lift(Unit, IO.print("QT612_EXCEPTIONS_OK await_error=1 result_error=1 cleanup=1 recovery=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
