import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expect_error(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Unexpected handler error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected handler failure")

def as_model(model: Qt.QAbstractListModel) -> Qt.QAbstractItemModel:
  Qt.QAbstractListModel.as_QAbstractItemModel(model)

# The data handler's value is copied before its scope ends.
def read_data(+model: Qt.QAbstractListModel, index: Qt.QModelIndex) -> Qt.Action(Unit):
  Qt.QVariant.with(Unit, Qt.QAbstractListModel.data__QModelIndex_Int32(model, index, Qt.Int32{0}), value => do Qt.Action<Unit>:
    text: String <- Qt.QVariant.toString(value)
    require(String.eq(text, "Bend handler value"), "The data handler value was not returned"))

# Qt may not delete the model while it runs one of its handlers. The handler
# calls Qt again, which runs the data handler inside this one.
def counted(+model: Qt.QAbstractListModel) -> Qt.Action(Qt.Int32):
  do Qt.Action<Qt.Int32>:
    deletion: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QAbstractListModel.destroy(model))
    expect_error(Unit, deletion, 16)
    Qt.QModelIndex.with(Unit, Qt.QModelIndex.new(), index => read_data(model, index))
    return Qt.Int32{3}

def row_count(model: Qt.QAbstractListModel, parent: Qt.QModelIndex) -> Qt.Action(Qt.Int32):
  counted(model)

def row_text(state: Unit, index: Qt.QModelIndex, role: Qt.Int32) -> Qt.Action(Qt.QVariant):
  Qt.QVariant.fromString("Bend handler value")

def failing_count(code: U32, parent: Qt.QModelIndex) -> Qt.Action(Qt.Int32):
  Qt.Action.fail(Qt.Int32, code, "Intentional handler failure")

def waiting_count(ms: U32, parent: Qt.QModelIndex) -> Qt.Action(Qt.Int32):
  do Qt.Action<Qt.Int32>:
    Qt.Action.lift(Unit, IO.sleep(ms))
    return Qt.Int32{1}

def base_header(state: Unit, section: Qt.Int32, orientation: Qt.Qt.Orientation, role: Qt.Int32) -> Qt.Action(Qt.QVariant):
  Qt.Virtual.base(Qt.QVariant)

def answered(+model: Qt.QAbstractListModel) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QAbstractItemModel.Virtual.rowCount.handle(~Qt.QAbstractListModel, ~row_count, as_model(model), model)
    Qt.QAbstractItemModel.Virtual.data.handle(~Unit, ~row_text, as_model(model), Unit{})
    count: Qt.Int32 <- Qt.QAbstractListModel.rowCount(model)
    require(U32.is_eq(Qt.Int32.word(count), 3), "Wrong abstract virtual result")

def expected_count(+model: Qt.QAbstractListModel, code: U32) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    result: Result<&1, &1, U32 & String, Qt.Int32> <- Qt.Action.attempt(Qt.Int32, Qt.QAbstractListModel.rowCount(model))
    expect_error(Qt.Int32, result, code)

def refused(+model: Qt.QAbstractListModel) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QAbstractItemModel.Virtual.rowCount.handle(~U32, ~failing_count, as_model(model), 41)
    expected_count(model, 41)

def waiting(+model: Qt.QAbstractListModel) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QAbstractItemModel.Virtual.rowCount.handle(~U32, ~waiting_count, as_model(model), 5)
    expected_count(model, 11)

# headerData has a C++ base implementation; rowCount has none.
def fallback(+model: Qt.QAbstractListModel) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    expected_count(model, 38)
    Qt.QAbstractItemModel.Virtual.headerData.handle(~Unit, ~base_header, as_model(model), Unit{})
    Qt.QVariant.with(Unit, Qt.QAbstractListModel.headerData__Int32_Qt_Orientation(model, Qt.Int32{0}, Qt.Qt.Orientation.Horizontal()), value => do Qt.Action<Unit>:
      section: Qt.Int32 <- Qt.QVariant.toInt32(value)
      require(U32.is_eq(Qt.Int32.word(section), 1), "The base implementation did not run"))

# Qt calls connectNotify while a signal is being connected.
def notified(probe: Qt.QObject, signal: Qt.QMetaMethod) -> Qt.Action(Unit):
  Qt.QObject.setObjectName(probe, "notified")

def ignore_name(state: Unit, name: String) -> Qt.Action(Unit):
  Qt.Action.pure(Unit, Unit{})

def connected(+probe: Qt.QObject, connection: Qt.Connection) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    name: String <- Qt.QObject.objectName(probe)
    require(String.eq(name, "notified"), "The connectNotify handler did not run")

def registration(+probe: Qt.QObject, +object: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QObject.Virtual.connectNotify.handle(~Qt.QObject, ~notified, object, probe)
    Qt.Connection.with(Unit, Qt.Signal.connect(~Qt.QObject.objectNameChanged(), ~Unit, ~ignore_name, object, Unit{}),
      connection => connected(probe, connection))

def empty() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Handler test leaked Qt resources")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QAbstractListModel.with(Unit, Qt.QAbstractListModel.newOverride(), model => answered(model))
    Qt.QAbstractListModel.with(Unit, Qt.QAbstractListModel.newOverride(), model => refused(model))
    Qt.QAbstractListModel.with(Unit, Qt.QAbstractListModel.newOverride(), model => waiting(model))
    Qt.QAbstractListModel.with(Unit, Qt.QAbstractListModel.newOverride(), model => fallback(model))
    Qt.QObject.with(Unit, Qt.QObject.new(), probe => Qt.QObject.with(Unit, Qt.QObject.newOverride(), object => registration(probe, object)))
    empty()
    Qt.Action.lift(Unit, IO.print("QT612_CALLBACKS_OK abstract=1 nested=1 typed_copy=1 deletion_guard=1 handler_error=1 wait_rejected=1 pure_virtual=1 base_fallback=1 registration=1 objects=0 connections=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
