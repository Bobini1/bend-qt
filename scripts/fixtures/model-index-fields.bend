import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def stale(value: Result<&1, &1, U32 & String, String>) -> Qt.Action(Unit):
  match value:
    case Fail{(code, message)}: require(U32.is_eq(code, 116), "Wrong aggregate index error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Stale aggregate QModelIndex reached native access")

def failed(~A: Type, expected: U32, value: Result<&1, &1, U32 & String, A>) -> Qt.Action(Unit):
  match value:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong field failure: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Invalid model field operation succeeded")

def invalidated(+model: Qt.QAbstractItemModel, original: Qt.QStyleOptionViewItem, +copy: Qt.QStyleOptionViewItem, mode: U32) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QStyleOptionViewItem.destroy(original)
    Qt.Fixture.mutateIndexModel(model, mode)
    result: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QStyleOptionViewItem.Fields.text(copy))
    stale(result)
    escaped: Result<&1, &1, U32 & String, Qt.QModelIndex> <- Qt.Action.attempt(Qt.QModelIndex, Qt.QStyleOptionViewItem.Fields.index(copy))
    failed(Qt.QModelIndex, 116, escaped)

def option(+model: Qt.QAbstractItemModel, +index: Qt.QModelIndex, +value: Qt.QStyleOptionViewItem, mode: U32) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QStyleOptionViewItem.Fields.set_index(value, index)
    Qt.QModelIndex.destroy(index)
    Qt.QStyleOptionViewItem.with(Unit, Qt.QStyleOptionViewItem.new__QStyleOptionViewItem(value), copy => invalidated(model, value, copy, mode))

def index(+model: Qt.QAbstractItemModel, +value: Qt.QModelIndex, mode: U32) -> Qt.Action(Unit):
  Qt.QStyleOptionViewItem.with(Unit, Qt.QStyleOptionViewItem.new(), item => option(model, value, item, mode))

def model(+value: Qt.QAbstractItemModel, mode: U32) -> Qt.Action(Unit):
  Qt.QModelIndex.with(Unit, Qt.Fixture.index(value), item => index(value, item, mode))

def valid_index(value: Qt.QModelIndex) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    valid: Bool <- Qt.QModelIndex.isValid(value)
    require(valid, "Replacement lost its valid model index")

def replacement_copy(+old_model: Qt.QAbstractItemModel, +old_index: Qt.QModelIndex, +next_index: Qt.QModelIndex, +value: Qt.QStyleOptionViewItem, +copy: Qt.QStyleOptionViewItem) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QStyleOptionViewItem.Fields.set_index(value, next_index)
    before: U32 <- Qt.Runtime.liveObjects()
    held_before: U32 <- Qt.Runtime.liveRetentions()
    Qt.Fixture.failAfter(1)
    allocation: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QStyleOptionViewItem.Fields.set_index(value, old_index))
    failed(Unit, 12, allocation)
    after: U32 <- Qt.Runtime.liveObjects()
    held_after: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(before, after) && U32.is_eq(held_before, held_after), "Failed field conversion leaked its private origin")
    Qt.Fixture.mutateIndexModel(old_model, 0)
    stale_copy: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QStyleOptionViewItem.Fields.text(copy))
    stale(stale_copy)
    rejected: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QStyleOptionViewItem.Fields.set_index(value, old_index))
    failed(Unit, 116, rejected)
    Qt.QModelIndex.with(Unit, Qt.QStyleOptionViewItem.Fields.index(value), valid_index)

def replacement_option(+old_model: Qt.QAbstractItemModel, +old_index: Qt.QModelIndex, +next_index: Qt.QModelIndex, +value: Qt.QStyleOptionViewItem) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QStyleOptionViewItem.Fields.set_index(value, old_index)
    Qt.QStyleOptionViewItem.with(Unit, Qt.QStyleOptionViewItem.new__QStyleOptionViewItem(value), copy => replacement_copy(old_model, old_index, next_index, value, copy))

def replacement_index(+old_model: Qt.QAbstractItemModel, +old_index: Qt.QModelIndex, +next_index: Qt.QModelIndex) -> Qt.Action(Unit):
  Qt.QStyleOptionViewItem.with(Unit, Qt.QStyleOptionViewItem.new(), value => replacement_option(old_model, old_index, next_index, value))

def replacement_model(+old_model: Qt.QAbstractItemModel, +old_index: Qt.QModelIndex, next_model: Qt.QAbstractItemModel) -> Qt.Action(Unit):
  Qt.QModelIndex.with(Unit, Qt.Fixture.index(next_model), next_index => replacement_index(old_model, old_index, next_index))

def replacement_old_index(+old_model: Qt.QAbstractItemModel, +old_index: Qt.QModelIndex) -> Qt.Action(Unit):
  Qt.QAbstractItemModel.with(Unit, Qt.Fixture.newIndexModel(), next_model => replacement_model(old_model, old_index, next_model))

def replacement(+old_model: Qt.QAbstractItemModel) -> Qt.Action(Unit):
  Qt.QModelIndex.with(Unit, Qt.Fixture.index(old_model), old_index => replacement_old_index(old_model, old_index))

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QAbstractItemModel.with(Unit, Qt.Fixture.newIndexModel(), value => model(value, 0))
    Qt.QAbstractItemModel.with(Unit, Qt.Fixture.newIndexModel(), value => model(value, 1))
    Qt.QAbstractItemModel.with(Unit, Qt.Fixture.newIndexModel(), value => model(value, 2))
    Qt.QAbstractItemModel.with(Unit, Qt.Fixture.newIndexModel(), value => replacement(value))
    count: U32 <- Qt.Runtime.liveObjects()
    held: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(count, 0) && U32.is_eq(held, 0), "Aggregate model indexes leaked registry state")
    Qt.Action.lift(Unit, IO.print("QT612_MODEL_INDEX_FIELDS_OK reset=1 removal=1 destruction=1 copy=1 replacement=1 rollback=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
