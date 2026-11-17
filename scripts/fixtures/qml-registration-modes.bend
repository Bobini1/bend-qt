import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def title() -> Qt.Property:
  Qt.Property.define("title", Qt.string())

def Card() -> Qt.ObjectType:
  Qt.QObject.define("UncreatableModeCard", [title()])

def Anonymous() -> Qt.ObjectType:
  Qt.QObject.define("AnonymousModeCard", [title()])

def child() -> Qt.Property:
  Qt.Property.define("child", Qt.ObjectType.arg(~Anonymous()))

def Holder() -> Qt.ObjectType:
  Qt.QObject.define("AnonymousModeHolder", [child()])

def NonDefault() -> Qt.ObjectType:
  Qt.QSocketNotifier.define("UncreatableModeNotifier", [])

def promoted_registration() -> Qt.Action(Qt.Qml.Registration(Card())):
  do Qt.Action<Qt.Qml.Registration(Card())>:
    registration: Qt.Qml.Registration(Card()) <- Qt.Qml.registerUncreatable(~Card(), "Bend.UncreatableMode", 1, 0, "Card", "Cards come from Bend")
    Qt.Qml.Registration.moveToParentScope(~Card(), registration)

def expect_error(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(+code, message)}:
      require(U32.is_eq(code, expected), "QML registration error " ++ U32.show(code) ++ ": " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Invalid QML registration succeeded")

def error_message(errors: List<&2, Qt.QQmlError>, expected: String) -> Qt.Action(Unit):
  match errors:
    case Nil{}: Qt.Action.fail(Unit, 1, "Rejected QML did not provide an error")
    case first <> rest:
      do Qt.Action<Unit>:
        +description: String <- Qt.QQmlError.description(first)
        require(String.eq(description, expected), "Wrong QML rejection: " ++ description)

def rejected(source: String, expected: String) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +engine: Qt.QQmlEngine <- Qt.QQmlEngine.new()
    +component: Qt.QQmlComponent <- Qt.QQmlComponent.new__QQmlEngine_QObject(engine, Qt.QObject{0})
    data: Qt.QByteArray <- Qt.QByteArray.fromUtf8(source)
    url: Qt.QUrl <- Qt.QUrl.new()
    Qt.QQmlComponent.setData(component, data, url)
    error: Bool <- Qt.QQmlComponent.isError(component)
    require(error, "Uncreatable QML unexpectedly compiled")
    errors: List<&2, Qt.QQmlError> <- Qt.QQmlComponent.errors(component)
    error_message(errors, expected)

def read_title(source: String, name: String, object: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +engine: Qt.QQmlEngine <- Qt.QQmlEngine.new()
    context: Qt.QQmlContext <- Qt.QQmlEngine.rootContext(engine)
    Qt.QQmlContext.setContextProperty__String_QObject(context, name, object)
    +component: Qt.QQmlComponent <- Qt.QQmlComponent.new__QQmlEngine_QObject(engine, Qt.QObject{0})
    data: Qt.QByteArray <- Qt.QByteArray.fromUtf8(source)
    url: Qt.QUrl <- Qt.QUrl.new()
    Qt.QQmlComponent.setData(component, data, url)
    ready: Bool <- Qt.QQmlComponent.isReady(component)
    require(ready, "QML could not refer to the registered type")
    root: Qt.QObject <- Qt.QQmlComponent.create__QQmlContext(component, Qt.QQmlContext{0})
    result: Qt.QVariant <- Qt.QQmlProperty.read__QObject_String(root, "result")
    text: String <- Qt.QVariant.toString(result)
    require(String.eq(text, "from-bend"), "Registered type lost its properties in QML")

def cases() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    uncreatable: Qt.Qml.Registration(Card()) <- Qt.scoped(Qt.Qml.Registration(Card()), promoted_registration())
    +card: Qt.ObjectType.Instance(Card()) <- Qt.ObjectType.new(~Card())
    Qt.ObjectType.set(~Card(), ~title(), card, "from-bend")
    Qt.scoped(Unit, read_title("import QtQml\nimport Bend.UncreatableMode 1.0\nQtObject { property Card card: provided; property string result: card.title }", "provided", Qt.ObjectType.as_QObject(~Card(), card)))
    Qt.scoped(Unit, rejected("import Bend.UncreatableMode 1.0\nCard {}", "Cards come from Bend"))
    Qt.Qml.Registration.with(~NonDefault(), Unit,
      Qt.Qml.registerUncreatable(~NonDefault(), "Bend.UncreatableMode", 1, 0, "Notifier", "Native constructor requires arguments"),
      registration => Qt.scoped(Unit, rejected("import Bend.UncreatableMode 1.0\nNotifier {}", "Native constructor requires arguments")))
    anonymous: Qt.Qml.Registration(Anonymous()) <- Qt.Qml.registerAnonymous(~Anonymous(), "Bend.AnonymousMode", 1)
    +related: Qt.ObjectType.Instance(Anonymous()) <- Qt.ObjectType.new(~Anonymous())
    Qt.ObjectType.set(~Anonymous(), ~title(), related, "from-bend")
    +holder: Qt.ObjectType.Instance(Holder()) <- Qt.ObjectType.new(~Holder())
    Qt.ObjectType.set(~Holder(), ~child(), holder, related)
    Qt.scoped(Unit, read_title("import QtQml\nimport Bend.AnonymousMode 1.0\nQtObject { property string result: provided.child.title }", "provided", Qt.ObjectType.as_QObject(~Holder(), holder)))
    Qt.scoped(Unit, rejected("import Bend.AnonymousMode 1.0\nAnonymousModeCard {}", "AnonymousModeCard is not a type"))
    unavailable: Qt.Qml.RegistrationHandle <- Qt.Qml.registerUnavailable("Bend.UnavailableMode", 1, 0, "Missing", "Missing is unavailable in this build")
    Qt.scoped(Unit, rejected("import Bend.UnavailableMode 1.0\nMissing {}", "Missing is unavailable in this build"))
    bad_version: Result<&1, &1, U32 & String, Qt.Qml.RegistrationHandle> <- Qt.Action.attempt(Qt.Qml.RegistrationHandle, Qt.Qml.registerUnavailable("Bend.InvalidMode", 255, 0, "Missing", "unavailable"))
    expect_error(Qt.Qml.RegistrationHandle, bad_version, 34)
    bad_name: Result<&1, &1, U32 & String, Qt.Qml.RegistrationHandle> <- Qt.Action.attempt(Qt.Qml.RegistrationHandle, Qt.Qml.registerUnavailable("Bend.InvalidMode", 1, 0, "lowercase", "unavailable"))
    expect_error(Qt.Qml.RegistrationHandle, bad_name, 22)
    bad_uri: Result<&1, &1, U32 & String, Qt.Qml.Registration(Anonymous())> <- Qt.Action.attempt(Qt.Qml.Registration(Anonymous()), Qt.Qml.registerAnonymous(~Anonymous(), "", 1))
    expect_error(Qt.Qml.Registration(Anonymous()), bad_uri, 22)
    bad_version: Result<&1, &1, U32 & String, Qt.Qml.Registration(Card())> <- Qt.Action.attempt(Qt.Qml.Registration(Card()), Qt.Qml.registerUncreatable(~Card(), "Bend.InvalidMode", 1, 255, "Card", "uncreatable"))
    expect_error(Qt.Qml.Registration(Card()), bad_version, 34)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, cases())
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "QML registrations leaked scoped objects")
    Qt.Action.lift(Unit, IO.print("QT612_QML_REGISTRATION_MODES_OK uncreatable=1 anonymous=1 unavailable=1 validation=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
