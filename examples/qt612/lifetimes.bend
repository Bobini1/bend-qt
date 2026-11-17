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
      Qt.Action.fail(Unit, 1, "Expected a checked Qt error")

def clicks(count: Nat, +button: Qt.QPushButton) -> Qt.Action(Unit):
  match count:
    case Zero{}: Qt.Action.pure(Unit, Unit{})
    case Succ{rest}:
      do Qt.Action<Unit>:
        Qt.QPushButton.click(button)
        clicks(rest, button)

# The handler copies the signal's string into the probe's name.
def name_changed(probe: Qt.QObject, name: String) -> Qt.Action(Unit):
  Qt.QObject.setObjectName(probe, name)

def names_case(+child: Qt.QPushButton, +probe: Qt.QObject, +names: Qt.Connection) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QPushButton.setObjectName(child, "Copied 🎵")
    original: String <- Qt.QObject.objectName(probe)
    require(String.eq(original, "Copied 🎵"), "Signal string was not copied")
    Qt.QPushButton.setObjectName(child, "Changed")
    changed: String <- Qt.QObject.objectName(probe)
    require(String.eq(changed, "Changed"), "Second signal string was not delivered")
    # Explicit release stays strict; the enclosing scope accepts it as released.
    Qt.Connection.disconnect(names)
    again: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.Connection.disconnect(names))
    expect_error(Unit, again, 116)

def watch_names(+child: Qt.QPushButton, +probe: Qt.QObject) -> Qt.Action(Unit):
  Qt.Connection.with(Unit, Qt.QPushButton.connect_objectNameChanged(~Qt.QObject, ~name_changed, child, probe),
    names => names_case(child, probe, names))

def child_case(+parent: Qt.QWidget, +child: Qt.QPushButton) -> Qt.Action(Qt.QPushButton):
  do Qt.Action<Qt.QPushButton>:
    alias: Qt.QWidget <- Qt.QPushButton.parentWidget(child)
    require(U32.is_eq(Qt.QWidget.word(alias), Qt.QWidget.word(parent)), "Object identity was lost")
    wrong: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QPoint.destroy(Qt.QPoint{Qt.QPushButton.word(child)}))
    expect_error(Unit, wrong, 22)
    Qt.QObject.with(Unit, Qt.QObject.new(), probe => watch_names(child, probe))
    Qt.QWidget.destroy(parent)
    stale: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QPushButton.text(child))
    expect_error(String, stale, 116)
    # Deliberately retain a stale handle only to test generation checks below.
    return child

def parent_case(+parent: Qt.QWidget) -> Qt.Action(Qt.QPushButton):
  Qt.QPushButton.with(Qt.QPushButton, Qt.QPushButton.new__QWidget(parent), child => child_case(parent, child))

# Each click runs the handler once, before click returns.
def bump(+counter: Qt.QTimer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    count: Qt.Int32 <- Qt.QTimer.interval(counter)
    Qt.QTimer.setInterval__Int32(counter, Qt.Int32{(Qt.Int32.word(count) + 1 : U32)})

def count_click(counter: Qt.QTimer, checked: Bool) -> Qt.Action(Unit):
  bump(counter)

def burst_case(+button: Qt.QPushButton, +counter: Qt.QTimer, connection: Qt.Connection) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    clicks(65n, button)
    count: Qt.Int32 <- Qt.QTimer.interval(counter)
    require(U32.is_eq(Qt.Int32.word(count), 65), "A click did not run its handler exactly once")

def counted(+button: Qt.QPushButton, +counter: Qt.QTimer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QTimer.setInterval__Int32(counter, Qt.Int32{0})
    # A signal of a handle with the wrong class is rejected.
    mismatch: Result<&1, &1, U32 & String, Qt.Connection> <- Qt.Action.attempt(Qt.Connection, Qt.QPushButton.connect_clicked(~Qt.QTimer, ~count_click, Qt.QPushButton{Qt.QTimer.word(counter)}, counter))
    expect_error(Qt.Connection, mismatch, 22)
    Qt.Connection.with(Unit, Qt.QPushButton.connect_clicked(~Qt.QTimer, ~count_click, button, counter),
      connection => burst_case(button, counter, connection))

def replacement_case(child: Qt.QPushButton, +replacement: Qt.QPushButton) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    old: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QPushButton.destroy(child))
    expect_error(Unit, old, 116)
    Qt.QTimer.with(Unit, Qt.QTimer.new(), counter => counted(replacement, counter))

def timeout(code: U32) -> Qt.Action(Unit):
  Qt.QCoreApplication.exit__Int32(Qt.Int32{code})

# The timer fires inside the event loop; destroying it ends its connection.
def ticking(+timer: Qt.QTimer, ticks: Qt.Connection) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QTimer.setSingleShot(timer, True{})
    Qt.QTimer.start__Int32(timer, Qt.Int32{5})
    code: Qt.Int32 <- Qt.QCoreApplication.exec()
    require(U32.is_eq(Qt.Int32.word(code), 3), "The timeout handler did not end the event loop")
    Qt.QTimer.destroy(timer)
    ended: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.Connection.disconnect(ticks))
    expect_error(Unit, ended, 116)
    live: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(live, 0), "Destroying the sender left its connection open")

def timer_case(+timer: Qt.QTimer) -> Qt.Action(Unit):
  Qt.Connection.with(Unit, Qt.QTimer.connect_timeout(~U32, ~timeout, timer, 3), ticks => ticking(timer, ticks))

def date_case(date: Qt.QDate) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    text: String <- Qt.QDate.toString__String(date, "yyyy-MM-dd")
    require(String.eq(text, "2026-11-09"), "Value/string conversion failed")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    child: Qt.QPushButton <- Qt.QWidget.with(Qt.QPushButton, Qt.QWidget.new(), parent => parent_case(parent))
    Qt.QPushButton.with(Unit, Qt.QPushButton.new(), replacement => replacement_case(child, replacement))
    Qt.QTimer.with(Unit, Qt.QTimer.new(), timer => timer_case(timer))
    Qt.QDate.with(Unit, Qt.QDate.new__Int32_Int32_Int32(Qt.Int32{2026}, Qt.Int32{11}, Qt.Int32{9}), date_case)
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Qt resources were not released")
    Qt.Action.lift(Unit, IO.print("QT612_LIFETIMES_OK parent=1 stale=1 generation=1 type=1 signal_copy=1 burst=1 sender_death=1 objects=0 connections=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
