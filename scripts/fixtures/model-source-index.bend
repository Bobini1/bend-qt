import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def rejected(result: Result<&1, &1, U32 & String, Qt.QModelIndex>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 22), "Wrong source identity error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "A foreign internal data pointer reached the source model")

def exercise() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +source: Qt.QStandardItemModel <- Qt.QStandardItemModel.new__Int32_Int32(Qt.Int32{1}, Qt.Int32{1})
    +foreign: Qt.QStandardItemModel <- Qt.QStandardItemModel.new__Int32_Int32(Qt.Int32{1}, Qt.Int32{1})
    +proxy: Qt.QIdentityProxyModel <- Qt.QIdentityProxyModel.new()
    +base: Qt.QAbstractProxyModel = Qt.QIdentityProxyModel.as_QAbstractProxyModel(proxy)
    Qt.QIdentityProxyModel.setSourceModel(proxy, Qt.QStandardItemModel.as_QAbstractItemModel(source))
    +index: Qt.QModelIndex <- Qt.QStandardItemModel.index__Int32_Int32(source, Qt.Int32{0}, Qt.Int32{0})
    +identity: Qt.ModelData <- Qt.QModelIndex.internalPointer(index)
    +restored: Qt.QModelIndex <- Qt.QAbstractProxyModel.createSourceIndex(base, Qt.Int32{0}, Qt.Int32{0}, identity)
    valid: Bool <- Qt.QModelIndex.isValid(restored)
    row: Qt.Int32 <- Qt.QModelIndex.row(restored)
    +owner: Qt.QAbstractItemModel <- Qt.QModelIndex.model(restored)
    require(valid && U32.is_eq(Qt.Int32.word(row), 0) && U32.is_eq(Qt.QAbstractItemModel.word(owner), Qt.QStandardItemModel.word(source)), "The source index changed its native model identity")
    +foreign_index: Qt.QModelIndex <- Qt.QStandardItemModel.index__Int32_Int32(foreign, Qt.Int32{0}, Qt.Int32{0})
    +foreign_identity: Qt.ModelData <- Qt.QModelIndex.internalPointer(foreign_index)
    result: Result<&1, &1, U32 & String, Qt.QModelIndex> <- Qt.Action.attempt(Qt.QModelIndex, Qt.QAbstractProxyModel.createSourceIndex(base, Qt.Int32{0}, Qt.Int32{0}, foreign_identity))
    rejected(result)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, exercise())
    objects: U32 <- Qt.Runtime.liveObjects()
    held: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(held, 0), "Source index identities leaked resources")
    Qt.Action.lift(Unit, IO.print("QT612_MODEL_SOURCE_INDEX_OK native_identity=1 source_model=1 foreign_rejected=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
