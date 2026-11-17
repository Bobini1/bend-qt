import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

# The handler consumes the event even when it fails.
def post_event(fail: Bool, event: Qt.QScxmlEvent) -> Qt.Action(Unit):
  match fail:
    case True{}: Qt.Action.fail(Unit, 41, "Intentional SCXML handler failure")
    case False{}: Qt.Action.pure(Unit, Unit{})

def posted(service: Qt.QScxmlInvokableService, +event: Qt.QScxmlEvent) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QScxmlInvokableService.postEvent(service, event)
    name: String <- Qt.QScxmlEvent.name(event)
    require(String.eq(name, "owned event"), "The transferred copy changed the source event")

def post(service: Qt.QScxmlInvokableService) -> Qt.Action(Unit):
  Qt.QScxmlEvent.with(Unit, Qt.CallbackProbe.scxmlEvent(), event => posted(service, event))

def checked(fail: Bool, result: Result<&1, &1, U32 & String, Unit>) -> Qt.Action(Unit):
  match result:
    case Done{value}: require(Bool.not(fail), "The SCXML handler failure was lost")
    case Fail{(code, message)}: require(Bool.and(fail, U32.is_eq(code, 41)), "Wrong SCXML handler error: " ++ message)

def service(+fail: Bool, +value: Qt.QScxmlInvokableService) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QScxmlInvokableService.Virtual.postEvent.handle(~Bool, ~post_event, value, fail)
    result: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, post(value))
    checked(fail, result)
    deleted: U32 <- Qt.CallbackProbe.scxmlDeleted()
    require(U32.is_eq(deleted, 1), "The native SCXML event leaked or was deleted twice")

def run(+fail: Bool) -> Qt.Action(Unit):
  Qt.QScxmlInvokableService.with(Unit, Qt.QScxmlInvokableService.newOverride(Qt.QScxmlStateMachine{0}, Qt.QScxmlInvokableServiceFactory{0}), value => service(fail, value))

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    run(False{})
    run(True{})
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "SCXML event handlers leaked native handles")
    Qt.Action.lift(Unit, IO.print("QT612_SCXML_EVENT_CALLBACKS_OK input_transfer=1 source_preserved=1 failure_cleanup=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
