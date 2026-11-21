import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def stale(-A: Type, result: Result<&1, &1, U32 & String, A>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 116), "Wrong model-index validity error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expired ordinary model index remained usable")

def shifted(+model: Qt.QStandardItemModel, +index: Qt.QModelIndex, +persistent: Qt.QPersistentModelIndex, +range: Qt.QItemSelectionRange) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    inserted: Bool <- Qt.QStandardItemModel.insertRow__Int32(model, Qt.Int32{0})
    require(inserted, "Model failed to insert a row")
    expired: Result<&1, &1, U32 & String, Qt.Int32> <- Qt.Action.attempt(Qt.Int32, Qt.QModelIndex.row(index))
    stale(Qt.Int32, expired)
    row: Qt.Int32 <- Qt.QPersistentModelIndex.row(persistent)
    require(U32.is_eq(Qt.Int32.word(row), 1), "Persistent index did not follow its item")
    valid: Bool <- Qt.QItemSelectionRange.isValid(range)
    require(valid, "Selection range did not preserve its native persistent indexes")
    Qt.QStandardItemModel.clear(model)
    present: Bool <- Qt.QPersistentModelIndex.isValid(persistent)
    selected: Bool <- Qt.QItemSelectionRange.isValid(range)
    require(Bool.not(present) && Bool.not(selected), "Reset did not invalidate persistent index/range")

def shift_index(+model: Qt.QStandardItemModel, +index: Qt.QModelIndex) -> Qt.Action(Unit):
  Qt.QPersistentModelIndex.with(Unit, Qt.QPersistentModelIndex.new__QModelIndex(index), persistent =>
    Qt.QItemSelectionRange.with(Unit, Qt.QItemSelectionRange.new__QModelIndex(index), range => shifted(model, index, persistent, range)))

def shifting(+model: Qt.QStandardItemModel) -> Qt.Action(Unit):
  Qt.QModelIndex.with(Unit, Qt.QStandardItemModel.index__Int32_Int32(model, Qt.Int32{0}, Qt.Int32{0}), index => shift_index(model, index))

def deleted(+model: Qt.QStandardItemModel, +index: Qt.QModelIndex) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QStandardItemModel.destroy(model)
    expired: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.QModelIndex.isValid(index))
    stale(Bool, expired)

def deleting(+model: Qt.QStandardItemModel) -> Qt.Action(Unit):
  Qt.QModelIndex.with(Unit, Qt.QStandardItemModel.index__Int32_Int32(model, Qt.Int32{0}, Qt.Int32{0}), index => deleted(model, index))

# The handler's index arguments are valid during the call only. It records the
# handle of the first one, which the test checks afterwards.
def record_index(+probe: Qt.QObject, +first: Qt.QModelIndex, last: Qt.QModelIndex) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    valid: Bool <- Qt.QModelIndex.isValid(first)
    row: Qt.Int32 <- Qt.QModelIndex.row(last)
    require(valid && U32.is_eq(Qt.Int32.word(row), 0), "Signal index argument was not usable during the call")
    Qt.QObject.setObjectName(probe, U32.show(Qt.QModelIndex.word(first)))

def data_changed(probe: Qt.QObject, first: Qt.QModelIndex, last: Qt.QModelIndex, roles: List<&2, Qt.Int32>) -> Qt.Action(Unit):
  record_index(probe, first, last)

def expired_argument(found: Maybe<&2, U32>) -> Qt.Action(Unit):
  match found:
    case None{}: Qt.Action.fail(Unit, 1, "dataChanged recorded no handle")
    case Some{word}:
      do Qt.Action<Unit>:
        expired: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.QModelIndex.isValid(Qt.QModelIndex{word}))
        stale(Bool, expired)

def emitted(+model: Qt.QStandardItemModel, +index: Qt.QModelIndex, value: Qt.QVariant, +probe: Qt.QObject, connection: Qt.Connection) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    changed: Bool <- Qt.QStandardItemModel.setData__QModelIndex_QVariant_Int32(model, index, value, Qt.Int32{256})
    require(changed, "Signal test model refused data")
    +recorded: String <- Qt.QObject.objectName(probe)
    require(Bool.not(String.is_empty(recorded)), "dataChanged did not run during setData")
    expired_argument(U32.read(recorded))

