import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expected(-A: Type, result: Result<&1, &1, U32 & String, A>, code: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(actual, message)}: require(U32.is_eq(actual, code), message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected native result ownership rejection")

def widgets() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +model: Qt.QFileSystemModel <- Qt.QFileSystemModel.new()
    +provider: Qt.QAbstractFileIconProvider <- Qt.QFileSystemModel.iconProvider(model)
    flags: Qt.Flags_QAbstractFileIconProvider__Option <- Qt.QAbstractFileIconProvider.options(provider)
    Qt.QAbstractFileIconProvider.setOptions(provider, flags)
    denied: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QAbstractFileIconProvider.destroy(provider))
    expected(Unit, denied, 1)
    +replacement: Qt.QFileIconProvider <- Qt.QFileIconProvider.new()
    +base: Qt.QAbstractFileIconProvider = Qt.QFileIconProvider.as_QAbstractFileIconProvider(replacement)
    Qt.QFileSystemModel.setIconProvider(model, base)
    stale: Result<&1, &1, U32 & String, Qt.Flags_QAbstractFileIconProvider__Option> <- Qt.Action.attempt(Qt.Flags_QAbstractFileIconProvider__Option, Qt.QAbstractFileIconProvider.options(provider))
    expected(Qt.Flags_QAbstractFileIconProvider__Option, stale, 116)
    selected: Qt.QAbstractFileIconProvider <- Qt.QFileSystemModel.iconProvider(model)
    require(U32.is_eq(Qt.QAbstractFileIconProvider.word(selected), Qt.QAbstractFileIconProvider.word(base)), "Native icon provider lost its identity")
    +factory: Qt.QItemEditorFactory <- Qt.QItemEditorFactory.defaultFactory()
    name: Qt.QByteArray <- Qt.QItemEditorFactory.valuePropertyName(factory, Qt.Int32{2})
    length: Qt.Int64 <- Qt.QByteArray.size(name)
    require(Bool.not(U32.is_eq(Qt.Int64.lo(length), 0)), "The default native editor factory could not be used")
    denied: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QItemEditorFactory.destroy(factory))
    expected(Unit, denied, 1)

def quick() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +window: Qt.QQuickWindow <- Qt.QQuickWindow.new()
    +controller: Qt.QQmlIncubationController <- Qt.QQuickWindow.incubationController(window)
    count: Qt.Int32 <- Qt.QQmlIncubationController.incubatingObjectCount(controller)
    require(U32.is_eq(Qt.Int32.word(count), 0), "A fresh window's controller was unavailable")
    Qt.QQuickWindow.destroy(window)
    stale: Result<&1, &1, U32 & String, Qt.Int32> <- Qt.Action.attempt(Qt.Int32, Qt.QQmlIncubationController.incubatingObjectCount(controller))
    expected(Qt.Int32, stale, 116)

def accessibility() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +edit: Qt.QLineEdit <- Qt.QLineEdit.new()
    Qt.QLineEdit.setText(edit, "abc")
    +interface: Qt.QAccessibleInterface <- Qt.QAccessible.queryAccessibleInterface(Qt.QLineEdit.as_QObject(edit))
    +text: Qt.QAccessibleTextInterface <- Qt.QAccessibleInterface.textInterface(interface)
    count: Qt.Int32 <- Qt.QAccessibleTextInterface.characterCount(text)
    require(U32.is_eq(Qt.Int32.word(count), 3), "A Qt-created text facet was unavailable")
    +editable: Qt.QAccessibleEditableTextInterface <- Qt.QAccessibleInterface.editableTextInterface(interface)
    Qt.QAccessibleEditableTextInterface.insertText(editable, Qt.Int32{3}, "d")
    value: String <- Qt.QLineEdit.text(edit)
    require(String.eq(value, "abcd"), "A native multiple-inheritance facet did not update its widget")
    +actions: Qt.QAccessibleActionInterface <- Qt.QAccessibleInterface.actionInterface(interface)
    _: List<&2, String> <- Qt.QAccessibleActionInterface.actionNames(actions)
    _: Qt.QAccessibleAttributesInterface <- Qt.QAccessibleInterface.attributesInterface(interface)
    _: Qt.QAccessibleSelectionInterface <- Qt.QAccessibleInterface.selectionInterface(interface)
    _: Qt.QAccessibleTableCellInterface <- Qt.QAccessibleInterface.tableCellInterface(interface)
    _: Qt.QAccessibleValueInterface <- Qt.QAccessibleInterface.valueInterface(interface)
    Qt.QLineEdit.destroy(edit)
    stale: Result<&1, &1, U32 & String, Qt.Int32> <- Qt.Action.attempt(Qt.Int32, Qt.QAccessibleTextInterface.characterCount(text))
    expected(Qt.Int32, stale, 116)

