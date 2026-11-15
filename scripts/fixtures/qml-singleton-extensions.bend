import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def detail() -> Qt.Property:
  Qt.Property.define("detail", Qt.string())

def Extension() -> Qt.QtObject:
  Qt.QObject.define("SingletonExtensionDetails", [detail()])

def Settings() -> Qt.QtObject:
  Qt.QtObject.withExtension(Qt.QObject.define("ExtendedSingletonSettings", []), Extension())

def revised() -> Qt.Property:
  Qt.Property.withRevision(Qt.Property.define("revised", Qt.string()), 2)

def Versioned() -> Qt.QtObject:
  Qt.QObject.define("RevisedSingletonSettings", [revised()])

def initialize(name: String, instance: Qt.QtObject.Instance(Settings())) -> Qt.Action(Unit):
  Qt.QObject.setObjectName(Qt.QtObject.as_QObject(~Settings(), instance), name)

def extended(label: String, target: Qt.QObject) -> Qt.Action(Qt.QtObject.Instance(Extension())):
  do Qt.Action<Qt.QtObject.Instance(Extension())>:
    +instance: Qt.QtObject.Instance(Extension()) <- Qt.QtObject.new(~Extension())
    Qt.Property.set(~detail(), Qt.QtObject.as_QObject(~Extension(), instance), label)
    return instance

def create(state: Unit, engine: Qt.QQmlEngine) -> Qt.Action(Qt.QtObject.Instance(Settings())):
  Qt.QtObject.new(~Settings())

def create_versioned(state: Unit, engine: Qt.QQmlEngine) -> Qt.Action(Qt.QtObject.Instance(Versioned())):
  Qt.QtObject.new(~Versioned())

def qml_text(+engine: Qt.QQmlEngine, source: String, property: String) -> Qt.Action(String):
  do Qt.Action<String>:
    +component: Qt.QQmlComponent <- Qt.QQmlComponent.new__QQmlEngine_QObject(engine, Qt.QObject{0})
    data: Qt.QByteArray <- Qt.QByteArray.fromUtf8(source)
    url: Qt.QUrl <- Qt.QUrl.new()
    Qt.QQmlComponent.setData(component, data, url)
    ready: Bool <- Qt.QQmlComponent.isReady(component)
    require(ready, "Singleton extension or revision QML did not compile")
    root: Qt.QObject <- Qt.QQmlComponent.create__QQmlContext(component, Qt.QQmlContext{0})
    value: Qt.QVariant <- Qt.QQmlProperty.read__QObject_String(root, property)
    Qt.QVariant.toString(value)

def reject_attached(result: Result<&1, &1, U32 & String, Qt.QObject>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 95), message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Singleton registration silently ignored its attached type")

def reject_revision(result: Result<&1, &1, U32 & String, Qt.QObject>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 34), message)
    case Done{value}: Qt.Action.fail(Unit, 1, "An invalid major revision was interpreted as the internal minor-only sentinel")

