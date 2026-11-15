import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def error(~A: Type, expected: U32, label: String, value: Result<&1, &1, U32 & String, A>) -> Qt.Action(Unit):
  match value:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong provenance error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Invalid provenance operation succeeded: " ++ label)

def script_iterator(+engine: Qt.QJSEngine, value: Qt.QJSValue, iterator: Qt.QJSValueIterator) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QJSValue.destroy(value)
    held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QJSEngine.destroy(engine))
    error(Unit, 16, "iterator engine", held)
    next: Bool <- Qt.QJSValueIterator.hasNext(iterator)
    require(Bool.not(next), "Empty native object gained properties")

def script_restored(+engine: Qt.QJSEngine, variant: Qt.QVariant, +value: Qt.QJSValue) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QVariant.destroy(variant)
    held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QJSEngine.destroy(engine))
    error(Unit, 16, "restored engine", held)
    valid: Bool <- Qt.QJSValue.isObject(value)
    require(valid, "QVariant copy lost the JavaScript object")
    Qt.QJSValueIterator.with(Unit, Qt.QJSValueIterator.new(value), iterator => script_iterator(engine, value, iterator))

def script_variant(+engine: Qt.QJSEngine, original: Qt.QJSValue, +value: Qt.QVariant) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QJSValue.destroy(original)
    Qt.QJSValue.with(Unit, Qt.QVariant.to_QJSValue(value), restored => script_restored(engine, value, restored))

def script_copy(+engine: Qt.QJSEngine, +original: Qt.QJSValue, +copy: Qt.QJSValue) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QJSValue.destroy(original)
    held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QJSEngine.destroy(engine))
    error(Unit, 16, "copied engine", held)
    Qt.QVariant.with(Unit, Qt.QVariant.from_QJSValue(copy), value => script_variant(engine, copy, value))

def script_original(+engine: Qt.QJSEngine, +value: Qt.QJSValue) -> Qt.Action(Unit):
  Qt.QJSValue.with(Unit, Qt.QJSValue.new__QJSValue(value), copy => script_copy(engine, value, copy))

def script(+engine: Qt.QJSEngine) -> Qt.Action(Unit):
  Qt.QJSValue.with(Unit, Qt.QJSEngine.newObject(engine), value => script_original(engine, value))

def cursor_copy(+document: Qt.QTextDocument, original: Qt.QTextCursor, +copy: Qt.QTextCursor) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QTextCursor.destroy(original)
    held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QTextDocument.destroy(document))
    error(Unit, 16, "cursor document", held)
    Qt.Fixture.deleteDocument(document)
    stale: Result<&1, &1, U32 & String, Qt.Int32> <- Qt.Action.attempt(Qt.Int32, Qt.QTextCursor.position(copy))
    error(Qt.Int32, 116, "stale cursor", stale)

def cursor_original(+document: Qt.QTextDocument, +cursor: Qt.QTextCursor) -> Qt.Action(Unit):
  Qt.QTextCursor.with(Unit, Qt.QTextCursor.new__QTextCursor(cursor), copy => cursor_copy(document, cursor, copy))

def document(+value: Qt.QTextDocument) -> Qt.Action(Unit):
  Qt.QTextCursor.with(Unit, Qt.QTextDocument.find__String(value, "hello"), cursor => cursor_original(value, cursor))

def property_copy(+context: Qt.QQmlContext, +object: Qt.QObject, original: Qt.QQmlProperty, +copy: Qt.QQmlProperty) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQmlProperty.destroy(original)
    held_context: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QQmlContext.destroy(context))
    error(Unit, 16, "property context", held_context)
    held_object: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QObject.destroy(object))
    error(Unit, 16, "property target", held_object)
    valid: Bool <- Qt.QQmlProperty.isValid(copy)
    require(valid, "Copied QML property lost its target")

def property_original(+context: Qt.QQmlContext, +object: Qt.QObject, +property: Qt.QQmlProperty) -> Qt.Action(Unit):
  Qt.QQmlProperty.with(Unit, Qt.QQmlProperty.new__QQmlProperty(property), copy => property_copy(context, object, property, copy))

