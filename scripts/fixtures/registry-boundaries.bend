import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def retention() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +view: Qt.QTableView <- Qt.QTableView.new()
    +first: Qt.QStyledItemDelegate <- Qt.QStyledItemDelegate.new()
    +fresh: Qt.QStyledItemDelegate <- Qt.QStyledItemDelegate.new()
    Qt.QTableView.setItemDelegateForRow(view, Qt.Int32{0}, Qt.QStyledItemDelegate.as_QAbstractItemDelegate(first))
    full: Bool <- Qt.CallbackProbe.retentionAtLimit(view, fresh)
    require(full, "The full retention admission checks failed")
    current: Qt.QAbstractItemDelegate <- Qt.QTableView.itemDelegateForRow(view, Qt.Int32{0})
    require(U32.is_eq(Qt.QAbstractItemDelegate.word(current), Qt.QStyledItemDelegate.word(fresh)), "Replacement at full capacity changed identity")

def consume(urls: List<&2, Qt.QUrl>) -> Qt.Action(Unit):
  match urls:
    case first <> second <> Nil{}: Qt.Action.pure(Unit, Unit{})
    case _: Qt.Action.fail(Unit, 1, "The rollback source needs two URL copies")

def outputs() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +mime: Qt.QMimeData <- Qt.QMimeData.new()
    +url: Qt.QUrl <- Qt.QUrl.new__String_QUrl_ParsingMode("https://example.org/limit", Qt.QUrl.ParsingMode.TolerantMode())
    Qt.QMimeData.setUrls(mime, [url, url])
    Qt.List_QUrl.with(Unit, Qt.QMimeData.urls(mime), consume)
    rolled_back: Bool <- Qt.CallbackProbe.outputRollbackAtLimit(mime)
    require(rolled_back, "Partial output leaked at the handle limit")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, retention())
    Qt.scoped(Unit, outputs())
    objects: U32 <- Qt.Runtime.liveObjects()
    retentions: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(retentions, 0), "Registry boundary checks leaked")
    Qt.Action.lift(Unit, IO.print("QT612_REGISTRY_BOUNDARIES_OK full_retention=1 replacement=1 partial_output_rollback=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
