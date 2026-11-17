import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def Status() -> Qt.Enum:
  Qt.Enum.define("RuntimeEnumCard::Status", [Qt.Enum.key("Idle", 0), Qt.Enum.key("Ready", 2), Qt.Enum.signedKey("Negative", Qt.Int32{4294967295})])

def Permissions() -> Qt.Enum:
  Qt.Enum.withAlias(Qt.Enum.withScoped(Qt.Enum.withUnsigned(Qt.Enum.withFlags(Qt.Enum.define("RuntimeEnumCard::Permissions", [Qt.Enum.key("Read", 1), Qt.Enum.key("Write", 2), Qt.Enum.key("All", 3)]), True{}), True{}), False{}), "Permission")

def Wide() -> Qt.Enum:
  Qt.Enum.withUnsigned(Qt.Enum.with64Bit(Qt.Enum.define("RuntimeEnumCard::Wide", [Qt.Enum.wideKey("Huge", Qt.UInt64{1, 1})]), True{}), True{})

def SignedWide() -> Qt.Enum:
  Qt.Enum.with64Bit(Qt.Enum.define("RuntimeEnumCard::SignedWide", [Qt.Enum.signedWideKey("BelowZero", Qt.Int64{4294967295, 4294967295})]), True{})

def Alternate() -> Qt.Enum:
  Qt.Enum.define("RuntimeEnumCard::Alternate", [Qt.Enum.key("Other", 0)])

def status() -> Qt.Property:
  Qt.Property.withBindable(Qt.Property.define("status", Qt.Enum.arg(~Status())), True{})

def alternate() -> Qt.Property:
  Qt.Property.withBindable(Qt.Property.define("alternate", Qt.Enum.arg(~Alternate())), True{})

def permissions() -> Qt.Property:
  Qt.Property.define("permissions", Qt.Enum.arg(~Permissions()))

def wide() -> Qt.Property:
  Qt.Property.define("wide", Qt.Enum.arg(~Wide()))

def sent() -> Qt.Signal:
  Qt.Signal.define("sent", [Qt.Enum.arg(~Status())])

def echo() -> Qt.Method:
  Qt.Method.define("echo", [Qt.Enum.arg(~Status())], Qt.Enum.arg(~Status()))

def Card() -> Qt.ObjectType:
  Qt.ObjectType.withMethods(Qt.ObjectType.withSignals(Qt.ObjectType.withEnums(Qt.QObject.define("RuntimeEnumCard", [status(), alternate(), permissions(), wide()]), [Status(), Permissions(), Wide(), SignedWide(), Alternate()]), [sent()]), [echo()])

def Derived() -> Qt.ObjectType:
  Qt.ObjectType.derive(~Card(), "RuntimeEnumDerived", [])

def UnicodeState() -> Qt.Enum:
  Qt.Enum.define("Bend::Żółw::Stan", [Qt.Enum.key("Gotowy", 2)])

def UnicodeObject() -> Qt.ObjectType:
  Qt.ObjectType.withEnums(Qt.QObject.define("Bend::Żółw", []), [UnicodeState()])

def received(self: Qt.QObject, value: Qt.Enum.Value(Status())) -> Qt.Action(Unit):
  Qt.Property.set(~status(), self, value)

def echoed(state: Unit, value: Qt.Enum.Value(Status())) -> Qt.Action(Qt.Enum.Value(Status())):
  Qt.Action.pure(Qt.Enum.Value(Status()), value)

def initialize(state: Unit, value: Qt.ObjectType.Instance(Card())) -> Qt.Action(Unit):
  Qt.Method.handle(~echo(), ~Unit, ~echoed, Qt.ObjectType.as_QObject(~Card(), value), Unit{})

def bits(+value: Qt.UInt64, lo: U32, hi: U32) -> Qt.Action(Unit):
  require(U32.is_eq(Qt.UInt64.lo(value), lo) && U32.is_eq(Qt.UInt64.hi(value), hi), "Enumeration bits changed")

def optional_bits(value: Maybe<&2, Qt.UInt64>, lo: U32, hi: U32) -> Qt.Action(Unit):
  match value:
    case Some{value}: bits(value, lo, hi)
    case None{}: Qt.Action.fail(Unit, 1, "Enumeration key is missing")

def text(value: Maybe<&2, String>, expected: String) -> Qt.Action(Unit):
  match value:
    case Some{value}: require(String.eq(value, expected), "Enumeration name changed")
    case None{}: Qt.Action.fail(Unit, 1, "Enumeration name is missing")

