import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def matrix(+stream: Qt.QDataStream, +values: Qt.ArrayView_float, indices: List<&2, U32>) -> Qt.Action(Unit):
  match indices:
    case Nil{}: Qt.Action.pure(Unit, Unit{})
    case index <> rest:
      do Qt.Action<Unit>:
        value: Qt.F64 <- Qt.ArrayView_float.at(values, Qt.UInt64{index, 0})
        Qt.QDataStream.writeFloat(stream, value)
        matrix(stream, values, rest)

type Tint is Data:
  Tint{red: Bool}

type Paint is Data:
  Paint{host: Qt.QObject, tint: Tint}

def key(material: Qt.QSGMaterial) -> String:
  "material:" ++ U32.show(Qt.QSGMaterial.word(material))

def tint(+stream: Qt.QDataStream, red: Bool) -> Qt.Action(Unit):
  match red:
    case True{}:
      do Qt.Action<Unit>:
        Qt.QDataStream.writeFloat(stream, Qt.F64{0, 1071644672})
        Qt.QDataStream.writeFloat(stream, Qt.F64{0, 0})
    case False{}:
      do Qt.Action<Unit>:
        Qt.QDataStream.writeFloat(stream, Qt.F64{0, 0})
        Qt.QDataStream.writeFloat(stream, Qt.F64{0, 1071644672})

def write_tint(stream: Qt.QDataStream, value: Tint) -> Qt.Action(Unit):
  match value:
    case Tint{red}: tint(stream, red)

def uniforms(host: Qt.QObject, +state: Qt.QSGMaterialShader.RenderState, material: Qt.QSGMaterial, +bytes: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +stream: Qt.QDataStream <- Qt.QDataStream.new__QByteArray_Flags_QIODeviceBase__OpenModeFlag(bytes, Qt.Flags_QIODeviceBase__OpenModeFlag{2})
    Qt.QDataStream.setByteOrder(stream, Qt.QDataStream.ByteOrder.LittleEndian())
    Qt.QDataStream.setFloatingPointPrecision(stream, Qt.QDataStream.FloatingPointPrecision.SinglePrecision())
    +transform: Qt.QMatrix4x4 <- Qt.QSGMaterialShader.RenderState.combinedMatrix(state)
    +values: Qt.ArrayView_float <- Qt.QMatrix4x4.constData(transform)
    matrix(stream, values, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15])
    opacity: Qt.F64 <- Qt.QSGMaterialShader.RenderState.opacity(state)
    Qt.QDataStream.writeFloat(stream, opacity)
    Qt.QDataStream.writeFloat(stream, Qt.F64{0, 0})
    Qt.QDataStream.writeFloat(stream, Qt.F64{0, 0})
    Qt.QDataStream.writeFloat(stream, Qt.F64{0, 0})
    # The tested std140 layout: tint=80, transColor=96,
    # colorKeyEnabled=112, blendMode=116.
    +boxed: Qt.QVariant <- Qt.QObject.property(host, key(material))
    value: Tint <- Qt.QVariant.toData(~Tint, boxed)
    write_tint(stream, value)
    Qt.QDataStream.writeFloat(stream, Qt.F64{0, 0})
    Qt.QDataStream.writeFloat(stream, Qt.F64{0, 1072693248})
    Qt.QDataStream.writeFloat(stream, Qt.F64{0, 0})
    Qt.QDataStream.writeFloat(stream, Qt.F64{0, 0})
    Qt.QDataStream.writeFloat(stream, Qt.F64{0, 0})
    Qt.QDataStream.writeFloat(stream, Qt.F64{0, 1072693248})
    Qt.QDataStream.writeFloat(stream, Qt.F64{0, 0})
    Qt.QDataStream.writeFloat(stream, Qt.F64{0, 1071644672})
    Qt.QDataStream.release(stream)
    +target: Qt.MemoryView <- Qt.QSGMaterialShader.RenderState.uniformData(state)
    Qt.MemoryView.write(target, Qt.UInt64{0, 0}, bytes)

