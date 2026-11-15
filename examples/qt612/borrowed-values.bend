import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def error(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong borrowed-value error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected checked borrowed-value failure")

def copied_gradient(value: Maybe<&2, Qt.QGradient>) -> Qt.Action(Unit):
  match value:
    case None{}: Qt.Action.fail(Unit, 1, "Gradient brush returned no gradient")
    case Some{gradient}:
      Qt.QGradient.with(Unit, Qt.Action.pure(Qt.QGradient, gradient), value => do Qt.Action<Unit>:
        kind: Qt.QGradient.Type <- Qt.QGradient.type(value)
        require(U32.is_eq(Qt.QGradient.Type.word(kind), Qt.QGradient.Type.word(Qt.QGradient.Type.LinearGradient())), "Gradient snapshot changed its type"))

def gradient_brush(+brush: Qt.QBrush) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    snapshot: Maybe<&2, Qt.QGradient> <- Qt.QBrush.gradient(brush)
    Qt.QBrush.destroy(brush)
    copied_gradient(snapshot)

def gradient(value: Qt.QLinearGradient) -> Qt.Action(Unit):
  Qt.QGradient.with(Unit, Qt.QLinearGradient.as_QGradient(value), base =>
    Qt.QBrush.with(Unit, Qt.QBrush.new__QGradient(base), brush => gradient_brush(brush)))

def empty_gradient(value: Maybe<&2, Qt.QGradient>) -> Qt.Action(Unit):
  match value:
    case None{}: Qt.Action.pure(Unit, Unit{})
    case Some{gradient}: Qt.Action.fail(Unit, 1, "Solid brush unexpectedly returned a gradient")

def solid(value: Qt.QBrush) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    snapshot: Maybe<&2, Qt.QGradient> <- Qt.QBrush.gradient(value)
    empty_gradient(snapshot)

def cursor_view(+view: Qt.QCursor) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QCursor.setShape(view, Qt.Qt.CursorShape.WaitCursor())
    Qt.QCursor.with(Unit, Qt.QGuiApplication.overrideCursor(), second => do Qt.Action<Unit>:
      shape: Qt.Qt.CursorShape <- Qt.QCursor.shape(second)
      require(U32.is_eq(Qt.Qt.CursorShape.word(shape), Qt.Qt.CursorShape.word(Qt.Qt.CursorShape.WaitCursor())), "Cursor view mutation did not reach Qt"))
    # The change input may itself alias the stack entry Qt is replacing.
    Qt.QGuiApplication.changeOverrideCursor(view)
    stale: Result<&1, &1, U32 & String, Qt.Qt.CursorShape> <- Qt.Action.attempt(Qt.Qt.CursorShape, Qt.QCursor.shape(view))
    error(Qt.Qt.CursorShape, stale, 116)
    Qt.QGuiApplication.restoreOverrideCursor()

def cursor(value: Qt.QCursor) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QGuiApplication.setOverrideCursor(value)
    Qt.QCursor.with(Unit, Qt.QGuiApplication.overrideCursor(), view => cursor_view(view))
    empty: Qt.QCursor <- Qt.QGuiApplication.overrideCursor()
    require(U32.is_eq(Qt.QCursor.word(empty), 0), "Override cursor stack did not empty")

def point_view(+event: Qt.QMouseEvent, +point: Qt.QEventPoint) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QEventPoint.setAccepted__Bool(point, False{})
    Qt.QEventPoint.with(Unit, Qt.QMouseEvent.pointById(event, Qt.Int32{0}), alias => do Qt.Action<Unit>:
      accepted: Bool <- Qt.QEventPoint.isAccepted(alias)
      require(Bool.not(accepted), "Event-point mutation did not reach the event"))
    denied: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QMouseEvent.destroy(event))
    error(Unit, denied, 16)

def mouse(+event: Qt.QMouseEvent) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QEventPoint.with(Unit, Qt.QMouseEvent.pointById(event, Qt.Int32{0}), point => point_view(event, point))
    absent: Qt.QEventPoint <- Qt.QMouseEvent.pointById(event, Qt.Int32{999})
    require(U32.is_eq(Qt.QEventPoint.word(absent), 0), "Missing event point did not return a null view")

