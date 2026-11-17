import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def error(-A: Type, value: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match value:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong raw-storage error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected checked raw-storage failure")

def expect_bytes(value: List<&2, U32>) -> Bool:
  match value:
    case 0 <> 255 <> 65 <> Nil{}: True{}
    case _: False{}

def verify_bytes(value: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    bytes: List<&2, U32> <- Qt.QByteArray.toBytes(value)
    require(expect_bytes(bytes), "Owned raw-data snapshot changed with its source")

def source(+value: Qt.QByteArray, +target: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QByteArray.with(Unit, Qt.QByteArray.setRawData(target, value, Qt.Int64{3, 0}), copy => do Qt.Action<Unit>:
      Qt.QByteArray.clear(value)
      verify_bytes(target)
      verify_bytes(copy))
    bad: Result<&1, &1, U32 & String, Qt.QByteArray> <- Qt.Action.attempt(Qt.QByteArray, Qt.QByteArray.fromRawData(value, Qt.Int64{1, 0}))
    error(Qt.QByteArray, bad, 34)

def arrays() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QByteArray.with(Unit,
      Qt.QByteArray.with(Qt.QByteArray, Qt.QByteArray.fromBytes(0 <> 255 <> 65 <> 99 <> Nil{}), value => Qt.QByteArray.fromRawData(value, Qt.Int64{3, 0})),
      value => verify_bytes(value))
    Qt.QByteArray.with(Unit, Qt.QByteArray.new(), target =>
      Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes(0 <> 255 <> 65 <> Nil{}), value => source(value, target)))

def cbor(+value: Qt.QCborStreamReader) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    unsigned: Bool <- Qt.QCborStreamReader.isUnsignedInteger(value)
    number: Qt.UInt64 <- Qt.QCborStreamReader.toUnsignedInteger(value)
    require(unsigned && U32.is_eq(Qt.UInt64.lo(number), 42), "CBOR raw constructor lost its owned backing")

def swapped(+left: Qt.QSemaphoreReleaser, +right: Qt.QSemaphoreReleaser, +first: Qt.QSemaphore, +second: Qt.QSemaphore) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QSemaphoreReleaser.swap(left, right)
    Qt.QSemaphoreReleaser.destroy(left)
    count: Qt.Int32 <- Qt.QSemaphore.available(second)
    require(U32.is_eq(Qt.Int32.word(count), 2), "Swapped releaser did not release its new resource")
    Qt.QSemaphore.destroy(second)
    held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QSemaphore.destroy(first))
    error(Unit, held, 16)
    Qt.QSemaphoreReleaser.destroy(right)
    released: Qt.Int32 <- Qt.QSemaphore.available(first)
    require(U32.is_eq(Qt.Int32.word(released), 1), "Swapped releaser lost its original resource")

def semaphores(+first: Qt.QSemaphore, +second: Qt.QSemaphore) -> Qt.Action(Unit):
  Qt.QSemaphoreReleaser.with(Unit, Qt.QSemaphoreReleaser.new__QSemaphore_Int32(first, Qt.Int32{1}), left =>
    Qt.QSemaphoreReleaser.with(Unit, Qt.QSemaphoreReleaser.new__QSemaphore_Int32(second, Qt.Int32{2}), right => swapped(left, right, first, second)))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    arrays()
    Qt.QCborStreamReader.with(Unit,
      Qt.QByteArray.with(Qt.QCborStreamReader, Qt.QByteArray.fromBytes(24 <> 42 <> Nil{}), bytes => Qt.QCborStreamReader.new__QByteArray_Int64(bytes, Qt.Int64{2, 0})),
      value => cbor(value))
    Qt.QSemaphore.with(Unit, Qt.QSemaphore.new(), first =>
      Qt.QSemaphore.with(Unit, Qt.QSemaphore.new(), second => semaphores(first, second)))
    objects: U32 <- Qt.Runtime.liveObjects()
    pins: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(pins, 0), "Raw storage or resource swaps leaked native handles")
    Qt.Action.lift(Unit, IO.print("QT612_RAW_STORAGE_OK byte_snapshots=1 cbor_backing=1 resource_swap=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
