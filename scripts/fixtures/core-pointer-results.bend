import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expected(-A: Type, result: Result<&1, &1, U32 & String, A>, code: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(+actual, message)}: require(U32.is_eq(actual, code), "Core pointer error " ++ U32.show(actual) ++ ": " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Invalid core pointer operation succeeded")

def received_kind(state: Qt.QObject, close: Bool) -> Qt.Action(Bool):
  match close:
    case True{}:
      do Qt.Action<Bool>:
        Qt.QObject.setObjectName(state, "delivered")
        return True{}
    case False{}: Qt.Action.pure(Bool, False{})

def received(state: Qt.QObject, event: Qt.QEvent) -> Qt.Action(Bool):
  do Qt.Action<Bool>:
    kind: Qt.QEvent.Type <- Qt.QEvent.type(event)
    received_kind(state, U32.is_eq(Qt.QEvent.Type.word(kind), Qt.QEvent.Type.word(Qt.QEvent.Type.Close())))

def event_clones() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +state: Qt.QObject <- Qt.QObject.new()
    +receiver: Qt.QObject <- Qt.QObject.newOverride()
    Qt.QObject.Virtual.event.handle(~Qt.QObject, ~received, receiver, state)
    +original: Qt.QCloseEvent <- Qt.QCloseEvent.new()
    Qt.QCloseEvent.ignore(original)
    +copy: Qt.QEvent <- Qt.QEvent.clone(Qt.QCloseEvent.as_QEvent(original))
    Qt.QCloseEvent.destroy(original)
    accepted: Bool <- Qt.QEvent.isAccepted(copy)
    require(Bool.not(accepted), "Event clone lost independent native state")
    dynamic: Bool <- Qt.CallbackProbe.isCloseEvent(copy)
    require(dynamic, "Cloning through QEvent sliced the concrete event type")
    Qt.QCoreApplication.postEvent__QObject_QEvent(receiver, copy)
    Qt.QCoreApplication.sendPostedEvents__QObject_Int32(receiver, Qt.Int32{0})
    text: String <- Qt.QObject.objectName(state)
    require(String.eq(text, "delivered"), "A native event clone could not be posted")
    stale: Result<&1, &1, U32 & String, Qt.QEvent.Type> <- Qt.Action.attempt(Qt.QEvent.Type, Qt.QEvent.type(copy))
    expected(Qt.QEvent.Type, stale, 116)
    +child: Qt.QObject <- Qt.QObject.new()
    +original: Qt.QChildEvent <- Qt.QChildEvent.new(Qt.QEvent.Type.ChildAdded(), child)
    +copy: Qt.QChildEvent <- Qt.QChildEvent.clone(original)
    Qt.QChildEvent.destroy(original)
    held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QObject.destroy(child))
    expected(Unit, held, 16)
    actual: Qt.QObject <- Qt.QChildEvent.child(copy)
    require(U32.is_eq(Qt.QObject.word(actual), Qt.QObject.word(child)), "Event clone lost its dependent QObject")
    Qt.QCoreApplication.postEvent__QObject_QEvent(receiver, Qt.QChildEvent.as_QEvent(copy))
    held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QObject.destroy(child))
    expected(Unit, held, 16)
    Qt.QCoreApplication.sendPostedEvents__QObject_Int32(receiver, Qt.Int32{0})
    Qt.QObject.destroy(child)

def icon_clones() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +source: Qt.QIconEngine <- Qt.CallbackProbe.cloneableIconEngine()
    +copy: Qt.QIconEngine <- Qt.QIconEngine.clone(source)
    Qt.QIconEngine.destroy(source)
    key: String <- Qt.QIconEngine.key(copy)
    require(String.eq(key, "CorePointerIcon"), "Icon engine clone was not independently owned")
    +icon: Qt.QIcon <- Qt.QIcon.new__QIconEngine(copy)
    +shared: Qt.QIcon <- Qt.QIcon.new__QIcon(icon)
    Qt.QIcon.destroy(icon)
    key: String <- Qt.QIconEngine.key(copy)
    require(String.eq(key, "CorePointerIcon"), "Shared QIcon released its engine too soon")
    name: String <- Qt.QIcon.name(shared)
    require(String.eq(name, "CorePointerIcon"), "Observing icon engine did not forward its native name")
    Qt.QIcon.destroy(shared)
    stale: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QIconEngine.key(copy))
    expected(String, stale, 116)

