import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def count(one: Bool) -> Qt.Action(Qt.Int32):
  match one:
    case True{}: Qt.Action.pure(Qt.Int32, Qt.Int32{1})
    case False{}: Qt.Action.pure(Qt.Int32, Qt.Int32{0})

def row_count(state: Qt.QObject, parent: Qt.QModelIndex) -> Qt.Action(Qt.Int32):
  do Qt.Action<Qt.Int32>:
    value: String <- Qt.QObject.objectName(state)
    count(String.eq(value, "one"))

def data(state: Unit, index: Qt.QModelIndex, role: Qt.Int32) -> Qt.Action(Qt.QVariant):
  Qt.QVariant.fromInt32(Qt.Int32{42})

def inserted(state: Qt.QObject, parent: Qt.QModelIndex, first: Qt.Int32, last: Qt.Int32) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    require(U32.is_eq(Qt.Int32.word(first), 0) && U32.is_eq(Qt.Int32.word(last), 0), "Wrong protected insertion range")
    Qt.QObject.setObjectName(state, "inserted")

def reset(state: Qt.QObject) -> Qt.Action(Unit):
  Qt.QObject.setObjectName(state, "reset")

def model() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +model: Qt.QAbstractListModel <- Qt.QAbstractListModel.newOverride()
    +base: Qt.QAbstractItemModel = Qt.QAbstractListModel.as_QAbstractItemModel(model)
    +rows: Qt.QObject <- Qt.QObject.new()
    +events: Qt.QObject <- Qt.QObject.new()
    Qt.QAbstractItemModel.Virtual.rowCount.handle(~Qt.QObject, ~row_count, base, rows)
    Qt.QAbstractItemModel.Virtual.data.handle(~Unit, ~data, base, Unit{})
    inserted_connection: Qt.Connection <- Qt.QAbstractItemModel.connect_rowsInserted(~Qt.QObject, ~inserted, base, events)
    reset_connection: Qt.Connection <- Qt.QAbstractItemModel.connect_modelReset(~Qt.QObject, ~reset, base, events)
    +parent: Qt.QModelIndex <- Qt.QModelIndex.new()
    Qt.QAbstractListModel.beginInsertRows(model, parent, Qt.Int32{0}, Qt.Int32{0})
    Qt.QObject.setObjectName(rows, "one")
    Qt.QAbstractListModel.endInsertRows(model)
    after: Qt.Int32 <- Qt.QAbstractListModel.rowCount(model)
    require(U32.is_eq(Qt.Int32.word(after), 1), "Protected insertion did not update the model")
    name: String <- Qt.QObject.objectName(events)
    require(String.eq(name, "inserted"), "Protected insertion did not emit its native signal")
    columns: Qt.Int32 <- Qt.QAbstractListModel.columnCount(model)
    require(U32.is_eq(Qt.Int32.word(columns), 1), "A private override lost its callable public base contract")
    Qt.QAbstractListModel.beginResetModel(model)
    Qt.QObject.setObjectName(rows, "zero")
    Qt.QAbstractListModel.endResetModel(model)
    after: Qt.Int32 <- Qt.QAbstractListModel.rowCount(model)
    require(U32.is_eq(Qt.Int32.word(after), 0), "Protected reset did not update the model")
    name: String <- Qt.QObject.objectName(events)
    require(String.eq(name, "reset"), "Protected reset did not emit its native signal")

def state_property() -> Qt.Property:
  Qt.Property.define("viewState", Qt.QAbstractItemView.State.arg())

def Holder() -> Qt.ObjectType:
  Qt.QObject.define("ProtectedEnumHolder", [state_property()])

def enumeration() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +view: Qt.QTableView <- Qt.QTableView.new()
    +base: Qt.QAbstractItemView = Qt.QTableView.as_QAbstractItemView(view)
    Qt.QAbstractItemView.setState(base, Qt.QAbstractItemView.State.DraggingState())
    value: Qt.QAbstractItemView.State <- Qt.QAbstractItemView.state(base)
    require(U32.is_eq(Qt.QAbstractItemView.State.word(value), Qt.QAbstractItemView.State.word(Qt.QAbstractItemView.State.DraggingState())), "Protected enum method lost its native value")
    Qt.QAbstractItemView.setState(base, Qt.QAbstractItemView.State.NoState())
    +holder: Qt.ObjectType.Instance(Holder()) <- Qt.ObjectType.new(~Holder())
    +object: Qt.QObject = Qt.ObjectType.as_QObject(~Holder(), holder)
    Qt.Property.set(~state_property(), object, Qt.QAbstractItemView.State.EditingState())
    +boxed: Qt.QVariant <- Qt.QObject.property(object, "viewState")
    value: Qt.QAbstractItemView.State <- Qt.QVariant.toValue(~Qt.QAbstractItemView.State.arg(), boxed)
    require(U32.is_eq(Qt.QAbstractItemView.State.word(value), Qt.QAbstractItemView.State.word(Qt.QAbstractItemView.State.EditingState())), "Protected enum property changed its native metatype")

def constructors() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +device: Qt.QFileDevice <- Qt.QFileDevice.new()
    opened: Bool <- Qt.QFileDevice.isOpen(device)
    require(Bool.not(opened), "Protected QFileDevice construction returned an open device")
    +option: Qt.QStyleOptionButton <- Qt.QStyleOptionButton.new__Int32(Qt.Int32{7})
    version: Qt.Int32 <- Qt.QStyleOptionButton.Fields.version(option)
    require(U32.is_eq(Qt.Int32.word(version), 7), "Protected nonvirtual constructor lost its version")
    +original: Qt.QCloseEvent <- Qt.QCloseEvent.new()
    Qt.QCloseEvent.ignore(original)
    +copy: Qt.QCloseEvent <- Qt.QCloseEvent.new__QCloseEvent(original)
    Qt.QCloseEvent.destroy(original)
    accepted: Bool <- Qt.QCloseEvent.isAccepted(copy)
    require(Bool.not(accepted), "Protected event copy did not preserve independent state")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, model())
    Qt.scoped(Unit, enumeration())
    Qt.scoped(Unit, constructors())
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Protected API operations leaked resources")
    Qt.Action.lift(Unit, IO.print("QT612_PROTECTED_MEMBERS_OK methods=1 private_override_contract=1 enums=1 property=1 constructors=1 copy=1 native_signals=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
