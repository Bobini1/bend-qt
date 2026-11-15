import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expect_error(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong parent-retention error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected parent-retention error")

def pins(expected: U32) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    count: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(count, expected), "Unexpected parent-retention count")

def attach_validator(edit: Qt.QLineEdit, +validator: Qt.QIntValidator) -> Qt.Action(Qt.QIntValidator):
  do Qt.Action<Qt.QIntValidator>:
    Qt.QLineEdit.setValidator(edit, Qt.QIntValidator.as_QValidator(validator))
    return validator

def validator_case(+edit: Qt.QLineEdit) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +validator: Qt.QIntValidator <- Qt.QIntValidator.with(Qt.QIntValidator, Qt.QIntValidator.new__Int32_Int32(Qt.Int32{0}, Qt.Int32{9}), value => attach_validator(edit, value))
    Qt.QLineEdit.setText(edit, "12")
    accepted: Bool <- Qt.QLineEdit.hasAcceptableInput(edit)
    require(Bool.not(accepted), "Scoped validator stopped validating")
    busy: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QIntValidator.destroy(validator))
    expect_error(Unit, busy, 16)
    invalid: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QLineEdit.setValidator(edit, Qt.QValidator{Qt.QLineEdit.word(edit)}))
    expect_error(Unit, invalid, 22)
    pins(1)
    Qt.QLineEdit.setValidator(edit, Qt.QValidator{0})
    accepted_now: Bool <- Qt.QLineEdit.hasAcceptableInput(edit)
    require(accepted_now, "Removing validator left validation active")
    stale: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QIntValidator.objectName(validator))
    expect_error(String, stale, 116)
    pins(0)

def attach_menu(button: Qt.QPushButton, +menu: Qt.QMenu) -> Qt.Action(Qt.QMenu):
  do Qt.Action<Qt.QMenu>:
    Qt.QMenu.setTitle(menu, "Retained menu🎵")
    Qt.QPushButton.setMenu(button, menu)
    return menu

def failed_menu(button: Qt.QPushButton, +menu: Qt.QMenu) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    ignored: Qt.QMenu <- attach_menu(button, menu)
    Qt.Action.fail(Unit, 83, "Menu body failed")

def menu_case(+button: Qt.QPushButton) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +old: Qt.QMenu <- Qt.QMenu.with(Qt.QMenu, Qt.QMenu.new(), menu => attach_menu(button, menu))
    title: String <- Qt.QMenu.title(old)
    require(String.eq(title, "Retained menu🎵"), "Menu scope deleted a retained menu")
    parent: Qt.QObject <- Qt.QMenu.parent(old)
    require(U32.is_eq(Qt.QObject.word(parent), 0), "Button unexpectedly owns the menu")
    +current: Qt.QMenu <- Qt.QMenu.new()
    failure: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QMenu.with(Unit, Qt.Action.pure(Qt.QMenu, current), menu => failed_menu(button, menu)))
    expect_error(Unit, failure, 83)
    gone: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QMenu.title(old))
    expect_error(String, gone, 116)
    alias: Qt.QMenu <- Qt.QPushButton.menu(button)
    require(U32.is_eq(Qt.QMenu.word(alias), Qt.QMenu.word(current)), "Failed body lost the newly retained menu")
    Qt.QPushButton.setMenu(button, Qt.QMenu{0})
    gone_current: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QMenu.title(current))
    expect_error(String, gone_current, 116)
    pins(0)

def attach_widget(area: Qt.QScrollArea, +widget: Qt.QWidget) -> Qt.Action(Qt.QWidget):
  do Qt.Action<Qt.QWidget>:
    Qt.QWidget.setObjectName(widget, "Scroll child")
    Qt.QScrollArea.setWidget(area, widget)
    return widget

def taken_widget(+widget: Qt.QWidget) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    parent: Qt.QObject <- Qt.QWidget.parent(widget)
    require(U32.is_eq(Qt.QObject.word(parent), 0), "takeWidget left its native parent")
    Qt.QWidget.destroy(widget)

