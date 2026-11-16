import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def value() -> Qt.Property:
  Qt.Property.define("value", Qt.string())

def Related() -> Qt.ObjectType:
  Qt.QObject.define("FailingQmlRelated", [value()])

def AttachedObject() -> Qt.ObjectType:
  Qt.ObjectType.withAttached(Qt.QObject.define("FailingQmlAttachedObject", []), Related())

def ExtendedObject() -> Qt.ObjectType:
  Qt.ObjectType.withExtension(Qt.QObject.define("FailingQmlExtendedObject", []), Related())

def NonDefault() -> Qt.ObjectType:
  Qt.QSocketNotifier.define("InvalidQmlSocketNotifier", [])

def NonDefaultRelated() -> Qt.ObjectType:
  Qt.QSocketNotifier.define("FactoryConstructedQmlNotifier", [value()])

def FactoryAttached() -> Qt.ObjectType:
  Qt.ObjectType.withAttached(Qt.QObject.define("FactoryConstructedAttached", []), NonDefaultRelated())

def FactoryExtended() -> Qt.ObjectType:
  Qt.ObjectType.withExtension(Qt.QObject.define("FactoryConstructedExtended", []), NonDefaultRelated())

def make_related(label: String, target: Qt.QObject) -> Qt.Action(Qt.ObjectType.Instance(NonDefaultRelated())):
  do Qt.Action<Qt.ObjectType.Instance(NonDefaultRelated())>:
    +instance: Qt.ObjectType.Instance(NonDefaultRelated()) <- Qt.ObjectType.attachUsing(~NonDefaultRelated(),
      Qt.QSocketNotifier.newOverride__QSocketNotifier_Type_QObject(Qt.QSocketNotifier.Type.Read(), Qt.QObject{0}))
    Qt.ObjectType.set(~NonDefaultRelated(), ~value(), instance, label)
    return instance

def fail_related(state: Unit, target: Qt.QObject) -> Qt.Action(Qt.ObjectType.Instance(NonDefaultRelated())):
  Qt.Action.fail(Qt.ObjectType.Instance(NonDefaultRelated()), 69, "Expected nondefault related factory failure")

def fail_attached(state: Unit, target: Qt.QObject) -> Qt.Action(Qt.ObjectType.Instance(Related())):
  Qt.Action.fail(Qt.ObjectType.Instance(Related()), 67, "Expected attached factory failure")

def fail_extension(state: Unit, target: Qt.QObject) -> Qt.Action(Qt.ObjectType.Instance(Related())):
  Qt.Action.fail(Qt.ObjectType.Instance(Related()), 68, "Expected extension factory failure")

def expect_error(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(+code, message)}: require(U32.is_eq(code, expected), "QML lost the original failure: " ++ U32.show(code) ++ " " ++ message)
    case Done{object}: Qt.Action.fail(Unit, 1, "QML ignored the expected failure")

def create(source: String, expected: U32) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +engine: Qt.QQmlEngine <- Qt.QQmlEngine.new()
    +component: Qt.QQmlComponent <- Qt.QQmlComponent.new__QQmlEngine_QObject(engine, Qt.QObject{0})
    data: Qt.QByteArray <- Qt.QByteArray.fromUtf8(source)
    url: Qt.QUrl <- Qt.QUrl.new()
    Qt.QQmlComponent.setData(component, data, url)
    ready: Bool <- Qt.QQmlComponent.isReady(component)
    require(ready, "QML failure fixture did not compile")
    result: Result<&1, &1, U32 & String, Qt.QObject> <- Qt.Action.attempt(Qt.QObject, Qt.QQmlComponent.create__QQmlContext(component, Qt.QQmlContext{0}))
    expect_error(Qt.QObject, result, expected)

