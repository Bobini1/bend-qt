import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def error(~A: Type, expected: U32, result: Result<&1, &1, U32 & String, A>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong iterator error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Invalid iterator operation succeeded")

def fragment(value: Qt.QTextFragment) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    text: String <- Qt.QTextFragment.text(value)
    require(String.eq(text, "alpha"), "Text fragment changed")

def block_iterator(+value: Qt.QTextBlock.iterator, +document: Qt.QTextDocument) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QTextFragment.with(Unit, Qt.QTextBlock.iterator.fragment(value), item => fragment(item))
    before: Result<&1, &1, U32 & String, Qt.QTextBlock.iterator> <- Qt.Action.attempt(Qt.QTextBlock.iterator, Qt.QTextBlock.iterator.op_decrement(value))
    error(Qt.QTextBlock.iterator, 34, before)
    Qt.QTextBlock.iterator.with(Unit, Qt.QTextBlock.iterator.op_increment(value), copy => Qt.Action.pure(Unit, Unit{}))
    at_end: Bool <- Qt.QTextBlock.iterator.atEnd(value)
    require(at_end, "Increment did not reach end")
    after: Result<&1, &1, U32 & String, Qt.QTextBlock.iterator> <- Qt.Action.attempt(Qt.QTextBlock.iterator, Qt.QTextBlock.iterator.op_increment(value))
    error(Qt.QTextBlock.iterator, 34, after)
    Qt.QTextBlock.iterator.with(Unit, Qt.QTextBlock.iterator.op_decrement(value), copy => Qt.Action.pure(Unit, Unit{}))
    retained: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QTextDocument.destroy(document))
    error(Unit, 16, retained)
    Qt.QTextDocument.setPlainText(document, "replacement")
    stale: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.QTextBlock.iterator.atEnd(value))
    error(Bool, 116, stale)

def block(value: Qt.QTextBlock, document: Qt.QTextDocument) -> Qt.Action(Unit):
  Qt.QTextBlock.iterator.with(Unit, Qt.QTextBlock.begin(value), iterator => block_iterator(iterator, document))

def frame_iterator(+value: Qt.QTextFrame.iterator) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    before: Result<&1, &1, U32 & String, Qt.QTextFrame.iterator> <- Qt.Action.attempt(Qt.QTextFrame.iterator, Qt.QTextFrame.iterator.op_decrement(value))
    error(Qt.QTextFrame.iterator, 34, before)
    Qt.QTextFrame.iterator.with(Unit, Qt.QTextFrame.iterator.op_increment(value), copy => Qt.Action.pure(Unit, Unit{}))
    Qt.QTextFrame.iterator.with(Unit, Qt.QTextFrame.iterator.op_decrement(value), copy => Qt.Action.pure(Unit, Unit{}))

def frame(value: Qt.QTextFrame) -> Qt.Action(Unit):
  Qt.QTextFrame.iterator.with(Unit, Qt.QTextFrame.begin(value), iterator => frame_iterator(iterator))

def suppressed(+block: Qt.QTextBlock, +document: Qt.QTextDocument) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    previous: Bool <- Qt.QObject.blockSignals(Qt.QTextDocument.as_QObject(document), True{})
    Qt.QTextDocument.setPlainText(document, "signals blocked")
    unavailable: Result<&1, &1, U32 & String, Qt.QTextBlock> <- Qt.Action.attempt(Qt.QTextBlock, Qt.QTextDocument.firstBlock(document))
    error(Qt.QTextBlock, 16, unavailable)
    ignored: Bool <- Qt.QObject.blockSignals(Qt.QTextDocument.as_QObject(document), previous)
    stale: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QTextBlock.text(block))
    error(String, 116, stale)

def editing(+cursor: Qt.QTextCursor, +document: Qt.QTextDocument) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QTextCursor.beginEditBlock(cursor)
    Qt.QTextCursor.insertText__String(cursor, "first")
    unavailable: Result<&1, &1, U32 & String, Qt.QTextBlock> <- Qt.Action.attempt(Qt.QTextBlock, Qt.QTextDocument.firstBlock(document))
    error(Qt.QTextBlock, 16, unavailable)
    Qt.QTextCursor.insertText__String(cursor, "second")
    Qt.QTextCursor.endEditBlock(cursor)
    Qt.QTextBlock.with(Unit, Qt.QTextDocument.firstBlock(document), block => Qt.Action.pure(Unit, Unit{}))

