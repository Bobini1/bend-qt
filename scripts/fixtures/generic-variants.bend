import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expected(-A: Type, result: Result<&1, &1, U32 & String, A>, code: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(+actual, message)}: require(U32.is_eq(actual, code), "Variant error " ++ U32.show(actual) ++ ": " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Invalid QVariant operation succeeded")

def words(values: List<&2, Qt.Int32>) -> Qt.Action(Unit):
  match values:
    case first <> second <> Nil{}:
      require(U32.is_eq(Qt.Int32.word(first), 1) && U32.is_eq(Qt.Int32.word(second), 4294967295), "Variant native list changed")
    case _: Qt.Action.fail(Unit, 1, "Variant native list shape changed")

def scalars() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +empty: Qt.QVariant <- Qt.QVariant.new()
    valid: Bool <- Qt.QVariant.isValid(empty)
    null: Bool <- Qt.QVariant.isNull(empty)
    require(Bool.not(valid) && null, "Default QVariant is not empty")
    +value: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.int32(), Qt.Int32{42})
    scalar: Qt.Int32 <- Qt.QVariant.toValue(~Qt.int32(), value)
    require(U32.is_eq(Qt.Int32.word(scalar), 42), "Variant scalar round trip changed")
    allowed: Bool <- Qt.QVariant.canConvert(~Qt.string(), value)
    require(allowed, "Qt numeric-string converter disappeared")
    wrong: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QVariant.toValue(~Qt.string(), value))
    expected(String, wrong, 22)
    converted: Bool <- Qt.QVariant.convert(~Qt.string(), value)
    require(converted, "Explicit QVariant conversion failed")
    text: String <- Qt.QVariant.toValue(~Qt.string(), value)
    require(String.eq(text, "42"), "Converted QVariant string changed")
    Qt.QVariant.clear(value)
    valid: Bool <- Qt.QVariant.isValid(value)
    require(Bool.not(valid), "QVariant.clear did not invalidate its value")
    wide: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.u64(), Qt.UInt64{4294967295, 4294967295})
    +number: Qt.UInt64 <- Qt.QVariant.toValue(~Qt.u64(), wide)
    require(U32.is_eq(Qt.UInt64.lo(number), 4294967295) && U32.is_eq(Qt.UInt64.hi(number), 4294967295), "Variant narrowed 64 bits")
    native_enum: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.Qt.DayOfWeek.arg(), Qt.Qt.DayOfWeek.Monday())
    day: Qt.Qt.DayOfWeek <- Qt.QVariant.toValue(~Qt.Qt.DayOfWeek.arg(), native_enum)
    require(U32.is_eq(Qt.Qt.DayOfWeek.word(day), 1), "Native enum lost its metatype")
    +list: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.list(Qt.int32()), [Qt.Int32{1}, Qt.Int32{4294967295}])
    values: List<&2, Qt.Int32> <- Qt.QVariant.toValue(~Qt.list(Qt.int32()), list)
    words(values)
    +whole: Qt.QVariant <- Qt.QVariant.toValue(~Qt.variant(), list)
    values: List<&2, Qt.Int32> <- Qt.QVariant.toValue(~Qt.list(Qt.int32()), whole)
    words(values)

def State() -> Qt.Enum:
  Qt.Enum.define("BoxedVariantObject::State", [Qt.Enum.key("Ready", 2)])

def title() -> Qt.Property:
  Qt.Property.define("title", Qt.string())

def Object() -> Qt.ObjectType:
  Qt.ObjectType.withEnums(Qt.QObject.define("BoxedVariantObject", [title()]), [State()])

def objects() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +source: Qt.QPushButton <- Qt.QPushButton.new()
    +value: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.QPushButton.arg(), source)
    +copy: Qt.QVariant <- Qt.QVariant.copy(value)
    Qt.QVariant.clear(value)
    held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QPushButton.destroy(source))
    expected(Unit, held, 16)
    +button: Qt.QPushButton <- Qt.QVariant.toValue(~Qt.QPushButton.arg(), copy)
    Qt.QPushButton.setText(button, "retained")
    converted: Bool <- Qt.QVariant.convert(~Qt.QObject.arg(), copy)
    require(converted, "QObject QVariant upcast failed")
    +object: Qt.QObject <- Qt.QVariant.toValue(~Qt.QObject.arg(), copy)
    Qt.QObject.setObjectName(object, "upcast")
    name: String <- Qt.QPushButton.objectName(source)
    require(String.eq(name, "upcast"), "QObject conversion changed native identity")
    held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QPushButton.destroy(source))
    expected(Unit, held, 16)
    Qt.QVariant.clear(copy)
    Qt.QPushButton.destroy(source)
    +declared: Qt.ObjectType.Instance(Object()) <- Qt.ObjectType.new(~Object())
    Qt.ObjectType.set(~Object(), ~title(), declared, "concrete")
    variant: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.ObjectType.arg(~Object()), declared)
    +restored: Qt.ObjectType.Instance(Object()) <- Qt.QVariant.toValue(~Qt.ObjectType.arg(~Object()), variant)
    text: String <- Qt.ObjectType.get(~Object(), ~title(), restored)
    require(String.eq(text, "concrete"), "Runtime QObject QVariant lost its declared class")
    state: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.Enum.arg(~State()), Qt.Enum.fromU32(~State(), 2))
    value: Qt.Enum.Value(State()) <- Qt.QVariant.toValue(~Qt.Enum.arg(~State()), state)
    bits: Qt.UInt64 = Qt.Enum.bits(~State(), value)
    require(U32.is_eq(Qt.UInt64.lo(bits), 2), "Runtime enum QVariant lost its native type")

