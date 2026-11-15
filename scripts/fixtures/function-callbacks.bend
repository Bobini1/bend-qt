import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expect_error(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Unexpected error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected the handler failure")

# Each handler names the probe object; the probe waits for that name.
def javascript(probe: Qt.QObject, value: Qt.QVariant) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    text: String <- Qt.QVariant.toString(value)
    require(String.eq(text, "42"), "Wrong JavaScript result")
    Qt.QObject.setObjectName(probe, "javascript")

def html(probe: Qt.QObject, value: String) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    require(Bool.not(String.eq(value, "")), "Empty HTML result")
    Qt.QObject.setObjectName(probe, "html")

def refused_html(code: U32, value: String) -> Qt.Action(Unit):
  Qt.Action.fail(Unit, code, "Intentional handler failure")

def named(probe: Qt.QObject, name: String, found: Bool) -> Qt.Action(Bool):
  match found:
    case True{}:
      do Qt.Action<Bool>:
        Qt.QObject.setObjectName(probe, name)
        return True{}
    case False{}: Qt.Action.pure(Bool, False{})

def matched(probe: Qt.QObject, +name: String) -> Qt.Action(Bool):
  named(probe, name, String.eq(name, "bend-source"))

# Qt copies its QStringView arguments for the filter.
def filter(probe: Qt.QObject, name: String, kind: String) -> Qt.Action(Bool):
  matched(probe, name)

def await_name(probe: Qt.QObject, name: String, message: String) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    found: Bool <- Qt.CallbackProbe.awaitObjectName(probe, name)
    require(found, message)

# A stored function that fails fails the Qt call during which Qt ran it.
def page_demo(+probe: Qt.QObject, +page: Qt.QWebEnginePage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.CallbackProbe.loadPage(page)
    Qt.QWebEnginePage.runJavaScriptWithHandler__String(~Qt.QObject, ~javascript, page, "String(21 * 2)", probe)
    await_name(probe, "javascript", "The JavaScript handler did not run")
    Qt.QWebEnginePage.toHtmlWithHandler(~Qt.QObject, ~html, page, probe)
    await_name(probe, "html", "The HTML handler did not run")
    Qt.QWebEnginePage.toHtmlWithHandler(~U32, ~refused_html, page, 44)
    failed: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.CallbackProbe.awaitObjectName(probe, "unused"))
    expect_error(Bool, failed, 44)

def proxied(proxy: Qt.QRemoteObjectHostBase, +probe: Qt.QObject, registry: Qt.QUrl, host: Qt.QUrl) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    accepted: Bool <- Qt.QRemoteObjectHostBase.proxyWithHandler(~Qt.QObject, ~filter, proxy, registry, host, probe)
    require(accepted, "The proxy host refused the registry")
    await_name(probe, "bend-source", "The Remote Objects proxy did not run the Bend filter")

def remote(+probe: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +proxy: Qt.QRemoteObjectHostBase <- Qt.CallbackProbe.startRemote()
    +url: String <- Qt.CallbackProbe.remoteRegistry()
    Qt.QUrl.with(Unit, Qt.QUrl.new__String(url), registry => Qt.QUrl.with(Unit, Qt.QUrl.new(), host => proxied(proxy, probe, registry, host)))
    Qt.CallbackProbe.stopRemote()

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QObject.with(Unit, Qt.QObject.new(), probe => Qt.QWebEnginePage.with(Unit, Qt.QWebEnginePage.new(), value => page_demo(probe, value)))
    Qt.QObject.with(Unit, Qt.QObject.new(), probe => remote(probe))
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Function handlers leaked native handles")
    Qt.Action.lift(Unit, IO.print("QT612_FUNCTION_CALLBACKS_OK javascript=1 html=1 native_remote_filter=1 string_view_copy=1 handler_error=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
