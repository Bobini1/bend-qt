import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expected(-A: Type, result: Result<&1, &1, U32 & String, A>, code: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(actual, message)}: require(U32.is_eq(actual, code), message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected property schema rejection")

def expected_text(value: Maybe<&2, String>, expected: String) -> Qt.Action(Unit):
  match value:
    case Some{text}: require(String.eq(text, expected), "ClassInfo was lost")
    case None{}: Qt.Action.fail(Unit, 1, "ClassInfo value is null")

def meta_property(self: Qt.QObject, name: String) -> Qt.Action(Qt.QMetaProperty):
  do Qt.Action<Qt.QMetaProperty>:
    +meta: Qt.QMetaObject <- Qt.QObject.metaObject(self)
    +index: Qt.Int32 <- Qt.QMetaObject.indexOfProperty(meta, name)
    require(U32.is_ne(Qt.Int32.word(index), 4294967295), "Missing property metadata")
    Qt.QMetaObject.property(meta, index)

def changed() -> Qt.Signal:
  Qt.Signal.define("textUpdated", [Qt.string()])

def title() -> Qt.Property:
  Qt.Property.withNotify(Qt.Property.define("title", Qt.string()), changed())

def hidden() -> Qt.Property:
  Qt.Property.withScriptable(Qt.Property.withDesignable(Qt.Property.define("hidden", Qt.string()), False{}), False{})

def user() -> Qt.Property:
  Qt.Property.withUser(Qt.Property.define("user", Qt.string()), True{})

def silent() -> Qt.Property:
  Qt.Property.withoutNotify(Qt.Property.define("silent", Qt.string()))

def virtualText() -> Qt.Property:
  Qt.Property.withVirtual(Qt.Property.define("virtualText", Qt.string()), True{})

def finalText() -> Qt.Property:
  Qt.Property.withFinal(Qt.Property.define("finalText", Qt.string()), True{})

def Parent() -> Qt.ObjectType:
  Qt.QObject.define("PropertyAttributeParent", [virtualText(), finalText()])

def Child() -> Qt.ObjectType:
  Qt.ObjectType.derive(~Parent(), "PropertyAttributeChild", [Qt.Property.withOverride(Qt.Property.define("virtualText", Qt.string()), True{})])

def Grandchild() -> Qt.ObjectType:
  Qt.ObjectType.derive(~Child(), "PropertyAttributeGrandchild", [Qt.Property.withOverride(Qt.Property.define("virtualText", Qt.string()), True{})])

def invalidFinal() -> Qt.ObjectType:
  Qt.ObjectType.derive(~Parent(), "PropertyAttributeInvalidFinal", [Qt.Property.define("finalText", Qt.string())])

def invalidOverride() -> Qt.ObjectType:
  Qt.QObject.define("PropertyAttributeInvalidOverride", [Qt.Property.withOverride(Qt.Property.define("missing", Qt.string()), True{})])

def invalidNotifier() -> Qt.ObjectType:
  Qt.QObject.define("PropertyAttributeInvalidNotify", [Qt.Property.withNotify(Qt.Property.define("wrong", Qt.string()), Qt.Signal.define("wrongChanged", [Qt.int32()]))])

def invalidConstant() -> Qt.ObjectType:
  Qt.QObject.define("PropertyAttributeInvalidConstant", [Qt.Property.withNotify(Qt.Property.constant("fixed", Qt.string()), changed())])

def Flags() -> Qt.ObjectType:
  Qt.ObjectType.withClassInfo(Qt.ObjectType.withSignals(Qt.QObject.define("PropertyAttributeFlags", [title(), hidden(), user(), silent()]), [changed()]), "Purpose", "property coverage")

def Namespaced() -> Qt.ObjectType:
  Qt.QObject.define("BendCoverage::Namespaced", [Qt.Property.define("value", Qt.string())])

def notified(self: Qt.QObject, value: String) -> Qt.Action(Unit):
  Qt.QObject.setObjectName(self, value)

def metadata() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    namespaced: Qt.ObjectType.Instance(Namespaced()) <- Qt.ObjectType.new(~Namespaced())
    +qualified: Qt.QObject = Qt.ObjectType.as_QObject(~Namespaced(), namespaced)
    Qt.Property.set(~Qt.Property.define("value", Qt.string()), qualified, "qualified")
    qualified_value: String <- Qt.Property.get(~Qt.Property.define("value", Qt.string()), qualified)
    require(String.eq(qualified_value, "qualified"), "A qualified QObject class name was rejected")
    instance: Qt.ObjectType.Instance(Flags()) <- Qt.ObjectType.new(~Flags())
    +self: Qt.QObject = Qt.ObjectType.as_QObject(~Flags(), instance)
    hidden_meta: Qt.QMetaProperty <- meta_property(self, "hidden")
    +hidden_property: Qt.QMetaProperty = hidden_meta
    designable: Bool <- Qt.QMetaProperty.isDesignable(hidden_property)
    scriptable: Bool <- Qt.QMetaProperty.isScriptable(hidden_property)
    require(Bool.not(designable || scriptable), "DESIGNABLE or SCRIPTABLE false was ignored")
    silent_meta: Qt.QMetaProperty <- meta_property(self, "silent")
    has_notify: Bool <- Qt.QMetaProperty.hasNotifySignal(silent_meta)
    require(Bool.not(has_notify), "A property without NOTIFY acquired a signal")
    +meta: Qt.QMetaObject <- Qt.QObject.metaObject(self)
    user_meta: Qt.QMetaProperty <- Qt.QMetaObject.userProperty(meta)
    user_flag: Bool <- Qt.QMetaProperty.isUser(user_meta)
    require(user_flag, "USER metadata was ignored")
    info_index: Qt.Int32 <- Qt.QMetaObject.indexOfClassInfo(meta, "Purpose")
    info: Qt.QMetaClassInfo <- Qt.QMetaObject.classInfo(meta, info_index)
    info_value: Maybe<&2, String> <- Qt.QMetaClassInfo.value(info)
    expected_text(info_value, "property coverage")
    +probe: Qt.QObject <- Qt.QObject.new()
    connection: Qt.Connection <- Qt.Signal.connect(~changed(), ~Qt.QObject, ~notified, self, probe)
    Qt.Property.set(~title(), self, "new value")
    received: String <- Qt.QObject.objectName(probe)
    require(String.eq(received, "new value"), "NOTIFY did not carry the new property value")
    Qt.Property.set(~silent(), self, "quiet")
    refused: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.Property.notify(~silent(), self))
    expected(Unit, refused, 95)
    child: Qt.ObjectType.Instance(Grandchild()) <- Qt.ObjectType.new(~Grandchild())
    +derived: Qt.QObject = Qt.ObjectType.as_QObject(~Grandchild(), child)
    Qt.Property.set(~virtualText(), derived, "overridden")
    text: String <- Qt.Property.get(~virtualText(), derived)
    require(String.eq(text, "overridden"), "Property override resolved the base field")
    override_meta: Qt.QMetaProperty <- meta_property(derived, "virtualText")
    override_flag: Bool <- Qt.QMetaProperty.isOverride(override_meta)
    require(override_flag, "OVERRIDE metadata was ignored")
    final_meta: Qt.QMetaProperty <- meta_property(derived, "finalText")
    final_flag: Bool <- Qt.QMetaProperty.isFinal(final_meta)
    require(final_flag, "FINAL metadata was ignored")
    refused: Result<&1, &1, U32 & String, Qt.ObjectType.Instance(invalidFinal())> <- Qt.Action.attempt(Qt.ObjectType.Instance(invalidFinal()), Qt.ObjectType.new(~invalidFinal()))
    expected(Qt.ObjectType.Instance(invalidFinal()), refused, 1)
    refused: Result<&1, &1, U32 & String, Qt.ObjectType.Instance(invalidOverride())> <- Qt.Action.attempt(Qt.ObjectType.Instance(invalidOverride()), Qt.ObjectType.new(~invalidOverride()))
    expected(Qt.ObjectType.Instance(invalidOverride()), refused, 22)
    refused: Result<&1, &1, U32 & String, Qt.ObjectType.Instance(invalidNotifier())> <- Qt.Action.attempt(Qt.ObjectType.Instance(invalidNotifier()), Qt.ObjectType.new(~invalidNotifier()))
    expected(Qt.ObjectType.Instance(invalidNotifier()), refused, 22)
    refused: Result<&1, &1, U32 & String, Qt.ObjectType.Instance(invalidConstant())> <- Qt.Action.attempt(Qt.ObjectType.Instance(invalidConstant()), Qt.ObjectType.new(~invalidConstant()))
    expected(Qt.ObjectType.Instance(invalidConstant()), refused, 22)

