import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expected(-A: Type, result: Result<&1, &1, U32 & String, A>, code: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(+actual, message)}: require(U32.is_eq(actual, code), "Value origin error " ++ U32.show(actual) ++ ": " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Invalid value origin was accepted")

def descriptor() -> Qt.Property:
  Qt.Property.define("descriptor", Qt.QMetaProperty.arg())

def descriptors() -> Qt.Property:
  Qt.Property.define("descriptors", Qt.variantList())

def image() -> Qt.Property:
  Qt.Property.define("image", Qt.QImage.arg())

def peer() -> Qt.Property:
  Qt.Property.define("peer", Qt.qobject())

def freshDescriptor() -> Qt.Method:
  Qt.Method.define("freshDescriptor", [], Qt.QMetaProperty.arg())

def freshImage() -> Qt.Method:
  Qt.Method.define("freshImage", [], Qt.QImage.arg())

def computedDescriptor() -> Qt.Property:
  Qt.Property.readOnly("computedDescriptor", Qt.QMetaProperty.arg())

def Holder() -> Qt.ObjectType:
  Qt.ObjectType.withMethods(Qt.QObject.define("MetadataValueHolder", [descriptor(), descriptors(), image(), peer(), computedDescriptor()]), [freshDescriptor(), freshImage()])

def from_meta(+meta: Qt.QMetaObject) -> Qt.Action(Qt.QMetaProperty):
  do Qt.Action<Qt.QMetaProperty>:
    index: Qt.Int32 <- Qt.QMetaObject.indexOfProperty(meta, "objectName")
    Qt.QMetaObject.property(meta, index)

def source(map: Qt.QQmlPropertyMap) -> Qt.Action(Qt.QMetaProperty):
  Qt.QMetaObject.with(Qt.QMetaProperty, Qt.QQmlPropertyMap.metaObject(map), meta => from_meta(meta))

def named(value: Maybe<&2, String>) -> Qt.Action(Unit):
  match value:
    case Some{name}: require(String.eq(name, "objectName"), "Raw metadata value changed")
    case None{}: Qt.Action.fail(Unit, 1, "Raw metadata name disappeared")

def one(values: List<&2, Qt.QVariant>) -> Qt.Action(Unit):
  match values:
    case +boxed <> Nil{}:
      do Qt.Action<Unit>:
        +value: Qt.QMetaProperty <- Qt.QVariant.toValue(~Qt.QMetaProperty.arg(), boxed)
        name: Maybe<&2, String> <- Qt.QMetaProperty.name(value)
        named(name)
        Qt.QMetaProperty.destroy(value)
        Qt.QVariant.destroy(boxed)
    case _: Qt.Action.fail(Unit, 1, "Raw metadata list changed")

def fields() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    instance: Qt.ObjectType.Instance(Holder()) <- Qt.ObjectType.new(~Holder())
    +self: Qt.QObject = Qt.ObjectType.as_QObject(~Holder(), instance)
    +map: Qt.QQmlPropertyMap <- Qt.QQmlPropertyMap.new()
    +value: Qt.QMetaProperty <- source(map)
    Qt.Property.set(~descriptor(), self, value)
    +boxed: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.QMetaProperty.arg(), value)
    Qt.Property.set(~descriptors(), self, [boxed])
    Qt.QVariant.destroy(boxed)
    Qt.QMetaProperty.destroy(value)
    +restored: Qt.QMetaProperty <- Qt.Property.get(~descriptor(), self)
    name: Maybe<&2, String> <- Qt.QMetaProperty.name(restored)
    named(name)
    Qt.QMetaProperty.destroy(restored)
    values: List<&2, Qt.QVariant> <- Qt.Property.get(~descriptors(), self)
    one(values)
    held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QQmlPropertyMap.destroy(map))
    expected(Unit, held, 16)
    +replacement: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.int32(), Qt.Int32{7})
    Qt.QQmlPropertyMap.insert__String_QVariant(map, "afterCapture", replacement)
    stale: Result<&1, &1, U32 & String, Qt.QMetaProperty> <- Qt.Action.attempt(Qt.QMetaProperty, Qt.Property.get(~descriptor(), self))
    expected(Qt.QMetaProperty, stale, 116)
    stale: Result<&1, &1, U32 & String, List<&2, Qt.QVariant>> <- Qt.Action.attempt(List<&2, Qt.QVariant>, Qt.Property.get(~descriptors(), self))
    expected(List<&2, Qt.QVariant>, stale, 116)
    empty: Qt.QMetaProperty <- Qt.QMetaProperty.new()
    Qt.Property.set(~descriptor(), self, empty)
    Qt.Property.set(~descriptors(), self, [])
    Qt.QQmlPropertyMap.destroy(map)
    +borrowed: Qt.QObject <- Qt.QObject.new()
    Qt.Property.set(~peer(), self, borrowed)
    Qt.QObject.destroy(borrowed)
    result: Qt.QObject <- Qt.Property.get(~peer(), self)
    require(U32.is_eq(Qt.QObject.word(result), 0), "Stored QObject pointer stopped being borrowed")

