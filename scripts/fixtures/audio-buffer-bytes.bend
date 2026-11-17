import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def bytes(actual: List<&2, U32>, first: U32) -> Qt.Action(Unit):
  match actual:
    case value <> 2 <> 3 <> Nil{}: require(U32.is_eq(value, first), "Audio byte snapshot changed")
    case _: Qt.Action.fail(Unit, 1, "Audio byte snapshot length changed")

def invalid(result: Result<&1, &1, U32 & String, Unit>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 22), message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Audio replacement resized the native buffer")

def values() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +format: Qt.QAudioFormat <- Qt.QAudioFormat.new()
    Qt.QAudioFormat.setChannelCount(format, Qt.Int32{1})
    Qt.QAudioFormat.setSampleRate(format, Qt.Int32{48000})
    Qt.QAudioFormat.setSampleFormat(format, Qt.QAudioFormat.SampleFormat.UInt8())
    source: Qt.QByteArray <- Qt.QByteArray.fromBytes([1, 2, 3])
    +buffer: Qt.QAudioBuffer <- Qt.QAudioBuffer.new__QByteArray_QAudioFormat(source, format)
    +copy: Qt.QAudioBuffer <- Qt.QAudioBuffer.new__QAudioBuffer(buffer)
    +snapshot: Qt.QByteArray <- Qt.QAudioBuffer.bytes(buffer)
    replacement: Qt.QByteArray <- Qt.QByteArray.fromBytes([9, 2, 3])
    Qt.QAudioBuffer.setBytes(buffer, replacement)
    values: List<&2, U32> <- Qt.QByteArray.toBytes(snapshot)
    bytes(values, 1)
    value: Qt.QByteArray <- Qt.QAudioBuffer.bytes(copy)
    values: List<&2, U32> <- Qt.QByteArray.toBytes(value)
    bytes(values, 1)
    +changed: Qt.QByteArray <- Qt.QAudioBuffer.bytes(buffer)
    Qt.QAudioBuffer.destroy(buffer)
    values: List<&2, U32> <- Qt.QByteArray.toBytes(changed)
    bytes(values, 9)
    short: Qt.QByteArray <- Qt.QByteArray.fromBytes([8])
    rejected: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QAudioBuffer.setBytes(copy, short))
    invalid(rejected)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, values())
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Audio snapshots leaked")
    Qt.Action.lift(Unit, IO.print("QT612_AUDIO_BUFFER_BYTES_OK snapshot=1 writable=1 detach=1 bounds=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
