import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expected(-A: Type, result: Result<&1, &1, U32 & String, A>, code: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(+actual, message)}: require(U32.is_eq(actual, code), "Wrong value error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Invalid value operation succeeded")

def tick() -> Qt.Property:
  Qt.Property.define("tick", Qt.int64())

def text() -> Qt.Property:
  Qt.Property.define("text", Qt.string())

def Time() -> Qt.ValueType:
  Qt.ValueType.define("BendAuthoredTime", [tick(), text()])

def stamp() -> Qt.Property:
  Qt.Property.define("stamp", Qt.value(~Time()))

def entries() -> Qt.Property:
  Qt.Property.define("entries", Qt.list(Qt.value(~Time())))

def Holder() -> Qt.ObjectType:
  Qt.QObject.define("BendValueHolder", [stamp(), entries()])

def list_values(values: List<&2, Qt.ValueType.Instance(Time())>, expected: String) -> Qt.Action(Unit):
  match values:
    case first <> Nil{}:
      do Qt.Action<Unit>:
        found: String <- Qt.ValueType.get(~Time(), ~text(), first)
        require(String.eq(found, expected), "Typed value list changed")
    case _: Qt.Action.fail(Unit, 1, "Typed value list has wrong length")

def values() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +first: Qt.ValueType.Instance(Time()) <- Qt.ValueType.make(~Time(), Qt.Int64{5, 2097152}, "bend")
    +copy: Qt.ValueType.Instance(Time()) <- Qt.ValueType.updated(~Time(), ~text(), first, "copy")
    original: String <- Qt.ValueType.get(~Time(), ~text(), first)
    updated: String <- Qt.ValueType.get(~Time(), ~text(), copy)
    require(String.eq(original, "bend") && String.eq(updated, "copy"), "Values did not copy independently")
    +wide: Qt.Int64 <- Qt.ValueType.get(~Time(), ~tick(), copy)
    require(U32.is_eq(Qt.Int64.lo(wide), 5) && U32.is_eq(Qt.Int64.hi(wide), 2097152), "Value narrowed a 64-bit field")
    +variant: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.value(~Time()), first)
    restored: Qt.ValueType.Instance(Time()) <- Qt.QVariant.toValue(~Qt.value(~Time()), variant)
    found: String <- Qt.ValueType.get(~Time(), ~text(), restored)
    require(String.eq(found, "bend"), "QVariant lost the value schema")
    +list: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.list(Qt.value(~Time())), [first])
    copied: List<&2, Qt.ValueType.Instance(Time())> <- Qt.QVariant.toValue(~Qt.list(Qt.value(~Time())), list)
    list_values(copied, "bend")
    +holder: Qt.ObjectType.Instance(Holder()) <- Qt.ObjectType.new(~Holder())
    +object: Qt.QObject = Qt.ObjectType.as_QObject(~Holder(), holder)
    Qt.Property.set(~stamp(), object, first)
    Qt.Property.set(~entries(), object, [copy])
    held: Qt.ValueType.Instance(Time()) <- Qt.Property.get(~stamp(), object)
    found: String <- Qt.ValueType.get(~Time(), ~text(), held)
    require(String.eq(found, "bend"), "QObject value property lost its fields")
    list: List<&2, Qt.ValueType.Instance(Time())> <- Qt.Property.get(~entries(), object)
    list_values(list, "copy")

def changed() -> Qt.Signal:
  Qt.Signal.define("changed", [Qt.value(~Time())])

def received(state: Qt.QObject, value: Qt.ValueType.Instance(Time())) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    found: String <- Qt.ValueType.get(~Time(), ~text(), value)
    Qt.QObject.setObjectName(state, found)

type Payload is Data:
  Payload{number: U32, text: String}

def owner() -> Qt.Property:
  Qt.Property.define("owner", Qt.QObject.arg())

def payload() -> Qt.Property:
  Qt.Property.define("payload", Qt.arg(~Payload))

def Envelope() -> Qt.ValueType:
  Qt.ValueType.define("BendValueEnvelope", [owner(), payload()])

def payload_value(value: Payload) -> Qt.Action(Unit):
  match value:
    case Payload{number, text}: require(U32.is_eq(number, 42) && String.eq(text, "opaque"), "Gadget lost its opaque Bend field")

def lifetimes() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +object: Qt.QObject <- Qt.QObject.newWithSignals("BendValueOwner", [])
    +record: Qt.ValueType.Instance(Envelope()) <- Qt.ValueType.make(~Envelope(), object, Payload{42, "opaque"})
    held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QObject.destroy(object))
    expected(Unit, held, 16)
    data: Payload <- Qt.ValueType.get(~Envelope(), ~payload(), record)
    payload_value(data)
    Qt.ValueType.release(~Envelope(), record)
    Qt.QObject.destroy(object)

def signals() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +sender: Qt.QObject <- Qt.QObject.newWithSignals("BendValueSender", [changed()])
    connection: Qt.Connection <- Qt.Signal.connect(~changed(), ~Qt.QObject, ~received, sender, sender)
    value: Qt.ValueType.Instance(Time()) <- Qt.ValueType.make(~Time(), Qt.Int64{42, 0}, "signal")
    Qt.Signal.emit(~changed(), sender, value)
    found: String <- Qt.QObject.objectName(sender)
    require(String.eq(found, "signal"), "Bend-authored value did not cross a Qt signal")

def qml() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    registration: U32 <- Qt.ValueType.register(~Time(), "BendValueRecords", 1, 0, "bendTime")
    holder: Qt.Qml.Registration(Holder()) <- Qt.Qml.registerType(~Holder(), "BendValueRecords", 1, 0, "Holder")
    +engine: Qt.QQmlEngine <- Qt.QQmlEngine.new()
    +component: Qt.QQmlComponent <- Qt.QQmlComponent.new__QQmlEngine_QObject(engine, Qt.QObject{0})
    source: Qt.QByteArray <- Qt.QByteArray.fromUtf8("import QtQml\nimport BendValueRecords 1.0\nHolder { stamp: ({tick:73, text:'qml'}); entries: [({tick:74, text:'list'})]; Component.onCompleted: { stamp.text = 'updated'; entries[0].text = 'list-updated'; } }")
    url: Qt.QUrl <- Qt.QUrl.new()
    Qt.QQmlComponent.setData(component, source, url)
    ready: Bool <- Qt.QQmlComponent.isReady(component)
    require(ready, "QML did not compile the authored value type")
    +root: Qt.QObject <- Qt.QQmlComponent.create__QQmlContext(component, Qt.QQmlContext{0})
    value: Qt.ValueType.Instance(Time()) <- Qt.Property.get(~stamp(), root)
    copied: List<&2, Qt.ValueType.Instance(Time())> <- Qt.Property.get(~entries(), root)
    Qt.QObject.destroy(root)
    found: String <- Qt.ValueType.get(~Time(), ~text(), value)
    require(String.eq(found, "updated"), "QML value property writeback failed")
    list_values(copied, "list-updated")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, values())
    Qt.scoped(Unit, signals())
    Qt.scoped(Unit, lifetimes())
    Qt.scoped(Unit, qml())
    live: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(live, 0), "Value integration leaked native handles")
    data: U32 <- Qt.Runtime.liveData()
    require(U32.is_eq(data, 0), "Value integration leaked opaque Bend fields")
    Qt.Action.lift(Unit, IO.print("QT612_VALUE_TYPES_OK"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
