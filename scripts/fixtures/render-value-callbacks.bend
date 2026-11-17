import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

# Qt keeps the pointer it gets from these handlers: each value is copied.
def clip(state: Unit) -> Qt.Action(Qt.QRegion):
  Qt.QRegion.new()

def projection(state: Unit) -> Qt.Action(Qt.QMatrix4x4):
  Qt.QMatrix4x4.new()

def material_type(state: Unit) -> Qt.Action(Qt.QSGMaterialType):
  Qt.QSGMaterialType.identifier("bend.test.material")

# A private pure virtual of QSGTextNode.
def text_layout(marker: Qt.QObject, position: Qt.QPointF, layout: Qt.QTextLayout, start: Qt.Int32, length: Qt.Int32, selection_start: Qt.Int32, selection_count: Qt.Int32) -> Qt.Action(Unit):
  Qt.QObject.setObjectName(marker, "private_virtual")

def render(+marker: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +state: Qt.QSGRenderNode.RenderState <- Qt.CallbackProbe.newRenderState()
    +material: Qt.QSGMaterial <- Qt.CallbackProbe.newRenderMaterial()
    +text: Qt.QSGTextNode <- Qt.CallbackProbe.newRenderText()
    Qt.QSGRenderNode.RenderState.Virtual.clipRegion.handle(~Unit, ~clip, state, Unit{})
    Qt.QSGRenderNode.RenderState.Virtual.projectionMatrix.handle(~Unit, ~projection, state, Unit{})
    Qt.QSGMaterial.Virtual.type.handle(~Unit, ~material_type, material, Unit{})
    Qt.QSGTextNode.Virtual.doAddTextLayout.handle(~Qt.QObject, ~text_layout, text, marker)
    valid: U32 <- Qt.CallbackProbe.renderValues(state, material, text, marker)
    require(U32.is_eq(valid, 1), "Stable value copies or the canonical material identity failed")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Render.useGuiThread()
    Qt.QObject.with(Unit, Qt.QObject.new(), marker => render(marker))
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Render handlers kept handles after the overrides were destroyed")
    Qt.Action.lift(Unit, IO.print("QT612_RENDER_VALUE_CALLBACKS_OK retained_const_copies=1 canonical_material_identity=1 private_virtual=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
