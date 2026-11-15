import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def size_copy(+size: Qt.QSize) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    width: Qt.Int32 <- Qt.QSize.width(size)
    height: Qt.Int32 <- Qt.QSize.height(size)
    require(U32.is_eq(Qt.Int32.word(width), 123) && U32.is_eq(Qt.Int32.word(height), 456), "QVariant QSize round trip changed fields")

def copied(+source: Qt.QSize, +variant: Qt.QVariant) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QSize.destroy(source)
    Qt.QSize.with(Unit, Qt.QVariant.to_QSize(variant), value => size_copy(value))

def size(+source: Qt.QSize) -> Qt.Action(Unit):
  Qt.QVariant.with(Unit, Qt.QVariant.from_QSize(source), variant => copied(source, variant))

def unsigned(value: Qt.QVariant) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +wide: Qt.UInt64 <- Qt.QVariant.toUInt64(value)
    require(U32.is_eq(Qt.UInt64.lo(wide), 4294967295) && U32.is_eq(Qt.UInt64.hi(wide), 4294967295), "QVariant narrowed unsigned 64 bits")

def signed(value: Qt.QVariant) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +wide: Qt.Int64 <- Qt.QVariant.toInt64(value)
    require(U32.is_eq(Qt.Int64.lo(wide), 17) && U32.is_eq(Qt.Int64.hi(wide), 2147483648), "QVariant changed signed 64-bit bits")

def wrong(result: Result<&1, &1, U32 & String, Qt.QSize>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 22), "Wrong QVariant mismatch error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "QVariant accepted a wrong native metatype")

def mismatch(value: Qt.QVariant) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    result: Result<&1, &1, U32 & String, Qt.QSize> <- Qt.Action.attempt(Qt.QSize, Qt.QVariant.to_QSize(value))
    wrong(result)

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QSize.with(Unit, Qt.QSize.new__Int32_Int32(Qt.Int32{123}, Qt.Int32{456}), value => size(value))
    Qt.QVariant.with(Unit, Qt.QVariant.fromUInt64(Qt.UInt64{4294967295, 4294967295}), unsigned)
    Qt.QVariant.with(Unit, Qt.QVariant.fromInt64(Qt.Int64{17, 2147483648}), signed)
    Qt.QVariant.with(Unit, Qt.QVariant.fromInt32(Qt.Int32{123}), mismatch)
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "QVariant converters leaked handles")
    Qt.Action.lift(Unit, IO.print("QT612_VARIANTS_OK registered_value=1 independent_copy=1 signed64=1 unsigned64=1 wrong_type=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