def scroll_case(+area: Qt.QScrollArea) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +old: Qt.QWidget <- Qt.QWidget.with(Qt.QWidget, Qt.QWidget.new(), widget => attach_widget(area, widget))
    strict: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QWidget.destroy(old))
    expect_error(Unit, strict, 1)
    +current: Qt.QWidget <- Qt.QWidget.with(Qt.QWidget, Qt.QWidget.new(), widget => attach_widget(area, widget))
    gone: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QWidget.objectName(old))
    expect_error(String, gone, 116)
    name: String <- Qt.QWidget.objectName(current)
    require(String.eq(name, "Scroll child"), "Adopted widget did not survive its scope")
    +taken: Qt.QWidget <- Qt.QScrollArea.takeWidget(area)
    require(U32.is_eq(Qt.QWidget.word(taken), Qt.QWidget.word(current)), "takeWidget lost identity")
    pins(0)
    Qt.QWidget.with(Unit, Qt.Action.pure(Qt.QWidget, taken), widget => taken_widget(widget))
    gone_current: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QWidget.objectName(current))
    expect_error(String, gone_current, 116)

def model_ready(+model: Qt.QStringListModel) -> Qt.Action(Unit):
  Qt.QStringListModel.setStringList(model, "First" <> "Second" <> Nil{})

def first_model(+combo: Qt.QComboBox, +completer: Qt.QCompleter, +model: Qt.QStringListModel) -> Qt.Action(Qt.QStringListModel):
  do Qt.Action<Qt.QStringListModel>:
    model_ready(model)
    Qt.QComboBox.setModel(combo, Qt.QStringListModel.as_QAbstractItemModel(model))
    Qt.QCompleter.setModel(completer, Qt.QStringListModel.as_QAbstractItemModel(model))
    Qt.QComboBox.setCompleter(combo, completer)
    return model

def replacement_model(combo: Qt.QComboBox, +model: Qt.QStringListModel) -> Qt.Action(Qt.QStringListModel):
  do Qt.Action<Qt.QStringListModel>:
    model_ready(model)
    # Native Qt also changes the completer's model. The binding must retarget
    # its existing watched edge, not merely remove the old edge.
    Qt.QComboBox.setModel(combo, Qt.QStringListModel.as_QAbstractItemModel(model))
    return model

def retarget_combo(+completer: Qt.QCompleter, +combo: Qt.QComboBox) -> Qt.Action(Qt.QStringListModel):
  do Qt.Action<Qt.QStringListModel>:
    Qt.QComboBox.setEditable(combo, True{})
    old: Qt.QStringListModel <- Qt.QStringListModel.with(Qt.QStringListModel, Qt.QStringListModel.new(), model => first_model(combo, completer, model))
    +current: Qt.QStringListModel <- Qt.QStringListModel.with(Qt.QStringListModel, Qt.QStringListModel.new(), model => replacement_model(combo, model))
    gone: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QStringListModel.objectName(old))
    expect_error(String, gone, 116)
    pins(3)
    Qt.QComboBox.setCompleter(combo, Qt.QCompleter{0})
    return current

def retarget_case(+completer: Qt.QCompleter) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +model: Qt.QStringListModel <- Qt.QComboBox.with(Qt.QStringListModel, Qt.QComboBox.new(), combo => retarget_combo(completer, combo))
    # The combo has died, so only the indirectly retargeted completer edge
    # can keep this model alive now.
    rows: Qt.Int32 <- Qt.QStringListModel.rowCount(model)
    require(U32.is_eq(Qt.Int32.word(rows), 2), "Indirect getter change lost its retained model")
    alias: Qt.QAbstractItemModel <- Qt.QCompleter.model(completer)
    require(U32.is_eq(Qt.QAbstractItemModel.word(alias), Qt.QStringListModel.word(model)), "Completer was not retargeted")
    pins(1)
    Qt.QCompleter.setModel(completer, Qt.QAbstractItemModel{0})
    gone: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QStringListModel.objectName(model))
    expect_error(String, gone, 116)
    pins(0)

