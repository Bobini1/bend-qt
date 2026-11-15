import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def check(result: Qt.Outputs_Bool_QGraphicsItem, panel: Qt.QGraphicsItem) -> Qt.Action(Unit):
  match result:
    case Qt.Outputs_Bool_QGraphicsItem{result, output0}:
      require(result && U32.is_eq(Qt.QGraphicsItem.word(output0), Qt.QGraphicsItem.word(panel)), "Modal panel output did not preserve native identity")

def scene(+scene: Qt.QGraphicsScene, +target: Qt.QGraphicsRectItem, +panel: Qt.QGraphicsRectItem) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QGraphicsScene.addItem(scene, Qt.QGraphicsRectItem.as_QGraphicsItem(target))
    Qt.QGraphicsScene.addItem(scene, Qt.QGraphicsRectItem.as_QGraphicsItem(panel))
    Qt.QGraphicsRectItem.setFlag__QGraphicsItem_GraphicsItemFlag_Bool(panel, Qt.QGraphicsItem.GraphicsItemFlag.ItemIsPanel(), True{})
    Qt.QGraphicsRectItem.setPanelModality(panel, Qt.QGraphicsItem.PanelModality.SceneModal())
    result: Qt.Outputs_Bool_QGraphicsItem <- Qt.QGraphicsItem.isBlockedByModalPanel(Qt.QGraphicsRectItem.as_QGraphicsItem(target))
    check(result, Qt.QGraphicsRectItem.as_QGraphicsItem(panel))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QGraphicsScene.with(Unit, Qt.QGraphicsScene.new(), value =>
      Qt.QGraphicsRectItem.with(Unit, Qt.QGraphicsRectItem.new(), target =>
        Qt.QGraphicsRectItem.with(Unit, Qt.QGraphicsRectItem.new(), panel => scene(value, target, panel))))
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Geometry output ownership leaked resources")
    Qt.Action.lift(Unit, IO.print("QT612_GEOMETRY_OUTPUTS_OK panel_identity=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
