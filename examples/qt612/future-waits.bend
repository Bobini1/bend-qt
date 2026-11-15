import Base
import ../../packages/qt612/qt.bend as Qt

# The Fixture producer is only in the maintainer package. Wait operations are
# ordinary generated public bindings; another thread supplies delayed data.
def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def finished(mode: U32, result: Result<&1, &1, U32 & String, Unit>) -> Qt.Action(Unit):
  match result:
    case Done{value}: require(U32.is_ne(mode, 2), "Stored future exception was lost")
    case Fail{(code, message)}:
      require(U32.is_eq(mode, 2) && U32.is_eq(code, 14), "Wrong future error: " ++ message)

def equal(left: Bool, right: Bool) -> Bool:
  match left right:
    case True{} True{}: True{}
    case False{} False{}: True{}
    case _ _: False{}

def waiting(+mode: U32, expected: Bool, +future: Qt.QFutureInterfaceBase) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    value: Bool <- Qt.QFutureInterfaceBase.waitForNextResult(future)
    require(equal(value, expected), "Unexpected next-result decision for mode " ++ U32.show(mode))
    result: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QFutureInterfaceBase.waitForFinished(future))
    finished(mode, result)
    native: Bool <- Qt.Fixture.nativeNext(future)
    repeated: Bool <- Qt.QFutureInterfaceBase.waitForNextResult(future)
    require(equal(native, repeated), "Next-result policy differs from Qt after completion")

def check(+mode: U32, expected: Bool) -> Qt.Action(Unit):
  Qt.QFutureInterfaceBase.with(Unit, Qt.Fixture.future(mode), future => waiting(mode, expected, future))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    check(0, True{})
    check(1, True{})
    check(2, False{})
    check(3, False{})
    check(4, True{})
    check(5, False{})
    objects: U32 <- Qt.Runtime.liveObjects()
    pins: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(pins, 0), "Future waits leaked native resources")
    Qt.Action.lift(Unit, IO.print("QT612_FUTURE_WAITS_OK sparse_result=1 delayed=1 exceptions=1 empty=1 cancellation_precedence=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
