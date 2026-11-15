import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expected(~A: Type, code: U32, result: Result<&1, &1, U32 & String, A>) -> Qt.Action(Unit):
  match result:
    case Fail{(actual, message)}: require(U32.is_eq(actual, code), "Wrong metatype storage error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Invalid metatype storage access succeeded")

def text(storage: Qt.MetaStorage) -> Qt.Action(String):
  Qt.QVariant.with(String, Qt.MetaStorage.toVariant(storage), Qt.QVariant.toString)

def allocated(+meta: Qt.QMetaType, +original: Qt.MetaStorage, +storage: Qt.MetaStorage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    initial: Bool <- Qt.MetaStorage.isInitialized(storage)
    require(Bool.not(initial), "Raw aligned storage already has a value")
    absent: Result<&1, &1, U32 & String, Qt.QVariant> <- Qt.Action.attempt(Qt.QVariant, Qt.MetaStorage.toVariant(storage))
    expected(Qt.QVariant, 61, absent)
    alias: Qt.MetaStorage <- Qt.QMetaType.construct__MetaStorage_MetaStorage(meta, storage, original)
    require(U32.is_eq(Qt.MetaStorage.word(alias), Qt.MetaStorage.word(storage)), "Placement construction changed storage identity")
    value: String <- text(storage)
    require(String.eq(value, "42"), "Placement copy lost its QString")
    duplicate: Result<&1, &1, U32 & String, Qt.MetaStorage> <- Qt.Action.attempt(Qt.MetaStorage, Qt.QMetaType.construct__MetaStorage_MetaStorage(meta, storage, original))
    expected(Qt.MetaStorage, 114, duplicate)
    Qt.QMetaType.destruct__MetaStorage(meta, storage)
    twice: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QMetaType.destruct__MetaStorage(meta, storage))
    expected(Unit, 61, twice)
    rebuilt: Qt.MetaStorage <- Qt.QMetaType.construct__MetaStorage(meta, storage)
    empty: String <- text(rebuilt)
    require(String.eq(empty, ""), "Default placement construction did not initialize QString")

def copied(+meta: Qt.QMetaType, +original: Qt.MetaStorage, +copy: Qt.MetaStorage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    same: Bool <- Qt.QMetaType.equals__MetaStorage_MetaStorage(meta, original, copy)
    require(same, "QMetaType copy changed the native value")
    Qt.QMetaType.native_destroy__MetaStorage(meta, copy)
    stale: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.MetaStorage.isInitialized(copy))
    expected(Bool, 116, stale)

def converted(+source_type: Qt.QMetaType, +source: Qt.MetaStorage, +target_type: Qt.QMetaType, +target: Qt.MetaStorage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    ok: Bool <- Qt.QMetaType.convert__QMetaType_MetaStorage_QMetaType_MetaStorage(source_type, source, target_type, target)
    require(ok, "Qt runtime conversion from QString to int failed")
    value: Qt.Int32 <- Qt.QVariant.with(Qt.Int32, Qt.MetaStorage.toVariant(target), Qt.QVariant.toInt32)
    require(U32.is_eq(Qt.Int32.word(value), 42), "Runtime conversion wrote the wrong int")
    wrong: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.QMetaType.equals__MetaStorage_MetaStorage(source_type, source, target))
    expected(Bool, 22, wrong)

def conversion(source_type: Qt.QMetaType, source: Qt.MetaStorage, +target_type: Qt.QMetaType) -> Qt.Action(Unit):
  Qt.MetaStorage.with(Unit, Qt.QMetaType.create(target_type), target => converted(source_type, source, target_type, target))

def typed(+meta: Qt.QMetaType, +storage: Qt.MetaStorage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.MetaStorage.with(Unit, Qt.MetaStorage.allocate(meta), value => allocated(meta, storage, value))
    Qt.MetaStorage.with(Unit, Qt.QMetaType.create__MetaStorage(meta, storage), copy => copied(meta, storage, copy))
    Qt.QMetaType.with(Unit, Qt.QMetaType.new__Int32(Qt.Int32{Qt.QMetaType.Type.word(Qt.QMetaType.Type.Int())}), target => conversion(meta, storage, target))

def storage_demo(+storage: Qt.MetaStorage) -> Qt.Action(Unit):
  Qt.QMetaType.with(Unit, Qt.MetaStorage.metaType(storage), meta => typed(meta, storage))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QVariant.with(Unit, Qt.QVariant.fromString("42"), value => Qt.MetaStorage.with(Unit, Qt.MetaStorage.fromVariant(value), storage => storage_demo(storage)))
    objects: U32 <- Qt.Runtime.liveObjects()
    pins: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(pins, 0), "Metatype storage leaked native values")
    Qt.Action.lift(Unit, IO.print("QT612_METATYPES_OK aligned_storage=1 copy=1 construct=1 destruct=1 convert=1 wrong_type=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
