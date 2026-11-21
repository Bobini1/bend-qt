import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}:
      Qt.Action.pure(Unit, Unit{})
    case False{}:
      Qt.Action.fail(Unit, 1, message)

# A slot. Qt runs it inside QPushButton.click, before click returns.
def clicked(button: Qt.QPushButton, checked: Bool) -> Qt.Action(Unit):
  Qt.QPushButton.setText(button, "clicked")

def click_demo(+button: Qt.QPushButton, connection: Qt.Connection) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QPushButton.click(button)
    text: String <- Qt.QPushButton.text(button)
    require(String.eq(text, "clicked"), "The clicked handler did not run during click")

def button_demo(+button: Qt.QPushButton) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QPushButton.setText(button, "Bend → Qt 6.12: Zażółć 🎵")
    text: String <- Qt.QPushButton.text(button)
    Qt.Action.lift(Unit, IO.print(text))
    Qt.Connection.with(Unit, Qt.Signal.connect(~Qt.QPushButton.clicked(), ~Qt.QPushButton, ~clicked, button, button),
      connection => click_demo(button, connection))

# The timer fires inside the application's event loop and ends it.
def timeout(code: U32) -> Qt.Action(Unit):
  Qt.QCoreApplication.exit__Int32(Qt.Int32{code})

def run_loop(connection: Qt.Connection) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    code: Qt.Int32 <- Qt.QCoreApplication.exec()
    require(U32.is_eq(Qt.Int32.word(code), 7), "The event loop did not end with the handler's code")

def timer_demo(+timer: Qt.QTimer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QTimer.setSingleShot(timer, True{})
    Qt.QTimer.start__Int32(timer, Qt.Int32{10})
    Qt.Connection.with(Unit, Qt.Signal.connect(~Qt.QTimer.timeout(), ~U32, ~timeout, timer, 7), run_loop)

def point_demo(point: Qt.QPoint) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    x: Qt.Int32 <- Qt.QPoint.x(point)
    require(U32.is_eq(Qt.Int32.word(x), (0 - 7 : U32)), "Signed integer round trip failed")

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QPushButton.with(Unit, Qt.QPushButton.new(), button => button_demo(button))
    Qt.QTimer.with(Unit, Qt.QTimer.new(), timer => timer_demo(timer))
    Qt.QPoint.with(Unit, Qt.QPoint.new__Int32_Int32(Qt.Int32.neg(7), Qt.Int32{12}), point_demo)
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Qt resources were not released")
    Qt.Action.lift(Unit, IO.print("QT612_OK unicode=1 click=1 timer=1 signed_value=1 objects=0 connections=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
