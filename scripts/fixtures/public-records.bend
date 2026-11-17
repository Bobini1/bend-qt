import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def rejected(~A: Type, code: U32, result: Result<&1, &1, U32 & String, A>) -> Qt.Action(Unit):
  match result:
    case Fail{(actual, message)}: require(U32.is_eq(actual, code), "Wrong public record error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Invalid public record operation succeeded")

def json_copy(+original: Qt.QJsonParseError, copy: Qt.QJsonParseError) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QJsonParseError.Fields.set_offset(original, Qt.Int32{0})
    offset: Qt.Int32 <- Qt.QJsonParseError.Fields.offset(copy)
    require(U32.is_eq(Qt.Int32.word(offset), 42), "Canonical conditional field did not preserve a copy")

def json_error(+value: Qt.QJsonParseError) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QJsonParseError.Fields.set_offset(value, Qt.Int32{42})
    Qt.QJsonParseError.with(Unit, Qt.QJsonParseError.new__QJsonParseError(value), copy => json_copy(value, copy))

def identity(value: Qt.QQuaternion) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    yes: Bool <- Qt.QQuaternion.isIdentity(value)
    require(yes, "Discovered quaternion value record changed the rotation")

def euler(+value: Qt.QQuaternion__EulerAngles_float) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQuaternion__EulerAngles_float.Fields.set_pitch(value, Qt.F64{0, 0})
    Qt.QQuaternion__EulerAngles_float.Fields.set_yaw(value, Qt.F64{0, 0})
    Qt.QQuaternion__EulerAngles_float.Fields.set_roll(value, Qt.F64{0, 0})
    Qt.QQuaternion.with(Unit, Qt.QQuaternion.fromEulerAngles__QQuaternion__EulerAngles_float(value), identity)

def angles(value: Qt.QQuaternion) -> Qt.Action(Unit):
  Qt.QQuaternion__EulerAngles_float.with(Unit, Qt.QQuaternion.eulerAngles(value), copy => euler(copy))

def axis(+axes: Qt.QQuaternion.Axes, +value: Qt.QQuaternion.Axis) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQuaternion.Axis.Fields.set_x(value, Qt.F64{0, 1072693248})
    Qt.QQuaternion.Axis.Fields.set_y(value, Qt.F64{0, 0})
    Qt.QQuaternion.Axis.Fields.set_z(value, Qt.F64{0, 0})
    Qt.QQuaternion.Axes.Fields.set_x(axes, value)
    Qt.QQuaternion.Axis.Fields.set_x(value, Qt.F64{0, 0})
    Qt.QQuaternion.Axis.Fields.set_y(value, Qt.F64{0, 1072693248})
    Qt.QQuaternion.Axes.Fields.set_y(axes, value)
    Qt.QQuaternion.Axis.Fields.set_y(value, Qt.F64{0, 0})
    Qt.QQuaternion.Axis.Fields.set_z(value, Qt.F64{0, 1072693248})
    Qt.QQuaternion.Axes.Fields.set_z(axes, value)
    Qt.QQuaternion.Axis.destroy(value)
    Qt.QQuaternion.with(Unit, Qt.QQuaternion.fromAxes__QQuaternion_Axes(axes), identity)

def axes(+value: Qt.QQuaternion.Axes) -> Qt.Action(Unit):
  Qt.QQuaternion.Axis.with(Unit, Qt.QQuaternion.Axis.new(), item => axis(value, item))

def matrix(value: Qt.QMatrix2x3) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    sample: Qt.F64 <- Qt.QMatrix2x3.op_call(value, Qt.Int32{2}, Qt.Int32{1})
    same: Bool <- Qt.F64.equal(sample, Qt.F64{0, 1074266112})
    require(same, "Bounded native matrix constructor changed element order")

def list_empty(value: List<&2, Qt.QXmlStreamAttribute>) -> Qt.Action(Unit):
  match value:
    case Nil{}: Qt.Action.pure(Unit, Unit{})
    case _: Qt.Action.fail(Unit, 1, "Qt list conversion did not copy the empty value")

def attributes(+value: Qt.QXmlStreamAttributes) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    empty: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QXmlStreamAttributes.pop_back(value))
    rejected(Unit, 34, empty)
    Qt.QXmlStreamAttributes.append__String_String(value, "a", "b")
    Qt.QXmlStreamAttributes.pop_front(value)
    Qt.List_QXmlStreamAttribute.with(Unit, Qt.QXmlStreamAttributes.toList(value), list_empty)
    Qt.List_QXmlStreamAttribute.with(Unit, Qt.QXmlStreamAttributes.fromList(Nil{}), list_empty)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QJsonParseError.with(Unit, Qt.QJsonParseError.new(), value => json_error(value))
    Qt.QQuaternion.with(Unit, Qt.QQuaternion.new(), angles)
    Qt.QQuaternion.Axes.with(Unit, Qt.QQuaternion.Axes.new(), value => axes(value))
    Qt.QMatrix2x3.with(Unit, Qt.QMatrix2x3.new__List_F64(Qt.F64{0, 0} <> Qt.F64{0, 0} <> Qt.F64{0, 0} <> Qt.F64{0, 0} <> Qt.F64{0, 0} <> Qt.F64{0, 1074266112} <> Nil{}), matrix)
    bad: Result<&1, &1, U32 & String, Qt.QMatrix2x3> <- Qt.Action.attempt(Qt.QMatrix2x3, Qt.QMatrix2x3.new__List_F64(Nil{}))
    rejected(Qt.QMatrix2x3, 22, bad)
    Qt.QXmlStreamAttributes.with(Unit, Qt.QXmlStreamAttributes.new(), value => attributes(value))
    count: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(count, 0), "Public records leaked native copies")
    Qt.Action.lift(Unit, IO.print("QT612_PUBLIC_RECORDS_OK conditional_field=1 nested_axis=1 specialized_euler=1 matrix_constructor=1 list_members=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
