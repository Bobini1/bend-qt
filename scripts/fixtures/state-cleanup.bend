import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def rejected(-A: Type, code: U32, result: Result<&1, &1, U32 & String, A>) -> Qt.Action(Unit):
  match result:
    case Fail{(actual, message)}: require(U32.is_eq(actual, code), "Wrong state cleanup error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Invalid state cleanup operation succeeded")

def snapshot(value: Qt.QStringConverterBase.State.CleanupSnapshot) -> Qt.Action(Unit):
  match value:
    case Qt.QStringConverterBase.State.CleanupSnapshot{flags, internal, +remaining, +invalid}:
      require(U32.is_eq(Qt.QStringConverterBase.Flag.word(flags), 0) && U32.is_eq(Qt.Int64.lo(remaining), 8) && U32.is_eq(Qt.Int64.hi(remaining), 0) && U32.is_eq(Qt.Int64.lo(invalid), 9) && U32.is_eq(Qt.Int64.hi(invalid), 0), "Cleanup snapshot changed native fields")

# Qt runs the handler when it clears the state, with a copy of the state's
# fields. The state itself is already cleared.
def cleanup(bad: Bool, value: Qt.QStringConverterBase.State.CleanupSnapshot) -> Qt.Action(Unit):
  match bad:
    case True{}: Qt.Action.fail(Unit, 42, "Cleanup handler failed")
    case False{}:
      do Qt.Action<Unit>:
        snapshot(value)
        Qt.Fixture.hit()

def install(state: Qt.QStringConverterBase.State, bad: Bool) -> Qt.Action(Unit):
  Qt.QStringConverterBase.State.Cleanup.install(~Bool, ~cleanup, state, bad)

def init(+state: Qt.QStringConverterBase.State) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QStringConverterBase.State.Fields.set_internalState(state, Qt.Int32{7})
    Qt.QStringConverterBase.State.Fields.set_remainingChars(state, Qt.Int64{8, 0})
    Qt.QStringConverterBase.State.Fields.set_invalidChars(state, Qt.Int64{9, 0})

def armed(+state: Qt.QStringConverterBase.State, bad: Bool) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    init(state)
    install(state, bad)

def clear_once(+state: Qt.QStringConverterBase.State) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    armed(state, False{})
    blocked: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QStringConverterBase.State.Fields.set_flags(state, Qt.QStringConverterBase.Flag.UsesIcu()))
    rejected(Unit, 22, blocked)
    Qt.QStringConverterBase.State.clear(state)
    installed: Bool <- Qt.QStringConverterBase.State.Cleanup.installed(state)
    require(Bool.not(installed), "Cleanup did not consume its handler")
    Qt.QStringConverterBase.State.clear(state)
    Qt.QStringConverterBase.State.reset(state)

def reset_once(+state: Qt.QStringConverterBase.State) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    armed(state, False{})
    Qt.QStringConverterBase.State.reset(state)

def moved(+source: Qt.QStringConverterBase.State, +target: Qt.QStringConverterBase.State) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    stale: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QStringConverterBase.State.clear(source))
    rejected(Unit, 116, stale)
    Qt.Fixture.clearOnOtherThread(target)

def move_source(+state: Qt.QStringConverterBase.State) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    armed(state, False{})
    Qt.QStringConverterBase.State.with(Unit, Qt.QStringConverterBase.State.new__QStringConverterBase_State(state), target => moved(state, target))

def assigned(+source: Qt.QStringConverterBase.State, +target: Qt.QStringConverterBase.State) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    armed(source, False{})
    armed(target, False{})
    _result: Qt.QStringConverterBase.State <- Qt.QStringConverterBase.State.op_assign(target, source)
    Qt.Fixture.clearOnOtherThread(target)

def assign_source(source: Qt.QStringConverterBase.State) -> Qt.Action(Unit):
  Qt.QStringConverterBase.State.with(Unit, Qt.QStringConverterBase.State.new(), target => assigned(source, target))

# A replacement that fails to allocate keeps the installed handler.
def replaced(+state: Qt.QStringConverterBase.State) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    armed(state, True{})
    Qt.Fixture.failNext()
    failed: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, install(state, False{}))
    rejected(Unit, 12, failed)
    kept: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QStringConverterBase.State.clear(state))
    rejected(Unit, 42, kept)
    armed(state, True{})
    install(state, False{})
    Qt.QStringConverterBase.State.clear(state)
    armed(state, True{})
    Qt.QStringConverterBase.State.Cleanup.remove(state)
    Qt.QStringConverterBase.State.clear(state)

def foreign(+state: Qt.QStringConverterBase.State) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Fixture.foreign(state)
    result: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, install(state, False{}))
    rejected(Unit, 95, result)
    Qt.QStringConverterBase.State.destroy(state)

def opaque_storage(+state: Qt.QStringConverterBase.State) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Fixture.nonempty(state)
    occupied: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, install(state, False{}))
    rejected(Unit, 95, occupied)
    Qt.QStringConverterBase.State.clear(state)
    Qt.QStringConverterBase.State.Fields.set_flags(state, Qt.QStringConverterBase.Flag.UsesIcu())
    icu: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, install(state, False{}))
    rejected(Unit, 95, icu)
    Qt.QStringConverterBase.State.Fields.set_flags(state, Qt.QStringConverterBase.Flag.Default())

def failed_handler(+state: Qt.QStringConverterBase.State) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    armed(state, True{})
    result: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QStringConverterBase.State.destroy(state))
    rejected(Unit, 42, result)

# Qt clears the state on another thread; the handler runs on the main thread
# while that thread waits.
def other_thread(+state: Qt.QStringConverterBase.State) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    armed(state, False{})
    Qt.Fixture.clearOnOtherThread(state)

def cases() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QStringConverterBase.State.with(Unit, Qt.QStringConverterBase.State.new(), state => clear_once(state))
    Qt.QStringConverterBase.State.with(Unit, Qt.QStringConverterBase.State.new(), state => armed(state, False{}))
    Qt.QStringConverterBase.State.with(Unit, Qt.QStringConverterBase.State.new(), state => reset_once(state))
    Qt.QStringConverterBase.State.with(Unit, Qt.QStringConverterBase.State.new(), state => move_source(state))
    Qt.QStringConverterBase.State.with(Unit, Qt.QStringConverterBase.State.new(), state => assign_source(state))
    Qt.QStringConverterBase.State.with(Unit, Qt.QStringConverterBase.State.new(), state => replaced(state))
    Qt.QStringConverterBase.State.with(Unit, Qt.QStringConverterBase.State.new(), state => foreign(state))
    Qt.QStringConverterBase.State.with(Unit, Qt.QStringConverterBase.State.new(), state => opaque_storage(state))
    Qt.QStringConverterBase.State.with(Unit, Qt.QStringConverterBase.State.new(), state => failed_handler(state))
    Qt.QStringConverterBase.State.with(Unit, Qt.QStringConverterBase.State.new(), state => other_thread(state))
    hits: U32 <- Qt.Fixture.hits()
    foreign_hits: U32 <- Qt.Fixture.foreignHits()
    require(U32.is_eq(hits, 8) && U32.is_eq(foreign_hits, 1), "Native cleanup handler count changed")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    cases()
    holders: U32 <- Qt.Fixture.holders()
    require(U32.is_eq(holders, 0), "Native cleanup holders leaked")
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "State cleanup leaked native handles")
    Qt.Action.lift(Unit, IO.print("QT612_STATE_CLEANUP_OK clear=1 reset=1 destroy=1 moves=1 replace=1 rollback=1 other_thread=1 foreign=1 failure=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