def signal_blocker(blocker: Qt.QSignalBlocker, +document: Qt.QTextDocument) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    unavailable: Result<&1, &1, U32 & String, Qt.QTextBlock> <- Qt.Action.attempt(Qt.QTextBlock, Qt.QTextDocument.firstBlock(document))
    error(Qt.QTextBlock, 16, unavailable)
    Qt.QTextDocument.setPlainText(document, "RAII signal suppression")

def document(+value: Qt.QTextDocument) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QTextDocument.setPlainText(value, "alpha\nbeta")
    Qt.QTextFrame.with(Unit, Qt.QTextDocument.rootFrame(value), root => frame(root))
    Qt.QTextBlock.with(Unit, Qt.QTextDocument.firstBlock(value), first => block(first, value))
    Qt.QTextBlock.with(Unit, Qt.QTextDocument.firstBlock(value), first => suppressed(first, value))
    Qt.QTextCursor.with(Unit, Qt.QTextCursor.new__QTextDocument(value), cursor => editing(cursor, value))
    Qt.QSignalBlocker.with(Unit, Qt.QSignalBlocker.new__QObject(Qt.QTextDocument.as_QObject(value)), blocker => signal_blocker(blocker, value))

def default_iterator(value: Qt.QTextBlock.iterator) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    result: Result<&1, &1, U32 & String, Qt.QTextBlock.iterator> <- Qt.Action.attempt(Qt.QTextBlock.iterator, Qt.QTextBlock.iterator.op_increment(value))
    error(Qt.QTextBlock.iterator, 22, result)

def tree_iterator(+iterator: Qt.QTreeWidgetItemIterator, +tree: Qt.QTreeWidget, item: Qt.QTreeWidgetItem) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    current: Qt.QTreeWidgetItem <- Qt.QTreeWidgetItemIterator.op_multiply(iterator)
    require(U32.is_eq(Qt.QTreeWidgetItem.word(current), Qt.QTreeWidgetItem.word(item)), "Tree iterator lost item identity")
    retained: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QTreeWidget.destroy(tree))
    error(Unit, 16, retained)
    Qt.QTreeWidgetItemIterator.with(Unit, Qt.QTreeWidgetItemIterator.op_increment(iterator), copy => Qt.Action.pure(Unit, Unit{}))
    end: Qt.QTreeWidgetItem <- Qt.QTreeWidgetItemIterator.op_multiply(iterator)
    require(U32.is_eq(Qt.QTreeWidgetItem.word(end), 0), "Tree iterator did not reach end")
    Qt.QTreeWidget.clear(tree)

def tree_item(+item: Qt.QTreeWidgetItem, +tree: Qt.QTreeWidget) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QTreeWidget.addTopLevelItem(tree, item)
    Qt.QTreeWidgetItemIterator.with(Unit, Qt.QTreeWidgetItemIterator.new__QTreeWidget_Flags_QTreeWidgetItemIterator__IteratorFlag(tree, Qt.Flags_QTreeWidgetItemIterator__IteratorFlag{0}), iterator => tree_iterator(iterator, tree, item))

def tree(value: Qt.QTreeWidget) -> Qt.Action(Unit):
  Qt.QTreeWidgetItem.with(Unit, Qt.QTreeWidgetItem.new(), item => tree_item(item, value))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QTextBlock.iterator.with(Unit, Qt.QTextBlock.iterator.new(), value => default_iterator(value))
    Qt.QTextDocument.with(Unit, Qt.QTextDocument.new(), value => document(value))
    Qt.QTreeWidget.with(Unit, Qt.QTreeWidget.new(), value => tree(value))
    objects: U32 <- Qt.Runtime.liveObjects()
    pins: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(pins, 0), "Iterator origins leaked handles or pins")
    Qt.Action.lift(Unit, IO.print("QT612_ITERATORS_OK fragments=1 bounds=1 default=1 mutation=1 edit_blocks=1 signal_suppression=1 document_retained=1 tree_identity=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
