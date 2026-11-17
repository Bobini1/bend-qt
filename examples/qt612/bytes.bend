import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expect_error(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong byte conversion error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected byte conversion failure")

def same_bytes(left: List<&2, U32>, right: List<&2, U32>) -> Bool:
  match left right:
    case Nil{} Nil{}: True{}
    case a <> left b <> right: U32.is_eq(a, b) && same_bytes(left, right)
    case _ _: False{}

def all_bytes(+count: Nat) -> List<&2, U32>:
  match count:
    case 0n: Nil{}
    case 1n+rest: U32.from_nat(rest) <> all_bytes(rest)

def binary() -> List<&2, U32>:
  0 <> 255 <> 128 <> 0 <> 65 <> Nil{}

def check_bytes(expected: List<&2, U32>, value: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    actual: List<&2, U32> <- Qt.QByteArray.toBytes(value)
    require(same_bytes(expected, actual), "Binary data lost bytes or length")

def view_input(+data: Qt.QByteArray, +needle: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    found: Bool <- Qt.QByteArray.contains__QByteArray(data, needle)
    require(found, "QByteArrayView did not preserve embedded zero bytes")
    +position: Qt.Int64 <- Qt.QByteArray.indexOf__QByteArray(data, needle)
    require(U32.is_eq(Qt.Int64.lo(position), 2) && U32.is_eq(Qt.Int64.hi(position), 0), "QByteArrayView matched at the wrong offset")
    Qt.QByteArray.push_back__QByteArray(data,needle)
    check_bytes(0 <> 255 <> 128 <> 0 <> 65 <> 128 <> 0 <> Nil{}, data)
    wrong: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QByteArray.push_back__QByteArray(data,Qt.QByteArray{0}))
    expect_error(Unit, wrong, 116)
    check_bytes(0 <> 255 <> 128 <> 0 <> 65 <> 128 <> 0 <> Nil{}, data)

def view_source(data: Qt.QByteArray) -> Qt.Action(Unit):
  Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes(128 <> 0 <> Nil{}), needle => view_input(data, needle))

def header_copy(+headers: Qt.QHttpHeaders) -> Qt.Action(Qt.QByteArray):
  do Qt.Action<Qt.QByteArray>:
    added: Bool <- Qt.QHttpHeaders.append__String_String(headers, "x-copy", "saved")
    require(added, "Could not create the view-return test header")
    Qt.QHttpHeaders.valueAt(headers, Qt.Int64{0, 0})

def fallback_copy(headers: Qt.QHttpHeaders, +source: Qt.QByteArray) -> Qt.Action(Qt.QByteArray):
  do Qt.Action<Qt.QByteArray>:
    +copy: Qt.QByteArray <- Qt.QHttpHeaders.value__String_QByteArray(headers, "x-missing", source)
    Qt.QByteArray.clear(source)
    check_bytes(binary(), copy)
    return copy

def fallback_header(headers: Qt.QHttpHeaders) -> Qt.Action(Qt.QByteArray):
  Qt.QByteArray.with(Qt.QByteArray, Qt.QByteArray.fromBytes(binary()), source => fallback_copy(headers, source))

def empty_default(headers: Qt.QHttpHeaders) -> Qt.Action(Unit):
  Qt.QByteArray.with(Unit, Qt.QHttpHeaders.value__String(headers, "x-missing"), value => check_bytes(Nil{}, value))

def color_components(+value: Qt.QRgba64) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    red: U32 <- Qt.QRgba64.red(value)
    green: U32 <- Qt.QRgba64.green(value)
    blue: U32 <- Qt.QRgba64.blue(value)
    alpha: U32 <- Qt.QRgba64.alpha(value)
    require(U32.is_eq(red, 65535) && U32.is_eq(green, 32768) && U32.is_eq(blue, 1) && U32.is_eq(alpha, 65535), "ushort alias lost 16-bit color data")

def color_value(value: Qt.QColor) -> Qt.Action(Unit):
  Qt.QRgba64.with(Unit, Qt.QColor.rgba64(value), rgba => color_components(rgba))

def wrong_type(value: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    result: Result<&1, &1, U32 & String, List<&2, U32>> <- Qt.Action.attempt(List<&2, U32>, Qt.QByteArray.toBytes(Qt.QByteArray{Qt.QObject.word(value)}))
    expect_error(List<&2, U32>, result, 22)

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes(all_bytes(256n)), value => check_bytes(all_bytes(256n), value))
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes(Nil{}), value => check_bytes(Nil{}, value))
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes(binary()), view_source)
    Qt.QByteArray.with(Unit, Qt.QHttpHeaders.with(Qt.QByteArray, Qt.QHttpHeaders.new(), headers => header_copy(headers)), value => check_bytes(115 <> 97 <> 118 <> 101 <> 100 <> Nil{}, value))
    Qt.QByteArray.with(Unit, Qt.QHttpHeaders.with(Qt.QByteArray, Qt.QHttpHeaders.new(), fallback_header), value => check_bytes(binary(), value))
    Qt.QHttpHeaders.with(Unit, Qt.QHttpHeaders.new(), empty_default)
    bad: Result<&1, &1, U32 & String, Qt.QByteArray> <- Qt.Action.attempt(Qt.QByteArray, Qt.QByteArray.fromBytes(0 <> 256 <> Nil{}))
    expect_error(Qt.QByteArray, bad, 34)
    Qt.QObject.with(Unit, Qt.QObject.new(), wrong_type)
    Qt.QColor.with(Unit, Qt.QColor.fromRgba64__U32_U32_U32_U32(65535, 32768, 1, 65535), color_value)
    bad_color: Result<&1, &1, U32 & String, Qt.QColor> <- Qt.Action.attempt(Qt.QColor, Qt.QColor.fromRgba64__U32_U32_U32_U32(65536, 0, 0, 65535))
    expect_error(Qt.QColor, bad_color, 34)
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Byte adapters leaked handles")
    Qt.Action.lift(Unit, IO.print("QT612_BYTES_OK all_bytes=1 binary=1 view_input=1 copied_views=1 source_mutation=1 source_destruction=1 invalid_input=1 narrow_alias=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
