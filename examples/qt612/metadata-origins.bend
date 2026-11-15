import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def error(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong metadata-origin error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected metadata-origin rejection")

def named(value: Maybe<&2, String>, expected: String) -> Qt.Action(Unit):
  match value:
    case Some{text}: require(String.eq(text, expected), "Metadata name differs")
    case None{}: Qt.Action.fail(Unit, 1, "Metadata name disappeared")

def property(+meta: Qt.QMetaObject) -> Qt.Action(Qt.QMetaProperty):
  do Qt.Action<Qt.QMetaProperty>:
    index: Qt.Int32 <- Qt.QMetaObject.indexOfProperty(meta, "objectName")
    Qt.QMetaObject.property(meta, index)

def object(value: Qt.QObject) -> Qt.Action(Qt.QMetaProperty):
  Qt.QMetaObject.with(Qt.QMetaProperty, Qt.QObject.metaObject(value), meta => property(meta))

def escaped(value: Qt.QMetaProperty) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    name: Maybe<&2, String> <- Qt.QMetaProperty.name(value)
    named(name, "objectName")

def changed(+map: Qt.QQmlPropertyMap, +meta: Qt.QMetaObject, value: Qt.QVariant) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQmlPropertyMap.insert__String_QVariant(map, "addedAfterMetadataBorrow", value)
    stale: Result<&1, &1, U32 & String, Qt.Int32> <- Qt.Action.attempt(Qt.Int32, Qt.QMetaObject.propertyCount(meta))
    error(Qt.Int32, stale, 116)

def map_meta(+map: Qt.QQmlPropertyMap) -> Qt.Action(Unit):
  Qt.QMetaObject.with(Unit, Qt.QQmlPropertyMap.metaObject(map), meta =>
    Qt.QVariant.with(Unit, Qt.QVariant.fromString("value"), value => changed(map, meta, value)))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QMetaProperty.with(Unit, Qt.QObject.with(Qt.QMetaProperty, Qt.QObject.new(), value => object(value)), value => escaped(value))
    Qt.QQmlPropertyMap.with(Unit, Qt.QQmlPropertyMap.new(), value => map_meta(value))
    objects: U32 <- Qt.Runtime.liveObjects()
    pins: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(pins, 0), "Metadata origin handles leaked")
    Qt.Action.lift(Unit, IO.print("QT612_METADATA_ORIGINS_OK borrowed_metaobject=1 copied_descriptor=1 retained_origin=1 dynamic_invalidation=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
