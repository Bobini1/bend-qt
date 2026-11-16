import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def title() -> Qt.Property:
  Qt.Property.define("title", Qt.string())

def counter() -> Qt.Property:
  Qt.Property.readOnly("counter", Qt.int32())

def greeting() -> Qt.Method:
  Qt.Method.define("greet", [Qt.string()], Qt.string())

def ping() -> Qt.Signal:
  Qt.Signal.define("ping", [Qt.string()])

def echoPeer() -> Qt.Method:
  Qt.Method.define("echoPeer", [Qt.ObjectType.reference("BendCard")], Qt.ObjectType.reference("BendCard"))

def makePeer() -> Qt.Method:
  Qt.Method.define("makePeer", [], Qt.ObjectType.reference("BendCard"))

def Card() -> Qt.ObjectType:
  Qt.ObjectType.withMethods(
    Qt.ObjectType.withSignals(Qt.QQuickItem.define("BendCard", [title(), counter()]), [ping()]),
    [greeting(), echoPeer(), makePeer()])

def echo_peer(state: Unit, value: Qt.ObjectType.Instance(Card())) -> Qt.Action(Qt.ObjectType.Instance(Card())):
  Qt.Action.pure(Qt.ObjectType.Instance(Card()), value)

def make_peer(state: Unit) -> Qt.Action(Qt.ObjectType.Instance(Card())):
  do Qt.Action<Qt.ObjectType.Instance(Card())>:
    +card: Qt.ObjectType.Instance(Card()) <- Qt.ObjectType.new(~Card())
    Qt.ObjectType.set(~Card(), ~title(), card, "fresh")
    return card

def greet(state: Unit, name: String) -> Qt.Action(String):
  Qt.Action.pure(String, "Hello " ++ name)

def GetterCard() -> Qt.ObjectType:
  Qt.QObject.define("GetterCard", [title()])

def setter(self: Qt.ObjectType.Instance(GetterCard()), value: String) -> Qt.Action(Unit):
  Qt.ObjectType.writeStorage(~GetterCard(), ~title(), self, "set:" ++ value)

def getter(self: Qt.ObjectType.Instance(GetterCard())) -> Qt.Action(String):
  do Qt.Action<String>:
    text: String <- Qt.ObjectType.readStorage(~GetterCard(), ~title(), self)
    return "get:" ++ text

def changed(probe: Qt.QObject, text: String) -> Qt.Action(Unit):
  Qt.QObject.setObjectName(probe, text)

def Child() -> Qt.ObjectType:
  Qt.ObjectType.derive(~Card(), "BendChildCard", [Qt.Property.constant("version", Qt.int32())])

def peer() -> Qt.Property:
  Qt.Property.define("peer", Qt.ObjectType.arg(~Card()))

def details() -> Qt.Property:
  Qt.Property.define("details", Qt.variantMap())

def variant_value() -> Qt.Property:
  Qt.Property.define("variantValue", Qt.variant())

def Box() -> Qt.ObjectType:
  Qt.QObject.define("BendBox", [peer(), details(), variant_value()])

def map_text(values: List<&2, Qt.PairValue<String, Qt.QVariant>>) -> Qt.Action(String):
  match values:
    case Qt.PairValue{key, value} <> Nil{}: Qt.QVariant.toString(value)
    case _: Qt.Action.fail(String, 1, "QML map property has the wrong shape")

def cardReady() -> Qt.Signal:
  Qt.Signal.define("cardReady", [Qt.ObjectType.arg(~Card())])

def received(probe: Qt.QObject, card: Qt.ObjectType.Instance(Card())) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    title: String <- Qt.ObjectType.get(~Card(), ~title(), card)
    Qt.QObject.setObjectName(probe, title)

def expected(-A: Type, value: Result<&1, &1, U32 & String, A>, code: U32) -> Qt.Action(Unit):
  match value:
    case Fail{(actual, message)}: require(U32.is_eq(actual, code), message)
    case Done{result}: Qt.Action.fail(Unit, 1, "Expected runtime QObject rejection")

def DuplicateParent() -> Qt.ObjectType:
  Qt.QObject.define("BendDuplicateDirect", [title()])

