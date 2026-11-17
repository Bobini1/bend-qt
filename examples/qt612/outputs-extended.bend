import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def date_result(value: Qt.Outputs_Int32_Int32_Int32) -> Qt.Action(Unit):
  match value:
    case Qt.Outputs_Int32_Int32_Int32{year, month, day}:
      require(U32.is_eq(Qt.Int32.word(year), 2024) && U32.is_eq(Qt.Int32.word(month), 2) && U32.is_eq(Qt.Int32.word(day), 29), "Date output values changed")

def date(value: Qt.QDate) -> Qt.Action(Unit):
  Qt.Outputs_Int32_Int32_Int32.with(Unit, Qt.QDate.getDate(value), date_result)

def color_result(value: Qt.Outputs_Int32_Int32_Int32_Int32_Int32) -> Qt.Action(Unit):
  match value:
    case Qt.Outputs_Int32_Int32_Int32_Int32_Int32{c, m, y, k, a}:
      require(U32.is_eq(Qt.Int32.word(c), 10) && U32.is_eq(Qt.Int32.word(m), 20) && U32.is_eq(Qt.Int32.word(y), 30) && U32.is_eq(Qt.Int32.word(k), 40) && U32.is_eq(Qt.Int32.word(a), 50), "Five output pointers lost order")

def color(value: Qt.QColor) -> Qt.Action(Unit):
  Qt.Outputs_Int32_Int32_Int32_Int32_Int32.with(Unit, Qt.QColor.getCmyk(value), color_result)

def intersect_result(value: Qt.Outputs_QLineF_IntersectionType_QPointF) -> Qt.Action(Unit):
  match value:
    case Qt.Outputs_QLineF_IntersectionType_QPointF{kind, +point}:
      do Qt.Action<Unit>:
        require(U32.is_eq(Qt.QLineF.IntersectionType.word(kind), Qt.QLineF.IntersectionType.word(Qt.QLineF.IntersectionType.BoundedIntersection())), "Expected a bounded line intersection")
        x: Qt.F64 <- Qt.QPointF.x(point)
        y: Qt.F64 <- Qt.QPointF.y(point)
        x_ok: Bool <- Qt.F64.equal(x, Qt.F64{0, 1072693248})
        y_ok: Bool <- Qt.F64.equal(y, Qt.F64{0, 1072693248})
        require(x_ok && y_ok, "Value output pointer did not preserve intersection")

def intersect_second(first: Qt.QLineF, second: Qt.QLineF) -> Qt.Action(Unit):
  Qt.Outputs_QLineF_IntersectionType_QPointF.with(Unit, Qt.QLineF.intersects(first, second), intersect_result)

def intersect(first: Qt.QLineF) -> Qt.Action(Unit):
  Qt.QLineF.with(Unit, Qt.QLineF.new__F64_F64_F64_F64(Qt.F64{0, 0}, Qt.F64{0, 1073741824}, Qt.F64{0, 1073741824}, Qt.F64{0, 0}), second => intersect_second(first, second))

def angles_result(value: Qt.Outputs_F64_F64_F64) -> Qt.Action(Unit):
  match value:
    case Qt.Outputs_F64_F64_F64{pitch, yaw, roll}:
      do Qt.Action<Unit>:
        p: Bool <- Qt.F64.equal(pitch, Qt.F64{0, 0})
        y: Bool <- Qt.F64.equal(yaw, Qt.F64{0, 0})
        r: Bool <- Qt.F64.equal(roll, Qt.F64{0, 0})
        require(p && y && r, "Quaternion output values changed")

def angles(value: Qt.QQuaternion) -> Qt.Action(Unit):
  Qt.Outputs_F64_F64_F64.with(Unit, Qt.QQuaternion.getEulerAngles(value), angles_result)

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QDate.with(Unit, Qt.QDate.new__Int32_Int32_Int32(Qt.Int32{2024}, Qt.Int32{2}, Qt.Int32{29}), date)
    Qt.QColor.with(Unit, Qt.QColor.fromCmyk__Int32_Int32_Int32_Int32_Int32(Qt.Int32{10}, Qt.Int32{20}, Qt.Int32{30}, Qt.Int32{40}, Qt.Int32{50}), color)
    Qt.QLineF.with(Unit, Qt.QLineF.new__F64_F64_F64_F64(Qt.F64{0, 0}, Qt.F64{0, 0}, Qt.F64{0, 1073741824}, Qt.F64{0, 1073741824}), intersect)
    Qt.QQuaternion.with(Unit, Qt.QQuaternion.new(), angles)
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Output records leaked native value copies")
    Qt.Action.lift(Unit, IO.print("QT612_OUTPUTS_EXTENDED_OK typed_locals=1 five_outputs=1 value_output=1 real_outputs=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