def attach_mime(drag: Qt.QDrag, +mime: Qt.QMimeData) -> Qt.Action(Qt.QMimeData):
  do Qt.Action<Qt.QMimeData>:
    Qt.QMimeData.setText(mime, "Native MIME ownership🎵")
    Qt.QDrag.setMimeData(drag, mime)
    return mime

def mime_case(source: Qt.QObject, +drag: Qt.QDrag) -> Qt.Action(Qt.QMimeData):
  do Qt.Action<Qt.QMimeData>:
    parent: Qt.QObject <- Qt.QDrag.parent(drag)
    require(U32.is_eq(Qt.QObject.word(parent), Qt.QObject.word(source)), "QDrag constructor did not establish native parenting")
    +old: Qt.QMimeData <- Qt.QMimeData.with(Qt.QMimeData, Qt.QMimeData.new(), mime => attach_mime(drag, mime))
    # Qt 6.12 owns this MIME data without making it a QObject child.
    native_parent: Qt.QObject <- Qt.QMimeData.parent(old)
    require(U32.is_eq(Qt.QObject.word(native_parent), 0), "MIME fixture does not exercise non-parent ownership")
    strict: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QMimeData.destroy(old))
    expect_error(Unit, strict, 16)
    +current: Qt.QMimeData <- Qt.QMimeData.with(Qt.QMimeData, Qt.QMimeData.new(), mime => attach_mime(drag, mime))
    gone: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QMimeData.text(old))
    expect_error(String, gone, 116)
    text: String <- Qt.QMimeData.text(current)
    require(String.eq(text, "Native MIME ownership🎵"), "MIME scope deleted retained data")
    return current

def drag_source(+source: Qt.QObject) -> Qt.Action(Qt.QMimeData):
  Qt.QDrag.with(Qt.QMimeData, Qt.QDrag.new(source), drag => mime_case(source, drag))

def custom_menu(window: Qt.QMainWindow, +widget: Qt.QWidget) -> Qt.Action(Qt.QWidget):
  do Qt.Action<Qt.QWidget>:
    Qt.QWidget.setObjectName(widget, "Custom menu widget")
    Qt.QMainWindow.setMenuWidget(window, widget)
    return widget

def main_window_case(+window: Qt.QMainWindow) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    before: List<&2, Qt.QObject> <- Qt.QMainWindow.children(window)
    Qt.QMainWindow.setStatusBar(window, Qt.QStatusBar{0})
    after: List<&2, Qt.QObject> <- Qt.QMainWindow.children(window)
    require(U32.is_eq(U32.from_nat(List.length(&2, Qt.QObject, before)), U32.from_nat(List.length(&2, Qt.QObject, after))), "Status-bar observer created a child during null reset")
    Qt.QStatusBar.with(Unit, Qt.QStatusBar.new(), bar => Qt.QMainWindow.setStatusBar(window, bar))
    Qt.QMainWindow.setStatusBar(window, Qt.QStatusBar{0})
    Qt.QMenuBar.with(Unit, Qt.QMenuBar.new(), bar => Qt.QMainWindow.setMenuBar(window, bar))
    +widget: Qt.QWidget <- Qt.QWidget.with(Qt.QWidget, Qt.QWidget.new(), value => custom_menu(window, value))
    # menuBar() creates a QMenuBar and replaces a custom menu widget. A
    # retention observer must use the noncreating menuWidget() accessor.
    Qt.QMainWindow.setWindowTitle(window, "Reconcile without mutating menus")
    current: Qt.QWidget <- Qt.QMainWindow.menuWidget(window)
    require(U32.is_eq(Qt.QWidget.word(current), Qt.QWidget.word(widget)), "Retention observer replaced the custom menu widget")
    name: String <- Qt.QWidget.objectName(widget)
    require(String.eq(name, "Custom menu widget"), "Retention observer destroyed the custom menu widget")

def scene_style(scene: Qt.QGraphicsScene, +style: Qt.QProxyStyle) -> Qt.Action(Qt.QProxyStyle):
  do Qt.Action<Qt.QProxyStyle>:
    Qt.QGraphicsScene.setStyle(scene, Qt.QProxyStyle.as_QStyle(style))
    return style

