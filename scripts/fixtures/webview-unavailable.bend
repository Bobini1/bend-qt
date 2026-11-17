import Base
import ../../packages/qt612/qt.bend as Qt

def rejected(result: Result<&1, &1, U32 & String, Qt.QWebView>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}:
      match code:
        case 95: Qt.Action.pure(Unit, Unit{})
        case _: Qt.Action.fail(Unit, code, message)
    case Done{view}:
      do Qt.Action<Unit>:
        Qt.QWebView.destroy(view)
        Qt.Action.fail(Unit, 1, "QWebView constructed without a runtime backend")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.CallbackProbe.hideWebViewPlugins()
    result: Result<&1, &1, U32 & String, Qt.QWebView> <- Qt.Action.attempt(Qt.QWebView, Qt.QWebView.new())
    rejected(result)
    Qt.Action.lift(Unit, IO.print("QT612_WEBVIEW_UNAVAILABLE_OK checked_error=95 native_abort=0"))

# Qt web modules are set up before the application object, as in C++.
def web_application() -> Qt.Action(Qt.QApplication):
  do Qt.Action<Qt.QApplication>:
    Qt.QtWebView.initialize()
    Qt.QApplication.new()

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, web_application(), application => checks())))
