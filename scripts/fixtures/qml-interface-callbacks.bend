import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def uri_value(uri: Maybe<&2, String>) -> Qt.Action(Unit):
  match uri:
    case None{}: Qt.Action.pure(Unit, Unit{})
    case Some{+text}: require(String.eq(text, "") || String.eq(text, "org.Bend.ä"), "The QML URI was not copied as UTF-8")

def registered(state: Unit, uri: Maybe<&2, String>) -> Qt.Action(Unit):
  uri_value(uri)

def initialized(state: Unit, engine: Qt.QQmlEngine, uri: Maybe<&2, String>) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    require(U32.is_ne(Qt.QQmlEngine.word(engine), 0), "The engine identity was lost")
    uri_value(uri)

def extension_demo(+extension: Qt.QQmlExtensionInterface) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQmlTypesExtensionInterface.Virtual.registerTypes.handle(~Unit, ~registered, Qt.QQmlExtensionInterface.as_QQmlTypesExtensionInterface(extension), Unit{})
    Qt.QQmlExtensionInterface.Virtual.initializeEngine.handle(~Unit, ~initialized, extension, Unit{})
    Qt.CallbackProbe.qmlInterface(extension)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQmlExtensionInterface.with(Unit, Qt.QQmlExtensionInterface.newOverride(), extension => extension_demo(extension))
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "The QML interface handlers leaked the borrowed engine")
    Qt.Action.lift(Unit, IO.print("QT612_QML_INTERFACE_CALLBACKS_OK uri_utf8=1 null_distinct=1 engine_identity=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
