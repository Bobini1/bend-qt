import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expect_error(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Unexpected error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected the handler failure")

def fill(+authenticator: Qt.QAuthenticator) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    realm: String <- Qt.QAuthenticator.realm(authenticator)
    require(String.eq(realm, "Bend native authentication fixture"), "The handler did not receive Qt's authenticator")
    Qt.QAuthenticator.setUser(authenticator, "bend-user")
    Qt.QAuthenticator.setPassword(authenticator, "bend-password")

# The handler fills in Qt's own authenticator, borrowed for the call, as a
# PySide slot does. Qt reads it after the signal returns.
def credentials(state: Unit, reply: Qt.QNetworkReply, authenticator: Qt.QAuthenticator) -> Qt.Action(Unit):
  fill(authenticator)

def refused(code: U32, reply: Qt.QNetworkReply, authenticator: Qt.QAuthenticator) -> Qt.Action(Unit):
  Qt.Action.fail(Unit, code, "Intentional handler failure")

def emit_signal(+manager: Qt.QNetworkAccessManager) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    committed: U32 <- Qt.CallbackProbe.authentication(manager)
    require(U32.is_eq(committed, 1), "The signal returned before Bend filled the credentials")
    threaded: U32 <- Qt.CallbackProbe.authenticationOnThread(manager)
    require(U32.is_eq(threaded, 1), "The other-thread emitter returned before Bend filled the credentials")

# A failed handler fails the Qt call that emitted the signal.
def emit_failing(+manager: Qt.QNetworkAccessManager, connection: Qt.Connection) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    result: Result<&1, &1, U32 & String, U32> <- Qt.Action.attempt(U32, Qt.CallbackProbe.authentication(manager))
    expect_error(U32, result, 44)
    threaded: Result<&1, &1, U32 & String, U32> <- Qt.Action.attempt(U32, Qt.CallbackProbe.authenticationOnThread(manager))
    expect_error(U32, threaded, 44)

def manager_demo(+manager: Qt.QNetworkAccessManager) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Connection.with(Unit, Qt.Signal.connect(~Qt.QNetworkAccessManager.authenticationRequired(), ~Unit, ~credentials, manager, Unit{}), connection => emit_signal(manager))
    Qt.Connection.with(Unit, Qt.Signal.connect(~Qt.QNetworkAccessManager.authenticationRequired(), ~U32, ~refused, manager, 44), connection => emit_failing(manager, connection))

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QNetworkAccessManager.with(Unit, Qt.QNetworkAccessManager.new(), manager => manager_demo(manager))
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "The signal handlers leaked handles")
    Qt.Action.lift(Unit, IO.print("QT612_SYNCHRONOUS_SIGNALS_OK credentials_before_return=1 borrowed_input=1 filled_in_place=1 handler_error=1 other_thread_reply=1 other_thread_error=1 objects=0 connections=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
