import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expected(-A: Type, result: Result<&1, &1, U32 & String, A>, code: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(+actual, message)}: require(U32.is_eq(actual, code), "Protected lifetime error " ++ U32.show(actual) ++ ": " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Invalid protected lifetime operation succeeded")

def mime_copies() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +rich: Qt.QTextEdit <- Qt.QTextEdit.new()
    +data: Qt.QMimeData <- Qt.QMimeData.new()
    Qt.QMimeData.setHtml(data, "<b>rich copy</b>")
    Qt.QTextEdit.insertFromMimeData(rich, data)
    Qt.QMimeData.destroy(data)
    text: String <- Qt.QTextEdit.toPlainText(rich)
    require(String.eq(text, "rich copy"), "QTextEdit did not copy MIME contents")
    +plain: Qt.QPlainTextEdit <- Qt.QPlainTextEdit.new()
    +data: Qt.QMimeData <- Qt.QMimeData.new()
    Qt.QMimeData.setText(data, "plain copy")
    Qt.QPlainTextEdit.insertFromMimeData(plain, data)
    Qt.QMimeData.destroy(data)
    text: String <- Qt.QPlainTextEdit.toPlainText(plain)
    require(String.eq(text, "plain copy"), "QPlainTextEdit did not copy MIME contents")

def wizard_parent() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +page: Qt.QWizardPage <- Qt.QWizardPage.new()
    absent: Qt.QWizard <- Qt.QWizardPage.wizard(page)
    require(U32.is_eq(Qt.QWizard.word(absent), 0), "A new page already had a wizard")
    +wizard: Qt.QWizard <- Qt.QWizard.new()
    Qt.QWizard.setPage(wizard, Qt.Int32{0}, page)
    actual: Qt.QWizard <- Qt.QWizardPage.wizard(page)
    require(U32.is_eq(Qt.QWizard.word(actual), Qt.QWizard.word(wizard)), "Wizard getter changed parent identity")
    Qt.QWizard.removePage(wizard, Qt.Int32{0})
    actual: Qt.QWizard <- Qt.QWizardPage.wizard(page)
    require(U32.is_eq(Qt.QWizard.word(actual), Qt.QWizard.word(wizard)), "Removing a page changed Qt's retained wizard association")
    Qt.QWizard.destroy(wizard)
    stale: Result<&1, &1, U32 & String, Qt.QWizard> <- Qt.Action.attempt(Qt.QWizard, Qt.QWizardPage.wizard(page))
    expected(Qt.QWizard, stale, 116)

def document_object() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +document: Qt.QTextDocument <- Qt.QTextDocument.new()
    +frame: Qt.QTextFrameFormat <- Qt.QTextFrameFormat.new()
    +format: Qt.QTextFormat <- Qt.QTextFrameFormat.as_QTextFormat(frame)
    +object: Qt.QTextObject <- Qt.QTextDocument.createObject(document, format)
    Qt.QTextFormat.destroy(format)
    Qt.QTextFrameFormat.destroy(frame)
    actual: Qt.QTextDocument <- Qt.QTextObject.document(object)
    require(U32.is_eq(Qt.QTextDocument.word(actual), Qt.QTextDocument.word(document)), "Text object lost its native document")
    parent: Qt.QObject <- Qt.QObject.parent(Qt.QTextObject.as_QObject(object))
    require(U32.is_eq(Qt.QObject.word(parent), Qt.QTextDocument.word(document)), "Text object was not a native document child")
    borrowed: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QTextObject.destroy(object))
    expected(Unit, borrowed, 1)
    Qt.QTextDocument.destroy(document)
    stale: Result<&1, &1, U32 & String, Qt.QTextDocument> <- Qt.Action.attempt(Qt.QTextDocument, Qt.QTextObject.document(object))
    expected(Qt.QTextDocument, stale, 116)

def held_engines(+printing: Qt.QPrintEngine, painting: Qt.QPaintEngine) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QPrintEngine.destroy(printing))
    expected(Unit, held, 16)
    held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QPaintEngine.destroy(painting))
    expected(Unit, held, 16)

def engine_counts(value: U32) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    actual: U32 <- Qt.CallbackProbe.printerEngineDestructions()
    require(U32.is_eq(actual, value), "QPrinter deleted an external engine or engine cleanup was lost")

