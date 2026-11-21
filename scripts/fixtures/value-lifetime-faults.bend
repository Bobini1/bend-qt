import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def error(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong injected failure: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected injected allocation failure")

def assignment(+receiver: Qt.QTextBlock, +source: Qt.QTextBlock, +old: Qt.QTextDocument, +fresh: Qt.QTextDocument) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Test.failNextGuardAssignment()
    failed: Result<&1, &1, U32 & String, Qt.QTextBlock> <- Qt.Action.attempt(Qt.QTextBlock, Qt.QTextBlock.op_assign(receiver, source))
    error(Qt.QTextBlock, failed, 12)
    stale: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QTextBlock.text(receiver))
    error(String, stale, 116)
    text: String <- Qt.QTextBlock.text(source)
    require(String.eq(text, "fresh"), "Failure damaged the assignment source")
    first: String <- Qt.QTextDocument.toPlainText(old)
    second: String <- Qt.QTextDocument.toPlainText(fresh)
    require(String.eq(first, "old") && String.eq(second, "fresh"), "Failure damaged a source document")
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 3), "Failed assignment leaked its returned value copy")

def documents(+old: Qt.QTextDocument, +fresh: Qt.QTextDocument) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QTextDocument.setPlainText(old, "old")
    Qt.QTextDocument.setPlainText(fresh, "fresh")
    Qt.QTextBlock.with(Unit, Qt.QTextDocument.firstBlock(old), receiver =>
      Qt.QTextBlock.with(Unit, Qt.QTextDocument.firstBlock(fresh), source => assignment(receiver, source, old, fresh)))

def native_tree_deletion(+tree: Qt.QTreeWidget, +iterator: Qt.QTreeWidgetItemIterator) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    model_alive: Bool <- Qt.Test.deleteTree(tree, iterator)
    require(model_alive, "Iterator cleanup ran after its native tree model died")
    stale: Result<&1, &1, U32 & String, Qt.QTreeWidgetItem> <- Qt.Action.attempt(Qt.QTreeWidgetItem, Qt.QTreeWidgetItemIterator.op_multiply(iterator))
    error(Qt.QTreeWidgetItem, stale, 116)

def tree(+value: Qt.QTreeWidget) -> Qt.Action(Unit):
  Qt.QTreeWidgetItemIterator.with(Unit, Qt.QTreeWidgetItemIterator.new__QTreeWidget_QTreeWidgetItemIterator_IteratorFlag(value, Qt.QTreeWidgetItemIterator.IteratorFlag.All()), iterator => native_tree_deletion(value, iterator))

def native_document_deletion(+document: Qt.QTextDocument, +block: Qt.QTextBlock, +iterator: Qt.QTextBlock.iterator) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Test.deleteDocument(document)
    stale_block: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QTextBlock.text(block))
    error(String, stale_block, 116)
    stale_iterator: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.QTextBlock.iterator.atEnd(iterator))
    error(Bool, stale_iterator, 116)

def document_block(document: Qt.QTextDocument, +block: Qt.QTextBlock) -> Qt.Action(Unit):
  Qt.QTextBlock.iterator.with(Unit, Qt.QTextBlock.begin(block), iterator => native_document_deletion(document, block, iterator))

def document(+value: Qt.QTextDocument) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QTextDocument.setPlainText(value, "native deletion")
    Qt.QTextBlock.with(Unit, Qt.QTextDocument.firstBlock(value), block => document_block(value, block))

def destroyed_guard(document: Qt.QTextDocument, +blocker: Qt.QSignalBlocker) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Test.deleteDocument(document)
    # The native destroyed hook dismisses the blocker before its referent dies.
    Qt.QSignalBlocker.unblock(blocker)
    Qt.QSignalBlocker.reblock(blocker)
    Qt.QSignalBlocker.dismiss(blocker)

def guarded_document(+value: Qt.QTextDocument) -> Qt.Action(Unit):
  Qt.QSignalBlocker.with(Unit, Qt.QSignalBlocker.new__QObject(Qt.QTextDocument.as_QObject(value)), blocker => destroyed_guard(value, blocker))

def registration(stage: U32, derived: Bool) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    failed: Result<&1, &1, U32 & String, Qt.QObject> <- Qt.Action.attempt(Qt.QObject, Qt.Test.failQObjectRegistration(stage, derived))
    error(Qt.QObject, failed, 12)
    clean: Bool <- Qt.Test.registrationRolledBack()
    require(clean, "QObject registration did not destroy exactly once or retained a dead pointer/token")
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Failed QObject registration left a live registry entry")

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    post: Bool <- Qt.Test.collectionScheduling(1)
    require(post, "Collection posting failure interrupted invalidation or prevented retry")
    refused: Bool <- Qt.Test.collectionScheduling(2)
    require(refused, "Refused collection event prevented retry")
    work: Bool <- Qt.Test.collectionScheduling(3)
    require(work, "Failed collection callback escaped Qt or prevented retry")
    registration(1, False{})
    registration(2, False{})
    registration(3, False{})
    registration(1, True{})
    registration(2, True{})
    registration(3, True{})
    Qt.QTextDocument.with(Unit, Qt.QTextDocument.new(), old =>
      Qt.QTextDocument.with(Unit, Qt.QTextDocument.new(), fresh => documents(old, fresh)))
    Qt.QTreeWidget.with(Unit, Qt.QTreeWidget.new(), value => tree(value))
    Qt.QTextDocument.with(Unit, Qt.QTextDocument.new(), value => document(value))
    Qt.QTextDocument.with(Unit, Qt.QTextDocument.new(), value => guarded_document(value))
    Qt.Test.failNextOwnedFinalization()
    allocation: Result<&1, &1, U32 & String, Qt.QSize> <- Qt.Action.attempt(Qt.QSize, Qt.QSize.new())
    error(Qt.QSize, allocation, 12)
    objects: U32 <- Qt.Runtime.liveObjects()
    pins: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(pins, 0), "Fault cleanup leaked native resources")
    # Leave the borrowed application identity registered through host teardown.
    # Its destroyed observer must still invalidate after the host stops work.
    application: Qt.QCoreApplication <- Qt.QCoreApplication.instance()
    require(U32.is_ne(Qt.QCoreApplication.word(application), 0), "No application identity")
    Qt.Action.lift(Unit, IO.print("QT612_VALUE_LIFETIME_FAULTS_OK qobject_registration_faults=6 exactly_one_destructor=1 no_dead_registration=1 assigned_stale=1 source_valid=1 result_copy_cleanup=1 native_tree_delete=1 model_alive_during_iterator_cleanup=1 native_document_delete=1 native_blocker_referent_delete=1 owned_finalization_rollback=1 host_teardown=1 objects=0 pins=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
