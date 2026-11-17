import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expect_permission(result: Result<&1, &1, U32 & String, Unit>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}:
      require(U32.is_eq(code, 1), "Wrong application lifecycle error: " ++ message)
    case Done{value}:
      Qt.Action.fail(Unit, 1, "Binding application lifecycle was not protected")

def parent_case(+application: Qt.QCoreApplication, +parent: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    reparent: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QObject.setParent(Qt.QCoreApplication.as_QObject(application), parent))
    expect_permission(reparent)
    inherited: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QCoreApplication.setParent(application, parent))
    expect_permission(inherited)
    destruction: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QCoreApplication.destroy(application))
    expect_permission(destruction)
    Qt.QCoreApplication.release(application)
    owner: Qt.QObject <- Qt.QCoreApplication.parent(application)
    require(U32.is_eq(Qt.QObject.word(owner), 0), "Rejected adoption changed the application parent")
    alias: Qt.QCoreApplication <- Qt.QCoreApplication.instance()
    require(U32.is_eq(Qt.QCoreApplication.word(alias), Qt.QCoreApplication.word(application)), "Releasing borrowed application changed its identity")

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +application: Qt.QCoreApplication <- Qt.QCoreApplication.instance()
    require(U32.is_ne(Qt.QCoreApplication.word(application), 0), "Binding application is missing")
    Qt.QObject.with(Unit, Qt.QObject.new(), parent => parent_case(application, parent))
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    # The binding owns this application until process exit. Its borrowed
    # identity remains registered; the user-created parent has been destroyed.
    # The runtime-owned application is not a leakable handle.
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Unexpected resources after application guard checks")
    Qt.Action.lift(Unit, IO.print("QT612_HOST_LIFETIME_OK reparent_rejected=1 destroy_rejected=1 release_safe=1 borrowed_host=1 connections=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
