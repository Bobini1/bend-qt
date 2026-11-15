import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expect_error(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong ownership error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected checked ownership error")

def give_child(parent: Qt.QObject, +child: Qt.QObject) -> Qt.Action(Qt.QObject):
  do Qt.Action<Qt.QObject>:
    Qt.QObject.setObjectName(child, "Transferred🎵")
    Qt.QObject.setParent(child, parent)
    strict: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QObject.destroy(child))
    expect_error(Unit, strict, 1)
    return child

def parent_case(+parent: Qt.QObject) -> Qt.Action(Qt.QObject):
  do Qt.Action<Qt.QObject>:
    +child: Qt.QObject <- Qt.QObject.with(Qt.QObject, Qt.QObject.new(), value => give_child(parent, value))
    text: String <- Qt.QObject.objectName(child)
    require(String.eq(text, "Transferred🎵"), "Inner scope deleted a transferred child")
    alias: Qt.QObject <- Qt.QObject.parent(child)
    require(U32.is_eq(Qt.QObject.word(alias), Qt.QObject.word(parent)), "Parent identity changed")
    cycle: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QObject.setParent(parent, child))
    expect_error(Unit, cycle, 22)
    self_cycle: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QObject.setParent(parent, parent))
    expect_error(Unit, self_cycle, 22)
    root: Qt.QObject <- Qt.QObject.parent(parent)
    unchanged: Qt.QObject <- Qt.QObject.parent(child)
    require(U32.is_eq(Qt.QObject.word(root), 0) && U32.is_eq(Qt.QObject.word(unchanged), Qt.QObject.word(parent)), "Rejected cycle changed the native tree")
    return child

def detached_parent(+parent: Qt.QObject) -> Qt.Action(Qt.QObject):
  do Qt.Action<Qt.QObject>:
    +child: Qt.QObject <- Qt.QObject.with(Qt.QObject, Qt.QObject.new(), value => give_child(parent, value))
    Qt.QObject.setParent(child, Qt.QObject{0})
    owner: Qt.QObject <- Qt.QObject.parent(child)
    require(U32.is_eq(Qt.QObject.word(owner), 0), "Child was not detached")
    return child

def detached_child(+child: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    text: String <- Qt.QObject.objectName(child)
    require(String.eq(text, "Transferred🎵"), "Parent destruction deleted detached child")
    Qt.QObject.destroy(child)

def born_child(+parent: Qt.QObject, +child: Qt.QObject) -> Qt.Action(Qt.QObject):
  do Qt.Action<Qt.QObject>:
    # A constructor parent already owns the child; an unchanged parent must
    # neither acquire a second ownership claim nor restore Bend ownership.
    initial: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QObject.destroy(child))
    expect_error(Unit, initial, 1)
    Qt.QObject.setParent(child, parent)
    unchanged: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QObject.destroy(child))
    expect_error(Unit, unchanged, 1)
    return child

