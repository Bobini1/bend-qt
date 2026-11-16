import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expected(-A: Type, result: Result<&1, &1, U32 & String, A>, code: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(actual, message)}: require(U32.is_eq(actual, code), message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected property rejection")

def title() -> Qt.Property:
  Qt.Property.define("title", Qt.string())

def version() -> Qt.Property:
  Qt.Property.constant("version", Qt.string())

def theme() -> Qt.Property:
  Qt.Property.withReset(Qt.Property.define("theme", Qt.string()))

def preview() -> Qt.Property:
  Qt.Property.withStored(Qt.Property.define("preview", Qt.string()), False{})

def automatic() -> Qt.Property:
  Qt.Property.withReset(Qt.Property.readOnly("automatic", Qt.string()))

def failedReset() -> Qt.Property:
  Qt.Property.withReset(Qt.Property.define("failedReset", Qt.string()))

def missingReset() -> Qt.Property:
  Qt.Property.withReset(Qt.Property.define("missingReset", Qt.string()))

def persisted() -> Qt.Property:
  Qt.Property.withStored(Qt.Property.withStored(Qt.Property.define("persisted", Qt.string()), False{}), True{})

def Settings() -> Qt.ObjectType:
  Qt.QObject.define("ExamplePropertySettings", [title(), version(), theme(), preview(), automatic(), failedReset(), missingReset(), persisted()])

def events() -> Qt.Property:
  Qt.Property.define("events", Qt.u32())

def Counter() -> Qt.ObjectType:
  Qt.QObject.define("ExamplePropertyCounter", [events()])

def titleChanged() -> Qt.Signal:
  Qt.Signal.define("titleChanged", [])

def get_title(self: Qt.QObject) -> Qt.Action(String):
  Qt.QObject.objectName(self)

def update_title(self: Qt.QObject, value: String, unchanged: Bool) -> Qt.Action(Unit):
  match unchanged:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}:
      do Qt.Action<Unit>:
        +object: Qt.QObject = self
        Qt.QObject.setObjectName(object, value)
        Qt.Property.notify(~title(), object)

def set_title(self: Qt.QObject, value: String) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +object: Qt.QObject = self
    +text: String = value
    previous: String <- Qt.QObject.objectName(object)
    update_title(object, text, String.eq(previous, text))

