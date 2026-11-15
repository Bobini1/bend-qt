import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expected(-A: Type, result: Result<&1, &1, U32 & String, A>, code: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(actual, message)}: require(U32.is_eq(actual, code), message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected cursor guard failure")

def shape_body(cursor: Qt.QCursor) -> Qt.Action(U32):
  do Qt.Action<U32>:
    shape: Qt.Qt.CursorShape <- Qt.QCursor.shape(cursor)
    return Qt.Qt.CursorShape.word(shape)

def shape() -> Qt.Action(U32):
  Qt.QCursor.with(U32, Qt.QGuiApplication.overrideCursor(), cursor => shape_body(cursor))

def empty() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    value: Qt.QCursor <- Qt.QGuiApplication.overrideCursor()
    require(U32.is_eq(Qt.QCursor.word(value), 0), "An override cursor was left on the native stack")

def nested(+cursor: Qt.QCursor) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +guard: Qt.QOverrideCursorGuard <- Qt.QOverrideCursorGuard.new(cursor)
    current: U32 <- shape()
    require(U32.is_eq(current, Qt.Qt.CursorShape.word(Qt.Qt.CursorShape.BusyCursor())), "The inner cursor did not reach Qt")
    Qt.QOverrideCursorGuard.restoreOverrideCursor(guard)
    current: U32 <- shape()
    require(U32.is_eq(current, Qt.Qt.CursorShape.word(Qt.Qt.CursorShape.WaitCursor())), "Restoring an inner guard lost the outer cursor")
    Qt.QOverrideCursorGuard.restore(guard)
    current: U32 <- shape()
    require(U32.is_eq(current, Qt.Qt.CursorShape.word(Qt.Qt.CursorShape.WaitCursor())), "An idempotent restore popped twice")
    active: Bool <- Qt.QOverrideCursorGuard.isActive(guard)
    require(Bool.not(active), "A restored cursor guard stayed active")

def refused(guard: Qt.QOverrideCursorGuard) -> Qt.Action(Unit):
  Qt.Action.fail(Unit, 85, "cursor body failed")

def cases() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    empty()
    +wait: Qt.QCursor <- Qt.QCursor.new__Qt_CursorShape(Qt.Qt.CursorShape.WaitCursor())
    +busy: Qt.QCursor <- Qt.QCursor.new__Qt_CursorShape(Qt.Qt.CursorShape.BusyCursor())
    +outer: Qt.QOverrideCursorGuard <- Qt.QOverrideCursorGuard.new(wait)
    Qt.scoped(Unit, nested(busy))
    active: Bool <- Qt.QOverrideCursorGuard.isActive(outer)
    require(active, "An inner scope restored the outer guard")
    failed: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit,
      Qt.QOverrideCursorGuard.with(Unit, Qt.QOverrideCursorGuard.new(busy), guard => refused(guard)))
    expected(Unit, failed, 85)
    current: U32 <- shape()
    require(U32.is_eq(current, Qt.Qt.CursorShape.word(Qt.Qt.CursorShape.WaitCursor())), "A failing body left its cursor on the stack")
    Qt.QGuiApplication.changeOverrideCursor(busy)
    current: U32 <- shape()
    require(U32.is_eq(current, Qt.Qt.CursorShape.word(Qt.Qt.CursorShape.BusyCursor())), "Changing an active guard's native cursor failed")
    Qt.QOverrideCursorGuard.destroy(outer)
    stale: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.QOverrideCursorGuard.isActive(outer))
    expected(Bool, stale, 116)
    empty()

def escaped(+cursor: Qt.QCursor) -> Qt.Action(Qt.QOverrideCursorGuard):
  do Qt.Action<Qt.QOverrideCursorGuard>:
    guard: Qt.QOverrideCursorGuard <- Qt.QOverrideCursorGuard.new(cursor)
    Qt.QOverrideCursorGuard.keep(guard)

def kept() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +cursor: Qt.QCursor <- Qt.QCursor.new__Qt_CursorShape(Qt.Qt.CursorShape.WaitCursor())
    +guard: Qt.QOverrideCursorGuard <- Qt.scoped(Qt.QOverrideCursorGuard, escaped(cursor))
    current: U32 <- shape()
    require(U32.is_eq(current, Qt.Qt.CursorShape.word(Qt.Qt.CursorShape.WaitCursor())), "Keeping a cursor guard restored it too early")
    Qt.QOverrideCursorGuard.release(guard)
    empty()

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, cases())
    Qt.scoped(Unit, kept())
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Cursor guards leaked native resources")
    Qt.Action.lift(Unit, IO.print("QT612_CURSOR_GUARDS_OK native_stack=1 nested=1 idempotent=1 failure=1 changes=1 keep=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