def constructor_parent(+parent: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +child: Qt.QObject <- Qt.QObject.with(Qt.QObject, Qt.QObject.new__QObject(parent), value => born_child(parent, value))
    Qt.QObject.setObjectName(child, "Constructor-owned child")
    Qt.QObject.setParent(child, Qt.QObject{0})
    Qt.QObject.destroy(child)

def fail_after_transfer(parent: Qt.QObject, child: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QObject.setParent(child, parent)
    Qt.Action.fail(Unit, 39, "Body failed after ownership transfer")

def failed_parent(+parent: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +child: Qt.QObject <- Qt.QObject.new()
    failure: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QObject.with(Unit, Qt.Action.pure(Qt.QObject, child), value => fail_after_transfer(parent, value)))
    expect_error(Unit, failure, 39)
    Qt.QObject.setObjectName(child, "Still alive after failed body")
    text: String <- Qt.QObject.objectName(child)
    require(String.eq(text, "Still alive after failed body"), "Failure cleanup deleted transferred object")

def give_widget(window: Qt.QMainWindow, +widget: Qt.QWidget) -> Qt.Action(Qt.QWidget):
  do Qt.Action<Qt.QWidget>:
    Qt.QWidget.setObjectName(widget, "Central🎵")
    Qt.QMainWindow.setCentralWidget(window, widget)
    strict: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QWidget.destroy(widget))
    expect_error(Unit, strict, 1)
    return widget

def central_taken(+taken: Qt.QWidget) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    owner: Qt.QObject <- Qt.QWidget.parent(taken)
    require(U32.is_eq(Qt.QObject.word(owner), 0), "takeCentralWidget left a native parent")
    Qt.QWidget.destroy(taken)

def main_window(+window: Qt.QMainWindow) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +child: Qt.QWidget <- Qt.QWidget.with(Qt.QWidget, Qt.QWidget.new(), value => give_widget(window, value))
    alias: Qt.QWidget <- Qt.QMainWindow.centralWidget(window)
    require(U32.is_eq(Qt.QWidget.word(alias), Qt.QWidget.word(child)), "Central widget identity was lost")
    +taken: Qt.QWidget <- Qt.QMainWindow.takeCentralWidget(window)
    require(U32.is_eq(Qt.QWidget.word(taken), Qt.QWidget.word(child)), "Taking widget changed its handle")
    Qt.QWidget.with(Unit, Qt.Action.pure(Qt.QWidget, taken), value => central_taken(value))
    empty: Qt.QWidget <- Qt.QMainWindow.centralWidget(window)
    require(U32.is_eq(Qt.QWidget.word(empty), 0), "Central widget was not removed")
    stale: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QWidget.objectName(child))
    expect_error(String, stale, 116)

def preparented_window(+window: Qt.QMainWindow) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +child: Qt.QWidget <- Qt.QWidget.with(Qt.QWidget, Qt.QWidget.new__QWidget(Qt.QMainWindow.as_QWidget(window)), value => give_widget(window, value))
    text: String <- Qt.QWidget.objectName(child)
    require(String.eq(text, "Central🎵"), "Adopting a preparented central widget restored scope ownership")
    +taken: Qt.QWidget <- Qt.QMainWindow.takeCentralWidget(window)
    require(U32.is_eq(Qt.QWidget.word(taken), Qt.QWidget.word(child)), "Preparented take lost identity")
    Qt.QWidget.with(Unit, Qt.Action.pure(Qt.QWidget, taken), value => central_taken(value))

def give_jar(manager: Qt.QNetworkAccessManager, +jar: Qt.QNetworkCookieJar) -> Qt.Action(Qt.QNetworkCookieJar):
  do Qt.Action<Qt.QNetworkCookieJar>:
    Qt.QNetworkCookieJar.setObjectName(jar, "Cookie jar🎵")
    Qt.QNetworkAccessManager.setCookieJar(manager, jar)
    strict: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QNetworkCookieJar.destroy(jar))
    expect_error(Unit, strict, 1)
    return jar

def manager_case(+manager: Qt.QNetworkAccessManager) -> Qt.Action(Qt.QNetworkCookieJar):
  do Qt.Action<Qt.QNetworkCookieJar>:
    +jar: Qt.QNetworkCookieJar <- Qt.QNetworkCookieJar.with(Qt.QNetworkCookieJar, Qt.QNetworkCookieJar.new(), value => give_jar(manager, value))
    alias: Qt.QNetworkCookieJar <- Qt.QNetworkAccessManager.cookieJar(manager)
    text: String <- Qt.QNetworkCookieJar.objectName(jar)
    require(U32.is_eq(Qt.QNetworkCookieJar.word(alias), Qt.QNetworkCookieJar.word(jar)) && String.eq(text, "Cookie jar🎵"), "Explicit C++ transfer did not survive inner scope")
    return jar

def editor_option(parent: Qt.QWidget, index: Qt.QModelIndex, delegate: Qt.QItemDelegate, option: Qt.QStyleOptionViewItem) -> Qt.Action(Qt.QWidget):
  Qt.QItemDelegate.createEditor(delegate, parent, option, index)

def editor_delegate(parent: Qt.QWidget, index: Qt.QModelIndex, delegate: Qt.QItemDelegate) -> Qt.Action(Qt.QWidget):
  Qt.QStyleOptionViewItem.with(Qt.QWidget, Qt.QStyleOptionViewItem.new(), option => editor_option(parent, index, delegate, option))

