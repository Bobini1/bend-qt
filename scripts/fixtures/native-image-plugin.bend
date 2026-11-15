import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def pixel(+image: Qt.QImage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +color: Qt.QColor <- Qt.QImage.pixelColor__Int32_Int32(image, Qt.Int32{1}, Qt.Int32{1})
    red: Qt.Int32 <- Qt.QColor.red(color)
    green: Qt.Int32 <- Qt.QColor.green(color)
    require(U32.is_eq(Qt.Int32.word(red), 255) && U32.is_eq(Qt.Int32.word(green), 0), "Native image handler pixels changed")

def reader(+value: Qt.QImageReader) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    accepted: Bool <- Qt.QImageReader.canRead(value)
    require(accepted, "Qt did not discover the native image plugin")
    Qt.QImage.with(Unit, Qt.QImageReader.read(value), image => pixel(image))

def buffer(+value: Qt.QBuffer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    opened: Bool <- Qt.QBuffer.open(value, Qt.Flags_QIODeviceBase__OpenModeFlag{1})
    require(opened, "Image input buffer did not open")
    +format: Qt.QByteArray <- Qt.QByteArray.fromUtf8("bqtrg")
    Qt.QImageReader.with(Unit, Qt.QImageReader.new__QIODevice_QByteArray(Qt.QBuffer.as_QIODevice(value), format), image => reader(image))

def decode() -> Qt.Action(Unit):
  Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes([66, 81, 84, 49]), bytes => Qt.QBuffer.with(Unit, Qt.QBuffer.new__QByteArray_QObject(bytes, Qt.QObject{0}), value => buffer(value)))

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    path: String <- Qt.CallbackProbe.imagePluginPath()
    Qt.QCoreApplication.addLibraryPath(path)
    Qt.scoped(Unit, decode())
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Native image plugin handles leaked")
    Qt.Action.lift(Unit, IO.print("QT_NATIVE_IMAGE_PLUGIN_OK qt_plugin_discovery=1 image_reader=1 red_pixels=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
