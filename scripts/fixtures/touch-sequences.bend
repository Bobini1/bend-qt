import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expected(-A: Type, result: Result<&1, &1, U32 & String, A>, code: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(+actual, message)}: require(U32.is_eq(actual, code), message)
    case Done{value}: Qt.Action.fail(Unit, 1, "A guarded touch operation succeeded")

def named(state: Qt.QObject, event: Qt.QEvent, name: String) -> Qt.Action(Bool):
  do Qt.Action<Bool>:
    Qt.QObject.setObjectName(state, name)
    Qt.QEvent.accept(event)
    return True{}

def ended(state: Qt.QObject, event: Qt.QEvent, end: Bool) -> Qt.Action(Bool):
  match end:
    case True{}: named(state, event, "released")
    case False{}: Qt.Action.pure(Bool, False{})

def moved(state: Qt.QObject, +event: Qt.QEvent, +kind: Qt.QEvent.Type, update: Bool) -> Qt.Action(Bool):
  match update:
    case True{}: named(state, event, "moved")
    case False{}: ended(state, event, U32.is_eq(Qt.QEvent.Type.word(kind), Qt.QEvent.Type.word(Qt.QEvent.Type.TouchEnd())))

def began(state: Qt.QObject, +event: Qt.QEvent, +kind: Qt.QEvent.Type, begin: Bool) -> Qt.Action(Bool):
  match begin:
    case True{}: named(state, event, "pressed")
    case False{}: moved(state, event, kind, U32.is_eq(Qt.QEvent.Type.word(kind), Qt.QEvent.Type.word(Qt.QEvent.Type.TouchUpdate())))

def touch(state: Qt.QObject, event: Qt.QEvent) -> Qt.Action(Bool):
  do Qt.Action<Bool>:
    +event: Qt.QEvent = event
    +kind: Qt.QEvent.Type <- Qt.QEvent.type(event)
    began(state, event, kind, U32.is_eq(Qt.QEvent.Type.word(kind), Qt.QEvent.Type.word(Qt.QEvent.Type.TouchBegin())))

def check_name(state: Qt.QObject, expected: String) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +expected: String = expected
    +name: String <- Qt.QObject.objectName(state)
    require(String.eq(name, expected), "Native touch dispatch did not produce " ++ expected ++ ": " ++ name)

def fail_release(+window: Qt.QWindow, device: Qt.QPointingDevice, point: Qt.QPoint) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +sequence: Qt.QTest.QTouchEventSequence <- Qt.QTest.touchEvent(window, device)
    Qt.QTest.QTouchEventSequence.releaseInWindow(sequence, Qt.Int32{0}, point, window)
    Qt.Action.fail(Unit, 81, "Expected touch body failure")

def objects() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +state: Qt.QObject <- Qt.QObject.new()
    +window: Qt.QWindow <- Qt.QWindow.newOverride()
    Qt.QObject.Virtual.event.handle(~Qt.QObject, ~touch, Qt.QWindow.as_QObject(window), state)
    Qt.QWindow.resize__Int32_Int32(window, Qt.Int32{100}, Qt.Int32{100})
    Qt.QWindow.show(window)
    Qt.QCoreApplication.processEvents()
    +device: Qt.QPointingDevice <- Qt.QTest.createTouchDevice()
    +point: Qt.QPoint <- Qt.QPoint.new__Int32_Int32(Qt.Int32{20}, Qt.Int32{30})
    +sequence: Qt.QTest.QTouchEventSequence <- Qt.QTest.touchEvent(window, device)
    held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QWindow.destroy(window))
    expected(Unit, held, 16)
    Qt.QTest.QTouchEventSequence.press(sequence, Qt.Int32{0}, point)
    committed: Bool <- Qt.QTest.QTouchEventSequence.commit(sequence)
    require(committed, "Qt refused a native touch press")
    check_name(state, "pressed")
    +next: Qt.QPoint <- Qt.QPoint.new__Int32_Int32(Qt.Int32{22}, Qt.Int32{33})
    Qt.QTest.QTouchEventSequence.moveInWindow(sequence, Qt.Int32{0}, next, window)
    committed: Bool <- Qt.QTest.QTouchEventSequence.commitWith(sequence, False{})
    require(committed, "Qt refused a native touch move")
    check_name(state, "moved")
    Qt.QTest.QTouchEventSequence.stationary(sequence, Qt.Int32{0})
    committed: Bool <- Qt.QTest.QTouchEventSequence.commit(sequence)
    Qt.QTest.QTouchEventSequence.release(sequence, Qt.Int32{0}, next)
    Qt.QTest.QTouchEventSequence.destroy(sequence)
    check_name(state, "released")
    stale: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.QTest.QTouchEventSequence.commit(sequence))
    expected(Bool, stale, 116)
    +sequence: Qt.QTest.QTouchEventSequence <- Qt.QTest.touchEventWithAutoCommit(window, device, False{})
    Qt.QTest.QTouchEventSequence.press(sequence, Qt.Int32{0}, point)
    Qt.QTest.QTouchEventSequence.destroy(sequence)
    check_name(state, "released")
    +sequence: Qt.QTest.QTouchEventSequence <- Qt.QTest.touchEvent(window, device)
    Qt.QTest.QTouchEventSequence.press(sequence, Qt.Int32{0}, point)
    Qt.QTest.QTouchEventSequence.destroy(sequence)
    check_name(state, "pressed")
    failure: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.scoped(Unit, fail_release(window, device, point)))
    expected(Unit, failure, 81)
    check_name(state, "released")
    +widget: Qt.QWidget <- Qt.QWidget.newOverride()
    Qt.QObject.Virtual.event.handle(~Qt.QObject, ~touch, Qt.QWidget.as_QObject(widget), state)
    Qt.QWidget.setAttribute__Qt_WidgetAttribute_Bool(widget, Qt.Qt.WidgetAttribute.WA_AcceptTouchEvents(), True{})
    Qt.QWidget.resize__Int32_Int32(widget, Qt.Int32{100}, Qt.Int32{100})
    Qt.QWidget.show(widget)
    Qt.QCoreApplication.processEvents()
    +sequence: Qt.QTest.QTouchEventSequence <- Qt.QTest.touchWidget(widget, device)
    Qt.QTest.QTouchEventSequence.pressInWidget(sequence, Qt.Int32{1}, point, widget)
    committed: Bool <- Qt.QTest.QTouchEventSequence.commit(sequence)
    require(committed, "Qt refused a native widget touch press")
    check_name(state, "pressed")
    Qt.QTest.QTouchEventSequence.releaseInWidget(sequence, Qt.Int32{1}, point, widget)
    Qt.QTest.QTouchEventSequence.destroy(sequence)
    check_name(state, "released")
    borrowed: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QPointingDevice.destroy(device))
    expected(Unit, borrowed, 1)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, objects())
    count: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(count, 0), "Touch sequence, device view or target leaked")
    Qt.Action.lift(Unit, IO.print("QT612_TOUCH_SEQUENCES_OK window=1 widget=1 autocommit=1 failure_cleanup=1 guarded=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
