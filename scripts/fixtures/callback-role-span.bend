import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def fill(role: Qt.QModelRoleData) -> Qt.Action(Unit):
  Qt.QVariant.with(Unit, Qt.QVariant.fromString("Bend role"), value => Qt.QModelRoleData.setData(role, value))

def mutate(view: Qt.ArrayView_QModelRoleData) -> Qt.Action(Unit):
  Qt.QModelRoleData.with(Unit, Qt.ArrayView_QModelRoleData.ref(view, Qt.UInt64{0, 0}), fill)

def copied(+span: Qt.QModelRoleDataSpan) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    saved: Qt.QModelRoleDataSpan <- Qt.QModelRoleDataSpan.new__QModelRoleDataSpan(span)
    Qt.CallbackProbe.captureSpan(saved)
    Qt.ArrayView_QModelRoleData.with(Unit, Qt.QModelRoleDataSpan.data(span), mutate)

# The span refers to the role array of the native call: a copy ends with it.
def multi_data(state: Unit, index: Qt.QModelIndex, span: Qt.QModelRoleDataSpan) -> Qt.Action(Unit):
  copied(span)

def expired(result: Result<&1, &1, U32 & String, Qt.Int64>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 116), "Wrong expired role span error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "A role span copy outlived its native call")

def after(span: Qt.QModelRoleDataSpan) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    result: Result<&1, &1, U32 & String, Qt.Int64> <- Qt.Action.attempt(Qt.Int64, Qt.QModelRoleDataSpan.size(span))
    expired(result)

def model(+value: Qt.QAbstractListModel) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QAbstractItemModel.Virtual.multiData.handle(~Unit, ~multi_data, Qt.QAbstractListModel.as_QAbstractItemModel(value), Unit{})
    Qt.QModelRoleDataSpan.with(Unit, Qt.CallbackProbe.roleSpan(value), after)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QAbstractListModel.with(Unit, Qt.QAbstractListModel.newOverride(), value => model(value))
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "The role span handler leaked native handles")
    Qt.Action.lift(Unit, IO.print("QT612_CALLBACK_ROLE_SPAN_OK native_mutation=1 copied_origin=1 expiry=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