def printer_replacement() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +fake: Qt.QPaintEngine <- Qt.CallbackProbe.ownedPaintEngine()
    +printer: Qt.QPrinter <- Qt.CallbackProbe.printerWithVirtualPaintEngine(fake)
    +first_print: Qt.QPrintEngine <- Qt.CallbackProbe.ownedPrintEngine()
    +first_paint: Qt.QPaintEngine <- Qt.CallbackProbe.ownedPaintEngine()
    Qt.QPrinter.setEngines(printer, first_print, first_paint)
    good: Bool <- Qt.CallbackProbe.printerNativeEngines(printer, first_print, first_paint, fake)
    require(good, "Native printer storage or virtual override control changed")
    held_engines(first_print, first_paint)
    +second_print: Qt.QPrintEngine <- Qt.CallbackProbe.ownedPrintEngine()
    +second_paint: Qt.QPaintEngine <- Qt.CallbackProbe.ownedPaintEngine()
    Qt.QPrinter.setEngines(printer, second_print, second_paint)
    Qt.QPrintEngine.destroy(first_print)
    Qt.QPaintEngine.destroy(first_paint)
    engine_counts(65537)
    held_engines(second_print, second_paint)
    Qt.QPrinter.destroy(printer)
    engine_counts(65537)
    Qt.QPrintEngine.destroy(second_print)
    Qt.QPaintEngine.destroy(second_paint)
    Qt.QPaintEngine.destroy(fake)
    engine_counts(131075)

def printer_reset() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +printer: Qt.QPrinter <- Qt.QPrinter.new()
    Qt.QPrinter.setOutputFormat(printer, Qt.QPrinter.OutputFormat.PdfFormat())
    +printing: Qt.QPrintEngine <- Qt.CallbackProbe.ownedPrintEngine()
    +painting: Qt.QPaintEngine <- Qt.CallbackProbe.ownedPaintEngine()
    Qt.QPrinter.setEngines(printer, printing, painting)
    Qt.QPrinter.setOutputFormat(printer, Qt.QPrinter.OutputFormat.PdfFormat())
    held_engines(printing, painting)
    Qt.QPrinter.setPdfVersion(printer, Qt.QPagedPaintDevice.PdfVersion.PdfVersion_1_6())
    engine_counts(131075)
    Qt.QPrintEngine.destroy(printing)
    Qt.QPaintEngine.destroy(painting)
    engine_counts(196612)
    Qt.QPrinter.destroy(printer)

def default_printer_engines() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +printer: Qt.QPrinter <- Qt.QPrinter.new()
    Qt.QPrinter.setOutputFormat(printer, Qt.QPrinter.OutputFormat.PdfFormat())
    +printing: Qt.QPrintEngine <- Qt.QPrinter.printEngine(printer)
    +painting: Qt.QPaintEngine <- Qt.QPrinter.paintEngine(printer)
    state: Qt.QPrinter.PrinterState <- Qt.QPrintEngine.printerState(printing)
    require(U32.is_eq(Qt.QPrinter.PrinterState.word(state), Qt.QPrinter.PrinterState.word(Qt.QPrinter.PrinterState.Idle())), "Default printer engine was not usable")
    kind: Qt.QPaintEngine.Type <- Qt.QPaintEngine.type(painting)
    require(U32.is_eq(Qt.QPaintEngine.Type.word(kind), Qt.QPaintEngine.Type.word(Qt.QPaintEngine.Type.Pdf())), "Default printer paint engine was not PDF")
    borrowed: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QPrintEngine.destroy(printing))
    expected(Unit, borrowed, 1)
    Qt.QPrinter.setPdfVersion(printer, Qt.QPagedPaintDevice.PdfVersion.PdfVersion_1_6())
    stale: Result<&1, &1, U32 & String, Qt.QPrinter.PrinterState> <- Qt.Action.attempt(Qt.QPrinter.PrinterState, Qt.QPrintEngine.printerState(printing))
    expected(Qt.QPrinter.PrinterState, stale, 116)
    stale: Result<&1, &1, U32 & String, Qt.QPaintEngine.Type> <- Qt.Action.attempt(Qt.QPaintEngine.Type, Qt.QPaintEngine.type(painting))
    expected(Qt.QPaintEngine.Type, stale, 116)
    +current: Qt.QPaintEngine <- Qt.QPrinter.paintEngine(printer)
    kind: Qt.QPaintEngine.Type <- Qt.QPaintEngine.type(current)
    require(U32.is_eq(Qt.QPaintEngine.Type.word(kind), Qt.QPaintEngine.Type.word(Qt.QPaintEngine.Type.Pdf())), "Reset printer paint engine was not usable")
    Qt.QPrinter.destroy(printer)
    stale: Result<&1, &1, U32 & String, Qt.QPaintEngine.Type> <- Qt.Action.attempt(Qt.QPaintEngine.Type, Qt.QPaintEngine.type(current))
    expected(Qt.QPaintEngine.Type, stale, 116)

