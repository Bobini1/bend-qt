import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def frame(value: Qt.Qt3DAnimation.QKeyFrame, x: U32, y: U32) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    point: Qt.QVector2D <- Qt.Qt3DAnimation.QKeyFrame.coordinates(value)
    +integers: Qt.QPoint <- Qt.QVector2D.toPoint(point)
    actual_x: Qt.Int32 <- Qt.QPoint.x(integers)
    actual_y: Qt.Int32 <- Qt.QPoint.y(integers)
    require(U32.is_eq(Qt.Int32.word(actual_x), x) && U32.is_eq(Qt.Int32.word(actual_y), y), "Key frame snapshot changed coordinates")

def frames(values: List<&2, Qt.Qt3DAnimation.QKeyFrame>) -> Qt.Action(Unit):
  match values:
    case first <> second <> Nil{}:
      do Qt.Action<Unit>:
        frame(first, 2, 3)
        frame(second, 5, 7)
    case _: Qt.Action.fail(Unit, 1, "Key frame traversal lost an element")

def empty(values: List<&2, Qt.Qt3DAnimation.QKeyFrame>) -> Qt.Action(Unit):
  match values:
    case Nil{}: Qt.Action.pure(Unit, Unit{})
    case _: Qt.Action.fail(Unit, 1, "Empty component returned a key frame")

def range_error(result: Result<&1, &1, U32 & String, Qt.Qt3DAnimation.QKeyFrame>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 34), message)
    case Done{value}: Qt.Action.fail(Unit, 1, "One-past key frame was dereferenced")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +component: Qt.Qt3DAnimation.QChannelComponent <- Qt.Qt3DAnimation.QChannelComponent.new()
    values: List<&2, Qt.Qt3DAnimation.QKeyFrame> <- Qt.Qt3DAnimation.QChannelComponent.keyFrames(component)
    empty(values)
    invalid: Result<&1, &1, U32 & String, Qt.Qt3DAnimation.QKeyFrame> <- Qt.Action.attempt(Qt.Qt3DAnimation.QKeyFrame,
      Qt.Qt3DAnimation.QChannelComponent.keyFrameAt(component, Qt.Int32{0}))
    range_error(invalid)
    integers: Qt.QPoint <- Qt.QPoint.new__Int32_Int32(Qt.Int32{2}, Qt.Int32{3})
    coordinates: Qt.QVector2D <- Qt.QVector2D.new__QPoint(integers)
    value: Qt.Qt3DAnimation.QKeyFrame <- Qt.Qt3DAnimation.QKeyFrame.new__QVector2D(coordinates)
    Qt.Qt3DAnimation.QChannelComponent.appendKeyFrame(component, value)
    integers: Qt.QPoint <- Qt.QPoint.new__Int32_Int32(Qt.Int32{5}, Qt.Int32{7})
    coordinates: Qt.QVector2D <- Qt.QVector2D.new__QPoint(integers)
    value: Qt.Qt3DAnimation.QKeyFrame <- Qt.Qt3DAnimation.QKeyFrame.new__QVector2D(coordinates)
    Qt.Qt3DAnimation.QChannelComponent.appendKeyFrame(component, value)
    values: List<&2, Qt.Qt3DAnimation.QKeyFrame> <- Qt.Qt3DAnimation.QChannelComponent.keyFrames(component)
    one: Qt.Qt3DAnimation.QKeyFrame <- Qt.Qt3DAnimation.QChannelComponent.keyFrameAt(component, Qt.Int32{1})
    invalid: Result<&1, &1, U32 & String, Qt.Qt3DAnimation.QKeyFrame> <- Qt.Action.attempt(Qt.Qt3DAnimation.QKeyFrame,
      Qt.Qt3DAnimation.QChannelComponent.keyFrameAt(component, Qt.Int32{2}))
    range_error(invalid)
    Qt.Qt3DAnimation.QChannelComponent.clearKeyFrames(component)
    Qt.Qt3DAnimation.QChannelComponent.destroy(component)
    frames(values)
    frame(one, 5, 7)
    Qt.Action.lift(Unit, IO.print("QT612_CORE_KEYFRAMES_OK owning_sequence=1 checked_index=1 empty=1 one_past_rejected=1 source_independent=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
