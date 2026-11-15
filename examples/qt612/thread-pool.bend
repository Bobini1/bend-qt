import Base
import ../../packages/qt612/qt.bend as Qt

# QRunnable::run is called on a pool thread. Its Bend handler runs on the main
# thread while that pool thread waits, so the main thread waits for jobs only
# inside QCoreApplication.exec.

type Job is Data:
  Job{pool: Qt.QThreadPool, job: Qt.QRunnable, probe: Qt.QObject, text: String, code: U32}

type Busy is Data:
  Busy{pool: Qt.QThreadPool, probe: Qt.QObject, blocker: Qt.QRunnable, queued: Qt.QRunnable, kept: Qt.QRunnable}

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expect_error(~A: Type, expected: U32, result: Result<&1, &1, U32 & String, A>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong pool error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "An invalid pool operation succeeded")

# Runs while its pool thread waits: the pool is busy with this job.
def work(+pool: Qt.QThreadPool, job: Qt.QRunnable, probe: Qt.QObject, text: String, code: U32) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    active: Qt.Int32 <- Qt.QThreadPool.activeThreadCount(pool)
    require(U32.is_eq(Qt.Int32.word(active), 1), "No pool thread was waiting for the job")
    ready: Bool <- Qt.QThreadPool.waitForDone__Int32(pool, Qt.Int32{0})
    require(Bool.not(ready), "A busy pool reported done")
    taken: Bool <- Qt.QThreadPool.tryTake(pool, job)
    require(Bool.not(taken), "tryTake removed a running job")
    Qt.QObject.setObjectName(probe, text)
    Qt.QCoreApplication.exit__Int32(Qt.Int32{code})

def ran(state: Job) -> Qt.Action(Unit):
  match state:
    case Job{pool, job, probe, text, code}: work(pool, job, probe, text, code)

# Serves a started job in exec, then waits for its thread.
def run_loop(+pool: Qt.QThreadPool, +probe: Qt.QObject, text: String, code: U32) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    exit: Qt.Int32 <- Qt.QCoreApplication.exec()
    require(U32.is_eq(Qt.Int32.word(exit), code), "The job did not end the event loop")
    name: String <- Qt.QObject.objectName(probe)
    require(String.eq(name, text), "The job did not change the probe")
    finished: Bool <- Qt.QThreadPool.waitForDone__Int32(pool, Qt.Int32{5000})
    require(finished, "The pool thread did not finish")

# Qt's auto-delete job is deleted once it has run.
def auto_job(+pool: Qt.QThreadPool, +probe: Qt.QObject, +job: Qt.QRunnable) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QRunnable.Virtual.run.handle(~Job, ~ran, job, Job{pool, job, probe, "auto", 5})
    Qt.QThreadPool.start__QRunnable(pool, job)
    # A main thread blocked outside an event loop cannot run the job's handler.
    early: Bool <- Qt.QThreadPool.waitForDone__Int32(pool, Qt.Int32{50})
    require(Bool.not(early), "The job finished while the main thread was blocked")
    run_loop(pool, probe, "auto", 5)
    stale: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.QRunnable.autoDelete(job))
    expect_error(Bool, 116, stale)

# A job without auto-delete stays with Bend and can run again.
def reusable_job(+pool: Qt.QThreadPool, +probe: Qt.QObject, +job: Qt.QRunnable) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QRunnable.setAutoDelete(job, False{})
    Qt.QRunnable.Virtual.run.handle(~Job, ~ran, job, Job{pool, job, probe, "first", 6})
    started: Bool <- Qt.QThreadPool.tryStart(pool, job)
    require(started, "An idle pool did not start the job")
    run_loop(pool, probe, "first", 6)
    automatic: Bool <- Qt.QRunnable.autoDelete(job)
    require(Bool.not(automatic), "The reusable job was deleted or changed")
    Qt.QRunnable.Virtual.run.handle(~Job, ~ran, job, Job{pool, job, probe, "reserved", 7})
    Qt.QThreadPool.reserveThread(pool)
    Qt.QThreadPool.startOnReservedThread(pool, job)
    run_loop(pool, probe, "reserved", 7)