def uniform_state(host: Qt.QObject, +state: Qt.QSGMaterialShader.RenderState, material: Qt.QSGMaterial) -> Qt.Action(Qt.CallbackReply_Bool_QSGMaterialShader_RenderState):
  do Qt.Action<Qt.CallbackReply_Bool_QSGMaterialShader_RenderState>:
    Qt.QByteArray.with(Unit, Qt.QByteArray.new(), bytes => uniforms(host, state, material, bytes))
    return Qt.CallbackReply_Bool_QSGMaterialShader_RenderState{True{}, state}

def update_uniforms(host: Qt.QObject, state: Qt.QSGMaterialShader.RenderState, material: Qt.QSGMaterial, previous: Qt.QSGMaterial) -> Qt.Action(Qt.CallbackReply_Bool_QSGMaterialShader_RenderState):
  uniform_state(host, state, material)

def pipeline_state(state: Qt.QSGMaterialShader.RenderState, +value: Qt.QSGMaterialShader.GraphicsPipelineState) -> Qt.Action(Qt.CallbackReply_Bool_QSGMaterialShader_RenderState_QSGMaterialShader_GraphicsPipelineState):
  do Qt.Action<Qt.CallbackReply_Bool_QSGMaterialShader_RenderState_QSGMaterialShader_GraphicsPipelineState>:
    Qt.QSGMaterialShader.GraphicsPipelineState.Fields.set_blendEnable(value, True{})
    Qt.QSGMaterialShader.GraphicsPipelineState.Fields.set_srcColor(value, Qt.QSGMaterialShader.GraphicsPipelineState.BlendFactor.One())
    Qt.QSGMaterialShader.GraphicsPipelineState.Fields.set_dstColor(value, Qt.QSGMaterialShader.GraphicsPipelineState.BlendFactor.One())
    Qt.QSGMaterialShader.GraphicsPipelineState.Fields.set_opColor(value, Qt.QSGMaterialShader.GraphicsPipelineState.BlendOp.Add())
    return Qt.CallbackReply_Bool_QSGMaterialShader_RenderState_QSGMaterialShader_GraphicsPipelineState{True{}, state, value}

def pipeline(unit: Unit, state: Qt.QSGMaterialShader.RenderState, value: Qt.QSGMaterialShader.GraphicsPipelineState, material: Qt.QSGMaterial, previous: Qt.QSGMaterial) -> Qt.Action(Qt.CallbackReply_Bool_QSGMaterialShader_RenderState_QSGMaterialShader_GraphicsPipelineState):
  pipeline_state(state, value)

def make_shader(+host: Qt.QObject) -> Qt.Action(Qt.QSGMaterialShader):
  do Qt.Action<Qt.QSGMaterialShader>:
    +value: Qt.QSGMaterialShader <- Qt.QSGMaterialShader.newOverride()
    previous: String <- Qt.QObject.objectName(host)
    Qt.QObject.setObjectName(host, previous ++ "S")
    +prefix: String <- Qt.CallbackProbe.materialShaderPrefix()
    Qt.QSGMaterialShader.configureShaderFile(value, Qt.QSGMaterialShader.Stage.VertexStage(), prefix ++ ".vert.qsb")
    Qt.QSGMaterialShader.configureShaderFile(value, Qt.QSGMaterialShader.Stage.FragmentStage(), prefix ++ ".frag.qsb")
    Qt.QSGMaterialShader.setFlag__Flags_QSGMaterialShader__Flag(value, Qt.Flags_QSGMaterialShader__Flag{Qt.QSGMaterialShader.Flag.word(Qt.QSGMaterialShader.Flag.UpdatesGraphicsPipelineState())})
    Qt.QSGMaterialShader.Virtual.updateUniformData.handle(~Qt.QObject, ~update_uniforms, value, host)
    Qt.QSGMaterialShader.Virtual.updateGraphicsPipelineState.handle(~Unit, ~pipeline, value, Unit{})
    return value