type Payload is Data:
  Payload{number: U32, text: String}

type OtherPayload is Data:
  OtherPayload{number: U32, text: String}

def payload(value: Payload) -> Qt.Action(Unit):
  match value:
    case Payload{number, text}: require(U32.is_eq(number, 7) && String.eq(text, "Bend"), "Opaque QVariant payload changed")

def data() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +variant: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.arg(~Payload), Payload{7, "Bend"})
    value: Payload <- Qt.QVariant.toValue(~Qt.arg(~Payload), variant)
    payload(value)
    wrong: Result<&1, &1, U32 & String, OtherPayload> <- Qt.Action.attempt(OtherPayload, Qt.QVariant.toValue(~Qt.arg(~OtherPayload), variant))
    expected(OtherPayload, wrong, 22)

def metadata_value(map: Qt.QQmlPropertyMap) -> Qt.Action(Qt.QMetaProperty):
  do Qt.Action<Qt.QMetaProperty>:
    +meta: Qt.QMetaObject <- Qt.QQmlPropertyMap.metaObject(map)
    index: Qt.Int32 <- Qt.QMetaObject.indexOfProperty(meta, "objectName")
    Qt.QMetaObject.property(meta, index)

def named(value: Maybe<&2, String>) -> Qt.Action(Unit):
  match value:
    case Some{name}: require(String.eq(name, "objectName"), "Boxed metadata changed")
    case None{}: Qt.Action.fail(Unit, 1, "Boxed metadata name disappeared")

def mapping(values: List<&2, Qt.PairValue<String, Qt.QVariant>>) -> Qt.Action(Qt.QMetaProperty):
  match values:
    case Qt.PairValue{key, value} <> Nil{}: Qt.QVariant.toValue(~Qt.QMetaProperty.arg(), value)
    case _: Qt.Action.fail(Qt.QMetaProperty, 1, "Boxed metadata container changed")

def metadata() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +map: Qt.QQmlPropertyMap <- Qt.QQmlPropertyMap.new()
    +source: Qt.QMetaProperty <- metadata_value(map)
    +variant: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.QMetaProperty.arg(), source)
    +copy: Qt.QVariant <- Qt.QVariant.copy(variant)
    Qt.QMetaProperty.destroy(source)
    +property: Qt.QMetaProperty <- Qt.QVariant.toValue(~Qt.QMetaProperty.arg(), copy)
    name: Maybe<&2, String> <- Qt.QMetaProperty.name(property)
    named(name)
    +container: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.variantMap(), [Qt.PairValue{"property", copy}])
    +container_copy: Qt.QVariant <- Qt.QVariant.copy(container)
    values: List<&2, Qt.PairValue<String, Qt.QVariant>> <- Qt.QVariant.toValue(~Qt.variantMap(), container_copy)
    +nested: Qt.QMetaProperty <- mapping(values)
    name: Maybe<&2, String> <- Qt.QMetaProperty.name(nested)
    named(name)
    +replacement: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.int32(), Qt.Int32{9})
    Qt.QVariant.assign(variant, replacement)
    Qt.QQmlPropertyMap.insert__String_QVariant(map, "newAfterSnapshot", replacement)
    stale: Result<&1, &1, U32 & String, Maybe<&2, String>> <- Qt.Action.attempt(Maybe<&2, String>, Qt.QMetaProperty.name(property))
    expected(Maybe<&2, String>, stale, 116)
    stale: Result<&1, &1, U32 & String, Maybe<&2, String>> <- Qt.Action.attempt(Maybe<&2, String>, Qt.QMetaProperty.name(nested))
    expected(Maybe<&2, String>, stale, 116)
    stale_copy: Result<&1, &1, U32 & String, Qt.QMetaProperty> <- Qt.Action.attempt(Qt.QMetaProperty, Qt.QVariant.toValue(~Qt.QMetaProperty.arg(), copy))
    expected(Qt.QMetaProperty, stale_copy, 116)
    number: Qt.Int32 <- Qt.QVariant.toValue(~Qt.int32(), variant)
    require(U32.is_eq(Qt.Int32.word(number), 9), "Assigning a boxed QVariant kept the old metadata lease")

def values() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +size: Qt.QSize <- Qt.QSize.new__Int32_Int32(Qt.Int32{123}, Qt.Int32{456})
    value: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.QSize.arg(), size)
    Qt.QSize.destroy(size)
    +restored: Qt.QSize <- Qt.QVariant.toValue(~Qt.QSize.arg(), value)
    width: Qt.Int32 <- Qt.QSize.width(restored)
    height: Qt.Int32 <- Qt.QSize.height(restored)
    require(U32.is_eq(Qt.Int32.word(width), 123) && U32.is_eq(Qt.Int32.word(height), 456), "Generic QVariant value copy borrowed its source wrapper")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, scalars())
    Qt.scoped(Unit, objects())
    Qt.scoped(Unit, data())
    Qt.scoped(Unit, values())
    Qt.scoped(Unit, metadata())
    objects: U32 <- Qt.Runtime.liveObjects()
    retentions: U32 <- Qt.Runtime.liveRetentions()
    data: U32 <- Qt.Runtime.liveData()
    require(U32.is_eq(objects, 0) && U32.is_eq(retentions, 0) && U32.is_eq(data, 0), "Generic QVariant leases or payloads leaked")
    Qt.Action.lift(Unit, IO.print("QT612_GENERIC_VARIANTS_OK scalars=1 nativeEnums=1 runtimeEnums=1 containers=1 objects=1 values=1 opaque=1 metadata=1 snapshots=1 convert=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
