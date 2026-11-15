import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def title() -> Qt.Property:
  Qt.Property.define("title", Qt.string())

def Notifier() -> Qt.QtObject:
  Qt.QSocketNotifier.define("QmlConstructedNotifier", [title()])

def Other() -> Qt.QtObject:
  Qt.QObject.define("QmlConstructorHelper", [])

def construct(label: String) -> Qt.Action(Qt.QtObject.Instance(Notifier())):
  do Qt.Action<Qt.QtObject.Instance(Notifier())>:
    helper: Qt.QtObject.Instance(Other()) <- Qt.QObject.newAs(~Other())
    +value: Qt.QtObject.Instance(Notifier()) <- Qt.QSocketNotifier.newAs__QSocketNotifier_Type_QObject(~Notifier(), Qt.QSocketNotifier.Type.Read(), Qt.QObject{0})
    Qt.Property.set(~title(), Qt.QtObject.as_QObject(~Notifier(), value), label)
    return value

def create_shared(state: Unit, engine: Qt.QQmlEngine) -> Qt.Action(Qt.QtObject.Instance(Notifier())):
  construct("singleton")

def construct_with_singleton(engine: Qt.QQmlEngine) -> Qt.Action(Qt.QtObject.Instance(Notifier())):
  do Qt.Action<Qt.QtObject.Instance(Notifier())>:
    +component: Qt.QQmlComponent <- Qt.QQmlComponent.new__QQmlEngine_QObject(engine, Qt.QObject{0})
    source: Qt.QByteArray <- Qt.QByteArray.fromUtf8("import QtQml\nimport Bend.NativeConstructors 1.0\nQtObject { property string text: Shared.title }")
    url: Qt.QUrl <- Qt.QUrl.new()
    Qt.QQmlComponent.setData(component, source, url)
    ready: Bool <- Qt.QQmlComponent.isReady(component)
    require(ready, "Nested singleton QML did not compile")
    root: Qt.QObject <- Qt.QQmlComponent.create__QQmlContext(component, Qt.QQmlContext{0})
    value: Qt.QVariant <- Qt.QQmlProperty.read__QObject_String(root, "text")
    text: String <- Qt.QVariant.toString(value)
    require(String.eq(text, "singleton"), "A singleton factory consumed another type's pending root placement")
    +value: Qt.QtObject.Instance(Notifier()) <- construct("outer")
    return value

def initialize(state: Unit, value: Qt.QtObject.Instance(Notifier())) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +self: Qt.QObject = Qt.QtObject.as_QObject(~Notifier(), value)
    text: String <- Qt.Property.get(~title(), self)
    Qt.Property.set(~title(), self, "initialized:" ++ text)

def failed_before(state: Unit) -> Qt.Action(Qt.QtObject.Instance(Notifier())):
  Qt.Action.fail(Qt.QtObject.Instance(Notifier()), 71, "Expected failure before placement")

def failed_after(state: Unit) -> Qt.Action(Qt.QtObject.Instance(Notifier())):
  do Qt.Action<Qt.QtObject.Instance(Notifier())>:
    value: Qt.QtObject.Instance(Notifier()) <- construct("before-failure")
    Qt.Action.fail(Qt.QtObject.Instance(Notifier()), 72, "Expected failure after placement")

def wrong_heap(state: Unit) -> Qt.Action(Qt.QtObject.Instance(Notifier())):
  Qt.QtObject.newWith(~Notifier(), Qt.QSocketNotifier.newOverride__QSocketNotifier_Type_QObject(Qt.QSocketNotifier.Type.Read(), Qt.QObject{0}))

def selected(which: Bool, first: Qt.QtObject.Instance(Notifier()), second: Qt.QtObject.Instance(Notifier())) -> Qt.QtObject.Instance(Notifier()):
  match which:
    case True{}: first
    case False{}: second

def extra_constructor(state: Bool) -> Qt.Action(Qt.QtObject.Instance(Notifier())):
  do Qt.Action<Qt.QtObject.Instance(Notifier())>:
    first: Qt.QtObject.Instance(Notifier()) <- construct("first")
    second: Qt.QtObject.Instance(Notifier()) <- construct("second")
    return selected(state, first, second)

