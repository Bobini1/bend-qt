import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def number() -> Qt.Property:
  Qt.Property.withBindable(Qt.Property.define("number", Qt.int32()), True{})

def readonly_number() -> Qt.Property:
  Qt.Property.withBindable(Qt.Property.readOnly("readonlyNumber", Qt.int32()), True{})

def text() -> Qt.Property:
  Qt.Property.withBindable(Qt.Property.define("text", Qt.string()), True{})

def values() -> Qt.Property:
  Qt.Property.withBindable(Qt.Property.define("values", Qt.variantList()), True{})

def Target() -> Qt.ObjectType:
  Qt.QObject.define("BindingTarget", [])

def peer() -> Qt.Property:
  Qt.Property.withBindable(Qt.Property.define("peer", Qt.ObjectType.arg(~Target())), True{})

def Model() -> Qt.ObjectType:
  Qt.QObject.define("BindingModel", [number(), readonly_number(), text(), values(), peer()])

def compute(self: Qt.QObject) -> Qt.Action(Qt.Int32):
  do Qt.Action<Qt.Int32>:
    value: Qt.Int32 <- Qt.Property.get(~number(), self)
    return Qt.Int32{U32.add(U32.mul(Qt.Int32.word(value), 3), 1)}

def expected_failure(result: Result<&1, &1, U32 & String, Unit>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 73), message)
    case Done{value}: Qt.Action.fail(Unit, 1, "A failed binding evaluator unexpectedly succeeded")

def refused(state: Unit) -> Qt.Action(Qt.Int32):
  Qt.Action.fail(Qt.Int32, 73, "Expected computed-binding failure")

def expected_readonly(result: Result<&1, &1, U32 & String, Unit>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 1), message)
    case Done{value}: Qt.Action.fail(Unit, 1, "A readonly computed property accepted a public write")

