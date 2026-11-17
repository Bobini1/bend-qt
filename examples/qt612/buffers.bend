import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expect_error(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong buffer error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected checked buffer failure")

def bytes_equal(expected: List<&2, U32>, actual: List<&2, U32>) -> Bool:
  match expected actual:
    case Nil{} Nil{}: True{}
    case a <> rest b <> tail: U32.is_eq(a, b) && bytes_equal(rest, tail)
    case _ _: False{}

def binary() -> List<&2, U32>:
  0 <> 255 <> 65 <> 0 <> Nil{}

def check_bytes(expected: List<&2, U32>, value: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    actual: List<&2, U32> <- Qt.QByteArray.toBytes(value)
    require(bytes_equal(expected, actual), "Native buffer bytes changed")

def copied(+source: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QByteArray.with(Unit, Qt.QByteArray.new__QByteArray_Int64(source, Qt.Int64{3, 0}), value => check_bytes(0 <> 255 <> 65 <> Nil{}, value))
    Qt.QByteArray.with(Unit, Qt.QByteArray.new__QByteArray_Int64(source, Qt.Int64{0, 0}), value => check_bytes(Nil{}, value))
    too_large: Result<&1, &1, U32 & String, Qt.QByteArray> <- Qt.Action.attempt(Qt.QByteArray, Qt.QByteArray.new__QByteArray_Int64(source, Qt.Int64{5, 0}))
    expect_error(Qt.QByteArray, too_large, 34)
    negative: Result<&1, &1, U32 & String, Qt.QByteArray> <- Qt.Action.attempt(Qt.QByteArray, Qt.QByteArray.new__QByteArray_Int64(source, Qt.Int64{4294967295, 4294967295}))
    expect_error(Qt.QByteArray, negative, 34)
    item: Qt.Int32 <- Qt.QByteArray.op_at(source, Qt.Int64{2, 0})
    require(U32.is_eq(Qt.Int32.word(item), 65), "Subscript operator changed a byte")
    invalid: Result<&1, &1, U32 & String, Qt.Int32> <- Qt.Action.attempt(Qt.Int32, Qt.QByteArray.op_at(source, Qt.Int64{4, 0}))
    expect_error(Qt.Int32, invalid, 34)
    check_bytes(binary(), source)

def aliased(+value: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QByteArray.with(Unit, Qt.QByteArray.append__QByteArray_Int64(value, value, Qt.Int64{2, 0}), result => check_bytes(0 <> 255 <> 65 <> 0 <> 0 <> 255 <> Nil{}, result))
    check_bytes(0 <> 255 <> 65 <> 0 <> 0 <> 255 <> Nil{}, value)

def nul_name(+object: Qt.QObject, value: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    name: String <- Qt.QByteArray.utf8(value)
    bad: Result<&1, &1, U32 & String, Qt.QVariant> <- Qt.Action.attempt(Qt.QVariant, Qt.QObject.property(object, name))
    expect_error(Qt.QVariant, bad, 22)

def cstring(object: Qt.QObject) -> Qt.Action(Unit):
  Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes(97 <> 0 <> 98 <> Nil{}), value => nul_name(object, value))

def allocated(value: Qt.QByteArray) -> Qt.Action(Unit):
  check_bytes(0 <> 0 <> 0 <> 0 <> Nil{}, value)

def stream_output(+stream: Qt.QDataStream, +output: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    bad: Result<&1, &1, U32 & String, Qt.Int64> <- Qt.Action.attempt(Qt.Int64, Qt.QDataStream.readRawData(stream, output, Qt.Int64{5, 0}))
    expect_error(Qt.Int64, bad, 34)
    count: Qt.Int64 <- Qt.QDataStream.readRawData(stream, output, Qt.Int64{4, 0})
    require(U32.is_eq(Qt.Int64.lo(count), 4), "Native raw output count changed")
    check_bytes(binary(), output)

def stream(value: Qt.QDataStream) -> Qt.Action(Unit):
  Qt.QByteArray.with(Unit, Qt.QByteArray.allocate(Qt.Int64{4, 0}), output => stream_output(value, output))

def stream_acquire() -> Qt.Action(Qt.QDataStream):
  # This overload copies its const QByteArray argument. The source scope ends
  # before the stream is used, which also verifies its native copy contract.
  Qt.QByteArray.with(Qt.QDataStream, Qt.QByteArray.fromBytes(binary()), Qt.QDataStream.new__QByteArray)

def line_output(+buffer: Qt.QBuffer, +output: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    read: Bool <- Qt.QBuffer.readLineInto__QByteArray_Int64(buffer, output, Qt.Int64{0, 0})
    require(read, "Byte-array output pointer did not read")
    check_bytes(65 <> 0 <> 255 <> 10 <> Nil{}, output)

def line_source(+buffer: Qt.QBuffer, source: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QBuffer.setData__QByteArray(buffer, source)
    opened: Bool <- Qt.QBuffer.open(buffer, Qt.Flags_QIODeviceBase__OpenModeFlag{1})
    require(opened, "Cannot open in-memory device")
    Qt.QByteArray.with(Unit, Qt.QByteArray.new(), output => line_output(buffer, output))

def line(buffer: Qt.QBuffer) -> Qt.Action(Unit):
  Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes(65 <> 0 <> 255 <> 10 <> Nil{}), source => line_source(buffer, source))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes(binary()), value => copied(value))
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes(binary()), value => aliased(value))
    Qt.QByteArray.with(Unit, Qt.QByteArray.allocate(Qt.Int64{4, 0}), allocated)
    negative: Result<&1, &1, U32 & String, Qt.QByteArray> <- Qt.Action.attempt(Qt.QByteArray, Qt.QByteArray.allocate(Qt.Int64{4294967295, 4294967295}))
    expect_error(Qt.QByteArray, negative, 34)
    Qt.QObject.with(Unit, Qt.QObject.new(), cstring)
    Qt.QDataStream.with(Unit, stream_acquire(), stream)
    Qt.QBuffer.with(Unit, Qt.QBuffer.new(), line)
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Buffer adapters leaked native handles")
    Qt.Action.lift(Unit, IO.print("QT612_BUFFERS_OK binary=1 bounds=1 negative=1 empty=1 alias=1 allocation=1 embedded_nul=1 raw_output=1 value_output=1 copied_stream=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
