import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

# Each call returns a new object. The window keeps every result until it is
# destroyed itself.
def focus(state: Unit) -> Qt.Action(Qt.QObject):
  Qt.QObject.new()

def retained(result: Result<&1, &1, U32 & String, Unit>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 16), "Wrong retained handler result error: " ++ message)
    case Done{unit}: Qt.Action.fail(Unit, 1, "Native handler result was not retained")

def results(+window: Qt.QWindow, +first: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QObject.setObjectName(first, "still alive")
    second: Qt.QObject <- Qt.QWindow.focusObject(window)
    require(U32.is_ne(Qt.QObject.word(first), Qt.QObject.word(second)), "Distinct handler results reused an identity")
    name: String <- Qt.QObject.objectName(first)
    require(String.eq(name, "still alive"), "An earlier handler result was released by a later result")
    deletion: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QObject.destroy(first))
    retained(deletion)

def window_demo(+window: Qt.QWindow) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QWindow.Virtual.focusObject.handle(~Unit, ~focus, window, Unit{})
    Qt.QObject.with(Unit, Qt.QWindow.focusObject(window), first => results(window, first))

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QWindow.with(Unit, Qt.QWindow.newOverride(), window => window_demo(window))
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Retained handler results survived their proxy")
    Qt.Action.lift(Unit, IO.print("QT612_RETAINED_CALLBACKS_OK cumulative_results=1 scope_release=1 protected_destroy=1 objects=0 connections=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
