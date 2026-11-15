import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def denied(result: Result<&1, &1, U32 & String, Unit>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Unexpected URL handler error: " ++ message)
    case Done{unit}: Qt.Action.fail(Unit, 1, "URL handler accepted an invalid operation")

def check_url(actual: Qt.QUrl, expected: Qt.QUrl) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    same: Bool <- Qt.QUrl.op_equal(actual, expected)
    require(same, "URL handler delivered the wrong QUrl")

def opened(+browser: Qt.QTextBrowser, +url: Qt.QUrl) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    accepted: Bool <- Qt.QDesktopServices.openUrl(url)
    require(accepted, "Native URL handler did not invoke its slot")
    Qt.QUrl.with(Unit, Qt.QTextBrowser.source(browser), actual => check_url(actual, url))

def active(+browser: Qt.QTextBrowser) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    busy: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QTextBrowser.destroy(browser))
    denied(busy, 16)
    Qt.QUrl.with(Unit, Qt.QUrl.new__String_QUrl_ParsingMode("bend-test://local/item", Qt.QUrl.ParsingMode.TolerantMode), url => opened(browser, url))

def scoped(+browser: Qt.QTextBrowser) -> Qt.Action(Unit):
  Qt.QDesktopServices.withUrlHandler(Unit, "BEND-TEST", Qt.QTextBrowser.as_QObject(browser), "setSource", active(browser))

def replaced(+first: Qt.QTextBrowser, +second: Qt.QTextBrowser) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QDesktopServices.setUrlHandler("bend-test", Qt.QTextBrowser.as_QObject(first), "setSource")
    Qt.QDesktopServices.setUrlHandler("BEND-TEST", Qt.QTextBrowser.as_QObject(second), "setSource")
    Qt.QTextBrowser.destroy(first)
    active(second)
    Qt.QDesktopServices.unsetUrlHandler("bend-test")

def replacing(+first: Qt.QTextBrowser) -> Qt.Action(Unit):
  Qt.QTextBrowser.with(Unit, Qt.QTextBrowser.new(), second => replaced(first, second))

def invalid(+browser: Qt.QTextBrowser) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    unknown: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QDesktopServices.setUrlHandler("bend-test", Qt.QTextBrowser.as_QObject(browser), "missing"))
    denied(unknown, 22)
    nul: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QDesktopServices.setUrlHandler("bend-test", Qt.QTextBrowser.as_QObject(browser), "setSource\0ignored"))
    denied(nul, 22)

def parent_destroyed(code: U32, identity: Qt.ObjectIdentity) -> Qt.Action(Unit):
  Qt.QCoreApplication.exit__Int32(Qt.Int32{code})

# Closing deletes the window later, inside the event loop.
def close_parent(+parent: Qt.QWidget, connection: Qt.Connection) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QWidget.setAttribute__Qt_WidgetAttribute_Bool(parent, Qt.Qt.WidgetAttribute.WA_DeleteOnClose, True{})
    closed: Bool <- Qt.QWidget.close(parent)
    require(closed, "Native parent window refused to close")
    code: Qt.Int32 <- Qt.QCoreApplication.exec()
    require(U32.is_eq(Qt.Int32.word(code), 4), "Parent destruction did not run its handler")
    pins: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(pins, 0), "Parent destruction left a URL registration alive")

def parented(+parent: Qt.QWidget, child: Qt.QTextBrowser) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QDesktopServices.setUrlHandler("bend-parent", Qt.QTextBrowser.as_QObject(child), "setSource")
    busy: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QWidget.destroy(parent))
    denied(busy, 16)
    Qt.Connection.with(Unit, Qt.QWidget.connect_destroyed(~U32, ~parent_destroyed, parent, 4), connection => close_parent(parent, connection))

def parent(+owner: Qt.QWidget) -> Qt.Action(Unit):
  Qt.QTextBrowser.with(Unit, Qt.QTextBrowser.new__QWidget(owner), child => parented(owner, child))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QTextBrowser.with(Unit, Qt.QTextBrowser.new(), browser => scoped(browser))
    Qt.QTextBrowser.with(Unit, Qt.QTextBrowser.new(), browser => replacing(browser))
    Qt.QTextBrowser.with(Unit, Qt.QTextBrowser.new(), browser => invalid(browser))
    Qt.QWidget.with(Unit, Qt.QWidget.new(), owner => parent(owner))
    objects: U32 <- Qt.Runtime.liveObjects()
    pins: U32 <- Qt.Runtime.liveRetentions()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(pins, 0) && U32.is_eq(connections, 0), "URL registrations leaked handles or pins")
    Qt.Action.lift(Unit, IO.print("QT612_URL_HANDLERS_OK dispatch=1 scope=1 replacement=1 parent_death=1 validation=1 cleanup=1 connections=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
