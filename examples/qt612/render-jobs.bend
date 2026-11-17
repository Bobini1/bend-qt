import Base
import ../../packages/qt612/qt.bend as Qt

# Render.useGuiThread selects Qt's basic render loop, so render jobs run on the
# main thread, inside the event loop that renders the frame. Qt deletes each
# job after running or discarding it.

type Mark is Data:
  Mark{probe: Qt.QObject, text: String, stop: Bool}

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expect_error(~A: Type, expected: U32, result: Result<&1, &1, U32 & String, A>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong render-job error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "A deleted render job is still usable")

def stale(+job: Qt.QRunnable) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    result: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.QRunnable.autoDelete(job))
    expect_error(Bool, 116, result)

def finish(stop: Bool) -> Qt.Action(Unit):
  match stop:
    case True{}: Qt.QCoreApplication.exit__Int32(Qt.Int32{9})
    case False{}: Qt.Action.pure(Unit, Unit{})

# Appends its text to the probe's name; the last job ends the event loop.
def marked(+probe: Qt.QObject, text: String, stop: Bool) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    previous: String <- Qt.QObject.objectName(probe)
    Qt.QObject.setObjectName(probe, previous ++ text)
    finish(stop)

def mark(state: Mark) -> Qt.Action(Unit):
  match state:
    case Mark{probe, text, stop}: marked(probe, text, stop)

def named(+probe: Qt.QObject, expected: String, message: String) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    name: String <- Qt.QObject.objectName(probe)
    require(String.eq(name, expected), message)

# A window that is not exposed discards jobs without running them.
def hidden_window(+probe: Qt.QObject, +early: Qt.QRunnable, +later: Qt.QRunnable, +window: Qt.QQuickWindow) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QRunnable.Virtual.run.handle(~Mark, ~mark, early, Mark{probe, "hidden", False{}})
    Qt.QRunnable.Virtual.run.handle(~Mark, ~mark, later, Mark{probe, "hidden", False{}})
    Qt.QQuickWindow.scheduleRenderJob(window, early, Qt.QQuickWindow.RenderStage.NoStage())
    stale(early)
    Qt.QQuickWindow.scheduleRenderJob(window, later, Qt.QQuickWindow.RenderStage.BeforeRenderingStage())

def hidden(+probe: Qt.QObject, +early: Qt.QRunnable, +later: Qt.QRunnable) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQuickWindow.with(Unit, Qt.QQuickWindow.new(), window => hidden_window(probe, early, later, window))
    # Destroying the window deletes its pending jobs.
    stale(later)
    named(probe, "", "A discarded render job ran")

def hidden_case(+probe: Qt.QObject) -> Qt.Action(Unit):
  Qt.QRunnable.with(Unit, Qt.QRunnable.newOverride(), early =>
    Qt.QRunnable.with(Unit, Qt.QRunnable.newOverride(), later => hidden(probe, early, later)))

# Jobs for later stages run while exec renders the next frame, in stage order.
def frame_jobs(+window: Qt.QQuickWindow, +probe: Qt.QObject, +after: Qt.QRunnable, +before: Qt.QRunnable) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QRunnable.Virtual.run.handle(~Mark, ~mark, after, Mark{probe, "after", True{}})
    Qt.QRunnable.Virtual.run.handle(~Mark, ~mark, before, Mark{probe, "before,", False{}})
    Qt.QQuickWindow.scheduleRenderJob(window, after, Qt.QQuickWindow.RenderStage.AfterRenderingStage())
    Qt.QQuickWindow.scheduleRenderJob(window, before, Qt.QQuickWindow.RenderStage.BeforeRenderingStage())
    named(probe, "", "A staged render job ran before rendering")
    Qt.QQuickWindow.update(window)
    code: Qt.Int32 <- Qt.QCoreApplication.exec()
    require(U32.is_eq(Qt.Int32.word(code), 9), "The render jobs did not end the event loop")
    named(probe, "before,after", "Render jobs did not run in stage order")
    stale(before)
    stale(after)

# On an exposed window a NoStage job runs during scheduleRenderJob.
def immediate_job(+window: Qt.QQuickWindow, +probe: Qt.QObject, +job: Qt.QRunnable) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QObject.setObjectName(probe, "")
    Qt.QRunnable.Virtual.run.handle(~Mark, ~mark, job, Mark{probe, "now", False{}})
    Qt.QQuickWindow.scheduleRenderJob(window, job, Qt.QQuickWindow.RenderStage.NoStage())
    named(probe, "now", "A NoStage job did not run at once")
    stale(job)

def shown(+probe: Qt.QObject, +window: Qt.QQuickWindow) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQuickWindow.resize__Int32_Int32(window, Qt.Int32{32}, Qt.Int32{32})
    Qt.QQuickWindow.show(window)
    Qt.QRunnable.with(Unit, Qt.QRunnable.newOverride(), after =>
      Qt.QRunnable.with(Unit, Qt.QRunnable.newOverride(), before => frame_jobs(window, probe, after, before)))
    exposed: Bool <- Qt.QQuickWindow.isExposed(window)
    require(exposed, "The rendered window is not exposed")
    Qt.QRunnable.with(Unit, Qt.QRunnable.newOverride(), job => immediate_job(window, probe, job))
    Qt.QQuickWindow.hide(window)

def cases(+probe: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    hidden_case(probe)
    Qt.QQuickWindow.with(Unit, Qt.QQuickWindow.new(), window => shown(probe, window))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Render.useGuiThread()
    Qt.QObject.with(Unit, Qt.QObject.new(), probe => cases(probe))
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Render jobs leaked handles or connections")
    Qt.Action.lift(Unit, IO.print("QT612_RENDER_JOBS_OK callback=1 stages=1 no_stage=1 hidden_discard=1 ownership=1 objects=0 connections=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
