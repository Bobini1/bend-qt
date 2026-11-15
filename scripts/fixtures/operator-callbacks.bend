import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def populate(+holder: Qt.Shared_Qt3DRender__QTextureImageData) -> Qt.Action(Qt.Shared_Qt3DRender__QTextureImageData):
  do Qt.Action<Qt.Shared_Qt3DRender__QTextureImageData>:
    value: Qt.Qt3DRender.QTextureImageData <- Qt.Shared_Qt3DRender__QTextureImageData.data(holder)
    Qt.Qt3DRender.QTextureImageData.setWidth(value, Qt.Int32{16})
    return holder

def image(state: Unit) -> Qt.Action(Qt.Shared_Qt3DRender__QTextureImageData):
  do Qt.Action<Qt.Shared_Qt3DRender__QTextureImageData>:
    holder: Qt.Shared_Qt3DRender__QTextureImageData <- Qt.Shared_Qt3DRender__QTextureImageData.create()
    populate(holder)

def equal(state: Unit, other: Qt.Qt3DRender.QTextureImageDataGenerator) -> Qt.Action(Bool):
  Qt.Action.pure(Bool, True{})

def installed(+generator: Qt.Qt3DRender.QTextureImageDataGenerator) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Qt3DRender.QTextureImageDataGenerator.Virtual.operator__.handle(~Unit, ~image, generator, Unit{})
    Qt.Qt3DRender.QTextureImageDataGenerator.Virtual.operator____Qt3DRender_QTextureImageDataGenerator.handle(~Unit, ~equal, generator, Unit{})

# Qt calls the operators on its own thread too: the handlers then run on the
# main thread while the probe runs a Qt event loop.
def generator_demo(+generator: Qt.Qt3DRender.QTextureImageDataGenerator) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    installed(generator)
    direct: U32 <- Qt.CallbackProbe.operators(generator, False{})
    require(U32.is_eq(direct, 1), "Virtual operators or the returned shared value failed")
    threaded: U32 <- Qt.CallbackProbe.operators(generator, True{})
    require(U32.is_eq(threaded, 1), "Operators called on another thread did not reach the handlers")

def stale(result: Result<&1, &1, U32 & String, Unit>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 116), "Native shared deletion answered the wrong error")
    case Done{value}: Qt.Action.fail(Unit, 1, "The shared override stayed live after its last native release")

def shared_holder(+holder: Qt.Shared_Qt3DRender__QTextureImageDataGenerator) -> Qt.Action(Qt.Qt3DRender.QTextureImageDataGenerator):
  do Qt.Action<Qt.Qt3DRender.QTextureImageDataGenerator>:
    +generator: Qt.Qt3DRender.QTextureImageDataGenerator <- Qt.Shared_Qt3DRender__QTextureImageDataGenerator.data(holder)
    installed(generator)
    Qt.CallbackProbe.retainGenerator(holder)
    return generator

def shared_demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    generator: Qt.Qt3DRender.QTextureImageDataGenerator <- Qt.Shared_Qt3DRender__QTextureImageDataGenerator.with(Qt.Qt3DRender.QTextureImageDataGenerator, Qt.Shared_Qt3DRender__QTextureImageDataGenerator.newOverride(), holder => shared_holder(holder))
    valid: U32 <- Qt.CallbackProbe.releaseGenerator()
    require(U32.is_eq(valid, 1), "The shared override lost its handlers after Bend released its holder")
    result: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.Qt3DRender.QTextureImageDataGenerator.destroy(generator))
    stale(result)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Qt3DRender.QTextureImageDataGenerator.with(Unit, Qt.Qt3DRender.QTextureImageDataGenerator.newOverride(), generator => generator_demo(generator))
    shared_demo()
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Virtual operators leaked shared or native handles")
    Qt.Action.lift(Unit, IO.print("QT612_OPERATOR_CALLBACKS_OK function_call=1 equality=1 shared_native_value=1 thread_calls=1 native_shared_proxy=1 thread_final_release=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
