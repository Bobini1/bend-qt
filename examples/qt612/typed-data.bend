import Base
import ../../packages/qt612/qt.bend as Qt

type Payload is Data:
  Payload{number: U32, text: String, samples: List<&2, U32>}

def delivered() -> Qt.Signal:
  Qt.Signal.define("delivered", [Qt.arg(~Payload)])

def received(probe: Qt.QObject, value: Payload) -> Qt.Action(Unit):
  match value:
    case Payload{number, text, samples}: Qt.QObject.setObjectName(probe, U32.show(number) ++ ": " ++ text)

def verify(ok: Bool) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, "Payload was changed")

def check(value: Payload) -> Qt.Action(Unit):
  match value:
    case Payload{number, text, samples}: verify(U32.is_eq(number, 42) && String.eq(text, "Bend") && U32.is_eq(U32.from_nat(List.length(&2, U32, samples)), 3))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +object: Qt.QObject <- Qt.QObject.newWithSignals("TypedDataExample", [delivered()])
    +probe: Qt.QObject <- Qt.QObject.new()
    connection: Qt.Connection <- Qt.Signal.connect(~delivered(), ~Qt.QObject, ~received, object, probe)
    Qt.Signal.emit(~delivered(), object, Payload{42, "Bend", [1, 2, 3]})
    name: String <- Qt.QObject.objectName(probe)
    Qt.Action.lift(Unit, IO.print(name))
    boxed: Qt.QVariant <- Qt.QVariant.fromData(~Payload, Payload{42, "Bend", [1, 2, 3]})
    value: Payload <- Qt.QVariant.toData(~Payload, boxed)
    check(value)
    Qt.Action.lift(Unit, IO.print("QT612_TYPED_DATA_OK"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
