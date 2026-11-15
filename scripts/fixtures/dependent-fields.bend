import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def error(~A: Type, expected: U32, value: Result<&1, &1, U32 & String, A>) -> Qt.Action(Unit):
  match value:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong aggregate error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Invalid aggregate operation succeeded")

def copied(+document: Qt.QTextDocument, original: Qt.QTextEdit.ExtraSelection, +copy: Qt.QTextEdit.ExtraSelection) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Action.lift(Unit, IO.print("aggregate: discard source selection"))
    Qt.QTextEdit.ExtraSelection.destroy(original)
    held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QTextDocument.destroy(document))
    error(Unit, 16, held)
    Qt.Action.lift(Unit, IO.print("aggregate: native document delete"))
    Qt.Fixture.deleteDocument(document)
    stale: Result<&1, &1, U32 & String, Qt.QTextCursor> <- Qt.Action.attempt(Qt.QTextCursor, Qt.QTextEdit.ExtraSelection.Fields.cursor(copy))
    error(Qt.QTextCursor, 116, stale)

def selected(+document: Qt.QTextDocument, +cursor: Qt.QTextCursor, +selection: Qt.QTextEdit.ExtraSelection) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Action.lift(Unit, IO.print("aggregate: set cursor"))
    Qt.QTextEdit.ExtraSelection.Fields.set_cursor(selection, cursor)
    Qt.Action.lift(Unit, IO.print("aggregate: discard source cursor"))
    Qt.QTextCursor.destroy(cursor)
    Qt.Action.lift(Unit, IO.print("aggregate: copy selection"))
    Qt.QTextEdit.ExtraSelection.with(Unit, Qt.QTextEdit.ExtraSelection.new__QTextEdit_ExtraSelection(selection), copy => copied(document, selection, copy))

def cursor(+document: Qt.QTextDocument, +value: Qt.QTextCursor) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Action.lift(Unit, IO.print("aggregate: cursor acquired"))
    Qt.QTextEdit.ExtraSelection.with(Unit, Qt.QTextEdit.ExtraSelection.new(), selection => selected(document, value, selection))

def document(+value: Qt.QTextDocument) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Action.lift(Unit, IO.print("aggregate: document acquired"))
    Qt.QTextCursor.with(Unit, Qt.QTextDocument.find__String(value, "hello"), item => cursor(value, item))

def read_script(value: Qt.QJSValue) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    valid: Bool <- Qt.QJSValue.isObject(value)
    require(valid, "Aggregate QVariant lost its managed value")

def read_variant(value: Qt.QVariant) -> Qt.Action(Unit):
  Qt.QJSValue.with(Unit, Qt.QVariant.to_QJSValue(value), read_script)

def replaced(+engine: Qt.QJSEngine, original: Qt.QQmlContext.PropertyPair, +copy: Qt.QQmlContext.PropertyPair, plain: Qt.QVariant) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQmlContext.PropertyPair.Fields.set_value(original, plain)
    held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QJSEngine.destroy(engine))
    error(Unit, 16, held)
    Qt.QVariant.with(Unit, Qt.QQmlContext.PropertyPair.Fields.value(copy), read_variant)
    Qt.QQmlContext.PropertyPair.destroy(copy)
    Qt.QJSEngine.destroy(engine)

def pair_copy(+engine: Qt.QJSEngine, +original: Qt.QQmlContext.PropertyPair, +copy: Qt.QQmlContext.PropertyPair) -> Qt.Action(Unit):
  Qt.QVariant.with(Unit, Qt.QVariant.fromString("independent"), plain => replaced(engine, original, copy, plain))

def pair(+engine: Qt.QJSEngine, +source: Qt.QVariant, +value: Qt.QQmlContext.PropertyPair) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQmlContext.PropertyPair.Fields.set_value(value, source)
    Qt.QVariant.destroy(source)
    Qt.QQmlContext.PropertyPair.with(Unit, Qt.QQmlContext.PropertyPair.new__QQmlContext_PropertyPair(value), copy => pair_copy(engine, value, copy))

def variant(+engine: Qt.QJSEngine, script: Qt.QJSValue, +value: Qt.QVariant) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QJSValue.destroy(script)
    Qt.QQmlContext.PropertyPair.with(Unit, Qt.QQmlContext.PropertyPair.new(), item => pair(engine, value, item))

def script(+engine: Qt.QJSEngine, +value: Qt.QJSValue) -> Qt.Action(Unit):
  Qt.QVariant.with(Unit, Qt.QVariant.from_QJSValue(value), item => variant(engine, value, item))

def engine(+value: Qt.QJSEngine) -> Qt.Action(Unit):
  Qt.QJSValue.with(Unit, Qt.QJSEngine.newObject(value), item => script(value, item))

def unchanged(values: List<&2, Qt.PairValue<String, Qt.QVariant>>) -> Qt.Action(Unit):
  match values:
    case Qt.PairValue{key, value} <> Nil{}:
      do Qt.Action<Unit>:
        text: String <- Qt.QVariant.toString(value)
        require(String.eq(key, "original") && String.eq(text, "unchanged"), "Failed conversion changed the old field")
    case _: Qt.Action.fail(Unit, 1, "Failed conversion changed the old field size")

