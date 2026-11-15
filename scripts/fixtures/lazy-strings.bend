import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def failed(~A: Type, expected: U32, value: Result<&1, &1, U32 & String, A>) -> Qt.Action(Unit):
  match value:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong deferred error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Invalid deferred operation succeeded")

def same(left: List<&2, U32>, right: List<&2, U32>) -> Bool:
  match left right:
    case Nil{} Nil{}: True{}
    case x <> xs y <> ys: U32.is_eq(x, y) && same(xs, ys)
    case _ _: False{}

def show(bytes: List<&2, U32>) -> String:
  match bytes:
    case Nil{}: ""
    case byte <> tail: U32.show(byte) ++ " " ++ show(tail)

def bytes_equal(expected: List<&2, U32>, value: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +bytes: List<&2, U32> <- Qt.QByteArray.toBytes(value)
    Qt.Action.lift(Unit, IO.print("bytes: " ++ show(bytes)))
    require(same(bytes, expected), "Deferred byte storage changed")

def acquire_input(decoder: Qt.QStringDecoder, +bytes: Qt.QByteArray) -> Qt.Action(Qt.QStringDecoder__EncodedData_QByteArrayView):
  do Qt.Action<Qt.QStringDecoder__EncodedData_QByteArrayView>:
    record: Qt.QStringDecoder__EncodedData_QByteArrayView <- Qt.QStringDecoder.decode(decoder, bytes)
    Qt.QByteArray.clear(bytes)
    Qt.Action.pure(Qt.QStringDecoder__EncodedData_QByteArrayView, record)

def acquire_decoder(decoder: Qt.QStringDecoder) -> Qt.Action(Qt.QStringDecoder__EncodedData_QByteArrayView):
  Qt.QByteArray.with(Qt.QStringDecoder__EncodedData_QByteArrayView, Qt.QByteArray.fromBytes(195 <> Nil{}), bytes => acquire_input(decoder, bytes))

def acquire() -> Qt.Action(Qt.QStringDecoder__EncodedData_QByteArrayView):
  Qt.QStringDecoder.with(Qt.QStringDecoder__EncodedData_QByteArrayView, Qt.QStringDecoder.new__QStringConverter_Encoding(Qt.QStringConverter.Encoding.Utf8()), acquire_decoder)

def blocked_move(decoder: Qt.QStringDecoder, +other: Qt.QStringDecoder) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    result: Result<&1, &1, U32 & String, Qt.QStringConverter> <- Qt.Action.attempt(Qt.QStringConverter, Qt.QStringDecoder.op_assign(decoder, Qt.QStringDecoder.as_QStringConverter(other)))
    failed(Qt.QStringConverter, 16, result)
    valid: Bool <- Qt.QStringDecoder.isValid(other)
    require(valid, "Rejected converter assignment consumed its source")

def suffix(+original: Qt.QStringDecoder__EncodedData_QByteArrayView, +copy: Qt.QStringDecoder__EncodedData_QByteArrayView, +input: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    count: U32 <- Qt.Runtime.liveObjects()
    held: U32 <- Qt.Runtime.liveRetentions()
    Qt.Fixture.failAfter(1)
    allocation: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QStringDecoder__EncodedData_QByteArrayView.Fields.set_data(copy, input))
    failed(Unit, 12, allocation)
    count_after: U32 <- Qt.Runtime.liveObjects()
    held_after: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(count, count_after) && U32.is_eq(held, held_after), "Deferred rollback leaked state")
    Qt.Action.lift(Unit, IO.print("lazy: preserved prefix"))
    Qt.QByteArray.with(Unit, Qt.QStringDecoder__EncodedData_QByteArrayView.Fields.data(copy), bytes => bytes_equal(195 <> Nil{}, bytes))
    Qt.QStringDecoder__EncodedData_QByteArrayView.Fields.set_data(copy, input)
    Qt.QByteArray.destroy(input)
    prefix: String <- Qt.QStringDecoder__EncodedData_QByteArrayView.value(original)
    require(String.eq(prefix, ""), "Native conversion was performed before value()")
    Qt.QStringDecoder__EncodedData_QByteArrayView.destroy(original)
    complete: String <- Qt.QStringDecoder__EncodedData_QByteArrayView.value(copy)
    require(String.eq(complete, "é"), "Deferred copies did not share actual converter state")
    +decoder: Qt.QStringDecoder <- Qt.QStringDecoder__EncodedData_QByteArrayView.Fields.decoder(copy)
    Qt.QStringDecoder.with(Unit, Qt.QStringDecoder.new__QStringConverter_Encoding(Qt.QStringConverter.Encoding.Utf8()), other => blocked_move(decoder, other))
    blocked: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QStringDecoder.destroy(decoder))
    failed(Unit, 16, blocked)
    Qt.QStringDecoder.resetState(decoder)
    _text: String <- Qt.QStringDecoder__EncodedData_QByteArrayView.value(copy)
    invalid: Bool <- Qt.QStringDecoder.hasError(decoder)
    require(invalid, "Explicit converter state mutation did not reach deferred values")

def copied(+original: Qt.QStringDecoder__EncodedData_QByteArrayView, +copy: Qt.QStringDecoder__EncodedData_QByteArrayView) -> Qt.Action(Unit):
  Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes(169 <> Nil{}), bytes => suffix(original, copy, bytes))

def decoder_record(+value: Qt.QStringDecoder__EncodedData_QByteArrayView) -> Qt.Action(Unit):
  Qt.QStringDecoder__EncodedData_QByteArrayView.with(Unit, Qt.QStringDecoder__EncodedData_QByteArrayView.new__QStringDecoder__EncodedData_QByteArrayView(value), copy => copied(value, copy))