def image_engine() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +image: Qt.QImage <- Qt.QImage.new__Int32_Int32_QImage_Format(Qt.Int32{2}, Qt.Int32{2}, Qt.QImage.Format.Format_ARGB32())
    +engine: Qt.QPaintEngine <- Qt.QImage.paintEngine(image)
    kind: Qt.QPaintEngine.Type <- Qt.QPaintEngine.type(engine)
    require(U32.is_eq(Qt.QPaintEngine.Type.word(kind), Qt.QPaintEngine.Type.word(Qt.QPaintEngine.Type.Raster())), "Native image paint engine was not usable")
    +copy: Qt.QImage <- Qt.QImage.new__QImage(image)
    Qt.QImage.fill__U32(image, 4278190335)
    stale: Result<&1, &1, U32 & String, Qt.QPaintEngine.Type> <- Qt.Action.attempt(Qt.QPaintEngine.Type, Qt.QPaintEngine.type(engine))
    expected(Qt.QPaintEngine.Type, stale, 116)
    +current: Qt.QPaintEngine <- Qt.QImage.paintEngine(image)
    Qt.QImage.destroy(image)
    stale: Result<&1, &1, U32 & String, Qt.QPaintEngine.Type> <- Qt.Action.attempt(Qt.QPaintEngine.Type, Qt.QPaintEngine.type(current))
    expected(Qt.QPaintEngine.Type, stale, 116)
    Qt.QImage.destroy(copy)

def painter_engine() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    image: Qt.QImage <- Qt.QImage.new__Int32_Int32_QImage_Format(Qt.Int32{2}, Qt.Int32{2}, Qt.QImage.Format.Format_ARGB32())
    device: Qt.QPaintDevice <- Qt.QImage.as_QPaintDevice(image)
    +painter: Qt.QPainter <- Qt.QPainter.new__QPaintDevice(device)
    +engine: Qt.QPaintEngine <- Qt.QPainter.paintEngine(painter)
    kind: Qt.QPaintEngine.Type <- Qt.QPaintEngine.type(engine)
    require(U32.is_eq(Qt.QPaintEngine.Type.word(kind), Qt.QPaintEngine.Type.word(Qt.QPaintEngine.Type.Raster())), "Native painter engine was not usable")
    ended: Bool <- Qt.QPainter.end(painter)
    require(ended, "Painter did not end")
    stale: Result<&1, &1, U32 & String, Qt.QPaintEngine.Type> <- Qt.Action.attempt(Qt.QPaintEngine.Type, Qt.QPaintEngine.type(engine))
    expected(Qt.QPaintEngine.Type, stale, 116)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, mime_copies())
    Qt.scoped(Unit, wizard_parent())
    Qt.scoped(Unit, document_object())
    Qt.scoped(Unit, printer_replacement())
    Qt.scoped(Unit, printer_reset())
    Qt.scoped(Unit, default_printer_engines())
    Qt.scoped(Unit, image_engine())
    Qt.scoped(Unit, painter_engine())
    +objects: U32 <- Qt.Runtime.liveObjects()
    +retentions: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(retentions, 0), "Protected lifetime adapters leaked resources")
    Qt.Action.lift(Unit, IO.print("QT612_PROTECTED_LIFETIMES_OK mime_copy=1 wizard_identity=1 document_child=1 printer_replacement=1 printer_reset=1 virtual_observer=1 engine_views=1 stale=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
