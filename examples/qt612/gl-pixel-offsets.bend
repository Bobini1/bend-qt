import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def verify_values(values: List<&2, U32>) -> Qt.Action(Unit):
  match values:
    case 97 <> 98 <> 99 <> 100 <> Nil{}: Qt.Action.pure(Unit, Unit{})
    case _: Qt.Action.fail(Unit, 1, "Pixel buffer upload returned different native pixels")

def verify(bytes: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    values: List<&2, U32> <- Qt.QByteArray.toBytes(bytes)
    verify_values(values)

def read(+functions: Qt.QOpenGLFunctions_3_2_Core, +bytes: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QOpenGLFunctions_3_2_Core.glGetTexImage(functions, 3553, Qt.Int32{0}, 6408, 5121, bytes)
    verify(bytes)

def texture(+buffer: Qt.QOpenGLBuffer, +value: Qt.QOpenGLTexture) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QOpenGLTexture.setSize__Int32_Int32(value, Qt.Int32{1}, Qt.Int32{1})
    Qt.QOpenGLTexture.setFormat(value, Qt.QOpenGLTexture.TextureFormat.RGBA8_UNorm())
    Qt.QOpenGLTexture.allocateStorage(value)
    Qt.QOpenGLTexture.setData__QOpenGLTexture_PixelFormat_QOpenGLTexture_PixelType_QByteArray_QOpenGLPixelTransferOptions_bufferOffset(value, Qt.QOpenGLTexture.PixelFormat.RGBA(), Qt.QOpenGLTexture.PixelType.UInt8(), Qt.GLBufferOffset{4, 0}, Qt.QOpenGLPixelTransferOptions{0})
    Qt.QOpenGLBuffer.release(buffer)
    Qt.QOpenGLTexture.bind(value)
    Qt.QOpenGLFunctions_3_2_Core.with(Unit, Qt.QOpenGLFunctions_3_2_Core.new(), functions =>
      Qt.QByteArray.with(Unit, Qt.QByteArray.fromUtf8("0000"), bytes => read(functions, bytes)))

def buffer(+value: Qt.QOpenGLBuffer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    created: Bool <- Qt.QOpenGLBuffer.create(value)
    require(created, "Pixel buffer creation failed")
    bound: Bool <- Qt.QOpenGLBuffer.bind(value)
    require(bound, "Pixel buffer binding failed")
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromUtf8("xxxxabcd"), bytes => Qt.QOpenGLBuffer.allocate__QByteArray_Int32(value, bytes, Qt.Int32{8}))
    Qt.QOpenGLTexture.with(Unit, Qt.QOpenGLTexture.new__QOpenGLTexture_Target(Qt.QOpenGLTexture.Target.Target2D()), native => texture(value, native))

def context(+value: Qt.QOpenGLContext, surface: Qt.QSurface) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    created: Bool <- Qt.QOpenGLContext.create(value)
    require(created, "GL context creation failed")
    current: Bool <- Qt.QOpenGLContext.makeCurrent(value, surface)
    require(current, "GL context could not become current")
    Qt.QOpenGLBuffer.with(Unit, Qt.QOpenGLBuffer.new__QOpenGLBuffer_Type(Qt.QOpenGLBuffer.Type.PixelUnpackBuffer()), native => buffer(native))
    Qt.QOpenGLContext.doneCurrent(value)

def surface(+value: Qt.QOffscreenSurface) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QOffscreenSurface.create(value)
    Qt.QOpenGLContext.with(Unit, Qt.QOpenGLContext.new(), native => context(native, Qt.QOffscreenSurface.as_QSurface(value)))

def format(+value: Qt.QSurfaceFormat) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QSurfaceFormat.setVersion(value, Qt.Int32{3}, Qt.Int32{3})
    Qt.QSurfaceFormat.setProfile(value, Qt.QSurfaceFormat.OpenGLContextProfile.CoreProfile())
    Qt.QSurfaceFormat.setDefaultFormat(value)

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QSurfaceFormat.with(Unit, Qt.QSurfaceFormat.new(), value => format(value))
    Qt.QOffscreenSurface.with(Unit, Qt.QOffscreenSurface.new(), value => surface(value))
    count: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(count, 0), "Pixel buffer scopes leaked native objects")
    Qt.Action.lift(Unit, IO.print("QT612_GL_PIXEL_OFFSETS_OK bound_buffer=1 nonzero_offset=1 native_pixels=1 scoped_cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
