import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def intrinsic(state: Unit, document: Qt.QTextDocument, position: Qt.Int32, format: Qt.QTextFormat) -> Qt.Action(Qt.QSizeF):
  do Qt.Action<Qt.QSizeF>:
    size: Qt.QSize <- Qt.QSize.new__Int32_Int32(Qt.Int32{19}, Qt.Int32{27})
    Qt.QSizeF.new__QSize(size)

def draw(state: Unit, painter: Qt.QPainter, rectangle: Qt.QRectF, document: Qt.QTextDocument, position: Qt.Int32, format: Qt.QTextFormat) -> Qt.Action(Unit):
  require(U32.is_ne(Qt.QPainter.word(painter), 0) && U32.is_ne(Qt.QTextDocument.word(document), 0), "Text callback lost native arguments")

def Parser() -> Qt.ObjectType:
  Qt.QPyQmlParserStatus.define("BendParserStatusHelper", [])

def begun(self: Qt.QObject) -> Qt.Action(Unit):
  Qt.QObject.setObjectName(self, "begun")

def complete(self: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +self: Qt.QObject = self
    name: String <- Qt.QObject.objectName(self)
    require(String.eq(name, "begun"), "Qt did not call classBegin before componentComplete")
    Qt.QObject.setObjectName(self, "complete")

def construct(state: Unit) -> Qt.Action(Qt.ObjectType.Instance(Parser())):
  do Qt.Action<Qt.ObjectType.Instance(Parser())>:
    +value: Qt.ObjectType.Instance(Parser()) <- Qt.QPyQmlParserStatus.newAs(~Parser())
    +native: Qt.QPyQmlParserStatus = Qt.ObjectType.asNativeBase(~Parser(), value)
    +interface: Qt.QQmlParserStatus = Qt.QPyQmlParserStatus.as_QQmlParserStatus(native)
    +self: Qt.QObject = Qt.QPyQmlParserStatus.as_QObject(native)
    Qt.QQmlParserStatus.Virtual.classBegin.handle(~Qt.QObject, ~begun, interface, self)
    Qt.QQmlParserStatus.Virtual.componentComplete.handle(~Qt.QObject, ~complete, interface, self)
    return value

def objects() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +text: Qt.QPyTextObject <- Qt.QPyTextObject.newOverride()
    +interface: Qt.QTextObjectInterface = Qt.QPyTextObject.as_QTextObjectInterface(text)
    Qt.QTextObjectInterface.Virtual.intrinsicSize.handle(~Unit, ~intrinsic, interface, Unit{})
    Qt.QTextObjectInterface.Virtual.drawObject.handle(~Unit, ~draw, interface, Unit{})
    good: U32 <- Qt.CallbackProbe.textObjectHelper(Qt.QPyTextObject.as_QObject(text))
    require(U32.is_eq(good, 1), "The text interface metadata, callback or document layout failed")
    +parser: Qt.QPyQmlParserStatus <- Qt.QPyQmlParserStatus.newOverride()
    +source: Qt.QPyQmlPropertyValueSource <- Qt.QPyQmlPropertyValueSource.newOverride()
    +container: Qt.QPyDesignerContainerExtension <- Qt.QPyDesignerContainerExtension.newOverride()
    +member: Qt.QPyDesignerMemberSheetExtension <- Qt.QPyDesignerMemberSheetExtension.newOverride()
    +property: Qt.QPyDesignerPropertySheetExtension <- Qt.QPyDesignerPropertySheetExtension.newOverride()
    +menu: Qt.QPyDesignerTaskMenuExtension <- Qt.QPyDesignerTaskMenuExtension.newOverride()
    good: U32 <- Qt.CallbackProbe.qobjectHelperInterfaces(Qt.QPyTextObject.as_QObject(text), Qt.QPyQmlParserStatus.as_QObject(parser), Qt.QPyQmlPropertyValueSource.as_QObject(source), Qt.QPyDesignerContainerExtension.as_QObject(container), Qt.QPyDesignerMemberSheetExtension.as_QObject(member), Qt.QPyDesignerPropertySheetExtension.as_QObject(property), Qt.QPyDesignerTaskMenuExtension.as_QObject(menu))
    require(U32.is_eq(good, 1), "A QObject/interface helper lost Q_INTERFACES or its pointer adjustment")
    +registration: Qt.Qml.Registration(Parser()) <- Qt.Qml.registerType(~Parser(), "Bend.NativeHelpers", 1, 0, "Parser")
    Qt.Qml.handleConstructor(~Parser(), ~Unit, ~construct, registration, Unit{})
    +engine: Qt.QQmlEngine <- Qt.QQmlEngine.new()
    +component: Qt.QQmlComponent <- Qt.QQmlComponent.new__QQmlEngine_QObject(engine, Qt.QObject{0})
    bytes: Qt.QByteArray <- Qt.QByteArray.fromUtf8("import Bend.NativeHelpers 1.0\nParser {}")
    url: Qt.QUrl <- Qt.QUrl.new()
    Qt.QQmlComponent.setData(component, bytes, url)
    ready: Bool <- Qt.QQmlComponent.isReady(component)
    require(ready, "The native parser-status type did not compile in QML")
    +root: Qt.QObject <- Qt.QQmlComponent.create__QQmlContext(component, Qt.QQmlContext{0})
    name: String <- Qt.QObject.objectName(root)
    require(String.eq(name, "complete"), "QML did not dispatch the parser-status lifecycle")
    +factory: Qt.QExtensionFactory <- Qt.QExtensionFactory.new()
    manager: Qt.QExtensionManager <- Qt.QExtensionFactory.extensionManager(factory)
    require(U32.is_eq(Qt.QExtensionManager.word(manager), 0), "The default extension factory had an unexpected manager")
    +delegate: Qt.QSqlRelationalDelegate <- Qt.QSqlRelationalDelegate.new()
    Qt.QObject.setObjectName(Qt.QSqlRelationalDelegate.as_QObject(delegate), "relational-delegate")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, objects())
    count: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(count, 0), "QObject/interface helper handles leaked")
    Qt.Action.lift(Unit, IO.print("QT612_QOBJECT_INTERFACE_HELPERS_OK interfaces=7 text=1 qml_parser=1 extension_factory=1 sql_delegate=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