def self_origin() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +instance: Qt.ObjectType.Instance(Holder()) <- Qt.ObjectType.new(~Holder())
    +self: Qt.QObject = Qt.ObjectType.as_QObject(~Holder(), instance)
    +value: Qt.QMetaProperty <- Qt.QMetaObject.with(Qt.QMetaProperty, Qt.QObject.metaObject(self), meta => from_meta(meta))
    Qt.Property.set(~descriptor(), self, value)
    Qt.QMetaProperty.destroy(value)
    +restored: Qt.QMetaProperty <- Qt.Property.get(~descriptor(), self)
    name: Maybe<&2, String> <- Qt.QMetaProperty.name(restored)
    named(name)
    Qt.QMetaProperty.destroy(restored)
    Qt.ObjectType.destroy(~Holder(), instance)

def fresh(map: Qt.QQmlPropertyMap) -> Qt.Action(Qt.QMetaProperty):
  source(map)

def make_image(state: Unit) -> Qt.Action(Qt.QImage):
  do Qt.Action<Qt.QImage>:
    bytes: Qt.QByteArray <- Qt.QByteArray.fromBytes([255, 0, 0, 255])
    buffer: Qt.ImageBuffer <- Qt.ImageBuffer.fromBytes(bytes)
    Qt.QImage.fromBuffer(buffer, Qt.Int32{1}, Qt.Int32{1}, Qt.QImage.Format.Format_RGBA8888())

def red(+image: Qt.QImage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +color: Qt.QColor <- Qt.QImage.pixelColor__Int32_Int32(image, Qt.Int32{0}, Qt.Int32{0})
    value: Qt.Int32 <- Qt.QColor.red(color)
    green: Qt.Int32 <- Qt.QColor.green(color)
    require(U32.is_eq(Qt.Int32.word(value), 255) && U32.is_eq(Qt.Int32.word(green), 0), "External image backing expired")

def answers() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    instance: Qt.ObjectType.Instance(Holder()) <- Qt.ObjectType.new(~Holder())
    +self: Qt.QObject = Qt.ObjectType.as_QObject(~Holder(), instance)
    +map: Qt.QQmlPropertyMap <- Qt.QQmlPropertyMap.new()
    Qt.Method.handle(~freshDescriptor(), ~Qt.QQmlPropertyMap, ~fresh, self, map)
    Qt.Property.handleGetter(~computedDescriptor(), ~Qt.QQmlPropertyMap, ~fresh, self, map)
    Qt.Method.handle(~freshImage(), ~Unit, ~make_image, self, Unit{})
    +method_value: Qt.QMetaProperty <- Qt.Method.call(~freshDescriptor(), self)
    name: Maybe<&2, String> <- Qt.QMetaProperty.name(method_value)
    named(name)
    +getter_value: Qt.QMetaProperty <- Qt.Property.get(~computedDescriptor(), self)
    name: Maybe<&2, String> <- Qt.QMetaProperty.name(getter_value)
    named(name)
    +picture: Qt.QImage <- Qt.Method.call(~freshImage(), self)
    red(picture)
    Qt.Property.set(~image(), self, picture)
    Qt.QImage.destroy(picture)
    restored: Qt.QImage <- Qt.Property.get(~image(), self)
    red(restored)
    replacement: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.int32(), Qt.Int32{9})
    Qt.QQmlPropertyMap.insert__String_QVariant(map, "afterAnswer", replacement)
    stale: Result<&1, &1, U32 & String, Maybe<&2, String>> <- Qt.Action.attempt(Maybe<&2, String>, Qt.QMetaProperty.name(method_value))
    expected(Maybe<&2, String>, stale, 116)
    stale: Result<&1, &1, U32 & String, Maybe<&2, String>> <- Qt.Action.attempt(Maybe<&2, String>, Qt.QMetaProperty.name(getter_value))
    expected(Maybe<&2, String>, stale, 116)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, fields())
    Qt.scoped(Unit, self_origin())
    Qt.scoped(Unit, answers())
    objects: U32 <- Qt.Runtime.liveObjects()
    retentions: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(retentions, 0), "Stored value origins leaked")
    Qt.Action.lift(Unit, IO.print("QT612_METADATA_ARGUMENTS_OK raw=1 list=1 source_release=1 epoch=1 overwrite=1 borrowed=1 self_cycle=0 answers=1 external_backing=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