def qml(+source: Qt.QObject, +target: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +engine: Qt.QQmlEngine <- Qt.QQmlEngine.new()
    context: Qt.QQmlContext <- Qt.QQmlEngine.rootContext(engine)
    Qt.QQmlContext.setContextProperty__String_QObject(context, "source", source)
    context: Qt.QQmlContext <- Qt.QQmlEngine.rootContext(engine)
    Qt.QQmlContext.setContextProperty__String_QObject(context, "target", target)
    +component: Qt.QQmlComponent <- Qt.QQmlComponent.new__QQmlEngine_QObject(engine, Qt.QObject{0})
    data: Qt.QByteArray <- Qt.QByteArray.fromUtf8("import QtQml\nQtObject { property int observed: target.number; property int readonlyObserved: target.readonlyNumber; property string label: target.text; Component.onCompleted: { target.number = Qt.binding(function() { return source.number * 2; }) } }")
    url: Qt.QUrl <- Qt.QUrl.new()
    Qt.QQmlComponent.setData(component, data, url)
    ready: Bool <- Qt.QQmlComponent.isReady(component)
    require(ready, "QML bindable-property component did not compile")
    +root: Qt.QObject <- Qt.QQmlComponent.create__QQmlContext(component, Qt.QQmlContext{0})
    Qt.Property.set(~number(), source, Qt.Int32{11})
    +actual: Qt.Int32 <- Qt.Property.get(~number(), target)
    require(U32.is_eq(Qt.Int32.word(actual), 22), "QML binding did not update the native bindable: " ++ U32.show(Qt.Int32.word(actual)))
    observed: Qt.QVariant <- Qt.QQmlProperty.read__QObject_String(root, "observed")
    number: Qt.Int32 <- Qt.QVariant.toInt32(observed)
    require(U32.is_eq(Qt.Int32.word(number), 22), "QML consumer did not observe a bindable update")
    observed: Qt.QVariant <- Qt.QQmlProperty.read__QObject_String(root, "readonlyObserved")
    number: Qt.Int32 <- Qt.QVariant.toInt32(observed)
    require(U32.is_eq(Qt.Int32.word(number), 34), "QML did not observe a readonly computed binding")
    Qt.Property.set(~text(), source, "QML")
    observed: Qt.QVariant <- Qt.QQmlProperty.read__QObject_String(root, "label")
    text: String <- Qt.QVariant.toString(observed)
    require(String.eq(text, "QML"), "QML did not observe a bound string")

def objects() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +first: Qt.ObjectType.Instance(Model()) <- Qt.ObjectType.new(~Model())
    +second: Qt.ObjectType.Instance(Model()) <- Qt.ObjectType.new(~Model())
    +source: Qt.QObject = Qt.ObjectType.as_QObject(~Model(), first)
    +target: Qt.QObject = Qt.ObjectType.as_QObject(~Model(), second)
    Qt.Property.set(~number(), source, Qt.Int32{3})
    Qt.ObjectType.bind(~Model(), ~number(), ~Model(), ~number(), second, first)
    bound: Bool <- Qt.ObjectType.hasBinding(~Model(), ~number(), second)
    actual: Qt.Int32 <- Qt.Property.get(~number(), target)
    require(bound && U32.is_eq(Qt.Int32.word(actual), 3), "Native property binding was not installed")
    Qt.Property.set(~number(), source, Qt.Int32{8})
    actual: Qt.Int32 <- Qt.Property.get(~number(), target)
    require(U32.is_eq(Qt.Int32.word(actual), 8), "Bound property did not update")
    Qt.ObjectType.unbind(~Model(), ~number(), second)
    bound: Bool <- Qt.Property.hasBinding(~number(), target)
    Qt.Property.set(~number(), source, Qt.Int32{9})
    actual: Qt.Int32 <- Qt.Property.get(~number(), target)
    require(Bool.not(bound) && U32.is_eq(Qt.Int32.word(actual), 8), "Unbinding changed the stored value or left a binding")
    Qt.ObjectType.handleBinding(~Model(), ~number(), ~Qt.QObject, ~compute, second, source)
    actual: Qt.Int32 <- Qt.Property.get(~number(), target)
    require(U32.is_eq(Qt.Int32.word(actual), 28), "Computed binding did not evaluate")
    Qt.Property.set(~number(), source, Qt.Int32{4})
    actual: Qt.Int32 <- Qt.Property.get(~number(), target)
    require(U32.is_eq(Qt.Int32.word(actual), 13), "Computed binding did not track Bend property reads")
    Qt.Property.set(~number(), target, Qt.Int32{13})
    bound: Bool <- Qt.Property.hasBinding(~number(), target)
    require(Bool.not(bound), "An equal manual write did not remove the binding")
    Qt.Property.bind(~readonly_number(), ~number(), target, source)
    actual: Qt.Int32 <- Qt.Property.get(~readonly_number(), target)
    require(U32.is_eq(Qt.Int32.word(actual), 4), "Explicit Bend binding could not initialize a readonly backing property")
    Qt.Property.handleBinding(~readonly_number(), ~Qt.QObject, ~compute, target, source)
    actual: Qt.Int32 <- Qt.Property.get(~readonly_number(), target)
    require(U32.is_eq(Qt.Int32.word(actual), 13), "Readonly computed binding did not evaluate")
    denied: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.Property.set(~readonly_number(), target, Qt.Int32{1}))
    expected_readonly(denied)
    Qt.Property.bind(~text(), ~text(), target, source)
    Qt.Property.set(~text(), source, "bound")
    text: String <- Qt.Property.get(~text(), target)
    require(String.eq(text, "bound"), "String binding did not update")
    Qt.Property.bind(~values(), ~values(), target, source)
    one: Qt.QVariant <- Qt.QVariant.fromUInt32(1)
    two: Qt.QVariant <- Qt.QVariant.fromUInt32(2)
    Qt.Property.set(~values(), source, [one, two])
    values: List<&2, Qt.QVariant> <- Qt.Property.get(~values(), target)
    require(U32.is_eq(U32.from_nat(List.length(&2, Qt.QVariant, values)), 2), "Container binding did not update")
    Qt.Property.bind(~peer(), ~peer(), target, source)
    +object: Qt.ObjectType.Instance(Target()) <- Qt.ObjectType.new(~Target())
    Qt.Property.set(~peer(), source, object)
    result: Qt.ObjectType.Instance(Target()) <- Qt.Property.get(~peer(), target)
    require(U32.is_eq(Qt.ObjectType.word(~Target(), object), Qt.ObjectType.word(~Target(), result)), "Runtime QObject pointer binding lost its concrete type")
    +meta: Qt.QMetaObject <- Qt.QObject.metaObject(source)
    index: Qt.Int32 <- Qt.QMetaObject.indexOfProperty(meta, "number")
    property: Qt.QMetaProperty <- Qt.QMetaObject.property(meta, index)
    bindable: Bool <- Qt.QMetaProperty.isBindable(property)
    require(bindable, "Native BINDABLE metadata is missing")
    index: Qt.Int32 <- Qt.QMetaObject.indexOfProperty(meta, "readonlyNumber")
    +property: Qt.QMetaProperty <- Qt.QMetaObject.property(meta, index)
    writable: Bool <- Qt.QMetaProperty.isWritable(property)
    bindable: Bool <- Qt.QMetaProperty.isBindable(property)
    require(bindable && Bool.not(writable), "Readonly computed property's native metadata changed")
    refused: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.Property.handleBinding(~number(), ~Unit, ~refused, target, Unit{}))
    expected_failure(refused)
    Qt.Property.unbind(~number(), target)
    Qt.scoped(Unit, qml(source, target))

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, objects())
    count: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(count, 0), "Bindable property values or handlers leaked")
    Qt.Action.lift(Unit, IO.print("QT612_PROPERTY_BINDINGS_OK native=1 computed=1 qml=1 concrete_types=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
