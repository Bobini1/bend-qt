import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def verify(values: List<&2, Qt.F64>) -> Qt.Action(Unit):
  match values:
    case Con{token, Con{value, Nil{}}}:
      do Qt.Action<Unit>:
        text: String <- Qt.F64.toString(value)
        require(String.eq(text, "42"), "GL feedback did not retain the supplied token")
    case _: Qt.Action.fail(Unit, 1, "GL feedback returned an unexpected value count")

def feedback(+functions: Qt.QOpenGLFunctions_1_0, buffer: Qt.GLFeedbackBuffer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    previous: Qt.Int32 <- Qt.QOpenGLFunctions_1_0.glRenderMode(functions, 7169)
    token: Qt.F64 <- Qt.F64.fromString("42")
    Qt.QOpenGLFunctions_1_0.glPassThrough(functions, token)
    count: Qt.Int32 <- Qt.QOpenGLFunctions_1_0.glRenderMode(functions, 7168)
    require(U32.is_eq(Qt.Int32.word(count), 2), "GL feedback did not produce two values")
    values: List<&2, Qt.F64> <- Qt.GLFeedbackBuffer.read(buffer, 2)
    verify(values)

def functions(+value: Qt.QOpenGLFunctions_1_0) -> Qt.Action(Unit):
  Qt.GLFeedbackBuffer.with(Unit, Qt.QOpenGLFunctions_1_0.glFeedbackBuffer(value, Qt.Int32{16}, 1536), buffer => feedback(value, buffer))

def context(+value: Qt.QOpenGLContext, surface: Qt.QSurface) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    created: Bool <- Qt.QOpenGLContext.create(value)
    require(created, "GL context creation failed")
    current: Bool <- Qt.QOpenGLContext.makeCurrent(value, surface)
    require(current, "GL context could not become current")
    Qt.QOpenGLFunctions_1_0.with(Unit, Qt.QOpenGLFunctions_1_0.new(), value => functions(value))
    Qt.QOpenGLContext.doneCurrent(value)

def surface(+value: Qt.QOffscreenSurface) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QOffscreenSurface.create(value)
    Qt.QOpenGLContext.with(Unit, Qt.QOpenGLContext.new(), native => context(native, Qt.QOffscreenSurface.as_QSurface(value)))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QOffscreenSurface.with(Unit, Qt.QOffscreenSurface.new(), value => surface(value))
    count: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(count, 0), "GL feedback scopes leaked resources")
    Qt.Action.lift(Unit, IO.print("QT612_GL_RETAINED_OK context_storage=1 feedback=1 copied_output=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
