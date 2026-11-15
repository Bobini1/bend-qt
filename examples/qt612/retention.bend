import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expect_error(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong retention error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected a checked retention error")

def pins(+expected: U32) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +actual: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(actual, expected), "Unexpected retention count: expected " ++ U32.show(expected) ++ ", got " ++ U32.show(actual))

def alive(+model: Qt.QStringListModel) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    text: String <- Qt.QStringListModel.objectName(model)
    rows: Qt.Int32 <- Qt.QStringListModel.rowCount(model)
    require(String.eq(text, "Retained🎵") && U32.is_eq(Qt.Int32.word(rows), 2), "Retained model was not usable")

def stale(model: Qt.QStringListModel) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    result: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QStringListModel.objectName(model))
    expect_error(String, result, 116)

def prepare(+model: Qt.QStringListModel) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QStringListModel.setObjectName(model, "Retained🎵")
    Qt.QStringListModel.setStringList(model, "One" <> "Two🎵" <> Nil{})

def share(first: Qt.QListView, second: Qt.QListView, +model: Qt.QStringListModel) -> Qt.Action(Qt.QStringListModel):
  do Qt.Action<Qt.QStringListModel>:
    prepare(model)
    Qt.QListView.setModel(first, Qt.QStringListModel.as_QAbstractItemModel(model))
    Qt.QListView.setModel(second, Qt.QStringListModel.as_QAbstractItemModel(model))
    strict: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QStringListModel.destroy(model))
    expect_error(Unit, strict, 16)
    return model

def dead_input(+view: Qt.QListView, +model: Qt.QStringListModel) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QStringListModel.destroy(model)
    rejected: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QListView.setModel(view, Qt.QStringListModel.as_QAbstractItemModel(model)))
    expect_error(Unit, rejected, 116)

def shared_views(+first: Qt.QListView, +second: Qt.QListView) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +model: Qt.QStringListModel <- Qt.QStringListModel.with(Qt.QStringListModel, Qt.QStringListModel.new(), value => share(first, second, value))
    pins(2)
    alive(model)
    strict: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QStringListModel.destroy(model))
    expect_error(Unit, strict, 16)
    Qt.QListView.setModel(first, Qt.QStringListModel.as_QAbstractItemModel(model))
    pins(2)
    wrong: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QListView.setModel(first, Qt.QAbstractItemModel{Qt.QListView.word(second)}))
    expect_error(Unit, wrong, 22)
    Qt.QStringListModel.with(Unit, Qt.QStringListModel.new(), dead => dead_input(first, dead))
    alias: Qt.QAbstractItemModel <- Qt.QListView.model(first)
    require(U32.is_eq(Qt.QAbstractItemModel.word(alias), Qt.QStringListModel.word(model)), "Rejected setter changed the native model")
    pins(2)
    Qt.QListView.setModel(first, Qt.QAbstractItemModel{0})
    pins(1)
    alive(model)
    Qt.QListView.destroy(second)
    stale(model)
    pins(0)

def shared_first(first: Qt.QListView) -> Qt.Action(Unit):
  Qt.QListView.with(Unit, Qt.QListView.new(), second => shared_views(first, second))

def unexpired_model(+model: Qt.QStringListModel) -> Qt.Action(Qt.QStringListModel):
  do Qt.Action<Qt.QStringListModel>:
    prepare(model)
    Qt.QListView.with(Unit, Qt.QListView.new(), view => Qt.QListView.setModel(view, Qt.QStringListModel.as_QAbstractItemModel(model)))
    pins(0)
    # Dropping a retention edge must not delete an object whose own scope
    # has not ended yet.
    alive(model)
    return model

def attach(view: Qt.QListView, +model: Qt.QStringListModel) -> Qt.Action(Qt.QStringListModel):
  do Qt.Action<Qt.QStringListModel>:
    prepare(model)
    Qt.QListView.setModel(view, Qt.QStringListModel.as_QAbstractItemModel(model))
    return model

def replacement(+view: Qt.QListView) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    old: Qt.QStringListModel <- Qt.QStringListModel.with(Qt.QStringListModel, Qt.QStringListModel.new(), value => attach(view, value))
    +current: Qt.QStringListModel <- Qt.QStringListModel.with(Qt.QStringListModel, Qt.QStringListModel.new(), value => attach(view, value))
    stale(old)
    alive(current)
    pins(1)
    Qt.QListView.setModel(view, Qt.QAbstractItemModel{0})
    stale(current)
    pins(0)

