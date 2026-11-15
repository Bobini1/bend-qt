import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def offsets(value: Qt.Outputs_String_Int32_Int32, expected: String, start: U32, end: U32) -> Qt.Action(Unit):
  match value:
    case Qt.Outputs_String_Int32_Int32{text, left, right}:
      do Qt.Action<Unit>:
        require(String.eq(text, expected), "Accessible text output changed")
        require(U32.is_eq(Qt.Int32.word(left), start), "Accessible start offset changed")
        require(U32.is_eq(Qt.Int32.word(right), end), "Accessible end offset changed")

def text_demo(+text: Qt.QAccessibleTextInterface) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    attrs: Qt.Outputs_String_Int32_Int32 <- Qt.QAccessibleTextInterface.attributes(text, Qt.Int32{3})
    offsets(attrs, "weight:bold", 2, 9)
    +selection: Qt.Outputs_Int32_Int32 <- Qt.QAccessibleTextInterface.selection(text, Qt.Int32{0})
    require(U32.is_eq(Qt.Int32.word(Qt.Outputs_Int32_Int32.arg0(selection)), 1), "Accessible selection start changed")
    require(U32.is_eq(Qt.Int32.word(Qt.Outputs_Int32_Int32.arg1(selection)), 4), "Accessible selection end changed")
    before: Qt.Outputs_String_Int32_Int32 <- Qt.QAccessibleTextInterface.textBeforeOffset(text, Qt.Int32{4}, Qt.QAccessible.TextBoundaryType.CharBoundary())
    offsets(before, "l", 3, 4)
    at: Qt.Outputs_String_Int32_Int32 <- Qt.QAccessibleTextInterface.textAtOffset(text, Qt.Int32{4}, Qt.QAccessible.TextBoundaryType.CharBoundary())
    offsets(at, "o", 4, 5)
    after: Qt.Outputs_String_Int32_Int32 <- Qt.QAccessibleTextInterface.textAfterOffset(text, Qt.Int32{4}, Qt.QAccessible.TextBoundaryType.CharBoundary())
    offsets(after, " ", 5, 6)

def number(value: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    text: String <- Qt.QByteArray.utf8(value)
    require(String.eq(text, "4294967295"), "Restored unsigned overload lost its range")

def machine(value: Qt.QStateMachine) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    animations: List<&2, Qt.QAbstractAnimation> <- Qt.QStateMachine.defaultAnimations(value)
    require(U32.is_eq(U32.from_nat(List.length(&2, Qt.QAbstractAnimation, animations)), 0), "Default animation list was not empty")

def busy(result: Result<&1, &1, U32 & String, Unit>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 16), "Retained event argument returned the wrong error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Event argument was destroyed while retained")

def event_fields(+first: Qt.QWidget, +second: Qt.QWidget, +data: Qt.QMimeData, +event: Qt.QGraphicsSceneDragDropEvent) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QGraphicsSceneDragDropEvent.setMimeData(event, data)
    Qt.QGraphicsSceneDragDropEvent.setSource(event, first)
    Qt.QGraphicsSceneEvent.setWidget(Qt.QGraphicsSceneDragDropEvent.as_QGraphicsSceneEvent(event), second)
    blocked_data: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QMimeData.destroy(data))
    busy(blocked_data)
    blocked_first: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QWidget.destroy(first))
    busy(blocked_first)
    blocked_second: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QWidget.destroy(second))
    busy(blocked_second)
    Qt.QGraphicsSceneDragDropEvent.setSource(event, second)
    Qt.QWidget.destroy(first)
    Qt.QGraphicsSceneEvent.setWidget(Qt.QGraphicsSceneDragDropEvent.as_QGraphicsSceneEvent(event), Qt.QWidget{0})
    still_source: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QWidget.destroy(second))
    busy(still_source)
    Qt.QGraphicsSceneDragDropEvent.setSource(event, Qt.QWidget{0})
    Qt.QWidget.destroy(second)
    Qt.QGraphicsSceneDragDropEvent.setMimeData(event, Qt.QMimeData{0})
    Qt.QMimeData.destroy(data)

def event_data(first: Qt.QWidget, second: Qt.QWidget, data: Qt.QMimeData) -> Qt.Action(Unit):
  Qt.QGraphicsSceneDragDropEvent.with(Unit, Qt.QGraphicsSceneDragDropEvent.new(), event => event_fields(first, second, data, event))

def event_widgets(first: Qt.QWidget, second: Qt.QWidget) -> Qt.Action(Unit):
  Qt.QMimeData.with(Unit, Qt.QMimeData.new(), data => event_data(first, second, data))

def retained_events(first: Qt.QWidget) -> Qt.Action(Unit):
  Qt.QWidget.with(Unit, Qt.QWidget.new(), second => event_widgets(first, second))

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    sensor: String <- Qt.QAccelerometer.Fields.sensorType()
    require(String.eq(sensor, "QAccelerometer"), "Sensor identifier snapshot changed")
    gyro: String <- Qt.QGyroscope.Fields.sensorType()
    require(String.eq(gyro, "QGyroscope"), "Discovered sensor identifier snapshot changed")
    h2: String <- Qt.QSslConfiguration.Fields.ALPNProtocolHTTP2()
    require(String.eq(h2, "h2"), "HTTP/2 protocol snapshot changed")
    http: String <- Qt.QSslConfiguration.Fields.NextProtocolHttp1_1()
    require(String.eq(http, "http/1.1"), "HTTP/1 protocol snapshot changed")
    Qt.QAccessibleTextInterface.with(Unit, Qt.Fixture.text(), value => text_demo(value))
    Qt.QByteArray.with(Unit, Qt.QByteArray.number__U32_Int32(4294967295, Qt.Int32{10}), number)
    Qt.QStateMachine.with(Unit, Qt.QStateMachine.new(), machine)
    Qt.QWidget.with(Unit, Qt.QWidget.new(), retained_events)
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Restored declarations leaked native handles")
    retentions: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(retentions, 0), "Restored event setters leaked dependencies")
    Qt.Action.lift(Unit, IO.print("QT612_RESTORED_NATIVE_OK accessible_outputs=1 native_boundaries=1 static_strings=1 numeric_overloads=1 typed_collections=1 retained_event_setters=1 objects=0 retentions=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
