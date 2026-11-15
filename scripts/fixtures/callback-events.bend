import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expect_error(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Unexpected error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected the timer handler failure")

def timed_out(code: U32) -> Qt.Action(Unit):
  Qt.Action.fail(Unit, code, "Intentional timer handler failure")

# The nested event loop runs the failing timer handler. Its failure belongs to
# processEvents, the call that ran it, not to the rowCount call around it.
def counted(state: Unit, parent: Qt.QModelIndex) -> Qt.Action(Qt.Int32):
  do Qt.Action<Qt.Int32>:
    nested: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QCoreApplication.processEvents())
    expect_error(Unit, nested, 47)
    return Qt.Int32{17}

def armed(+timer: Qt.QTimer, model: Qt.QAbstractListModel) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QTimer.setSingleShot(timer, True{})
    Qt.QTimer.start__Int32(timer, Qt.Int32{0})
    count: Qt.Int32 <- Qt.QAbstractListModel.rowCount(model)
    require(U32.is_eq(Qt.Int32.word(count), 17), "An event handler failure changed the direct result")

def nested_event(+model: Qt.QAbstractListModel, +timer: Qt.QTimer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QAbstractItemModel.Virtual.rowCount.handle(~Unit, ~counted, Qt.QAbstractListModel.as_QAbstractItemModel(model), Unit{})
    Qt.Connection.with(Unit, Qt.QTimer.connect_timeout(~U32, ~timed_out, timer, 47), connection => armed(timer, model))

def stop(code: U32) -> Qt.Action(Unit):
  Qt.QCoreApplication.exit__Int32(Qt.Int32{code})

def started(+timer: Qt.QTimer, delay: U32) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QTimer.setSingleShot(timer, True{})
    Qt.QTimer.start__Int32(timer, Qt.Int32{delay})

# Outside any handler the failure belongs to the event loop that ran it.
def looped(+timer: Qt.QTimer, +stopper: Qt.QTimer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    started(timer, 0)
    started(stopper, 50)
    result: Result<&1, &1, U32 & String, Qt.Int32> <- Qt.Action.attempt(Qt.Int32, Qt.QCoreApplication.exec())
    expect_error(Qt.Int32, result, 47)

def stopping(+timer: Qt.QTimer, +stopper: Qt.QTimer) -> Qt.Action(Unit):
  Qt.Connection.with(Unit, Qt.QTimer.connect_timeout(~U32, ~stop, stopper, 0), connection => looped(timer, stopper))

def loop_event(+timer: Qt.QTimer) -> Qt.Action(Unit):
  Qt.Connection.with(Unit, Qt.QTimer.connect_timeout(~U32, ~timed_out, timer, 47), connection =>
    Qt.QTimer.with(Unit, Qt.QTimer.new(), stopper => stopping(timer, stopper)))

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QAbstractListModel.with(Unit, Qt.QAbstractListModel.newOverride(), model => Qt.QTimer.with(Unit, Qt.QTimer.new(), timer => nested_event(model, timer)))
    Qt.QTimer.with(Unit, Qt.QTimer.new(), timer => loop_event(timer))
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Event handlers leaked handles")
    Qt.Action.lift(Unit, IO.print("QT612_CALLBACK_EVENTS_OK nested_event=1 direct_result_preserved=1 async_error_delivered=1 objects=0 connections=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
