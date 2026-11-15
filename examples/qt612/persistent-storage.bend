import Base
import ../../packages/qt612/qt.bend as Qt

# Fixture bytes below are produced from scripts/fixtures/persistent-resource.qrc
# and persistent-translations.ts with Qt 6.12 rcc/lrelease.

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def resource_bytes() -> List<&2, U32>:
  113 <> 114 <> 101 <> 115 <> 0 <> 0 <> 0 <> 3 <> 0 <> 0 <> 0 <> 96 <> 0 <> 0 <> 0 <> 24 <> 0 <> 0 <> 0 <> 46 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 18 <> 114 <> 101 <> 116 <> 97 <> 105 <> 110 <> 101 <> 100 <> 32 <> 114 <> 101 <> 115 <> 111 <> 117 <> 114 <> 99 <> 101 <> 10 <> 0 <> 8 <> 15 <> 204 <> 162 <> 117 <> 0 <> 108 <> 0 <> 105 <> 0 <> 102 <> 0 <> 101 <> 0 <> 116 <> 0 <> 105 <> 0 <> 109 <> 0 <> 101 <> 0 <> 11 <> 7 <> 51 <> 206 <> 212 <> 0 <> 109 <> 0 <> 101 <> 0 <> 115 <> 0 <> 115 <> 0 <> 97 <> 0 <> 103 <> 0 <> 101 <> 0 <> 46 <> 0 <> 116 <> 0 <> 120 <> 0 <> 116 <> 0 <> 0 <> 0 <> 0 <> 0 <> 2 <> 0 <> 0 <> 0 <> 1 <> 0 <> 0 <> 0 <> 1 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 2 <> 0 <> 0 <> 0 <> 1 <> 0 <> 0 <> 0 <> 2 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 22 <> 0 <> 0 <> 0 <> 0 <> 0 <> 1 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 1 <> 161 <> 192 <> 78 <> 24 <> 38 <> Nil{}

def translation_bytes() -> List<&2, U32>:
  60 <> 184 <> 100 <> 24 <> 202 <> 239 <> 156 <> 149 <> 205 <> 33 <> 28 <> 191 <> 96 <> 161 <> 189 <> 221 <> 167 <> 0 <> 0 <> 0 <> 5 <> 112 <> 108 <> 95 <> 80 <> 76 <> 66 <> 0 <> 0 <> 0 <> 8 <> 5 <> 166 <> 200 <> 149 <> 0 <> 0 <> 0 <> 0 <> 105 <> 0 <> 0 <> 0 <> 75 <> 3 <> 0 <> 0 <> 0 <> 40 <> 0 <> 82 <> 0 <> 101 <> 0 <> 116 <> 0 <> 97 <> 0 <> 105 <> 0 <> 110 <> 0 <> 101 <> 0 <> 100 <> 0 <> 32 <> 0 <> 116 <> 0 <> 114 <> 0 <> 97 <> 0 <> 110 <> 0 <> 115 <> 0 <> 108 <> 0 <> 97 <> 0 <> 116 <> 0 <> 105 <> 0 <> 111 <> 0 <> 110 <> 8 <> 0 <> 0 <> 0 <> 0 <> 6 <> 0 <> 0 <> 0 <> 6 <> 83 <> 111 <> 117 <> 114 <> 99 <> 101 <> 7 <> 0 <> 0 <> 0 <> 8 <> 76 <> 105 <> 102 <> 101 <> 116 <> 105 <> 109 <> 101 <> 1 <> 136 <> 0 <> 0 <> 0 <> 10 <> 1 <> 1 <> 255 <> 20 <> 2 <> 4 <> 253 <> 44 <> 10 <> 19 <> Nil{}

def malformed_tree_bytes() -> List<&2, U32>:
  113 <> 114 <> 101 <> 115 <> 0 <> 0 <> 0 <> 3 <> 0 <> 0 <> 0 <> 96 <> 0 <> 0 <> 0 <> 24 <> 0 <> 0 <> 0 <> 46 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 18 <> 114 <> 101 <> 116 <> 97 <> 105 <> 110 <> 101 <> 100 <> 32 <> 114 <> 101 <> 115 <> 111 <> 117 <> 114 <> 99 <> 101 <> 10 <> 0 <> 8 <> 15 <> 204 <> 162 <> 117 <> 0 <> 108 <> 0 <> 105 <> 0 <> 102 <> 0 <> 101 <> 0 <> 116 <> 0 <> 105 <> 0 <> 109 <> 0 <> 101 <> 0 <> 11 <> 7 <> 51 <> 206 <> 212 <> 0 <> 109 <> 0 <> 101 <> 0 <> 115 <> 0 <> 115 <> 0 <> 97 <> 0 <> 103 <> 0 <> 101 <> 0 <> 46 <> 0 <> 116 <> 0 <> 120 <> 0 <> 116 <> 0 <> 0 <> 0 <> 0 <> 0 <> 2 <> 127 <> 255 <> 255 <> 255 <> 0 <> 0 <> 0 <> 1 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 2 <> 0 <> 0 <> 0 <> 1 <> 0 <> 0 <> 0 <> 2 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 22 <> 0 <> 0 <> 0 <> 0 <> 0 <> 1 <> 0 <> 0 <> 0 <> 0 <> 0 <> 0 <> 1 <> 161 <> 192 <> 78 <> 24 <> 38 <> Nil{}