def encoded_second(+original: Qt.QStringEncoder__DecodedData_QStringView, +copy: Qt.QStringEncoder__DecodedData_QStringView) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QStringEncoder__DecodedData_QStringView.Fields.set_data(copy, "B")
    Qt.Action.lift(Unit, IO.print("lazy: first encoder value"))
    Qt.QByteArray.with(Unit, Qt.QStringEncoder__DecodedData_QStringView.value(original), bytes => bytes_equal(239 <> 187 <> 191 <> 65 <> Nil{}, bytes))
    Qt.QStringEncoder__DecodedData_QStringView.destroy(original)
    Qt.Action.lift(Unit, IO.print("lazy: second encoder value"))
    Qt.QByteArray.with(Unit, Qt.QStringEncoder__DecodedData_QStringView.value(copy), bytes => bytes_equal(66 <> Nil{}, bytes))

def encoded(+value: Qt.QStringEncoder__DecodedData_QStringView) -> Qt.Action(Unit):
  Qt.QStringEncoder__DecodedData_QStringView.with(Unit, Qt.QStringEncoder__DecodedData_QStringView.new__QStringEncoder__DecodedData_QStringView(value), copy => encoded_second(value, copy))

def acquire_encoder(value: Qt.QStringEncoder) -> Qt.Action(Qt.QStringEncoder__DecodedData_QStringView):
  Qt.QStringEncoder.encode(value, "A")

def encoder() -> Qt.Action(Unit):
  Qt.QStringEncoder__DecodedData_QStringView.with(Unit, Qt.QStringEncoder.with(Qt.QStringEncoder__DecodedData_QStringView, Qt.QStringEncoder.new__QStringConverter_Encoding_Flags_QStringConverterBase__Flag(Qt.QStringConverter.Encoding.Utf8(), Qt.Flags_QStringConverterBase__Flag{4}), acquire_encoder), value => encoded(value))

def empty(+value: Qt.QStringDecoder__EncodedData_QByteArrayView) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    result: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QStringDecoder__EncodedData_QByteArrayView.value(value))
    failed(String, 22, result)

def interval(+timer: Qt.QAbstractEventDispatcher.TimerInfoV2, +ticks: Qt.Nanoseconds) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QAbstractEventDispatcher.TimerInfoV2.Fields.set_interval(timer, ticks)
    +actual: Qt.Nanoseconds <- Qt.QAbstractEventDispatcher.TimerInfoV2.Fields.interval(timer)
    require(U32.is_eq(Qt.Nanoseconds.lo(actual), Qt.Nanoseconds.lo(ticks)) && U32.is_eq(Qt.Nanoseconds.hi(actual), Qt.Nanoseconds.hi(ticks)), "Timer duration changed ticks")

def timer(+value: Qt.QAbstractEventDispatcher.TimerInfoV2) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    interval(value, Qt.Nanoseconds{0, 0})
    interval(value, Qt.Nanoseconds{7, 0})
    interval(value, Qt.Nanoseconds{0, 2147483648})
    interval(value, Qt.Nanoseconds{4294967295, 2147483647})

def rebound_data(+value: Qt.QStringDecoder__EncodedData_QByteArrayView, input: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QStringDecoder__EncodedData_QByteArrayView.Fields.set_data(value, input)
    text: String <- Qt.QStringDecoder__EncodedData_QByteArrayView.value(value)
    require(String.eq(text, "A"), "Observed replacement converter did not decode the owned input")

def rebound_converter(+value: Qt.QStringDecoder__EncodedData_QByteArrayView, old: Qt.QStringDecoder, next: Qt.QStringDecoder) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QStringDecoder__EncodedData_QByteArrayView.Fields.set_decoder(value, next)
    Qt.QStringDecoder.destroy(old)
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes(65 <> Nil{}), bytes => rebound_data(value, bytes))

def original_converter(+value: Qt.QStringDecoder__EncodedData_QByteArrayView, +old: Qt.QStringDecoder) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QStringDecoder__EncodedData_QByteArrayView.Fields.set_decoder(value, old)
    Qt.QStringDecoder.with(Unit, Qt.QStringDecoder.new__QStringConverter_Encoding(Qt.QStringConverter.Encoding.Utf8()), next => rebound_converter(value, old, next))

def rebind(value: Qt.QStringDecoder__EncodedData_QByteArrayView) -> Qt.Action(Unit):
  Qt.QStringDecoder.with(Unit, Qt.QStringDecoder.new__QStringConverter_Encoding(Qt.QStringConverter.Encoding.Utf8()), old => original_converter(value, old))

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QStringDecoder__EncodedData_QByteArrayView.with(Unit, acquire(), value => decoder_record(value))
    encoder()
    Qt.QStringDecoder__EncodedData_QByteArrayView.with(Unit, Qt.QStringDecoder__EncodedData_QByteArrayView.new(), value => empty(value))
    Qt.QAbstractEventDispatcher.TimerInfoV2.with(Unit, Qt.QAbstractEventDispatcher.TimerInfoV2.new(), value => timer(value))
    Qt.QStringDecoder__EncodedData_QByteArrayView.with(Unit, Qt.QStringDecoder__EncodedData_QByteArrayView.new(), rebind)
    count: U32 <- Qt.Runtime.liveObjects()
    held: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(count, 0) && U32.is_eq(held, 0), "Deferred conversions leaked registry state")
    Qt.Action.lift(Unit, IO.print("QT612_LAZY_STRINGS_OK input=1 converter=1 copy=1 lazy=1 state=1 rollback=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
