import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def rejected(result: Result<&1, &1, U32 & String, Unit>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 34), message)
    case Done{value}: Qt.Action.fail(Unit, 1, "A narrow stream write accepted an out-of-range value")

def write_numbers(+stream: Qt.QDataStream) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    invalid: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QDataStream.writeUInt8(stream, 256))
    rejected(invalid)
    Qt.QDataStream.setByteOrder(stream, Qt.QDataStream.ByteOrder.BigEndian())
    Qt.QDataStream.writeBool(stream, True{})
    Qt.QDataStream.writeInt8(stream, Qt.Int32.neg(128))
    Qt.QDataStream.writeUInt8(stream, 255)
    Qt.QDataStream.writeInt16(stream, Qt.Int32.neg(32768))
    Qt.QDataStream.writeUInt16(stream, 65535)
    Qt.QDataStream.writeInt32(stream, Qt.Int32{2147483648})
    Qt.QDataStream.writeUInt32(stream, 4294967295)
    Qt.QDataStream.writeInt64(stream, Qt.Int64{0, 2147483648})
    Qt.QDataStream.writeUInt64(stream, Qt.UInt64{4294967295, 4294967295})
    Qt.QDataStream.setFloatingPointPrecision(stream, Qt.QDataStream.FloatingPointPrecision.SinglePrecision())
    Qt.QDataStream.writeFloat(stream, Qt.F64{0, 1072955392})
    Qt.QDataStream.setFloatingPointPrecision(stream, Qt.QDataStream.FloatingPointPrecision.DoublePrecision())
    Qt.QDataStream.writeDouble(stream, Qt.F64{0, 1072955392})

def native_bytes(values: List<&2, U32>) -> Qt.Action(Unit):
  match values:
    case 1 <> 128 <> 255 <> 128 <> 0 <> 255 <> 255 <>
      128 <> 0 <> 0 <> 0 <> 255 <> 255 <> 255 <> 255 <>
      128 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <>
      255 <> 255 <> 255 <> 255 <> 255 <> 255 <> 255 <> 255 <>
      63 <> 160 <> 0 <> 0 <> 63 <> 244 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> Nil{}:
      Qt.Action.pure(Unit, Unit{})
    case _: Qt.Action.fail(Unit, 1, "QDataStream widths, byte order or floating-point precision changed")

def read_numbers(+stream: Qt.QDataStream) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    flag: Bool <- Qt.QDataStream.readBool(stream)
    require(flag, "Stream bool changed")
    i8: Qt.Int32 <- Qt.QDataStream.readInt8(stream)
    require(U32.is_eq(Qt.Int32.word(i8), 4294967168), "Stream int8 changed")
    u8: U32 <- Qt.QDataStream.readUInt8(stream)
    require(U32.is_eq(u8, 255), "Stream uint8 changed")
    i16: Qt.Int32 <- Qt.QDataStream.readInt16(stream)
    require(U32.is_eq(Qt.Int32.word(i16), 4294934528), "Stream int16 changed")
    u16: U32 <- Qt.QDataStream.readUInt16(stream)
    require(U32.is_eq(u16, 65535), "Stream uint16 changed")
    i32: Qt.Int32 <- Qt.QDataStream.readInt32(stream)
    require(U32.is_eq(Qt.Int32.word(i32), 2147483648), "Stream int32 changed")
    u32: U32 <- Qt.QDataStream.readUInt32(stream)
    require(U32.is_eq(u32, 4294967295), "Stream uint32 changed")
    +i64: Qt.Int64 <- Qt.QDataStream.readInt64(stream)
    require(U32.is_eq(Qt.Int64.lo(i64), 0) && U32.is_eq(Qt.Int64.hi(i64), 2147483648), "Stream int64 lost bits")
    +u64: Qt.UInt64 <- Qt.QDataStream.readUInt64(stream)
    require(U32.is_eq(Qt.UInt64.lo(u64), 4294967295) && U32.is_eq(Qt.UInt64.hi(u64), 4294967295), "Stream uint64 lost bits")
    Qt.QDataStream.setFloatingPointPrecision(stream, Qt.QDataStream.FloatingPointPrecision.SinglePrecision())
    +real: Qt.F64 <- Qt.QDataStream.readFloat(stream)
    require(U32.is_eq(Qt.F64.lo(real), 0) && U32.is_eq(Qt.F64.hi(real), 1072955392), "Stream float changed")
    Qt.QDataStream.setFloatingPointPrecision(stream, Qt.QDataStream.FloatingPointPrecision.DoublePrecision())
    +real: Qt.F64 <- Qt.QDataStream.readDouble(stream)
    require(U32.is_eq(Qt.F64.lo(real), 0) && U32.is_eq(Qt.F64.hi(real), 1072955392), "Stream double changed")
    done: Bool <- Qt.QDataStream.atEnd(stream)
    require(done, "Stream width mismatch left unread bytes")
    status: Qt.QDataStream.Status <- Qt.QDataStream.status(stream)
    require(U32.is_eq(Qt.QDataStream.Status.word(status), 0), "Valid stream read changed its status")
    missing: U32 <- Qt.QDataStream.readUInt8(stream)
    status: Qt.QDataStream.Status <- Qt.QDataStream.status(stream)
    require(U32.is_eq(missing, 0) && U32.is_eq(Qt.QDataStream.Status.word(status), 1), "Stream EOF did not preserve Qt status semantics")