def spacer() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +layout: Qt.QHBoxLayout <- Qt.QHBoxLayout.new()
    Qt.QHBoxLayout.addStretch__Int32(layout, Qt.Int32{1})
    +item: Qt.QLayoutItem <- Qt.QHBoxLayout.itemAt(layout, Qt.Int32{0})
    +spacer: Qt.QSpacerItem <- Qt.QLayoutItem.spacerItem(item)
    _: Qt.QSize <- Qt.QSpacerItem.sizeHint(spacer)
    Qt.QHBoxLayout.destroy(layout)
    stale: Result<&1, &1, U32 & String, Qt.QSize> <- Qt.Action.attempt(Qt.QSize, Qt.QSpacerItem.sizeHint(spacer))
    expected(Qt.QSize, stale, 116)

def future_mutex() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +first: Qt.QFutureInterfaceBase <- Qt.QFutureInterfaceBase.new()
    +second: Qt.QFutureInterfaceBase <- Qt.QFutureInterfaceBase.new()
    +mutex: Qt.QMutex <- Qt.QFutureInterfaceBase.mutex(first)
    locked: Bool <- Qt.QMutex.tryLock(mutex)
    require(locked, "A native reference getter did not expose its mutex")
    Qt.QMutex.unlock(mutex)
    Qt.QFutureInterfaceBase.swap(first, second)
    stale: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.QMutex.tryLock(mutex))
    expected(Bool, stale, 116)

def sql_query(+database: Qt.QSqlDatabase) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +driver: Qt.QSqlDriver <- Qt.QSqlDatabase.driver(database)
    +result: Qt.QSqlResult <- Qt.QSqlDriver.createResult(driver)
    active: Bool <- Qt.QSqlResult.isActive(result)
    require(Bool.not(active), "A new driver result was unexpectedly active")
    +query: Qt.QSqlQuery <- Qt.QSqlQuery.new__QSqlResult(result)
    denied: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QSqlResult.destroy(result))
    expected(Unit, denied, 1)
    executed: Bool <- Qt.QSqlQuery.exec__String(query, "select 42")
    require(executed, "Could not execute a query built from its driver's result")
    +view: Qt.QSqlResult <- Qt.QSqlQuery.result(query)
    text: String <- Qt.QSqlResult.lastQuery(view)
    require(String.eq(text, "select 42"), "The native SQL result was unavailable")
    +copy: Qt.QSqlQuery <- Qt.QSqlQuery.new__QSqlQuery(query)
    before: U32 <- Qt.Runtime.liveRetentions()
    Qt.QSqlQuery.destroy(query)
    after: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(before, U32.add(after, 1)), "Query copies did not retain independent driver origins")
    stale: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QSqlResult.lastQuery(view))
    expected(String, stale, 116)
    +snapshot: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.QSqlQuery.arg(), copy)
    Qt.QSqlQuery.destroy(copy)
    +restored: Qt.QSqlQuery <- Qt.QVariant.toValue(~Qt.QSqlQuery.arg(), snapshot)
    +copied_result: Qt.QSqlResult <- Qt.QSqlQuery.result(restored)
    text: String <- Qt.QSqlResult.lastQuery(copied_result)
    require(String.eq(text, "select 42"), "A boxed query lost its native result or driver origin")

def sql() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +database: Qt.QSqlDatabase <- Qt.QSqlDatabase.addDatabase__String_String("QSQLITE", "native-result-views")
    Qt.QSqlDatabase.setDatabaseName(database, ":memory:")
    opened: Bool <- Qt.QSqlDatabase.open(database)
    require(opened, "Could not open SQLite")
    Qt.scoped(Unit, sql_query(database))
    Qt.QSqlDatabase.close(database)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, widgets())
    Qt.scoped(Unit, quick())
    Qt.scoped(Unit, accessibility())
    Qt.scoped(Unit, spacer())
    Qt.scoped(Unit, future_mutex())
    Qt.scoped(Unit, sql())
    Qt.QSqlDatabase.removeDatabase("native-result-views")
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Native result descriptors leaked")
    edges: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(edges, 0), "Native result dependencies leaked")
    Qt.Action.lift(Unit, IO.print("QT612_NATIVE_RESULT_VIEWS_OK widgets=1 static_factory=1 quick_controller=1 accessible_facets=1 native_spacer=1 sql_factory=1 query_copies=1 variant_origins=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
