import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expected(-A: Type, result: Result<&1, &1, U32 & String, A>, code: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(actual, message)}: require(U32.is_eq(actual, code), message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected mutex ownership rejection")

def basic() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +mutex: Qt.QMutex <- Qt.QMutex.new()
    +locker: Qt.QMutexLocker <- Qt.QMutexLocker.new(mutex)
    locked: Bool <- Qt.QMutexLocker.isLocked(locker)
    require(locked, "QMutexLocker did not lock its native mutex")
    same: Qt.QMutex <- Qt.QMutexLocker.mutex(locker)
    require(U32.is_eq(Qt.QMutex.word(same), Qt.QMutex.word(mutex)), "The locker erased its concrete mutex type")
    blocked: Bool <- Qt.QMutex.tryLock(mutex)
    require(Bool.not(blocked), "A locked mutex was available")
    Qt.QMutexLocker.unlock(locker)
    available: Bool <- Qt.QMutex.tryLock(mutex)
    require(available, "QMutexLocker.unlock did not release the native lock")
    Qt.QMutex.unlock(mutex)
    held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QMutex.destroy(mutex))
    expected(Unit, held, 16)
    Qt.QMutexLocker.relock(locker)
    locked: Bool <- Qt.QMutexLocker.isLocked(locker)
    require(locked, "QMutexLocker.relock did not acquire its native lock")
    Qt.QMutexLocker.release(locker)
    available: Bool <- Qt.QMutex.tryLock(mutex)
    require(available, "Destroying the locker did not unlock its mutex")
    Qt.QMutex.unlock(mutex)
    stale: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.QMutexLocker.isLocked(locker))
    expected(Bool, stale, 116)

def failing(locker: Qt.QMutexLocker) -> Qt.Action(Unit):
  Qt.Action.fail(Unit, 86, "locker body failed")

def scoped_failure() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +mutex: Qt.QMutex <- Qt.QMutex.new()
    failed: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit,
      Qt.QMutexLocker.with(Unit, Qt.QMutexLocker.new(mutex), locker => failing(locker)))
    expected(Unit, failed, 86)
    available: Bool <- Qt.QMutex.tryLock(mutex)
    require(available, "A failed Action body left its native mutex locked")
    Qt.QMutex.unlock(mutex)

def recursive_and_null() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +mutex: Qt.QRecursiveMutex <- Qt.QRecursiveMutex.new()
    +first: Qt.QRecursiveMutexLocker <- Qt.QMutexLocker.new__QRecursiveMutex(mutex)
    +second: Qt.QRecursiveMutexLocker <- Qt.QMutexLocker.new__QRecursiveMutex(mutex)
    locked: Bool <- Qt.QRecursiveMutexLocker.isLocked(second)
    require(locked, "The recursive specialization did not lock recursively")
    Qt.QRecursiveMutexLocker.unlock(first)
    same: Qt.QRecursiveMutex <- Qt.QRecursiveMutexLocker.mutex(second)
    require(U32.is_eq(Qt.QRecursiveMutex.word(same), Qt.QRecursiveMutex.word(mutex)), "The recursive specialization lost its mutex type")
    +empty: Qt.QMutexLocker <- Qt.QMutexLocker.new__QMutex(Qt.QMutex{0})
    locked: Bool <- Qt.QMutexLocker.isLocked(empty)
    require(Bool.not(locked), "A null mutex locker was locked")
    Qt.QMutexLocker.unlock(empty)
    Qt.QMutexLocker.relock(empty)
    same: Qt.QMutex <- Qt.QMutexLocker.mutex(empty)
    require(U32.is_eq(Qt.QMutex.word(same), 0), "A null locker invented a native mutex")

def swapping() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +first: Qt.QMutex <- Qt.QMutex.new()
    +second: Qt.QMutex <- Qt.QMutex.new()
    +a: Qt.QMutexLocker <- Qt.QMutexLocker.new(first)
    +b: Qt.QMutexLocker <- Qt.QMutexLocker.new(second)
    Qt.QMutexLocker.swap(a, b)
    selected: Qt.QMutex <- Qt.QMutexLocker.mutex(a)
    require(U32.is_eq(Qt.QMutex.word(selected), Qt.QMutex.word(second)), "A native locker swap kept its old mutex")
    Qt.QMutexLocker.destroy(a)
    Qt.QMutex.destroy(second)
    held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QMutex.destroy(first))
    expected(Unit, held, 16)
    Qt.QMutexLocker.destroy(b)
    Qt.QMutex.destroy(first)

def future_state() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +first: Qt.QFutureInterfaceBase <- Qt.QFutureInterfaceBase.new()
    +second: Qt.QFutureInterfaceBase <- Qt.QFutureInterfaceBase.new()
    +mutex: Qt.QMutex <- Qt.QFutureInterfaceBase.mutex(first)
    +locker: Qt.QMutexLocker <- Qt.QMutexLocker.new(mutex)
    held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QFutureInterfaceBase.swap(first, second))
    expected(Unit, held, 16)
    Qt.QMutexLocker.unlock(locker)
    held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QFutureInterfaceBase.swap(first, second))
    expected(Unit, held, 16)
    Qt.QMutexLocker.release(locker)
    Qt.QFutureInterfaceBase.swap(first, second)
    stale: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.QMutex.tryLock(mutex))
    expected(Bool, stale, 116)

def escaped(+mutex: Qt.QMutex) -> Qt.Action(Qt.QMutexLocker):
  do Qt.Action<Qt.QMutexLocker>:
    locker: Qt.QMutexLocker <- Qt.QMutexLocker.new(mutex)
    Qt.QMutexLocker.keep(locker)

def kept() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +mutex: Qt.QMutex <- Qt.QMutex.new()
    +locker: Qt.QMutexLocker <- Qt.scoped(Qt.QMutexLocker, escaped(mutex))
    locked: Bool <- Qt.QMutexLocker.isLocked(locker)
    require(locked, "Keeping a locker did not preserve its native lock")
    Qt.QMutexLocker.release(locker)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, basic())
    Qt.scoped(Unit, scoped_failure())
    Qt.scoped(Unit, recursive_and_null())
    Qt.scoped(Unit, swapping())
    Qt.scoped(Unit, future_state())
    Qt.scoped(Unit, kept())
    live: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(live, 0), "Mutex lockers leaked native handles")
    leases: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(leases, 0), "Mutex lockers leaked mutex leases")
    Qt.Action.lift(Unit, IO.print("QT612_MUTEX_LOCKERS_OK native=1 recursive=1 nullable=1 scopes=1 failure=1 swaps=1 future_mutex=1 keep=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
