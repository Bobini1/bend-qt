import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

# The window would retain the object that already retains the window.
def focus(value: Qt.QObject) -> Qt.Action(Qt.QObject):
  Qt.Action.pure(Qt.QObject, value)

def rejected(result: Result<&1, &1, U32 & String, Qt.QObject>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 40), "Wrong retention cycle error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "A retention cycle was accepted")

def window_demo(+window: Qt.QWindow, +value: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QWindow.Virtual.focusObject.handle(~Qt.QObject, ~focus, window, value)
    Qt.CallbackProbe.prepareCycle(window, value)
    result: Result<&1, &1, U32 & String, Qt.QObject> <- Qt.Action.attempt(Qt.QObject, Qt.QWindow.focusObject(window))
    rejected(result)

def value_demo(+value: Qt.QObject) -> Qt.Action(Unit):
  Qt.QWindow.with(Unit, Qt.QWindow.newOverride(), window => window_demo(window, value))

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QObject.with(Unit, Qt.QObject.new(), value => value_demo(value))
    objects: U32 <- Qt.Runtime.liveObjects()
    edges: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(edges, 0), "A rejected retention leaked native state")
    Qt.Action.lift(Unit, IO.print("QT612_CALLBACK_RETENTION_CYCLE_OK rejected_before_native_return=1 objects=0 edges=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
