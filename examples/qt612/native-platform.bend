import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def stale(result: Result<&1, &1, U32 & String, Qt.UInt64>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 116), "Unexpected native platform error: " ++ message)
    case Done{address}: Qt.Action.fail(Unit, 1, "Destroyed platform surface exposed an address")

def capability(+window: Qt.QWindow, +value: Qt.NativePlatform_QPlatformSurface) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    valid: Bool <- Qt.NativePlatform_QPlatformSurface.isValid(value)
    require(valid, "Created window has no current native surface")
    Qt.QWindow.native_destroy(window)
    invalid: Bool <- Qt.NativePlatform_QPlatformSurface.isValid(value)
    require(Bool.not(invalid), "Platform capability ignored surface destruction")
    address: Result<&1, &1, U32 & String, Qt.UInt64> <- Qt.Action.attempt(Qt.UInt64, Qt.NativePlatform_QPlatformSurface.unsafeAddress(value))
    stale(address)

def window(+value: Qt.QWindow) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QWindow.create(value)
    Qt.NativePlatform_QPlatformSurface.with(Unit, Qt.QSurface.surfaceHandle(Qt.QWindow.as_QSurface(value)), native => capability(value, native))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QWindow.with(Unit, Qt.QWindow.new(), value => window(value))
    count: U32 <- Qt.Runtime.liveObjects()
    pins: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(count, 0) && U32.is_eq(pins, 0), "Native platform scopes leaked handles")
    Qt.Action.lift(Unit, IO.print("QT612_NATIVE_PLATFORM_OK typed_capability=1 revalidation=1 stale_address_rejected=1 scoped_cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