def scene_style_case(+scene: Qt.QGraphicsScene) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    style: Qt.QProxyStyle <- Qt.QProxyStyle.with(Qt.QProxyStyle, Qt.QProxyStyle.new(), value => scene_style(scene, value))
    Qt.QGraphicsScene.setStyle(scene, Qt.QStyle{0})
    gone: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QProxyStyle.objectName(style))
    expect_error(String, gone, 116)

def proxy_style_case(+style: Qt.QProxyStyle) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    before: Qt.QStyle <- Qt.QProxyStyle.baseStyle(style)
    self_cycle: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QProxyStyle.setBaseStyle(style, Qt.QProxyStyle.as_QStyle(style)))
    expect_error(Unit, self_cycle, 22)
    after: Qt.QStyle <- Qt.QProxyStyle.baseStyle(style)
    require(U32.is_eq(Qt.QStyle.word(before), Qt.QStyle.word(after)), "Rejected proxy-style cycle changed the native base style")
    Qt.QProxyStyle.setBaseStyle(style, Qt.QStyle{0})

def attach_document(edit: Qt.QTextEdit, +document: Qt.QTextDocument) -> Qt.Action(Qt.QTextDocument):
  do Qt.Action<Qt.QTextDocument>:
    Qt.QTextDocument.setPlainText(document, "Retained document🎵")
    Qt.QTextEdit.setDocument(edit, document)
    return document

def document_case(+edit: Qt.QTextEdit) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    old: Qt.QTextDocument <- Qt.QTextDocument.with(Qt.QTextDocument, Qt.QTextDocument.new(), document => attach_document(edit, document))
    text: String <- Qt.QTextEdit.toPlainText(edit)
    require(String.eq(text, "Retained document🎵"), "External document did not survive its scope")
    pins(1)
    Qt.QTextEdit.setDocument(edit, Qt.QTextDocument{0})
    gone: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QTextDocument.toPlainText(old))
    expect_error(String, gone, 116)
    +default_document: Qt.QTextDocument <- Qt.QTextEdit.document(edit)
    parent: Qt.QObject <- Qt.QTextDocument.parent(default_document)
    require(U32.is_ne(Qt.QObject.word(parent), 0), "Default document lost native ownership")
    strict: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QTextDocument.destroy(default_document))
    expect_error(Unit, strict, 1)
    Qt.QTextEdit.setPlainText(edit, "Default document is usable")
    default_text: String <- Qt.QTextEdit.toPlainText(edit)
    require(String.eq(default_text, "Default document is usable"), "Null document reset lost its replacement")
    pins(0)

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QLineEdit.with(Unit, Qt.QLineEdit.new(), edit => validator_case(edit))
    Qt.QPushButton.with(Unit, Qt.QPushButton.new(), button => menu_case(button))
    Qt.QScrollArea.with(Unit, Qt.QScrollArea.new(), area => scroll_case(area))
    Qt.QCompleter.with(Unit, Qt.QCompleter.new(), completer => retarget_case(completer))
    mime: Qt.QMimeData <- Qt.QObject.with(Qt.QMimeData, Qt.QObject.new(), source => drag_source(source))
    gone_mime: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QMimeData.text(mime))
    expect_error(String, gone_mime, 116)
    Qt.QMainWindow.with(Unit, Qt.QMainWindow.new(), window => main_window_case(window))
    Qt.QGraphicsScene.with(Unit, Qt.QGraphicsScene.new(), scene => scene_style_case(scene))
    Qt.QProxyStyle.with(Unit, Qt.QProxyStyle.new(), style => proxy_style_case(style))
    Qt.QTextEdit.with(Unit, Qt.QTextEdit.new(), edit => document_case(edit))
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Parent-retention tests leaked resources")
    pins(0)
    Qt.Action.lift(Unit, IO.print("QT612_RETENTION_PARENT_OK validator=1 menu=1 native_adoption=1 take=1 indirect_retarget=1 nonparent_mime=1 noncreating_observers=1 default_resets=1 document_reset=1 failure=1 objects=0 connections=0 retentions=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
