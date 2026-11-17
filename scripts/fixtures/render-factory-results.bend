import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def remember(+probe: Qt.QObject, name: String, word: U32) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    stored: Bool <- Qt.QVariant.with(Bool, Qt.QVariant.fromUInt32(word), value => Qt.QObject.setProperty(probe, name, value))
    return Unit{}

def recall(probe: Qt.QObject, name: String) -> Qt.Action(U32):
  Qt.QVariant.with(U32, Qt.QObject.property(probe, name), value => Qt.QVariant.toUInt32(value))

def stale(result: Result<&1, &1, U32 & String, Qt.Int32>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 116), "Factory handle expired with the wrong error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "A consumed factory token remained usable")

def rectangle() -> Qt.Action(Qt.QRectF):
  do Qt.Action<Qt.QRectF>:
    width: Qt.F64 <- Qt.F64.fromString("64")
    height: Qt.F64 <- Qt.F64.fromString("48")
    Qt.QRectF.new__F64_F64_F64_F64(Qt.F64{0, 0}, Qt.F64{0, 0}, width, height)

def configure_node(+probe: Qt.QObject, +node: Qt.QSGRectangleNode) -> Qt.Action(Qt.QSGNode):
  do Qt.Action<Qt.QSGNode>:
    Qt.QRectF.with(Unit, rectangle(), rect => Qt.QSGRectangleNode.setRect__QRectF(node, rect))
    Qt.QColor.with(Unit, Qt.QColor.fromString("red"), color => Qt.QSGRectangleNode.setColor(node, color))
    +base: Qt.QSGNode = Qt.QSGRectangleNode.as_QSGNode(node)
    +child: Qt.QSGNode <- Qt.QSGNode.new()
    Qt.QSGNode.appendChildNode(base, child)
    remember(probe, "factory", Qt.QSGRectangleNode.word(node))
    remember(probe, "child", Qt.QSGNode.word(child))
    return base

def fresh(+probe: Qt.QObject, window: Qt.QQuickWindow) -> Qt.Action(Qt.QSGNode):
  do Qt.Action<Qt.QSGNode>:
    node: Qt.QSGRectangleNode <- Qt.QQuickWindow.createRectangleNode(window)
    configure_node(probe, node)

def next_node(+probe: Qt.QObject, +window: Qt.QQuickWindow, +old: Qt.QSGNode, count: U32) -> Qt.Action(Qt.QSGNode):
  match count:
    case 0: fresh(probe, window)
    case 1:
      do Qt.Action<Qt.QSGNode>:
        children: Qt.Int32 <- Qt.QSGNode.childCount(old)
        require(U32.is_eq(Qt.Int32.word(children), 1), "A factory handoff lost its observed child")
        child: U32 <- recall(probe, "child")
        parent: Qt.QSGNode <- Qt.QSGNode.parent(Qt.QSGNode{child})
        require(U32.is_eq(Qt.QSGNode.word(parent), Qt.QSGNode.word(old)), "A child lost the factory parent identity")
        return old
    case _: fresh(probe, window)

type Scene is Data:
  Scene{item: Qt.QQuickItem, probe: Qt.QObject}

def painted(+item: Qt.QQuickItem, +probe: Qt.QObject, old: Qt.QSGNode) -> Qt.Action(Qt.QSGNode):
  do Qt.Action<Qt.QSGNode>:
    +count: U32 <- recall(probe, "frames")
    remember(probe, "frames", U32.add(count, 1))
    window: Qt.QQuickWindow <- Qt.QQuickItem.window(item)
    next_node(probe, window, old, count)

def update(scene: Scene, old: Qt.QSGNode, data: Qt.QQuickItem.UpdatePaintNodeData) -> Qt.Action(Qt.QSGNode):
  match scene:
    case Scene{item, probe}: painted(item, probe, old)

def pixel(color: Qt.QColor) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    red: Qt.Int32 <- Qt.QColor.red(color)
    require(U32.is_eq(Qt.Int32.word(red), 255), "A native rectangle factory did not paint")

def image(image: Qt.QImage) -> Qt.Action(Unit):
  Qt.QColor.with(Unit, Qt.QImage.pixelColor__Int32_Int32(image, Qt.Int32{5}, Qt.Int32{5}), pixel)

def frame(+probe: Qt.QObject, window: Qt.QQuickWindow, count: U32) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QImage.with(Unit, Qt.QQuickWindow.grabWindow(window), image)
    seen: U32 <- recall(probe, "frames")
    require(U32.is_eq(seen, count), "The factory render handler did not run exactly once")
    token: U32 <- recall(probe, "factory")
    result: Result<&1, &1, U32 & String, Qt.Int32> <- Qt.Action.attempt(Qt.Int32, Qt.QSGNode.childCount(Qt.QSGNode{token}))
    stale(result)

def configured(+window: Qt.QQuickWindow, +probe: Qt.QObject, +item: Qt.QQuickItem) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQuickItem.Virtual.updatePaintNode.handle(~Scene, ~update, item, Scene{item, probe})
    width: Qt.F64 <- Qt.F64.fromString("64")
    height: Qt.F64 <- Qt.F64.fromString("48")
    Qt.QQuickItem.setWidth(item, width)
    Qt.QQuickItem.setHeight(item, height)
    Qt.QQuickItem.setFlag__QQuickItem_Flag_Bool(item, Qt.QQuickItem.Flag.ItemHasContents(), True{})
    remember(probe, "frames", 0)
    Qt.QQuickWindow.show(window)
    frame(probe, window, 1)
    Qt.QQuickItem.update(item)
    frame(probe, window, 2)
    previous: U32 <- recall(probe, "child")
    Qt.QQuickItem.update(item)
    frame(probe, window, 3)
    expired: Result<&1, &1, U32 & String, Qt.Int32> <- Qt.Action.attempt(Qt.Int32, Qt.QSGNode.childCount(Qt.QSGNode{previous}))
    stale(expired)
    Qt.QQuickWindow.hide(window)

def window(+probe: Qt.QObject, +window: Qt.QQuickWindow) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQuickWindow.resize__Int32_Int32(window, Qt.Int32{64}, Qt.Int32{48})
    content: Qt.QQuickItem <- Qt.QQuickWindow.contentItem(window)
    Qt.QQuickItem.with(Unit, Qt.QQuickItem.newOverride__QQuickItem(content), item => configured(window, probe, item))

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Render.useGuiThread()
    Qt.QObject.with(Unit, Qt.QObject.new(), probe => Qt.QQuickWindow.with(Unit, Qt.QQuickWindow.new(), view => window(probe, view)))
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Factory render domains leaked handles")
    Qt.Action.lift(Unit, IO.print("QT612_RENDER_FACTORY_RESULTS_OK native_factory=1 consumed=1 restored=1 observed_child=1 replaced=1 painted=1 objects=0 connections=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
