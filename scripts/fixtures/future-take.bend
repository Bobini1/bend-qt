import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def error(~A: Type, expected: U32, value: Result<&1, &1, U32 & String, A>) -> Qt.Action(Unit):
  match value:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong future take error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Invalid future take succeeded")

def bytes(value: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    text: String <- Qt.QByteArray.utf8(value)
    require(String.eq(text, "first"), "Future did not move its first response")

def response(value: Qt.QHttpServerResponse) -> Qt.Action(Unit):
  Qt.QByteArray.with(Unit, Qt.QHttpServerResponse.data(value), bytes)

def watched(+original: Qt.Future_QHttpServerResponse, +clone: Qt.Future_QHttpServerResponse, +watcher: Qt.FutureWatcher_QHttpServerResponse, +alias: Qt.Future_QHttpServerResponse) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QHttpServerResponse.with(Unit, Qt.Future_QHttpServerResponse.takeResult(clone), response)
    valid_original: Bool <- Qt.Future_QHttpServerResponse.isValid(original)
    valid_clone: Bool <- Qt.Future_QHttpServerResponse.isValid(clone)
    valid_alias: Bool <- Qt.Future_QHttpServerResponse.isValid(alias)
    require(Bool.not(valid_original || valid_clone || valid_alias), "Taking a result did not invalidate shared aliases")
    count: Qt.Int32 <- Qt.Future_QHttpServerResponse.resultCount(original)
    require(U32.is_eq(Qt.Int32.word(count), 0), "Taking a result did not discard remaining responses")
    repeated: Result<&1, &1, U32 & String, Qt.QHttpServerResponse> <- Qt.Action.attempt(Qt.QHttpServerResponse, Qt.Future_QHttpServerResponse.takeResult(original))
    error(Qt.QHttpServerResponse, 61, repeated)
    watcher_repeated: Result<&1, &1, U32 & String, Qt.QHttpServerResponse> <- Qt.Action.attempt(Qt.QHttpServerResponse, Qt.Future_QHttpServerResponse.takeResult(alias))
    error(Qt.QHttpServerResponse, 61, watcher_repeated)
    rejected_watch: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.FutureWatcher_QHttpServerResponse.setFuture(watcher, original))
    error(Unit, 61, rejected_watch)

def watcher(+original: Qt.Future_QHttpServerResponse, clone: Qt.Future_QHttpServerResponse, +watcher: Qt.FutureWatcher_QHttpServerResponse) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.FutureWatcher_QHttpServerResponse.setFuture(watcher, original)
    Qt.Future_QHttpServerResponse.with(Unit, Qt.FutureWatcher_QHttpServerResponse.future(watcher), alias => watched(original, clone, watcher, alias))

def cloned(original: Qt.Future_QHttpServerResponse, clone: Qt.Future_QHttpServerResponse) -> Qt.Action(Unit):
  Qt.FutureWatcher_QHttpServerResponse.with(Unit, Qt.FutureWatcher_QHttpServerResponse.new(), value => watcher(original, clone, value))

def aliases(+original: Qt.Future_QHttpServerResponse) -> Qt.Action(Unit):
  Qt.Future_QHttpServerResponse.with(Unit, Qt.Future_QHttpServerResponse.clone(original), value => cloned(original, value))

def pending(+future: Qt.Future_QHttpServerResponse) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    ready: Bool <- Qt.Future_QHttpServerResponse.isResultReadyAt(future, Qt.Int32{0})
    require(ready, "Pending fixture had no first result")
    early: Result<&1, &1, U32 & String, Qt.QHttpServerResponse> <- Qt.Action.attempt(Qt.QHttpServerResponse, Qt.Future_QHttpServerResponse.takeResult(future))
    error(Qt.QHttpServerResponse, 11, early)
    Qt.Future_QHttpServerResponse.await(future)
    Qt.QHttpServerResponse.with(Unit, Qt.Future_QHttpServerResponse.takeResult(future), response)

def failure(expected: U32, future: Qt.Future_QHttpServerResponse) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    result: Result<&1, &1, U32 & String, Qt.QHttpServerResponse> <- Qt.Action.attempt(Qt.QHttpServerResponse, Qt.Future_QHttpServerResponse.takeResult(future))
    error(Qt.QHttpServerResponse, expected, result)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Future_QHttpServerResponse.with(Unit, Qt.Fixture.future(0), value => aliases(value))
    Qt.Future_QHttpServerResponse.with(Unit, Qt.Fixture.future(1), value => pending(value))
    Qt.Future_QHttpServerResponse.with(Unit, Qt.Fixture.future(2), value => failure(61, value))
    Qt.Future_QHttpServerResponse.with(Unit, Qt.Fixture.future(3), value => failure(1, value))
    Qt.Future_QHttpServerResponse.with(Unit, Qt.Future_QHttpServerResponse.fromError("future failure"), value => failure(14, value))
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Future consumption leaked handles or connections")
    Qt.Action.lift(Unit, IO.print("QT612_FUTURE_TAKE_OK move_only=1 shared_aliases=1 watcher_alias=1 repeated_rejected=1 pending_ready_rejected=1 exception=1 readonly=1 objects=0 connections=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
