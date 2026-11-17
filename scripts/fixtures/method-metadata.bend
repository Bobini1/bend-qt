import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def compose() -> Qt.Method:
  Qt.Method.withRevision(
    Qt.Method.withTag(
      Qt.Method.withArgumentNames(
        Qt.Method.define("compose", [Qt.string(), Qt.int32()], Qt.string()),
        ["text", "count"]),
      "RPC"),
    2)

def invokable() -> Qt.Method:
  Qt.Method.withInvokable(Qt.Method.define("direct", [], Qt.string()), True{})

def private_method() -> Qt.Method:
  Qt.Method.withAccess(Qt.Method.define("privateMethod", [], Qt.unit()), Qt.QMetaMethod.Access.Private())

def protected_method() -> Qt.Method:
  Qt.Method.withAccess(Qt.Method.define("protectedMethod", [], Qt.unit()), Qt.QMetaMethod.Access.Protected())

def versioned() -> Qt.Method:
  Qt.Method.withVersionRevision(Qt.Method.define("versioned", [], Qt.unit()), 3, 4)

def Subject() -> Qt.ObjectType:
  Qt.ObjectType.withMethods(Qt.QObject.define("MethodMetadataSubject", []), [compose(), invokable(), private_method(), protected_method(), versioned()])

def Derived() -> Qt.ObjectType:
  Qt.ObjectType.withMethods(Qt.ObjectType.derive(~Subject(), "MethodMetadataDerived", []), [compose()])

def InheritedOnly() -> Qt.ObjectType:
  Qt.ObjectType.derive(~Subject(), "MethodMetadataInheritedOnly", [])

def compose_value(state: Unit, text: String, count: Qt.Int32) -> Qt.Action(String):
  Qt.Action.pure(String, text ++ U32.show(Qt.Int32.word(count)))

def direct_value(state: Unit) -> Qt.Action(String):
  Qt.Action.pure(String, "direct")

def initialize(state: Unit, value: Qt.ObjectType.Instance(Subject())) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +self: Qt.QObject = Qt.ObjectType.as_QObject(~Subject(), value)
    Qt.Method.handle(~compose(), ~Unit, ~compose_value, self, Unit{})
    Qt.Method.handle(~invokable(), ~Unit, ~direct_value, self, Unit{})

def derived_value(state: Unit, text: String, count: Qt.Int32) -> Qt.Action(String):
  Qt.Action.pure(String, "derived-" ++ text ++ U32.show(Qt.Int32.word(count)))

def initialize_derived(state: Unit, value: Qt.ObjectType.Instance(Derived())) -> Qt.Action(Unit):
  Qt.Method.handle(~compose(), ~Unit, ~derived_value, Qt.ObjectType.as_QObject(~Derived(), value), Unit{})

def meta_method(self: Qt.QObject, signature: String) -> Qt.Action(Qt.QMetaMethod):
  do Qt.Action<Qt.QMetaMethod>:
    +meta: Qt.QMetaObject <- Qt.QObject.metaObject(self)
    +index: Qt.Int32 <- Qt.QMetaObject.indexOfMethod(meta, signature)
    require(U32.is_ne(Qt.Int32.word(index), 4294967295), "Method metadata is missing")
    Qt.QMetaObject.method(meta, index)

def tag(value: Maybe<&2, String>) -> Qt.Action(Unit):
  match value:
    case Some{text}: require(String.eq(text, "RPC"), "Method tag changed")
    case None{}: Qt.Action.fail(Unit, 1, "Method tag is missing")

def names(values: List<&2, Qt.QByteArray>) -> Qt.Action(Unit):
  match values:
    case first <> second <> Nil{}:
      do Qt.Action<Unit>:
        a: String <- Qt.QByteArray.utf8(first)
        b: String <- Qt.QByteArray.utf8(second)
        require(String.eq(a, "text") && String.eq(b, "count"), "Method argument names changed")
    case _: Qt.Action.fail(Unit, 1, "Method argument-name count changed")