def numbers() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +bytes: Qt.QByteArray <- Qt.QByteArray.new()
    +writer: Qt.QDataStream <- Qt.QDataStream.new__QByteArray_Flags_QIODeviceBase__OpenModeFlag(bytes, Qt.Flags_QIODeviceBase__OpenModeFlag{2})
    write_numbers(writer)
    Qt.QDataStream.release(writer)
    values: List<&2, U32> <- Qt.QByteArray.toBytes(bytes)
    native_bytes(values)
    +reader: Qt.QDataStream <- Qt.QDataStream.new__QByteArray(bytes)
    read_numbers(reader)

def write_text(+stream: Qt.QDataStream) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QDataStream.writeString(stream, "Bend żółw")
    Qt.QDataStream.writeQString(stream, "Qt λ")
    Qt.QDataStream.writeQChar(stream, 955)
    Qt.QDataStream.writeQStringList(stream, ["one", "dwa"])
    +value: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.int32(), Qt.Int32{42})
    Qt.QDataStream.writeQVariant(stream, value)

def names(values: List<&2, String>) -> Qt.Action(Unit):
  match values:
    case first <> second <> Nil{}: require(String.eq(first, "one") && String.eq(second, "dwa"), "Stream QStringList changed")
    case _: Qt.Action.fail(Unit, 1, "Stream QStringList changed length")

def read_text(+stream: Qt.QDataStream) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    text: String <- Qt.QDataStream.readString(stream)
    require(String.eq(text, "Bend żółw"), "Stream string changed")
    text: String <- Qt.QDataStream.readQString(stream)
    require(String.eq(text, "Qt λ"), "Stream QString changed")
    character: U32 <- Qt.QDataStream.readQChar(stream)
    require(U32.is_eq(character, 955), "Stream QChar changed")
    values: List<&2, String> <- Qt.QDataStream.readQStringList(stream)
    names(values)
    +value: Qt.QVariant <- Qt.QDataStream.readQVariant(stream)
    number: Qt.Int32 <- Qt.QVariant.toValue(~Qt.int32(), value)
    require(U32.is_eq(Qt.Int32.word(number), 42), "Stream QVariant changed")

def text() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +bytes: Qt.QByteArray <- Qt.QByteArray.new()
    +writer: Qt.QDataStream <- Qt.QDataStream.new__QByteArray_Flags_QIODeviceBase__OpenModeFlag(bytes, Qt.Flags_QIODeviceBase__OpenModeFlag{2})
    write_text(writer)
    Qt.QDataStream.release(writer)
    +reader: Qt.QDataStream <- Qt.QDataStream.new__QByteArray(bytes)
    read_text(reader)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, numbers())
    Qt.scoped(Unit, text())
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Typed stream operations leaked handles")
    Qt.Action.lift(Unit, IO.print("QT612_DATA_STREAM_VALUES_OK widths=1 bytes=1 float=1 text=1 variant=1 status=1 bounds=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
