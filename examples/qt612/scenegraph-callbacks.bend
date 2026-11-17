import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def ownership_rejected(result: Result<&1, &1, U32 & String, Unit>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 22), "Wrong inline geometry ownership error: " ++ message)
    case Done{unit}: Qt.Action.fail(Unit, 1, "Inline scene graph geometry ownership was accepted")

def native_rejected(~A: Type, expected: U32, result: Result<&1, &1, U32 & String, A>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong scene graph lifetime error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Invalid scene graph lifetime operation succeeded")

def geometry_layout(+attributes: Qt.QSGGeometry.AttributeSet, geometry: Qt.QSGGeometry) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    count: Qt.Int32 <- Qt.QSGGeometry.attributeCount(geometry)
    require(U32.is_eq(Qt.Int32.word(count), 1), "Owned attribute array changed size")
    blocked: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QSGGeometry.AttributeSet.Fields.set_stride(attributes, Qt.Int32{16}))
    native_rejected(Unit, 16, blocked)

def layout(+attributes: Qt.QSGGeometry.AttributeSet) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    bad_count: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QSGGeometry.AttributeSet.Fields.set_count(attributes, Qt.Int32{2}))
    native_rejected(Unit, 34, bad_count)
    bad_type: Result<&1, &1, U32 & String, Qt.QSGGeometry> <- Qt.Action.attempt(Qt.QSGGeometry, Qt.QSGGeometry.new__QSGGeometry_AttributeSet_Int32_Int32_Int32(attributes, Qt.Int32{4}, Qt.Int32{0}, Qt.Int32{0}))
    native_rejected(Qt.QSGGeometry, 22, bad_type)
    overflow: Result<&1, &1, U32 & String, Qt.QSGGeometry> <- Qt.Action.attempt(Qt.QSGGeometry, Qt.QSGGeometry.new__QSGGeometry_AttributeSet_Int32(attributes, Qt.Int32{2147483647}))
    native_rejected(Qt.QSGGeometry, 75, overflow)
    Qt.QSGGeometry.with(Unit, Qt.QSGGeometry.new__QSGGeometry_AttributeSet_Int32(attributes, Qt.Int32{4}), geometry => geometry_layout(attributes, geometry))
    Qt.QSGGeometry.AttributeSet.Fields.set_stride(attributes, Qt.Int32{16})

def copied_attributes(values: List<&2, Qt.QSGGeometry.Attribute>) -> Qt.Action(Unit):
  Qt.QSGGeometry.AttributeSet.with(Unit, Qt.QSGGeometry.AttributeSet.fromAttributes(Qt.Int32{8}, values), attributes => layout(attributes))

def attributes(value: Qt.QSGGeometry.AttributeSet) -> Qt.Action(Unit):
  Qt.List_QSGGeometry_Attribute.with(Unit, Qt.QSGGeometry.AttributeSet.Fields.attributes(value), copied_attributes)

def child_demo(+parent: Qt.QSGNode, +child: Qt.QSGNode) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QSGNode.appendChildNode(parent, child)
    adopted: Qt.Int32 <- Qt.QSGNode.childCount(parent)
    require(U32.is_eq(Qt.Int32.word(adopted), 1), "Scene graph child adoption failed")
    Qt.QSGNode.removeChildNode(parent, child)
    removed: Qt.Int32 <- Qt.QSGNode.childCount(parent)
    require(U32.is_eq(Qt.Int32.word(removed), 0), "Scene graph child removal failed")

def validate_node(+base: Qt.QSGNode) -> Qt.Action(Qt.QSGNode):
  do Qt.Action<Qt.QSGNode>:
    Qt.QSGGeometry.AttributeSet.with(Unit, Qt.QSGGeometry.defaultAttributes_Point2D(), attributes)
    rejected: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QSGNode.setFlag(base, Qt.QSGNode.Flag.OwnsGeometry(), True{}))
    ownership_rejected(rejected)
    Qt.QSGNode.with(Unit, Qt.QSGNode.new(), child => child_demo(base, child))
    return base

def create_node(rectangle: Qt.QRectF, color: Qt.QColor) -> Qt.Action(Qt.QSGNode):
  do Qt.Action<Qt.QSGNode>:
    node: Qt.QSGSimpleRectNode <- Qt.QSGSimpleRectNode.new__QRectF_QColor(rectangle, color)
    validate_node(Qt.QSGSimpleRectNode.as_QSGNode(node))

