import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def text(count: Nat) -> String:
  match count:
    case 0n: "message end"
    case 1n+rest: "A complete native callback failure message with Unicode Łódź and no truncation. " ++ text(rest)

def cleanup_text() -> String:
  "Cleanup failure: " ++ text(16n)

def body_text() -> String:
  "Body failure: " ++ text(16n)

def cleanup(state: Unit, identity: Qt.ObjectIdentity) -> Qt.Action(Unit):
  Qt.Action.fail(Unit, 74, cleanup_text())

def failure() -> Qt.Method:
  Qt.Method.define("failure", [], Qt.string())

def fresh() -> Qt.Method:
  Qt.Method.define("fresh", [], Qt.qobject())

def Model() -> Qt.ObjectType:
  Qt.ObjectType.withMethods(Qt.QObject.define("ErrorMessageModel", []), [failure(), fresh()])

def fail_body(state: Unit) -> Qt.Action(String):
  do Qt.Action<String>:
    object: Qt.QObject <- Qt.QObject.new()
    connection: Qt.Connection <- Qt.QObject.connect_destroyed(~Unit, ~cleanup, object, Unit{})
    kept: Qt.Connection <- Qt.Connection.detachFromScope(connection)
    Qt.Action.fail(String, 73, body_text())

def new_then_cleanup_fails(state: Unit) -> Qt.Action(Qt.QObject):
  do Qt.Action<Qt.QObject>:
    object: Qt.QObject <- Qt.QObject.new()
    connection: Qt.Connection <- Qt.QObject.connect_destroyed(~Unit, ~cleanup, object, Unit{})
    kept: Qt.Connection <- Qt.Connection.detachFromScope(connection)
    Qt.QObject.new()

def check(-A: Type, result: Result<&1, &1, U32 & String, A>, code: U32, message: String) -> Qt.Action(Unit):
  match result:
    case Fail{(actual, received)}:
      require(U32.is_eq(actual, code) && String.eq(received, message), "A native callback changed its failure code or message")
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected native callback failure")

def repeat(count: Nat, +self: Qt.QObject) -> Qt.Action(Unit):
  match count:
    case 0n: Qt.Action.pure(Unit, Unit{})
    case 1n+rest:
      do Qt.Action<Unit>:
        body: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.Method.call(~failure(), self))
        check(String, body, 73, body_text())
        cleanup_result: Result<&1, &1, U32 & String, Qt.QObject> <- Qt.Action.attempt(Qt.QObject, Qt.Method.call(~fresh(), self))
        check(Qt.QObject, cleanup_result, 74, cleanup_text())
        live: U32 <- Qt.Runtime.liveObjects()
        require(U32.is_eq(live, 1), "A failed callback retained an automatically promoted result")
        repeat(rest, self)

def objects() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    instance: Qt.ObjectType.Instance(Model()) <- Qt.ObjectType.new(~Model())
    +self: Qt.QObject = Qt.ObjectType.as_QObject(~Model(), instance)
    Qt.Method.handle(~failure(), ~Unit, ~fail_body, self, Unit{})
    Qt.Method.handle(~fresh(), ~Unit, ~new_then_cleanup_fails, self, Unit{})
    repeat(16n, self)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, objects())
    live: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(live, 0) && U32.is_eq(connections, 0), "Error handling leaked native resources")
    Qt.Action.lift(Unit, IO.print("QT612_ERROR_MESSAGES_OK text=1 precedence=1 rollback=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