# Runs while the only pool thread is busy with the blocker. Neither job
# queued here runs: tryTake and clear remove them first.
def busy_work(+pool: Qt.QThreadPool, probe: Qt.QObject, +blocker: Qt.QRunnable, +queued: Qt.QRunnable, +kept: Qt.QRunnable) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    running: Bool <- Qt.QThreadPool.tryTake(pool, blocker)
    require(Bool.not(running), "tryTake removed a running job")
    destroyed: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QRunnable.destroy(blocker))
    expect_error(Unit, 16, destroyed)
    immediate: Bool <- Qt.QThreadPool.tryStart(pool, queued)
    require(Bool.not(immediate), "tryStart ignored the busy pool")
    unused: Bool <- Qt.QRunnable.autoDelete(queued)
    require(unused, "A failed tryStart consumed the job")
    Qt.QThreadPool.start__QRunnable(pool, queued)
    twice: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QThreadPool.start__QRunnable(pool, queued))
    expect_error(Unit, 16, twice)
    taken: Bool <- Qt.QThreadPool.tryTake(pool, queued)
    require(taken, "A queued job could not be taken back")
    Qt.QRunnable.setAutoDelete(kept, False{})
    Qt.QThreadPool.start__QRunnable(pool, kept)
    pinned: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QRunnable.setAutoDelete(kept, True{}))
    expect_error(Unit, 16, pinned)
    Qt.QThreadPool.start__QRunnable(pool, queued)
    Qt.QThreadPool.clear(pool)
    automatic: Bool <- Qt.QRunnable.autoDelete(kept)
    require(Bool.not(automatic), "clear deleted a job without auto-delete")
    cleared: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.QRunnable.autoDelete(queued))
    expect_error(Bool, 116, cleared)
    Qt.QObject.setObjectName(probe, "busy")
    Qt.QCoreApplication.exit__Int32(Qt.Int32{8})

def busy(state: Busy) -> Qt.Action(Unit):
  match state:
    case Busy{pool, probe, blocker, queued, kept}: busy_work(pool, probe, blocker, queued, kept)

def busy_jobs(+pool: Qt.QThreadPool, +probe: Qt.QObject, +blocker: Qt.QRunnable, +queued: Qt.QRunnable, +kept: Qt.QRunnable) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QThreadPool.setMaxThreadCount(pool, Qt.Int32{1})
    Qt.QRunnable.setAutoDelete(blocker, False{})
    Qt.QRunnable.Virtual.run.handle(~Busy, ~busy, blocker, Busy{pool, probe, blocker, queued, kept})
    Qt.QThreadPool.start__QRunnable(pool, blocker)
    run_loop(pool, probe, "busy", 8)

def busy_case(+pool: Qt.QThreadPool, +probe: Qt.QObject) -> Qt.Action(Unit):
  Qt.QRunnable.with(Unit, Qt.QRunnable.newOverride(), blocker =>
    Qt.QRunnable.with(Unit, Qt.QRunnable.newOverride(), queued =>
      Qt.QRunnable.with(Unit, Qt.QRunnable.newOverride(), kept => busy_jobs(pool, probe, blocker, queued, kept))))

def cases(+pool: Qt.QThreadPool, +probe: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QRunnable.with(Unit, Qt.QRunnable.newOverride(), job => auto_job(pool, probe, job))
    Qt.QRunnable.with(Unit, Qt.QRunnable.newOverride(), job => reusable_job(pool, probe, job))
    busy_case(pool, probe)

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QThreadPool.with(Unit, Qt.QThreadPool.new(), pool =>
      Qt.QObject.with(Unit, Qt.QObject.new(), probe => cases(pool, probe)))
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Pool jobs leaked handles or connections")
    Qt.Action.lift(Unit, IO.print("QT612_THREAD_POOL_OK pool_handler=1 main_thread_effect=1 main_wait=1 auto_delete=1 reusable=1 reserved=1 running_try_take=1 busy_try_start=1 duplicate=1 try_take=1 pinned=1 clear=1 objects=0 connections=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
