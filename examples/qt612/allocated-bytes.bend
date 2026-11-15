import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def payload(value: List<&2, U32>) -> Qt.Action(Unit):
  match value:
    case 65 <> 0 <> 66 <> []: Qt.Action.pure(Unit, Unit{})
    case _: Qt.Action.fail(Unit, 1, "Allocated bytes lost their embedded NUL or exact extent")

def length_is_three(value: Qt.Int64) -> Bool:
  match value:
    case Qt.Int64{lo, hi}: U32.is_eq(hi, 0) && U32.is_eq(lo, 3)

def bytes(value: Qt.Outputs_QDataStream_QByteArray_Int64) -> Qt.Action(Unit):
  match value:
    case Qt.Outputs_QDataStream_QByteArray_Int64{alias, array, length}:
      do Qt.Action<Unit>:
        require(length_is_three(length), "Native output length changed")
        contents: List<&2, U32> <- Qt.QByteArray.toBytes(array)
        payload(contents)

def string(value: Qt.Outputs_QDataStream_QByteArray) -> Qt.Action(Unit):
  match value:
    case Qt.Outputs_QDataStream_QByteArray{alias, array}:
      do Qt.Action<Unit>:
        contents: List<&2, U32> <- Qt.QByteArray.toBytes(array)
        payload(contents)

def read(+stream: Qt.QDataStream) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Outputs_QDataStream_QByteArray_Int64.with(Unit, Qt.QDataStream.readBytes__charPtr_qint64(stream), bytes)
    Qt.Outputs_QDataStream_QByteArray.with(Unit, Qt.QDataStream.op_shift_right(stream), string)

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes(0 <> 0 <> 0 <> 3 <> 65 <> 0 <> 66 <> 0 <> 0 <> 0 <> 3 <> 65 <> 0 <> 66 <> []), data => Qt.QDataStream.with(Unit, Qt.QDataStream.new__QByteArray(data), stream => read(stream)))
    count: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(count, 0), "Allocated byte output scopes leaked native handles")
    Qt.Action.lift(Unit, IO.print("QT612_ALLOCATED_BYTES_OK read_bytes=1 extraction_operator=1 embedded_nul=1 exact_extent=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
