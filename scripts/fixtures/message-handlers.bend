import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

type Seen is Data:
  Seen{mode: U32, probe: Qt.QObject}

def optional(value: Maybe<&2, String>, expected: String) -> Bool:
  match value:
    case Some{text}: String.eq(text, expected)
    case None{}: False{}

def check_message(+message: Qt.LogMessage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    require(U32.is_eq(Qt.QtMsgType.word(Qt.LogMessage.arg0(message)), 1), "Wrong native message severity")
    require(String.eq(Qt.LogMessage.arg1(message), "Bend native λ"), "The Unicode message changed")
    require(optional(Qt.LogMessage.arg2(message), "bend.fixture"), "The category changed")
    require(optional(Qt.LogMessage.arg3(message), "bend-native.cpp"), "The file context changed")
    require(U32.is_eq(Qt.Int32.word(Qt.LogMessage.arg4(message)), 27), "The line changed")
    require(optional(Qt.LogMessage.arg5(message), "nativeMessage"), "The function context changed")
    formatted: String <- Qt.MessageHandler.format(message)
    require(Bool.not(String.eq(formatted, "")), "Qt message formatting failed")

# Mode 1 fails after reading the message: Qt then logs it the previous way.
def received(mode: U32, probe: Qt.QObject, message: Qt.LogMessage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    check_message(message)
    Qt.QObject.setObjectName(probe, "delivered")
    require(U32.is_eq(mode, 0), "Intentional logging handler failure")

def logged(state: Seen, message: Qt.LogMessage) -> Qt.Action(Unit):
  match state:
    case Seen{mode, probe}: received(mode, probe, message)

def delivered(+probe: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    name: String <- Qt.QObject.objectName(probe)
    require(String.eq(name, "delivered"), "The handler did not get the message")
    Qt.QObject.setObjectName(probe, "")

# A message logged on another thread goes to the previous handler.
def succeeding(+probe: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.MessageHandler.install(~Seen, ~logged, Seen{0, probe})
    handled: U32 <- Qt.CallbackProbe.emitMessage(False{})
    require(U32.is_eq(handled, 0), "A handled message also reached the previous handler")
    delivered(probe)
    other: U32 <- Qt.CallbackProbe.emitMessage(True{})
    require(U32.is_eq(other, 1), "A message from another thread did not reach the previous handler")
    error: U32 <- Qt.MessageHandler.lastError()
    require(U32.is_eq(error, 0), "A successful handler recorded an error")
    Qt.MessageHandler.restore()
    restored: U32 <- Qt.CallbackProbe.emitMessage(False{})
    require(U32.is_eq(restored, 1), "restore did not give Qt its previous handler back")

# A failed logging handler never fails the Qt call that logged.
def failing(+probe: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.MessageHandler.install(~Seen, ~logged, Seen{1, probe})
    fallback: U32 <- Qt.CallbackProbe.emitMessage(False{})
    require(U32.is_eq(fallback, 1), "A failed handler did not pass the message to the previous handler")
    delivered(probe)
    error: U32 <- Qt.MessageHandler.lastError()
    require(U32.is_eq(error, 1), "The handler failure was not recorded")
    Qt.MessageHandler.restore()

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.CallbackProbe.prepareMessages()
    Qt.QObject.with(Unit, Qt.QObject.new(), probe => succeeding(probe))
    Qt.QObject.with(Unit, Qt.QObject.new(), probe => failing(probe))
    Qt.CallbackProbe.restoreMessages()
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Message handlers leaked handles")
    Qt.Action.lift(Unit, IO.print("QT612_MESSAGE_HANDLERS_OK native_install=1 gui=1 other_thread_previous=1 copied_context=1 unicode=1 format=1 error_fallback=1 scoped_restore=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
