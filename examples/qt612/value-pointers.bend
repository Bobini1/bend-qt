import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def parsed(value: Qt.Outputs_QJsonDocument_QJsonParseError) -> Qt.Action(Unit):
  match value:
    case Qt.Outputs_QJsonDocument_QJsonParseError{document, error}:
      do Qt.Action<Unit>:
        empty: Bool <- Qt.QJsonDocument.isNull(document)
        description: String <- Qt.QJsonParseError.errorString(error)
        require(empty && Bool.not(String.eq(description, "")), "JSON parse error output was lost")

def parse(bytes: Qt.QByteArray) -> Qt.Action(Unit):
  Qt.Outputs_QJsonDocument_QJsonParseError.with(Unit, Qt.QJsonDocument.fromJson(bytes), parsed)

def unit_axis(value: Qt.QVector3D) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    square: Qt.F64 <- Qt.QVector3D.lengthSquared(value)
    unit: Bool <- Qt.F64.equal(square, Qt.F64{0, 1072693248})
    require(unit, "Quaternion axis output was not initialized")

def axes(value: Qt.Outputs_QVector3D_QVector3D_QVector3D) -> Qt.Action(Unit):
  match value:
    case Qt.Outputs_QVector3D_QVector3D_QVector3D{+x, +y, z}:
      do Qt.Action<Unit>:
        unit_axis(x)
        unit_axis(y)
        unit_axis(z)
        product: Qt.F64 <- Qt.QVector3D.dotProduct(x, y)
        orthogonal: Bool <- Qt.F64.equal(product, Qt.F64{0, 0})
        require(orthogonal, "Quaternion axis outputs alias each other")

def quaternion(value: Qt.QQuaternion) -> Qt.Action(Unit):
  Qt.Outputs_QVector3D_QVector3D_QVector3D.with(Unit, Qt.QQuaternion.getAxes(value), axes)

def cached(value: Qt.Outputs_Bool_QPixmap) -> Qt.Action(Unit):
  match value:
    case Qt.Outputs_Bool_QPixmap{found, +pixmap}:
      do Qt.Action<Unit>:
        width: Qt.Int32 <- Qt.QPixmap.width(pixmap)
        height: Qt.Int32 <- Qt.QPixmap.height(pixmap)
        require(found && U32.is_eq(Qt.Int32.word(width), 17) && U32.is_eq(Qt.Int32.word(height), 19), "Pixmap output pointer was not copied")

def exposed(value: Qt.Outputs_QRegion) -> Qt.Action(Unit):
  match value:
    case Qt.Outputs_QRegion{region}:
      do Qt.Action<Unit>:
        empty: Bool <- Qt.QRegion.isEmpty(region)
        require(Bool.not(empty), "Pixmap scroll did not return its exposed region")

def pixmap(+value: Qt.QPixmap) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    inserted: Bool <- Qt.QPixmapCache.insert__String_QPixmap("bend-value-output", value)
    require(inserted, "Pixmap cache insertion failed")
    Qt.Outputs_Bool_QPixmap.with(Unit, Qt.QPixmapCache.find__String("bend-value-output"), cached)
    Qt.QPixmapCache.remove__String("bend-value-output")
    Qt.Outputs_QRegion.with(Unit, Qt.QPixmap.scroll__Int32_Int32_Int32_Int32_Int32_Int32(value, Qt.Int32{1}, Qt.Int32{0}, Qt.Int32{0}, Qt.Int32{0}, Qt.Int32{17}, Qt.Int32{19}), exposed)

def out_of_bounds(result: Result<&1, &1, U32 & String, Unit>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 34), "Wrong native array bound error")
    case Done{value}: Qt.Action.fail(Unit, 1, "Oversized native array was accepted")

def rectangles(+first: Qt.QRect, +second: Qt.QRect, +region: Qt.QRegion) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    bad: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QRegion.setRects(region, first <> second <> Nil{}, Qt.Int32{3}))
    out_of_bounds(bad)
    Qt.QRegion.setRects(region, first <> second <> Nil{}, Qt.Int32{2})
    count: Qt.Int32 <- Qt.QRegion.rectCount(region)
    require(U32.is_eq(Qt.Int32.word(count), 2), "Bounded value array lost a rectangle")

def second_rectangle(first: Qt.QRect, second: Qt.QRect) -> Qt.Action(Unit):
  Qt.QRegion.with(Unit, Qt.QRegion.new(), region => rectangles(first, second, region))

def first_rectangle(first: Qt.QRect) -> Qt.Action(Unit):
  Qt.QRect.with(Unit, Qt.QRect.new__Int32_Int32_Int32_Int32(Qt.Int32{10}, Qt.Int32{10}, Qt.Int32{2}, Qt.Int32{2}), second => second_rectangle(first, second))

def scaled(value: Qt.QPoint) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    x: Qt.Int32 <- Qt.QPoint.x(value)
    require(U32.is_eq(Qt.Int32.word(x), 6), "Synchronous mutable matrix pointer did not update its caller-owned value")

def apply_point(matrix: Qt.QMatrix4x4, point: Qt.QPoint) -> Qt.Action(Unit):
  Qt.QPoint.with(Unit, Qt.QPoint.op_reverse_multiply__QMatrix4x4(point, matrix), scaled)

def apply(scale: Qt.QGraphicsScale, +matrix: Qt.QMatrix4x4) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QGraphicsScale.applyTo(scale, matrix)
    Qt.QPoint.with(Unit, Qt.QPoint.new__Int32_Int32(Qt.Int32{3}, Qt.Int32{4}), point => apply_point(matrix, point))

def scale(+value: Qt.QGraphicsScale) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QGraphicsScale.setXScale(value, Qt.F64{0, 1073741824})
    Qt.QMatrix4x4.with(Unit, Qt.QMatrix4x4.new(), matrix => apply(value, matrix))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromUtf8("{"), parse)
    Qt.QQuaternion.with(Unit, Qt.QQuaternion.new(), quaternion)
    Qt.QPixmap.with(Unit, Qt.QPixmap.new__Int32_Int32(Qt.Int32{17}, Qt.Int32{19}), value => pixmap(value))
    Qt.QRect.with(Unit, Qt.QRect.new__Int32_Int32_Int32_Int32(Qt.Int32{0}, Qt.Int32{0}, Qt.Int32{2}, Qt.Int32{2}), first_rectangle)
    Qt.QGraphicsScale.with(Unit, Qt.QGraphicsScale.new(), value => scale(value))
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Value pointer conversion leaked native copies")
    Qt.Action.lift(Unit, IO.print("QT612_VALUE_POINTERS_OK parse_error=1 axes=1 pixmap_outputs=1 bounded_values=1 mutable_matrix=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
