import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def bytes_equal(values: List<&2, U32>) -> Bool:
  match values:
    case 97 <> 98 <> 99 <> 100 <> Nil{}: True{}
    case _: False{}

def verify(value: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    bytes: List<&2, U32> <- Qt.QByteArray.toBytes(value)
    require(bytes_equal(bytes), "Raw GL mapping returned the wrong bytes")

def view(+functions: Qt.QOpenGLExtraFunctions, +value: Qt.MemoryView) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromUtf8("abcd"), bytes => Qt.MemoryView.write(value, Qt.UInt64{0, 0}, bytes))
    Qt.MemoryView.with(Unit, Qt.QOpenGLExtraFunctions.glGetBufferPointerv(functions, 34962, 35005), alias =>
      Qt.QByteArray.with(Unit, Qt.MemoryView.read(alias, Qt.UInt64{0, 0}, Qt.UInt64{4, 0}), bytes => verify(bytes)))

def buffer(+functions: Qt.QOpenGLExtraFunctions, +value: Qt.QOpenGLBuffer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    created: Bool <- Qt.QOpenGLBuffer.create(value)
    require(created, "GL buffer creation failed")
    bound: Bool <- Qt.QOpenGLBuffer.bind(value)
    require(bound, "GL buffer binding failed")
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromUtf8("0000"), bytes => Qt.QOpenGLBuffer.allocate__QByteArray_Int32(value, bytes, Qt.Int32{4}))
    Qt.MemoryView.with(Unit, Qt.QOpenGLExtraFunctions.glMapBufferRange(functions, 34962, Qt.Int64{0, 0}, Qt.Int64{4, 0}, 3), mapped => view(functions, mapped))
    Qt.MemoryView.with(Unit, Qt.QOpenGLBuffer.map(value, Qt.QOpenGLBuffer.Access.ReadOnly()), mapped =>
      Qt.QByteArray.with(Unit, Qt.MemoryView.read(mapped, Qt.UInt64{0, 0}, Qt.UInt64{4, 0}), bytes => verify(bytes)))

def context(+value: Qt.QOpenGLContext, surface: Qt.QSurface) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    created: Bool <- Qt.QOpenGLContext.create(value)
    require(created, "GL context creation failed")
    current: Bool <- Qt.QOpenGLContext.makeCurrent(value, surface)
    require(current, "GL context could not become current")
    Qt.QOpenGLExtraFunctions.with(Unit, Qt.QOpenGLExtraFunctions.new__QOpenGLContext(value), functions =>
      Qt.QOpenGLBuffer.with(Unit, Qt.QOpenGLBuffer.new(), native => buffer(functions, native)))
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
    pins: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(count, 0) && U32.is_eq(pins, 0), "Raw GL mapping scopes leaked resources")
    Qt.Action.lift(Unit, IO.print("QT612_GL_RAW_MAPPINGS_OK raw_range=1 pointer_alias=1 writes=1 reads=1 scope_unmap=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
