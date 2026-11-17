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

def uniforms(+state: Qt.QSGMaterialShader.RenderState, +bytes: Qt.QByteArray) -> Qt.Action(Unit):
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
    Qt.QDataStream.writeFloat(stream, Qt.F64{0, 1071644672})
    Qt.QDataStream.writeFloat(stream, Qt.F64{0, 0})
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

def uniform_state(+state: Qt.QSGMaterialShader.RenderState) -> Qt.Action(Qt.CallbackReply_Bool_QSGMaterialShader_RenderState):
  do Qt.Action<Qt.CallbackReply_Bool_QSGMaterialShader_RenderState>:
    Qt.QByteArray.with(Unit, Qt.QByteArray.new(), bytes => uniforms(state, bytes))
    return Qt.CallbackReply_Bool_QSGMaterialShader_RenderState{True{}, state}

def update_uniforms(unit: Unit, state: Qt.QSGMaterialShader.RenderState, material: Qt.QSGMaterial, previous: Qt.QSGMaterial) -> Qt.Action(Qt.CallbackReply_Bool_QSGMaterialShader_RenderState):
  uniform_state(state)

def pipeline_state(state: Qt.QSGMaterialShader.RenderState, +value: Qt.QSGMaterialShader.GraphicsPipelineState) -> Qt.Action(Qt.CallbackReply_Bool_QSGMaterialShader_RenderState_QSGMaterialShader_GraphicsPipelineState):
  do Qt.Action<Qt.CallbackReply_Bool_QSGMaterialShader_RenderState_QSGMaterialShader_GraphicsPipelineState>:
    Qt.QSGMaterialShader.GraphicsPipelineState.Fields.set_blendEnable(value, True{})
    Qt.QSGMaterialShader.GraphicsPipelineState.Fields.set_srcColor(value, Qt.QSGMaterialShader.GraphicsPipelineState.BlendFactor.One())
    Qt.QSGMaterialShader.GraphicsPipelineState.Fields.set_dstColor(value, Qt.QSGMaterialShader.GraphicsPipelineState.BlendFactor.One())
    Qt.QSGMaterialShader.GraphicsPipelineState.Fields.set_opColor(value, Qt.QSGMaterialShader.GraphicsPipelineState.BlendOp.Add())
    return Qt.CallbackReply_Bool_QSGMaterialShader_RenderState_QSGMaterialShader_GraphicsPipelineState{True{}, state, value}

def pipeline(unit: Unit, state: Qt.QSGMaterialShader.RenderState, value: Qt.QSGMaterialShader.GraphicsPipelineState, material: Qt.QSGMaterial, previous: Qt.QSGMaterial) -> Qt.Action(Qt.CallbackReply_Bool_QSGMaterialShader_RenderState_QSGMaterialShader_GraphicsPipelineState):
  pipeline_state(state, value)

def shader(unit: Unit, mode: Qt.QSGRendererInterface.RenderMode) -> Qt.Action(Qt.QSGMaterialShader):
  do Qt.Action<Qt.QSGMaterialShader>:
    +value: Qt.QSGMaterialShader <- Qt.QSGMaterialShader.newOverride()
    +prefix: String <- Qt.CallbackProbe.materialShaderPrefix()
    Qt.QSGMaterialShader.configureShaderFile(value, Qt.QSGMaterialShader.Stage.VertexStage(), prefix ++ ".vert.qsb")
    Qt.QSGMaterialShader.configureShaderFile(value, Qt.QSGMaterialShader.Stage.FragmentStage(), prefix ++ ".frag.qsb")
    Qt.QSGMaterialShader.setFlag__Flags_QSGMaterialShader__Flag(value, Qt.Flags_QSGMaterialShader__Flag{Qt.QSGMaterialShader.Flag.word(Qt.QSGMaterialShader.Flag.UpdatesGraphicsPipelineState())})
    Qt.QSGMaterialShader.Virtual.updateUniformData.handle(~Unit, ~update_uniforms, value, Unit{})
    Qt.QSGMaterialShader.Virtual.updateGraphicsPipelineState.handle(~Unit, ~pipeline, value, Unit{})
    return value

def identity(unit: Unit) -> Qt.Action(Qt.QSGMaterialType):
  Qt.QSGMaterialType.identifier("bend.scenegraph.material-render")

