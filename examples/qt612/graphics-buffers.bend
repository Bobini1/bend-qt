import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def error(-A: Type, result: Result<&1, &1, U32 & String, A>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 34), "Wrong graphics buffer bound error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Invalid graphics buffer bound succeeded")

def bytes(value: List<&2, U32>) -> Bool:
  match value:
    case 0 <> 255 <> 65 <> 0 <> Nil{}: True{}
    case _: False{}

def readback(buffer: Qt.QOpenGLBuffer, +output: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    copied: Bool <- Qt.QOpenGLBuffer.read(buffer, Qt.Int32{0}, output, Qt.Int32{4})
    require(copied, "OpenGL byte read failed")
    values: List<&2, U32> <- Qt.QByteArray.toBytes(output)
    require(bytes(values), "OpenGL byte buffer changed its binary payload")

def upload(+buffer: Qt.QOpenGLBuffer, +source: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QOpenGLBuffer.allocate__QByteArray_Int32(buffer, source, Qt.Int32{4})
    bad: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QOpenGLBuffer.allocate__QByteArray_Int32(buffer, source, Qt.Int32{5}))
    error(Unit, bad)
    Qt.QOpenGLBuffer.write(buffer, Qt.Int32{0}, source, Qt.Int32{4})
    Qt.QByteArray.with(Unit, Qt.QByteArray.allocate(Qt.Int64{4, 0}), output => readback(buffer, output))

def buffer(+value: Qt.QOpenGLBuffer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    created: Bool <- Qt.QOpenGLBuffer.create(value)
    require(created, "OpenGL buffer creation failed")
    bound: Bool <- Qt.QOpenGLBuffer.bind(value)
    require(bound, "OpenGL buffer binding failed")
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes(0 <> 255 <> 65 <> 0 <> Nil{}), source => upload(value, source))

def generated_name(+functions: Qt.QOpenGLFunctions, +name: U32) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    require(Bool.not(U32.is_eq(name, 0)), "OpenGL output array did not contain a buffer name")
    Qt.QOpenGLFunctions.glBindBuffer(functions, 34962, name)
    exists: U32 <- Qt.QOpenGLFunctions.glIsBuffer(functions, name)
    require(Bool.not(U32.is_eq(exists, 0)), "Generated OpenGL buffer was invalid")
    Qt.QOpenGLFunctions.glDeleteBuffers(functions, Qt.Int32{1}, name <> Nil{})
    gone: U32 <- Qt.QOpenGLFunctions.glIsBuffer(functions, name)
    require(U32.is_eq(gone, 0), "OpenGL array deletion failed")

def generated(functions: Qt.QOpenGLFunctions, value: Qt.Outputs_List_U32) -> Qt.Action(Unit):
  match value:
    case Qt.Outputs_List_U32{name <> Nil{}}: generated_name(functions, name)
    case _: Qt.Action.fail(Unit, 1, "OpenGL output array changed its shape")

def arrays(+functions: Qt.QOpenGLFunctions) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    bad: Result<&1, &1, U32 & String, Qt.Outputs_List_U32> <- Qt.Action.attempt(Qt.Outputs_List_U32, Qt.QOpenGLFunctions.glGenBuffers(functions, Qt.Int32{2}, 0 <> Nil{}))
    error(Qt.Outputs_List_U32, bad)
    uniform: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QOpenGLFunctions.glUniform4fv(functions, Qt.Int32.neg(1), Qt.Int32{1}, Nil{}))
    error(Unit, uniform)
    Qt.Outputs_List_U32.with(Unit, Qt.QOpenGLFunctions.glGenBuffers(functions, Qt.Int32{1}, 0 <> Nil{}), value => generated(functions, value))

def context(+value: Qt.QOpenGLContext, surface: Qt.QSurface) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    created: Bool <- Qt.QOpenGLContext.create(value)
    require(created, "OpenGL context creation failed")
    current: Bool <- Qt.QOpenGLContext.makeCurrent(value, surface)
    require(current, "OpenGL context could not become current")
    Qt.QOpenGLBuffer.with(Unit, Qt.QOpenGLBuffer.new(), native => buffer(native))
    functions: Qt.QOpenGLFunctions <- Qt.QOpenGLContext.functions(value)
    arrays(functions)
    Qt.QOpenGLContext.doneCurrent(value)

def surface(+value: Qt.QOffscreenSurface) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QOffscreenSurface.create(value)
    Qt.QOpenGLContext.with(Unit, Qt.QOpenGLContext.new(), native => context(native, Qt.QOffscreenSurface.as_QSurface(value)))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QOffscreenSurface.with(Unit, Qt.QOffscreenSurface.new(), value => surface(value))
    count: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(count, 0), "Graphics buffers leaked native handles")
    Qt.Action.lift(Unit, IO.print("QT612_GRAPHICS_BUFFERS_OK byte_upload=1 byte_readback=1 typed_output_array=1 typed_input_array=1 extent_rejection=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
