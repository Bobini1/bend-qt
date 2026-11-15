import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expected(~A: Type, code: U32, result: Result<&1, &1, U32 & String, A>) -> Qt.Action(Unit):
  match result:
    case Fail{(actual, message)}: require(U32.is_eq(actual, code), "Wrong primitive storage error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Invalid primitive storage operation succeeded")

def change(+meta: Qt.QMetaType, +source: Qt.MetaStorage, +destination: Qt.MetaStorage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    ok: Bool <- Qt.QMetaType.convert__QMetaType_MetaStorage_QMetaType_MetaStorage(meta, source, meta, destination)
    require(ok, "Primitive storage write failed")

def read_only(+meta: Qt.QMetaType, +source: Qt.MetaStorage, +destination: Qt.MetaStorage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    result: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.QMetaType.convert__QMetaType_MetaStorage_QMetaType_MetaStorage(meta, source, meta, destination))
    expected(Bool, 1, result)

def alias(+primitive: Qt.QJSPrimitiveValue, +meta: Qt.QMetaType, +source: Qt.MetaStorage, +storage: Qt.MetaStorage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    change(meta, source, storage)
    value: String <- Qt.QJSPrimitiveValue.toString(primitive)
    require(String.eq(value, "updated"), "Mutable storage did not update the native primitive")
    destruction: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QMetaType.destruct__MetaStorage(meta, storage))
    expected(Unit, 1, destruction)
    owner: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QJSPrimitiveValue.destroy(primitive))
    expected(Unit, 16, owner)

def typed(+primitive: Qt.QJSPrimitiveValue, +meta: Qt.QMetaType, +source: Qt.MetaStorage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.MetaStorage.with(Unit, Qt.QJSPrimitiveValue.data(primitive), storage => alias(primitive, meta, source, storage))
    Qt.MetaStorage.with(Unit, Qt.QJSPrimitiveValue.constData(primitive), storage => read_only(meta, source, storage))
    Qt.QJSPrimitiveValue.with(Unit, Qt.QJSPrimitiveValue.new__QMetaType_MetaStorage(meta, source), copy =>
      do Qt.Action<Unit>:
        value: String <- Qt.QJSPrimitiveValue.toString(copy)
        require(String.eq(value, "updated"), "Primitive storage constructor lost its value"))

def primitive(+value: Qt.QJSPrimitiveValue, +source: Qt.MetaStorage) -> Qt.Action(Unit):
  Qt.QMetaType.with(Unit, Qt.MetaStorage.metaType(source), meta => typed(value, meta, source))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QVariant.with(Unit, Qt.QVariant.fromString("updated"), value =>
      Qt.MetaStorage.with(Unit, Qt.MetaStorage.fromVariant(value), source =>
        Qt.QJSPrimitiveValue.with(Unit, Qt.QJSPrimitiveValue.new__String("original"), value => primitive(value, source))))
    Qt.QJSPrimitiveValue.with(Unit, Qt.QJSPrimitiveValue.new(), value =>
      do Qt.Action<Unit>:
        absent: Qt.MetaStorage <- Qt.QJSPrimitiveValue.data(value)
        require(U32.is_eq(Qt.MetaStorage.word(absent), 0), "Undefined primitive has native data"))
    objects: U32 <- Qt.Runtime.liveObjects()
    pins: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(pins, 0), "Primitive storage leaked native resources")
    Qt.Action.lift(Unit, IO.print("QT612_PRIMITIVE_STORAGE_OK mutable_alias=1 readonly=1 borrowed_destruction=1 retention=1 typed_constructor=1 null_data=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
