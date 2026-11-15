import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def saved() -> Qt.Property:
  Qt.Property.define("saved", Qt.u32())

def pixel() -> Qt.Property:
  Qt.Property.define("pixel", Qt.u32())

def Model() -> Qt.QtObject:
  Qt.QObject.define("CanvasCallbackState", [saved(), pixel()])

def capture_body(+state: Qt.QObject, image: Qt.QImage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +kept: Qt.QImage <- Qt.QImage.keep(image)
    color: Qt.QColor <- Qt.QImage.pixelColor__Int32_Int32(kept, Qt.Int32{0}, Qt.Int32{0})
    rgba: U32 <- Qt.QColor.rgba(color)
    Qt.Property.store(~pixel(), state, rgba)
    Qt.Property.store(~saved(), state, Qt.QImage.word(kept))

def capture(state: Qt.QObject, image: Qt.QImage) -> Qt.Action(Unit):
  capture_body(state, image)

def refused(state: Unit, image: Qt.QImage) -> Qt.Action(Unit):
  Qt.Action.fail(Unit, 95, "Expected canvas capture failure")

def expected(result: Result<&1, &1, U32 & String, Unit>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 95), message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected canvas callback failure")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +fixture: Qt.QObject <- Qt.CallbackProbe.canvasFixture()
    +driver: Qt.QCanvasRhiPaintDriver <- Qt.CallbackProbe.canvasDriver(fixture)
    +canvas: Qt.QCanvasOffscreenCanvas <- Qt.CallbackProbe.canvasValue(fixture)
    +instance: Qt.QtObject.Instance(Model()) <- Qt.QtObject.new(~Model())
    +state: Qt.QObject = Qt.QtObject.as_QObject(~Model(), instance)
    Qt.QCanvasRhiPaintDriver.grabCanvasWithHandler(~Qt.QObject, ~capture, driver, canvas, state, state)
    +id: U32 <- Qt.Property.get(~saved(), state)
    require(Bool.not(U32.is_eq(id, 0)), "The native canvas callback did not run")
    +image: Qt.QImage = Qt.QImage{id}
    expectedPixel: U32 <- Qt.Property.get(~pixel(), state)
    result: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QCanvasRhiPaintDriver.grabCanvasWithHandler(~Unit, ~refused, driver, canvas, state, Unit{}))
    expected(result)
    Qt.QObject.destroy(fixture)
    Qt.CallbackProbe.churnReadback()
    width: Qt.Int32 <- Qt.QImage.width(image)
    require(U32.is_eq(Qt.Int32.word(width), 8), "A kept canvas capture lost its image storage")
    color: Qt.QColor <- Qt.QImage.pixelColor__Int32_Int32(image, Qt.Int32{0}, Qt.Int32{0})
    actualPixel: U32 <- Qt.QColor.rgba(color)
    require(U32.is_eq(actualPixel, expectedPixel), "A canvas capture still referenced Qt's released readback memory")
    Qt.Action.lift(Unit, IO.print("QT612_CANVAS_GRAB_CALLBACKS_OK native_null_rhi=1 image_snapshot=1 keep=1 failure=95"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.scoped(Unit, checks())))
