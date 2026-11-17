import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def stream_identity(expected: Qt.QDataStream, actual: Qt.QDataStream) -> Qt.Action(Unit):
  require(U32.is_eq(Qt.QDataStream.word(expected), Qt.QDataStream.word(actual)), "Stream operator changed native identity")

def write_color(+stream: Qt.QDataStream, color: Qt.QColor) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    header: Qt.QDataStream <- Qt.QDataStream.op_shift_left__Int32(stream, Qt.Int32{16909060})
    stream_identity(stream, header)
    colored: Qt.QDataStream <- Qt.QDataStream.op_shift_left__QColor(stream, color)
    stream_identity(stream, colored)
    text: Qt.QDataStream <- Qt.QDataStream.op_shift_left__String(stream, "Bend Qt")
    stream_identity(stream, text)
    status: Qt.QDataStream.Status <- Qt.QDataStream.status(stream)
    require(U32.is_eq(Qt.QDataStream.Status.word(status), 0), "Binary stream write failed")

def write(stream: Qt.QDataStream) -> Qt.Action(Unit):
  Qt.QColor.with(Unit, Qt.QColor.new__Int32_Int32_Int32_Int32(Qt.Int32{17}, Qt.Int32{34}, Qt.Int32{51}, Qt.Int32{255}), color => write_color(stream, color))

def read_header(stream: Qt.QDataStream, value: Qt.Outputs_QDataStream_Int32) -> Qt.Action(Unit):
  match value:
    case Qt.Outputs_QDataStream_Int32{alias, header}:
      do Qt.Action<Unit>:
        stream_identity(stream, alias)
        require(U32.is_eq(Qt.Int32.word(header), 16909060), "Binary integer roundtrip changed")

def read_text(stream: Qt.QDataStream, value: Qt.Outputs_QDataStream_String) -> Qt.Action(Unit):
  match value:
    case Qt.Outputs_QDataStream_String{alias, text}:
      do Qt.Action<Unit>:
        stream_identity(stream, alias)
        require(String.eq(text, "Bend Qt"), "Binary QString roundtrip changed")

def past_end(+stream: Qt.QDataStream, value: Qt.Outputs_QDataStream_Int32) -> Qt.Action(Unit):
  match value:
    case Qt.Outputs_QDataStream_Int32{alias, ignored}:
      do Qt.Action<Unit>:
        stream_identity(stream, alias)
        status: Qt.QDataStream.Status <- Qt.QDataStream.status(stream)
        require(U32.is_eq(Qt.QDataStream.Status.word(status), Qt.QDataStream.Status.word(Qt.QDataStream.Status.ReadPastEnd())), "Truncated binary input did not report ReadPastEnd")

def read_color(+stream: Qt.QDataStream, +color: Qt.QColor) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    alias: Qt.QDataStream <- Qt.QDataStream.op_shift_right__QColor(stream, color)
    stream_identity(stream, alias)
    red: Qt.Int32 <- Qt.QColor.red(color)
    green: Qt.Int32 <- Qt.QColor.green(color)
    blue: Qt.Int32 <- Qt.QColor.blue(color)
    require(U32.is_eq(Qt.Int32.word(red), 17) && U32.is_eq(Qt.Int32.word(green), 34) && U32.is_eq(Qt.Int32.word(blue), 51), "Free extraction operator did not mutate its QColor reference")
    Qt.Outputs_QDataStream_String.with(Unit, Qt.QDataStream.op_shift_right__String(stream, ""), value => read_text(stream, value))
    Qt.Outputs_QDataStream_Int32.with(Unit, Qt.QDataStream.op_shift_right__Int32(stream, Qt.Int32{0}), value => past_end(stream, value))

def read(+stream: Qt.QDataStream) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Outputs_QDataStream_Int32.with(Unit, Qt.QDataStream.op_shift_right__Int32(stream, Qt.Int32{0}), value => read_header(stream, value))
    Qt.QColor.with(Unit, Qt.QColor.new(), color => read_color(stream, color))

