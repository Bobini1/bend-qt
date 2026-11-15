import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expected(-A: Type, result: Result<&1, &1, U32 & String, A>, code: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(actual, message)}: require(U32.is_eq(actual, code), message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected HTTP callback failure")

def saved() -> Qt.Property:
  Qt.Property.define("saved", Qt.u32())

def Model() -> Qt.QtObject:
  Qt.QObject.define("HttpCallbackState", [saved()])

def route(state: Unit, request: Qt.QHttpServerRequest) -> Qt.Action(String):
  Qt.Action.pure(String, "route-ok")

def refused(state: Unit, request: Qt.QHttpServerRequest) -> Qt.Action(String):
  Qt.Action.fail(String, 91, "Expected route failure")

def changed_body(state: Qt.QObject, +response: Qt.QHttpServerResponse) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +headers: Qt.QHttpHeaders <- Qt.QHttpServerResponse.headers(response)
    ok: Bool <- Qt.QHttpHeaders.append__String_String(headers, "X-Bend", "yes")
    require(ok, "The after-request callback could not append a header")
    Qt.QHttpServerResponse.setHeaders(response, headers)
    Qt.Property.store(~saved(), state, Qt.QHttpServerResponse.word(response))

def changed(state: Qt.QObject, request: Qt.QHttpServerRequest, response: Qt.QHttpServerResponse) -> Qt.Action(Unit):
  changed_body(state, response)

def refused_after(state: Unit, request: Qt.QHttpServerRequest, response: Qt.QHttpServerResponse) -> Qt.Action(Unit):
  Qt.Action.fail(Unit, 92, "Expected after-request failure")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +server: Qt.QHttpServer <- Qt.QHttpServer.new()
    +instance: Qt.QtObject.Instance(Model()) <- Qt.QtObject.new(~Model())
    +state: Qt.QObject = Qt.QtObject.as_QObject(~Model(), instance)
    ok: Bool <- Qt.QHttpServer.routeWithHandler(~Unit, ~route, server, "/ok", Unit{})
    require(ok, "Qt rejected the HTTP route")
    ok: Bool <- Qt.QHttpServer.routeWithHandler(~Unit, ~refused, server, "/fail", Unit{})
    require(ok, "Qt rejected the failing HTTP route")
    Qt.QHttpServer.addAfterRequestHandlerWithHandler(~Qt.QObject, ~changed, server, state, state)
    ok: Bool <- Qt.CallbackProbe.httpListen(server)
    require(ok, "Qt could not bind its HTTP server")
    text: String <- Qt.CallbackProbe.httpRequest(server, "/ok")
    require(String.eq(text, "route-ok|yes"), "Route output or the native response mutation was lost")
    id: U32 <- Qt.Property.get(~saved(), state)
    expired: Result<&1, &1, U32 & String, Qt.QByteArray> <- Qt.Action.attempt(Qt.QByteArray, Qt.QHttpServerResponse.data(Qt.QHttpServerResponse{id}))
    expected(Qt.QByteArray, expired, 116)
    result: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.CallbackProbe.httpRequest(server, "/fail"))
    expected(String, result, 91)
    Qt.QHttpServer.addAfterRequestHandlerWithHandler(~Unit, ~refused_after, server, state, Unit{})
    result: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.CallbackProbe.httpRequest(server, "/ok"))
    expected(String, result, 92)
    Qt.Action.lift(Unit, IO.print("QT612_HTTP_SERVER_CALLBACKS_OK route=1 response_mutation=1 temporary_response=1 failures=91_92"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.scoped(Unit, checks())))
