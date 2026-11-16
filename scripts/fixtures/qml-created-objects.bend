import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def title() -> Qt.Property:
  Qt.Property.define("title", Qt.string())

def label() -> Qt.Property:
  Qt.Property.define("label", Qt.string())

def detail() -> Qt.Property:
  Qt.Property.define("detail", Qt.string())

def Attached() -> Qt.ObjectType:
  Qt.QObject.define("BendCreatedAttached", [label()])

def Extension() -> Qt.ObjectType:
  Qt.QObject.define("BendCreatedExtension", [detail()])

def describe() -> Qt.Method:
  Qt.Method.define("describe", [Qt.string()], Qt.string())

def Card() -> Qt.ObjectType:
  Qt.ObjectType.withExtension(Qt.ObjectType.withAttached(
    Qt.ObjectType.withMethods(Qt.QQuickItem.define("BendCreatedCard", [title()]), [describe()]),
    Attached()), Extension())

def describe_card(self: Qt.QObject, suffix: String) -> Qt.Action(String):
  do Qt.Action<String>:
    value: String <- Qt.Property.get(~title(), self)
    return value ++ suffix

def initialize(state: Unit, card: Qt.ObjectType.Instance(Card())) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +self: Qt.QObject = Qt.ObjectType.as_QObject(~Card(), card)
    Qt.Property.set(~title(), self, "initialized")
    Qt.Method.handle(~describe(), ~Qt.QObject, ~describe_card, self, self)

def failing_initializer(state: Unit, card: Qt.ObjectType.Instance(Card())) -> Qt.Action(Unit):
  Qt.Action.fail(Unit, 61, "Expected initializer failure")

def initializer_error(result: Result<&1, &1, U32 & String, Qt.QObject>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 61), "QML lost the initializer's original failure")
    case Done{object}: Qt.Action.fail(Unit, 1, "QML ignored the initializer failure")

def failing_creation() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +registration: Qt.Qml.Registration(Card()) <- Qt.Qml.registerType(~Card(), "BendFailingCreated", 1, 0, "Card")
    Qt.Qml.handleCreate(~Card(), ~Unit, ~failing_initializer, registration, Unit{})
    +engine: Qt.QQmlEngine <- Qt.QQmlEngine.new()
    +component: Qt.QQmlComponent <- Qt.QQmlComponent.new__QQmlEngine_QObject(engine, Qt.QObject{0})
    source: Qt.QByteArray <- Qt.QByteArray.fromUtf8("import BendFailingCreated 1.0\nCard {}")
    url: Qt.QUrl <- Qt.QUrl.new()
    Qt.QQmlComponent.setData(component, source, url)
    result: Result<&1, &1, U32 & String, Qt.QObject> <- Qt.Action.attempt(Qt.QObject, Qt.QQmlComponent.create__QQmlContext(component, Qt.QQmlContext{0}))
    initializer_error(result)

def attached(state: Unit, target: Qt.QObject) -> Qt.Action(Qt.ObjectType.Instance(Attached())):
  do Qt.Action<Qt.ObjectType.Instance(Attached())>:
    +value: Qt.ObjectType.Instance(Attached()) <- Qt.ObjectType.new(~Attached())
    Qt.ObjectType.set(~Attached(), ~label(), value, "attached")
    return value

def extended(state: Unit, target: Qt.QObject) -> Qt.Action(Qt.ObjectType.Instance(Extension())):
  do Qt.Action<Qt.ObjectType.Instance(Extension())>:
    +value: Qt.ObjectType.Instance(Extension()) <- Qt.ObjectType.new(~Extension())
    Qt.ObjectType.set(~Extension(), ~detail(), value, "extended")
    return value

def read(self: Qt.QObject, +name: String, expected: String) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    value: Qt.QVariant <- Qt.QQmlProperty.read__QObject_String(self, name)
    +text: String <- Qt.QVariant.toString(value)
    require(String.eq(text, expected), "Wrong QML property " ++ name ++ ": " ++ text)

