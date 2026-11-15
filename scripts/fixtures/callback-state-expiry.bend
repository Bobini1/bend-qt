import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def copied(+state: Qt.QSGMaterialShader.RenderState) -> Qt.Action(Qt.CallbackReply_Bool_QSGMaterialShader_RenderState):
  do Qt.Action<Qt.CallbackReply_Bool_QSGMaterialShader_RenderState>:
    copy: Qt.QSGMaterialShader.RenderState <- Qt.QSGMaterialShader.RenderState.new__QSGMaterialShader_RenderState(state)
    Qt.CallbackProbe.captureState(copy)
    return Qt.CallbackReply_Bool_QSGMaterialShader_RenderState{False{}, state}

# A copy of the renderer state still refers to the renderer: it ends with
# the call that delivered it.
def update_uniforms(unit: Unit, state: Qt.QSGMaterialShader.RenderState, material: Qt.QSGMaterial, previous: Qt.QSGMaterial) -> Qt.Action(Qt.CallbackReply_Bool_QSGMaterialShader_RenderState):
  copied(state)

def expired(result: Result<&1, &1, U32 & String, Qt.F64>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 116), "Wrong expired renderer state error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "A renderer state copy outlived its native call")

def state_demo(state: Qt.QSGMaterialShader.RenderState) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    result: Result<&1, &1, U32 & String, Qt.F64> <- Qt.Action.attempt(Qt.F64, Qt.QSGMaterialShader.RenderState.opacity(state))
    expired(result)

def shader_demo(+shader: Qt.QSGMaterialShader) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QSGMaterialShader.Virtual.updateUniformData.handle(~Unit, ~update_uniforms, shader, Unit{})
    Qt.QSGMaterialShader.RenderState.with(Unit, Qt.CallbackProbe.stateExpiry(shader), state => state_demo(state))

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Render.useGuiThread()
    shader: Qt.QSGMaterialShader <- Qt.CallbackProbe.newShader()
    shader_demo(shader)
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Expired renderer state copies were not cleaned up")
    Qt.Action.lift(Unit, IO.print("QT612_CALLBACK_STATE_EXPIRY_OK copied_origin=1 callback_expiry=1 cleanup=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
