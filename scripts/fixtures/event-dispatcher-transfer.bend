import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expected(-A: Type, result: Result<&1, &1, U32 & String, A>, code: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(actual, message)}: require(U32.is_eq(actual, code), message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected event dispatcher rejection")

def noop(state: Unit) -> Qt.Action(Unit):
  Qt.Action.pure(Unit, Unit{})

type WorkerState is Data:
  WorkerState{thread: Qt.QThread, probe: Qt.QObject}

def process(state: WorkerState, flags: Qt.Flags_QEventLoop__ProcessEventsFlag) -> Qt.Action(Bool):
  match state:
    case WorkerState{thread, probe}:
      do Qt.Action<Bool>:
        main: Bool <- Qt.QThread.isMainThread()
        require(main, "An event dispatcher handler left the Bend main thread")
        Qt.QObject.setObjectName(probe, "processed")
        Qt.QThread.quit(thread)
        return False{}

def finished() -> Qt.Signal:
  Qt.Signal.define("finished", [])

def quit() -> Qt.Method:
  Qt.Method.define("quit", [], Qt.unit())

def install(+thread: Qt.QThread, +dispatcher: Qt.QAbstractEventDispatcher) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +held: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.QAbstractEventDispatcher.arg(), dispatcher)
    retained: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QThread.setEventDispatcher(thread, dispatcher))
    expected(Unit, retained, 18)
    Qt.QVariant.release(held)
    Qt.QThread.setEventDispatcher(thread, dispatcher)
    foreign: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QAbstractEventDispatcher.objectName(dispatcher))
    expected(String, foreign, 18)

def transferred() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +thread: Qt.QThread <- Qt.QThread.new()
    +dispatcher: Qt.QAbstractEventDispatcher <- Qt.QAbstractEventDispatcher.newOverride()
    +probe: Qt.QObject <- Qt.QObject.new()
    +loop: Qt.QEventLoop <- Qt.QEventLoop.new()
    Qt.QAbstractEventDispatcher.Virtual.processEvents.handle(~WorkerState, ~process, dispatcher, WorkerState{thread, probe})
    Qt.QAbstractEventDispatcher.Virtual.interrupt.handle(~Unit, ~noop, dispatcher, Unit{})
    Qt.QAbstractEventDispatcher.Virtual.wakeUp.handle(~Unit, ~noop, dispatcher, Unit{})
    install(thread, dispatcher)
    +other: Qt.QAbstractEventDispatcher <- Qt.QAbstractEventDispatcher.newOverride()
    duplicate: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QThread.setEventDispatcher(thread, other))
    expected(Unit, duplicate, 17)
    connection: Qt.Connection <- Qt.Signal.connectMethod(~finished(), ~quit(), Qt.QThread.as_QObject(thread), Qt.QEventLoop.as_QObject(loop))
    Qt.QThread.start(thread)
    result: Qt.Int32 <- Qt.QEventLoop.exec(loop)
    joined: Bool <- Qt.QThread.wait__UInt64(thread, Qt.UInt64{2000, 0})
    require(joined, "The transferred event dispatcher did not finish")
    name: String <- Qt.QObject.objectName(probe)
    require(String.eq(name, "processed"), "The worker did not call its Bend event dispatcher")
    Qt.QCoreApplication.processEvents()
    expired: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QAbstractEventDispatcher.objectName(dispatcher))
    expected(String, expired, 116)

def rejected() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +thread: Qt.QThread <- Qt.QThread.new()
    null: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QThread.setEventDispatcher(thread, Qt.QAbstractEventDispatcher{0}))
    expected(Unit, null, 22)
    +parent: Qt.QObject <- Qt.QObject.new()
    +child: Qt.QAbstractEventDispatcher <- Qt.QAbstractEventDispatcher.newOverride__QObject(parent)
    parented: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QThread.setEventDispatcher(thread, child))
    expected(Unit, parented, 22)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, transferred())
    Qt.scoped(Unit, rejected())
    Qt.QCoreApplication.processEvents()
    objects: U32 <- Qt.Runtime.liveObjects()
    retentions: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(retentions, 0), "Event dispatcher ownership or callbacks leaked")
    Qt.Action.lift(Unit, IO.print("QT612_EVENT_DISPATCHER_TRANSFER_OK ownership=1 main_handlers=1 thread_deletion=1 guards=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
