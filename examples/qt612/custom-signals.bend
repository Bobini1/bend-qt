import Base
import ../../packages/qt612/qt.bend as Qt

# The declaration determines both the handler and emission argument types.
def progressChanged() -> Qt.Signal:
  Qt.Signal.define("progressChanged", [Qt.int32(), Qt.string()])

def buttonReady() -> Qt.Signal:
  Qt.Signal.define("buttonReady", [Qt.QPushButton.arg()])

def ready(state: Unit, button: Qt.QPushButton) -> Qt.Action(Unit):
  Qt.QPushButton.setText(button, "Ready")

def received(probe: Qt.QObject, percent: Qt.Int32, title: String) -> Qt.Action(Unit):
  Qt.QObject.setObjectName(probe, title)

def checked(received: Bool) -> Qt.Action(Unit):
  match received:
    case True{}: Qt.Action.lift(Unit, IO.print("QT612_CUSTOM_SIGNALS_OK typed=1 emitted=1 synchronous=1 concrete_object=1"))
    case False{}: Qt.Action.fail(Unit, 1, "The custom signal handler did not run")

def emit_once(+object: Qt.QObject, probe: Qt.QObject, +button: Qt.QPushButton) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Signal.emit(~progressChanged(), object, Qt.Int32{42}, "Loading")
    Qt.Signal.emit(~buttonReady(), object, button)
    title: String <- Qt.QObject.objectName(probe)
    text: String <- Qt.QPushButton.text(button)
    checked(String.eq(title, "Loading") && String.eq(text, "Ready"))

def connected(+object: Qt.QObject, +probe: Qt.QObject, button: Qt.QPushButton) -> Qt.Action(Unit):
  Qt.Connection.with(Unit,
    Qt.Signal.connect(~progressChanged(), ~Qt.QObject, ~received, object, probe),
    connection => Qt.Connection.with(Unit,
      Qt.Signal.connect(~buttonReady(), ~Unit, ~ready, object, Unit{}),
      button_connection => emit_once(object, probe, button)))

def checks() -> Qt.Action(Unit):
  Qt.QObject.with(Unit, Qt.QObject.new(), probe =>
    Qt.QPushButton.with(Unit, Qt.QPushButton.new(), button =>
      Qt.QObject.with(Unit, Qt.QObject.newWithSignals("Task", [progressChanged(), buttonReady()]),
        object => connected(object, probe, button))))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
