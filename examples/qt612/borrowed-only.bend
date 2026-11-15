import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def borrowed_delete(result: Result<&1, &1, U32 & String, Unit>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 1), "Wrong borrowed-only deletion error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Borrowed-only class allowed native deletion")

# The native harness uses Qt's offscreen platform, so this is an isolated
# clipboard. The test never changes the desktop session's clipboard.
def clipboard(+value: Qt.QClipboard) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    original: String <- Qt.QClipboard.text__QClipboard_Mode(value, Qt.QClipboard.Mode.Clipboard())
    Qt.QClipboard.setText__String_QClipboard_Mode(value, "Bend borrowed clipboard 🎵", Qt.QClipboard.Mode.Clipboard())
    text: String <- Qt.QClipboard.text__QClipboard_Mode(value, Qt.QClipboard.Mode.Clipboard())
    require(String.eq(text, "Bend borrowed clipboard 🎵"), "Borrowed native object did not retain its state")
    deletion: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QClipboard.destroy(value))
    borrowed_delete(deletion)
    alias: Qt.QClipboard <- Qt.QGuiApplication.clipboard()
    require(U32.is_eq(Qt.QClipboard.word(value), Qt.QClipboard.word(alias)), "Borrowed-only singleton lost identity")
    Qt.QClipboard.setText__String_QClipboard_Mode(value, original, Qt.QClipboard.Mode.Clipboard())

def input_method(+value: Qt.QInputMethod) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    visible: Bool <- Qt.QInputMethod.isVisible(value)
    deletion: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QInputMethod.destroy(value))
    borrowed_delete(deletion)

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QClipboard.with(Unit, Qt.QGuiApplication.clipboard(), value => clipboard(value))
    Qt.QInputMethod.with(Unit, Qt.QGuiApplication.inputMethod(), value => input_method(value))
    location: String <- Qt.QStandardPaths.writableLocation(Qt.QStandardPaths.StandardLocation.TempLocation())
    require(Bool.not(String.eq(location, "")), "Borrow-only static class was unavailable")
    Qt.Action.lift(Unit, IO.print("QT612_BORROWED_ONLY_OK singleton_identity=1 mutable_borrow=1 delete_rejected=1 scoped_release=1 static_api=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
