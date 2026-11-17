import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

# Mode 0 answers a new texture and the existing one; mode 1 answers the wrong
# number of textures; mode 2 answers a null texture.
def reply(mode: U32, textures: List<&2, Qt.QSGTexture>) -> Qt.Action(List<&2, Qt.QSGTexture>):
  match mode:
    case 1: Qt.Action.pure(List<&2, Qt.QSGTexture>, Nil{})
    case 2:
      do Qt.Action<List<&2, Qt.QSGTexture>>:
        texture: Qt.QSGTexture <- Qt.CallbackProbe.newSampledTexture()
        return texture <> Qt.QSGTexture{0} <> Nil{}
    case _:
      match textures:
        case old <> existing <> Nil{}:
          do Qt.Action<List<&2, Qt.QSGTexture>>:
            texture: Qt.QSGTexture <- Qt.CallbackProbe.newSampledTexture()
            return texture <> existing <> Nil{}
        case _: Qt.Action.fail(List<&2, Qt.QSGTexture>, 22, "The native sampler list has the wrong extent")

def forward_result(result: List<&2, Qt.QSGTexture>) -> Qt.Action(Unit):
  match result:
    case first <> second <> Nil{}:
      require(U32.is_eq(Qt.QSGTexture.word(first), Qt.QSGTexture.word(second)), "Forward sampled-image outputs differ")
    case _: Qt.Action.fail(Unit, 22, "The forward sampled-image output extent changed")

def protected_rejected(result: Result<&1, &1, U32 & String, Unit>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 95), "Wrong native shader rejection: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Shader configuration accepted a native shader")

def configure_value(+shader: Qt.QSGMaterialShader, value: Qt.QShader) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QSGMaterialShader.configureShader(shader, Qt.QSGMaterialShader.Stage.FragmentStage(), value)
    count: U32 <- Qt.CallbackProbe.prepareSampler(shader)
    require(U32.is_eq(count, 2), "The shader value hook lost the native reflection")

# Override shaders made inside the render handler can be configured.
def configure(+shader: Qt.QSGMaterialShader) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +path: String <- Qt.CallbackProbe.samplerPath()
    Qt.QSGMaterialShader.configureShaderFile(shader, Qt.QSGMaterialShader.Stage.FragmentStage(), path)
    count: U32 <- Qt.CallbackProbe.prepareSampler(shader)
    require(U32.is_eq(count, 2), "The shader file hook lost the native reflection")
    Qt.QSGMaterialShader.configureShaderFileViews(shader, Qt.QSGMaterialShader.Stage.FragmentStage(), path, Qt.Int32{1})
    Qt.QShader.with(Unit, Qt.CallbackProbe.samplerShader(), value => configure_value(shader, value))

def forward(state: Qt.QSGMaterialShader.RenderState, binding: Qt.Int32, +existing: Qt.QSGTexture, material: Qt.QSGMaterial, previous: Qt.QSGMaterial, +shader: Qt.QSGMaterialShader) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    rejected: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QSGMaterialShader.configureShaderFile(shader, Qt.QSGMaterialShader.Stage.FragmentStage(), "unused.qsb"))
    protected_rejected(rejected)
    result: List<&2, Qt.QSGTexture> <- Qt.QSGMaterialShader.updateSampledImage(shader, state, binding, existing <> existing <> Nil{}, material, previous)
    forward_result(result)

def forward_args(state: Qt.QSGMaterialShader.RenderState, binding: Qt.Int32, textures: List<&2, Qt.QSGTexture>, material: Qt.QSGMaterial, previous: Qt.QSGMaterial) -> Qt.Action(Unit):
  match textures:
    case old <> existing <> Nil{}:
      Qt.QSGMaterialShader.with(Unit, Qt.CallbackProbe.newSamplerBase(), shader => forward(state, binding, existing, material, previous, shader))
    case _: Qt.Action.fail(Unit, 22, "Forward sampled-image inputs have the wrong extent")

def answered(mode: U32, +state: Qt.QSGMaterialShader.RenderState, +binding: Qt.Int32, +textures: List<&2, Qt.QSGTexture>, +material: Qt.QSGMaterial, +previous: Qt.QSGMaterial) -> Qt.Action(List<&2, Qt.QSGTexture>):
  do Qt.Action<List<&2, Qt.QSGTexture>>:
    Qt.QSGMaterialShader.with(Unit, Qt.QSGMaterialShader.newOverride(), shader => configure(shader))
    forward_args(state, binding, textures, material, previous)
    reply(mode, textures)

def sampled(mode: U32, state: Qt.QSGMaterialShader.RenderState, binding: Qt.Int32, textures: List<&2, Qt.QSGTexture>, material: Qt.QSGMaterial, previous: Qt.QSGMaterial) -> Qt.Action(List<&2, Qt.QSGTexture>):
  answered(mode, state, binding, textures, material, previous)

# The probe answers how many textures shader destruction released.
def run(+mode: U32, expected: U32) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +shader: Qt.QSGMaterialShader <- Qt.CallbackProbe.newShader()
    Qt.QSGMaterialShader.Virtual.updateSampledImage.handle(~U32, ~sampled, shader, mode)
    destroyed: U32 <- Qt.CallbackProbe.sampledImages(shader, mode)
    require(U32.is_eq(destroyed, expected), "The sampled-image cleanup count changed")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Render.useGuiThread()
    run(0, 1)
    run(1, 0)
    run(2, 1)
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Sampled-image handlers leaked handles")
    Qt.Action.lift(Unit, IO.print("QT612_SAMPLED_IMAGES_OK reflected_count=2 array_writeback=1 retain_until_shader=1 no_ownership_transfer=1 wrong_length_atomic=1 null_output_atomic=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
