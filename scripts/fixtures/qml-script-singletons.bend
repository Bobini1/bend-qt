import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expected(-A: Type, result: Result<&1, &1, U32 & String, A>, code: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(+actual, message)}: require(U32.is_eq(actual, code), "Script singleton error " ++ U32.show(actual) ++ ": " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Invalid script singleton operation succeeded")

def create(state: Qt.QObject, engine: Qt.QQmlEngine) -> Qt.Action(Qt.QJSValue):
  do Qt.Action<Qt.QJSValue>:
    +state: Qt.QObject = state
    count: String <- Qt.QObject.objectName(state)
    Qt.QObject.setObjectName(state, count ++ "x")
    number: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.int32(), Qt.Int32{42})
    map: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.variantMap(), [Qt.PairValue{"answer", number}])
    Qt.QJSEngine.toScriptValue(Qt.QQmlEngine.as_QJSEngine(engine), map)

def refused(state: Unit, engine: Qt.QQmlEngine) -> Qt.Action(Qt.QJSValue):
  Qt.Action.fail(Qt.QJSValue, 91, "Expected script singleton factory failure")

def foreign(value: Qt.QJSValue, engine: Qt.QQmlEngine) -> Qt.Action(Qt.QJSValue):
  Qt.Action.pure(Qt.QJSValue, value)

def image_factory(state: Unit, engine: Qt.QQmlEngine) -> Qt.Action(Qt.QJSValue):
  do Qt.Action<Qt.QJSValue>:
    bytes: Qt.QByteArray <- Qt.QByteArray.fromBytes([255, 0, 0, 255])
    buffer: Qt.ImageBuffer <- Qt.ImageBuffer.fromBytes(bytes)
    image: Qt.QImage <- Qt.QImage.fromBuffer(buffer, Qt.Int32{1}, Qt.Int32{1}, Qt.QImage.Format.Format_RGBA8888())
    boxed: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.QImage.arg(), image)
    Qt.QJSEngine.toScriptValue(Qt.QQmlEngine.as_QJSEngine(engine), boxed)

def qml_text(+engine: Qt.QQmlEngine) -> Qt.Action(String):
  do Qt.Action<String>:
    +component: Qt.QQmlComponent <- Qt.QQmlComponent.new__QQmlEngine_QObject(engine, Qt.QObject{0})
    data: Qt.QByteArray <- Qt.QByteArray.fromUtf8("import QtQml\nimport Bend.ScriptSingletons 1.0\nQtObject { property string text: Data.answer + ':' + Data.answer }")
    url: Qt.QUrl <- Qt.QUrl.new()
    Qt.QQmlComponent.setData(component, data, url)
    ready: Bool <- Qt.QQmlComponent.isReady(component)
    require(ready, "Script singleton QML did not compile")
    root: Qt.QObject <- Qt.QQmlComponent.create__QQmlContext(component, Qt.QQmlContext{0})
    value: Qt.QVariant <- Qt.QQmlProperty.read__QObject_String(root, "text")
    Qt.QVariant.toString(value)

def one_engine(+registration: Qt.Qml.RegistrationHandle) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +engine: Qt.QQmlEngine <- Qt.QQmlEngine.new()
    +value: Qt.QJSValue <- Qt.QQmlEngine.singletonInstance(~Qt.QJSValue.arg(), engine, "Bend.ScriptSingletons", "Data")
    +answer: Qt.QJSValue <- Qt.QJSValue.property__String(value, "answer")
    number: Qt.Int32 <- Qt.QJSValue.toInt(answer)
    require(U32.is_eq(Qt.Int32.word(number), 42), "Script singleton lost its JavaScript object")
    held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.Qml.RegistrationHandle.destroy(registration))
    expected(Unit, held, 16)
    held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QQmlEngine.destroy(engine))
    expected(Unit, held, 16)
    Qt.QJSValue.destroy(answer)
    Qt.QJSValue.destroy(value)
    text: String <- Qt.scoped(String, qml_text(engine))
    require(String.eq(text, "42:42"), "QML could not read the script singleton")
    Qt.QQmlEngine.destroy(engine)