def content(value: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    text: String <- Qt.QByteArray.utf8(value)
    require(String.eq(text, "retained resource\n"), "Resource snapshot changed after unregister")

def retained_readers(+source: Qt.QByteArray, +resource: Qt.QResource, +file: Qt.QFile) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    opened: Bool <- Qt.QFile.open__Flags_QIODeviceBase__OpenModeFlag(file, Qt.Flags_QIODeviceBase__OpenModeFlag{1})
    require(opened, "Resource file did not open")
    valid: Bool <- Qt.QResource.isValid(resource)
    require(valid, "Registered resource was not visible")
    Qt.QByteArray.clear(source)
    unloaded: Bool <- Qt.QResource.unregisterResource__QByteArray_String(source, "")
    require(Bool.not(unloaded), "Qt failed to report the outstanding resource reader")
    Qt.QByteArray.with(Unit, Qt.QResource.uncompressedData(resource), content)
    Qt.QByteArray.with(Unit, Qt.QFile.readAll(file), content)

def retained_resource(+source: Qt.QByteArray, +resource: Qt.QResource) -> Qt.Action(Unit):
  Qt.QFile.with(Unit, Qt.QFile.new__String(":/lifetime/message.txt"), file => retained_readers(source, resource, file))

def resource(+source: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    loaded: Bool <- Qt.QResource.registerResource__QByteArray_String(source, "")
    require(loaded, "Validated RCC registration failed")
    Qt.QResource.with(Unit, Qt.QResource.new__String(":/lifetime/message.txt"), value => retained_resource(source, value))

def translation(+source: Qt.QByteArray, +translator: Qt.QTranslator) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    loaded: Bool <- Qt.QTranslator.load__QByteArray_Int32(translator, source, Qt.Int32{134})
    require(loaded, "Owned translation snapshot failed to load")
    Qt.QByteArray.clear(source)
    text: String <- Qt.QTranslator.translate__String_String(translator, "Lifetime", "Source")
    require(String.eq(text, "Retained translation"), "Translator read mutated or released input data")

def logging_name(name: Maybe<&2, String>) -> Qt.Action(Unit):
  match name:
    case Some{text}: require(String.eq(text, "bend.retained.category"), "Logging category lost its retained name")
    case None{}: Qt.Action.fail(Unit, 1, "Logging category name disappeared")

def logging(value: Qt.QLoggingCategory) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    name: Maybe<&2, String> <- Qt.QLoggingCategory.categoryName(value)
    logging_name(name)

def malformed(source: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    loaded: Bool <- Qt.QResource.registerResource__QByteArray_String(source, "")
    require(Bool.not(loaded), "Malformed RCC data reached Qt's unchecked reader")

def optional_text(value: Maybe<&2, String>, expected: String) -> Qt.Action(Unit):
  match value:
    case Some{text}: require(String.eq(text, expected), "Logging field lost its native backing")
    case None{}: Qt.Action.fail(Unit, 1, "Logging field unexpectedly became null")

def null_text(value: Maybe<&2, String>) -> Qt.Action(Unit):
  match value:
    case None{}: Qt.Action.pure(Unit, Unit{})
    case Some{text}: Qt.Action.fail(Unit, 1, "Null logging field was changed into an empty string")

def context(+value: Qt.QMessageLogContext) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    file: Maybe<&2, String> <- Qt.QMessageLogContext.Fields.file(value)
    optional_text(file, "sample.cpp")
    formatted: String <- Qt.Global.qFormatLogMessage(Qt.QtMsgType{4}, value, "original")
    require(String.eq(formatted, "sample.cpp|42|sample|bend.context|original"), "Native logging context read expired constructor strings")
    Qt.QMessageLogContext.Fields.set_file(value, Some{"other." ++ "cpp"})
    Qt.QMessageLogContext.Fields.set_function(value, Some{"changed"})
    Qt.QMessageLogContext.Fields.set_category(value, Some{"bend.changed"})
    Qt.QMessageLogContext.Fields.set_line(value, Qt.Int32{43})
    updated: String <- Qt.Global.qFormatLogMessage(Qt.QtMsgType{4}, value, "updated")
    require(String.eq(updated, "other.cpp|43|changed|bend.changed|updated"), "Native logging context did not preserve updated fields")
    Qt.QMessageLogContext.Fields.set_file(value, None{})
    missing: Maybe<&2, String> <- Qt.QMessageLogContext.Fields.file(value)
    null_text(missing)

def logger(+value: Qt.QMessageLogger) -> Qt.Action(Unit):
  Qt.QMessageLogger.info__String(value, "QT612_LOGGER_STORAGE_OK")

def contexts() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Global.qSetMessagePattern("%{file}|%{line}|%{function}|%{category}|%{message}")
    Qt.QMessageLogContext.with(Unit, Qt.QMessageLogContext.new__String_Int32_String_String("sample." ++ "cpp", Qt.Int32{42}, "sample", "bend.context"), value => context(value))
    Qt.QMessageLogger.with(Unit, Qt.QMessageLogger.new__String_Int32_String_String("logger." ++ "cpp", Qt.Int32{9}, "logger", "bend.logger"), value => logger(value))
    Qt.Global.qSetMessagePattern("%{if-category}%{category}: %{endif}%{message}")

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes(resource_bytes()), source => resource(source))
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes(malformed_tree_bytes()), malformed)
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes(113 <> 114 <> 101 <> 115 <> Nil{}), malformed)
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes(translation_bytes()), source =>
      Qt.QTranslator.with(Unit, Qt.QTranslator.new(), value => translation(source, value)))
    Qt.QLoggingCategory.with(Unit, Qt.QLoggingCategory.new__String("bend.retained." ++ "category"), logging)
    contexts()
    objects: U32 <- Qt.Runtime.liveObjects()
    pins: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(pins, 0), "Persistent native storage leaked handles")
    Qt.Action.lift(Unit, IO.print("QT612_PERSISTENT_STORAGE_OK resource_snapshot=1 unregister_reader=1 malformed=1 translator=1 logging=1 context_fields=1 logger=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
