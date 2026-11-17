import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def error(~A: Type, expected: U32, value: Result<&1, &1, U32 & String, A>) -> Qt.Action(Unit):
  match value:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong JS exposure error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Unsafe JS exposure operation succeeded; expected error " ++ U32.show(expected))

def stop(+thread: Qt.QThread) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QThread.quit(thread)
    done: Bool <- Qt.QThread.wait(thread)
    require(done, "Exposed object's thread did not stop")

def foreign_call(value: Result<&1, &1, U32 & String, String>) -> Qt.Action(Unit):
  match value:
    case Fail{(code, message)}: require(U32.is_eq(code, 18), "Wrong error for a moved object: " ++ message)
    case Done{name}: Qt.Action.fail(Unit, 1, "A moved object was used from the main thread")

# Once moved, the object belongs to the other thread, and calls on it from
# this thread fail.
def moved(+thread: Qt.QThread, +object: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    accepted: Bool <- Qt.QObject.moveToThread(object, thread)
    require(accepted, "Released JS exposure still blocked migration")
    foreign: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QObject.objectName(object))
    foreign_call(foreign)

# The thread deletes the object when it finishes. Its handle then reports
# the destruction.
def migrate(+thread: Qt.QThread, +object: Qt.QObject, connection: Qt.QMetaObject.Connection) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QThread.start(thread)
    Qt.Action.finally(Unit, moved(thread, object), stop(thread))
    Qt.QCoreApplication.processEvents()
    gone: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QObject.objectName(object))
    error(String, 116, gone)

def after_engine(+thread: Qt.QThread, +object: Qt.QObject) -> Qt.Action(Unit):
  Qt.QMetaObject.Connection.with(Unit, Qt.QObject.connect__QObject_String_QObject_String(Qt.QThread.as_QObject(thread), "2finished()", object, "1deleteLater()"),
    connection => migrate(thread, object, connection))

def held(+thread: Qt.QThread, +object: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    denied: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.QObject.moveToThread(object, thread))
    error(Bool, 18, denied)
    retained: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QObject.destroy(object))
    error(Unit, 16, retained)

def store_global(value: Qt.QJSValue, global: Qt.QJSValue) -> Qt.Action(Unit):
  Qt.QJSValue.setProperty__String_QJSValue(global, "exposedObject", value)

def wrapper(engine: Qt.QJSEngine, value: Qt.QJSValue) -> Qt.Action(Unit):
  Qt.QJSValue.with(Unit, Qt.QJSEngine.globalObject(engine), global => store_global(value, global))

def engine(+thread: Qt.QThread, +object: Qt.QObject, +value: Qt.QJSEngine) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    cycle: Result<&1, &1, U32 & String, Qt.QJSValue> <- Qt.Action.attempt(Qt.QJSValue, Qt.QJSEngine.newQObject(value, Qt.QJSEngine.as_QObject(value)))
    error(Qt.QJSValue, 40, cycle)
    Qt.QJSEngine.setObjectOwnership(object, Qt.QJSEngine.ObjectOwnership.CppOwnership())
    Qt.QJSValue.with(Unit, Qt.QJSEngine.newQObject(value, object), wrapped => wrapper(value, wrapped))
    held(thread, object)
    Qt.QJSEngine.destroy(value)
    after_engine(thread, object)

def object(thread: Qt.QThread, +value: Qt.QObject) -> Qt.Action(Unit):
  Qt.QJSEngine.with(Unit, Qt.QJSEngine.new(), js => engine(thread, value, js))

def thread(value: Qt.QThread) -> Qt.Action(Unit):
  Qt.QObject.with(Unit, Qt.QObject.new(), target => object(value, target))

# A variant that fails part way through conversion leaves its object free.
def context_bad_variant(+thread: Qt.QThread, +object: Qt.QObject, context: Qt.QQmlContext, variant: Qt.QVariant) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    failed: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QQmlContext.setContextProperty__String_QVariant(context, "bad", variant))
    error(Unit, 95, failed)
    after_engine(thread, object)

def failed_context(+thread: Qt.QThread, +object: Qt.QObject, engine: Qt.QQmlEngine) -> Qt.Action(Unit):
  Qt.QQmlContext.with(Unit, Qt.QQmlContext.new__QQmlEngine_QObject(engine, Qt.QObject{0}), context =>
    Qt.QVariant.with(Unit, Qt.Fixture.badExposedVariant(object), variant => context_bad_variant(thread, object, context, variant)))

def failed_object(thread: Qt.QThread, +object: Qt.QObject) -> Qt.Action(Unit):
  Qt.QQmlEngine.with(Unit, Qt.QQmlEngine.new(), engine => failed_context(thread, object, engine))

def failed_thread(thread: Qt.QThread) -> Qt.Action(Unit):
  Qt.QObject.with(Unit, Qt.QObject.new(), object => failed_object(thread, object))

def context_variant(+context: Qt.QQmlContext, variant: Qt.QVariant) -> Qt.Action(Unit):
  Qt.QQmlContext.setContextProperty__String_QVariant(context, "nested", variant)

def context(+thread: Qt.QThread, +object: Qt.QObject, +engine: Qt.QQmlEngine, +value: Qt.QQmlContext) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQmlContext.setContextObject(value, object)
    Qt.QQmlContext.setContextProperty__String_QObject(value, "target", object)
    Qt.QVariant.with(Unit, Qt.Fixture.exposedVariant(object), variant => context_variant(value, variant))
    Qt.QQmlContext.setContextObject(value, Qt.QObject{0})
    Qt.QQmlContext.setContextProperty__String_QObject(value, "target", Qt.QObject{0})
    Qt.QQmlContext.destroy(value)
    held(thread, object)
    Qt.QQmlEngine.destroy(engine)
    after_engine(thread, object)

def context_engine(+thread: Qt.QThread, +object: Qt.QObject, +engine: Qt.QQmlEngine) -> Qt.Action(Unit):
  Qt.QQmlContext.with(Unit, Qt.QQmlContext.new__QQmlEngine_QObject(engine, Qt.QObject{0}), value => context(thread, object, engine, value))

def context_object(thread: Qt.QThread, +object: Qt.QObject) -> Qt.Action(Unit):
  Qt.QQmlEngine.with(Unit, Qt.QQmlEngine.new(), engine => context_engine(thread, object, engine))

def context_thread(thread: Qt.QThread) -> Qt.Action(Unit):
  Qt.QObject.with(Unit, Qt.QObject.new(), object => context_object(thread, object))

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QThread.with(Unit, Qt.QThread.new(), thread)
    Qt.QThread.with(Unit, Qt.QThread.new(), failed_thread)
    Qt.QThread.with(Unit, Qt.QThread.new(), context_thread)
    objects: U32 <- Qt.Runtime.liveObjects()
    retentions: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(retentions, 0), "JS exposure cleanup leaked registry state")
    Qt.Action.lift(Unit, IO.print("QT612_JS_EXPOSURE_OK global_heap=1 wrapper_released=1 context_cleared=1 recursive_variant=1 failed_prefix_unpinned=1 migration_blocked=1 engine_release=1 cycles_rejected=1 thread_affinity=1 objects=0 retentions=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