def future() -> Qt.Property:
  Qt.Property.withRevision(Qt.Property.define("future", Qt.string()), 1)

def versioned() -> Qt.Property:
  Qt.Property.withVersionRevision(Qt.Property.define("versioned", Qt.string()), 2, 3)

def Revisioned() -> Qt.ObjectType:
  Qt.QObject.define("PropertyAttributeRevisioned", [future(), versioned()])

def requiredName() -> Qt.Property:
  Qt.Property.withRequired(Qt.Property.define("requiredName", Qt.string()), True{})

def Required() -> Qt.ObjectType:
  Qt.QObject.define("PropertyAttributeRequired", [requiredName()])

def DefaultContent() -> Qt.ObjectType:
  Qt.ObjectType.withDefaultProperty(Qt.QObject.define("PropertyAttributeDefaultContent", [Qt.Property.define("content", Qt.qobject())]), "content")

def qml_component(engine: Qt.QQmlEngine, source: String) -> Qt.Action(Qt.QQmlComponent):
  do Qt.Action<Qt.QQmlComponent>:
    +component: Qt.QQmlComponent <- Qt.QQmlComponent.new__QQmlEngine_QObject(engine, Qt.QObject{0})
    data: Qt.QByteArray <- Qt.QByteArray.fromUtf8(source)
    url: Qt.QUrl <- Qt.QUrl.new()
    Qt.QQmlComponent.setData(component, data, url)
    Qt.Action.pure(Qt.QQmlComponent, component)