def signal_probe(+model: Qt.QStandardItemModel, +index: Qt.QModelIndex, +value: Qt.QVariant, +probe: Qt.QObject) -> Qt.Action(Unit):
  Qt.Connection.with(Unit, Qt.Signal.connect(~Qt.QStandardItemModel.dataChanged(), ~Qt.QObject, ~data_changed, model, probe),
    connection => emitted(model, index, value, probe, connection))

def signal_index(+model: Qt.QStandardItemModel, +index: Qt.QModelIndex, +value: Qt.QVariant) -> Qt.Action(Unit):
  Qt.QObject.with(Unit, Qt.QObject.new(), probe => signal_probe(model, index, value, probe))

def signal_value(+model: Qt.QStandardItemModel, +index: Qt.QModelIndex) -> Qt.Action(Unit):
  Qt.QVariant.with(Unit, Qt.QVariant.fromString("change"), value => signal_index(model, index, value))

def signalling(+model: Qt.QStandardItemModel) -> Qt.Action(Unit):
  Qt.QModelIndex.with(Unit, Qt.QStandardItemModel.index__Int32_Int32(model, Qt.Int32{0}, Qt.Int32{0}), index => signal_value(model, index))

def variant_reset(+model: Qt.QStandardItemModel, +value: Qt.QVariant) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QStandardItemModel.clear(model)
    expired: Result<&1, &1, U32 & String, Qt.QModelIndex> <- Qt.Action.attempt(Qt.QModelIndex, Qt.QVariant.to_QModelIndex(value))
    stale(Qt.QModelIndex, expired)

def variant_index(+model: Qt.QStandardItemModel, index: Qt.QModelIndex) -> Qt.Action(Unit):
  Qt.QVariant.with(Unit, Qt.QVariant.from_QModelIndex(index), value => variant_reset(model, value))

def variant_model(+model: Qt.QStandardItemModel) -> Qt.Action(Unit):
  Qt.QModelIndex.with(Unit, Qt.QStandardItemModel.index__Int32_Int32(model, Qt.Int32{0}, Qt.Int32{0}), index => variant_index(model, index))

def native_variant(+model: Qt.QStandardItemModel, +index: Qt.QModelIndex, value: Qt.QVariant) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    stored: Bool <- Qt.QStandardItemModel.setData__QModelIndex_QVariant_Int32(model, index, value, Qt.Int32{257})
    require(stored, "Model refused its index-valued role")
    Qt.QVariant.with(Unit, Qt.QStandardItemModel.data__QModelIndex_Int32(model, index, Qt.Int32{257}), returned => variant_reset(model, returned))

def native_variant_index(+model: Qt.QStandardItemModel, +index: Qt.QModelIndex) -> Qt.Action(Unit):
  Qt.QVariant.with(Unit, Qt.QVariant.from_QModelIndex(index), value => native_variant(model, index, value))

def native_variant_model(+model: Qt.QStandardItemModel) -> Qt.Action(Unit):
  Qt.QModelIndex.with(Unit, Qt.QStandardItemModel.index__Int32_Int32(model, Qt.Int32{0}, Qt.Int32{0}), index => native_variant_index(model, index))

def pointer_changes(+model: Qt.QStandardItemModel, +ordinary: Qt.ModelData, +persistent: Qt.ModelData) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    same: Bool <- Qt.ModelData.same(ordinary, persistent)
    require(same, "Ordinary/persistent internal data identities differ")
    inserted: Bool <- Qt.QStandardItemModel.insertRow__Int32(model, Qt.Int32{0})
    require(inserted, "Internal data fixture could not insert a row")
    expired: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.ModelData.isNull(ordinary))
    stale(Bool, expired)
    empty: Bool <- Qt.ModelData.isNull(persistent)
    require(Bool.not(empty), "Persistent internal data lost its item after insertion")
    Qt.QStandardItemModel.clear(model)
    removed: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.ModelData.isNull(persistent))
    stale(Bool, removed)

def persistent_data(+model: Qt.QStandardItemModel, +index: Qt.QModelIndex, +persistent: Qt.QPersistentModelIndex) -> Qt.Action(Unit):
  Qt.ModelData.with(Unit, Qt.QModelIndex.internalPointer(index), ordinary =>
    Qt.ModelData.with(Unit, Qt.QPersistentModelIndex.internalPointer(persistent), durable => pointer_changes(model, ordinary, durable)))