def expected(result: Result<&1, &1, U32 & String, Qt.QObject>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected QML constructor rejection")

def component(+engine: Qt.QQmlEngine, name: String) -> Qt.Action(Qt.QQmlComponent):
  do Qt.Action<Qt.QQmlComponent>:
    +value: Qt.QQmlComponent <- Qt.QQmlComponent.new__QQmlEngine_QObject(engine, Qt.QObject{0})
    source: Qt.QByteArray <- Qt.QByteArray.fromUtf8("import Bend.NativeConstructors 1.0\n" ++ name ++ " {}")
    url: Qt.QUrl <- Qt.QUrl.new()
    Qt.QQmlComponent.setData(value, source, url)
    ready: Bool <- Qt.QQmlComponent.isReady(value)
    require(ready, "QML constructor fixture did not compile")
    Qt.Action.pure(Qt.QQmlComponent, value)

def accepted(+engine: Qt.QQmlEngine, name: String, expected: String) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    value: Qt.QQmlComponent <- component(engine, name)
    root: Qt.QObject <- Qt.QQmlComponent.create__QQmlContext(value, Qt.QQmlContext{0})
    text: String <- Qt.Property.get(~title(), root)
    require(String.eq(text, expected), "QML did not use constructor state before its initializer")

def rejected(+engine: Qt.QQmlEngine, name: String, code: U32) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    value: Qt.QQmlComponent <- component(engine, name)
    result: Result<&1, &1, U32 & String, Qt.QObject> <- Qt.Action.attempt(Qt.QObject, Qt.QQmlComponent.create__QQmlContext(value, Qt.QQmlContext{0}))
    expected(result, code)

def objects() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +valid: Qt.QObject <- Qt.Qml.registerType(~Notifier(), "Bend.NativeConstructors", 1, 0, "Valid")
    Qt.Qml.handleConstructor(~Notifier(), ~String, ~construct, valid, "runtime")
    Qt.Qml.handleCreate(~Notifier(), ~Unit, ~initialize, valid, Unit{})
    missing: Qt.QObject <- Qt.Qml.registerType(~Notifier(), "Bend.NativeConstructors", 1, 0, "Missing")
    +before: Qt.QObject <- Qt.Qml.registerType(~Notifier(), "Bend.NativeConstructors", 1, 0, "Before")
    Qt.Qml.handleConstructor(~Notifier(), ~Unit, ~failed_before, before, Unit{})
    +after: Qt.QObject <- Qt.Qml.registerType(~Notifier(), "Bend.NativeConstructors", 1, 0, "After")
    Qt.Qml.handleConstructor(~Notifier(), ~Unit, ~failed_after, after, Unit{})
    +heap: Qt.QObject <- Qt.Qml.registerType(~Notifier(), "Bend.NativeConstructors", 1, 0, "Heap")
    Qt.Qml.handleConstructor(~Notifier(), ~Unit, ~wrong_heap, heap, Unit{})
    +extra: Qt.QObject <- Qt.Qml.registerType(~Notifier(), "Bend.NativeConstructors", 1, 0, "Extra")
    Qt.Qml.handleConstructor(~Notifier(), ~Bool, ~extra_constructor, extra, True{})
    +wrong: Qt.QObject <- Qt.Qml.registerType(~Notifier(), "Bend.NativeConstructors", 1, 0, "Wrong")
    Qt.Qml.handleConstructor(~Notifier(), ~Bool, ~extra_constructor, wrong, False{})
    +engine: Qt.QQmlEngine <- Qt.QQmlEngine.new()
    shared: Qt.QObject <- Qt.Qml.registerSingletonFactory(~Notifier(), ~Unit, ~create_shared, "Bend.NativeConstructors", 1, 0, "Shared", Unit{})
    +nested: Qt.QObject <- Qt.Qml.registerType(~Notifier(), "Bend.NativeConstructors", 1, 0, "Nested")
    Qt.Qml.handleConstructor(~Notifier(), ~Qt.QQmlEngine, ~construct_with_singleton, nested, engine)
    accepted(engine, "Valid", "initialized:runtime")
    accepted(engine, "Extra", "first")
    accepted(engine, "Nested", "outer")
    rejected(engine, "Missing", 38)
    rejected(engine, "Before", 71)
    rejected(engine, "After", 72)
    rejected(engine, "Heap", 22)
    rejected(engine, "Wrong", 22)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, objects())
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "QML constructor failures or extra objects leaked")
    Qt.Action.lift(Unit, IO.print("QT612_QML_CONSTRUCTORS_OK runtime_args=1 initializer=1 missing=38 failures=71_72 heap=22 multiple=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