def editor_value(model: Qt.QStandardItemModel, index: Qt.QModelIndex, value: Qt.QVariant) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    accepted: Bool <- Qt.QStandardItemModel.setData__QModelIndex_QVariant(model, index, value)
    require(accepted, "Could not initialize editor model")

def editor_index(parent: Qt.QWidget, model: Qt.QStandardItemModel, +index: Qt.QModelIndex) -> Qt.Action(Qt.QWidget):
  do Qt.Action<Qt.QWidget>:
    Qt.QVariant.with(Unit, Qt.QVariant.fromString("Editor text"), value => editor_value(model, index, value))
    editor: Qt.QWidget <- Qt.QItemDelegate.with(Qt.QWidget, Qt.QItemDelegate.new(), delegate => editor_delegate(parent, index, delegate))
    return editor

def editor_model(parent: Qt.QWidget, +model: Qt.QStandardItemModel) -> Qt.Action(Qt.QWidget):
  Qt.QModelIndex.with(Qt.QWidget, Qt.QStandardItemModel.index__Int32_Int32(model, Qt.Int32{0}, Qt.Int32{0}), index => editor_index(parent, model, index))

def create_editor(parent: Qt.QWidget) -> Qt.Action(Qt.QWidget):
  Qt.QStandardItemModel.with(Qt.QWidget, Qt.QStandardItemModel.new__Int32_Int32(Qt.Int32{1}, Qt.Int32{1}), model => editor_model(parent, model))

def parented_editor(+editor: Qt.QWidget) -> Qt.Action(Qt.QWidget):
  do Qt.Action<Qt.QWidget>:
    require(U32.is_ne(Qt.QWidget.word(editor), 0), "Native delegate did not create an editor")
    strict: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QWidget.destroy(editor))
    expect_error(Unit, strict, 1)
    return editor

def delegate_parent(+parent: Qt.QWidget) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +editor: Qt.QWidget <- Qt.QWidget.with(Qt.QWidget, create_editor(parent), value => parented_editor(value))
    Qt.QWidget.setObjectName(editor, "Native factory child")
    # PySide's virtual-factory argument policy must not steal this parent.
    Qt.QWidget.destroy(parent)
    stale: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QWidget.objectName(editor))
    expect_error(String, stale, 116)

def unparented_editor(+editor: Qt.QWidget) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    require(U32.is_ne(Qt.QWidget.word(editor), 0), "Native factory returned no standalone editor")
    owner: Qt.QObject <- Qt.QWidget.parent(editor)
    require(U32.is_eq(Qt.QObject.word(owner), 0), "Standalone editor acquired an unexpected parent")
    Qt.QWidget.destroy(editor)

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    child: Qt.QObject <- Qt.QObject.with(Qt.QObject, Qt.QObject.new(), parent => parent_case(parent))
    stale: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QObject.objectName(child))
    expect_error(String, stale, 116)
    detached: Qt.QObject <- Qt.QObject.with(Qt.QObject, Qt.QObject.new(), parent => detached_parent(parent))
    Qt.QObject.with(Unit, Qt.Action.pure(Qt.QObject, detached), child => detached_child(child))
    Qt.QObject.with(Unit, Qt.QObject.new(), parent => constructor_parent(parent))
    Qt.QObject.with(Unit, Qt.QObject.new(), parent => failed_parent(parent))
    Qt.QMainWindow.with(Unit, Qt.QMainWindow.new(), window => main_window(window))
    Qt.QMainWindow.with(Unit, Qt.QMainWindow.new(), window => preparented_window(window))
    jar: Qt.QNetworkCookieJar <- Qt.QNetworkAccessManager.with(Qt.QNetworkCookieJar, Qt.QNetworkAccessManager.new(), manager => manager_case(manager))
    stale_jar: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QNetworkCookieJar.objectName(jar))
    expect_error(String, stale_jar, 116)
    Qt.QWidget.with(Unit, Qt.QWidget.new(), parent => delegate_parent(parent))
    Qt.QWidget.with(Unit, create_editor(Qt.QWidget{0}), editor => unparented_editor(editor))
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Ownership scopes leaked resources")
    Qt.Action.lift(Unit, IO.print("QT612_OWNERSHIP_OK transfer=1 detach=1 cycles=1 take=1 failure_cleanup=1 native_owner=1 objects=0 connections=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