def data_index(+model: Qt.QStandardItemModel, +index: Qt.QModelIndex) -> Qt.Action(Unit):
  Qt.QPersistentModelIndex.with(Unit, Qt.QPersistentModelIndex.new__QModelIndex(index), persistent => persistent_data(model, index, persistent))

def data_model(+model: Qt.QStandardItemModel) -> Qt.Action(Unit):
  Qt.QModelIndex.with(Unit, Qt.QStandardItemModel.index__Int32_Int32(model, Qt.Int32{0}, Qt.Int32{0}), index => data_index(model, index))

def index_row(index: Qt.QModelIndex) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    row: Qt.Int32 <- Qt.QModelIndex.row(index)
    require(U32.is_eq(Qt.Int32.word(row), 0), "Copied index changed its row")

def variant_read(value: Qt.QVariant) -> Qt.Action(Unit):
  Qt.QModelIndex.with(Unit, Qt.QVariant.to_QModelIndex(value), index_row)

def storage_expired(+model: Qt.QStandardItemModel, +source: Qt.QVariant, +storage: Qt.MetaStorage, +value: Qt.QVariant) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QVariant.destroy(source)
    Qt.MetaStorage.destroy(storage)
    variant_read(value)
    Qt.QStandardItemModel.destroy(model)
    result: Result<&1, &1, U32 & String, Qt.QModelIndex> <- Qt.Action.attempt(Qt.QModelIndex, Qt.QVariant.to_QModelIndex(value))
    stale(Qt.QModelIndex, result)

def storage_roundtrip(+model: Qt.QStandardItemModel, +source: Qt.QVariant, +storage: Qt.MetaStorage) -> Qt.Action(Unit):
  Qt.QVariant.with(Unit, Qt.MetaStorage.toVariant(storage), value => storage_expired(model, source, storage, value))

def storage_variant(+model: Qt.QStandardItemModel, +source: Qt.QVariant) -> Qt.Action(Unit):
  Qt.MetaStorage.with(Unit, Qt.MetaStorage.fromVariant(source), storage => storage_roundtrip(model, source, storage))

def storage_index(+model: Qt.QStandardItemModel, index: Qt.QModelIndex) -> Qt.Action(Unit):
  Qt.QVariant.with(Unit, Qt.QVariant.from_QModelIndex(index), value => storage_variant(model, value))

def storage_model(+model: Qt.QStandardItemModel) -> Qt.Action(Unit):
  Qt.QModelIndex.with(Unit, Qt.QStandardItemModel.index__Int32_Int32(model, Qt.Int32{0}, Qt.Int32{0}), index => storage_index(model, index))

def assigned_variant(+model: Qt.QStandardItemModel, +original: Qt.QVariant, +copied: Qt.QVariant, +assigned: Qt.QVariant) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QVariant.assign(assigned, copied)
    Qt.QVariant.destroy(original)
    Qt.QVariant.destroy(copied)
    variant_read(assigned)
    variant_reset(model, assigned)

def copied_variant(+model: Qt.QStandardItemModel, +original: Qt.QVariant, +copied: Qt.QVariant) -> Qt.Action(Unit):
  Qt.QVariant.with(Unit, Qt.QVariant.fromString("replace me"), assigned => assigned_variant(model, original, copied, assigned))

def copy_variant(+model: Qt.QStandardItemModel, +value: Qt.QVariant) -> Qt.Action(Unit):
  Qt.QVariant.with(Unit, Qt.QVariant.copy(value), copied => copied_variant(model, value, copied))

def copy_index(+model: Qt.QStandardItemModel, index: Qt.QModelIndex) -> Qt.Action(Unit):
  Qt.QVariant.with(Unit, Qt.QVariant.from_QModelIndex(index), value => copy_variant(model, value))

def copy_model(+model: Qt.QStandardItemModel) -> Qt.Action(Unit):
  Qt.QModelIndex.with(Unit, Qt.QStandardItemModel.index__Int32_Int32(model, Qt.Int32{0}, Qt.Int32{0}), index => copy_index(model, index))

def swapped_variant(+model: Qt.QStandardItemModel, +indexed: Qt.QVariant, +scalar: Qt.QVariant) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QVariant.swap(indexed, scalar)
    text: String <- Qt.QVariant.toString(indexed)
    require(String.eq(text, "scalar"), "QVariant swap lost the independent value")
    variant_read(scalar)
    Qt.QStandardItemModel.clear(model)
    preserved: String <- Qt.QVariant.toString(indexed)
    require(String.eq(preserved, "scalar"), "QVariant swap retained the wrong model origin")
    result: Result<&1, &1, U32 & String, Qt.QModelIndex> <- Qt.Action.attempt(Qt.QModelIndex, Qt.QVariant.to_QModelIndex(scalar))
    stale(Qt.QModelIndex, result)