def shader(host: Qt.QObject, mode: Qt.QSGRendererInterface.RenderMode) -> Qt.Action(Qt.QSGMaterialShader):
  make_shader(host)

def identity(unit: Unit) -> Qt.Action(Qt.QSGMaterialType):
  Qt.QSGMaterialType.identifier("bend.scenegraph.material-render")

def node(+host: Qt.QObject, tint: Tint, +rectangle: Qt.QRectF, +attributes: Qt.QSGGeometry.AttributeSet) -> Qt.Action(Qt.QSGNode):
  do Qt.Action<Qt.QSGNode>:
    +geometry: Qt.QSGGeometry <- Qt.QSGGeometry.new__QSGGeometry_AttributeSet_Int32(attributes, Qt.Int32{4})
    Qt.QSGGeometry.updateRectGeometry(geometry, rectangle)
    +material: Qt.QSGMaterial <- Qt.QSGMaterial.newOverride()
    +boxed: Qt.QVariant <- Qt.QVariant.fromData(~Tint, tint)
    stored: Bool <- Qt.QObject.setProperty(host, key(material), boxed)
    Qt.QSGMaterial.setFlag__Flags_QSGMaterial__Flag(material, Qt.Flags_QSGMaterial__Flag{Qt.QSGMaterial.Flag.word(Qt.QSGMaterial.Flag.Blending())})
    Qt.QSGMaterial.Virtual.type.handle(~Unit, ~identity, material, Unit{})
    Qt.QSGMaterial.Virtual.createShader.handle(~Qt.QObject, ~shader, material, host)
    +value: Qt.QSGGeometryNode <- Qt.QSGGeometryNode.new()
    Qt.QSGGeometryNode.setGeometry(value, geometry)
    Qt.QSGGeometryNode.setMaterial(value, material)
    Qt.QSGGeometryNode.setFlag(value, Qt.QSGNode.Flag.OwnsGeometry(), True{})
    Qt.QSGGeometryNode.setFlag(value, Qt.QSGNode.Flag.OwnsMaterial(), True{})
    return Qt.QSGGeometryNode.as_QSGNode(value)

def painted_node(host: Qt.QObject, tint: Tint, old: Qt.QSGNode, exists: Bool) -> Qt.Action(Qt.QSGNode):
  match exists:
    case True{}: Qt.Action.pure(Qt.QSGNode, old)
    case False{}:
      do Qt.Action<Qt.QSGNode>:
        width: Qt.F64 <- Qt.F64.fromString("16")
        height: Qt.F64 <- Qt.F64.fromString("32")
        +rectangle: Qt.QRectF <- Qt.QRectF.new__F64_F64_F64_F64(Qt.F64{0, 0}, Qt.F64{0, 0}, width, height)
        +attributes: Qt.QSGGeometry.AttributeSet <- Qt.QSGGeometry.defaultAttributes_Point2D()
        node(host, tint, rectangle, attributes)

def painted_old(host: Qt.QObject, tint: Tint, +old: Qt.QSGNode) -> Qt.Action(Qt.QSGNode):
  painted_node(host, tint, old, U32.is_ne(Qt.QSGNode.word(old), 0))

def painted(paint: Paint, old: Qt.QSGNode, data: Qt.QQuickItem.UpdatePaintNodeData) -> Qt.Action(Qt.QSGNode):
  match paint:
    case Paint{host, tint}: painted_old(host, tint, old)

def channels(+high: U32, zero: U32, +blue: U32) -> Bool:
  Bool.not(U32.is_lt(high, 127)) && U32.is_lt(high, 130) && U32.is_eq(zero, 0) && Bool.not(U32.is_lt(blue, 63)) && U32.is_lt(blue, 66)