def fail_retained(view: Qt.QListView, +model: Qt.QStringListModel) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    ignored: Qt.QStringListModel <- attach(view, model)
    Qt.Action.fail(Unit, 81, "Retained body failed")

def failed_scope(+view: Qt.QListView) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +model: Qt.QStringListModel <- Qt.QStringListModel.new()
    failed: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QStringListModel.with(Unit, Qt.Action.pure(Qt.QStringListModel, model), value => fail_retained(view, value)))
    expect_error(Unit, failed, 81)
    alive(model)
    Qt.QListView.setModel(view, Qt.QAbstractItemModel{0})
    stale(model)

def child_model(view: Qt.QListView, parent: Qt.QObject) -> Qt.Action(Qt.QStringListModel):
  Qt.QStringListModel.with(Qt.QStringListModel, Qt.QStringListModel.new__QObject(parent), value => attach(view, value))

def ancestor(+view: Qt.QListView) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +parent: Qt.QObject <- Qt.QObject.new()
    Qt.QObject.setObjectName(parent, "Retained ancestor")
    +child: Qt.QStringListModel <- Qt.QObject.with(Qt.QStringListModel, Qt.Action.pure(Qt.QObject, parent), value => child_model(view, value))
    text: String <- Qt.QObject.objectName(parent)
    require(String.eq(text, "Retained ancestor"), "Parent scope destroyed a retained descendant")
    alive(child)
    strict: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QObject.destroy(parent))
    expect_error(Unit, strict, 16)
    Qt.QListView.setModel(view, Qt.QAbstractItemModel{0})
    stale(child)
    gone: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QObject.objectName(parent))
    expect_error(String, gone, 116)
    pins(0)

def cycles(+first: Qt.QSortFilterProxyModel, +second: Qt.QSortFilterProxyModel) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QSortFilterProxyModel.setSourceModel(first, Qt.QSortFilterProxyModel.as_QAbstractItemModel(second))
    cyclic: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QSortFilterProxyModel.setSourceModel(second, Qt.QSortFilterProxyModel.as_QAbstractItemModel(first)))
    expect_error(Unit, cyclic, 40)
    self_cycle: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QSortFilterProxyModel.setSourceModel(first, Qt.QSortFilterProxyModel.as_QAbstractItemModel(first)))
    expect_error(Unit, self_cycle, 40)
    parent_cycle: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QSortFilterProxyModel.setParent(first, Qt.QSortFilterProxyModel.as_QObject(second)))
    expect_error(Unit, parent_cycle, 40)
    no_source: Qt.QAbstractItemModel <- Qt.QSortFilterProxyModel.sourceModel(second)
    no_parent: Qt.QObject <- Qt.QSortFilterProxyModel.parent(first)
    require(U32.is_eq(Qt.QAbstractItemModel.word(no_source), 0) && U32.is_eq(Qt.QObject.word(no_parent), 0), "Cycle rejection mutated Qt state")
    pins(1)
    Qt.QSortFilterProxyModel.setSourceModel(first, Qt.QAbstractItemModel{0})
    pins(0)

def cycle_first(first: Qt.QSortFilterProxyModel) -> Qt.Action(Unit):
  Qt.QSortFilterProxyModel.with(Unit, Qt.QSortFilterProxyModel.new(), second => cycles(first, second))

type Chain is Data:
  Chain{middle: Qt.QSortFilterProxyModel, base: Qt.QStringListModel}

def chain_base(top: Qt.QSortFilterProxyModel, +middle: Qt.QSortFilterProxyModel, +base: Qt.QStringListModel) -> Qt.Action(Chain):
  do Qt.Action<Chain>:
    prepare(base)
    Qt.QSortFilterProxyModel.setSourceModel(middle, Qt.QStringListModel.as_QAbstractItemModel(base))
    Qt.QSortFilterProxyModel.setSourceModel(top, Qt.QSortFilterProxyModel.as_QAbstractItemModel(middle))
    return Chain{middle, base}

def chain_middle(top: Qt.QSortFilterProxyModel, +middle: Qt.QSortFilterProxyModel) -> Qt.Action(Chain):
  Qt.QStringListModel.with(Chain, Qt.QStringListModel.new(), base => chain_base(top, middle, base))