def DuplicateChild() -> Qt.ObjectType:
  Qt.ObjectType.derive(~DuplicateParent(), "BendDuplicateDirect", [])

def ConflictingParent() -> Qt.ObjectType:
  Qt.QObject.define("BendDuplicateDirect", [])

def DuplicateRoot() -> Qt.ObjectType:
  Qt.QObject.define("BendDuplicateDeep", [title()])

def DuplicateMiddle() -> Qt.ObjectType:
  Qt.ObjectType.derive(~DuplicateRoot(), "BendDuplicateMiddle", [])

def DuplicateLeaf() -> Qt.ObjectType:
  Qt.ObjectType.derive(~DuplicateMiddle(), "BendDuplicateDeep", [])

def NativeCollision() -> Qt.ObjectType:
  Qt.QObject.define("QTimer", [])

def NativePointerCollision() -> Qt.ObjectType:
  Qt.QObject.define("QSGNode", [])

def NativeValueCollision() -> Qt.ObjectType:
  Qt.QObject.define("QString", [])

def reject_duplicate(~schema: Qt.ObjectType) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    result: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit,
      Qt.ObjectType.with(~schema, Unit, Qt.ObjectType.new(~schema), value => Qt.Action.pure(Unit, Unit{})))
    expected(Unit, result, 17)

def duplicate_names() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    # A native class name is reserved even before its pointer metatype exists.
    reject_duplicate(~NativeCollision())
    reject_duplicate(~NativePointerCollision())
    reject_duplicate(~NativeValueCollision())
    # These ancestors must not be registered before the conflicting child.
    reject_duplicate(~DuplicateChild())
    reject_duplicate(~DuplicateLeaf())
    +parent: Qt.ObjectType.Instance(DuplicateParent()) <- Qt.ObjectType.new(~DuplicateParent())
    +other: Qt.ObjectType.Instance(DuplicateParent()) <- Qt.ObjectType.new(~DuplicateParent())
    +parent_object: Qt.QObject = Qt.ObjectType.as_QObject(~DuplicateParent(), parent)
    Qt.Property.set(~title(), parent_object, "parent remains valid")
    first: String <- Qt.Property.get(~title(), parent_object)
    second: String <- Qt.ObjectType.get(~DuplicateParent(), ~title(), other)
    require(String.eq(first, "parent remains valid") && String.eq(second, ""), "Identical schemas did not create independent instances")
    reject_duplicate(~ConflictingParent())
    +middle: Qt.ObjectType.Instance(DuplicateMiddle()) <- Qt.ObjectType.new(~DuplicateMiddle())
    +middle_object: Qt.QObject = Qt.ObjectType.as_QObject(~DuplicateMiddle(), middle)
    root: Qt.ObjectType.Instance(DuplicateRoot()) <- Qt.ObjectType.cast(~DuplicateRoot(), middle_object)
    Qt.ObjectType.set(~DuplicateRoot(), ~title(), root, "ancestor remains valid")
    inherited: String <- Qt.Property.get(~title(), middle_object)
    require(String.eq(inherited, "ancestor remains valid"), "Failed child registration damaged ancestor metadata")

def DynamicBase() -> Qt.ObjectType:
  Qt.QQmlPropertyMap.define("BendDynamicNativeBase", [])

def native_dynamic_meta() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +map: Qt.QQmlPropertyMap <- Qt.QQmlPropertyMap.newOverride()
    value: Qt.QVariant <- Qt.QVariant.fromString("native metadata")
    Qt.QQmlPropertyMap.insert__String_QVariant(map, "nativeValue", value)
    result: Qt.QVariant <- Qt.QQmlPropertyMap.value(map, "nativeValue")
    text: String <- Qt.QVariant.toString(result)
    require(String.eq(text, "native metadata"), "Native dynamic property storage changed")
    meta: Qt.QMetaObject <- Qt.QObject.metaObject(Qt.QQmlPropertyMap.as_QObject(map))
    index: Qt.Int32 <- Qt.QMetaObject.indexOfProperty(meta, "nativeValue")
    require(U32.is_ne(Qt.Int32.word(index), 4294967295), "A proxy hid the native dynamic metaobject")
    refused: Result<&1, &1, U32 & String, Qt.ObjectType.Instance(DynamicBase())> <- Qt.Action.attempt(Qt.ObjectType.Instance(DynamicBase()), Qt.ObjectType.attach(~DynamicBase(), map))
    expected(Qt.ObjectType.Instance(DynamicBase()), refused, 95)

