import Base
import ../../packages/qt612/qt.bend as Qt

def title() -> Qt.Property:
  Qt.Property.define("title", Qt.string())

def label() -> Qt.Property:
  Qt.Property.define("label", Qt.string())

def detail() -> Qt.Property:
  Qt.Property.define("detail", Qt.string())

def Attached() -> Qt.ObjectType:
  Qt.QObject.define("ExampleCardAttached", [label()])

def Extension() -> Qt.ObjectType:
  Qt.QObject.define("ExampleCardExtension", [detail()])

def Card() -> Qt.ObjectType:
  Qt.ObjectType.withExtension(Qt.ObjectType.withAttached(
    Qt.QObject.define("ExampleCreatableCard", [title()]),
    Attached()), Extension())

def initialize(state: Unit, card: Qt.ObjectType.Instance(Card())) -> Qt.Action(Unit):
  Qt.ObjectType.set(~Card(), ~title(), card, "Initialized in Bend")

def make_attached(state: Unit, target: Qt.QObject) -> Qt.Action(Qt.ObjectType.Instance(Attached())):
  do Qt.Action<Qt.ObjectType.Instance(Attached())>:
    +value: Qt.ObjectType.Instance(Attached()) <- Qt.ObjectType.new(~Attached())
    Qt.ObjectType.set(~Attached(), ~label(), value, "Attached in Bend")
    return value

def make_extension(state: Unit, target: Qt.QObject) -> Qt.Action(Qt.ObjectType.Instance(Extension())):
  do Qt.Action<Qt.ObjectType.Instance(Extension())>:
    +value: Qt.ObjectType.Instance(Extension()) <- Qt.ObjectType.new(~Extension())
    Qt.ObjectType.set(~Extension(), ~detail(), value, "Extended in Bend")
    return value

def verify(ok: Bool) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.lift(Unit, IO.print("QT612_QML_CREATABLE_OK"))
    case False{}: Qt.Action.fail(Unit, 1, "QML construction or attached/extension factory failed")

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +registration: Qt.Qml.Registration(Card()) <- Qt.Qml.registerType(~Card(), "Bend.Creatable", 1, 0, "Card")
    Qt.Qml.handleCreate(~Card(), ~Unit, ~initialize, registration, Unit{})
    Qt.Qml.handleAttached(~Card(), ~Unit, ~make_attached, registration, Unit{})
    Qt.Qml.handleExtension(~Card(), ~Unit, ~make_extension, registration, Unit{})
    +engine: Qt.QQmlEngine <- Qt.QQmlEngine.new()
    +component: Qt.QQmlComponent <- Qt.QQmlComponent.new__QQmlEngine_QObject(engine, Qt.QObject{0})
    source: Qt.QByteArray <- Qt.QByteArray.fromUtf8(
      "import Bend.Creatable 1.0\nCard { property string summary: title + ' / ' + Card.label + ' / ' + detail; Card.label: 'Attached in QML' }")
    url: Qt.QUrl <- Qt.QUrl.new()
    Qt.QQmlComponent.setData(component, source, url)
    root: Qt.QObject <- Qt.QQmlComponent.create__QQmlContext(component, Qt.QQmlContext{0})
    summary: Qt.QVariant <- Qt.QQmlProperty.read__QObject_String(root, "summary")
    +text: String <- Qt.QVariant.toString(summary)
    Qt.Action.lift(Unit, IO.print(text))
    verify(String.eq(text, "Initialized in Bend / Attached in QML / Extended in Bend"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