def swap_variant(+model: Qt.QStandardItemModel, +value: Qt.QVariant) -> Qt.Action(Unit):
  Qt.QVariant.with(Unit, Qt.QVariant.fromString("scalar"), scalar => swapped_variant(model, value, scalar))

def swap_index(+model: Qt.QStandardItemModel, index: Qt.QModelIndex) -> Qt.Action(Unit):
  Qt.QVariant.with(Unit, Qt.QVariant.from_QModelIndex(index), value => swap_variant(model, value))

def swap_model(+model: Qt.QStandardItemModel) -> Qt.Action(Unit):
  Qt.QModelIndex.with(Unit, Qt.QStandardItemModel.index__Int32_Int32(model, Qt.Int32{0}, Qt.Int32{0}), index => swap_index(model, index))

def unobserved_deleted(+source: Qt.QStandardItemModel, +holder: Qt.QStandardItemModel, +position: Qt.QModelIndex, value: Qt.QVariant) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    stored: Bool <- Qt.QStandardItemModel.setData__QModelIndex_QVariant_Int32(holder, position, value, Qt.Int32{258})
    require(stored, "Model refused a foreign index-valued role")
    Qt.QStandardItemModel.destroy(source)
    expired: Result<&1, &1, U32 & String, Qt.QVariant> <- Qt.Action.attempt(Qt.QVariant, Qt.QStandardItemModel.data__QModelIndex_Int32(holder, position, Qt.Int32{258}))
    stale(Qt.QVariant, expired)

def unobserved_index(+source: Qt.QStandardItemModel, +holder: Qt.QStandardItemModel, +position: Qt.QModelIndex, index: Qt.QModelIndex) -> Qt.Action(Unit):
  Qt.QVariant.with(Unit, Qt.QVariant.from_QModelIndex(index), value => unobserved_deleted(source, holder, position, value))

def unobserved_source(+holder: Qt.QStandardItemModel, +position: Qt.QModelIndex, +source: Qt.QStandardItemModel) -> Qt.Action(Unit):
  Qt.QModelIndex.with(Unit, Qt.QStandardItemModel.index__Int32_Int32(source, Qt.Int32{0}, Qt.Int32{0}), index => unobserved_index(source, holder, position, index))

def unobserved_position(+holder: Qt.QStandardItemModel, +position: Qt.QModelIndex) -> Qt.Action(Unit):
  Qt.QStandardItemModel.with(Unit, Qt.QStandardItemModel.new__Int32_Int32_QObject(Qt.Int32{1}, Qt.Int32{1}, Qt.QObject{0}), source => unobserved_source(holder, position, source))

def unobserved_model(+holder: Qt.QStandardItemModel) -> Qt.Action(Unit):
  Qt.QModelIndex.with(Unit, Qt.QStandardItemModel.index__Int32_Int32(holder, Qt.Int32{0}, Qt.Int32{0}), position => unobserved_position(holder, position))

def model(body: Qt.QStandardItemModel -> Qt.Action(Unit)) -> Qt.Action(Unit):
  Qt.QStandardItemModel.with(Unit, Qt.QStandardItemModel.new__Int32_Int32_QObject(Qt.Int32{1}, Qt.Int32{1}, Qt.QObject{0}), body)

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    model(value => shifting(value))
    model(value => deleting(value))
    model(value => signalling(value))
    model(value => variant_model(value))
    model(value => native_variant_model(value))
    model(value => data_model(value))
    model(value => copy_model(value))
    model(value => swap_model(value))
    model(value => storage_model(value))
    model(value => unobserved_model(value))
    objects: U32 <- Qt.Runtime.liveObjects()
    pins: U32 <- Qt.Runtime.liveRetentions()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(pins, 0) && U32.is_eq(connections, 0), "Model index guards leaked values")
    Qt.Action.lift(Unit, IO.print("QT612_MODEL_INDICES_OK shift=1 reset=1 persistent=1 range=1 destruction=1 signal_arguments=1 variant=1 native_variant=1 opaque_data=1 cleanup=1 connections=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
