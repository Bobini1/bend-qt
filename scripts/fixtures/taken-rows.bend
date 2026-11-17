import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def error(~A: Type, expected: U32, value: Result<&1, &1, U32 & String, A>) -> Qt.Action(Unit):
  match value:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong row ownership error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Invalid row ownership operation succeeded")

def count(expected: U32) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    actual: U32 <- Qt.Fixture.liveItems()
    require(U32.is_eq(actual, expected), "Taken row item destructor count changed")

def borrowed(item: Qt.QLayoutItem) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    denied: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QLayoutItem.destroy(item))
    error(Unit, 1, denied)

def extracted(item: Qt.QLayoutItem) -> Qt.Action(Unit):
  Qt.QLayoutItem.destroy(item)

def cloned(+original: Qt.QFormLayout.TakeRowResult, +copy: Qt.QFormLayout.TakeRowResult) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    denied: Result<&1, &1, U32 & String, Qt.QLayoutItem> <- Qt.Action.attempt(Qt.QLayoutItem, Qt.QFormLayout.TakeRowResult.takeFieldItem(copy))
    error(Qt.QLayoutItem, 16, denied)
    Qt.QFormLayout.TakeRowResult.destroy(original)
    count(2)
    Qt.QLayoutItem.with(Unit, Qt.QFormLayout.TakeRowResult.Fields.labelItem(copy), borrowed)
    Qt.QLayoutItem.with(Unit, Qt.QFormLayout.TakeRowResult.takeFieldItem(copy), extracted)
    count(1)
    empty: Qt.QLayoutItem <- Qt.QFormLayout.TakeRowResult.Fields.fieldItem(copy)
    require(U32.is_eq(Qt.QLayoutItem.word(empty), 0), "Taking an item did not clear its field")

def taken(+row: Qt.QFormLayout.TakeRowResult) -> Qt.Action(Unit):
  Qt.QFormLayout.TakeRowResult.with(Unit, Qt.QFormLayout.TakeRowResult.new__QFormLayout_TakeRowResult(row), copy => cloned(row, copy))

def row_items(+layout: Qt.QFormLayout, first: Qt.QLayoutItem, second: Qt.QLayoutItem) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QFormLayout.setItem(layout, Qt.Int32{0}, Qt.QFormLayout.ItemRole.LabelRole(), first)
    Qt.QFormLayout.setItem(layout, Qt.Int32{0}, Qt.QFormLayout.ItemRole.FieldRole(), second)
    Qt.QFormLayout.TakeRowResult.with(Unit, Qt.QFormLayout.takeRow__Int32(layout, Qt.Int32{0}), value => taken(value))
    count(0)

def row_first(layout: Qt.QFormLayout, first: Qt.QLayoutItem) -> Qt.Action(Unit):
  Qt.QLayoutItem.with(Unit, Qt.Fixture.item(), second => row_items(layout, first, second))

def row_layout(layout: Qt.QFormLayout) -> Qt.Action(Unit):
  Qt.QLayoutItem.with(Unit, Qt.Fixture.item(), first => row_first(layout, first))

def fail_item(+layout: Qt.QFormLayout, item: Qt.QLayoutItem) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QFormLayout.setItem(layout, Qt.Int32{0}, Qt.QFormLayout.ItemRole.FieldRole(), item)
    Qt.Fixture.failRowAllocation()
    failed: Result<&1, &1, U32 & String, Qt.QFormLayout.TakeRowResult> <- Qt.Action.attempt(Qt.QFormLayout.TakeRowResult, Qt.QFormLayout.takeRow__Int32(layout, Qt.Int32{0}))
    error(Qt.QFormLayout.TakeRowResult, 12, failed)
    count(0)
    rows: Qt.Int32 <- Qt.QFormLayout.rowCount(layout)
    require(U32.is_eq(Qt.Int32.word(rows), 0), "Native row mutation did not complete before allocation fault")

def fail_layout(layout: Qt.QFormLayout) -> Qt.Action(Unit):
  Qt.QLayoutItem.with(Unit, Qt.Fixture.item(), item => fail_item(layout, item))

def adopted(+row: Qt.QFormLayout.TakeRowResult, item: Qt.QLayoutItem) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QFormLayout.TakeRowResult.Fields.set_labelItem(row, item)
    count(1)
    Qt.QFormLayout.TakeRowResult.Fields.set_labelItem(row, Qt.QLayoutItem{0})
    count(0)

def empty_row(row: Qt.QFormLayout.TakeRowResult) -> Qt.Action(Unit):
  Qt.QLayoutItem.with(Unit, Qt.Fixture.item(), item => adopted(row, item))

def externally_deleted(+row: Qt.QFormLayout.TakeRowResult, +item: Qt.QLayoutItem) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QFormLayout.TakeRowResult.Fields.set_labelItem(row, item)
    Qt.Fixture.deleteItem(item)
    count(0)
    stale: Result<&1, &1, U32 & String, Qt.QLayoutItem> <- Qt.Action.attempt(Qt.QLayoutItem, Qt.QFormLayout.TakeRowResult.Fields.labelItem(row))
    error(Qt.QLayoutItem, 116, stale)

def external_row(row: Qt.QFormLayout.TakeRowResult) -> Qt.Action(Unit):
  Qt.QLayoutItem.with(Unit, Qt.Fixture.item(), item => externally_deleted(row, item))

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QFormLayout.with(Unit, Qt.QFormLayout.new(), row_layout)
    Qt.QFormLayout.with(Unit, Qt.QFormLayout.new(), fail_layout)
    Qt.QFormLayout.TakeRowResult.with(Unit, Qt.QFormLayout.TakeRowResult.new(), empty_row)
    Qt.QFormLayout.TakeRowResult.with(Unit, Qt.QFormLayout.TakeRowResult.new(), external_row)
    count(0)
    objects: U32 <- Qt.Runtime.liveObjects()
    retentions: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(retentions, 0), "Taken row cleanup leaked registry state")
    Qt.Action.lift(Unit, IO.print("QT612_TAKEN_ROWS_OK copied_aggregate=1 borrowed_fields=1 explicit_take=1 setter_adoption=1 native_allocation_fault=1 items=0 objects=0 retentions=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