def meta_enum(self: Qt.QObject, name: String) -> Qt.Action(Qt.QMetaEnum):
  do Qt.Action<Qt.QMetaEnum>:
    +meta: Qt.QMetaObject <- Qt.QObject.metaObject(self)
    +index: Qt.Int32 <- Qt.QMetaObject.indexOfEnumerator(meta, name)
    require(U32.is_ne(Qt.Int32.word(index), 4294967295), "QObject enumeration is missing")
    Qt.QMetaObject.enumerator(meta, index)

def inspect(+self: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +status_meta: Qt.QMetaEnum <- meta_enum(self, "Status")
    scoped: Bool <- Qt.QMetaEnum.isScoped(status_meta)
    flagged: Bool <- Qt.QMetaEnum.isFlag(status_meta)
    require(scoped && Bool.not(flagged), "Scoped enumeration flags changed")
    name: Maybe<&2, String> <- Qt.QMetaEnum.scope(status_meta)
    text(name, "RuntimeEnumCard")
    value: Maybe<&2, Qt.UInt64> <- Qt.QMetaEnum.keyToValue64(status_meta, "Negative")
    optional_bits(value, 4294967295, 4294967295)
    +permissions_meta: Qt.QMetaEnum <- meta_enum(self, "Permissions")
    scoped: Bool <- Qt.QMetaEnum.isScoped(permissions_meta)
    flagged: Bool <- Qt.QMetaEnum.isFlag(permissions_meta)
    require(flagged && Bool.not(scoped), "Flag enumeration attributes changed")
    name: Maybe<&2, String> <- Qt.QMetaEnum.enumName(permissions_meta)
    text(name, "Permission")
    +wide_meta: Qt.QMetaEnum <- meta_enum(self, "Wide")
    is64: Bool <- Qt.QMetaEnum.is64Bit(wide_meta)
    require(is64, "64-bit enumeration metadata is missing")
    value: Maybe<&2, Qt.UInt64> <- Qt.QMetaEnum.value64(wide_meta, Qt.Int32{0})
    optional_bits(value, 1, 1)
    signed_meta: Qt.QMetaEnum <- meta_enum(self, "SignedWide")
    value: Maybe<&2, Qt.UInt64> <- Qt.QMetaEnum.keyToValue64(signed_meta, "BelowZero")
    optional_bits(value, 4294967295, 4294967295)
    +meta: Qt.QMetaObject <- Qt.QObject.metaObject(self)
    index: Qt.Int32 <- Qt.QMetaObject.indexOfProperty(meta, "status")
    +property: Qt.QMetaProperty <- Qt.QMetaObject.property(meta, index)
    is_enum: Bool <- Qt.QMetaProperty.isEnumType(property)
    require(is_enum, "Enum property is not a native enumeration")
    property_type: Qt.QMetaType <- Qt.QMetaProperty.metaType(property)
    enum_type: Qt.QMetaType <- Qt.QMetaEnum.metaType(status_meta)
    a: Qt.Int32 <- Qt.QMetaType.id(property_type)
    b: Qt.Int32 <- Qt.QMetaType.id(enum_type)
    require(U32.is_eq(Qt.Int32.word(a), Qt.Int32.word(b)), "Property and enumeration metatypes differ")

def expected(-A: Type, result: Result<&1, &1, U32 & String, A>, code: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(+actual, message)}: require(U32.is_eq(actual, code), "Unexpected enum failure " ++ U32.show(actual) ++ ": " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Invalid enumeration was accepted")

def invalid(~schema: Qt.ObjectType, code: U32) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    result: Result<&1, &1, U32 & String, Qt.ObjectType.Instance(schema)> <- Qt.Action.attempt(Qt.ObjectType.Instance(schema), Qt.ObjectType.new(~schema))
    expected(Qt.ObjectType.Instance(schema), result, code)

def qml() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +registration: Qt.Qml.Registration(Card()) <- Qt.Qml.registerType(~Card(), "Bend.RuntimeEnums", 1, 0, "Card")
    Qt.Qml.handleCreate(~Card(), ~Unit, ~initialize, registration, Unit{})
    +engine: Qt.QQmlEngine <- Qt.QQmlEngine.new()
    +component: Qt.QQmlComponent <- Qt.QQmlComponent.new__QQmlEngine_QObject(engine, Qt.QObject{0})
    data: Qt.QByteArray <- Qt.QByteArray.fromUtf8("import Bend.RuntimeEnums 1.0\nCard { status: Card.Status.Ready; permissions: Card.Read | Card.Write; wide: Card.Wide.Huge; property string result: String(echo(status)) + ':' + String(permissions) + ':' + String(wide) }")
    url: Qt.QUrl <- Qt.QUrl.new()
    Qt.QQmlComponent.setData(component, data, url)
    ready: Bool <- Qt.QQmlComponent.isReady(component)
    require(ready, "QML could not use Bend enumerations")
    +root: Qt.QObject <- Qt.QQmlComponent.create__QQmlContext(component, Qt.QQmlContext{0})
    result: Qt.QVariant <- Qt.QQmlProperty.read__QObject_String(root, "result")
    +value: String <- Qt.QVariant.toString(result)
    # The moc-generated runtime-enums-native.cpp control has the same QML
    # constant truncation. Native/Bend enum metadata retains all 64 bits.
    require(String.eq(value, "2:3:1"), "QML enum values differ from native Qt: " ++ value)
    +instance: Qt.ObjectType.Instance(Card()) <- Qt.ObjectType.cast(~Card(), root)
    value: Qt.Enum.Value(Status()) <- Qt.ObjectType.get(~Card(), ~status(), instance)
    bits(Qt.Enum.bits(~Status(), value), 2, 0)

def standalone_received(self: Qt.QObject, value: Qt.Enum.Value(Status())) -> Qt.Action(Unit):
  Qt.QObject.setObjectName(self, U32.show(Qt.UInt64.lo(Qt.Enum.bits(~Status(), value))))

def standalone() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +boxed: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.Enum.arg(~Status()), Qt.Enum.fromU32(~Status(), 2))
    value: String <- Qt.QVariant.toString(boxed)
    require(String.eq(value, "Ready"), "A standalone enum has no native string conversion")
    +native_type: Qt.QMetaType <- Qt.QVariant.metaType(boxed)
    +first_meta: Qt.QMetaObject <- Qt.QMetaType.metaObject(native_type)
    +first_enum: Qt.QMetaEnum <- Qt.QMetaObject.enumerator(first_meta, Qt.Int32{0})
    name: Maybe<&2, String> <- Qt.QMetaEnum.valueToKey(first_enum, Qt.UInt64{2, 0})
    text(name, "Ready")
    count: Qt.Int32 <- Qt.QMetaObject.enumeratorCount(first_meta)
    require(U32.is_eq(Qt.Int32.word(count), 1), "Standalone enum owner has unexpected entries")
    +flags: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.Enum.arg(~Permissions()), Qt.Enum.fromU32(~Permissions(), 3))
    grown_meta: Qt.QMetaObject <- Qt.QMetaType.metaObject(native_type)
    count: Qt.Int32 <- Qt.QMetaObject.enumeratorCount(grown_meta)
    require(U32.is_eq(Qt.Int32.word(count), 2), "Standalone enum owner did not gain its second enum")
    count: Qt.Int32 <- Qt.QMetaObject.enumeratorCount(first_meta)
    require(U32.is_eq(Qt.Int32.word(count), 1), "A borrowed enum owner table was mutated")
    value: Maybe<&2, Qt.UInt64> <- Qt.QMetaEnum.keyToValue64(first_enum, "Ready")
    optional_bits(value, 2, 0)
    +host: Qt.QObject <- Qt.QObject.newWithSignals("StandaloneEnumEmitter", [sent()])
    +probe: Qt.QObject <- Qt.QObject.new()
    connection: Qt.Connection <- Qt.Signal.connect(~sent(), ~Qt.QObject, ~standalone_received, host, probe)
    Qt.Signal.emit(~sent(), host, Qt.Enum.fromU32(~Status(), 2))
    value: String <- Qt.QObject.objectName(probe)
    require(String.eq(value, "2"), "Standalone enum signal did not reach Bend")
    instance: Qt.ObjectType.Instance(Card()) <- Qt.ObjectType.new(~Card())
    attached_meta: Qt.QMetaObject <- Qt.QMetaType.metaObject(native_type)
    index: Qt.Int32 <- Qt.QMetaObject.indexOfProperty(attached_meta, "status")
    require(U32.is_ne(Qt.Int32.word(index), 4294967295), "Enum metatype did not attach to its QObject owner")
    count: Qt.Int32 <- Qt.QMetaObject.enumeratorCount(first_meta)
    require(U32.is_eq(Qt.Int32.word(count), 1), "Attaching an enum invalidated its old namespace metadata")
    name: Maybe<&2, String> <- Qt.QMetaEnum.valueToKey(first_enum, Qt.UInt64{2, 0})
    text(name, "Ready")
    value: String <- Qt.QVariant.toString(boxed)
    require(String.eq(value, "Ready"), "Attaching an enum changed its native string conversion")