def promote() -> Qt.Action(Qt.QRandomGenerator):
  do Qt.Action<Qt.QRandomGenerator>:
    value: Qt.QRandomGenerator <- Qt.QRandomGenerator.global()
    Qt.QRandomGenerator.moveToParentScope(value)

def static_views() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +global: Qt.QRandomGenerator <- Qt.QRandomGenerator.global()
    +alias: Qt.QRandomGenerator <- Qt.QRandomGenerator.global()
    require(U32.is_eq(Qt.QRandomGenerator.word(global), Qt.QRandomGenerator.word(alias)), "Static generator identity changed")
    number: U32 <- Qt.QRandomGenerator.bounded__U32(global, 1)
    require(U32.is_eq(number, 0), "Static generator was not usable")
    borrowed: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QRandomGenerator.destroy(global))
    expected(Unit, borrowed, 1)
    Qt.QRandomGenerator.release(global)
    stale: Result<&1, &1, U32 & String, U32> <- Qt.Action.attempt(U32, Qt.QRandomGenerator.generate(alias))
    expected(U32, stale, 116)
    +kept: Qt.QRandomGenerator <- Qt.scoped(Qt.QRandomGenerator, promote())
    number: U32 <- Qt.QRandomGenerator.bounded__U32(kept, 1)
    require(U32.is_eq(number, 0), "Keeping a static view lost its scope")
    Qt.QRandomGenerator.release(kept)
    +system: Qt.QRandomGenerator <- Qt.QRandomGenerator.system()
    number: U32 <- Qt.QRandomGenerator.bounded__U32(system, 1)
    require(U32.is_eq(number, 0), "System generator was not usable")
    Qt.QRandomGenerator.release(system)
    +global64: Qt.QRandomGenerator64 <- Qt.QRandomGenerator64.global()
    _: Qt.UInt64 <- Qt.QRandomGenerator64.generate64(global64)
    Qt.QRandomGenerator64.release(global64)
    +system64: Qt.QRandomGenerator64 <- Qt.QRandomGenerator64.system()
    _: Qt.UInt64 <- Qt.QRandomGenerator64.generate64(system64)
    Qt.QRandomGenerator64.release(system64)
    +logging: Qt.QLoggingCategory <- Qt.QLoggingCategory.defaultCategory()
    +alias: Qt.QLoggingCategory <- Qt.QLoggingCategory.defaultCategory()
    before: Bool <- Qt.QLoggingCategory.isEnabled(logging, Qt.QtMsgType.QtWarningMsg())
    Qt.QLoggingCategory.setEnabled(logging, Qt.QtMsgType.QtWarningMsg(), False{})
    disabled: Bool <- Qt.QLoggingCategory.isEnabled(alias, Qt.QtMsgType.QtWarningMsg())
    Qt.QLoggingCategory.setEnabled(logging, Qt.QtMsgType.QtWarningMsg(), before)
    require(Bool.not(disabled), "Static logging category was copied rather than shared")
    Qt.QLoggingCategory.release(logging)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, event_clones())
    Qt.scoped(Unit, icon_clones())
    Qt.scoped(Unit, static_views())
    +objects: U32 <- Qt.Runtime.liveObjects()
    +retentions: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(retentions, 0), "Core pointer adapters leaked resources")
    Qt.Action.lift(Unit, IO.print("QT612_CORE_POINTER_RESULTS_OK clones=1 dynamic_type=1 post_event=1 dependencies=1 static_identity=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