def objects() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +defaults: Qt.QObject <- Qt.Qml.registerSingleton(~Settings(), "Bend.SingletonExtensions", 1, 0, "Defaults")
    +instance: Qt.QtObject.Instance(Settings()) <- Qt.QtObject.new(~Settings())
    +existing: Qt.QObject <- Qt.Qml.registerSingletonInstance(~Settings(), "Bend.SingletonExtensions", 1, 0, "Existing", instance)
    +factory: Qt.QObject <- Qt.Qml.registerSingletonFactory(~Settings(), ~Unit, ~create, "Bend.SingletonExtensions", 1, 0, "Factory", Unit{})
    Qt.Qml.handleCreate(~Settings(), ~String, ~initialize, defaults, "DefaultInit")
    Qt.Qml.handleCreate(~Settings(), ~String, ~initialize, existing, "ExistingInit")
    Qt.Qml.handleCreate(~Settings(), ~String, ~initialize, factory, "FactoryInit")
    Qt.Qml.handleExtension(~Settings(), ~String, ~extended, defaults, "default")
    Qt.Qml.handleExtension(~Settings(), ~String, ~extended, existing, "existing")
    Qt.Qml.handleExtension(~Settings(), ~String, ~extended, factory, "factory")
    +engine: Qt.QQmlEngine <- Qt.QQmlEngine.new()
    text: String <- qml_text(engine, "import QtQml\nimport Bend.SingletonExtensions 1.0\nQtObject { property string text: Defaults.detail + '|' + Existing.detail + '|' + Factory.detail + '|' + Defaults.objectName + '|' + Existing.objectName + '|' + Factory.objectName }", "text")
    require(String.eq(text, "default|existing|factory|DefaultInit|ExistingInit|FactoryInit"), "Singleton extensions or initializers did not run in every registration mode")
    extension: Qt.QtObject.Instance(Extension()) <- Qt.Qml.extension(~Settings(), existing, instance)
    text: String <- Qt.Property.get(~detail(), Qt.QtObject.as_QObject(~Extension(), extension))
    require(String.eq(text, "existing"), "Typed singleton extension lookup did not use the QML-created instance")
    rejected: Result<&1, &1, U32 & String, Qt.QObject> <- Qt.Action.attempt(Qt.QObject,
      Qt.Qml.registerSingleton(~Qt.QtObject.withAttached(Settings(), Extension()), "Bend.SingletonAttached", 1, 0, "Unsupported"))
    reject_attached(rejected)
    old: Qt.QObject <- Qt.Qml.registerSingletonRevision(~Versioned(), "Bend.SingletonRevisions", 1, 0, "Settings", 0)
    current: Qt.QObject <- Qt.Qml.registerSingletonRevision(~Versioned(), "Bend.SingletonRevisions", 1, 2, "Settings", 2)
    +versioned: Qt.QtObject.Instance(Versioned()) <- Qt.QtObject.new(~Versioned())
    instance_revision: Qt.QObject <- Qt.Qml.registerSingletonInstanceVersionRevision(~Versioned(), "Bend.SingletonRevisions", 1, 2, "Existing", 1, 2, versioned)
    factory_revision: Qt.QObject <- Qt.Qml.registerSingletonFactoryVersionRevision(~Versioned(), ~Unit, ~create_versioned, "Bend.SingletonRevisions", 1, 2, "Factory", 1, 2, Unit{})
    +old_engine: Qt.QQmlEngine <- Qt.QQmlEngine.new()
    text: String <- qml_text(old_engine, "import QtQml\nimport Bend.SingletonRevisions 1.0\nQtObject { property string text: typeof Settings.revised }", "text")
    require(String.eq(text, "string"), "Dynamic singleton lookup differs from native Qt revision behavior")
    +meta: Qt.QMetaObject <- Qt.QObject.metaObject(Qt.QtObject.as_QObject(~Versioned(), versioned))
    index: Qt.Int32 <- Qt.QMetaObject.indexOfProperty(meta, "revised")
    property: Qt.QMetaProperty <- Qt.QMetaObject.property(meta, index)
    revision: Qt.Int32 <- Qt.QMetaProperty.revision(property)
    require(U32.is_eq(Qt.Int32.word(revision), 65282), "Singleton property revision metadata was lost")
    +new_engine: Qt.QQmlEngine <- Qt.QQmlEngine.new()
    text: String <- qml_text(new_engine, "import QtQml\nimport Bend.SingletonRevisions 1.2\nQtObject { property string text: typeof Settings.revised + '|' + typeof Existing.revised + '|' + typeof Factory.revised }", "text")
    require(String.eq(text, "string|string|string"), "A revised singleton property is missing in one registration mode")
    rejected: Result<&1, &1, U32 & String, Qt.QObject> <- Qt.Action.attempt(Qt.QObject,
      Qt.Qml.registerSingletonVersionRevision(~Versioned(), "Bend.InvalidSingletonRevision", 1, 0, "Invalid", 65535, 0))
    reject_revision(rejected)
    rejected: Result<&1, &1, U32 & String, Qt.QObject> <- Qt.Action.attempt(Qt.QObject,
      Qt.Qml.registerSingletonInstanceVersionRevision(~Versioned(), "Bend.InvalidSingletonRevision", 1, 0, "InvalidInstance", 65535, 0, versioned))
    reject_revision(rejected)
    rejected: Result<&1, &1, U32 & String, Qt.QObject> <- Qt.Action.attempt(Qt.QObject,
      Qt.Qml.registerSingletonFactoryVersionRevision(~Versioned(), ~Unit, ~create_versioned, "Bend.InvalidSingletonRevision", 1, 0, "InvalidFactory", 65535, 0, Unit{}))
    reject_revision(rejected)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, objects())
    live: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(live, 0), "Singleton extensions, handlers or engines leaked")
    Qt.Action.lift(Unit, IO.print("QT612_QML_SINGLETON_EXTENSIONS_OK modes=3 initializer=1 extension=1 revision=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
