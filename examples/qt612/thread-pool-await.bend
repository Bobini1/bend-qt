import Base
import ../../packages/qt612/qt.bend as Qt

def work(result: Qt.QObject) -> Qt.Action(Unit):
  Qt.QObject.setObjectName(result, "The pool job finished")

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +pool: Qt.QThreadPool <- Qt.QThreadPool.new()
    +result: Qt.QObject <- Qt.QObject.new()
    +job: Qt.QRunnable <- Qt.QRunnable.newOverride()
    Qt.QRunnable.Virtual.run.handle(~Qt.QObject, ~work, job, result)
    Qt.QThreadPool.start__QRunnable(pool, job)
    # Qt/Bend events keep running while the pool thread waits for its handler.
    Qt.QThreadPool.awaitDone(pool)
    text: String <- Qt.QObject.objectName(result)
    Qt.Action.lift(Unit, IO.print(text))
    Qt.Action.lift(Unit, IO.print("QT612_THREAD_POOL_AWAIT_OK"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
