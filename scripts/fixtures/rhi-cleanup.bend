import Base
import ../../packages/qt612/qt.bend as Qt

type State is Data:
  State{root: Qt.QRhi, buffer: Qt.QRhiBuffer}

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def rejected(-A: Type, expected: U32, result: Result<&1, &1, U32 & String, A>) -> Qt.Action(Unit):
  match result:
    case Fail{(actual, message)}: require(U32.is_eq(actual, expected), "Wrong cleanup error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "A cleanup operation unexpectedly succeeded")

def resource(present: Bool, buffer: Qt.QRhiBuffer) -> Qt.Action(Unit):
  match present:
    case False{}: Qt.Action.pure(Unit, Unit{})
    case True{}:
      do Qt.Action<Unit>:
        size: U32 <- Qt.QRhiBuffer.size(buffer)
        require(U32.is_eq(size, 4), "The native resource died before its cleanup handler")

# Resources stay usable while their cleanup handler runs; handlers cannot be
# changed during cleanup.
def cleanup_state(state: State, key: U32) -> Qt.Action(Unit):
  match state:
    case State{root, +buffer}:
      do Qt.Action<Unit>:
        resource(Bool.not(U32.is_eq(Qt.QRhiBuffer.word(buffer), 0)), buffer)
        blocked: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QRhi.removeCleanupHandler(root, 3))
        rejected(Unit, 16, blocked)
        Qt.CallbackProbe.cleanupHit(key)

def cleanup(state: State, key: U32) -> Qt.Action(Unit):
  cleanup_state(state, key)

def bad(code: U32, key: U32) -> Qt.Action(Unit):
  Qt.Action.fail(Unit, code, "A replaced, removed or failing handler ran")

def keyed(+root: Qt.QRhi) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QRhi.addCleanupHandler(~U32, ~bad, root, 1, 42)
    Qt.QRhi.addCleanupHandler(~State, ~cleanup, root, 1, State{root, Qt.QRhiBuffer{0}})
    Qt.QRhi.addCleanupHandler(~U32, ~bad, root, 2, 42)
    Qt.QRhi.removeCleanupHandler(root, 2)
    Qt.QRhi.removeCleanupHandler(root, 99)
    Qt.QRhi.addCleanupHandler(~State, ~cleanup, root, 3, State{root, Qt.QRhiBuffer{0}})
    Qt.QRhi.addCleanupHandlerUnkeyed(~State, ~cleanup, root, State{root, Qt.QRhiBuffer{0}})
    Qt.QRhi.destroy(root)

def external(+root: Qt.QRhi, +buffer: Qt.QRhiBuffer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QRhi.addCleanupHandler(~State, ~cleanup, root, 11, State{root, buffer})
    Qt.QRhi.addCleanupHandler(~State, ~cleanup, root, 12, State{root, buffer})
    Qt.CallbackProbe.rhiDeleteNative(root)
    stale: Result<&1, &1, U32 & String, U32> <- Qt.Action.attempt(U32, Qt.QRhiBuffer.size(buffer))
    rejected(U32, 116, stale)

def external_root(+root: Qt.QRhi) -> Qt.Action(Unit):
  Qt.QRhiBuffer.with(Unit, Qt.QRhi.newBuffer(root, Qt.QRhiBuffer.Type.Static(), Qt.QRhiBuffer.UsageFlag.UniformBuffer(), 4), buffer => external(root, buffer))

# A failed handler fails the Qt call that deleted the root.
def native_failed(+root: Qt.QRhi) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QRhi.addCleanupHandler(~U32, ~bad, root, 4, 43)
    failure: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.CallbackProbe.rhiDeleteNative(root))
    rejected(Unit, 43, failure)

def failed(+root: Qt.QRhi) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QRhi.addCleanupHandler(~U32, ~bad, root, 99, 42)
    failure: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QRhi.destroy(root))
    rejected(Unit, 42, failure)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QRhi.with(Unit, Qt.QRhi.newNull(), root => keyed(root))
    Qt.QRhi.with(Unit, Qt.QRhi.newNull(), root => external_root(root))
    Qt.QRhi.with(Unit, Qt.QRhi.newNull(), root => native_failed(root))
    Qt.QRhi.with(Unit, Qt.QRhi.newNull(), root => failed(root))
    hits: U32 <- Qt.CallbackProbe.cleanupHits()
    require(U32.is_eq(hits, 5), "The cleanup handler count changed")
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "QRhi cleanup leaked native entries")
    Qt.Action.lift(Unit, IO.print("QT612_RHI_CLEANUP_OK keyed_replace=1 keyed_remove=1 unkeyed=1 native_resource_phase=1 handler_error=1 hits=5 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
