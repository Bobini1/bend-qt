import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def missing(result: Result<&1, &1, U32 & String, String>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong future result error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected unavailable future result")

def invalid_wait(result: Result<&1, &1, U32 & String, Unit>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 61), "Wrong invalid future wait error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Invalid future unexpectedly completed")

def clone(+original: Qt.Future_QString, +copy: Qt.Future_QString) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Future_QString.destroy(original)
    Qt.Future_QString.await(copy)
    value: String <- Qt.Future_QString.resultAt(copy, Qt.Int32{0})
    require(String.eq(value, "Future result 🎵"), "Future copy lost native shared state")
    absent: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.Future_QString.resultAt(copy, Qt.Int32{1}))
    missing(absent, 61)
    negative: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.Future_QString.resultAt(copy, Qt.Int32.neg(1)))
    missing(negative, 34)

def ready(+value: Qt.Future_QString) -> Qt.Action(Unit):
  Qt.Future_QString.with(Unit, Qt.Future_QString.clone(value), copy => clone(value, copy))

def empty(+value: Qt.Future_QString) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    valid: Bool <- Qt.Future_QString.isValid(value)
    require(Bool.not(valid), "Default future unexpectedly contains a result")
    absent: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.Future_QString.resultAt(value, Qt.Int32{0}))
    missing(absent, 61)
    waited: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.Future_QString.await(value))
    invalid_wait(waited)

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Future_QString.with(Unit, Qt.Future_QString.fromResult("Future result 🎵"), value => ready(value))
    Qt.Future_QString.with(Unit, Qt.Future_QString.new(), value => empty(value))
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Future scopes leaked handles or connections")
    Qt.Action.lift(Unit, IO.print("QT612_FUTURES_OK completed_before_watch=1 clone_state=1 nonblocking_results=1 invalid_index=1 empty=1 objects=0 connections=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
