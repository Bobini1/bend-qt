import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def error(~A: Type, expected: U32, result: Result<&1, &1, U32 & String, A>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Unexpected OpenGL error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Invalid OpenGL operation succeeded")

def current(context: Qt.QOpenGLContext, surface: Qt.QSurface) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    ok: Bool <- Qt.QOpenGLContext.makeCurrent(context, surface)
    require(ok, "Could not make the OpenGL context current")

def buffer(+value: Qt.QOpenGLBuffer, +first: Qt.QOpenGLContext, second: Qt.QOpenGLContext, +surface: Qt.QSurface) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    created: Bool <- Qt.QOpenGLBuffer.create(value)
    require(created, "OpenGL buffer creation failed")
    bound: Bool <- Qt.QOpenGLBuffer.bind(value)
    require(bound, "OpenGL buffer binding failed")
    Qt.QOpenGLContext.doneCurrent(first)
    destroyed: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QOpenGLBuffer.destroy(value))
    error(Unit, 16, destroyed)
    unavailable: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.QOpenGLBuffer.bind(value))
    error(Bool, 19, unavailable)
    retained: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QOpenGLContext.destroy(first))
    error(Unit, 16, retained)
    current(second, surface)
    wrong: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.QOpenGLBuffer.bind(value))
    error(Bool, 18, wrong)
    current(first, surface)

def contexts(+first: Qt.QOpenGLContext, +second: Qt.QOpenGLContext, +surface: Qt.QSurface) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    created: Bool <- Qt.QOpenGLContext.create(first)
    require(created, "First OpenGL context creation failed")
    created_second: Bool <- Qt.QOpenGLContext.create(second)
    require(created_second, "Second OpenGL context creation failed")
    current(first, surface)
    Qt.QOpenGLBuffer.with(Unit, Qt.QOpenGLBuffer.new(), value => buffer(value, first, second, surface))
    Qt.QOpenGLContext.doneCurrent(first)

def local_array(+array: Qt.QOpenGLVertexArrayObject, +first: Qt.QOpenGLContext, second: Qt.QOpenGLContext, +surface: Qt.QSurface) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    created: Bool <- Qt.QOpenGLVertexArrayObject.create(array)
    require(created, "Vertex array creation failed")
    current(second, surface)
    wrong: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QOpenGLVertexArrayObject.bind(array))
    error(Unit, 18, wrong)
    current(first, surface)
    Qt.QOpenGLVertexArrayObject.bind(array)

def shared_buffer(+value: Qt.QOpenGLBuffer, +first: Qt.QOpenGLContext, +second: Qt.QOpenGLContext, +surface: Qt.QSurface) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    created: Bool <- Qt.QOpenGLBuffer.create(value)
    require(created, "Shared buffer creation failed")
    current(second, surface)
    bound: Bool <- Qt.QOpenGLBuffer.bind(value)
    require(bound, "Shared context could not bind shared buffer")
    current(first, surface)
    Qt.QOpenGLVertexArrayObject.with(Unit, Qt.QOpenGLVertexArrayObject.new(), array => local_array(array, first, second, surface))

def sharing(+first: Qt.QOpenGLContext, +second: Qt.QOpenGLContext, +surface: Qt.QSurface) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    created: Bool <- Qt.QOpenGLContext.create(first)
    require(created, "Share-group root creation failed")
    Qt.QOpenGLContext.setShareContext(second, first)
    shared: Bool <- Qt.QOpenGLContext.create(second)
    require(shared, "Sharing context creation failed")
    current(first, surface)
    Qt.QOpenGLBuffer.with(Unit, Qt.QOpenGLBuffer.new(), value => shared_buffer(value, first, second, surface))
    Qt.QOpenGLContext.doneCurrent(first)

def surface(+value: Qt.QOffscreenSurface) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QOffscreenSurface.create(value)
    Qt.QOpenGLContext.with(Unit, Qt.QOpenGLContext.new(), first => Qt.QOpenGLContext.with(Unit, Qt.QOpenGLContext.new(), second => contexts(first, second, Qt.QOffscreenSurface.as_QSurface(value))))
    Qt.QOpenGLContext.with(Unit, Qt.QOpenGLContext.new(), first => Qt.QOpenGLContext.with(Unit, Qt.QOpenGLContext.new(), second => sharing(first, second, Qt.QOffscreenSurface.as_QSurface(value))))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QOffscreenSurface.with(Unit, Qt.QOffscreenSurface.new(), value => surface(value))
    count: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(count, 0), "OpenGL scopes leaked handles")
    Qt.Action.lift(Unit, IO.print("QT612_OPENGL_OK native_context=1 wrong_context_rejected=1 context_retained=1 shared_buffer=1 context_local_vao=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
