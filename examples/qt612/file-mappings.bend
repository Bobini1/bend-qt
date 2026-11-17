import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def error(~A: Type, expected: U32, result: Result<&1, &1, U32 & String, A>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong mapping error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Invalid mapping operation succeeded")

def bytes(value: Qt.QByteArray, expected: String) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    text: String <- Qt.QByteArray.utf8(value)
    require(String.eq(text, expected), "Mapped storage has wrong bytes")

def mapping(+view: Qt.MemoryView, +file: Qt.QTemporaryFile) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QByteArray.with(Unit, Qt.MemoryView.read(view, Qt.UInt64{0, 0}, Qt.UInt64{4, 0}), value => bytes(value, "abcd"))
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromUtf8("XY"), value => Qt.MemoryView.write(view, Qt.UInt64{1, 0}, value))
    blocked: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.QTemporaryFile.resize__Int64(file, Qt.Int64{1, 0}))
    error(Bool, 16, blocked)
    Qt.QTemporaryFile.close(file)
    Qt.QByteArray.with(Unit, Qt.MemoryView.read(view, Qt.UInt64{0, 0}, Qt.UInt64{4, 0}), value => bytes(value, "aXYd"))
    unmapped: Bool <- Qt.QTemporaryFile.unmap(file, view)
    require(unmapped, "Unmap failed")
    stale: Result<&1, &1, U32 & String, Qt.QByteArray> <- Qt.Action.attempt(Qt.QByteArray, Qt.MemoryView.read(view, Qt.UInt64{0, 0}, Qt.UInt64{1, 0}))
    error(Qt.QByteArray, 116, stale)

def file(+value: Qt.QTemporaryFile) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    opened: Bool <- Qt.QTemporaryFile.open(value)
    require(opened, "Temporary file did not open")
    written: Qt.Int64 <- Qt.QTemporaryFile.write__String(value, "abcd")
    require(U32.is_eq(Qt.Int64.lo(written), 4), "Temporary file write failed")
    flushed: Bool <- Qt.QTemporaryFile.flush(value)
    require(flushed, "Temporary file flush failed")
    Qt.MemoryView.with(Unit, Qt.QTemporaryFile.map__Int64_Int64(value, Qt.Int64{0, 0}, Qt.Int64{4, 0}), view => mapping(view, value))
    reopened: Bool <- Qt.QTemporaryFile.open(value)
    require(reopened, "File mapping retained file storage after cleanup")
    Qt.MemoryView.with(Unit, Qt.QTemporaryFile.map__Int64_Int64(value, Qt.Int64{0, 0}, Qt.Int64{4, 0}), view => Qt.Action.pure(Unit, Unit{}))
    resized: Bool <- Qt.QTemporaryFile.resize__Int64(value, Qt.Int64{2, 0})
    require(resized, "Scoped mapping cleanup did not permit resizing")

def buffer_view(+view: Qt.MemoryView, +array: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromUtf8("XY"), value => Qt.MemoryView.write(view, Qt.UInt64{1, 0}, value))
    bytes(array, "aXYd")
    Qt.QByteArray.resize__Int64(array, Qt.Int64{1, 0})
    stale: Result<&1, &1, U32 & String, Qt.QByteArray> <- Qt.Action.attempt(Qt.QByteArray, Qt.MemoryView.read(view, Qt.UInt64{0, 0}, Qt.UInt64{1, 0}))
    error(Qt.QByteArray, 116, stale)

def buffer(+value: Qt.QByteArray) -> Qt.Action(Unit):
  Qt.MemoryView.with(Unit, Qt.QByteArray.data(value), view => buffer_view(view, value))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QTemporaryFile.with(Unit, Qt.QTemporaryFile.new(), value => file(value))
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromUtf8("abcd"), value => buffer(value))
    objects: U32 <- Qt.Runtime.liveObjects()
    pins: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(pins, 0), "Mapped storage leaked handles or pins")
    Qt.Action.lift(Unit, IO.print("QT612_FILE_MAPPINGS_OK map=1 write=1 closed_file=1 unmap=1 scoped_unmap=1 storage_guard=1 byte_view=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