def engines() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +state: Qt.QObject <- Qt.QObject.new()
    +registration: Qt.Qml.RegistrationHandle <- Qt.Qml.registerScriptSingleton(~Qt.QObject, ~create, "Bend.ScriptSingletons", 1, 0, "Data", state)
    one_engine(registration)
    one_engine(registration)
    count: String <- Qt.QObject.objectName(state)
    require(String.eq(count, "xx"), "The script singleton factory did not run once per engine")
    Qt.Qml.RegistrationHandle.destroy(registration)
    Qt.QObject.destroy(state)

def failures() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +registration: Qt.Qml.RegistrationHandle <- Qt.Qml.registerScriptSingleton(~Unit, ~refused, "Bend.ScriptFailures", 1, 0, "Data", Unit{})
    +engine: Qt.QQmlEngine <- Qt.QQmlEngine.new()
    result: Result<&1, &1, U32 & String, Qt.QJSValue> <- Qt.Action.attempt(Qt.QJSValue,
      Qt.QQmlEngine.singletonInstance(~Qt.QJSValue.arg(), engine, "Bend.ScriptFailures", "Data"))
    expected(Qt.QJSValue, result, 91)
    Qt.QQmlEngine.destroy(engine)
    Qt.Qml.RegistrationHandle.destroy(registration)
    result: Result<&1, &1, U32 & String, Qt.Qml.RegistrationHandle> <- Qt.Action.attempt(Qt.Qml.RegistrationHandle,
      Qt.Qml.registerScriptSingleton(~Unit, ~refused, "Bend.ScriptFailures", 255, 0, "Invalid", Unit{}))
    expected(Qt.Qml.RegistrationHandle, result, 34)

def wrong_engine() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +source: Qt.QJSEngine <- Qt.QJSEngine.new()
    +value: Qt.QJSValue <- Qt.QJSEngine.newObject(source)
    +registration: Qt.Qml.RegistrationHandle <- Qt.Qml.registerScriptSingleton(~Qt.QJSValue, ~foreign, "Bend.ScriptForeign", 1, 0, "Data", value)
    +engine: Qt.QQmlEngine <- Qt.QQmlEngine.new()
    result: Result<&1, &1, U32 & String, Qt.QJSValue> <- Qt.Action.attempt(Qt.QJSValue,
      Qt.QQmlEngine.singletonInstance(~Qt.QJSValue.arg(), engine, "Bend.ScriptForeign", "Data"))
    expected(Qt.QJSValue, result, 18)
    Qt.QQmlEngine.destroy(engine)
    Qt.Qml.RegistrationHandle.destroy(registration)
    Qt.QJSValue.destroy(value)
    Qt.QJSEngine.destroy(source)

def external_data() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +registration: Qt.Qml.RegistrationHandle <- Qt.Qml.registerScriptSingleton(~Unit, ~image_factory, "Bend.ScriptImage", 1, 0, "Data", Unit{})
    +engine: Qt.QQmlEngine <- Qt.QQmlEngine.new()
    +value: Qt.QJSValue <- Qt.QQmlEngine.singletonInstance(~Qt.QJSValue.arg(), engine, "Bend.ScriptImage", "Data")
    +boxed: Qt.QVariant <- Qt.QJSValue.toVariant(value)
    +image: Qt.QImage <- Qt.QVariant.toValue(~Qt.QImage.arg(), boxed)
    +color: Qt.QColor <- Qt.QImage.pixelColor__Int32_Int32(image, Qt.Int32{0}, Qt.Int32{0})
    red: Qt.Int32 <- Qt.QColor.red(color)
    require(U32.is_eq(Qt.Int32.word(red), 255), "Script singleton lost external image backing after its callback returned")
    Qt.QColor.destroy(color)
    Qt.QImage.destroy(image)
    Qt.QVariant.destroy(boxed)
    Qt.QJSValue.destroy(value)
    Qt.QQmlEngine.destroy(engine)
    Qt.Qml.RegistrationHandle.destroy(registration)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, engines())
    Qt.scoped(Unit, failures())
    Qt.scoped(Unit, wrong_engine())
    Qt.scoped(Unit, external_data())
    +objects: U32 <- Qt.Runtime.liveObjects()
    +retentions: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(retentions, 0), "Script singleton resources leaked")
    Qt.Action.lift(Unit, IO.print("QT612_QML_SCRIPT_SINGLETONS_OK qml=1 per_engine=1 origins=1 failures=91_18 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
