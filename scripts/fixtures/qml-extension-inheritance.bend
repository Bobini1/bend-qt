import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def base_value() -> Qt.Property:
  Qt.Property.define("baseValue", Qt.string())

def child_value() -> Qt.Property:
  Qt.Property.define("childValue", Qt.string())

def BaseExtension() -> Qt.QtObject:
  Qt.QObject.define("InheritedBaseExtension", [base_value()])

def ChildExtension() -> Qt.QtObject:
  Qt.QObject.define("InheritedChildExtension", [child_value()])

def BaseObject() -> Qt.QtObject:
  Qt.QtObject.withExtension(Qt.QObject.define("InheritedBaseObject", []), BaseExtension())

def ChildObject() -> Qt.QtObject:
  Qt.QtObject.withExtension(Qt.QtObject.derive(~BaseObject(), "InheritedChildObject", []), ChildExtension())

def objects() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +base_registration: Qt.QObject <- Qt.Qml.registerType(~BaseObject(), "Bend.InheritedExtensions", 1, 0, "BaseObject")
    +child_registration: Qt.QObject <- Qt.Qml.registerType(~ChildObject(), "Bend.InheritedExtensions", 1, 0, "ChildObject")
    +engine: Qt.QQmlEngine <- Qt.QQmlEngine.new()
    +component: Qt.QQmlComponent <- Qt.QQmlComponent.new__QQmlEngine_QObject(engine, Qt.QObject{0})
    source: Qt.QByteArray <- Qt.QByteArray.fromUtf8("import Bend.InheritedExtensions 1.0\nChildObject { baseValue: 'base'; childValue: 'child' }")
    url: Qt.QUrl <- Qt.QUrl.new()
    Qt.QQmlComponent.setData(component, source, url)
    ready: Bool <- Qt.QQmlComponent.isReady(component)
    require(ready, "QML did not inherit the base extension")
    +root: Qt.QObject <- Qt.QQmlComponent.create__QQmlContext(component, Qt.QQmlContext{0})
    child: Qt.QtObject.Instance(ChildObject()) <- Qt.QtObject.cast(~ChildObject(), root)
    base: Qt.QtObject.Instance(BaseObject()) <- Qt.QtObject.cast(~BaseObject(), root)
    child_extension: Qt.QtObject.Instance(ChildExtension()) <- Qt.Qml.extension(~ChildObject(), child_registration, child)
    child_text: String <- Qt.Property.get(~child_value(), Qt.QtObject.as_QObject(~ChildExtension(), child_extension))
    require(String.eq(child_text, "child"), "The derived extension changed")
    base_extension: Qt.QtObject.Instance(BaseExtension()) <- Qt.Qml.extension(~BaseObject(), base_registration, base)
    base_text: String <- Qt.Property.get(~base_value(), Qt.QtObject.as_QObject(~BaseExtension(), base_extension))
    require(String.eq(base_text, "base"), "The inherited extension changed")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, objects())
    live: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(live, 0), "Inherited extensions leaked")
    Qt.Action.lift(Unit, IO.print("QT612_QML_EXTENSION_INHERITANCE_OK base=1 child=1 typed_access=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