def create_valid(source: String, expected: String) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +engine: Qt.QQmlEngine <- Qt.QQmlEngine.new()
    +component: Qt.QQmlComponent <- Qt.QQmlComponent.new__QQmlEngine_QObject(engine, Qt.QObject{0})
    data: Qt.QByteArray <- Qt.QByteArray.fromUtf8(source)
    url: Qt.QUrl <- Qt.QUrl.new()
    Qt.QQmlComponent.setData(component, data, url)
    ready: Bool <- Qt.QQmlComponent.isReady(component)
    require(ready, "Factory-constructed related QML did not compile")
    root: Qt.QObject <- Qt.QQmlComponent.create__QQmlContext(component, Qt.QQmlContext{0})
    value: Qt.QVariant <- Qt.QQmlProperty.read__QObject_String(root, "result")
    text: String <- Qt.QVariant.toString(value)
    require(String.eq(text, expected), "Factory-constructed native related type did not reach QML")

def cases() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +attached: Qt.Qml.Registration(AttachedObject()) <- Qt.Qml.registerType(~AttachedObject(), "Bend.FailingAttached", 1, 0, "Card")
    Qt.Qml.handleAttached(~AttachedObject(), ~Unit, ~fail_attached, attached, Unit{})
    create("import Bend.FailingAttached 1.0\nCard { Card.value: 'force-attached' }", 67)
    +extended: Qt.Qml.Registration(ExtendedObject()) <- Qt.Qml.registerType(~ExtendedObject(), "Bend.FailingExtension", 1, 0, "Card")
    Qt.Qml.handleExtension(~ExtendedObject(), ~Unit, ~fail_extension, extended, Unit{})
    create("import Bend.FailingExtension 1.0\nCard { value: 'force-extension' }", 68)
    non_default: Qt.Qml.Registration(NonDefault()) <- Qt.Qml.registerType(~NonDefault(), "Bend.InvalidDefault", 1, 0, "Card")
    create("import Bend.InvalidDefault 1.0\nCard {}", 38)
    +factory_attached: Qt.Qml.Registration(FactoryAttached()) <- Qt.Qml.registerType(~FactoryAttached(), "Bend.FactoryAttached", 1, 0, "Card")
    Qt.Qml.handleAttached(~FactoryAttached(), ~String, ~make_related, factory_attached, "attached-factory")
    create_valid("import Bend.FactoryAttached 1.0\nCard { property string result: Card.value }", "attached-factory")
    +factory_extended: Qt.Qml.Registration(FactoryExtended()) <- Qt.Qml.registerType(~FactoryExtended(), "Bend.FactoryExtended", 1, 0, "Card")
    Qt.Qml.handleExtension(~FactoryExtended(), ~String, ~make_related, factory_extended, "extension-factory")
    create_valid("import Bend.FactoryExtended 1.0\nCard { property string result: value }", "extension-factory")
    +factory_singleton: Qt.Qml.Registration(FactoryExtended()) <- Qt.Qml.registerSingleton(~FactoryExtended(), "Bend.FactorySingleton", 1, 0, "Settings")
    Qt.Qml.handleExtension(~FactoryExtended(), ~String, ~make_related, factory_singleton, "singleton-factory")
    create_valid("import QtQml\nimport Bend.FactorySingleton 1.0\nQtObject { property string result: Settings.value }", "singleton-factory")
    +missing_attached: Qt.Qml.Registration(FactoryAttached()) <- Qt.Qml.registerType(~FactoryAttached(), "Bend.MissingAttached", 1, 0, "Card")
    create("import Bend.MissingAttached 1.0\nCard { Card.value: 'missing-factory' }", 38)
    +missing_extended: Qt.Qml.Registration(FactoryExtended()) <- Qt.Qml.registerType(~FactoryExtended(), "Bend.MissingExtension", 1, 0, "Card")
    create("import Bend.MissingExtension 1.0\nCard { value: 'missing-factory' }", 38)
    +failed_extended: Qt.Qml.Registration(FactoryExtended()) <- Qt.Qml.registerType(~FactoryExtended(), "Bend.FailedFactory", 1, 0, "Card")
    Qt.Qml.handleExtension(~FactoryExtended(), ~Unit, ~fail_related, failed_extended, Unit{})
    create("import Bend.FailedFactory 1.0\nCard { value: 'failed-factory' }", 69)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, cases())
    live: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(live, 0), "QML factory failures leaked")
    Qt.Action.lift(Unit, IO.print("QT612_QML_FACTORY_FAILURES_OK attached=67 extension=68 nondefault_root=38 nondefault_related=1 missing=38 failed=69 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