def chain_top(+top: Qt.QSortFilterProxyModel) -> Qt.Action(Chain):
  do Qt.Action<Chain>:
    result: Chain <- Qt.QSortFilterProxyModel.with(Chain, Qt.QSortFilterProxyModel.new(), middle => chain_middle(top, middle))
    rows: Qt.Int32 <- Qt.QSortFilterProxyModel.rowCount(top)
    require(U32.is_eq(Qt.Int32.word(rows), 2), "Deferred chain was not usable")
    pins(2)
    return result

def check_chain(result: Chain) -> Qt.Action(Unit):
  match result:
    case Chain{middle, base}:
      do Qt.Action<Unit>:
        stale(base)
        gone: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QSortFilterProxyModel.objectName(middle))
        expect_error(String, gone, 116)
        pins(0)

def row_delegate(view: Qt.QTableView, row: Qt.Int32, +delegate: Qt.QStyledItemDelegate) -> Qt.Action(Qt.QStyledItemDelegate):
  do Qt.Action<Qt.QStyledItemDelegate>:
    Qt.QTableView.setItemDelegateForRow(view, row, Qt.QStyledItemDelegate.as_QAbstractItemDelegate(delegate))
    return delegate

def stale_delegate(delegate: Qt.QStyledItemDelegate) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    result: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QStyledItemDelegate.objectName(delegate))
    expect_error(String, result, 116)

def keyed_delegates(+view: Qt.QTableView) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    old: Qt.QStyledItemDelegate <- Qt.QStyledItemDelegate.with(Qt.QStyledItemDelegate, Qt.QStyledItemDelegate.new(), value => row_delegate(view, Qt.Int32{0}, value))
    +other: Qt.QStyledItemDelegate <- Qt.QStyledItemDelegate.with(Qt.QStyledItemDelegate, Qt.QStyledItemDelegate.new(), value => row_delegate(view, Qt.Int32{1}, value))
    +current: Qt.QStyledItemDelegate <- Qt.QStyledItemDelegate.with(Qt.QStyledItemDelegate, Qt.QStyledItemDelegate.new(), value => row_delegate(view, Qt.Int32{0}, value))
    stale_delegate(old)
    pins(2)
    Qt.QTableView.setItemDelegateForRow(view, Qt.Int32{0}, Qt.QStyledItemDelegate.as_QAbstractItemDelegate(current))
    pins(2)
    alias: Qt.QAbstractItemDelegate <- Qt.QTableView.itemDelegateForRow(view, Qt.Int32{1})
    require(U32.is_eq(Qt.QAbstractItemDelegate.word(alias), Qt.QStyledItemDelegate.word(other)), "Replacing row zero removed row one")
    Qt.QTableView.setItemDelegateForColumn(view, Qt.Int32{0}, Qt.QStyledItemDelegate.as_QAbstractItemDelegate(current))
    pins(3)
    Qt.QTableView.setItemDelegateForRow(view, Qt.Int32{0}, Qt.QAbstractItemDelegate{0})
    pins(2)
    Qt.QStyledItemDelegate.setObjectName(current, "Still retained by column")
    Qt.QTableView.setItemDelegateForColumn(view, Qt.Int32{0}, Qt.QAbstractItemDelegate{0})
    stale_delegate(current)
    Qt.QTableView.setItemDelegateForRow(view, Qt.Int32{1}, Qt.QAbstractItemDelegate{0})
    stale_delegate(other)
    pins(0)

def attach_selection(view: Qt.QListView, +selection: Qt.QItemSelectionModel) -> Qt.Action(Qt.QItemSelectionModel):
  do Qt.Action<Qt.QItemSelectionModel>:
    Qt.QListView.setSelectionModel(view, selection)
    return selection

def rejected_selection(+view: Qt.QListView, original: Qt.QItemSelectionModel, invalid: Qt.QItemSelectionModel) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    rejected: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QListView.setSelectionModel(view, invalid))
    expect_error(Unit, rejected, 22)
    current: Qt.QItemSelectionModel <- Qt.QListView.selectionModel(view)
    require(U32.is_eq(Qt.QItemSelectionModel.word(current), Qt.QItemSelectionModel.word(original)), "Rejected selection model replaced the native one")
    # Both selection models retain their constructor model; the view retains
    # its displayed model and its accepted selection model.
    pins(4)

def incompatible_selection(view: Qt.QListView, original: Qt.QItemSelectionModel, other: Qt.QStringListModel) -> Qt.Action(Unit):
  Qt.QItemSelectionModel.with(Unit, Qt.QItemSelectionModel.new__QAbstractItemModel_QObject(Qt.QStringListModel.as_QAbstractItemModel(other), Qt.QObject{0}), invalid => rejected_selection(view, original, invalid))