def cases() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +instance: Qt.ObjectType.Instance(Card()) <- Qt.ObjectType.new(~Card())
    +self: Qt.QObject = Qt.ObjectType.as_QObject(~Card(), instance)
    initialize(Unit{}, instance)
    +ready: Qt.Enum.Value(Status()) <- Qt.Enum.value(~Status(), "Ready")
    Qt.Property.set(~status(), self, ready)
    +connection: Qt.Connection <- Qt.Signal.connect(~sent(), ~Qt.QObject, ~received, self, self)
    idle: Qt.Enum.Value(Status()) <- Qt.Enum.value(~Status(), "Idle")
    Qt.Signal.emit(~sent(), self, idle)
    value: Qt.Enum.Value(Status()) <- Qt.Property.get(~status(), self)
    bits(Qt.Enum.bits(~Status(), value), 0, 0)
    value: Qt.Enum.Value(Status()) <- Qt.Method.call(~echo(), self, ready)
    bits(Qt.Enum.bits(~Status(), value), 2, 0)
    read: Qt.Enum.Value(Permissions()) <- Qt.Enum.value(~Permissions(), "Read")
    write: Qt.Enum.Value(Permissions()) <- Qt.Enum.value(~Permissions(), "Write")
    Qt.Property.set(~permissions(), self, Qt.Enum.or(~Permissions(), read, write))
    value: Qt.Enum.Value(Permissions()) <- Qt.Property.get(~permissions(), self)
    bits(Qt.Enum.bits(~Permissions(), value), 3, 0)
    Qt.scoped(Unit, inspect(self))
    +source: Qt.ObjectType.Instance(Card()) <- Qt.ObjectType.new(~Card())
    +other: Qt.QObject = Qt.ObjectType.as_QObject(~Card(), source)
    Qt.Property.bind(~status(), ~status(), self, other)
    Qt.Property.set(~status(), other, ready)
    value: Qt.Enum.Value(Status()) <- Qt.Property.get(~status(), self)
    bits(Qt.Enum.bits(~Status(), value), 2, 0)
    mismatch: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.Property.bind(~status(), ~alternate(), self, other))
    expected(Unit, mismatch, 22)
    Qt.Property.unbind(~status(), self)
    +derived: Qt.ObjectType.Instance(Derived()) <- Qt.ObjectType.new(~Derived())
    inherited: Qt.QMetaEnum <- meta_enum(Qt.ObjectType.as_QObject(~Derived(), derived), "Status")
    scope: Maybe<&2, String> <- Qt.QMetaEnum.scope(inherited)
    text(scope, "RuntimeEnumCard")
    unicode: Qt.ObjectType.Instance(UnicodeObject()) <- Qt.ObjectType.new(~UnicodeObject())
    +enumeration: Qt.QMetaEnum <- meta_enum(Qt.ObjectType.as_QObject(~UnicodeObject(), unicode), "Stan")
    scope: Maybe<&2, String> <- Qt.QMetaEnum.scope(enumeration)
    text(scope, "Bend::Żółw")
    value: Maybe<&2, Qt.UInt64> <- Qt.QMetaEnum.keyToValue64(enumeration, "Gotowy")
    optional_bits(value, 2, 0)
    outside: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.Property.set(~status(), self, Qt.Enum.fromU64(~Status(), Qt.UInt64{0, 1})))
    expected(Unit, outside, 34)
    unknown: Result<&1, &1, U32 & String, Qt.Enum.Value(Status())> <- Qt.Action.attempt(Qt.Enum.Value(Status()), Qt.Enum.value(~Status(), "Unknown"))
    expected(Qt.Enum.Value(Status()), unknown, 2)
    invalid(~Qt.ObjectType.withEnums(Qt.QObject.define("BadEnumKey", []), [Qt.Enum.define("BadEnumKey::Status", [Qt.Enum.key("Idle", 0), Qt.Enum.key("Idle", 1)])]), 17)
    invalid(~Qt.ObjectType.withEnums(Qt.QObject.define("BadEnumScope", []), [Status()]), 22)
    invalid(~Qt.ObjectType.withEnums(Qt.QObject.define("BadEnumWidth", []), [Qt.Enum.define("BadEnumWidth::Status", [Qt.Enum.wideKey("Huge", Qt.UInt64{0, 1})])]), 34)
    Qt.scoped(Unit, qml())

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, standalone())
    Qt.scoped(Unit, cases())
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Runtime enums leaked resources")
    Qt.Action.lift(Unit, IO.print("QT612_RUNTIME_ENUMS_OK enum=1 flags=1 scoped=1 signed=1 wide=1 standalone=1 immutable_metadata=1 metatype=1 property=1 signals=1 methods=1 bindings=1 qml=1 inherited=1 errors=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
