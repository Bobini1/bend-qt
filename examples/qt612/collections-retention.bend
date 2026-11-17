import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def error(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong collection lifetime error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected a collection lifetime error")

def stale(+action: Qt.QAction) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    result: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QAction.text(action))
    error(String, result, 116)

def group_member(+first: Qt.QActionGroup, +second: Qt.QActionGroup, +action: Qt.QAction) -> Qt.Action(Qt.QAction):
  do Qt.Action<Qt.QAction>:
    Qt.QAction.setText(action, "Collection member")
    Qt.QAction.setActionGroup(action, first)
    same: Qt.QAction <- Qt.QActionGroup.addAction__QAction(first, action)
    require(U32.is_eq(Qt.QAction.word(same), Qt.QAction.word(action)), "Idempotent add changed action identity")
    Qt.QAction.setActionGroup(action, second)
    old: List<&2, Qt.QAction> <- Qt.QActionGroup.actions(first)
    require(List.is_empty(&2, Qt.QAction, old), "Changing groups retained old native membership")
    strict: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QAction.destroy(action))
    error(Unit, strict, 16)
    return action

def group_pair(first: Qt.QActionGroup, +second: Qt.QActionGroup) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +action: Qt.QAction <- Qt.QAction.with(Qt.QAction, Qt.QAction.new(), value => group_member(first, second, value))
    text: String <- Qt.QAction.text(action)
    require(String.eq(text, "Collection member"), "Group did not retain scoped action")
    Qt.QActionGroup.removeAction(second, action)
    stale(action)

def group_case(first: Qt.QActionGroup) -> Qt.Action(Unit):
  Qt.QActionGroup.with(Unit, Qt.QActionGroup.new(Qt.QObject{0}), second => group_pair(first, second))

def bulk_member(+widget: Qt.QWidget, +action: Qt.QAction) -> Qt.Action(Qt.QAction):
  do Qt.Action<Qt.QAction>:
    Qt.QAction.setText(action, "Bulk member")
    Qt.QWidget.addActions(widget, action <> action <> Nil{})
    Qt.QWidget.insertActions(widget, Qt.QAction{0}, action <> Nil{})
    return action

def bulk_case(+widget: Qt.QWidget) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +action: Qt.QAction <- Qt.QAction.with(Qt.QAction, Qt.QAction.new(), value => bulk_member(widget, value))
    text: String <- Qt.QAction.text(action)
    require(String.eq(text, "Bulk member"), "Bulk action scope released a retained member")
    Qt.QWidget.removeAction(widget, action)
    stale(action)
    invalid: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QWidget.addActions(widget, Qt.QAction{0} <> Nil{}))
    error(Unit, invalid, 22)

def style_member(+widget: Qt.QWidget, +style: Qt.QProxyStyle) -> Qt.Action(Qt.QProxyStyle):
  do Qt.Action<Qt.QProxyStyle>:
    Qt.QWidget.setStyle(widget, Qt.QProxyStyle.as_QStyle(style))
    Qt.QWidget.setStyleSheet(widget, "QWidget { color: red; }")
    strict: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QProxyStyle.destroy(style))
    error(Unit, strict, 16)
    return style

def style_case(+widget: Qt.QWidget) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +style: Qt.QProxyStyle <- Qt.QProxyStyle.with(Qt.QProxyStyle, Qt.QProxyStyle.new(), value => style_member(widget, value))
    Qt.QProxyStyle.setObjectName(style, "Pinned through stylesheet")
    Qt.QWidget.setStyle(widget, Qt.QStyle{0})
    gone: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QProxyStyle.objectName(style))
    error(String, gone, 116)

def popup_member(+completer: Qt.QCompleter, +view: Qt.QListView) -> Qt.Action(Qt.QListView):
  do Qt.Action<Qt.QListView>:
    Qt.QCompleter.setPopup(completer, Qt.QListView.as_QAbstractItemView(view))
    Qt.QCompleter.setPopup(completer, Qt.QListView.as_QAbstractItemView(view))
    strict: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QListView.destroy(view))
    error(Unit, strict, 1)
    return view