def map_value(+source: Qt.QVariant, +record: Qt.QCanFrameProcessor.ParseResult, original: Qt.QVariant) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QCanFrameProcessor.ParseResult.Fields.set_signalValues(record, Qt.PairValue{"original", original} <> Nil{})
    Qt.Fixture.failAfter(2)
    failed: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QCanFrameProcessor.ParseResult.Fields.set_signalValues(record, Qt.PairValue{"a", source} <> Qt.PairValue{"b", source} <> Nil{}))
    error(Unit, 12, failed)
    Qt.List_Pair_String_QVariant.with(Unit, Qt.QCanFrameProcessor.ParseResult.Fields.signalValues(record), unchanged)

def map_record(+source: Qt.QVariant, +record: Qt.QCanFrameProcessor.ParseResult) -> Qt.Action(Unit):
  Qt.QVariant.with(Unit, Qt.QVariant.fromString("unchanged"), original => map_value(source, record, original))

def map_variant(+source: Qt.QVariant) -> Qt.Action(Unit):
  Qt.QCanFrameProcessor.ParseResult.with(Unit, Qt.QCanFrameProcessor.ParseResult.new(), record => map_record(source, record))

def map_script(source: Qt.QJSValue) -> Qt.Action(Unit):
  Qt.QVariant.with(Unit, Qt.QVariant.from_QJSValue(source), value => map_variant(value))

def map_engine(engine: Qt.QJSEngine) -> Qt.Action(Unit):
  Qt.QJSValue.with(Unit, Qt.QJSEngine.newObject(engine), map_script)

def style_copy(+widget: Qt.QWidget, original: Qt.QStyleOptionViewItem, +copy: Qt.QStyleOptionViewItem) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QStyleOptionViewItem.destroy(original)
    held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QWidget.destroy(widget))
    error(Unit, 16, held)
    alias: Qt.QObject <- Qt.QStyleOptionViewItem.Fields.styleObject(copy)
    name: String <- Qt.QObject.objectName(alias)
    require(String.eq(name, ""), "Observed widget field changed identity")
    Qt.QStyleOptionViewItem.destroy(copy)
    Qt.QWidget.destroy(widget)

def style_option(+widget: Qt.QWidget, +option: Qt.QStyleOptionViewItem) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QStyleOptionViewItem.initFrom(option, widget)
    Qt.QStyleOptionViewItem.with(Unit, Qt.QStyleOptionViewItem.new__QStyleOptionViewItem(option), copy => style_copy(widget, option, copy))

def style_widget(+widget: Qt.QWidget) -> Qt.Action(Unit):
  Qt.QStyleOptionViewItem.with(Unit, Qt.QStyleOptionViewItem.new(), option => style_option(widget, option))

def native_style(+option: Qt.QStyleOptionViewItem) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    widget: Qt.QWidget <- Qt.QStyleOptionViewItem.Fields.widget(option)
    name: String <- Qt.QWidget.objectName(widget)
    require(String.eq(name, ""), "Native callback field observation changed the widget")
    Qt.Fixture.deleteStyleWidget()
    stale: Result<&1, &1, U32 & String, Qt.QWidget> <- Qt.Action.attempt(Qt.QWidget, Qt.QStyleOptionViewItem.Fields.widget(option))
    error(Qt.QWidget, 116, stale)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    initial: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(initial, 0), "Nonempty startup registry")
    Qt.Action.lift(Unit, IO.print("aggregate: document"))
    Qt.QTextDocument.with(Unit, Qt.QTextDocument.new__String("hello"), value => document(value))
    Qt.Action.lift(Unit, IO.print("aggregate: variant"))
    Qt.QJSEngine.with(Unit, Qt.QJSEngine.new(), value => engine(value))
    Qt.Action.lift(Unit, IO.print("aggregate: fault"))
    Qt.QJSEngine.with(Unit, Qt.QJSEngine.new(), map_engine)
    Qt.Action.lift(Unit, IO.print("aggregate: widget"))
    Qt.QWidget.with(Unit, Qt.QWidget.new(), widget => style_widget(widget))
    unobserved: Result<&1, &1, U32 & String, Qt.QStyleOptionViewItem> <- Qt.Action.attempt(Qt.QStyleOptionViewItem, Qt.Fixture.unobservedStyle())
    error(Qt.QStyleOptionViewItem, 95, unobserved)
    Qt.QStyleOptionViewItem.with(Unit, Qt.Fixture.nativeStyle(), option => native_style(option))
    objects: U32 <- Qt.Runtime.liveObjects()
    retentions: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(retentions, 0), "Aggregate fields leaked state")
    Qt.Action.lift(Unit, IO.print("QT612_DEPENDENT_FIELDS_OK copy=1 native_deletion=1 objects=0 retentions=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))

