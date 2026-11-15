import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

# The result is a copy owned by the call; the handler names the probe object.
def result(probe: Qt.QObject, value: Qt.QVariant) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    text: String <- Qt.QVariant.toString(value)
    require(String.eq(text, "42"), "The QWebView JavaScript handler lost its QVariant result")
    Qt.QObject.setObjectName(probe, "answered")

def exercise(+probe: Qt.QObject, +view: Qt.QWebView) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.CallbackProbe.prepareWebView(view)
    Qt.QWebView.runJavaScript(view, "globalThis.bendAnswer = 21")
    Qt.QWebView.runJavaScriptWithHandler(~Qt.QObject, ~result, view, "String(globalThis.bendAnswer * 2)", probe)
    completed: Bool <- Qt.CallbackProbe.awaitObjectName(probe, "answered")
    require(completed, "The QWebView JavaScript handler did not run")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QObject.with(Unit, Qt.QObject.new(), probe => Qt.QWebView.with(Unit, Qt.QWebView.new(), view => exercise(probe, view)))
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "The QWebView handler leaked native objects")
    Qt.Action.lift(Unit, IO.print("QT612_WEBVIEW_CALLBACKS_OK native_window=1 default_callback=1 javascript_result=42 copied_variant=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