def popup_case(+completer: Qt.QCompleter) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +popup: Qt.QListView <- Qt.QListView.with(Qt.QListView, Qt.QListView.new(), view => popup_member(completer, view))
    Qt.QListView.setObjectName(popup, "Native-owned popup")
    rejected: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QCompleter.setPopup(completer, Qt.QAbstractItemView{0}))
    error(Unit, rejected, 22)
    Qt.QCompleter.destroy(completer)
    gone: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QListView.objectName(popup))
    error(String, gone, 116)

def calendar_member(+edit: Qt.QDateTimeEdit, +calendar: Qt.QCalendarWidget) -> Qt.Action(Qt.QCalendarWidget):
  do Qt.Action<Qt.QCalendarWidget>:
    rejected: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QDateTimeEdit.setCalendarWidget(edit, calendar))
    error(Unit, rejected, 22)
    Qt.QDateTimeEdit.setCalendarPopup(edit, True{})
    Qt.QDateTimeEdit.setCalendarWidget(edit, calendar)
    Qt.QDateTimeEdit.setCalendarWidget(edit, calendar)
    Qt.QDateTimeEdit.setCalendarPopup(edit, False{})
    return calendar

def calendar_case(+edit: Qt.QDateTimeEdit) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +calendar: Qt.QCalendarWidget <- Qt.QCalendarWidget.with(Qt.QCalendarWidget, Qt.QCalendarWidget.new(), value => calendar_member(edit, value))
    Qt.QCalendarWidget.setObjectName(calendar, "Popup disabled but still owned")
    Qt.QDateTimeEdit.destroy(edit)
    gone: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QCalendarWidget.objectName(calendar))
    error(String, gone, 116)

def visual_child(+parent: Qt.QQuickItem, +child: Qt.QQuickItem) -> Qt.Action(Qt.QQuickItem):
  do Qt.Action<Qt.QQuickItem>:
    Qt.QQuickItem.setObjectName(child, "Visual child")
    Qt.QQuickItem.setParentItem(child, parent)
    actual: Qt.QObject <- Qt.QQuickItem.parent(child)
    require(U32.is_eq(Qt.QObject.word(actual), 0), "Visual parenting changed QObject ownership")
    rejected: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QQuickItem.setParentItem(parent, child))
    error(Unit, rejected, 40)
    return child

def visual_case(+parent: Qt.QQuickItem) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +child: Qt.QQuickItem <- Qt.QQuickItem.with(Qt.QQuickItem, Qt.QQuickItem.new(), value => visual_child(parent, value))
    text: String <- Qt.QQuickItem.objectName(child)
    require(String.eq(text, "Visual child"), "Visual parent did not retain its child")
    Qt.QQuickItem.setParentItem(child, Qt.QQuickItem{0})
    gone: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QQuickItem.objectName(child))
    error(String, gone, 116)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QActionGroup.with(Unit, Qt.QActionGroup.new(Qt.QObject{0}), group_case)
    Qt.QWidget.with(Unit, Qt.QWidget.new(), value => bulk_case(value))
    Qt.QWidget.with(Unit, Qt.QWidget.new(), value => style_case(value))
    Qt.QCompleter.with(Unit, Qt.QCompleter.new(), value => popup_case(value))
    Qt.QDateTimeEdit.with(Unit, Qt.QDateTimeEdit.new(), value => calendar_case(value))
    Qt.QQuickItem.with(Unit, Qt.QQuickItem.new(), value => visual_case(value))
    objects: U32 <- Qt.Runtime.liveObjects()
    pins: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(pins, 0), "Collection/native-owner resources leaked")
    Qt.Action.lift(Unit, IO.print("QT612_COLLECTION_RETENTION_OK groups=1 move=1 bulk=1 style=1 popup=1 calendar=1 visual_parent=1 objects=0 pins=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
