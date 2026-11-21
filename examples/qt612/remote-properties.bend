# Maintainer fixture supplies the registered gadget; consumer uses normal imports.
import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def rejected(result: Result<&1, &1, U32 & String, Unit>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 22), "Wrong gadget compatibility error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Remote properties accepted non-gadget storage")

def verify(property: Qt.QMetaProperty, storage: Qt.MetaStorage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    text: String <- Qt.QVariant.with(String, Qt.QMetaProperty.readOnGadget(property, storage), Qt.QVariant.toString)
    require(String.eq(text, "remote 🎵"), "Remote stored properties changed their value")

def write(property: Qt.QMetaProperty, storage: Qt.MetaStorage, value: Qt.QVariant) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    written: Bool <- Qt.QMetaProperty.writeOnGadget(property, storage, value)
    require(written, "Could not initialize gadget property")

def deserialize(metadata: Qt.QMetaObject, property: Qt.QMetaProperty, +target: Qt.MetaStorage, stream: Qt.QDataStream) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QtRemoteObjects.copyStoredProperties__QMetaObject_QDataStream_MetaStorage(metadata, stream, target)
    verify(property, target)

def read_bytes(metadata: Qt.QMetaObject, property: Qt.QMetaProperty, target: Qt.MetaStorage, bytes: Qt.QByteArray) -> Qt.Action(Unit):
  Qt.QDataStream.with(Unit, Qt.QDataStream.new__QByteArray(bytes), stream => deserialize(metadata, property, target, stream))

def stream_bytes(+metadata: Qt.QMetaObject, +property: Qt.QMetaProperty, source: Qt.MetaStorage, +target: Qt.MetaStorage, +bytes: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QDataStream.with(Unit, Qt.QDataStream.new__QByteArray_QIODeviceBase_OpenModeFlag(bytes, Qt.QIODeviceBase.OpenModeFlag.ReadWrite()), stream =>
      Qt.QtRemoteObjects.copyStoredProperties__QMetaObject_MetaStorage_QDataStream(metadata, source, stream))
    read_bytes(metadata, property, target, bytes)

def wrong_storage(metadata: Qt.QMetaObject, source: Qt.MetaStorage, target: Qt.MetaStorage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    result: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QtRemoteObjects.copyStoredProperties__QMetaObject_MetaStorage_MetaStorage(metadata, source, target))
    rejected(result)

def wrong_variant(metadata: Qt.QMetaObject, source: Qt.MetaStorage, value: Qt.QVariant) -> Qt.Action(Unit):
  Qt.MetaStorage.with(Unit, Qt.MetaStorage.fromVariant(value), target => wrong_storage(metadata, source, target))

def targets(+metadata: Qt.QMetaObject, +property: Qt.QMetaProperty, +source: Qt.MetaStorage, +target: Qt.MetaStorage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QVariant.with(Unit, Qt.QVariant.fromString("remote 🎵"), value => write(property, source, value))
    Qt.QtRemoteObjects.copyStoredProperties__QMetaObject_MetaStorage_MetaStorage(metadata, source, target)
    verify(property, target)
    Qt.QVariant.with(Unit, Qt.QVariant.fromString("wrong"), value => wrong_variant(metadata, source, value))
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromUtf8(""), bytes => stream_bytes(metadata, property, source, target, bytes))

def source(+meta: Qt.QMetaType, metadata: Qt.QMetaObject, property: Qt.QMetaProperty, source: Qt.MetaStorage) -> Qt.Action(Unit):
  Qt.MetaStorage.with(Unit, Qt.QMetaType.create(meta), target => targets(metadata, property, source, target))

def property(+meta: Qt.QMetaType, metadata: Qt.QMetaObject, property: Qt.QMetaProperty) -> Qt.Action(Unit):
  Qt.MetaStorage.with(Unit, Qt.QMetaType.create(meta), value => source(meta, metadata, property, value))

def metadata(meta: Qt.QMetaType, +metadata: Qt.QMetaObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    index: Qt.Int32 <- Qt.QMetaObject.indexOfProperty(metadata, "text")
    Qt.QMetaProperty.with(Unit, Qt.QMetaObject.property(metadata, index), value => property(meta, metadata, value))

def gadget(+meta: Qt.QMetaType) -> Qt.Action(Unit):
  Qt.QMetaObject.with(Unit, Qt.QMetaType.metaObject(meta), object => metadata(meta, object))

def lookup(name: Qt.QByteArray) -> Qt.Action(Unit):
  Qt.QMetaType.with(Unit, Qt.QMetaType.fromName(name), meta => gadget(meta))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromUtf8("BendQtTestGadget"), lookup)
    live: U32 <- Qt.Fixture.liveGadgets()
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(live, 0) && U32.is_eq(objects, 0), "Remote property storage leaked values")
    Qt.Action.lift(Unit, IO.print("QT612_REMOTE_PROPERTIES_OK copy=1 serialization=1 deserialization=1 type_check=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
