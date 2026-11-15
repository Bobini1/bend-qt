import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expect_error(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}:
      require(U32.is_eq(code, expected), "Unexpected error: " ++ message)
    case Done{value}:
      Qt.Action.fail(Unit, 1, "Expected an Action failure")

def empty() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Scope leaked native resources")

# The Qt object name records actual effect order, including cleanup on failure.
def record(+trace: Qt.QTimer, text: String) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    previous: String <- Qt.QTimer.objectName(trace)
    Qt.QTimer.setObjectName(trace, previous ++ text)

def acquire_ok(trace: Qt.QTimer) -> Qt.Action(U32):
  do Qt.Action<U32>:
    record(trace, "A")
    return 1

def acquire_bad(trace: Qt.QTimer) -> Qt.Action(U32):
  do Qt.Action<U32>:
    record(trace, "A")
    Qt.Action.fail(U32, 41, "acquire")

def body_ok(trace: Qt.QTimer, resource: U32) -> Qt.Action(U32):
  do Qt.Action<U32>:
    record(trace, "B")
    return 42

def body_bad(+trace: Qt.QTimer, resource: U32) -> Qt.Action(U32):
  do Qt.Action<U32>:
    record(trace, "B")
    Qt.Action.fail(Unit, 42, "body")
    record(trace, "UNREACHABLE")
    return 0

def release_ok(trace: Qt.QTimer, resource: U32) -> Qt.Action(Unit):
  record(trace, "C")

def release_bad(trace: Qt.QTimer, resource: U32) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    record(trace, "C")
    Qt.Action.fail(Unit, 43, "cleanup")

def expect_result(result: Result<&1, &1, U32 & String, U32>, expected: U32, message: String) -> Qt.Action(Unit):
  match result:
    case Done{value}:
      require(U32.is_eq(expected, 0) && U32.is_eq(value, 42), "Successful result changed during cleanup")
    case Fail{(code, text)}:
      require(U32.is_eq(code, expected) && String.eq(text, message), "Error precedence or message changed")

def scenario(+trace: Qt.QTimer, action: Qt.Action(U32), code: U32, message: String, expected: String) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QTimer.setObjectName(trace, "")
    result: Result<&1, &1, U32 & String, U32> <- Qt.Action.attempt(U32, action)
    expect_result(result, code, message)
    text: String <- Qt.QTimer.objectName(trace)
    require(String.eq(text, expected), "Incorrect acquisition/body/cleanup order")

def inner_cleanup(trace: Qt.QTimer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    record(trace, "I")
    Qt.Action.fail(Unit, 43, "cleanup")

def composition_cases(+trace: Qt.QTimer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    scenario(trace, Qt.Action.using(U32, U32, acquire_ok(trace), r => release_ok(trace, r), r => body_ok(trace, r)), 0, "", "ABC")
    scenario(trace, Qt.Action.using(U32, U32, acquire_bad(trace), r => release_ok(trace, r), r => body_ok(trace, r)), 41, "acquire", "A")
    scenario(trace, Qt.Action.using(U32, U32, acquire_ok(trace), r => release_ok(trace, r), r => body_bad(trace, r)), 42, "body", "ABC")
    scenario(trace, Qt.Action.using(U32, U32, acquire_ok(trace), r => release_bad(trace, r), r => body_ok(trace, r)), 43, "cleanup", "ABC")
    scenario(trace, Qt.Action.using(U32, U32, acquire_ok(trace), r => release_bad(trace, r), r => body_bad(trace, r)), 42, "body", "ABC")
    scenario(trace, Qt.Action.finally(U32, Qt.Action.finally(U32, Qt.Action.fail(U32, 42, "body"), inner_cleanup(trace)), record(trace, "O")), 42, "body", "IO")

def fail_point(point: Qt.QPoint) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    x: Qt.Int32 <- Qt.QPoint.x(point)
    Qt.Action.fail(Unit, 61, "inside nested Qt scopes")
    unreachable: Qt.QObject <- Qt.QObject.new()
    return Unit{}

def ignore_click(state: U32, checked: Bool) -> Qt.Action(Unit):
  Qt.Action.pure(Unit, Unit{})

def fail_clicked(+button: Qt.QPushButton, connection: Qt.Connection) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QPushButton.click(button)
    Qt.QPoint.with(Unit, Qt.QPoint.new(), fail_point)

def fail_button(+button: Qt.QPushButton) -> Qt.Action(Unit):
  Qt.Connection.with(Unit, Qt.QPushButton.connect_clicked(~U32, ~ignore_click, button, 0),
    connection => fail_clicked(button, connection))

def wrong_type(button: Qt.QPushButton) -> Qt.Action(Unit):
  Qt.QPoint.with(Unit, Qt.Action.pure(Qt.QPoint, Qt.QPoint{Qt.QPushButton.word(button)}), point => Qt.Action.pure(Unit, Unit{}))

# A handler's failure has no caller of its own: the Qt call during which Qt
# ran it fails with it.
def refuse_click(code: U32, checked: Bool) -> Qt.Action(Unit):
  Qt.Action.fail(Unit, code, "handler")

def refused_click(+button: Qt.QPushButton, connection: Qt.Connection) -> Qt.Action(Unit):
  Qt.QPushButton.click(button)

def refusing_button(+button: Qt.QPushButton) -> Qt.Action(Unit):
  Qt.Connection.with(Unit, Qt.QPushButton.connect_clicked(~U32, ~refuse_click, button, 44),
    connection => refused_click(button, connection))

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QTimer.with(Unit, Qt.QTimer.new(), trace => composition_cases(trace))
    empty()
    failed: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QPushButton.with(Unit, Qt.QPushButton.new(), button => fail_button(button)))
    expect_error(Unit, failed, 61)
    empty()
    mistyped: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QPushButton.with(Unit, Qt.QPushButton.new(), wrong_type))
    expect_error(Unit, mistyped, 22)
    empty()
    refused: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QPushButton.with(Unit, Qt.QPushButton.new(), button => refusing_button(button)))
    expect_error(Unit, refused, 44)
    empty()
    Qt.Action.lift(Unit, IO.print("QT612_ACTIONS_OK acquisition=1 short_circuit=1 cleanup_success=1 cleanup_failure=1 precedence=1 nested=1 handler_failure=1 objects=0 connections=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
