import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def assign(+state: Qt.QState, +target: Qt.QObject, value: Qt.QVariant) -> Qt.Action(Unit):
  Qt.QState.assignProperty(state, target, "objectName", value)

# The handlers record the machine's progress in the probe's name.
def machine_started(probe: Qt.QObject) -> Qt.Action(Unit):
  Qt.QObject.setObjectName(probe, "started")

def second_entered(probe: Qt.QObject) -> Qt.Action(Unit):
  Qt.QObject.setObjectName(probe, "second")

def machine_stopped(probe: Qt.QObject) -> Qt.Action(Unit):
  Qt.QObject.setObjectName(probe, "stopped")

# The machine starts and stops through posted events, so the test lets Qt
# process them before it reads the probe.
def progress(+probe: Qt.QObject, expected: String, message: String) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QCoreApplication.processEvents()
    seen: String <- Qt.QObject.objectName(probe)
    require(String.eq(seen, expected), message)

def running(+machine: Qt.QStateMachine, +target: Qt.QObject, +trigger: Qt.QObject, +probe: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QStateMachine.start(machine)
    progress(probe, "started", "State machine did not start")
    name: String <- Qt.QObject.objectName(target)
    require(String.eq(name, "entered"), "State did not apply its copied property name/value")
    Qt.QObject.setObjectName(trigger, "advance")
    progress(probe, "second", "Named-signal transition did not enter the second state")
    Qt.QStateMachine.stop(machine)
    progress(probe, "stopped", "State machine did not stop")

def watched(+machine: Qt.QStateMachine, +second: Qt.QState, +target: Qt.QObject, +trigger: Qt.QObject, +probe: Qt.QObject) -> Qt.Action(Unit):
  Qt.Connection.with(Unit, Qt.Signal.connect(~Qt.QStateMachine.started(), ~Qt.QObject, ~machine_started, machine, probe), started =>
    Qt.Connection.with(Unit, Qt.Signal.connect(~Qt.QState.entered(), ~Qt.QObject, ~second_entered, second, probe), entered =>
      Qt.Connection.with(Unit, Qt.Signal.connect(~Qt.QStateMachine.stopped(), ~Qt.QObject, ~machine_stopped, machine, probe), stopped =>
        running(machine, target, trigger, probe))))

def connected(+machine: Qt.QStateMachine, +second: Qt.QState, +target: Qt.QObject, +trigger: Qt.QObject, transition: Qt.QSignalTransition) -> Qt.Action(Unit):
  Qt.QObject.with(Unit, Qt.QObject.new(), probe => watched(machine, second, target, trigger, probe))

def configured(+machine: Qt.QStateMachine, +first: Qt.QState, +second: Qt.QState, +target: Qt.QObject, +trigger: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QVariant.with(Unit, Qt.QVariant.fromString("entered"), value => assign(first, target, value))
    Qt.QStateMachine.setInitialState(machine, Qt.QState.as_QAbstractState(first))
    Qt.QSignalTransition.with(Unit, Qt.QState.addTransition__QObject_String_QAbstractState(first, trigger, "2objectNameChanged(QString)", Qt.QState.as_QAbstractState(second)), transition => connected(machine, second, target, trigger, transition))

def objects(+machine: Qt.QStateMachine, +first: Qt.QState, +second: Qt.QState) -> Qt.Action(Unit):
  Qt.QObject.with(Unit, Qt.QObject.new(), target =>
    Qt.QObject.with(Unit, Qt.QObject.new(), trigger => configured(machine, first, second, target, trigger)))

def states(+machine: Qt.QStateMachine) -> Qt.Action(Unit):
  Qt.QState.with(Unit, Qt.QState.new__QState(Qt.QStateMachine.as_QState(machine)), first =>
    Qt.QState.with(Unit, Qt.QState.new__QState(Qt.QStateMachine.as_QState(machine)), second => objects(machine, first, second)))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QStateMachine.with(Unit, Qt.QStateMachine.new(), machine => states(machine))
    objects: U32 <- Qt.Runtime.liveObjects()
    pins: U32 <- Qt.Runtime.liveRetentions()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(pins, 0) && U32.is_eq(connections, 0), "State property/transition test leaked handles")
    Qt.Action.lift(Unit, IO.print("QT612_STATE_PROPERTIES_OK property=1 named_signal=1 transition=1 cleanup=1 connections=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