def notified(self: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +object: Qt.QObject = self
    count: U32 <- Qt.Property.get(~events(), object)
    Qt.Property.set(~events(), object, U32.add(count, 1))

def reset_theme(self: Qt.QObject) -> Qt.Action(Unit):
  Qt.Property.set(~theme(), self, "system")

def reset_automatic(self: Qt.QObject) -> Qt.Action(Unit):
  Qt.Property.writeStorage(~automatic(), self, "automatic")

def reject_reset(state: Unit) -> Qt.Action(Unit):
  Qt.Action.fail(Unit, 73, "Expected reset-handler failure")

def meta_property(self: Qt.QObject, name: String) -> Qt.Action(Qt.QMetaProperty):
  do Qt.Action<Qt.QMetaProperty>:
    +meta: Qt.QMetaObject <- Qt.QObject.metaObject(self)
    +index: Qt.Int32 <- Qt.QMetaObject.indexOfProperty(meta, name)
    require(U32.is_ne(Qt.Int32.word(index), 4294967295), "Property metadata is missing")
    Qt.QMetaObject.property(meta, index)

def metadata(+self: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +normal: Qt.QMetaProperty <- meta_property(self, "title")
    stored: Bool <- Qt.QMetaProperty.isStored(normal)
    designable: Bool <- Qt.QMetaProperty.isDesignable(normal)
    notify: Bool <- Qt.QMetaProperty.hasNotifySignal(normal)
    require(stored && designable && notify, "Normal Qt property defaults changed")
    +constant: Qt.QMetaProperty <- meta_property(self, "version")
    fixed: Bool <- Qt.QMetaProperty.isConstant(constant)
    writable: Bool <- Qt.QMetaProperty.isWritable(constant)
    announced: Bool <- Qt.QMetaProperty.hasNotifySignal(constant)
    require(fixed && Bool.not(writable || announced), "Constant property attributes changed")
    +reset: Qt.QMetaProperty <- meta_property(self, "theme")
    resettable: Bool <- Qt.QMetaProperty.isResettable(reset)
    require(resettable, "RESET metadata is missing")
    +readonly: Qt.QMetaProperty <- meta_property(self, "automatic")
    resettable: Bool <- Qt.QMetaProperty.isResettable(readonly)
    writable: Bool <- Qt.QMetaProperty.isWritable(readonly)
    require(resettable && Bool.not(writable), "Read-only RESET attributes changed")
    transient: Qt.QMetaProperty <- meta_property(self, "preview")
    stored: Bool <- Qt.QMetaProperty.isStored(transient)
    require(Bool.not(stored), "STORED false metadata is missing")
    restored: Qt.QMetaProperty <- meta_property(self, "persisted")
    stored: Bool <- Qt.QMetaProperty.isStored(restored)
    require(stored, "STORED true did not clear the modifier")

def qml_source() -> String:
  "import QtQml\nQtObject { property string version: settings.version; property string preview: settings.preview; Component.onCompleted: { settings.theme = undefined } }"

def qml(+self: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Property.set(~theme(), self, "dark")
    +engine: Qt.QQmlEngine <- Qt.QQmlEngine.new__QObject(Qt.QObject{0})
    context: Qt.QQmlContext <- Qt.QQmlEngine.rootContext(engine)
    Qt.QQmlContext.setContextProperty__String_QObject(context, "settings", self)
    +component: Qt.QQmlComponent <- Qt.QQmlComponent.new__QQmlEngine_QObject(engine, Qt.QObject{0})
    data: Qt.QByteArray <- Qt.QByteArray.fromUtf8(qml_source())
    url: Qt.QUrl <- Qt.QUrl.new()
    Qt.QQmlComponent.setData(component, data, url)
    ready: Bool <- Qt.QQmlComponent.isReady(component)
    require(ready, "Property QML did not compile")
    +root: Qt.QObject <- Qt.QQmlComponent.create__QQmlContext(component, Qt.QQmlContext{0})
    current: String <- Qt.Property.get(~theme(), self)
    require(String.eq(current, "system"), "QML undefined did not invoke RESET")
    value: Qt.QVariant <- Qt.QQmlProperty.read__QObject_String(root, "version")
    text: String <- Qt.QVariant.toString(value)
    require(String.eq(text, "1.0"), "QML constant property changed")
    Qt.Property.set(~preview(), self, "updated")
    value: Qt.QVariant <- Qt.QQmlProperty.read__QObject_String(root, "preview")
    text: String <- Qt.QVariant.toString(value)
    require(String.eq(text, "updated"), "STORED false disabled QML access or notification")

def objects() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +settings: Qt.ObjectType.Instance(Settings()) <- Qt.ObjectType.new(~Settings())
    +self: Qt.QObject = Qt.ObjectType.as_QObject(~Settings(), settings)
    Qt.Property.handleGetter(~title(), ~Qt.QObject, ~get_title, self, self)
    Qt.Property.handleSetter(~title(), ~Qt.QObject, ~set_title, self, self)
    Qt.Property.handleResetter(~theme(), ~Qt.QObject, ~reset_theme, self, self)
    Qt.Property.handleResetter(~automatic(), ~Qt.QObject, ~reset_automatic, self, self)
    Qt.Property.handleResetter(~failedReset(), ~Unit, ~reject_reset, self, Unit{})
    Qt.Property.writeStorage(~version(), self, "1.0")
    +counter: Qt.ObjectType.Instance(Counter()) <- Qt.ObjectType.new(~Counter())
    +observer: Qt.QObject = Qt.ObjectType.as_QObject(~Counter(), counter)
    connection: Qt.Connection <- Qt.Signal.connect(~titleChanged(), ~Qt.QObject, ~notified, self, observer)
    Qt.Property.set(~title(), self, "Bend")
    Qt.Property.set(~title(), self, "Bend")
    current_title: String <- Qt.Property.get(~title(), self)
    count: U32 <- Qt.Property.get(~events(), observer)
    require(String.eq(current_title, "Bend") && U32.is_eq(count, 1), "Custom setter notification changed")
    fixed: String <- Qt.Property.get(~version(), self)
    require(String.eq(fixed, "1.0"), "Constant initialization failed")
    refused: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.Property.writeStorage(~version(), self, "2.0"))
    expected(Unit, refused, 1)
    refused: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.Property.set(~version(), self, "2.0"))
    expected(Unit, refused, 1)
    Qt.Property.set(~theme(), self, "dark")
    Qt.Property.reset(~theme(), self)
    current: String <- Qt.Property.get(~theme(), self)
    require(String.eq(current, "system"), "Bend RESET did not run its handler")
    Qt.Property.set(~theme(), self, "light")
    theme_meta: Qt.QMetaProperty <- meta_property(self, "theme")
    reset: Bool <- Qt.QMetaProperty.reset(theme_meta, self)
    current: String <- Qt.Property.get(~theme(), self)
    require(reset && String.eq(current, "system"), "QMetaProperty RESET failed")
    Qt.Property.reset(~automatic(), self)
    current: String <- Qt.Property.get(~automatic(), self)
    require(String.eq(current, "automatic"), "Read-only property could not RESET")
    refused: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.Property.reset(~title(), self))
    expected(Unit, refused, 95)
    refused: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.Property.reset(~missingReset(), self))
    expected(Unit, refused, 38)
    refused: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.Property.reset(~failedReset(), self))
    expected(Unit, refused, 73)
    Qt.Property.set(~preview(), self, "temporary")
    transient: String <- Qt.Property.get(~preview(), self)
    require(String.eq(transient, "temporary"), "STORED false disabled backing storage")
    Qt.scoped(Unit, metadata(self))
    Qt.scoped(Unit, qml(self))

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, objects())
    count: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(count, 0) && U32.is_eq(connections, 0), "Property handlers or values leaked")
    Qt.Action.lift(Unit, IO.print("QT612_PROPERTIES_OK notify=1 constant=1 reset=1 qml=1 stored=1 failure=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
