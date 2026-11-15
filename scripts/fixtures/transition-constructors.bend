import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expected(-A: Type, result: Result<&1, &1, U32 & String, A>, wanted: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, wanted), message)
    case Done{value}: Qt.Action.fail(Unit, 1, "A guarded transition operation succeeded")

def event_test(state: Unit, event: Qt.QEvent) -> Qt.Action(Bool):
  Qt.Action.pure(Bool, False{})

def on_transition(state: Qt.QObject, event: Qt.QEvent) -> Qt.Action(Unit):
  Qt.QObject.setObjectName(state, "called")

def verify(+transition: Qt.QAbstractTransition, +source: Qt.QState) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    actual: Qt.QState <- Qt.QAbstractTransition.sourceState(transition)
    require(U32.is_eq(Qt.QState.word(actual), Qt.QState.word(source)), "Transition lost its constructor source state")
    parent: Qt.QObject <- Qt.QObject.parent(Qt.QAbstractTransition.as_QObject(transition))
    require(U32.is_eq(Qt.QObject.word(parent), Qt.QState.word(source)), "Native source-state parenting was not preserved")
    +probe: Qt.QObject <- Qt.QObject.new()
    Qt.QAbstractTransition.Virtual.eventTest.handle(~Unit, ~event_test, transition, Unit{})
    Qt.QAbstractTransition.Virtual.onTransition.handle(~Qt.QObject, ~on_transition, transition, probe)
    good: Bool <- Qt.CallbackProbe.transitionVirtual(transition, source)
    require(good, "Native transition virtual dispatch or source state failed")
    name: String <- Qt.QObject.objectName(probe)
    require(String.eq(name, "called"), "The transition did not invoke its Bend override")

def objects() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +source: Qt.QState <- Qt.QState.new()
    +transition: Qt.QAbstractTransition <- Qt.QAbstractTransition.newOverride__QState(source)
    verify(transition, source)
    borrowed: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QAbstractTransition.destroy(transition))
    expected(Unit, borrowed, 1)
    +event: Qt.QEventTransition <- Qt.QEventTransition.newOverride__QState(source)
    verify(Qt.QEventTransition.as_QAbstractTransition(event), source)
    +empty: Qt.QAbstractTransition <- Qt.QAbstractTransition.newOverride()
    verify(empty, Qt.QState{0})
    +empty_event: Qt.QEventTransition <- Qt.QEventTransition.newOverride__NoArgs()
    verify(Qt.QEventTransition.as_QAbstractTransition(empty_event), Qt.QState{0})
    Qt.QState.destroy(source)
    stale: Result<&1, &1, U32 & String, Qt.QState> <- Qt.Action.attempt(Qt.QState, Qt.QAbstractTransition.sourceState(transition))
    expected(Qt.QState, stale, 116)
    stale: Result<&1, &1, U32 & String, Qt.QState> <- Qt.Action.attempt(Qt.QState, Qt.QAbstractTransition.sourceState(Qt.QEventTransition.as_QAbstractTransition(event)))
    expected(Qt.QState, stale, 116)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, objects())
    count: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(count, 0), "Transition constructors leaked source-state or handler roots")
    Qt.Action.lift(Unit, IO.print("QT612_TRANSITION_CONSTRUCTORS_OK default=1 source_parent=1 native_virtuals=1 parent_deletion=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
