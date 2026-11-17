import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expect_error(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong conversion error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected conversion failure")

def bytes_equal(expected: List<&2, U32>, actual: List<&2, U32>) -> Bool:
  match expected actual:
    case Nil{} Nil{}: True{}
    case a <> rest b <> tail: U32.is_eq(a, b) && bytes_equal(rest, tail)
    case _ _: False{}

def binary() -> List<&2, U32>:
  0 <> 255 <> 65 <> 0 <> Nil{}

def check_bytes(value: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    bytes: List<&2, U32> <- Qt.QByteArray.toBytes(value)
    require(bytes_equal(binary(), bytes), "Binary std::string or copied rvalue lost bytes")

def bytes(+source: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QByteArray.with(Unit, Qt.QByteArray.toStdString(source), check_bytes)
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromStdString(source), check_bytes)
    Qt.QByteArray.with(Unit, Qt.QByteArray.new__QByteArray(source), check_bytes)
    check_bytes(source)

def characters(+query: Qt.QUrlQuery) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QUrlQuery.setQueryDelimiters(query, 61, 59)
    pair: U32 <- Qt.QUrlQuery.queryPairDelimiter(query)
    value: U32 <- Qt.QUrlQuery.queryValueDelimiter(query)
    require(U32.is_eq(pair, 59) && U32.is_eq(value, 61), "QChar code units changed")
    bad: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QUrlQuery.setQueryDelimiters(query, 65536, 59))
    expect_error(Unit, bad, 34)
    unchanged: U32 <- Qt.QUrlQuery.queryValueDelimiter(query)
    require(U32.is_eq(unchanged, 61), "Rejected QChar input mutated Qt")

def duration(+timer: Qt.QTimer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QTimer.setInterval__Milliseconds(timer, Qt.Milliseconds{12345, 0})
    +value: Qt.Milliseconds <- Qt.QTimer.intervalAsDuration(timer)
    require(U32.is_eq(Qt.Milliseconds.lo(value), 12345) && U32.is_eq(Qt.Milliseconds.hi(value), 0), "Chrono count or unit changed")

def latin_value(value: Qt.QJsonValue) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    text: String <- Qt.QJsonValue.toString(value)
    require(String.eq(text, "éA"), "Latin1 input was treated as UTF8")

def latin(source: Qt.QByteArray) -> Qt.Action(Unit):
  Qt.QJsonValue.with(Unit, Qt.QJsonValue.new__QByteArray(source), latin_value)

def json_value(value: Qt.QJsonValue) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    text: String <- Qt.QJsonValue.toString(value)
    require(String.eq(text, "Zażółć 🎵"), "QJsonObject lost Unicode")

def json_object(+value: Qt.QJsonObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    present: Bool <- Qt.QJsonObject.contains(value, "name")
    require(present, "JSON object lost its key")
    Qt.QJsonValue.with(Unit, Qt.QJsonObject.value(value, "name"), json_value)

def json_encoded(value: Qt.QByteArray) -> Qt.Action(Unit):
  Qt.QJsonObject.with(Unit, Qt.QJsonObject.fromJson(value), object => json_object(object))

def json_insert(+object: Qt.QJsonObject, value: Qt.QJsonValue) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QJsonObject.insert(object, "name", value)
    json_object(object)
    Qt.QByteArray.with(Unit, Qt.QJsonObject.toJson(object), json_encoded)

def json(object: Qt.QJsonObject) -> Qt.Action(Unit):
  Qt.QJsonValue.with(Unit, Qt.QJsonValue.new__String("Zażółć 🎵"), value => json_insert(object, value))

def matrix_values() -> List<&2, Qt.F64>:
  Qt.F64{0, 1072693248} <> Qt.F64{0, 1073741824} <> Qt.F64{0, 1074266112} <> Qt.F64{0, 1074790400} <> Nil{}

def matrix_result(values: List<&2, Qt.F64>) -> Qt.Action(Unit):
  match values:
    case a <> b <> c <> d <> Nil{}:
      do Qt.Action<Unit>:
        first: Bool <- Qt.F64.equal(a, Qt.F64{0, 1072693248})
        second: Bool <- Qt.F64.equal(b, Qt.F64{0, 1074266112})
        third: Bool <- Qt.F64.equal(c, Qt.F64{0, 1073741824})
        fourth: Bool <- Qt.F64.equal(d, Qt.F64{0, 1074790400})
        require(first && second && third && fourth, "Matrix transpose or row-major conversion changed")
    case _: Qt.Action.fail(Unit, 1, "Wrong matrix shape")

def matrix_transposed(value: Qt.QMatrix2x2) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    values: List<&2, Qt.F64> <- Qt.QMatrix2x2.toValues(value)
    matrix_result(values)

def matrix(+value: Qt.QMatrix2x2) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    entry: Qt.F64 <- Qt.QMatrix2x2.op_call(value, Qt.Int32{0}, Qt.Int32{1})
    correct: Bool <- Qt.F64.equal(entry, Qt.F64{0, 1073741824})
    require(correct, "Matrix callable operator changed its row/column order")
    invalid: Result<&1, &1, U32 & String, Qt.F64> <- Qt.Action.attempt(Qt.F64, Qt.QMatrix2x2.op_call(value, Qt.Int32{2}, Qt.Int32{0}))
    expect_error(Qt.F64, invalid, 34)
    Qt.QMatrix2x2.with(Unit, Qt.QMatrix2x2.transposed(value), matrix_transposed)

def collator(value: Qt.QCollator) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    same: Qt.Int32 <- Qt.QCollator.compare__String_String(value, "é", "é")
    require(U32.is_eq(Qt.Int32.word(same), 0), "QCollator value conversion failed")

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes(binary()), value => bytes(value))
    Qt.QUrlQuery.with(Unit, Qt.QUrlQuery.new(), value => characters(value))
    Qt.QTimer.with(Unit, Qt.QTimer.new(), value => duration(value))
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes(233 <> 65 <> Nil{}), latin)
    Qt.QJsonObject.with(Unit, Qt.QJsonObject.new(), json)
    Qt.QMatrix2x2.with(Unit, Qt.QMatrix2x2.fromValues(matrix_values()), value => matrix(value))
    bad_matrix: Result<&1, &1, U32 & String, Qt.QMatrix2x2> <- Qt.Action.attempt(Qt.QMatrix2x2, Qt.QMatrix2x2.fromValues(Nil{}))
    expect_error(Qt.QMatrix2x2, bad_matrix, 22)
    Qt.QCollator.with(Unit, Qt.QCollator.new(), collator)
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Representation adapters leaked native handles")
    Qt.Action.lift(Unit, IO.print("QT612_REPRESENTATIONS_OK qchar=1 chrono=1 latin1=1 binary_std_string=1 copy_rvalue=1 json_object=1 matrix=1 collator=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
