import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expected(-A: Type, result: Result<&1, &1, U32 & String, A>, code: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(actual, text)}: require(U32.is_eq(actual, code), text)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected pool await failure")

type Job is Data:
  Job{pool: Qt.QThreadPool, probe: Qt.QObject}

def job_work(+pool: Qt.QThreadPool, probe: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    poll: Bool <- Qt.QThreadPool.awaitDoneFor(pool, Qt.Int32{0})
    require(Bool.not(poll), "A running job reported its own pool complete")
    self_wait: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QThreadPool.awaitDone(pool))
    expected(Unit, self_wait, 35)
    Qt.QObject.setObjectName(probe, "finished")

def work(state: Job) -> Qt.Action(Unit):
  match state:
    case Job{pool, probe}: job_work(pool, probe)

def failed(state: Unit) -> Qt.Action(Unit):
  Qt.Action.fail(Unit, 69, "Expected job failure")

def jobs() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +pool: Qt.QThreadPool <- Qt.QThreadPool.new()
    +probe: Qt.QObject <- Qt.QObject.new()
    +job: Qt.QRunnable <- Qt.QRunnable.newOverride()
    Qt.QRunnable.Virtual.run.handle(~Job, ~work, job, Job{pool, probe})
    Qt.QThreadPool.start__QRunnable(pool, job)
    early: Bool <- Qt.QThreadPool.awaitDoneFor(pool, Qt.Int32{0})
    require(Bool.not(early), "A zero timeout unexpectedly executed the job")
    Qt.QThreadPool.awaitDone(pool)
    name: String <- Qt.QObject.objectName(probe)
    require(String.eq(name, "finished"), "Pool await did not run Bend handlers")
    stale: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.QRunnable.autoDelete(job))
    expected(Bool, stale, 116)
    ready: Bool <- Qt.QThreadPool.awaitDoneFor(pool, Qt.Int32{5000})
    require(ready, "An idle pool timed out")
    +failure: Qt.QRunnable <- Qt.QRunnable.newOverride()
    Qt.QRunnable.Virtual.run.handle(~Unit, ~failed, failure, Unit{})
    Qt.QThreadPool.start__QRunnable(pool, failure)
    result: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QThreadPool.awaitDone(pool))
    expected(Unit, result, 69)
    Qt.QThreadPool.awaitDone(pool)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, jobs())
    live: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(live, 0), "Pool await left live jobs")
    Qt.Action.lift(Unit, IO.print("QT612_POOL_AWAIT_OK event_loop=1 poll=1 timeout=1 self_wait=35 failure=69 auto_delete=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
