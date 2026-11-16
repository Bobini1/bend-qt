import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def failure() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    object: Qt.QObject <- Qt.QObject.new()
    Qt.Action.fail(Unit, 44, "body failure")

def promoted() -> Qt.Action(Qt.QObject):
  do Qt.Action<Qt.QObject>:
    object: Qt.QObject <- Qt.QObject.new()
    Qt.QObject.moveToParentScope(object)

def created_then_released(count: Nat) -> Qt.Action(Unit):
  match count:
    case 0n: Qt.Action.pure(Unit, Unit{})
    case 1n+rest:
      do Qt.Action<Unit>:
        object: Qt.QObject <- Qt.QObject.new()
        Qt.QObject.destroy(object)
        created_then_released(rest)

def task(delay: U32) -> IO(Result<&1, &1, U32 & String, Unit>):
  Qt.run(Unit, do Qt.Action<Unit>:
    +object: Qt.QObject <- Qt.QObject.new()
    Qt.Action.lift(Unit, IO.sleep(delay))
    Qt.QObject.setObjectName(object, "still alive"))

def concurrent() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    first: Chan(Result<&1, &1, U32 & String, Unit>) <- Qt.Action.lift(Chan(Result<&1, &1, U32 & String, Unit>), IO.fork(Result<&1, &1, U32 & String, Unit>, task(5)))
    second: Result<&1, &1, U32 & String, Unit> <- Qt.Action.lift(Result<&1, &1, U32 & String, Unit>, task(20))
    one: Result<&1, &1, U32 & String, Unit> <- Qt.Action.lift(Result<&1, &1, U32 & String, Unit>, IO.join(Result<&1, &1, U32 & String, Unit>, first))
    Qt.Action.result(Unit, second)
    Qt.Action.result(Unit, one)

def inspect_failure(result: Result<&1, &1, U32 & String, Unit>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 44) && String.eq(message, "body failure"), "Cleanup changed body failure")
    case Done{unit}: Qt.Action.fail(Unit, 1, "Expected scope failure")

def expected(-A: Type, result: Result<&1, &1, U32 & String, A>, code: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(actual, message)}: require(U32.is_eq(actual, code), message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected scope transfer rejection")

def scope_ownership() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +object: Qt.QObject <- Qt.QObject.new()
    refused: Result<&1, &1, U32 & String, Qt.QObject> <- Qt.Action.attempt(Qt.QObject, Qt.QObject.moveToParentScope(object))
    expected(Qt.QObject, refused, 22)
    Qt.QObject.setObjectName(object, "root still owns cleanup")
    stolen: Result<&1, &1, U32 & String, Qt.QObject> <- Qt.Action.attempt(Qt.QObject,
      Qt.scoped(Qt.QObject, Qt.QObject.detachFromScope(object)))
    expected(Qt.QObject, stolen, 1)
    Qt.QObject.destroy(object)

def detached() -> Qt.Action(Qt.QObject):
  do Qt.Action<Qt.QObject>:
    object: Qt.QObject <- Qt.QObject.new()
    Qt.QObject.detachFromScope(object)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    scope_ownership()
    failed: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.scoped(Unit, failure()))
    inspect_failure(failed)
    +kept: Qt.QObject <- Qt.scoped(Qt.QObject, promoted())
    Qt.QObject.setObjectName(kept, "promoted")
    count: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(count, 1), "A nested scope released a promoted object")
    Qt.QObject.destroy(kept)
    # Exercises scope record compaction across many reused native slots.
    created_then_released(4200n)
    concurrent()
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Scope failure, churn or concurrent evaluation leaked")
    Qt.Action.lift(Unit, IO.print("QT612_ACTION_SCOPES_OK"))

def main() -> IO(Unit):
  do IO<Unit>:
    failed: Result<&1, &1, U32 & String, Unit> <- Qt.run(Unit, failure())
    +object: Qt.QObject <- IO.try(Qt.QObject, Qt.run(Qt.QObject, detached()))
    IO.try(Unit, Qt.run(Unit, do Qt.Action<Unit>:
      inspect_failure(failed)
      Qt.QObject.setObjectName(object, "detached across root scopes")
      Qt.QObject.destroy(object)
      objects: U32 <- Qt.Runtime.liveObjects()
      require(U32.is_eq(objects, 0), "A failed root evaluation leaked an owned QObject")
      checks()))