def node(+rectangle: Qt.QRectF, +attributes: Qt.QSGGeometry.AttributeSet) -> Qt.Action(Qt.QSGNode):
  do Qt.Action<Qt.QSGNode>:
    +geometry: Qt.QSGGeometry <- Qt.QSGGeometry.new__QSGGeometry_AttributeSet_Int32(attributes, Qt.Int32{4})
    Qt.QSGGeometry.updateRectGeometry(geometry, rectangle)
    +material: Qt.QSGMaterial <- Qt.QSGMaterial.newOverride()
    Qt.QSGMaterial.setFlag__Flags_QSGMaterial__Flag(material, Qt.Flags_QSGMaterial__Flag{Qt.QSGMaterial.Flag.word(Qt.QSGMaterial.Flag.Blending())})
    Qt.QSGMaterial.Virtual.type.handle(~Unit, ~identity, material, Unit{})
    Qt.QSGMaterial.Virtual.createShader.handle(~Unit, ~shader, material, Unit{})
    +value: Qt.QSGGeometryNode <- Qt.QSGGeometryNode.new()
    Qt.QSGGeometryNode.setGeometry(value, geometry)
    Qt.QSGGeometryNode.setMaterial(value, material)
    Qt.QSGGeometryNode.setFlag(value, Qt.QSGNode.Flag.OwnsGeometry(), True{})
    Qt.QSGGeometryNode.setFlag(value, Qt.QSGNode.Flag.OwnsMaterial(), True{})
    return Qt.QSGGeometryNode.as_QSGNode(value)

def painted_node(old: Qt.QSGNode, exists: Bool) -> Qt.Action(Qt.QSGNode):
  match exists:
    case True{}: Qt.Action.pure(Qt.QSGNode, old)
    case False{}:
      do Qt.Action<Qt.QSGNode>:
        +width: Qt.F64 <- Qt.F64.fromString("32")
        +rectangle: Qt.QRectF <- Qt.QRectF.new__F64_F64_F64_F64(Qt.F64{0, 0}, Qt.F64{0, 0}, width, width)
        +attributes: Qt.QSGGeometry.AttributeSet <- Qt.QSGGeometry.defaultAttributes_Point2D()
        node(rectangle, attributes)

def painted_old(+old: Qt.QSGNode) -> Qt.Action(Qt.QSGNode):
  painted_node(old, U32.is_ne(Qt.QSGNode.word(old), 0))

def painted(unit: Unit, old: Qt.QSGNode, data: Qt.QQuickItem.UpdatePaintNodeData) -> Qt.Action(Qt.QSGNode):
  painted_old(old)

def pixel(+color: Qt.QColor) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +red: Qt.Int32 <- Qt.QColor.red(color)
    green: Qt.Int32 <- Qt.QColor.green(color)
    +blue: Qt.Int32 <- Qt.QColor.blue(color)
    require(Bool.not(U32.is_lt(Qt.Int32.word(red), 127)) && U32.is_lt(Qt.Int32.word(red), 130) && U32.is_eq(Qt.Int32.word(green), 0) && Bool.not(U32.is_lt(Qt.Int32.word(blue), 63)) && U32.is_lt(Qt.Int32.word(blue), 66), "Custom material uniform or additive pipeline pixels changed")

def image(value: Qt.QImage) -> Qt.Action(Unit):
  Qt.QColor.with(Unit, Qt.QImage.pixelColor__Int32_Int32(value, Qt.Int32{10}, Qt.Int32{10}), color => pixel(color))

def item(+window: Qt.QQuickWindow, +value: Qt.QQuickItem) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQuickItem.Virtual.updatePaintNode.handle(~Unit, ~painted, value, Unit{})
    +width: Qt.F64 <- Qt.F64.fromString("32")
    Qt.QQuickItem.setWidth(value, width)
    Qt.QQuickItem.setHeight(value, width)
    Qt.QQuickItem.setFlag__QQuickItem_Flag_Bool(value, Qt.QQuickItem.Flag.ItemHasContents(), True{})
    Qt.QQuickWindow.show(window)
    Qt.QImage.with(Unit, Qt.QQuickWindow.grabWindow(window), image)
    Qt.QQuickItem.update(value)
    Qt.QImage.with(Unit, Qt.QQuickWindow.grabWindow(window), image)
    Qt.QQuickWindow.hide(window)

def window(+value: Qt.QQuickWindow) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQuickWindow.resize__Int32_Int32(value, Qt.Int32{32}, Qt.Int32{32})
    Qt.QColor.with(Unit, Qt.QColor.fromString("#000040"), color => Qt.QQuickWindow.setColor(value, color))
    content: Qt.QQuickItem <- Qt.QQuickWindow.contentItem(value)
    Qt.QQuickItem.with(Unit, Qt.QQuickItem.newOverride__QQuickItem(content), child => item(value, child))

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Render.useGuiThread()
    Qt.QQuickWindow.with(Unit, Qt.QQuickWindow.new(), value => window(value))
    objects: U32 <- Qt.Runtime.liveObjects()
    data: U32 <- Qt.Runtime.liveData()
    require(U32.is_eq(objects, 0) && U32.is_eq(data, 0), "Custom material handlers leaked")
    Qt.Action.lift(Unit, IO.print("QT_SCENEGRAPH_MATERIAL_RENDER_OK bend_material=1 shader_factory=1 matrix=1 uniform_offsets=1 additive_pipeline=1 rendered_pixels=1 objects=0 data=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
