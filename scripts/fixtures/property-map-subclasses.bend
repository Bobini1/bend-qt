import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expected(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected schema-aware constructor rejection")

def title() -> Qt.Property:
  Qt.Property.define("title", Qt.string())

def number() -> Qt.Property:
  Qt.Property.define("number", Qt.int32())

def Mapped() -> Qt.QtObject:
  Qt.QQmlPropertyMap.define("SchemaAwarePropertyMap", [title()])

def Child() -> Qt.QtObject:
  Qt.QtObject.derive(~Mapped(), "SchemaAwareChildMap", [number()])

def Notifier() -> Qt.QtObject:
  Qt.QSocketNotifier.define("SchemaAwareNotifier", [title()])

def Extended() -> Qt.QtObject:
  Qt.QtObject.withExtension(Qt.QObject.define("SchemaAwareMapExtension", []), Mapped())

def Attached() -> Qt.QtObject:
  Qt.QtObject.withAttached(Qt.QObject.define("SchemaAwareMapAttached", []), Mapped())

def updated(prefix: String, key: String, value: Qt.QVariant) -> Qt.Action(Qt.QVariant):
  do Qt.Action<Qt.QVariant>:
    text: String <- Qt.QVariant.toString(value)
    Qt.QVariant.fromString(prefix ++ text)

def initialize(state: Unit, value: Qt.QtObject.Instance(Mapped())) -> Qt.Action(Unit):
  Qt.Property.set(~title(), Qt.QtObject.as_QObject(~Mapped(), value), "initialized")

def load_component(engine: Qt.QQmlEngine, source: String) -> Qt.Action(Qt.QQmlComponent):
  do Qt.Action<Qt.QQmlComponent>:
    +component: Qt.QQmlComponent <- Qt.QQmlComponent.new__QQmlEngine_QObject(engine, Qt.QObject{0})
    data: Qt.QByteArray <- Qt.QByteArray.fromUtf8(source)
    url: Qt.QUrl <- Qt.QUrl.new()
    Qt.QQmlComponent.setData(component, data, url)
    ready: Bool <- Qt.QQmlComponent.isReady(component)
    require(ready, "Property-map QML did not compile")
    Qt.Action.pure(Qt.QQmlComponent, component)

def qml(+instance: Qt.QtObject.Instance(Mapped())) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +map: Qt.QQmlPropertyMap = Qt.QtObject.asNativeBase(~Mapped(), instance)
    +engine: Qt.QQmlEngine <- Qt.QQmlEngine.new()
    context: Qt.QQmlContext <- Qt.QQmlEngine.rootContext(engine)
    Qt.QQmlContext.setContextProperty__String_QObject(context, "model", Qt.QtObject.as_QObject(~Mapped(), instance))
    +component: Qt.QQmlComponent <- load_component(engine, "import QtQml\nQtObject { property string result: model.title + '|' + model.item; Component.onCompleted: model.item = 'qml' }")
    +root: Qt.QObject <- Qt.QQmlComponent.create__QQmlContext(component, Qt.QQmlContext{0})
    value: Qt.QVariant <- Qt.QQmlProperty.read__QObject_String(root, "result")
    text: String <- Qt.QVariant.toString(value)
    require(String.eq(text, "Bend|updated:qml"), "Static properties, dynamic map data or updateValue override were lost")
    Qt.Property.set(~title(), Qt.QtObject.as_QObject(~Mapped(), instance), "changed")
    value: Qt.QVariant <- Qt.QQmlProperty.read__QObject_String(root, "result")
    text: String <- Qt.QVariant.toString(value)
    require(String.eq(text, "changed|updated:qml"), "A declared map property did not notify QML")
    next: Qt.QVariant <- Qt.QVariant.fromString("native")
    Qt.QQmlPropertyMap.insert__String_QVariant(map, "item", next)
    value: Qt.QVariant <- Qt.QQmlProperty.read__QObject_String(root, "result")
    text: String <- Qt.QVariant.toString(value)
    require(String.eq(text, "changed|native"), "Native map insertion did not notify QML")

def objects() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +instance: Qt.QtObject.Instance(Mapped()) <- Qt.QtObject.new(~Mapped())
    +map: Qt.QQmlPropertyMap = Qt.QtObject.asNativeBase(~Mapped(), instance)
    Qt.QQmlPropertyMap.Virtual.updateValue.handle(~String, ~updated, map, "updated:")
    Qt.Property.set(~title(), Qt.QtObject.as_QObject(~Mapped(), instance), "Bend")
    value: Qt.QVariant <- Qt.QVariant.fromString("initial")
    Qt.QQmlPropertyMap.insert__String_QVariant(map, "item", value)
    Qt.scoped(Unit, qml(instance))
    +parent: Qt.QObject <- Qt.QObject.new()
    +parented: Qt.QtObject.Instance(Mapped()) <- Qt.QQmlPropertyMap.newAs__QObject(~Mapped(), parent)
    object: Qt.QObject <- Qt.QObject.parent(Qt.QtObject.as_QObject(~Mapped(), parented))
    require(U32.is_eq(Qt.QObject.word(object), Qt.QObject.word(parent)), "Schema-aware map constructor lost its native argument")
    +notifier: Qt.QtObject.Instance(Notifier()) <- Qt.QSocketNotifier.newAs__QSocketNotifier_Type_QObject(~Notifier(), Qt.QSocketNotifier.Type.Read(), parent)
    Qt.Property.set(~title(), Qt.QtObject.as_QObject(~Notifier(), notifier), "constructed")
    text: String <- Qt.Property.get(~title(), Qt.QtObject.as_QObject(~Notifier(), notifier))
    require(String.eq(text, "constructed"), "Nondefault schema-aware constructor failed")
    +child: Qt.QtObject.Instance(Child()) <- Qt.QtObject.new(~Child())
    +self: Qt.QObject = Qt.QtObject.as_QObject(~Child(), child)
    Qt.Property.set(~title(), self, "inherited")
    Qt.Property.set(~number(), self, Qt.Int32{42})
    text: String <- Qt.Property.get(~title(), self)
    number: Qt.Int32 <- Qt.Property.get(~number(), self)
    require(String.eq(text, "inherited") && U32.is_eq(Qt.Int32.word(number), 42), "Property-map schema inheritance failed")
    refused: Result<&1, &1, U32 & String, Qt.QtObject.Instance(Mapped())> <- Qt.Action.attempt(Qt.QtObject.Instance(Mapped()), Qt.QObject.newAs(~Mapped()))
    expected(Qt.QtObject.Instance(Mapped()), refused, 22)
    refused: Result<&1, &1, U32 & String, Qt.QtObject.Instance(Mapped())> <- Qt.Action.attempt(Qt.QtObject.Instance(Mapped()),
      Qt.QtObject.newWith(~Mapped(), Qt.QQmlPropertyMap.newOverride()))
    expected(Qt.QtObject.Instance(Mapped()), refused, 95)

def registered() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +registration: Qt.QObject <- Qt.Qml.registerType(~Mapped(), "Bend.PropertyMapSubclasses", 1, 0, "Mapped")
    Qt.Qml.handleCreate(~Mapped(), ~Unit, ~initialize, registration, Unit{})
    extended: Result<&1, &1, U32 & String, Qt.QObject> <- Qt.Action.attempt(Qt.QObject,
      Qt.Qml.registerType(~Extended(), "Bend.PropertyMapSubclasses", 1, 0, "Extended"))
    expected(Qt.QObject, extended, 95)
    +attached: Qt.QObject <- Qt.Qml.registerType(~Attached(), "Bend.PropertyMapSubclasses", 1, 0, "Attached")
    +engine: Qt.QQmlEngine <- Qt.QQmlEngine.new()
    +component: Qt.QQmlComponent <- load_component(engine, "import Bend.PropertyMapSubclasses 1.0\nMapped { title: 'qml-created' }")
    +root: Qt.QObject <- Qt.QQmlComponent.create__QQmlContext(component, Qt.QQmlContext{0})
    text: String <- Qt.Property.get(~title(), root)
    require(String.eq(text, "qml-created"), "QML placement construction lost the map schema")
    +component: Qt.QQmlComponent <- load_component(engine, "import Bend.PropertyMapSubclasses 1.0\nAttached { Attached.title: 'attached-map' }")
    +root: Qt.QObject <- Qt.QQmlComponent.create__QQmlContext(component, Qt.QQmlContext{0})
    value: Qt.QtObject.Instance(Mapped()) <- Qt.Qml.attached(~Attached(), attached, root)
    text: String <- Qt.Property.get(~title(), Qt.QtObject.as_QObject(~Mapped(), value))
    require(String.eq(text, "attached-map"), "An attached property map lost its schema")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, objects())
    Qt.scoped(Unit, registered())
    live: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(live, 0), "Schema-aware property-map constructors leaked")
    Qt.Action.lift(Unit, IO.print("QT612_PROPERTY_MAP_SUBCLASSES_OK default=1 newAs=1 qml=1 dynamic=1 virtual=1 inheritance=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
