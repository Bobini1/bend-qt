import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def error(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong typed-view error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected typed-view rejection")

def point(+value: Qt.QPoint) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    x: Qt.Int32 <- Qt.QPoint.x(value)
    y: Qt.Int32 <- Qt.QPoint.y(value)
    require(U32.is_eq(Qt.Int32.word(x), 7) && U32.is_eq(Qt.Int32.word(y), 9), "Typed span write did not change its native element")

def readonly(+view: Qt.ArrayView_QPoint, value: Qt.QPoint) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    denied: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.ArrayView_QPoint.set(view, Qt.UInt64{0, 0}, value))
    error(Unit, denied, 1)

def span(+polygon: Qt.QPolygon, +view: Qt.ArrayView_QPoint, +value: Qt.QPoint) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.ArrayView_QPoint.set(view, Qt.UInt64{0, 0}, value)
    Qt.QPoint.with(Unit, Qt.QPolygon.at(polygon, Qt.Int64{0, 0}), value => point(value))
    Qt.ArrayView_QPoint.with(Unit, Qt.QPolygon.constData(polygon), readonly_view => readonly(readonly_view, value))
    held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QPolygon.destroy(polygon))
    error(Unit, held, 16)
    beyond: Result<&1, &1, U32 & String, Qt.QPoint> <- Qt.Action.attempt(Qt.QPoint, Qt.ArrayView_QPoint.at(view, Qt.UInt64{1, 0}))
    error(Qt.QPoint, beyond, 34)
    Qt.QPolygon.clear(polygon)
    stale: Result<&1, &1, U32 & String, Qt.UInt64> <- Qt.Action.attempt(Qt.UInt64, Qt.ArrayView_QPoint.size(view))
    error(Qt.UInt64, stale, 116)

def polygon(+polygon: Qt.QPolygon, +value: Qt.QPoint) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QPolygon.append__QPoint(polygon, value)
    Qt.ArrayView_QPoint.with(Unit, Qt.QPolygon.data(polygon), view => span(polygon, view, value))

def empty_region(view: Qt.ArrayView_QRect) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    size: Qt.UInt64 <- Qt.ArrayView_QRect.size(view)
    require(U32.is_eq(Qt.UInt64.lo(size), 0), "Empty native range changed its extent")

def cbor_bytes(value: List<&2, U32>) -> Bool:
  match value:
    case 24 <> 42 <> Nil{}: True{}
    case _: False{}

def cbor(+writer: Qt.QCborStreamWriter, +array: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QByteArray.release(array)
    Qt.QCborStreamWriter.append__U32(writer, 42)
    bytes: List<&2, U32> <- Qt.QByteArray.toBytes(array)
    require(cbor_bytes(bytes), "CBOR writer lost its retained byte array")
    Qt.QCborStreamWriter.destroy(writer)
    stale: Result<&1, &1, U32 & String, List<&2, U32>> <- Qt.Action.attempt(List<&2, U32>, Qt.QByteArray.toBytes(array))
    error(List<&2, U32>, stale, 116)

def cbor_backing(+array: Qt.QByteArray) -> Qt.Action(Unit):
  Qt.QCborStreamWriter.with(Unit, Qt.QCborStreamWriter.new__QByteArray(array), writer => cbor(writer, array))

def xml(+writer: Qt.QXmlStreamWriter, +buffer: Qt.QStringBuffer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QXmlStreamWriter.writeTextElement__String_String(writer, "root", "safe")
    text: String <- Qt.QStringBuffer.value(buffer)
    require(String.eq(text, "<root>safe</root>"), "XML writer lost its retained string buffer")
    held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QStringBuffer.destroy(buffer))
    error(Unit, held, 16)

def xml_backing(+buffer: Qt.QStringBuffer) -> Qt.Action(Unit):
  Qt.QXmlStreamWriter.with(Unit, Qt.QXmlStreamWriter.new__QStringBuffer(buffer), writer => xml(writer, buffer))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QPoint.with(Unit, Qt.QPoint.new__Int32_Int32(Qt.Int32{7}, Qt.Int32{9}), value =>
      Qt.QPolygon.with(Unit, Qt.QPolygon.new(), shape => polygon(shape, value)))
    Qt.QRegion.with(Unit, Qt.QRegion.new(), value =>
      Qt.ArrayView_QRect.with(Unit, Qt.QRegion.begin(value), view => empty_region(view)))
    Qt.QByteArray.with(Unit, Qt.QByteArray.new(), array => cbor_backing(array))
    Qt.QStringBuffer.with(Unit, Qt.QStringBuffer.new(""), buffer => xml_backing(buffer))
    objects: U32 <- Qt.Runtime.liveObjects()
    pins: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(pins, 0), "Typed spans or native writers leaked resources")
    Qt.Action.lift(Unit, IO.print("QT612_TYPED_VIEWS_OK mutation=1 readonly=1 bounds=1 stale=1 empty_range=1 writer_backing=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
