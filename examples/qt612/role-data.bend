import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def error(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong role-span error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected checked role-span rejection")

def text(value: Qt.QVariant, expected: String) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    actual: String <- Qt.QVariant.toString(value)
    require(String.eq(actual, expected), "Native role data changed unexpectedly")

def write(role: Qt.QModelRoleData, value: Qt.QVariant) -> Qt.Action(Unit):
  Qt.QModelRoleData.setData(role, value)

def mutate(+roles: Qt.ArrayView_QModelRoleData, value: Qt.QVariant) -> Qt.Action(Unit):
  Qt.QModelRoleData.with(Unit, Qt.ArrayView_QModelRoleData.ref(roles, Qt.UInt64{0, 0}), role => write(role, value))

def checked_span(+span: Qt.QModelRoleDataSpan, +value: Qt.QVariant) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.ArrayView_QModelRoleData.with(Unit, Qt.QModelRoleDataSpan.data(span), roles => mutate(roles, value))
    Qt.QVariant.with(Unit, Qt.QModelRoleDataSpan.dataForRole(span, Qt.Int32{0}), data => text(data, "retained"))
    absent: Result<&1, &1, U32 & String, Qt.QVariant> <- Qt.Action.attempt(Qt.QVariant, Qt.QModelRoleDataSpan.dataForRole(span, Qt.Int32{99}))
    error(Qt.QVariant, absent, 34)

def retained(+buffer: Qt.RoleDataBuffer) -> Qt.Action(Qt.QModelRoleDataSpan):
  do Qt.Action<Qt.QModelRoleDataSpan>:
    +span: Qt.QModelRoleDataSpan <- Qt.RoleDataBuffer.span(buffer)
    pinned: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.RoleDataBuffer.destroy(buffer))
    error(Unit, pinned, 16)
    +copy: Qt.QModelRoleDataSpan <- Qt.QModelRoleDataSpan.new__QModelRoleDataSpan(span)
    Qt.QModelRoleDataSpan.destroy(span)
    return copy

def copied(+span: Qt.QModelRoleDataSpan) -> Qt.Action(Unit):
  Qt.QVariant.with(Unit, Qt.QVariant.fromString("retained"), value => checked_span(span, value))

def single(+role: Qt.QModelRoleData) -> Qt.Action(Qt.QModelRoleDataSpan):
  Qt.QModelRoleDataSpan.new__QModelRoleData(role)

def single_check(+span: Qt.QModelRoleDataSpan) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    count: Qt.Int64 <- Qt.QModelRoleDataSpan.size(span)
    require(U32.is_eq(Qt.Int64.lo(count), 1), "Single-role reference lost its native backing")

def single_check_role_zero(span: Qt.QModelRoleDataSpan) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    count: Qt.Int64 <- Qt.QModelRoleDataSpan.size(span)
    require(U32.is_eq(Qt.Int64.lo(count), 1), "Checked pointer constructor ignored the requested extent")

def bounds(+buffer: Qt.RoleDataBuffer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    bad: Result<&1, &1, U32 & String, Qt.QModelRoleDataSpan> <- Qt.Action.attempt(Qt.QModelRoleDataSpan, Qt.QModelRoleDataSpan.new__RoleDataBuffer_Int64(buffer, Qt.Int64{3, 0}))
    error(Qt.QModelRoleDataSpan, bad, 34)
    Qt.QModelRoleDataSpan.with(Unit, Qt.QModelRoleDataSpan.new__RoleDataBuffer_Int64(buffer, Qt.Int64{1, 0}), span => single_check_role_zero(span))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QModelRoleDataSpan.with(Unit,
      Qt.RoleDataBuffer.with(Qt.QModelRoleDataSpan, Qt.RoleDataBuffer.new(Qt.Int32{0} <> Qt.Int32{1} <> Nil{}), value => retained(value)), value => copied(value))
    Qt.QModelRoleDataSpan.with(Unit,
      Qt.QModelRoleData.with(Qt.QModelRoleDataSpan, Qt.QModelRoleData.new__Int32(Qt.Int32{7}), value => single(value)), value => single_check(value))
    Qt.RoleDataBuffer.with(Unit, Qt.RoleDataBuffer.new(Qt.Int32{0} <> Qt.Int32{1} <> Nil{}), value => bounds(value))
    objects: U32 <- Qt.Runtime.liveObjects()
    pins: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(pins, 0), "Role span backing leaked resources")
    Qt.Action.lift(Unit, IO.print("QT612_ROLE_DATA_OK retained=1 copied=1 mutable=1 missing_role=1 bounds=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
