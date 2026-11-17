import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def bounds(state: Unit) -> Qt.Action(Qt.QRectF):
  do Qt.Action<Qt.QRectF>:
    width: Qt.F64 <- Qt.F64.fromString("64")
    height: Qt.F64 <- Qt.F64.fromString("48")
    Qt.QRectF.new__F64_F64_F64_F64(Qt.F64{0, 0}, Qt.F64{0, 0}, width, height)

def paint(state: Unit, painter: Qt.QPainter, option: Qt.QStyleOptionGraphicsItem, widget: Qt.QWidget) -> Qt.Action(Unit):
  Qt.Action.pure(Unit, Unit{})

def inspect(rectangle: Qt.QRectF) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +width: Qt.F64 <- Qt.QRectF.width(rectangle)
    +expected: Qt.F64 <- Qt.F64.fromString("64")
    require(U32.is_eq(Qt.F64.hi(width), Qt.F64.hi(expected)) && U32.is_eq(Qt.F64.lo(width), Qt.F64.lo(expected)), "Native item virtual result was not returned")

# The scene takes ownership of the item and deletes it with itself.
def adopted(+item: Qt.QGraphicsItem, scene: Qt.QGraphicsScene) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QGraphicsScene.addItem(scene, item)
    Qt.QRectF.with(Unit, Qt.QGraphicsItem.boundingRect(item), inspect)

def item(+item: Qt.QGraphicsItem) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QGraphicsItem.Virtual.boundingRect.handle(~Unit, ~bounds, item, Unit{})
    Qt.QGraphicsItem.Virtual.paint.handle(~Unit, ~paint, item, Unit{})
    Qt.QGraphicsScene.with(Unit, Qt.QGraphicsScene.new(), scene => adopted(item, scene))

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QGraphicsItem.with(Unit, Qt.QGraphicsItem.newOverride(), graphics => item(graphics))
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Non-QObject proxy destruction leaked objects")
    Qt.Action.lift(Unit, IO.print("QT612_GRAPHICS_CALLBACKS_OK native_subclass=1 virtual=1 scene_ownership=1 observed_destruction=1 objects=0 connections=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
