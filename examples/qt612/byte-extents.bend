import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def bits(+value: Qt.QBitArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    size: Qt.Int64 <- Qt.QBitArray.size(value)
    count: Qt.Int64 <- Qt.QBitArray.count__Bool(value, True{})
    require(U32.is_eq(Qt.Int64.lo(size), 3) && U32.is_eq(Qt.Int64.lo(count), 3), "Bit extent did not round up to its byte storage")

def oversized(result: Result<&1, &1, U32 & String, Qt.QBitArray>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 34), "Wrong bit extent error")
    case Done{value}: Qt.Action.finally(Unit, Qt.Action.fail(Unit, 1, "Nine bits read beyond one input byte"), Qt.QBitArray.release(value))

def byte(+value: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    bad: Result<&1, &1, U32 & String, Qt.QBitArray> <- Qt.Action.attempt(Qt.QBitArray, Qt.QBitArray.fromBits(value, Qt.Int64{9, 0}))
    oversized(bad)
    Qt.QBitArray.with(Unit, Qt.QBitArray.fromBits(value, Qt.Int64{3, 0}), result => bits(result))

def parsed(value: Qt.Outputs_QCborValue_QCborParserError) -> Qt.Action(Unit):
  match value:
    case Qt.Outputs_QCborValue_QCborParserError{item, error}:
      do Qt.Action<Unit>:
        integer: Qt.Int64 <- Qt.QCborValue.toInteger(item)
        require(U32.is_eq(Qt.Int64.lo(integer), 42), "Bounded CBOR parse changed its integer")

def add(reader: Qt.QCborStreamReader, +bytes: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QCborStreamReader.addData__QByteArray_Int64(reader, bytes, Qt.Int64{2, 0})
    Qt.Outputs_QCborValue_QCborParserError.with(Unit, Qt.QCborValue.fromCbor__QByteArray_Int64(bytes, Qt.Int64{2, 0}), parsed)

def reader(+value: Qt.QCborStreamReader) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes(24 <> 42 <> Nil{}), bytes => add(value, bytes))
    integer: Qt.Int64 <- Qt.QCborStreamReader.toInteger(value)
    require(U32.is_eq(Qt.Int64.lo(integer), 42), "CBOR addData retained a temporary input pointer")

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes(255 <> Nil{}), value => byte(value))
    Qt.QCborStreamReader.with(Unit, Qt.QCborStreamReader.new(), value => reader(value))
    count: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(count, 0), "Byte extent conversion leaked native handles")
    Qt.Action.lift(Unit, IO.print("QT612_BYTE_EXTENTS_OK bit_count=1 rounded_capacity=1 bounded_cbor=1 copied_stream_input=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
