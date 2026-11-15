import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def error(~A: Type, expected: U32, result: Result<&1, &1, U32 & String, A>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong shared-memory error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Invalid shared-memory operation succeeded")

def bytes(value: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    text: String <- Qt.QByteArray.utf8(value)
    require(String.eq(text, "test"), "Attached shared memory has wrong bytes")

def readonly(+view: Qt.MemoryView) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QByteArray.with(Unit, Qt.MemoryView.read(view, Qt.UInt64{0, 0}, Qt.UInt64{4, 0}), value => bytes(value))
    result: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QByteArray.with(Unit, Qt.QByteArray.fromUtf8("fail"), value => Qt.MemoryView.write(view, Qt.UInt64{0, 0}, value)))
    error(Unit, 1, result)

def attachment(+memory: Qt.QSharedMemory, key: String) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QSharedMemory.setKey(memory, key)
    attached: Bool <- Qt.QSharedMemory.attach__QSharedMemory_AccessMode(memory, Qt.QSharedMemory.AccessMode.ReadOnly())
    require(attached, "Read-only shared-memory attachment failed")
    Qt.MemoryView.with(Unit, Qt.QSharedMemory.data(memory), view => readonly(view))

def mapped(+view: Qt.MemoryView, +memory: Qt.QSharedMemory, key: String) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromUtf8("test"), value => Qt.MemoryView.write(view, Qt.UInt64{0, 0}, value))
    blocked: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.QSharedMemory.detach(memory))
    error(Bool, 16, blocked)
    Qt.QSharedMemory.with(Unit, Qt.QSharedMemory.new(), second => attachment(second, key))

def memory(+value: Qt.QSharedMemory, +key: String) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QSharedMemory.setKey(value, key)
    created: Bool <- Qt.QSharedMemory.create__Int64(value, Qt.Int64{4, 0})
    require(created, "Shared-memory segment creation failed")
    Qt.MemoryView.with(Unit, Qt.QSharedMemory.data(value), view => mapped(view, value, key))
    detached: Bool <- Qt.QSharedMemory.detach(value)
    require(detached, "View cleanup did not allow detachment")

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    pid: Qt.Int64 <- Qt.QCoreApplication.applicationPid()
    Qt.QSharedMemory.with(Unit, Qt.QSharedMemory.new(), value => memory(value, "bendqt-memory-" ++ U32.show(Qt.Int64.lo(pid))))
    objects: U32 <- Qt.Runtime.liveObjects()
    pins: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(pins, 0), "Shared memory leaked handles or pins")
    Qt.Action.lift(Unit, IO.print("QT612_SHARED_MEMORY_OK read_write=1 attachment=1 readonly=1 detach_guard=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