def inheritance() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +child: Qt.ObjectType.Instance(Child()) <- Qt.ObjectType.new(~Child())
    +object: Qt.QObject = Qt.ObjectType.as_QObject(~Child(), child)
    +card: Qt.ObjectType.Instance(Card()) <- Qt.ObjectType.cast(~Card(), object)
    Qt.Property.set(~title(), object, "inherited")
    Qt.Property.writeStorage(~counter(), object, Qt.Int32{7})
    readonly: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.Property.set(~counter(), object, Qt.Int32{8}))
    expected(Unit, readonly, 1)
    Qt.Property.writeStorage(~Qt.Property.constant("version", Qt.int32()), object, Qt.Int32{1})
    version: Qt.Int32 <- Qt.Property.get(~Qt.Property.constant("version", Qt.int32()), object)
    frozen: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit,
      Qt.Property.writeStorage(~Qt.Property.constant("version", Qt.int32()), object, Qt.Int32{2}))
    expected(Unit, frozen, 1)
    +box: Qt.ObjectType.Instance(Box()) <- Qt.ObjectType.new(~Box())
    +holder: Qt.QObject = Qt.ObjectType.as_QObject(~Box(), box)
    unset: Qt.QVariant <- Qt.Property.get(~variant_value(), holder)
    storage: Result<&1, &1, U32 & String, Qt.MetaStorage> <- Qt.Action.attempt(Qt.MetaStorage, Qt.MetaStorage.fromVariant(unset))
    expected(Qt.MetaStorage, storage, 22)
    Qt.Property.set(~peer(), holder, card)
    copied: Qt.ObjectType.Instance(Card()) <- Qt.Property.get(~peer(), holder)
    text: String <- Qt.ObjectType.get(~Card(), ~title(), copied)
    require(String.eq(text, "inherited"), "Concrete QObject property type was lost")
    mismatch: Result<&1, &1, U32 & String, Qt.ObjectType.Instance(Card())> <- Qt.Action.attempt(Qt.ObjectType.Instance(Card()), Qt.ObjectType.cast(~Card(), holder))
    expected(Qt.ObjectType.Instance(Card()), mismatch, 22)
    +sender: Qt.QObject <- Qt.QObject.newWithSignals("BendCardSignals", [cardReady()])
    +probe: Qt.QObject <- Qt.QObject.new()
    connection: Qt.Connection <- Qt.Signal.connect(~cardReady(), ~Qt.QObject, ~received, sender, probe)
    Qt.Signal.emit(~cardReady(), sender, card)
    result: String <- Qt.QObject.objectName(probe)
    require(String.eq(result, "inherited"), "Typed Bend class signal lost its identity")
    Qt.ObjectType.destroy(~Child(), child)
    cleared: Qt.ObjectType.Instance(Card()) <- Qt.Property.get(~peer(), holder)
    require(U32.is_eq(Qt.ObjectType.word(~Card(), cleared), 0), "Destroyed QObject property was not cleared")

def qml_source() -> String:
  "import QtQuick\nQtObject { property string captured: card.title; property string result: card.greet('QML'); property string nested: box.peer.title; property string typedResult: card.echoPeer(box.peer).title; property var made: card.makePeer(); property string fresh: made.title; property string mapName: box.details.name; property int count: card.counter; property real nativeWidth: card.width; Component.onCompleted: { card.title = 'from QML'; box.details = {name: 'edited'} } }"

