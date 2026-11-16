import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def changed() -> Qt.Signal:
  Qt.Signal.withArgumentNames(Qt.Signal.define("changé", [Qt.string()]), ["valeur"])

def name() -> Qt.Property:
  Qt.Property.withNotify(Qt.Property.define("prénom", Qt.string()), changed())

def Card() -> Qt.ObjectType:
  Qt.ObjectType.withSignals(Qt.QObject.define("Élément", [name()]), [changed()])

def notified(self: Qt.QObject, value: String) -> Qt.Action(Unit):
  Qt.QObject.setObjectName(self, value)

def objects() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    instance: Qt.ObjectType.Instance(Card()) <- Qt.ObjectType.new(~Card())
    +self: Qt.QObject = Qt.ObjectType.as_QObject(~Card(), instance)
    +probe: Qt.QObject <- Qt.QObject.new()
    connection: Qt.Connection <- Qt.Signal.connect(~changed(), ~Qt.QObject, ~notified, self, probe)
    Qt.Property.set(~name(), self, "Élodie")
    read: String <- Qt.Property.get(~name(), self)
    heard: String <- Qt.QObject.objectName(probe)
    require(String.eq(read, "Élodie") && String.eq(heard, "Élodie"), "Unicode property or notification failed")
    registration: Qt.Qml.Registration(Card()) <- Qt.Qml.registerType(~Card(), "Bend.Unicode", 1, 0, "Élément")
    +engine: Qt.QQmlEngine <- Qt.QQmlEngine.new__QObject(Qt.QObject{0})
    context: Qt.QQmlContext <- Qt.QQmlEngine.rootContext(engine)
    Qt.QQmlContext.setContextProperty__String_QObject(context, "personne", self)
    +component: Qt.QQmlComponent <- Qt.QQmlComponent.new__QQmlEngine_QObject(engine, Qt.QObject{0})
    data: Qt.QByteArray <- Qt.QByteArray.fromUtf8("import Bend.Unicode 1.0\nÉlément { prénom: personne.prénom }")
    url: Qt.QUrl <- Qt.QUrl.new()
    Qt.QQmlComponent.setData(component, data, url)
    ready: Bool <- Qt.QQmlComponent.isReady(component)
    require(ready, "Unicode QML element or property did not compile")
    +root: Qt.QObject <- Qt.QQmlComponent.create__QQmlContext(component, Qt.QQmlContext{0})
    initial: String <- Qt.Property.get(~name(), root)
    require(String.eq(initial, "Élodie"), "Unicode QML property initialization failed")
    Qt.Property.set(~name(), self, "Łucja")
    updated: String <- Qt.Property.get(~name(), root)
    require(String.eq(updated, "Łucja"), "Unicode QML property binding did not update")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, objects())
    live: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(live, 0) && U32.is_eq(connections, 0), "Unicode metadata leaked")
    Qt.Action.lift(Unit, IO.print("QT612_UNICODE_METADATA_OK names=1 native=1 qml=1 notify=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