def rectangle() -> Qt.Action(Qt.QRectF):
  do Qt.Action<Qt.QRectF>:
    width: Qt.F64 <- Qt.F64.fromString("64")
    height: Qt.F64 <- Qt.F64.fromString("48")
    Qt.QRectF.new__F64_F64_F64_F64(Qt.F64{0, 0}, Qt.F64{0, 0}, width, height)

def node(old: Qt.QSGNode, exists: Bool) -> Qt.Action(Qt.QSGNode):
  match exists:
    case True{}: Qt.Action.pure(Qt.QSGNode, old)
    case False{}:
      Qt.QRectF.with(Qt.QSGNode, rectangle(), rectangle => Qt.QColor.with(Qt.QSGNode, Qt.QColor.fromString("red"), color => create_node(rectangle, color)))

# The handler records what it saw on a probe object.
def remember(+probe: Qt.QObject, name: String, word: U32) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    stored: Bool <- Qt.QVariant.with(Bool, Qt.QVariant.fromUInt32(word), value => Qt.QObject.setProperty(probe, name, value))
    return Unit{}

def recall(+probe: Qt.QObject, name: String) -> Qt.Action(U32):
  Qt.QVariant.with(U32, Qt.QObject.property(probe, name), value => Qt.QVariant.toUInt32(value))

def old_mark(empty: Bool) -> String:
  match empty:
    case True{}: "N"
    case False{}: "R"

def trace(+probe: Qt.QObject, old: Qt.QSGNode) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    previous: String <- Qt.QObject.objectName(probe)
    Qt.QObject.setObjectName(probe, previous ++ old_mark(U32.is_eq(Qt.QSGNode.word(old), 0)))

def render_resource(+probe: Qt.QObject, window: Qt.QQuickWindow, interface: Qt.QSGRendererInterface) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    acquired: Qt.NativeRenderResource <- Qt.QSGRendererInterface.getResource__QQuickWindow_String(interface, window, "bend-fixture-unknown-resource")
    +resource: Qt.NativeRenderResource <- Qt.NativeRenderResource.detachFromScope(acquired)
    valid: Bool <- Qt.NativeRenderResource.isNull(resource)
    require(valid, "Unknown renderer resource key was not null")
    remember(probe, "resource", Qt.NativeRenderResource.word(resource))

def inspect_resources(+probe: Qt.QObject, +window: Qt.QQuickWindow) -> Qt.Action(Unit):
  Qt.QSGRendererInterface.with(Unit, Qt.QQuickWindow.rendererInterface(window), interface => render_resource(probe, window, interface))

def inspect_transform(+probe: Qt.QObject, +data: Qt.QQuickItem.UpdatePaintNodeData) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +transform: Qt.QSGTransformNode <- Qt.QQuickItem.UpdatePaintNodeData.Fields.transformNode(data)
    require(U32.is_ne(Qt.QSGTransformNode.word(transform), 0), "Native item transform was null")
    copied: Qt.QQuickItem.UpdatePaintNodeData <- Qt.QQuickItem.UpdatePaintNodeData.new(data)
    # Keep the handle for the expiry check below, past this callback's pool.
    # This does not extend the native transform's call-scoped lifetime.
    +copy: Qt.QQuickItem.UpdatePaintNodeData <- Qt.QQuickItem.UpdatePaintNodeData.detachFromScope(copied)
    Qt.QQuickItem.UpdatePaintNodeData.Fields.set_transformNode(copy, transform)
    remember(probe, "transform", Qt.QSGTransformNode.word(transform))
    remember(probe, "copy", Qt.QQuickItem.UpdatePaintNodeData.word(copy))

type Scene is Data:
  Scene{item: Qt.QQuickItem, probe: Qt.QObject}

def painted(+item: Qt.QQuickItem, +probe: Qt.QObject, +old: Qt.QSGNode, data: Qt.QQuickItem.UpdatePaintNodeData) -> Qt.Action(Qt.QSGNode):
  do Qt.Action<Qt.QSGNode>:
    trace(probe, old)
    inspect_transform(probe, data)
    window: Qt.QQuickWindow <- Qt.QQuickItem.window(item)
    inspect_resources(probe, window)
    node(old, U32.is_ne(Qt.QSGNode.word(old), 0))

def update_paint_node(scene: Scene, old: Qt.QSGNode, data: Qt.QQuickItem.UpdatePaintNodeData) -> Qt.Action(Qt.QSGNode):
  match scene:
    case Scene{item, probe}: painted(item, probe, old, data)

def inspect_pixel(+color: Qt.QColor) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    red: Qt.Int32 <- Qt.QColor.red(color)
    green: Qt.Int32 <- Qt.QColor.green(color)
    blue: Qt.Int32 <- Qt.QColor.blue(color)
    require(U32.is_eq(Qt.Int32.word(red), 255) && U32.is_eq(Qt.Int32.word(green), 0) && U32.is_eq(Qt.Int32.word(blue), 0), "Bend scene graph node did not render a red pixel")

