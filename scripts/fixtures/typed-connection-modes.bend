import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def clicked(self: Qt.QObject, checked: Bool) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +object: Qt.QObject = self
    previous: String <- Qt.QObject.objectName(object)
    Qt.QObject.setObjectName(object, previous ++ "clicked;")

def expected(result: Result<&1, &1, U32 & String, Qt.Connection>, code: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(actual, message)}: require(U32.is_eq(actual, code), message)
    case Done{connection}: Qt.Action.fail(Unit, 1, "Expected connection type rejection")

def objects() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +button: Qt.QPushButton <- Qt.QPushButton.new()
    +probe: Qt.QObject <- Qt.QObject.new()
    +connection: Qt.Connection <- Qt.QPushButton.connect_clickedWith(~Qt.QObject, ~clicked, button, Qt.Qt.ConnectionType.QueuedConnection(), probe)
    Qt.QPushButton.click(button)
    Qt.QPushButton.click(button)
    before: String <- Qt.QObject.objectName(probe)
    require(String.eq(before, ""), "Typed queued handler ran synchronously")
    Qt.QCoreApplication.processEvents()
    after: String <- Qt.QObject.objectName(probe)
    require(String.eq(after, "clicked;clicked;"), "Typed queued handler lost emissions")
    Qt.Connection.disconnect(connection)
    Qt.QObject.setObjectName(probe, "")
    +single: Qt.Connection <- Qt.QPushButton.connect_clickedWith(~Qt.QObject, ~clicked, button,
      Qt.Qt.ConnectionType{U32.or(Qt.Qt.ConnectionType.word(Qt.Qt.ConnectionType.QueuedConnection()), Qt.Qt.ConnectionType.word(Qt.Qt.ConnectionType.SingleShotConnection()))}, probe)
    Qt.QPushButton.click(button)
    Qt.QPushButton.click(button)
    Qt.QCoreApplication.processEvents()
    once: String <- Qt.QObject.objectName(probe)
    require(String.eq(once, "clicked;"), "Typed single-shot handler ran more than once")
    count: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(count, 0), "Typed single-shot retained its handler")
    refused: Result<&1, &1, U32 & String, Qt.Connection> <- Qt.Action.attempt(Qt.Connection,
      Qt.QPushButton.connect_clickedWith(~Qt.QObject, ~clicked, button, Qt.Qt.ConnectionType.UniqueConnection(), probe))
    expected(refused, 22)
    refused: Result<&1, &1, U32 & String, Qt.Connection> <- Qt.Action.attempt(Qt.Connection,
      Qt.QPushButton.connect_clickedWith(~Qt.QObject, ~clicked, button, Qt.Qt.ConnectionType{4}, probe))
    expected(refused, 22)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, objects())
    live: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(live, 0) && U32.is_eq(connections, 0), "Typed connection modes leaked")
    Qt.Action.lift(Unit, IO.print("QT612_TYPED_CONNECTION_MODES_OK queued=1 singleshot=1 validation=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