def property_object(+context: Qt.QQmlContext, +object: Qt.QObject) -> Qt.Action(Unit):
  Qt.QQmlProperty.with(Unit, Qt.QQmlProperty.new__QObject_String_QQmlContext(object, "objectName", context), property => property_original(context, object, property))

def property_context(+context: Qt.QQmlContext) -> Qt.Action(Unit):
  Qt.QObject.with(Unit, Qt.QObject.new(), object => property_object(context, object))

def property_engine(engine: Qt.QQmlEngine) -> Qt.Action(Unit):
  Qt.QQmlContext.with(Unit, Qt.QQmlContext.new__QQmlEngine_QObject(engine, Qt.QObject{0}), context => property_context(context))

def script_list(+engine: Qt.QJSEngine, values: List<&2, Qt.QJSValue>) -> Qt.Action(Unit):
  match values:
    case first <> second <> Nil{}:
      do Qt.Action<Unit>:
        held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QJSEngine.destroy(engine))
        error(Unit, 16, "container engine", held)
        object: Bool <- Qt.QJSValue.isObject(first)
        array: Bool <- Qt.QJSValue.isArray(second)
        require(object && array, "Recursive container copies changed native values")
    case _: Qt.Action.fail(Unit, 1, "Wrong native script list size")

def script_list_engine(+engine: Qt.QJSEngine) -> Qt.Action(Unit):
  Qt.List_QJSValue.with(Unit, Qt.Fixture.scriptList(engine), values => script_list(engine, values))

def ignore_script(value: Qt.QJSValue) -> Qt.Action(Unit):
  Qt.Action.pure(Unit, Unit{})

def assigned(+engine: Qt.QJSEngine, +original: Qt.QJSValue, copy: Qt.QJSValue, primitive: Qt.QJSValue) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QJSValue.with(Unit, Qt.QJSValue.op_assign(original, primitive), ignore_script)
    held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QJSEngine.destroy(engine))
    error(Unit, 16, "independent copy after assignment", held)
    Qt.QJSValue.destroy(copy)
    Qt.QJSEngine.destroy(engine)
    number: Bool <- Qt.QJSValue.isNumber(original)
    require(number, "Replacing a managed value kept a stale engine dependency")

def assigned_copy(+engine: Qt.QJSEngine, +original: Qt.QJSValue, copy: Qt.QJSValue) -> Qt.Action(Unit):
  Qt.QJSValue.with(Unit, Qt.QJSValue.new__Int32(Qt.Int32{7}), primitive => assigned(engine, original, copy, primitive))

def assigned_original(+engine: Qt.QJSEngine, +original: Qt.QJSValue) -> Qt.Action(Unit):
  Qt.QJSValue.with(Unit, Qt.QJSValue.new__QJSValue(original), copy => assigned_copy(engine, original, copy))

def assigned_engine(+engine: Qt.QJSEngine) -> Qt.Action(Unit):
  Qt.QJSValue.with(Unit, Qt.QJSEngine.newObject(engine), original => assigned_original(engine, original))

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QJSEngine.with(Unit, Qt.QJSEngine.new(), engine => script(engine))
    Qt.QJSEngine.with(Unit, Qt.QJSEngine.new(), engine => script_list_engine(engine))
    Qt.QJSEngine.with(Unit, Qt.QJSEngine.new(), engine => assigned_engine(engine))
    Qt.QTextDocument.with(Unit, Qt.QTextDocument.new__String("hello"), value => document(value))
    Qt.QQmlEngine.with(Unit, Qt.QQmlEngine.new(), property_engine)
    unknown: Result<&1, &1, U32 & String, Qt.QJSValue> <- Qt.Action.attempt(Qt.QJSValue, Qt.Fixture.unknownScript())
    error(Qt.QJSValue, 95, "unknown script", unknown)
    objects: U32 <- Qt.Runtime.liveObjects()
    retentions: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(retentions, 0), "Value provenance leaked registry state")
    Qt.Action.lift(Unit, IO.print("QT612_VALUE_PROVENANCE_OK script_copies=1 variant_roundtrip=1 iterator=1 recursive_container=1 assignment=1 cursor_copy=1 native_document_delete=1 property_context=1 unknown_managed_rejected=1 objects=0 retentions=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
