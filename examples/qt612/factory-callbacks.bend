import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

# Qt takes ownership of the editor the handler creates and passes it to the
# caller of createEditor.
def create_editor(state: Unit, parent: Qt.QWidget, option: Qt.QStyleOptionViewItem, index: Qt.QModelIndex) -> Qt.Action(Qt.QWidget):
  Qt.QWidget.new()

def create(delegate: Qt.QStyledItemDelegate, option: Qt.QStyleOptionViewItem, index: Qt.QModelIndex) -> Qt.Action(Unit):
  Qt.QWidget.with(Unit, Qt.QStyledItemDelegate.createEditor(delegate, Qt.QWidget{0}, option, index), editor =>
    require(U32.is_ne(Qt.QWidget.word(editor), 0), "The editor handler returned null"))

def delegate(+delegate: Qt.QStyledItemDelegate) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QAbstractItemDelegate.Virtual.createEditor.handle(~Unit, ~create_editor, Qt.QStyledItemDelegate.as_QAbstractItemDelegate(delegate), Unit{})
    Qt.QModelIndex.with(Unit, Qt.QModelIndex.new(), index => Qt.QStyleOptionViewItem.with(Unit, Qt.QStyleOptionViewItem.new(), option => create(delegate, option, index)))

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QStyledItemDelegate.with(Unit, Qt.QStyledItemDelegate.newOverride(), item => delegate(item))
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Editor ownership transfer leaked objects")
    Qt.Action.lift(Unit, IO.print("QT612_FACTORY_CALLBACKS_OK upstream_transfer=1 native_result=1 scoped_cleanup=1 objects=0 connections=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