def closures(remaining: Nat, +index: U32, +target: Qt.QObject) -> Qt.Action(Unit):
  match remaining:
    case 0n: Qt.Action.pure(Unit, Unit{})
    case 1n+rest:
      do Qt.Action<Unit>:
        +registration: Qt.Qml.Registration(Card()) <- Qt.Qml.registerType(~Card(), "BendManyFactories", 1, 0, "Provider" ++ U32.show(index))
        +first: Qt.ObjectType.Instance(Attached()) <- Qt.Qml.attached(~Card(), registration, target)
        again: Qt.ObjectType.Instance(Attached()) <- Qt.Qml.attached(~Card(), registration, target)
        require(U32.is_eq(Qt.ObjectType.word(~Attached(), first), Qt.ObjectType.word(~Attached(), again)), "Attached lookup did not use Qt's cache")
        Qt.ObjectType.set(~Attached(), ~label(), first, U32.show(index))
        closures(rest, U32.add(index, 1), target)
        text: String <- Qt.ObjectType.get(~Attached(), ~label(), first)
        require(String.eq(text, U32.show(index)), "Different registrations shared an attached factory identity")

def objects() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +registration: Qt.Qml.Registration(Card()) <- Qt.Qml.registerType(~Card(), "BendCreated", 1, 0, "Card")
    Qt.Qml.handleCreate(~Card(), ~Unit, ~initialize, registration, Unit{})
    Qt.Qml.handleAttached(~Card(), ~Unit, ~attached, registration, Unit{})
    Qt.Qml.handleExtension(~Card(), ~Unit, ~extended, registration, Unit{})
    +engine: Qt.QQmlEngine <- Qt.QQmlEngine.new()
    +component: Qt.QQmlComponent <- Qt.QQmlComponent.new__QQmlEngine_QObject(engine, Qt.QObject{0})
    url: Qt.QUrl <- Qt.QUrl.new()
    source: Qt.QByteArray <- Qt.QByteArray.fromUtf8(
      "import QtQuick\nimport BendCreated 1.0\nCard { id: root; width: 42; property string initial: title; property string result: { title; return describe('!'); } property string attachedValue: Card.label; property string extensionValue: detail; property list<Card> cards: [Card { title: 'child' }]; property string childValue: cards[0].title; property string listSize: String(cards.length); Card.label: 'qml-attached'; detail: 'qml-extended'; }")
    Qt.QQmlComponent.setData(component, source, url)
    ready: Bool <- Qt.QQmlComponent.isReady(component)
    require(ready, "QML-creatable class did not compile")
    +root: Qt.QObject <- Qt.QQmlComponent.create__QQmlContext(component, Qt.QQmlContext{0})
    read(root, "initial", "initialized")
    read(root, "result", "initialized!")
    read(root, "attachedValue", "qml-attached")
    read(root, "extensionValue", "qml-extended")
    +card: Qt.ObjectType.Instance(Card()) <- Qt.ObjectType.cast(~Card(), root)
    related: Qt.ObjectType.Instance(Attached()) <- Qt.Qml.attached(~Card(), registration, root)
    text: String <- Qt.ObjectType.get(~Attached(), ~label(), related)
    require(String.eq(text, "qml-attached"), "Bend and QML got different attached objects")
    extension: Qt.ObjectType.Instance(Extension()) <- Qt.Qml.extension(~Card(), registration, card)
    detail: String <- Qt.ObjectType.get(~Extension(), ~detail(), extension)
    require(String.eq(detail, "qml-extended"), "Bend and QML got different extension objects")
    Qt.Property.set(~title(), root, "updated")
    read(root, "initial", "updated")
    read(root, "result", "updated!")
    read(root, "listSize", "1")
    read(root, "childValue", "child")

def factory_checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +target: Qt.QObject <- Qt.QObject.new()
    closures(150n, 0, target)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, objects())
    Qt.scoped(Unit, factory_checks())
    Qt.scoped(Unit, failing_creation())
    live: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(live, 0), "QML-created objects leaked")
    Qt.Action.lift(Unit, IO.print("QT612_QML_CREATED_OBJECTS_OK constructors=1 initializers=1 native_base=1 methods=1 attached=1 extension=1 typed_lists=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
