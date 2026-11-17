import Base
import ../../packages/qt612/qt.bend as Qt

# The program constructs its single application object, as in C++. GUI APIs
# report ENXIO (6) before one exists instead of letting Qt abort the process;
# documented pre-application setup works; a second application is EEXIST (17).

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def rejected(-A: Type, result: Result<&1, &1, U32 & String, A>, code: U32, message: String) -> Qt.Action(Unit):
  match result:
    case Fail{(actual, text)}: require(U32.is_eq(actual, code), text)
    case Done{value}: Qt.Action.fail(Unit, 1, message)

def running() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    second: Result<&1, &1, U32 & String, Qt.QGuiApplication> <- Qt.Action.attempt(Qt.QGuiApplication, Qt.QGuiApplication.new())
    rejected(Qt.QGuiApplication, second, 17, "A second application object was constructed")
    Qt.QWidget.with(Unit, Qt.QWidget.new(), widget => Qt.Action.pure(Unit, Unit{}))
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "The application handle counted as a leakable object")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    early: Result<&1, &1, U32 & String, Qt.QWidget> <- Qt.Action.attempt(Qt.QWidget, Qt.QWidget.new())
    rejected(Qt.QWidget, early, 6, "A QWidget was constructed before the QApplication")
    Qt.QSurfaceFormat.with(Unit, Qt.QSurfaceFormat.new(), format => Qt.QSurfaceFormat.setDefaultFormat(format))
    Qt.QApplication.with(Unit, Qt.QApplication.new(), app => running())
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Application objects leaked handles")
    Qt.Action.lift(Unit, IO.print("QT612_APPLICATION_OBJECTS_OK early_gui=1 setup=1 second=1 widgets=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