def binary_prefix(bytes: List<&2, U32>) -> Qt.Action(Unit):
  match bytes:
    case a <> b <> c <> d <> tail:
      require(U32.is_eq(a, 1) && U32.is_eq(b, 2) && U32.is_eq(c, 3) && U32.is_eq(d, 4), "QDataStream output is not the expected binary representation")
    case _: Qt.Action.fail(Unit, 1, "Binary stream output was truncated")

def binary(+bytes: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QDataStream.with(Unit, Qt.QDataStream.new__QByteArray_Flags_QIODeviceBase__OpenModeFlag(bytes, Qt.Flags_QIODeviceBase__OpenModeFlag{2}), write)
    data: List<&2, U32> <- Qt.QByteArray.toBytes(bytes)
    binary_prefix(data)
    Qt.QDataStream.with(Unit, Qt.QDataStream.new__QByteArray(bytes), stream => read(stream))

def point(expected_x: U32, expected_y: U32, +value: Qt.QPoint) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    x: Qt.Int32 <- Qt.QPoint.x(value)
    y: Qt.Int32 <- Qt.QPoint.y(value)
    require(U32.is_eq(Qt.Int32.word(x), expected_x) && U32.is_eq(Qt.Int32.word(y), expected_y), "Free operator operand order changed")

def transform_point(+matrix: Qt.QMatrix4x4, +value: Qt.QPoint) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QPoint.with(Unit, Qt.QPoint.op_multiply__QMatrix4x4(value, matrix), result => point(11, 16, result))
    Qt.QPoint.with(Unit, Qt.QPoint.op_reverse_multiply__QMatrix4x4(value, matrix), result => point(8, 18, result))
    point(2, 3, value)

def transform(matrix: Qt.QMatrix4x4) -> Qt.Action(Unit):
  Qt.QPoint.with(Unit, Qt.QPoint.new__Int32_Int32(Qt.Int32{2}, Qt.Int32{3}), value => transform_point(matrix, value))

def merged(+left: Qt.QBitArray, +right: Qt.QBitArray, +result: Qt.QBitArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    first: Bool <- Qt.QBitArray.testBit(result, Qt.Int64{0, 0})
    second: Bool <- Qt.QBitArray.testBit(result, Qt.Int64{1, 0})
    original_left: Bool <- Qt.QBitArray.testBit(left, Qt.Int64{1, 0})
    original_right: Bool <- Qt.QBitArray.testBit(right, Qt.Int64{0, 0})
    require(first && second && Bool.not(original_left) && Bool.not(original_right), "Rvalue operator consumed or changed a caller-owned handle")

def merge(+left: Qt.QBitArray, +right: Qt.QBitArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QBitArray.setBit__Int64(left, Qt.Int64{0, 0})
    Qt.QBitArray.setBit__Int64(right, Qt.Int64{1, 0})
    Qt.QBitArray.with(Unit, Qt.QBitArray.op_bit_or(left, right), result => merged(left, right, result))

def bits(left: Qt.QBitArray) -> Qt.Action(Unit):
  Qt.QBitArray.with(Unit, Qt.QBitArray.new__Int64_Bool(Qt.Int64{2, 0}, False{}), right => merge(left, right))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QByteArray.with(Unit, Qt.QByteArray.new(), bytes => binary(bytes))
    Qt.QMatrix4x4.with(Unit, Qt.QMatrix4x4.new__List_F64(Qt.F64{0, 1072693248} <> Qt.F64{0, 1073741824} <> Qt.F64{0, 0} <> Qt.F64{0, 0} <> Qt.F64{0, 1074266112} <> Qt.F64{0, 1074790400} <> Qt.F64{0, 0} <> Qt.F64{0, 0} <> Qt.F64{0, 0} <> Qt.F64{0, 0} <> Qt.F64{0, 1072693248} <> Qt.F64{0, 0} <> Qt.F64{0, 0} <> Qt.F64{0, 0} <> Qt.F64{0, 0} <> Qt.F64{0, 1072693248} <> Nil{}), transform)
    Qt.QBitArray.with(Unit, Qt.QBitArray.new__Int64_Bool(Qt.Int64{2, 0}, False{}), bits)
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Operator fixture leaked native objects")
    Qt.Action.lift(Unit, IO.print("QT612_OPERATORS_OK binary_roundtrip=1 stream_identity=1 read_past_end=1 reverse_order=1 copied_rvalues=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