def inspect(+self: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +method: Qt.QMetaMethod <- meta_method(self, "compose(QString,int)")
    value: Maybe<&2, String> <- Qt.QMetaMethod.tag(method)
    tag(value)
    values: List<&2, Qt.QByteArray> <- Qt.QMetaMethod.parameterNames(method)
    names(values)
    revision: Qt.Int32 <- Qt.QMetaMethod.revision(method)
    require(U32.is_eq(Qt.Int32.word(revision), 65282), "Minor method revision changed")
    access: Qt.QMetaMethod.Access <- Qt.QMetaMethod.access(method)
    require(U32.is_eq(Qt.QMetaMethod.Access.word(access), Qt.QMetaMethod.Access.word(Qt.QMetaMethod.Access.Public())), "Default method access changed")
    kind: Qt.QMetaMethod.MethodType <- Qt.QMetaMethod.methodType(method)
    require(U32.is_eq(Qt.QMetaMethod.MethodType.word(kind), Qt.QMetaMethod.MethodType.word(Qt.QMetaMethod.MethodType.Slot())), "Default method is not a slot")
    direct: Qt.QMetaMethod <- meta_method(self, "direct()")
    kind: Qt.QMetaMethod.MethodType <- Qt.QMetaMethod.methodType(direct)
    require(U32.is_eq(Qt.QMetaMethod.MethodType.word(kind), Qt.QMetaMethod.MethodType.word(Qt.QMetaMethod.MethodType.Method())), "Invokable method is not an ordinary method")
    private: Qt.QMetaMethod <- meta_method(self, "privateMethod()")
    access: Qt.QMetaMethod.Access <- Qt.QMetaMethod.access(private)
    require(U32.is_eq(Qt.QMetaMethod.Access.word(access), Qt.QMetaMethod.Access.word(Qt.QMetaMethod.Access.Private())), "Private method access changed")
    protected: Qt.QMetaMethod <- meta_method(self, "protectedMethod()")
    access: Qt.QMetaMethod.Access <- Qt.QMetaMethod.access(protected)
    require(U32.is_eq(Qt.QMetaMethod.Access.word(access), Qt.QMetaMethod.Access.word(Qt.QMetaMethod.Access.Protected())), "Protected method access changed")
    version: Qt.QMetaMethod <- meta_method(self, "versioned()")
    revision: Qt.Int32 <- Qt.QMetaMethod.revision(version)
    require(U32.is_eq(Qt.Int32.word(revision), 772), "Versioned method revision changed")

def qml(+version: U32, expected: String) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +engine: Qt.QQmlEngine <- Qt.QQmlEngine.new()
    +component: Qt.QQmlComponent <- Qt.QQmlComponent.new__QQmlEngine_QObject(engine, Qt.QObject{0})
    source: Qt.QByteArray <- Qt.QByteArray.fromUtf8("import Bend.MethodMetadata 1." ++ U32.show(version) ++ "\nSubject { property string result: typeof compose === 'function' ? compose('qml', 4) : 'hidden'; property string directResult: direct() }")
    url: Qt.QUrl <- Qt.QUrl.new()
    Qt.QQmlComponent.setData(component, source, url)
    ready: Bool <- Qt.QQmlComponent.isReady(component)
    require(ready, "Method metadata QML did not compile")
    +root: Qt.QObject <- Qt.QQmlComponent.create__QQmlContext(component, Qt.QQmlContext{0})
    result: Qt.QVariant <- Qt.QQmlProperty.read__QObject_String(root, "result")
    value: String <- Qt.QVariant.toString(result)
    require(String.eq(value, expected), "QML ignored method revision")
    result: Qt.QVariant <- Qt.QQmlProperty.read__QObject_String(root, "directResult")
    value: String <- Qt.QVariant.toString(result)
    require(String.eq(value, "direct"), "QML could not call invokable method")

def invalid_result(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(+code, message)}: require(U32.is_eq(code, expected), "Wrong method rejection " ++ U32.show(code) ++ ": " ++ message)
    case Done{object}: Qt.Action.fail(Unit, 1, "Invalid method attributes were accepted")

def invalid(~schema: Qt.ObjectType, expected: U32) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    result: Result<&1, &1, U32 & String, Qt.ObjectType.Instance(schema)> <- Qt.Action.attempt(Qt.ObjectType.Instance(schema), Qt.ObjectType.new(~schema))
    invalid_result(Qt.ObjectType.Instance(schema), result, expected)

def qml_derived() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +registration: Qt.Qml.Registration(Derived()) <- Qt.Qml.registerTypeRevision(~Derived(), "Bend.DerivedMethodMetadata", 1, 0, "Derived", 2)
    Qt.Qml.handleCreate(~Derived(), ~Unit, ~initialize_derived, registration, Unit{})
    +engine: Qt.QQmlEngine <- Qt.QQmlEngine.new()
    +component: Qt.QQmlComponent <- Qt.QQmlComponent.new__QQmlEngine_QObject(engine, Qt.QObject{0})
    source: Qt.QByteArray <- Qt.QByteArray.fromUtf8("import Bend.DerivedMethodMetadata 1.0\nDerived { property string result: compose('qml', 5) }")
    url: Qt.QUrl <- Qt.QUrl.new()
    Qt.QQmlComponent.setData(component, source, url)
    ready: Bool <- Qt.QQmlComponent.isReady(component)
    require(ready, "Derived method QML did not compile")
    root: Qt.QObject <- Qt.QQmlComponent.create__QQmlContext(component, Qt.QQmlContext{0})
    result: Qt.QVariant <- Qt.QQmlProperty.read__QObject_String(root, "result")
    value: String <- Qt.QVariant.toString(result)
    require(String.eq(value, "derived-qml5"), "QML did not route the overriding method")

def cases() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +subject: Qt.ObjectType.Instance(Subject()) <- Qt.ObjectType.new(~Subject())
    initialize(Unit{}, subject)
    +self: Qt.QObject = Qt.ObjectType.as_QObject(~Subject(), subject)
    text: String <- Qt.Method.call(~compose(), self, "bend", Qt.Int32{3})
    require(String.eq(text, "bend3"), "Metadata changed Bend method dispatch")
    Qt.scoped(Unit, inspect(self))
    +older: Qt.Qml.Registration(Subject()) <- Qt.Qml.registerTypeRevision(~Subject(), "Bend.MethodMetadata", 1, 0, "Subject", 0)
    Qt.Qml.handleCreate(~Subject(), ~Unit, ~initialize, older, Unit{})
    +newer: Qt.Qml.Registration(Subject()) <- Qt.Qml.registerTypeRevision(~Subject(), "Bend.MethodMetadata", 1, 1, "Subject", 2)
    Qt.Qml.handleCreate(~Subject(), ~Unit, ~initialize, newer, Unit{})
    Qt.scoped(Unit, qml(0, "hidden"))
    Qt.scoped(Unit, qml(1, "qml4"))
    +derived: Qt.ObjectType.Instance(Derived()) <- Qt.ObjectType.new(~Derived())
    initialize_derived(Unit{}, derived)
    text: String <- Qt.ObjectType.call(~Derived(), ~compose(), derived, "bend", Qt.Int32{6})
    require(String.eq(text, "derived-bend6"), "Bend did not route the overriding method")
    invoked: Bool <- Qt.CallbackProbe.parentMethodDispatch(Qt.ObjectType.as_QObject(~Derived(), derived))
    require(invoked, "A parent QMetaMethod did not invoke the child override")
    +inherited: Qt.ObjectType.Instance(InheritedOnly()) <- Qt.ObjectType.new(~InheritedOnly())
    +child: Qt.QObject = Qt.ObjectType.as_QObject(~InheritedOnly(), inherited)
    Qt.Method.handle(~compose(), ~Unit, ~derived_value, child, Unit{})
    invoked: Bool <- Qt.CallbackProbe.parentMethodDispatch(child)
    require(invoked, "A parent QMetaMethod did not invoke an inherited handler")
    Qt.scoped(Unit, qml_derived())
    invalid(~Qt.ObjectType.withMethods(Qt.QObject.define("BadMethodNamesCount", []), [Qt.Method.withArgumentNames(Qt.Method.define("bad", [Qt.string(), Qt.int32()], Qt.unit()), ["one"])]), 22)
    invalid(~Qt.ObjectType.withMethods(Qt.QObject.define("BadMethodName", []), [Qt.Method.withArgumentNames(Qt.Method.define("bad", [Qt.string()], Qt.unit()), ["bad-name"])]), 22)
    invalid(~Qt.ObjectType.withMethods(Qt.QObject.define("BadMethodRevision", []), [Qt.Method.withRevision(Qt.Method.define("bad", [], Qt.unit()), 255)]), 34)
    invalid(~Qt.ObjectType.withMethods(Qt.QObject.define("BadMethodVersion", []), [Qt.Method.withVersionRevision(Qt.Method.define("bad", [], Qt.unit()), 255, 0)]), 34)
    invalid(~Qt.ObjectType.withMethods(Qt.QObject.define("BadMethodVersionSentinel", []), [Qt.Method.withVersionRevision(Qt.Method.define("bad", [], Qt.unit()), 65535, 0)]), 34)
    invalid(~Qt.ObjectType.withMethods(Qt.QObject.define("BadMethodAccess", []), [Qt.Method.withAccess(Qt.Method.define("bad", [], Qt.unit()), Qt.QMetaMethod.Access{3})]), 22)
    invalid(~Qt.ObjectType.withMethods(Qt.ObjectType.derive(~Subject(), "BadMethodOverrideResult", []), [Qt.Method.define("compose", [Qt.string(), Qt.int32()], Qt.u32())]), 22)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, cases())
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Method metadata fixtures leaked")
    Qt.Action.lift(Unit, IO.print("QT612_METHOD_METADATA_OK names=1 tag=1 revisions=1 access=1 invokable=1 override=1 parent_invoke=1 inherited_handler=1 qml=1 validation=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
