import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def bitmap_image(+image: Qt.QImage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    first: Qt.Int32 <- Qt.QImage.pixelIndex__Int32_Int32(image, Qt.Int32{0}, Qt.Int32{0})
    second: Qt.Int32 <- Qt.QImage.pixelIndex__Int32_Int32(image, Qt.Int32{1}, Qt.Int32{0})
    require(U32.is_eq(Qt.Int32.word(first), 1) && U32.is_eq(Qt.Int32.word(second), 0), "Bitmap byte-aligned input changed its bit order")

def bitmap_result(value: Qt.QBitmap) -> Qt.Action(Unit):
  Qt.QImage.with(Unit, Qt.QBitmap.toImage(value), image => bitmap_image(image))

def bitmap_bytes(size: Qt.QSize, bytes: Qt.QByteArray) -> Qt.Action(Unit):
  Qt.QBitmap.with(Unit, Qt.QBitmap.fromData(size, bytes, Qt.QImage.Format.Format_MonoLSB()), bitmap_result)

def bitmap_size(size: Qt.QSize) -> Qt.Action(Unit):
  Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes(1 <> Nil{}), bytes => bitmap_bytes(size, bytes))

def uuid_value(value: Qt.QUuid) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    text: String <- Qt.QUuid.toString__QUuid_StringFormat(value, Qt.QUuid.StringFormat.WithoutBraces())
    require(String.eq(text, "00112233-4455-6677-8899-aabbccddeeff"), "Fixed-size UUID bytes changed order")

def uuid_bytes(bytes: Qt.QByteArray) -> Qt.Action(Unit):
  Qt.QUuid.with(Unit, Qt.QUuid.fromBytes(bytes, Qt.QSysInfo.Endian.BigEndian()), uuid_value)

def collator(value: Qt.QCollator) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    comparison: Qt.Int32 <- Qt.QCollator.compare__List_U32_Int64_List_U32_Int64(value, 65 <> Nil{}, Qt.Int64{1, 0}, 66 <> Nil{}, Qt.Int64{1, 0})
    require(U32.is_gt(Qt.Int32.word(comparison), 2147483647), "Bounded UTF-16 collation changed ordering")

def random_compare(left: Qt.QRandomGenerator, right: Qt.QRandomGenerator) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    first: U32 <- Qt.QRandomGenerator.generate(left)
    second: U32 <- Qt.QRandomGenerator.generate(right)
    require(U32.is_eq(first, second), "Pointer-range seed and pointer-count seed disagree")

def random_left(left: Qt.QRandomGenerator) -> Qt.Action(Unit):
  Qt.QRandomGenerator.with(Unit, Qt.QRandomGenerator.new__List_U32_Int64(1 <> 2 <> 3 <> Nil{}, Qt.Int64{3, 0}), right => random_compare(left, right))

def random_empty(value: Qt.QRandomGenerator) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    ignored: U32 <- Qt.QRandomGenerator.generate(value)
    Qt.Action.pure(Unit, Unit{})

def random_rejected(result: Result<&1, &1, U32 & String, Qt.QRandomGenerator>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 34), "Wrong pointer-range bounds error")
    case Done{value}: Qt.Action.finally(Unit, Qt.Action.fail(Unit, 1, "Seed pointer range exceeded its list"), Qt.QRandomGenerator.release(value))

def audio_bytes(format: Qt.QAudioFormat, bytes: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    sample: Qt.F64 <- Qt.QAudioFormat.normalizedSampleValue(format, bytes)
    one: Bool <- Qt.F64.equal(sample, Qt.F64{0, 1072693248})
    require(one, "Typed audio sample scratch changed its normalized value")

def audio(+format: Qt.QAudioFormat) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QAudioFormat.setSampleFormat(format, Qt.QAudioFormat.SampleFormat.Int16())
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes(255 <> 127 <> Nil{}), bytes => audio_bytes(format, bytes))

def exception(value: Qt.Outputs_QJSValue_List_String) -> Qt.Action(Unit):
  match value:
    case Qt.Outputs_QJSValue_List_String{result, trace}:
      require(Bool.not(List.is_empty(&2, String, trace)), "JavaScript exception output pointer lost its stack")

def engine(value: Qt.QJSEngine) -> Qt.Action(Unit):
  Qt.Outputs_QJSValue_List_String.with(Unit, Qt.QJSEngine.evaluate(value, "throw 42", "bounded-inputs.js", Qt.Int32{1}), exception)

def bit_number(value: Qt.Outputs_U32_Bool) -> Qt.Action(Unit):
  match value:
    case Qt.Outputs_U32_Bool{number, ok}:
      require(ok && U32.is_eq(number, 7), "Scalar success output was not returned")

def bits(value: Qt.QBitArray) -> Qt.Action(Unit):
  Qt.Outputs_U32_Bool.with(Unit, Qt.QBitArray.toUInt32(value, Qt.QSysInfo.Endian.LittleEndian()), bit_number)

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QSize.with(Unit, Qt.QSize.new__Int32_Int32(Qt.Int32{2}, Qt.Int32{1}), bitmap_size)
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes(0 <> 17 <> 34 <> 51 <> 68 <> 85 <> 102 <> 119 <> 136 <> 153 <> 170 <> 187 <> 204 <> 221 <> 238 <> 255 <> Nil{}), uuid_bytes)
    Qt.QCollator.with(Unit, Qt.QCollator.new(), collator)
    Qt.QRandomGenerator.with(Unit, Qt.QRandomGenerator.new__List_U32_Int64(1 <> 2 <> 3 <> Nil{}, Qt.Int64{3, 0}), random_left)
    Qt.QRandomGenerator.with(Unit, Qt.QRandomGenerator.new__List_U32_Int64(Nil{}, Qt.Int64{0, 0}), random_empty)
    bad: Result<&1, &1, U32 & String, Qt.QRandomGenerator> <- Qt.Action.attempt(Qt.QRandomGenerator, Qt.QRandomGenerator.new__List_U32_Int64(Nil{}, Qt.Int64{1, 0}))
    random_rejected(bad)
    Qt.QAudioFormat.with(Unit, Qt.QAudioFormat.new(), value => audio(value))
    Qt.QJSEngine.with(Unit, Qt.QJSEngine.new(), engine)
    Qt.QBitArray.with(Unit, Qt.QBitArray.new__Int64_Bool(Qt.Int64{3, 0}, True{}), bits)
    count: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(count, 0), "Bounded input conversions leaked native handles")
    Qt.Action.lift(Unit, IO.print("QT612_BOUNDED_INPUTS_OK bitmap=1 uuid=1 utf16=1 seed_range=1 empty_range=1 audio_sample=1 scalar_output=1 exception_stack=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
