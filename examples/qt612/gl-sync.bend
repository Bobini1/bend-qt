import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def signaled(+status: U32) -> Bool:
  U32.is_eq(status, 37146) || U32.is_eq(status, 37148)

def fence(+functions: Qt.QOpenGLExtraFunctions, +sync: Qt.QOpenGLSync) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    valid: U32 <- Qt.QOpenGLExtraFunctions.glIsSync(functions, sync)
    require(U32.is_eq(valid, 1), "Created GL fence was not valid")
    status: U32 <- Qt.QOpenGLExtraFunctions.glClientWaitSync(functions, sync, 1, Qt.UInt64{1000000000, 0})
    require(signaled(status), "GL fence did not complete within its timeout")

def functions(+value: Qt.QOpenGLExtraFunctions) -> Qt.Action(Unit):
  Qt.QOpenGLSync.with(Unit, Qt.QOpenGLExtraFunctions.glFenceSync(value, 37143, 0), sync => fence(value, sync))

def context(+value: Qt.QOpenGLContext, surface: Qt.QSurface) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    created: Bool <- Qt.QOpenGLContext.create(value)
    require(created, "OpenGL context creation failed")
    current: Bool <- Qt.QOpenGLContext.makeCurrent(value, surface)
    require(current, "OpenGL context could not become current")
    Qt.QOpenGLExtraFunctions.with(Unit, Qt.QOpenGLExtraFunctions.new__QOpenGLContext(value), fn => functions(fn))
    Qt.QOpenGLContext.doneCurrent(value)

def surface(+value: Qt.QOffscreenSurface) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QOffscreenSurface.create(value)
    Qt.QOpenGLContext.with(Unit, Qt.QOpenGLContext.new(), ctx => context(ctx, Qt.QOffscreenSurface.as_QSurface(value)))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QOffscreenSurface.with(Unit, Qt.QOffscreenSurface.new(), value => surface(value))
    count: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(count, 0), "GL fence scopes leaked native handles")
    Qt.Action.lift(Unit, IO.print("QT612_GL_SYNC_OK native_fence=1 typed_handle=1 wait=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
