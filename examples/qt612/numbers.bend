import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def invalid_number(result: Result<&1, &1, U32 & String, Qt.F64>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 22), "Wrong conversion error")
    case Done{value}: Qt.Action.fail(Unit, 1, "Invalid conversion accepted")

def invalid_conversion(variant: Qt.QVariant) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    result: Result<&1, &1, U32 & String, Qt.F64> <- Qt.Action.attempt(Qt.F64, Qt.QVariant.toF64(variant))
    invalid_number(result)

def invalid_byte(result: Result<&1, &1, U32 & String, Qt.QByteArray>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 34), "Wrong integer range error")
    case Done{value}: Qt.Action.fail(Unit, 1, "Out-of-range char was silently truncated")

def tag_value(value: Qt.QCborValue) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +tag: Qt.QCborTag <- Qt.QCborValue.tag(value)
    require(U32.is_eq(Qt.QCborTag.lo(tag), 7) && U32.is_eq(Qt.QCborTag.hi(tag), 1), "64-bit enum was truncated")

def tagged(value: Qt.QCborValue) -> Qt.Action(Unit):
  Qt.QCborValue.with(Unit, Qt.QCborValue.new__QCborTag_QCborValue(Qt.QCborTag{7, 1}, value), tag_value)

def port_error(result: Result<&1, &1, U32 & String, Unit>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 34), "Wrong quint16 range error")
    case Done{unit}: Qt.Action.fail(Unit, 1, "quint16 was truncated")

def proxy(+value: Qt.QNetworkProxy) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QNetworkProxy.setPort(value, 65535)
    bad: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QNetworkProxy.setPort(value, 65536))
    port_error(bad)
    port: U32 <- Qt.QNetworkProxy.port(value)
    require(U32.is_eq(port, 65535), "Invalid alias conversion mutated Qt")

def default_url(value: Qt.QUrl) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    text: String <- Qt.QUrl.toString(value)
    require(String.eq(text, "https://example.org/score"), "Native Qt defaults were not applied")

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +exact: Qt.F64 <- Qt.F64.fromString("1.0000000000000002")
    require(U32.is_eq(Qt.F64.lo(exact), 1) && U32.is_eq(Qt.F64.hi(exact), 1072693248), "F64 parsing lost precision")
    text: String <- Qt.F64.toString(exact)
    require(String.eq(text, "1.0000000000000002"), "F64 formatting lost precision")
    sum: Qt.F64 <- Qt.F64.add(Qt.F64{0, 1072693248}, Qt.F64{0, 1072693248})
    equal: Bool <- Qt.F64.equal(sum, Qt.F64{0, 1073741824})
    require(equal, "F64 arithmetic failed")
    invalid: Result<&1, &1, U32 & String, Qt.F64> <- Qt.Action.attempt(Qt.F64, Qt.F64.fromString("no number"))
    invalid_number(invalid)
    +days: Qt.Int64 <- Qt.QDate.with(Qt.Int64, Qt.QDate.fromJulianDay(Qt.Int64{1, 1}), Qt.QDate.toJulianDay)
    require(U32.is_eq(Qt.Int64.lo(days), 1) && U32.is_eq(Qt.Int64.hi(days), 1), "64-bit integer was truncated")
    Qt.QVariant.with(Unit, Qt.QVariant.fromBool(True{}), invalid_conversion)
    byte: Result<&1, &1, U32 & String, Qt.QByteArray> <- Qt.Action.attempt(Qt.QByteArray, Qt.QByteArray.new__Int64_Int32(Qt.Int64{1, 0}, Qt.Int32{300}))
    invalid_byte(byte)
    Qt.QCborValue.with(Unit, Qt.QCborValue.new__Bool(True{}), tagged)
    Qt.QNetworkProxy.with(Unit, Qt.QNetworkProxy.new(), value => proxy(value))
    Qt.QUrl.with(Unit, Qt.QUrl.new__String("https://example.org/score"), default_url)
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Numeric adapters leaked handles")
    Qt.Action.lift(Unit, IO.print("QT612_NUMBERS_OK f64_precision=1 arithmetic=1 int64=1 invalid_input=1 variant_type=1 integer_range=1 enum64=1 aliases=1 defaults=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