def qml() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    registration0: Qt.Qml.Registration(Revisioned()) <- Qt.Qml.registerTypeRevision(~Revisioned(), "Bend.PropertyAttributes", 1, 0, "Revisioned", 0)
    registration1: Qt.Qml.Registration(Revisioned()) <- Qt.Qml.registerTypeRevision(~Revisioned(), "Bend.PropertyAttributes", 1, 1, "Revisioned", 1)
    registration2: Qt.Qml.Registration(Required()) <- Qt.Qml.registerType(~Required(), "Bend.PropertyAttributes", 1, 0, "Required")
    registration3: Qt.Qml.Registration(Flags()) <- Qt.Qml.registerType(~Flags(), "Bend.PropertyAttributes", 1, 0, "Flags")
    registration4: Qt.Qml.Registration(DefaultContent()) <- Qt.Qml.registerType(~DefaultContent(), "Bend.PropertyAttributes", 1, 0, "DefaultContent")
    +engine: Qt.QQmlEngine <- Qt.QQmlEngine.new__QObject(Qt.QObject{0})
    rejected: Qt.QQmlComponent <- qml_component(engine, "import Bend.PropertyAttributes 1.0\nRevisioned { future: 'hidden' }")
    error: Bool <- Qt.QQmlComponent.isError(rejected)
    require(error, "A revised property leaked into an older QML import")
    hidden_component: Qt.QQmlComponent <- qml_component(engine, "import Bend.PropertyAttributes 1.0\nFlags { hidden: 'private' }")
    hidden_error: Bool <- Qt.QQmlComponent.isError(hidden_component)
    require(hidden_error, "SCRIPTABLE false remained writable from QML")
    +accepted: Qt.QQmlComponent <- qml_component(engine, "import Bend.PropertyAttributes 1.1\nRevisioned { future: 'visible' }")
    ready: Bool <- Qt.QQmlComponent.isReady(accepted)
    require(ready, "A revised property was unavailable in its QML revision")
    +root: Qt.QObject <- Qt.QQmlComponent.create__QQmlContext(accepted, Qt.QQmlContext{0})
    text: String <- Qt.Property.get(~future(), root)
    require(String.eq(text, "visible"), "Revised QML property write failed")
    +future_meta: Qt.QMetaProperty <- meta_property(root, "future")
    revision: Qt.Int32 <- Qt.QMetaProperty.revision(future_meta)
    require(U32.is_eq(Qt.Int32.word(revision), 65281), "Minor revision encoding changed")
    notify: Qt.QMetaMethod <- Qt.QMetaProperty.notifySignal(future_meta)
    notify_revision: Qt.Int32 <- Qt.QMetaMethod.revision(notify)
    require(U32.is_eq(Qt.Int32.word(notify_revision), 65281), "NOTIFY revision was lost")
    version_meta: Qt.QMetaProperty <- meta_property(root, "versioned")
    revision: Qt.Int32 <- Qt.QMetaProperty.revision(version_meta)
    require(U32.is_eq(Qt.Int32.word(revision), 515), "Version revision encoding changed")
    +missing: Qt.QQmlComponent <- qml_component(engine, "import Bend.PropertyAttributes 1.0\nRequired {}")
    absent: Qt.QObject <- Qt.QQmlComponent.create__QQmlContext(missing, Qt.QQmlContext{0})
    require(U32.is_eq(Qt.QObject.word(absent), 0), "QML created an object without its REQUIRED property")
    +complete: Qt.QQmlComponent <- qml_component(engine, "import Bend.PropertyAttributes 1.0\nRequired { requiredName: 'present' }")
    +valid: Qt.QObject <- Qt.QQmlComponent.create__QQmlContext(complete, Qt.QQmlContext{0})
    text: String <- Qt.Property.get(~requiredName(), valid)
    require(String.eq(text, "present"), "QML could not initialize REQUIRED")
    required_meta: Qt.QMetaProperty <- meta_property(valid, "requiredName")
    required_flag: Bool <- Qt.QMetaProperty.isRequired(required_meta)
    require(required_flag, "REQUIRED metadata was ignored")
    +default_component: Qt.QQmlComponent <- qml_component(engine, "import QtQml\nimport Bend.PropertyAttributes 1.0\nDefaultContent { QtObject { objectName: 'default child' } }")
    default_ready: Bool <- Qt.QQmlComponent.isReady(default_component)
    require(default_ready, "QML did not recognize the declared default property")
    default_root: Qt.QObject <- Qt.QQmlComponent.create__QQmlContext(default_component, Qt.QQmlContext{0})
    child: Qt.QObject <- Qt.Property.get(~Qt.Property.define("content", Qt.qobject()), default_root)
    child_name: String <- Qt.QObject.objectName(child)
    require(String.eq(child_name, "default child"), "QML default property lost its child")
    invalid_revision: Result<&1, &1, U32 & String, Qt.Qml.Registration(Revisioned())> <- Qt.Action.attempt(Qt.Qml.Registration(Revisioned()),
      Qt.Qml.registerTypeVersionRevision(~Revisioned(), "Bend.PropertyAttributes.Invalid", 1, 0, "Invalid", 65535, 1))
    expected(Qt.Qml.Registration(Revisioned()), invalid_revision, 34)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, metadata())
    Qt.scoped(Unit, qml())
    live: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(live, 0) && U32.is_eq(connections, 0), "Property attributes leaked resources")
    Qt.Action.lift(Unit, IO.print("QT612_PROPERTY_ATTRIBUTES_OK flags=1 notify=1 inheritance=1 revisions=1 required=1 classinfo=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
