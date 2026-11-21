import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def set_value(+record: Qt.QSqlRecord, value: Qt.QVariant) -> Qt.Action(Unit):
  Qt.QSqlRecord.setValue__String_QVariant(record, "score", value)

# The record is Qt's own, passed by reference and borrowed for the call:
# Qt reads the new value after the signal returns.
def before_insert(state: Unit, record: Qt.QSqlRecord) -> Qt.Action(Unit):
  Qt.QVariant.with(Unit, Qt.QVariant.fromString("42"), value => set_value(record, value))

def emit_signal(model: Qt.QSqlTableModel, connection: Qt.Connection) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    changed: U32 <- Qt.CallbackProbe.reference(model)
    require(U32.is_eq(changed, 1), "The signal returned before Bend changed the record")

def model_demo(+model: Qt.QSqlTableModel) -> Qt.Action(Unit):
  Qt.Connection.with(Unit, Qt.Signal.connect(~Qt.QSqlTableModel.beforeInsert(), ~Unit, ~before_insert, model, Unit{}), connection => emit_signal(model, connection))

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QSqlTableModel.with(Unit, Qt.QSqlTableModel.new(), model => model_demo(model))
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "The reference signal handler leaked handles")
    Qt.Action.lift(Unit, IO.print("QT612_SYNCHRONOUS_REFERENCES_OK mutable_record=1 committed_before_return=1 objects=0 connections=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