def qml(+self: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +engine: Qt.QQmlEngine <- Qt.QQmlEngine.new()
    +context: Qt.QQmlContext <- Qt.QQmlEngine.rootContext(engine)
    Qt.QQmlContext.setContextProperty__String_QObject(context, "card", self)
    box: Qt.ObjectType.Instance(Box()) <- Qt.ObjectType.new(~Box())
    +holder: Qt.QObject = Qt.ObjectType.as_QObject(~Box(), box)
    card: Qt.ObjectType.Instance(Card()) <- Qt.ObjectType.cast(~Card(), self)
    Qt.Property.set(~peer(), holder, card)
    map_value: Qt.QVariant <- Qt.QVariant.fromString("map")
    Qt.Property.set(~details(), holder, [Qt.PairValue{"name", map_value}])
    Qt.QQmlContext.setContextProperty__String_QObject(context, "box", holder)
    +component: Qt.QQmlComponent <- Qt.QQmlComponent.new__QQmlEngine_QObject(engine, Qt.QObject{0})
    data: Qt.QByteArray <- Qt.QByteArray.fromUtf8(qml_source())
    url: Qt.QUrl <- Qt.QUrl.new()
    Qt.QQmlComponent.setData(component, data, url)
    ready: Bool <- Qt.QQmlComponent.isReady(component)
    require(ready, "QObject schema QML did not compile")
    +root: Qt.QObject <- Qt.QQmlComponent.create__QQmlContext(component, Qt.QQmlContext{0})
    text: String <- Qt.Property.get(~title(), self)
    require(String.eq(text, "from QML"), "QML property write failed")
    result: Qt.QVariant <- Qt.QQmlProperty.read__QObject_String(root, "result")
    greeting: String <- Qt.QVariant.toString(result)
    require(String.eq(greeting, "Hello QML"), "Named Bend method failed in QML")
    Qt.Property.set(~title(), self, "updated")
    captured: Qt.QVariant <- Qt.QQmlProperty.read__QObject_String(root, "captured")
    latest: String <- Qt.QVariant.toString(captured)
    require(String.eq(latest, "updated"), "Property notify did not update QML binding")
    typed: Qt.QVariant <- Qt.QQmlProperty.read__QObject_String(root, "typedResult")
    typed_text: String <- Qt.QVariant.toString(typed)
    require(String.eq(typed_text, "updated"), "A concrete QObject method argument/result failed in QML")
    nested: Qt.QVariant <- Qt.QQmlProperty.read__QObject_String(root, "nested")
    nested_text: String <- Qt.QVariant.toString(nested)
    require(String.eq(nested_text, "updated"), "A concrete QObject property failed in QML")
    fresh: Qt.QVariant <- Qt.QQmlProperty.read__QObject_String(root, "fresh")
    fresh_text: String <- Qt.QVariant.toString(fresh)
    require(String.eq(fresh_text, "fresh"), "A newly created QObject result expired inside its handler")
    width: Qt.QVariant <- Qt.QQmlProperty.read__QObject_String(root, "nativeWidth")
    +width_value: Qt.F64 <- Qt.QVariant.toF64(width)
    require(U32.is_eq(Qt.F64.lo(width_value), 0) && U32.is_eq(Qt.F64.hi(width_value), 1079574528), "The native QQuickItem property was lost")
    values: List<&2, Qt.PairValue<String, Qt.QVariant>> <- Qt.Property.get(~details(), holder)
    map_value: String <- map_text(values)
    require(String.eq(map_value, "edited"), "QML did not write the QVariantMap property")
    count: Qt.QVariant <- Qt.QQmlProperty.read__QObject_String(root, "count")
    n: Qt.Int32 <- Qt.QVariant.toInt32(count)
    require(U32.is_eq(Qt.Int32.word(n), 42), "Read-only property failed in QML")

def objects() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    # References make the focused checker include these generated proxies.
    native: Qt.QQuickItem <- Qt.QQuickItem.newOverride()
    +item: Qt.ObjectType.Instance(Card()) <- Qt.ObjectType.attachUsing(~Card(), Qt.Action.pure(Qt.QQuickItem, native))
    +self: Qt.QObject = Qt.ObjectType.as_QObject(~Card(), item)
    Qt.QQuickItem.setWidth(Qt.ObjectType.asNativeBase(~Card(), item), Qt.F64{0, 1079574528})
    Qt.ObjectType.writeStorage(~Card(), ~counter(), item, Qt.Int32{42})
    Qt.ObjectType.set(~Card(), ~title(), item, "initial")
    Qt.ObjectType.handle(~Card(), ~greeting(), ~Unit, ~greet, item, Unit{})
    Qt.ObjectType.handle(~Card(), ~echoPeer(), ~Unit, ~echo_peer, item, Unit{})
    Qt.ObjectType.handle(~Card(), ~makePeer(), ~Unit, ~make_peer, item, Unit{})
    fresh: Qt.ObjectType.Instance(Card()) <- Qt.ObjectType.call(~Card(), ~makePeer(), item)
    fresh_text: String <- Qt.ObjectType.get(~Card(), ~title(), fresh)
    require(String.eq(fresh_text, "fresh"), "A new QObject result expired before Bend received it")
    answer: String <- Qt.ObjectType.call(~Card(), ~greeting(), item, "Bend")
    require(String.eq(answer, "Hello Bend"), "Named method failed in Bend")
    +probe: Qt.QObject <- Qt.QObject.new()
    connection: Qt.Connection <- Qt.ObjectType.connect(~Card(), ~ping(), ~Qt.QObject, ~changed, item, probe)
    Qt.ObjectType.emit(~Card(), ~ping(), item, "signal")
    name: String <- Qt.QObject.objectName(probe)
    require(String.eq(name, "signal"), "Schema signal failed")
    Qt.scoped(Unit, qml(self))
    base: Qt.QObject <- Qt.QObject.newOverride()
    +holder: Qt.ObjectType.Instance(GetterCard()) <- Qt.ObjectType.attachUsing(~GetterCard(), Qt.Action.pure(Qt.QObject, base))
    Qt.ObjectType.handleSetter(~GetterCard(), ~title(), ~Qt.ObjectType.Instance(GetterCard()), ~setter, holder, holder)
    Qt.ObjectType.handleGetter(~GetterCard(), ~title(), ~Qt.ObjectType.Instance(GetterCard()), ~getter, holder, holder)
    Qt.ObjectType.set(~GetterCard(), ~title(), holder, "value")
    read: String <- Qt.ObjectType.get(~GetterCard(), ~title(), holder)
    require(String.eq(read, "get:set:value"), "Typed property handlers failed")

def MutualFirst() -> Qt.ObjectType:
  Qt.QObject.define("MutualFirst", [Qt.Property.define("peer", Qt.ObjectType.reference("MutualSecond"))])

def MutualSecond() -> Qt.ObjectType:
  Qt.QObject.define("MutualSecond", [Qt.Property.define("peer", Qt.ObjectType.reference("MutualFirst"))])

def mutual_references() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +first: Qt.ObjectType.Instance(MutualFirst()) <- Qt.ObjectType.new(~MutualFirst())
    +first_object: Qt.QObject = Qt.ObjectType.as_QObject(~MutualFirst(), first)
    empty: Qt.ObjectType.Instance(MutualSecond()) <- Qt.Property.get(~Qt.Property.define("peer", Qt.ObjectType.reference("MutualSecond")), first_object)
    require(U32.is_eq(Qt.ObjectType.word(~MutualSecond(), empty), 0), "A forward reference did not default to null")
    +second: Qt.ObjectType.Instance(MutualSecond()) <- Qt.ObjectType.new(~MutualSecond())
    +second_object: Qt.QObject = Qt.ObjectType.as_QObject(~MutualSecond(), second)
    Qt.Property.set(~Qt.Property.define("peer", Qt.ObjectType.reference("MutualSecond")), first_object, second)
    Qt.Property.set(~Qt.Property.define("peer", Qt.ObjectType.reference("MutualFirst")), second_object, first)
    back: Qt.ObjectType.Instance(MutualFirst()) <- Qt.Property.get(~Qt.Property.define("peer", Qt.ObjectType.reference("MutualFirst")), second_object)
    require(U32.is_eq(Qt.ObjectType.word(~MutualFirst(), back), Qt.ObjectType.word(~MutualFirst(), first)), "Mutual QObject references changed identity")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, duplicate_names())
    Qt.scoped(Unit, objects())
    Qt.scoped(Unit, inheritance())
    Qt.scoped(Unit, native_dynamic_meta())
    Qt.scoped(Unit, mutual_references())
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Automatic QObject cleanup leaked")
    Qt.Action.lift(Unit, IO.print("QT612_QT_OBJECTS_OK"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
