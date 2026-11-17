import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def recorded(result: Result<&1, &1, U32, Unit>) -> Qt.Action(Unit):
  match result:
    case Done{unit}: Qt.Action.pure(Unit, Unit{})
    case Fail{value}: Qt.Action.fail(Unit, 1, "Cleanup order queue was full")

def record(state: Chan(U32), value: U32) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    result: Result<&1, &1, U32, Unit> <- Qt.Action.lift(Result<&1, &1, U32, Unit>, Chan.send(U32, state, value))
    recorded(result)

def first(state: Chan(U32)) -> Qt.Action(Unit):
  record(state, 1)

def second(state: Chan(U32)) -> Qt.Action(Unit):
  record(state, 2)

def removed(state: Unit) -> Qt.Action(Unit):
  Qt.Action.fail(Unit, 91, "A removed cleanup callback ran")

def ordered(a: Maybe<&1, U32>, b: Maybe<&1, U32>) -> Qt.Action(Unit):
  match a b:
    case Some{2} Some{1}: Qt.Action.pure(Unit, Unit{})
    case _ _: Qt.Action.fail(Unit, 1, "Qt cleanup callbacks ran in the wrong order")

def finish_queue(+state: Chan(U32)) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    a: Maybe<&1, U32> <- Qt.Action.lift(Maybe<&1, U32>, Chan.recv(U32, state))
    b: Maybe<&1, U32> <- Qt.Action.lift(Maybe<&1, U32>, Chan.recv(U32, state))
    ordered(a, b)
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Qt cleanup registrations leaked")
    Qt.Action.lift(Unit, IO.print("QT612_POST_ROUTINES_OK destructor=1 reverse_order=1 remove=1 scoped=1 bend_heap=1 cleanup=1"))

def finish(state: Chan(U32)) -> Qt.Action(Unit):
  finish_queue(state)

def register(+state: Chan(U32)) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    done: Qt.PostRoutine <- Qt.PostRoutine.add(~Chan(U32), ~finish, state)
    a: Qt.PostRoutine <- Qt.PostRoutine.add(~Chan(U32), ~first, state)
    +cancelled: Qt.PostRoutine <- Qt.PostRoutine.add(~Unit, ~removed, Unit{})
    Qt.PostRoutine.remove(cancelled)
    Qt.PostRoutine.with(Unit, Qt.PostRoutine.add(~Unit, ~removed, Unit{}), ignored => Qt.Action.pure(Unit, Unit{}))
    b: Qt.PostRoutine <- Qt.PostRoutine.add(~Chan(U32), ~second, state)
    return Unit{}

def main() -> IO(Unit):
  do IO<Unit>:
    state: Chan(U32) <- Chan.new(U32, 2)
    IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => register(state))))