def expected(red: U32, green: U32, blue: U32, first: Bool) -> Bool:
  match first:
    case True{}: channels(red, green, blue)
    case False{}: channels(green, red, blue)

def pixel(+color: Qt.QColor, first: Bool) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    red: Qt.Int32 <- Qt.QColor.red(color)
    green: Qt.Int32 <- Qt.QColor.green(color)
    blue: Qt.Int32 <- Qt.QColor.blue(color)
    require(expected(Qt.Int32.word(red), Qt.Int32.word(green), Qt.Int32.word(blue), first), "Shared shader used the wrong material data")

def image(+value: Qt.QImage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QColor.with(Unit, Qt.QImage.pixelColor__Int32_Int32(value, Qt.Int32{10}, Qt.Int32{10}), color => pixel(color, True{}))
    Qt.QColor.with(Unit, Qt.QImage.pixelColor__Int32_Int32(value, Qt.Int32{26}, Qt.Int32{10}), color => pixel(color, False{}))

def configure(+value: Qt.QQuickItem, host: Qt.QObject, tint: Tint) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQuickItem.Virtual.updatePaintNode.handle(~Paint, ~painted, value, Paint{host, tint})
    width: Qt.F64 <- Qt.F64.fromString("16")
    height: Qt.F64 <- Qt.F64.fromString("32")
    Qt.QQuickItem.setWidth(value, width)
    Qt.QQuickItem.setHeight(value, height)
    Qt.QQuickItem.setFlag__QQuickItem_Flag_Bool(value, Qt.QQuickItem.Flag.ItemHasContents(), True{})

def shown(+host: Qt.QObject, +window: Qt.QQuickWindow, +first: Qt.QQuickItem, +second: Qt.QQuickItem) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    configure(first, host, Tint{True{}})
    configure(second, host, Tint{False{}})
    x: Qt.F64 <- Qt.F64.fromString("16")
    Qt.QQuickItem.setX(second, x)
    Qt.QQuickWindow.show(window)
    Qt.QImage.with(Unit, Qt.QQuickWindow.grabWindow(window), value => image(value))
    +first_factories: String <- Qt.QObject.objectName(host)
    require(String.eq(first_factories, "S"), "First frame did not share a shader: " ++ first_factories)
    Qt.QQuickItem.update(first)
    Qt.QQuickItem.update(second)
    Qt.QImage.with(Unit, Qt.QQuickWindow.grabWindow(window), value => image(value))
    Qt.QQuickWindow.hide(window)

def window(+host: Qt.QObject, +value: Qt.QQuickWindow) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQuickWindow.resize__Int32_Int32(value, Qt.Int32{32}, Qt.Int32{32})
    Qt.QColor.with(Unit, Qt.QColor.fromString("#000040"), color => Qt.QQuickWindow.setColor(value, color))
    +content: Qt.QQuickItem <- Qt.QQuickWindow.contentItem(value)
    Qt.QQuickItem.with(Unit, Qt.QQuickItem.newOverride__QQuickItem(content), first => Qt.QQuickItem.with(Unit, Qt.QQuickItem.newOverride__QQuickItem(content), second => shown(host, value, first, second)))

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Render.useGuiThread()
    Qt.QObject.with(Unit, Qt.QObject.new(), host => Qt.QQuickWindow.with(Unit, Qt.QQuickWindow.new(), value => window(host, value)))
    objects: U32 <- Qt.Runtime.liveObjects()
    data: U32 <- Qt.Runtime.liveData()
    require(U32.is_eq(objects, 0) && U32.is_eq(data, 0), "Custom material handlers leaked")
    Qt.Action.lift(Unit, IO.print("QT_SCENEGRAPH_MATERIAL_INSTANCES_OK shared_shader=1 instance_data=1 typed_bend_payload=1 red_and_green_pixels=1 objects=0 data=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
