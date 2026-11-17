import Base
import ../../packages/qt612/qt.bend as Qt

def title() -> Qt.Property:
  Qt.Property.define("title", Qt.string())

def greeting() -> Qt.Method:
  Qt.Method.define("greet", [Qt.string()], Qt.string())

def Card() -> Qt.ObjectType:
  Qt.ObjectType.withMethods(Qt.QObject.define("ExampleCard", [title()]), [greeting()])

def Settings() -> Qt.ObjectType:
  Qt.QObject.define("ExampleSettings", [title()])

def greet(state: Unit, name: String) -> Qt.Action(String):
  Qt.Action.pure(String, "Hello " ++ name)

def make_card(state: Unit, engine: Qt.QQmlEngine) -> Qt.Action(Qt.ObjectType.Instance(Card())):
  do Qt.Action<Qt.ObjectType.Instance(Card())>:
    +card: Qt.ObjectType.Instance(Card()) <- Qt.ObjectType.new(~Card())
    Qt.ObjectType.set(~Card(), ~title(), card, "Bend")
    Qt.ObjectType.handle(~Card(), ~greeting(), ~Unit, ~greet, card, Unit{})
    return card

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def load() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    engine: Qt.QQmlEngine <- Qt.QQmlEngine.new()
    +component: Qt.QQmlComponent <- Qt.QQmlComponent.new__QQmlEngine_QObject(engine, Qt.QObject{0})
    source: Qt.QByteArray <- Qt.QByteArray.fromUtf8("import QtQml\nimport Bend.Example 1.0\nQtObject { property string result: Card.greet(Card.title) }")
    url: Qt.QUrl <- Qt.QUrl.new()
    Qt.QQmlComponent.setData(component, source, url)
    ready: Bool <- Qt.QQmlComponent.isReady(component)
    require(ready, "QML singleton component failed to load")
    root: Qt.QObject <- Qt.QQmlComponent.create__QQmlContext(component, Qt.QQmlContext{0})
    result: Qt.QVariant <- Qt.QQmlProperty.read__QObject_String(root, "result")
    text: String <- Qt.QVariant.toString(result)
    require(String.eq(text, "Hello Bend"), "Typed singleton method failed")

def load_settings(uri: String, expected: String) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    engine: Qt.QQmlEngine <- Qt.QQmlEngine.new()
    +component: Qt.QQmlComponent <- Qt.QQmlComponent.new__QQmlEngine_QObject(engine, Qt.QObject{0})
    source: Qt.QByteArray <- Qt.QByteArray.fromUtf8("import QtQml\nimport " ++ uri ++ " 1.0\nQtObject { property string result: Settings.title }")
    url: Qt.QUrl <- Qt.QUrl.new()
    Qt.QQmlComponent.setData(component, source, url)
    root: Qt.QObject <- Qt.QQmlComponent.create__QQmlContext(component, Qt.QQmlContext{0})
    result: Qt.QVariant <- Qt.QQmlProperty.read__QObject_String(root, "result")
    text: String <- Qt.QVariant.toString(result)
    require(String.eq(text, expected), "Instance/default singleton property failed")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    registration: Qt.Qml.Registration(Card()) <- Qt.Qml.registerSingletonFactory(~Card(), ~Unit, ~make_card, "Bend.Example", 1, 0, "Card", Unit{})
    Qt.scoped(Unit, load())
    Qt.scoped(Unit, load())
    +settings: Qt.ObjectType.Instance(Settings()) <- Qt.ObjectType.new(~Settings())
    Qt.ObjectType.set(~Settings(), ~title(), settings, "existing")
    instance: Qt.Qml.Registration(Settings()) <- Qt.Qml.registerSingletonInstance(~Settings(), "Bend.Instance", 1, 0, "Settings", settings)
    Qt.scoped(Unit, load_settings("Bend.Instance", "existing"))
    defaults: Qt.Qml.Registration(Settings()) <- Qt.Qml.registerSingleton(~Settings(), "Bend.Default", 1, 0, "Settings")
    Qt.scoped(Unit, load_settings("Bend.Default", ""))
    Qt.scoped(Unit, load_settings("Bend.Default", ""))
    Qt.Action.lift(Unit, IO.print("QT612_QML_TYPES_OK named_methods=1 singleton_factory=1 engines=2"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
