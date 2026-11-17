import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

# Empty instance data with a count of 1 does not fit the native stride.
def instance_buffer(count: U32, output: Maybe<&2, Qt.Int32>) -> Qt.Action(Qt.CallbackReply_QByteArray_Optional_Int32):
  do Qt.Action<Qt.CallbackReply_QByteArray_Optional_Int32>:
    bytes: Qt.QByteArray <- Qt.QByteArray.fromBytes(Nil{})
    return Qt.CallbackReply_QByteArray_Optional_Int32{bytes, Some{Qt.Int32{count}}}

def rejected(result: Result<&1, &1, U32 & String, U32>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 22), "Wrong instance buffer bounds error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Empty instance data was accepted with a nonzero count")

def instance_demo(count: U32, instance: Qt.QQuick3DInstancing) -> Qt.Action(Unit):
  match count:
    case 0:
      do Qt.Action<Unit>:
        valid: U32 <- Qt.CallbackProbe.instancing(instance)
        require(U32.is_eq(valid, 1), "The empty instance buffer or count was lost")
    case _:
      do Qt.Action<Unit>:
        invalid: Result<&1, &1, U32 & String, U32> <- Qt.Action.attempt(U32, Qt.CallbackProbe.instancing(instance))
        rejected(invalid)

def installed(+count: U32, +instance: Qt.QQuick3DInstancing) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQuick3DInstancing.Virtual.getInstanceBuffer.handle(~U32, ~instance_buffer, instance, count)
    instance_demo(count, instance)

def run(+count: U32) -> Qt.Action(Unit):
  Qt.QQuick3DInstancing.with(Unit, Qt.QQuick3DInstancing.newOverride(), instance => installed(count, instance))

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    run(0)
    run(1)
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Instance handlers leaked byte arrays or overrides")
    Qt.Action.lift(Unit, IO.print("QT612_INSTANCING_CALLBACKS_OK output_count=1 native_stride_bounds=1 rejected_before_commit=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