def selection_model(+view: Qt.QListView, +model: Qt.QStringListModel) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QListView.setModel(view, Qt.QStringListModel.as_QAbstractItemModel(model))
    +original: Qt.QItemSelectionModel <- Qt.QItemSelectionModel.with(Qt.QItemSelectionModel, Qt.QItemSelectionModel.new__QAbstractItemModel_QObject(Qt.QStringListModel.as_QAbstractItemModel(model), Qt.QObject{0}), value => attach_selection(view, value))
    pins(3)
    Qt.QStringListModel.with(Unit, Qt.QStringListModel.new(), other => incompatible_selection(view, original, other))
    # setModel also replaces selectionModel. Its old retention must disappear
    # even though setSelectionModel itself was not called again.
    Qt.QListView.setModel(view, Qt.QAbstractItemModel{0})
    gone: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QItemSelectionModel.objectName(original))
    expect_error(String, gone, 116)
    pins(0)

def selection_view(view: Qt.QListView) -> Qt.Action(Unit):
  Qt.QStringListModel.with(Unit, Qt.QStringListModel.new(), model => selection_model(view, model))

def fill_rows(fuel: Nat, +row: U32, +view: Qt.QTableView, +delegate: Qt.QStyledItemDelegate) -> Qt.Action(Unit):
  match fuel:
    case Zero{}: Qt.Action.pure(Unit, Unit{})
    case Succ{rest}:
      do Qt.Action<Unit>:
        Qt.QTableView.setItemDelegateForRow(view, Qt.Int32{row}, Qt.QStyledItemDelegate.as_QAbstractItemDelegate(delegate))
        fill_rows(rest, (row + 1 : U32), view, delegate)

def replace_grown(+view: Qt.QTableView, delegate: Qt.QStyledItemDelegate) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QTableView.setItemDelegateForRow(view, Qt.Int32{0}, Qt.QStyledItemDelegate.as_QAbstractItemDelegate(delegate))
    pins(5001)

def growing_registry(+view: Qt.QTableView, +delegate: Qt.QStyledItemDelegate) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    fill_rows(5000n, 0, view, delegate)
    pins(5000)
    Qt.QTableView.setItemDelegateForRow(view, Qt.Int32{5000}, Qt.QStyledItemDelegate.as_QAbstractItemDelegate(delegate))
    pins(5001)
    stored: Qt.QAbstractItemDelegate <- Qt.QTableView.itemDelegateForRow(view, Qt.Int32{5000})
    require(U32.is_eq(Qt.QAbstractItemDelegate.word(stored), Qt.QStyledItemDelegate.word(delegate)), "Growing retention changed the native row delegate")
    Qt.QStyledItemDelegate.with(Unit, Qt.QStyledItemDelegate.new(), fresh => replace_grown(view, fresh))

def capacity_view(+view: Qt.QTableView) -> Qt.Action(Unit):
  Qt.QStyledItemDelegate.with(Unit, Qt.QStyledItemDelegate.new(), delegate => growing_registry(view, delegate))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QListView.with(Unit, Qt.QListView.new(), first => shared_first(first))
    expired: Qt.QStringListModel <- Qt.QStringListModel.with(Qt.QStringListModel, Qt.QStringListModel.new(), model => unexpired_model(model))
    stale(expired)
    Qt.QListView.with(Unit, Qt.QListView.new(), view => replacement(view))
    Qt.QListView.with(Unit, Qt.QListView.new(), view => failed_scope(view))
    Qt.QListView.with(Unit, Qt.QListView.new(), view => ancestor(view))
    Qt.QSortFilterProxyModel.with(Unit, Qt.QSortFilterProxyModel.new(), first => cycle_first(first))
    chain: Chain <- Qt.QSortFilterProxyModel.with(Chain, Qt.QSortFilterProxyModel.new(), top => chain_top(top))
    check_chain(chain)
    Qt.QTableView.with(Unit, Qt.QTableView.new(), view => keyed_delegates(view))
    Qt.QListView.with(Unit, Qt.QListView.new(), view => selection_view(view))
    Qt.QTableView.with(Unit, Qt.QTableView.new(), view => capacity_view(view))
    pins(0)
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Retention tests leaked native resources")
    Qt.Action.lift(Unit, IO.print("QT612_RETENTION_OK shared=1 unexpired=1 replace=1 failure=1 ancestor=1 cycles=1 cascade=1 keyed=1 selection=1 capacity=1 objects=0 connections=0 retentions=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
