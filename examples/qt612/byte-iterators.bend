import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def stale(result: Result<&1, &1, U32 & String, U32>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 116), "Wrong stale iterator error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Erased iterator remained live")

def bytes_equal(values: List<&2, U32>) -> Bool:
  match values:
    case 88 <> 100 <> Nil{}: True{}
    case _: False{}

def changed(+array: Qt.QByteArray, +first: Qt.QByteArrayIterator, +current: Qt.QByteArrayIterator) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    byte: U32 <- Qt.QByteArrayIterator.read(current)
    require(U32.is_eq(byte, 99), "Erase returned the wrong next byte")
    Qt.QByteArrayIterator.write(current, 88)
    bytes: List<&2, U32> <- Qt.QByteArray.toBytes(array)
    require(bytes_equal(bytes), "Iterator write did not update its array")
    invalid: Result<&1, &1, U32 & String, U32> <- Qt.Action.attempt(U32, Qt.QByteArrayIterator.read(first))
    stale(invalid)

def range(+array: Qt.QByteArray, +first: Qt.QByteArrayIterator, last: Qt.QByteArrayIterator) -> Qt.Action(Unit):
  Qt.QByteArrayIterator.with(Unit, Qt.QByteArray.erase__QByteArrayIterator_QByteArrayIterator(array, first, last), current => changed(array, first, current))

def first(+array: Qt.QByteArray, +value: Qt.QByteArrayIterator) -> Qt.Action(Unit):
  Qt.QByteArrayIterator.with(Unit, Qt.QByteArrayIterator.advance(value, Qt.Int64{2, 0}), last => range(array, value, last))

def array(+value: Qt.QByteArray) -> Qt.Action(Unit):
  Qt.QByteArrayIterator.with(Unit, Qt.QByteArray.cbegin(value), iterator => first(value, iterator))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromUtf8("abcd"), value => array(value))
    objects: U32 <- Qt.Runtime.liveObjects()
    pins: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(pins, 0), "Byte iterator scopes leaked resources")
    Qt.Action.lift(Unit, IO.print("QT612_BYTE_ITERATORS_OK bounds=1 erase=1 write=1 invalidation=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
