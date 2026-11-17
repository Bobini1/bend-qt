import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def error(~A: Type, expected: U32, result: Result<&1, &1, U32 & String, A>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong view error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Invalid memory view operation succeeded")

def red(+value: Qt.QColor) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    r: Qt.Int32 <- Qt.QColor.red(value)
    g: Qt.Int32 <- Qt.QColor.green(value)
    b: Qt.Int32 <- Qt.QColor.blue(value)
    require(U32.is_eq(Qt.Int32.word(r), 255) && U32.is_eq(Qt.Int32.word(g), 0) && U32.is_eq(Qt.Int32.word(b), 0), "View write did not update image pixels")

def write(bytes: Qt.QByteArray, +view: Qt.MemoryView, +image: Qt.QImage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    size: Qt.UInt64 <- Qt.MemoryView.size(view)
    require(U32.is_eq(Qt.UInt64.lo(size), 8), "Wrong image byte extent")
    Qt.MemoryView.write(view, Qt.UInt64{0, 0}, bytes)
    Qt.QColor.with(Unit, Qt.QImage.pixelColor__Int32_Int32(image, Qt.Int32{0}, Qt.Int32{0}), value => red(value))
    destroyed: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QImage.destroy(image))
    error(Unit, 16, destroyed)
    overflow: Result<&1, &1, U32 & String, Qt.QByteArray> <- Qt.Action.attempt(Qt.QByteArray, Qt.MemoryView.read(view, Qt.UInt64{7, 0}, Qt.UInt64{2, 0}))
    error(Qt.QByteArray, 34, overflow)

def mutable_view(view: Qt.MemoryView, image: Qt.QImage) -> Qt.Action(Unit):
  Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes([255, 0, 0, 255]), bytes => write(bytes, view, image))

def read_only(bytes: Qt.QByteArray, view: Qt.MemoryView) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    mutation: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.MemoryView.write(view, Qt.UInt64{0, 0}, bytes))
    error(Unit, 1, mutation)

def stale(+view: Qt.MemoryView, +image: Qt.QImage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QImage.with(Unit, Qt.QImage.new(), replacement => Qt.QImage.swap(image, replacement))
    result: Result<&1, &1, U32 & String, Qt.QByteArray> <- Qt.Action.attempt(Qt.QByteArray, Qt.MemoryView.read(view, Qt.UInt64{0, 0}, Qt.UInt64{1, 0}))
    error(Qt.QByteArray, 116, result)

def image(+value: Qt.QImage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.MemoryView.with(Unit, Qt.QImage.bits(value), view => mutable_view(view, value))
    Qt.MemoryView.with(Unit, Qt.QImage.constBits(value), view => Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes([0]), bytes => read_only(bytes, view)))
    Qt.MemoryView.with(Unit, Qt.QImage.constBits(value), view => stale(view, value))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QImage.with(Unit, Qt.QImage.new__Int32_Int32_QImage_Format(Qt.Int32{2}, Qt.Int32{1}, Qt.QImage.Format.Format_RGBA8888()), value => image(value))
    objects: U32 <- Qt.Runtime.liveObjects()
    pins: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(pins, 0), "Memory view cleanup leaked storage")
    Qt.Action.lift(Unit, IO.print("QT612_MEMORY_VIEWS_OK pixel_write=1 readonly=1 extent=1 retained_owner=1 stale_storage=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
