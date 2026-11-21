import Base
import ../../packages/qt612/qt.bend as Qt

# QUiLoader builds a Qt Designer form natively, so Bend holds no handles to
# its children. Typed child lookup finds them by class and object name, like
# findChild<T *> and findChildren<T *> in C++. Results are borrowed: the form
# still owns its children and destroys them with itself.

def form_xml() -> String:
  "<ui version='4.0'><class>Login</class><widget class='QWidget' name='Login'><layout class='QVBoxLayout' name='layout'><item><widget class='QLineEdit' name='userName'/></item><item><widget class='QLineEdit' name='password'/></item><item><widget class='QLabel' name='status_main'/></item><item><widget class='QLabel' name='status_detail'/></item><item><widget class='QPushButton' name='okButton'><property name='text'><string>Sign in</string></property></widget></item></layout></widget></ui>"

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}:
      Qt.Action.pure(Unit, Unit{})
    case False{}:
      Qt.Action.fail(Unit, 1, message)

def absent(value: Maybe<&2, Qt.QPushButton>, message: String) -> Qt.Action(Unit):
  match value:
    case None{}:
      Qt.Action.pure(Unit, Unit{})
    case Some{button}:
      Qt.Action.fail(Unit, 1, message)

def missing_edit(value: Maybe<&2, Qt.QLineEdit>) -> Qt.Action(Unit):
  match value:
    case None{}:
      Qt.Action.pure(Unit, Unit{})
    case Some{edit}:
      Qt.Action.fail(Unit, 1, "An unknown object name matched a child")

def clicked(probe: Qt.QObject, checked: Bool) -> Qt.Action(Unit):
  match checked:
    case True{}: Qt.QObject.setObjectName(probe, "checked")
    case False{}: Qt.QObject.setObjectName(probe, "unchecked")

def press(+button: Qt.QPushButton, +probe: Qt.QObject, connection: Qt.Connection) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QPushButton.click(button)
    state: String <- Qt.QObject.objectName(probe)
    require(String.eq(state, "unchecked"), "The found button did not report an unchecked click")

def watch_button(+button: Qt.QPushButton, +probe: Qt.QObject) -> Qt.Action(Unit):
  Qt.Connection.with(Unit, Qt.Signal.connect(~Qt.QPushButton.clicked(), ~Qt.QObject, ~clicked, button, probe),
    connection => press(button, probe, connection))

def sign_in(value: Maybe<&2, Qt.QPushButton>) -> Qt.Action(Unit):
  match value:
    case None{}:
      Qt.Action.fail(Unit, 1, "findIn did not find the Designer button")
    case Some{+button}:
      do Qt.Action<Unit>:
        text: String <- Qt.QPushButton.text(button)
        require(String.eq(text, "Sign in"), "The found button is not the Designer button")
        Qt.QObject.with(Unit, Qt.QObject.new(), probe => watch_button(button, probe))

def edits(value: List<&2, Qt.QLineEdit>) -> Qt.Action(Unit):
  match value:
    case Con{+user, Con{+secret, Nil{}}}:
      do Qt.Action<Unit>:
        first: String <- Qt.QLineEdit.objectName(user)
        second: String <- Qt.QLineEdit.objectName(secret)
        require(String.eq(first, "userName") && String.eq(second, "password"), "findAllIn changed the Designer order")
        Qt.QLineEdit.setText(user, "Zażółć 🎵")
        text: String <- Qt.QLineEdit.text(user)
        require(String.eq(text, "Zażółć 🎵"), "A found line edit did not keep its text")
    case _:
      Qt.Action.fail(Unit, 1, "findAllIn did not return exactly the two line edits")

def same_user(value: Maybe<&2, Qt.QLineEdit>) -> Qt.Action(Unit):
  match value:
    case None{}:
      Qt.Action.fail(Unit, 1, "findIn did not find the user name field")
    case Some{user}:
      do Qt.Action<Unit>:
        text: String <- Qt.QLineEdit.text(user)
        require(String.eq(text, "Zażółć 🎵"), "Two lookups returned different line edits")

def labels(pattern: Qt.QRegularExpression, root: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    found: List<&2, Qt.QLabel> <- Qt.QLabel.findAllMatchingIn(root, pattern)
    require(U32.is_eq(U32.from_nat(List.length(&2, Qt.QLabel, found)), 2), "findAllMatchingIn did not apply the pattern")

def search(+root: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    button: Maybe<&2, Qt.QPushButton> <- Qt.QPushButton.findIn(root, "okButton")
    sign_in(button)
    all_edits: List<&2, Qt.QLineEdit> <- Qt.QLineEdit.findAllIn(root, "")
    edits(all_edits)
    user: Maybe<&2, Qt.QLineEdit> <- Qt.QLineEdit.findIn(root, "userName")
    same_user(user)
    wrong_class: Maybe<&2, Qt.QPushButton> <- Qt.QPushButton.findIn(root, "userName")
    absent(wrong_class, "findIn ignored the requested class")
    unknown: Maybe<&2, Qt.QLineEdit> <- Qt.QLineEdit.findIn(root, "noSuchField")
    missing_edit(unknown)
    Qt.QRegularExpression.with(Unit, Qt.QRegularExpression.new__String("^status_"), pattern => labels(pattern, root))
    every: List<&2, Qt.QObject> <- Qt.QObject.findAllIn(root, "")
    # Line edits own internal helper objects, so there can be more than six.
    require(U32.is_gt(U32.from_nat(List.length(&2, Qt.QObject, every)), 5), "QObject.findAllIn did not see the layout and five widgets")

def inspect(form: Qt.QWidget) -> Qt.Action(Unit):
  search(Qt.QWidget.as_QObject(form))

def load(loader: Qt.QUiLoader, buffer: Qt.QBuffer) -> Qt.Action(Unit):
  Qt.QWidget.with(Unit, Qt.QUiLoader.load__QIODevice(loader, Qt.QBuffer.as_QIODevice(buffer)), inspect)

def open_form(+buffer: Qt.QBuffer, xml: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QBuffer.setData__QByteArray(buffer, xml)
    opened: Bool <- Qt.QBuffer.open(buffer, Qt.QIODeviceBase.OpenModeFlag.ReadOnly())
    require(opened, "The form buffer did not open")
    Qt.QUiLoader.with(Unit, Qt.QUiLoader.new(), loader => load(loader, buffer))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromUtf8(form_xml()), xml =>
      Qt.QBuffer.with(Unit, Qt.QBuffer.new(), buffer => open_form(buffer, xml)))
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Found children outlived their form")
    Qt.Action.lift(Unit, IO.print("QT612_CHILD_LOOKUP_OK find=1 find_all=1 pattern=1 class_filter=1 missing=1 borrowed=1 click=1 objects=0 connections=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
