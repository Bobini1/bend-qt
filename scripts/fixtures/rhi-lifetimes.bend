import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def rejected(-A: Type, code: U32, result: Result<&1, &1, U32 & String, A>) -> Qt.Action(Unit):
  match result:
    case Fail{(actual, message)}: require(U32.is_eq(actual, code), "Wrong RHI lifetime error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "RHI lifetime violation was accepted")

def frame(+buffer: Qt.QRhiBuffer, +batch: Qt.QRhiResourceUpdateBatch, command: Qt.QRhiCommandBuffer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QRhiCommandBuffer.resourceUpdate(command, batch)
    consumed: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.QRhiResourceUpdateBatch.hasOptimalCapacity(batch))
    rejected(Bool, 116, consumed)
    early: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QRhiBuffer.destroy(buffer))
    rejected(Unit, 16, early)
    Qt.QRhiBuffer.release(buffer)
    size: U32 <- Qt.QRhiBuffer.size(buffer)
    require(U32.is_eq(size, 4), "Scoped RHI release deleted a resource inside an active frame")

def bytes(data: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    value: String <- Qt.QByteArray.utf8(data)
    require(String.eq(value, "1234"), "Native RHI readback bytes changed")

# Qt runs the readback handler when the frame completes; the result is
# valid during the call.
def read_back(probe: Qt.QObject, value: Qt.QRhiReadbackResult) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QByteArray.with(Unit, Qt.QRhiReadbackResult.Fields.data(value), bytes)
    Qt.QObject.setObjectName(probe, "read")

def readback(root: Qt.QRhi, buffer: Qt.QRhiBuffer, batch: Qt.QRhiResourceUpdateBatch, +probe: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QRhi.withOffscreenFrame(Unit, root, command => frame(buffer, batch, command))
    name: String <- Qt.QObject.objectName(probe)
    require(String.eq(name, "read"), "The readback handler did not run when the frame completed")

def uploaded(+root: Qt.QRhi, +buffer: Qt.QRhiBuffer, +batch: Qt.QRhiResourceUpdateBatch, data: Qt.QByteArray, +probe: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QRhiResourceUpdateBatch.uploadStaticBuffer__QRhiBuffer_QByteArray(batch, buffer, data)
    Qt.QRhiResourceUpdateBatch.readBackBufferAsync(~Qt.QObject, ~read_back, batch, buffer, 0, 4, probe)
    readback(root, buffer, batch, probe)

def batch(+root: Qt.QRhi, +buffer: Qt.QRhiBuffer, updates: Qt.QRhiResourceUpdateBatch) -> Qt.Action(Unit):
  Qt.QByteArray.with(Unit, Qt.QByteArray.fromUtf8("1234"), data => Qt.QObject.with(Unit, Qt.QObject.new(), probe => uploaded(root, buffer, updates, data, probe)))

def buffer(+root: Qt.QRhi, +value: Qt.QRhiBuffer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    ready: Bool <- Qt.QRhiBuffer.create(value)
    require(ready, "Null RHI buffer creation failed")
    Qt.QRhi.release(root)
    Qt.QRhiResourceUpdateBatch.with(Unit, Qt.QRhi.nextResourceUpdateBatch(root), updates => batch(root, value, updates))

def root(+root: Qt.QRhi) -> Qt.Action(Unit):
  Qt.QRhiBuffer.with(Unit, Qt.QRhi.newBuffer(root, Qt.QRhiBuffer.Type.Static(), Qt.Flags_QRhiBuffer__UsageFlag{4}, 4), value => buffer(root, value))

def native_delete(+root: Qt.QRhi, +buffer: Qt.QRhiBuffer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.CallbackProbe.rhiDeleteNative(root)
    stale: Result<&1, &1, U32 & String, U32> <- Qt.Action.attempt(U32, Qt.QRhiBuffer.size(buffer))
    rejected(U32, 116, stale)

def externally_deleted(+root: Qt.QRhi) -> Qt.Action(Unit):
  Qt.QRhiBuffer.with(Unit, Qt.QRhi.newBuffer(root, Qt.QRhiBuffer.Type.Static(), Qt.Flags_QRhiBuffer__UsageFlag{4}, 4), value => native_delete(root, value))

def unread(probe: Qt.QObject, value: Qt.QRhiReadbackResult) -> Qt.Action(Unit):
  Qt.QObject.setObjectName(probe, "read")

# A batch released unsubmitted never runs its readback handler.
def pending(buffer: Qt.QRhiBuffer, +batch: Qt.QRhiResourceUpdateBatch, +probe: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QRhiResourceUpdateBatch.readBackBufferAsync(~Qt.QObject, ~unread, batch, buffer, 0, 4, probe)
    Qt.QRhiResourceUpdateBatch.native_release(batch)
    name: String <- Qt.QObject.objectName(probe)
    require(String.eq(name, ""), "A released batch ran its readback handler")

def cancel_buffer(root: Qt.QRhi, buffer: Qt.QRhiBuffer) -> Qt.Action(Unit):
  Qt.QRhiResourceUpdateBatch.with(Unit, Qt.QRhi.nextResourceUpdateBatch(root), batch => Qt.QObject.with(Unit, Qt.QObject.new(), probe => pending(buffer, batch, probe)))

def cancel_root(+root: Qt.QRhi) -> Qt.Action(Unit):
  Qt.QRhiBuffer.with(Unit, Qt.QRhi.newBuffer(root, Qt.QRhiBuffer.Type.Static(), Qt.Flags_QRhiBuffer__UsageFlag{4}, 4), value => cancel_buffer(root, value))

def fail_in_pass(command: Qt.QRhiCommandBuffer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QRhiCommandBuffer.beginComputePass(command)
    Qt.Action.fail(Unit, 41, "Deliberate failure inside an RHI pass")

def failed_frame(+root: Qt.QRhi) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    failed: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QRhi.withOffscreenFrame(Unit, root, fail_in_pass))
    rejected(Unit, 41, failed)
    recording: Bool <- Qt.QRhi.isRecordingFrame(root)
    require(Bool.not(recording), "RHI Action failure did not close its native pass and frame")

def copied_binding(+buffer: Qt.QRhiBuffer, original: Qt.QRhiShaderResourceBinding, copy: Qt.QRhiShaderResourceBinding) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QRhiShaderResourceBinding.release(original)
    Qt.QRhiBuffer.release(buffer)
    size: U32 <- Qt.QRhiBuffer.size(buffer)
    require(U32.is_eq(size, 4), "Copied RHI descriptor lost its native buffer dependency")

def binding_copy(buffer: Qt.QRhiBuffer, +binding: Qt.QRhiShaderResourceBinding) -> Qt.Action(Unit):
  Qt.QRhiShaderResourceBinding.with(Unit, Qt.QRhiShaderResourceBinding.new__QRhiShaderResourceBinding(binding), copy => copied_binding(buffer, binding, copy))

def binding_buffer(+buffer: Qt.QRhiBuffer) -> Qt.Action(Unit):
  Qt.QRhiShaderResourceBinding.with(Unit, Qt.QRhiShaderResourceBinding.uniformBuffer__Int32_Flags_QRhiShaderResourceBinding__StageFlag_QRhiBuffer(Qt.Int32{0}, Qt.Flags_QRhiShaderResourceBinding__StageFlag{1}, buffer), binding => binding_copy(buffer, binding))

def binding_root(root: Qt.QRhi) -> Qt.Action(Unit):
  Qt.QRhiBuffer.with(Unit, Qt.QRhi.newBuffer(root, Qt.QRhiBuffer.Type.Static(), Qt.Flags_QRhiBuffer__UsageFlag{4}, 4), value => binding_buffer(value))

def cross_bind(binding: Qt.QRhiShaderResourceBinding, bindings: Qt.QRhiShaderResourceBindings) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    failure: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QRhiShaderResourceBindings.setBindings(bindings, [binding]))
    rejected(Unit, 18, failure)

def cross_root(binding: Qt.QRhiShaderResourceBinding, root: Qt.QRhi) -> Qt.Action(Unit):
  Qt.QRhiShaderResourceBindings.with(Unit, Qt.QRhi.newShaderResourceBindings(root), bindings => cross_bind(binding, bindings))

def cross_descriptor(binding: Qt.QRhiShaderResourceBinding) -> Qt.Action(Unit):
  Qt.QRhi.with(Unit, Qt.QRhi.newNull(), root => cross_root(binding, root))

def cross_buffer(buffer: Qt.QRhiBuffer) -> Qt.Action(Unit):
  Qt.QRhiShaderResourceBinding.with(Unit, Qt.QRhiShaderResourceBinding.uniformBuffer__Int32_Flags_QRhiShaderResourceBinding__StageFlag_QRhiBuffer(Qt.Int32{0}, Qt.Flags_QRhiShaderResourceBinding__StageFlag{1}, buffer), cross_descriptor)

def cross_source(root: Qt.QRhi) -> Qt.Action(Unit):
  Qt.QRhiBuffer.with(Unit, Qt.QRhi.newBuffer(root, Qt.QRhiBuffer.Type.Static(), Qt.Flags_QRhiBuffer__UsageFlag{4}, 4), cross_buffer)

def expired_descriptor(root: Qt.QRhi, +descriptor: Qt.QRhiShaderResourceBinding) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.CallbackProbe.rhiDeleteNative(root)
    Qt.Action.lift(Unit, IO.sleep(1))
    failure: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.QRhiShaderResourceBinding.isLayoutCompatible(descriptor, descriptor))
    rejected(Bool, 116, failure)

def expire_buffer(root: Qt.QRhi, buffer: Qt.QRhiBuffer) -> Qt.Action(Unit):
  Qt.QRhiShaderResourceBinding.with(Unit,
    Qt.QRhiShaderResourceBinding.uniformBuffer__Int32_Flags_QRhiShaderResourceBinding__StageFlag_QRhiBuffer(Qt.Int32{0}, Qt.Flags_QRhiShaderResourceBinding__StageFlag{1}, buffer), descriptor => expired_descriptor(root, descriptor))

def expire_root(+root: Qt.QRhi) -> Qt.Action(Unit):
  Qt.QRhiBuffer.with(Unit, Qt.QRhi.newBuffer(root, Qt.QRhiBuffer.Type.Static(), Qt.Flags_QRhiBuffer__UsageFlag{4}, 4), buffer => expire_buffer(root, buffer))

def typed_null(+parameters: Qt.QRhiNullInitParams) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    possible: Bool <- Qt.QRhi.probeWithNull(parameters)
    require(possible, "Typed Null initialization probe failed")
    Qt.QRhi.with(Unit, Qt.QRhi.createWithNull(parameters, Qt.Flags_QRhi__Flag{0}), binding_root)

def texture_arrays() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    empty: Result<&1, &1, U32 & String, Qt.QRhiShaderResourceBinding> <- Qt.Action.attempt(Qt.QRhiShaderResourceBinding,
      Qt.QRhiShaderResourceBinding.textures(Qt.Int32{0}, Qt.Flags_QRhiShaderResourceBinding__StageFlag{1}, []))
    rejected(Qt.QRhiShaderResourceBinding, 34, empty)
    Qt.QRhiShaderResourceBinding.with(Unit,
      Qt.QRhiShaderResourceBinding.textures(Qt.Int32{0}, Qt.Flags_QRhiShaderResourceBinding__StageFlag{1}, [Qt.QRhiTexture{0}]), value => Qt.Action.pure(Unit, Unit{}))

def destroyed(probe: Qt.QObject, identity: Qt.ObjectIdentity) -> Qt.Action(Unit):
  Qt.QObject.setObjectName(probe, U32.show(Qt.ObjectIdentity.word(identity)))

# The connection closes itself after the single notification.
def destroyed_signal(+root: Qt.QRhi, +probe: Qt.QObject, connection: Qt.Connection) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QRhi.destroy(root)
    name: String <- Qt.QObject.objectName(probe)
    require(String.eq(name, U32.show(Qt.QRhi.word(root))), "The RHI cleanup notification lost its native identity")

def cleanup_signal(+root: Qt.QRhi) -> Qt.Action(Unit):
  Qt.QObject.with(Unit, Qt.QObject.new(), +probe => Qt.Connection.with(Unit, Qt.QRhi.onDestroyed(~Qt.QObject, ~destroyed, root, probe), connection => destroyed_signal(root, probe, connection)))

def gles_live(+surface: Qt.QOffscreenSurface, +parameters: Qt.QRhiGles2InitParams, +root: Qt.QRhi) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QRhiGles2InitParams.release(parameters)
    Qt.QOffscreenSurface.release(surface)
    Qt.QRhi.withOffscreenFrame(Unit, root, command => Qt.Action.pure(Unit, Unit{}))

def gles_params(+surface: Qt.QOffscreenSurface, +parameters: Qt.QRhiGles2InitParams) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QRhiGles2InitParams.Fields.set_fallbackSurface(parameters, Qt.QOffscreenSurface.as_QSurface(surface))
    possible: Bool <- Qt.QRhi.probeWithGles2(parameters)
    require(possible, "Typed OpenGL initialization probe failed")
    Qt.QRhi.with(Unit, Qt.QRhi.createWithGles2(parameters, Qt.Flags_QRhi__Flag{0}), root => gles_live(surface, parameters, root))

def gles_surface(surface: Qt.QOffscreenSurface) -> Qt.Action(Unit):
  Qt.QRhiGles2InitParams.with(Unit, Qt.QRhiGles2InitParams.new(), parameters => gles_params(surface, parameters))

def frame_kind(+root: Qt.QRhi, +first: Qt.QRhiSwapChain, +second: Qt.QRhiSwapChain) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    cb: Qt.QRhiCommandBuffer <- Qt.QRhi.beginOffscreen(root)
    wrong: Result<&1, &1, U32 & String, Qt.QRhi.FrameOpResult> <- Qt.Action.attempt(Qt.QRhi.FrameOpResult, Qt.QRhi.endFrame__QRhiSwapChain(root, first))
    rejected(Qt.QRhi.FrameOpResult, 22, wrong)
    finished: Qt.QRhi.FrameOpResult <- Qt.QRhi.finish(root)
    active: Bool <- Qt.QRhi.isRecordingFrame(root)
    require(active, "RHI finish ended the active frame")
    Qt.QRhi.endOffscreen(root)
    started: Qt.QRhi.FrameOpResult <- Qt.QRhi.beginFrame__QRhiSwapChain(root, first)
    wrong: Result<&1, &1, U32 & String, Qt.QRhi.FrameOpResult> <- Qt.Action.attempt(Qt.QRhi.FrameOpResult, Qt.QRhi.endOffscreenFrame(root))
    rejected(Qt.QRhi.FrameOpResult, 22, wrong)
    wrong: Result<&1, &1, U32 & String, Qt.QRhi.FrameOpResult> <- Qt.Action.attempt(Qt.QRhi.FrameOpResult, Qt.QRhi.endFrame__QRhiSwapChain(root, second))
    rejected(Qt.QRhi.FrameOpResult, 22, wrong)
    again: Result<&1, &1, U32 & String, Qt.QRhiCommandBuffer> <- Qt.Action.attempt(Qt.QRhiCommandBuffer, Qt.QRhi.beginOffscreen(root))
    rejected(Qt.QRhiCommandBuffer, 16, again)
    ended: Qt.QRhi.FrameOpResult <- Qt.QRhi.endFrame__QRhiSwapChain(root, first)
    Qt.CallbackProbe.rhiExternalFrame(root, True{})
    outside: Result<&1, &1, U32 & String, Qt.QRhi.FrameOpResult> <- Qt.Action.attempt(Qt.QRhi.FrameOpResult, Qt.QRhi.endOffscreenFrame(root))
    rejected(Qt.QRhi.FrameOpResult, 1, outside)
    outside: Result<&1, &1, U32 & String, Qt.QRhi.FrameOpResult> <- Qt.Action.attempt(Qt.QRhi.FrameOpResult, Qt.QRhi.finish(root))
    rejected(Qt.QRhi.FrameOpResult, 1, outside)
    Qt.CallbackProbe.rhiExternalFrame(root, False{})

def frame_second(root: Qt.QRhi, first: Qt.QRhiSwapChain, +second: Qt.QRhiSwapChain) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    ready: Bool <- Qt.QRhiSwapChain.createOrResize(second)
    require(ready, "Null swapchain creation failed")
    frame_kind(root, first, second)

def frame_first(+root: Qt.QRhi, +first: Qt.QRhiSwapChain) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    ready: Bool <- Qt.QRhiSwapChain.createOrResize(first)
    require(ready, "Null swapchain creation failed")
    Qt.QRhiSwapChain.with(Unit, Qt.QRhi.newSwapChain(root), second => frame_second(root, first, second))

def frame_contract(+root: Qt.QRhi) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    failed: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.CallbackProbe.rhiAbortFrame(root, False{}))
    rejected(Unit, 12, failed)
    active: Bool <- Qt.QRhi.isRecordingFrame(root)
    require(Bool.not(active), "Failed RHI output conversion left a native frame active")
    failed: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.CallbackProbe.rhiAbortFrame(root, True{}))
    rejected(Unit, 12, failed)
    active: Bool <- Qt.QRhi.isRecordingFrame(root)
    require(Bool.not(active), "Native exception left a native frame active")
    Qt.QRhiSwapChain.with(Unit, Qt.QRhi.newSwapChain(root), first => frame_first(root, first))

def queue_submit_parameters(+root: Qt.QRhi) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    parameters: Qt.QRhiNativeHandles <- Qt.QRhiNativeHandles.new()
    Qt.QRhi.setQueueSubmitParams(root, parameters)
    Qt.QRhi.setQueueSubmitParams(root, Qt.QRhiNativeHandles{0})
    active: Bool <- Qt.QRhi.isRecordingFrame(root)
    require(Bool.not(active), "Native queue-submit parameters changed frame state")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QRhi.with(Unit, Qt.QRhi.newNull(), value => root(value))
    Qt.QRhi.with(Unit, Qt.QRhi.newNull(), value => externally_deleted(value))
    Qt.QRhi.with(Unit, Qt.QRhi.newNull(), value => cancel_root(value))
    Qt.QRhi.with(Unit, Qt.QRhi.newNull(), value => failed_frame(value))
    Qt.QRhi.with(Unit, Qt.QRhi.newNull(), binding_root)
    Qt.QRhi.with(Unit, Qt.QRhi.newNull(), cross_source)
    Qt.QRhi.with(Unit, Qt.QRhi.newNull(), root => expire_root(root))
    Qt.QRhiNullInitParams.with(Unit, Qt.QRhiNullInitParams.new(), parameters => typed_null(parameters))
    Qt.QRhi.with(Unit, Qt.QRhi.newNull(), root => cleanup_signal(root))
    texture_arrays()
    Qt.QOffscreenSurface.with(Unit, Qt.QRhiGles2InitParams.newFallbackSurface(), gles_surface)
    Qt.QRhi.with(Unit, Qt.QRhi.newNull(), root => frame_contract(root))
    Qt.QRhi.with(Unit, Qt.QRhi.newNull(), root => queue_submit_parameters(root))
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "RHI lifecycle leaked native handles")
    Qt.Action.lift(Unit, IO.print("QT612_RHI_LIFETIMES_OK null_backend=1 factory_ownership=1 root_retained=1 batch_consumed=1 frame_cleanup=1 frame_kind=1 frame_owner=1 finish_preserves_frame=1 readback_snapshot=1 readback_cancel=1 external_root_cleanup=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