def inspect_image(image: Qt.QImage) -> Qt.Action(Unit):
  Qt.QColor.with(Unit, Qt.QImage.pixelColor__Int32_Int32(image, Qt.Int32{5}, Qt.Int32{5}), color => inspect_pixel(color))

def resource_expired(result: Result<&1, &1, U32 & String, Bool>) -> Qt.Action(Unit):
  match result:
    case Fail{(error, message)}: require(U32.is_eq(error, 116), "Wrong expired renderer resource error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Escaped renderer resource outlived its handler")

# Values the handler saw are valid only during its call.
def check_resource(+token: U32) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    failed: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.NativeRenderResource.isNull(Qt.NativeRenderResource{token}))
    resource_expired(failed)
    Qt.NativeRenderResource.release(Qt.NativeRenderResource{token})

def check_transform(node: U32, +copy: U32) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    stale_node: Result<&1, &1, U32 & String, Qt.Int32> <- Qt.Action.attempt(Qt.Int32, Qt.QSGNode.childCount(Qt.QSGNode{node}))
    native_rejected(Qt.Int32, 116, stale_node)
    stale_copy: Result<&1, &1, U32 & String, Qt.QSGTransformNode> <- Qt.Action.attempt(Qt.QSGTransformNode, Qt.QQuickItem.UpdatePaintNodeData.Fields.transformNode(Qt.QQuickItem.UpdatePaintNodeData{copy}))
    native_rejected(Qt.QSGTransformNode, 116, stale_copy)
    Qt.QQuickItem.UpdatePaintNodeData.release(Qt.QQuickItem.UpdatePaintNodeData{copy})

def check_frame(+probe: Qt.QObject, +window: Qt.QQuickWindow, expected: String) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QImage.with(Unit, Qt.QQuickWindow.grabWindow(window), inspect_image)
    +seen: String <- Qt.QObject.objectName(probe)
    require(String.eq(seen, expected), "Unexpected scene graph handler calls: " ++ seen)
    transform: U32 <- recall(probe, "transform")
    copy: U32 <- recall(probe, "copy")
    check_transform(transform, copy)
    resource: U32 <- recall(probe, "resource")
    check_resource(resource)

# With the GUI-thread render loop, grabWindow synchronizes the scene graph,
# so Qt runs the updatePaintNode handler inside it.
def shown(+window: Qt.QQuickWindow, +item: Qt.QQuickItem, +probe: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQuickWindow.show(window)
    check_frame(probe, window, "N")
    Qt.QQuickItem.update(item)
    check_frame(probe, window, "NR")
    Qt.QQuickWindow.hide(window)

def configured(+window: Qt.QQuickWindow, +item: Qt.QQuickItem, +probe: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQuickItem.Virtual.updatePaintNode.handle(~Scene, ~update_paint_node, item, Scene{item, probe})
    width: Qt.F64 <- Qt.F64.fromString("64")
    height: Qt.F64 <- Qt.F64.fromString("48")
    Qt.QQuickItem.setWidth(item, width)
    Qt.QQuickItem.setHeight(item, height)
    Qt.QQuickItem.setFlag__QQuickItem_Flag_Bool(item, Qt.QQuickItem.Flag.ItemHasContents(), True{})
    shown(window, item, probe)

def window_demo(+window: Qt.QQuickWindow, +probe: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQuickWindow.resize__Int32_Int32(window, Qt.Int32{64}, Qt.Int32{48})
    content: Qt.QQuickItem <- Qt.QQuickWindow.contentItem(window)
    Qt.QQuickItem.with(Unit, Qt.QQuickItem.newOverride__QQuickItem(content), item => configured(window, item, probe))

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Render.useGuiThread()
    Qt.QObject.with(Unit, Qt.QObject.new(), probe => Qt.QQuickWindow.with(Unit, Qt.QQuickWindow.new(), window => window_demo(window, probe)))
    +objects: U32 <- Qt.Runtime.liveObjects()
    +connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Scene graph handler test leaked native handles: objects=" ++ U32.show(objects) ++ " connections=" ++ U32.show(connections))
    Qt.Action.lift(Unit, IO.print("QT612_SCENEGRAPH_CALLBACKS_OK gui_render_loop=1 bend_node=1 red_pixels=1 old_node_reused=1 child_transfer=1 inline_geometry_guard=1 call_scoped_values=1 objects=0 connections=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