def point(position: Qt.QPointF, device: Qt.QPointingDevice) -> Qt.Action(Unit):
  Qt.QMouseEvent.with(Unit, Qt.QMouseEvent.new__QEvent_Type_QPointF_Qt_MouseButton_Flags_Qt__MouseButton_Flags_Qt__KeyboardModifier_QPointingDevice(Qt.QEvent.Type.MouseMove(), position, Qt.Qt.MouseButton.NoButton(), Qt.Flags_Qt__MouseButton{0}, Qt.Flags_Qt__KeyboardModifier{0}, device), event => mouse(event))

def pointer_device(device: Qt.QPointingDevice) -> Qt.Action(Unit):
  Qt.QPointF.with(Unit, Qt.QPointF.new(), position => point(position, device))

def no_string(value: Maybe<&2, String>) -> Qt.Action(Unit):
  match value:
    case None{}: Qt.Action.pure(Unit, Unit{})
    case Some{text}: Qt.Action.fail(Unit, 1, "Unbacked stream unexpectedly returned a string")

def stream(value: Qt.QTextStream) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    snapshot: Maybe<&2, String> <- Qt.QTextStream.string(value)
    no_string(snapshot)

def present_string(value: Maybe<&2, String>, expected: String) -> Qt.Action(Unit):
  match value:
    case Some{text}: require(String.eq(text, expected), "Stream string snapshot changed")
    case None{}: Qt.Action.fail(Unit, 1, "String-backed stream returned no string")

def backing_member(+stream: Qt.QTextStream, +buffer: Qt.QStringBuffer) -> Qt.Action(Qt.QStringBuffer):
  do Qt.Action<Qt.QStringBuffer>:
    Qt.QTextStream.setString(stream, buffer, Qt.Flags_QIODeviceBase__OpenModeFlag{3})
    denied: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QStringBuffer.destroy(buffer))
    error(Unit, denied, 16)
    return buffer

def string_backing(+stream: Qt.QTextStream) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +buffer: Qt.QStringBuffer <- Qt.QStringBuffer.with(Qt.QStringBuffer, Qt.QStringBuffer.new("backing"), value => backing_member(stream, value))
    snapshot: Maybe<&2, String> <- Qt.QTextStream.string(stream)
    present_string(snapshot, "backing")
    Qt.QStringBuffer.replace(buffer, "changed")
    second: Maybe<&2, String> <- Qt.QTextStream.string(stream)
    present_string(second, "changed")
    Qt.QTextStream.setString(stream, Qt.QStringBuffer{0}, Qt.Flags_QIODeviceBase__OpenModeFlag{3})
    stale: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QStringBuffer.value(buffer))
    error(String, stale, 116)

def backing_constructor(buffer: Qt.QStringBuffer) -> Qt.Action(Unit):
  Qt.QTextStream.with(Unit, Qt.QTextStream.new__QStringBuffer_Flags_QIODeviceBase__OpenModeFlag(buffer, Qt.Flags_QIODeviceBase__OpenModeFlag{1}), value => do Qt.Action<Unit>:
    snapshot: Maybe<&2, String> <- Qt.QTextStream.string(value)
    present_string(snapshot, "constructor"))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QLinearGradient.with(Unit, Qt.QLinearGradient.new(), gradient)
    Qt.QBrush.with(Unit, Qt.QBrush.new(), solid)
    Qt.QCursor.with(Unit, Qt.QCursor.new(), cursor)
    Qt.QPointingDevice.with(Unit, Qt.QPointingDevice.new(), pointer_device)
    Qt.QTextStream.with(Unit, Qt.QTextStream.new(), stream)
    Qt.QTextStream.with(Unit, Qt.QTextStream.new(), value => string_backing(value))
    Qt.QStringBuffer.with(Unit, Qt.QStringBuffer.new("constructor"), backing_constructor)
    objects: U32 <- Qt.Runtime.liveObjects()
    pins: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(pins, 0), "Borrowed values leaked handles or retention pins")
    Qt.Action.lift(Unit, IO.print("QT612_BORROWED_VALUES_OK gradient_snapshot=1 cursor_view=1 cursor_expiry=1 event_point_view=1 null_string=1 objects=0 pins=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
