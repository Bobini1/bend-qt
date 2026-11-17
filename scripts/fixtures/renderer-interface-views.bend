import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expired(result: Result<&1, &1, U32 & String, Qt.QSGRendererInterface.GraphicsApi>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 116), "Wrong renderer view expiry: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Renderer view survived its supplying window")

def windows() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +first: Qt.QQuickWindow <- Qt.QQuickWindow.new()
    +second: Qt.QQuickWindow <- Qt.QQuickWindow.new()
    +left: Qt.QSGRendererInterface <- Qt.QQuickWindow.rendererInterface(first)
    +right: Qt.QSGRendererInterface <- Qt.QQuickWindow.rendererInterface(second)
    before: Qt.QSGRendererInterface.GraphicsApi <- Qt.QSGRendererInterface.graphicsApi(left)
    +expected: U32 = Qt.QSGRendererInterface.GraphicsApi.word(before)
    Qt.QQuickWindow.destroy(first)
    stale: Result<&1, &1, U32 & String, Qt.QSGRendererInterface.GraphicsApi> <- Qt.Action.attempt(Qt.QSGRendererInterface.GraphicsApi, Qt.QSGRendererInterface.graphicsApi(left))
    expired(stale)
    after: Qt.QSGRendererInterface.GraphicsApi <- Qt.QSGRendererInterface.graphicsApi(right)
    require(U32.is_eq(expected, Qt.QSGRendererInterface.GraphicsApi.word(after)), "A second window lost its renderer view")
    Qt.QSGRendererInterface.release(right)
    fresh: Qt.QSGRendererInterface <- Qt.QQuickWindow.rendererInterface(second)
    again: Qt.QSGRendererInterface.GraphicsApi <- Qt.QSGRendererInterface.graphicsApi(fresh)
    require(U32.is_eq(expected, Qt.QSGRendererInterface.GraphicsApi.word(again)), "Releasing a renderer view destroyed Qt's implementation")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Render.useGuiThread()
    Qt.scoped(Unit, windows())
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Renderer views left native handles alive")
    Qt.Action.lift(Unit, IO.print("QT_RENDERER_INTERFACE_VIEWS_OK owner_expiry=1 independent_windows=1 release_keeps_qt_alive=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
