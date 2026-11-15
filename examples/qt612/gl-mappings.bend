import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def error(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong GL mapping error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected checked GL mapping failure")

def bytes(value: List<&2, U32>) -> Bool:
  match value:
    case 0 <> 9 <> 8 <> 0 <> Nil{}: True{}
    case _: False{}

def verify(value: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    actual: List<&2, U32> <- Qt.QByteArray.toBytes(value)
    require(bytes(actual), "GL mapped writes did not reach the buffer")

def read_only(+view: Qt.MemoryView, +source: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QByteArray.with(Unit, Qt.MemoryView.read(view, Qt.UInt64{0, 0}, Qt.UInt64{4, 0}), value => verify(value))
    denied: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.MemoryView.write(view, Qt.UInt64{0, 0}, source))
    error(Unit, denied, 1)

def mapped(+buffer: Qt.QOpenGLBuffer, +view: Qt.MemoryView, +source: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    duplicate: Result<&1, &1, U32 & String, Qt.MemoryView> <- Qt.Action.attempt(Qt.MemoryView, Qt.QOpenGLBuffer.map(buffer, Qt.QOpenGLBuffer.Access.ReadWrite()))
    error(Qt.MemoryView, duplicate, 16)
    held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QOpenGLBuffer.allocate__QByteArray_Int32(buffer, source, Qt.Int32{2}))
    error(Unit, held, 16)
    Qt.MemoryView.write(view, Qt.UInt64{1, 0}, source)
    over: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.MemoryView.write(view, Qt.UInt64{3, 0}, source))
    error(Unit, over, 34)
    unmapped: Bool <- Qt.QOpenGLBuffer.unmap(buffer)
    require(unmapped, "Explicit GL unmap failed")
    # A new map may reuse the native address. The old view still must expire.
    Qt.MemoryView.with(Unit, Qt.QOpenGLBuffer.map(buffer, Qt.QOpenGLBuffer.Access.ReadOnly()), current => do Qt.Action<Unit>:
      stale: Result<&1, &1, U32 & String, Qt.UInt64> <- Qt.Action.attempt(Qt.UInt64, Qt.MemoryView.size(view))
      error(Qt.UInt64, stale, 116)
      read_only(current, source))

def write_only(+view: Qt.MemoryView, source: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    denied: Result<&1, &1, U32 & String, Qt.QByteArray> <- Qt.Action.attempt(Qt.QByteArray, Qt.MemoryView.read(view, Qt.UInt64{0, 0}, Qt.UInt64{1, 0}))
    error(Qt.QByteArray, denied, 1)
    Qt.MemoryView.write(view, Qt.UInt64{0, 0}, source)

def mapping(+buffer: Qt.QOpenGLBuffer, +source: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    bad: Result<&1, &1, U32 & String, Qt.MemoryView> <- Qt.Action.attempt(Qt.MemoryView, Qt.QOpenGLBuffer.mapRange(buffer, Qt.Int32{3}, Qt.Int32{2}, Qt.Flags_QOpenGLBuffer__RangeAccessFlag{3}))
    error(Qt.MemoryView, bad, 34)
    Qt.MemoryView.with(Unit, Qt.QOpenGLBuffer.map(buffer, Qt.QOpenGLBuffer.Access.ReadWrite()), view => mapped(buffer, view, source))
    # Previous scope unmapped automatically, so a new map succeeds.
    Qt.MemoryView.with(Unit, Qt.QOpenGLBuffer.mapRange(buffer, Qt.Int32{1}, Qt.Int32{2}, Qt.Flags_QOpenGLBuffer__RangeAccessFlag{18}), view => write_only(view, source))
    Qt.MemoryView.with(Unit, Qt.QOpenGLBuffer.map(buffer, Qt.QOpenGLBuffer.Access.ReadOnly()), view => read_only(view, source))

def buffer(+value: Qt.QOpenGLBuffer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    created: Bool <- Qt.QOpenGLBuffer.create(value)
    require(created, "OpenGL buffer creation failed")
    bound: Bool <- Qt.QOpenGLBuffer.bind(value)
    require(bound, "OpenGL buffer binding failed")
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes(0 <> 0 <> 0 <> 0 <> Nil{}), source => Qt.QOpenGLBuffer.allocate__QByteArray_Int32(value, source, Qt.Int32{4}))
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes(9 <> 8 <> Nil{}), source => mapping(value, source))

def context(+value: Qt.QOpenGLContext, surface: Qt.QSurface) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    created: Bool <- Qt.QOpenGLContext.create(value)
    require(created, "OpenGL context creation failed")
    current: Bool <- Qt.QOpenGLContext.makeCurrent(value, surface)
    require(current, "OpenGL context could not become current")
    Qt.QOpenGLBuffer.with(Unit, Qt.QOpenGLBuffer.new(), native => buffer(native))
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
    require(U32.is_eq(count, 0) && U32.is_eq(pins, 0), "OpenGL mappings leaked resources")
    Qt.Action.lift(Unit, IO.print("QT612_GL_MAPPINGS_OK range=1 reads=1 writes=1 bounds=1 permissions=1 explicit_unmap=1 scope_unmap=1 stale_after_remap=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
