import Base
import ../../packages/qt612/qt.bend as Qt

type Payload is Data:
  Payload{serial: U32, label: String, values: List<&2, U32>}

type Other is Data:
  Other{serial: U32}

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def payload() -> Payload:
  Payload{41, "Bend", [1, 2, 3]}

def check_payload(value: Payload, serial: U32, label: String) -> Qt.Action(Unit):
  match value:
    case Payload{actual, text, values}:
      match values:
        case 1 <> 2 <> 3 <> Nil{}:
          require(U32.is_eq(actual, serial) && String.eq(text, label), "Opaque payload changed during transport")
        case _: Qt.Action.fail(Unit, 1, "Nested opaque payload data changed")

def delivered() -> Qt.Signal:
  Qt.Signal.define("delivered", [Qt.arg(~Payload)])

def data_property() -> Qt.Property:
  Qt.Property.define("payload", Qt.arg(~Payload))

def map_property() -> Qt.Property:
  Qt.Property.define("map", Qt.variantMap())

def echo_method() -> Qt.Method:
  Qt.Method.define("echo", [Qt.arg(~Payload)], Qt.arg(~Payload))

def Holder() -> Qt.QtObject:
  Qt.QtObject.withMethods(
    Qt.QtObject.withSignals(Qt.QObject.define("BendOpaqueHolder", [data_property(), map_property()]), [delivered()]),
    [echo_method()])

def echo(state: Unit, value: Payload) -> Qt.Action(Payload):
  match value:
    case Payload{serial, label, values}: Qt.Action.pure(Payload, Payload{(serial + 1 : U32), label ++ "!", values})

def received(probe: Qt.QObject, value: Payload) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    check_payload(value, 41, "Bend")
    Qt.QObject.setObjectName(probe, "received")

def rejected(-A: Type, value: Result<&1, &1, U32 & String, A>) -> Qt.Action(Unit):
  match value:
    case Fail{(code, text)}: require(U32.is_eq(code, 22), "Wrong opaque type mismatch error: " ++ text)
    case Done{value}: Qt.Action.fail(Unit, 1, "An incompatible opaque payload was accepted")

def variants() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +boxed: Qt.QVariant <- Qt.QVariant.fromData(~Payload, payload())
    value: Payload <- Qt.QVariant.toData(~Payload, boxed)
    check_payload(value, 41, "Bend")
    wrong: Result<&1, &1, U32 & String, Other> <- Qt.Action.attempt(Other, Qt.QVariant.toData(~Other, boxed))
    rejected(Other, wrong)
    integer: Qt.QVariant <- Qt.QVariant.fromData(~U32, 42)
    number: U32 <- Qt.QVariant.toData(~U32, integer)
    require(U32.is_eq(number, 42), "A primitive opaque payload changed")
    list: Qt.QVariant <- Qt.QVariant.fromData(~List<&2, U32>, [1, 2])
    mismatch: Result<&1, &1, U32 & String, List<&2, String>> <- Qt.Action.attempt(List<&2, String>, Qt.QVariant.toData(~List<&2, String>, list))
    rejected(List<&2, String>, mismatch)

def churn(count: Nat) -> Qt.Action(Unit):
  match count:
    case 0n: Qt.Action.pure(Unit, Unit{})
    case 1n+rest:
      do Qt.Action<Unit>:
        Qt.QVariant.with(Unit, Qt.QVariant.fromData(~Payload, payload()),
          value => Qt.CallbackProbe.opaqueDropOnWorker(value))
        churn(rest)

def qml(+holder: Qt.QObject, +root: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Signal.emit(~delivered(), holder, payload())
    stored: Qt.QVariant <- Qt.QQmlProperty.read__QObject_String(root, "saved")
    value: Payload <- Qt.QVariant.toData(~Payload, stored)
    check_payload(value, 41, "Bend")
    answer: Qt.QVariant <- Qt.QQmlProperty.read__QObject_String(root, "answer")
    result: Payload <- Qt.QVariant.toData(~Payload, answer)
    check_payload(result, 42, "Bend!")
    mapped: Qt.QVariant <- Qt.QQmlProperty.read__QObject_String(root, "mapped")
    map_value: Payload <- Qt.QVariant.toData(~Payload, mapped)
    check_payload(map_value, 41, "Bend")

def engine(+holder: Qt.QObject, +engine: Qt.QQmlEngine) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    context: Qt.QQmlContext <- Qt.QQmlEngine.rootContext(engine)
    Qt.QQmlContext.setContextProperty__String_QObject(context, "holder", holder)
    +component: Qt.QQmlComponent <- Qt.QQmlComponent.new__QQmlEngine_QObject(engine, Qt.QObject{0})
    url: Qt.QUrl <- Qt.QUrl.new()
    source: Qt.QByteArray <- Qt.QByteArray.fromUtf8(
      "import QtQml\nQtObject { property var saved; property var answer; property var mapped: holder.map.data; Component.onCompleted: { holder.delivered.connect(function(value) { saved=value; answer=holder.echo(value); }); } }")
    Qt.QQmlComponent.setData(component, source, url)
    ready: Bool <- Qt.QQmlComponent.isReady(component)
    require(ready, "Opaque payload QML component did not compile")
    root: Qt.QObject <- Qt.QQmlComponent.create__QQmlContext(component, Qt.QQmlContext{0})
    qml(holder, root)

def objects() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    holder: Qt.QtObject.Instance(Holder()) <- Qt.QtObject.newWith(~Holder(), Qt.QObject.newOverride())
    +object: Qt.QObject = Qt.QtObject.as_QObject(~Holder(), holder)
    Qt.Method.handle(~echo_method(), ~Unit, ~echo, object, Unit{})
    Qt.Property.set(~data_property(), object, payload())
    boxed: Qt.QVariant <- Qt.QVariant.fromData(~Payload, payload())
    Qt.Property.set(~map_property(), object, [Qt.PairValue{"data", boxed}])
    copied: Payload <- Qt.Property.get(~data_property(), object)
    check_payload(copied, 41, "Bend")
    reply: Payload <- Qt.Method.call(~echo_method(), object, payload())
    check_payload(reply, 42, "Bend!")
    +probe: Qt.QObject <- Qt.QObject.new()
    connection: Qt.Connection <- Qt.Signal.connect(~delivered(), ~Qt.QObject, ~received, object, probe)
    Qt.Signal.emit(~delivered(), object, payload())
    seen: String <- Qt.QObject.objectName(probe)
    require(String.eq(seen, "received"), "Bend signal did not receive its opaque payload")
    Qt.QObject.setObjectName(probe, "waiting")
    worker_value: Qt.QVariant <- Qt.QVariant.fromData(~Payload, payload())
    Qt.CallbackProbe.opaqueSignalFromWorker(object, worker_value)
    Qt.CallbackProbe.opaqueFlush()
    delivered: String <- Qt.QObject.objectName(probe)
    require(String.eq(delivered, "received"), "Queued signal did not retain its opaque payload")
    qml_engine: Qt.QQmlEngine <- Qt.QQmlEngine.new()
    engine(object, qml_engine)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, variants())
    Qt.scoped(Unit, objects())
    churn(5000n)
    live: U32 <- Qt.Runtime.liveData()
    require(U32.is_eq(live, 0), "Opaque Bend value references leaked")
    Qt.Action.lift(Unit, IO.print("QT612_OPAQUE_DATA_OK typed=1 generic_types=1 wrong_type_rejected=1 signals=1 properties=1 methods=1 maps=1 qml_roundtrip=1 queued=1 worker_destruction=1 churn=5000 live_data=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
