import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def same_bytes(left: List<&2, U32>, right: List<&2, U32>) -> Bool:
  match left right:
    case Nil{} Nil{}: True{}
    case a <> left b <> right: U32.is_eq(a, b) && same_bytes(left, right)
    case _ _: False{}

def error(-A: Type, result: Result<&1, &1, U32 & String, A>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 34), "Wrong image extent error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Image accepted an undersized backing buffer")

def red(+color: Qt.QColor) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    r: Qt.Int32 <- Qt.QColor.red(color)
    g: Qt.Int32 <- Qt.QColor.green(color)
    require(U32.is_eq(Qt.Int32.word(r), 255) && U32.is_eq(Qt.Int32.word(g), 0), "Image no longer aliases its live pixels")

def red_image(image: Qt.QImage) -> Qt.Action(Unit):
  Qt.QColor.with(Unit, Qt.QImage.pixelColor__Int32_Int32(image, Qt.Int32{0}, Qt.Int32{0}), color => red(color))

def write_red(bytes: Qt.QByteArray, view: Qt.MemoryView) -> Qt.Action(Unit):
  Qt.MemoryView.write(view, Qt.UInt64{0, 0}, bytes)

def paint_buffer(view: Qt.MemoryView) -> Qt.Action(Unit):
  Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes([255, 0, 0, 255]), bytes => write_red(bytes, view))

def retained_copy(+buffer: Qt.ImageBuffer, +original: Qt.QImage, +copy: Qt.QImage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QImage.destroy(original)
    Qt.ImageBuffer.destroy(buffer)
    red_image(copy)

def alias_image(+buffer: Qt.ImageBuffer, +image: Qt.QImage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.MemoryView.with(Unit, Qt.ImageBuffer.bytes(buffer), paint_buffer)
    red_image(image)
    Qt.QImage.with(Unit, Qt.QImage.new__QImage(image), copy => retained_copy(buffer, image, copy))

def alias_buffer(+buffer: Qt.ImageBuffer) -> Qt.Action(Unit):
  Qt.QImage.with(Unit, Qt.QImage.fromBuffer(buffer, Qt.Int32{2}, Qt.Int32{1}, Qt.QImage.Format.Format_RGBA8888()), image => alias_image(buffer, image))

def preserved_bytes(bytes: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    values: List<&2, U32> <- Qt.QByteArray.toBytes(bytes)
    require(same_bytes(values, [255, 0, 0, 255]), "Read-only image wrote into original storage")

def readonly_changed(+buffer: Qt.ImageBuffer, +image: Qt.QImage, bytes: Qt.QByteArray, view: Qt.MemoryView) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.MemoryView.write(view, Qt.UInt64{0, 0}, bytes)
    Qt.MemoryView.with(Unit, Qt.ImageBuffer.bytes(buffer), source =>
      Qt.QByteArray.with(Unit, Qt.MemoryView.read(source, Qt.UInt64{0, 0}, Qt.UInt64{4, 0}), preserved_bytes))

def readonly_image(+buffer: Qt.ImageBuffer, +image: Qt.QImage) -> Qt.Action(Unit):
  Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes([0, 255, 0, 255]), bytes =>
    Qt.MemoryView.with(Unit, Qt.QImage.bits(image), view => readonly_changed(buffer, image, bytes, view)))

def readonly_buffer(+buffer: Qt.ImageBuffer) -> Qt.Action(Unit):
  Qt.QImage.with(Unit, Qt.QImage.fromReadOnlyBufferWithStride(buffer, Qt.Int32{1}, Qt.Int32{1}, Qt.Int64{4, 0}, Qt.QImage.Format.Format_RGBA8888()), image => readonly_image(buffer, image))

def input_bytes(bytes: Qt.QByteArray) -> Qt.Action(Unit):
  Qt.ImageBuffer.with(Unit, Qt.ImageBuffer.fromBytes(bytes), buffer => readonly_buffer(buffer))

def bounds(+buffer: Qt.ImageBuffer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    extent: Result<&1, &1, U32 & String, Qt.QImage> <- Qt.Action.attempt(Qt.QImage, Qt.QImage.fromBuffer(buffer, Qt.Int32{3}, Qt.Int32{1}, Qt.QImage.Format.Format_RGBA8888()))
    error(Qt.QImage, extent)
    stride: Result<&1, &1, U32 & String, Qt.QImage> <- Qt.Action.attempt(Qt.QImage, Qt.QImage.fromBufferWithStride(buffer, Qt.Int32{1}, Qt.Int32{2}, Qt.Int64{3, 0}, Qt.QImage.Format.Format_RGBA8888()))
    error(Qt.QImage, stride)

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.ImageBuffer.with(Unit, Qt.ImageBuffer.new(Qt.UInt64{8, 0}), buffer => alias_buffer(buffer))
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes([255, 0, 0, 255]), input_bytes)
    Qt.ImageBuffer.with(Unit, Qt.ImageBuffer.new(Qt.UInt64{8, 0}), buffer => bounds(buffer))
    objects: U32 <- Qt.Runtime.liveObjects()
    pins: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(pins, 0), "Image backing leaked handles")
    Qt.Action.lift(Unit, IO.print("QT612_IMAGE_BUFFERS_OK alias=1 native_copy_lifetime=1 readonly_detach=1 extent=1 stride=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
