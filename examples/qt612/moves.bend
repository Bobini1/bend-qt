import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def error(~A: Type, expected: U32, result: Result<&1, &1, U32 & String, A>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong move error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Invalid move operation succeeded")

def moved_directory(+value: Qt.QTemporaryDir, source: Qt.QTemporaryDir, +path: String) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    actual: String <- Qt.QTemporaryDir.path(value)
    require(String.eq(actual, path), "Move changed the temporary directory")
    stale: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QTemporaryDir.path(source))
    error(String, 116, stale)
    exists: Bool <- Qt.QFileInfo.exists__String(path)
    require(exists, "Moved-from cleanup removed the directory")

def directory(+source: Qt.QTemporaryDir) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +path: String <- Qt.QTemporaryDir.path(source)
    Qt.QTemporaryDir.with(Unit, Qt.QTemporaryDir.new__QTemporaryDir(source), value => moved_directory(value, source, path))
    exists: Bool <- Qt.QFileInfo.exists__String(path)
    require(Bool.not(exists), "Moved directory was not removed on cleanup")

def moved_blocker(+value: Qt.QSignalBlocker, source: Qt.QSignalBlocker, +object: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    blocked: Bool <- Qt.QObject.signalsBlocked(object)
    require(blocked, "Moving a blocker unblocked its object")
    stale: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QSignalBlocker.unblock(source))
    error(Unit, 116, stale)
    held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QObject.destroy(object))
    error(Unit, 16, held)
    self_move: Result<&1, &1, U32 & String, Qt.QSignalBlocker> <- Qt.Action.attempt(Qt.QSignalBlocker, Qt.QSignalBlocker.op_assign(value, value))
    error(Qt.QSignalBlocker, 22, self_move)
    Qt.QSignalBlocker.unblock(value)
    Qt.QSignalBlocker.reblock(value)

def blocker(+source: Qt.QSignalBlocker, +object: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QSignalBlocker.with(Unit, Qt.QSignalBlocker.new__QSignalBlocker(source), value => moved_blocker(value, source, object))
    blocked: Bool <- Qt.QObject.signalsBlocked(object)
    require(Bool.not(blocked), "Moved blocker cleanup did not restore signals")

def assigned_blocker(+target: Qt.QSignalBlocker, +source: Qt.QSignalBlocker, +first: Qt.QObject, +second: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    ignored: Qt.QSignalBlocker <- Qt.QSignalBlocker.op_assign(target, source)
    first_blocked: Bool <- Qt.QObject.signalsBlocked(first)
    second_blocked: Bool <- Qt.QObject.signalsBlocked(second)
    require(Bool.not(first_blocked) && second_blocked, "Move assignment did not transfer the blocker")
    stale: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QSignalBlocker.reblock(source))
    error(Unit, 116, stale)
    held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QObject.destroy(second))
    error(Unit, 16, held)

def assignment(+first: Qt.QObject, +second: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QSignalBlocker.with(Unit, Qt.QSignalBlocker.new__QObject(first), target =>
      Qt.QSignalBlocker.with(Unit, Qt.QSignalBlocker.new__QObject(second), source => assigned_blocker(target, source, first, second)))
    blocked: Bool <- Qt.QObject.signalsBlocked(second)
    require(Bool.not(blocked), "Assigned blocker cleanup did not restore signals")

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QTemporaryDir.with(Unit, Qt.QTemporaryDir.new(), value => directory(value))
    Qt.QObject.with(Unit, Qt.QObject.new(), +object =>
      Qt.QSignalBlocker.with(Unit, Qt.QSignalBlocker.new__QObject(object), source => blocker(source, object)))
    Qt.QObject.with(Unit, Qt.QObject.new(), first =>
      Qt.QObject.with(Unit, Qt.QObject.new(), second => assignment(first, second)))
    objects: U32 <- Qt.Runtime.liveObjects()
    pins: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(pins, 0), "Moves leaked handles or retained objects")
    Qt.Action.lift(Unit, IO.print("QT612_MOVES_OK constructor=1 assignment=1 stale_source=1 self_move=1 retention=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
