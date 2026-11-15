import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def first() -> Qt.Property:
  Qt.Property.withBindable(Qt.Property.define("first", Qt.QWebSocketCorsAuthenticator.valueArg()), True{})

def second() -> Qt.Property:
  Qt.Property.withBindable(Qt.Property.define("second", Qt.QWebSocketCorsAuthenticator.valueArg()), True{})

def delivered() -> Qt.Signal:
  Qt.Signal.define("delivered", [Qt.QWebSocketCorsAuthenticator.valueArg()])

def Holder() -> Qt.QtObject:
  Qt.QtObject.withSignals(Qt.QObject.define("ExplicitCopyValues", [first(), second()]), [delivered()])

def copied_body(+probe: Qt.QObject, +value: Qt.QWebSocketCorsAuthenticator) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    origin: String <- Qt.QWebSocketCorsAuthenticator.origin(value)
    require(String.eq(origin, "https://bend.example"), "Explicit-copy signal lost its value")
    Qt.QWebSocketCorsAuthenticator.setAllowed(value, True{})
    Qt.QObject.setObjectName(probe, "copied")

def copied(probe: Qt.QObject, value: Qt.QWebSocketCorsAuthenticator) -> Qt.Action(Unit):
  copied_body(probe, value)

def cases() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +source: Qt.QWebSocketCorsAuthenticator <- Qt.QWebSocketCorsAuthenticator.new__String("https://bend.example")
    Qt.QWebSocketCorsAuthenticator.setAllowed(source, False{})
    +holder: Qt.QtObject.Instance(Holder()) <- Qt.QtObject.new(~Holder())
    +self: Qt.QObject = Qt.QtObject.as_QObject(~Holder(), holder)
    +probe: Qt.QObject <- Qt.QObject.new()
    Qt.Property.set(~first(), self, source)
    Qt.Property.bind(~second(), ~first(), self, self)
    +target: Qt.QWebSocketCorsAuthenticator <- Qt.Property.get(~second(), self)
    origin: String <- Qt.QWebSocketCorsAuthenticator.origin(target)
    require(String.eq(origin, "https://bend.example"), "Explicit-copy property binding lost its value")
    +boxed: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.QWebSocketCorsAuthenticator.valueArg(), target)
    +unboxed: Qt.QWebSocketCorsAuthenticator <- Qt.QVariant.toValue(~Qt.QWebSocketCorsAuthenticator.valueArg(), boxed)
    origin: String <- Qt.QWebSocketCorsAuthenticator.origin(unboxed)
    require(String.eq(origin, "https://bend.example"), "Explicit-copy QVariant lost its value")
    connection: Qt.Connection <- Qt.Signal.connect(~delivered(), ~Qt.QObject, ~copied, self, probe)
    Qt.Signal.emit(~delivered(), self, source)
    name: String <- Qt.QObject.objectName(probe)
    require(String.eq(name, "copied"), "Explicit-copy signal was not delivered")
    allowed: Bool <- Qt.QWebSocketCorsAuthenticator.allowed(source)
    require(Bool.not(allowed), "A value signal changed its explicit-copy source")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, cases())
    live: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(live, 0), "Explicit-copy values leaked resources")
    Qt.Action.lift(Unit, IO.print("QT612_EXPLICIT_COPY_VALUES_OK property=1 binding=1 variant=1 signal=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
