import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def error(-A: Type, code: U32, result: Result<&1, &1, U32 & String, A>) -> Qt.Action(Unit):
  match result:
    case Fail{(actual, message)}: require(U32.is_eq(code, actual), "Wrong generic invocation error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Unsafe generic invocation succeeded")

def readonly_type(+storage: Qt.MetaStorage, meta: Qt.QMetaType) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    rejected: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QMetaType.destruct__MetaStorage(meta, storage))
    error(Unit, 1, rejected)

def readonly_storage(+storage: Qt.MetaStorage) -> Qt.Action(Unit):
  Qt.QMetaType.with(Unit, Qt.MetaStorage.metaType(storage), meta => readonly_type(storage, meta))

def wrong_object(+method: Qt.QMetaMethod, +argument: Qt.QGenericArgument, object: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    rejected: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.QMetaMethod.invoke__QObject_QGenericArgument(method, object, argument))
    error(Bool, 22, rejected)

def wrong_method(+method: Qt.QMetaMethod, +argument: Qt.QGenericArgument) -> Qt.Action(Unit):
  Qt.QObject.with(Unit, Qt.QObject.new(), object => wrong_object(method, argument, object))

def wrong_metadata(+metadata: Qt.QMetaObject, +argument: Qt.QGenericArgument) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    index: Qt.Int32 <- Qt.QMetaObject.indexOfMethod(metadata, "start(int)")
    Qt.QMetaMethod.with(Unit, Qt.QMetaObject.method(metadata, index), method => wrong_method(method, argument))

def start(+timer: Qt.QTimer, +argument: Qt.QGenericArgument) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.MetaStorage.with(Unit, Qt.QGenericArgument.data(argument), storage => readonly_storage(storage))
    Qt.QMetaObject.with(Unit, Qt.QTimer.metaObject(timer), metadata => wrong_metadata(metadata, argument))
    called: Bool <- Qt.QMetaObject.invokeMethod__QObject_String_QGenericArgument(Qt.QTimer.as_QObject(timer), "start", argument)
    require(called, "QObject typed invocation failed")
    active: Bool <- Qt.QTimer.isActive(timer)
    require(active, "Native meta-call did not start the timer")
    blocked: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.QMetaObject.invokeMethod__QObject_String_Qt_ConnectionType_QGenericArgument(Qt.QTimer.as_QObject(timer), "start", Qt.Qt.ConnectionType{3}, argument))
    error(Bool, 35, blocked)

def start_storage(+timer: Qt.QTimer, storage: Qt.MetaStorage) -> Qt.Action(Unit):
  Qt.QGenericArgument.with(Unit, Qt.QGenericArgument.fromStorage(storage), argument => start(timer, argument))

def start_variant(+timer: Qt.QTimer, variant: Qt.QVariant) -> Qt.Action(Unit):
  Qt.MetaStorage.with(Unit, Qt.MetaStorage.fromVariant(variant), storage => start_storage(timer, storage))

def delete_later(+timer: Qt.QTimer, empty: Qt.QGenericArgument) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    called: Bool <- Qt.QMetaObject.invokeMethod__QObject_String_QGenericArgument(Qt.QTimer.as_QObject(timer), "deleteLater", empty)
    require(called, "Checked dynamic deletion did not run")
    # deleteLater takes effect when Qt delivers its deferred deletions.
    Qt.QCoreApplication.sendPostedEvents__QObject_Int32(Qt.QObject{0}, Qt.Int32{52})
    stale: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.QTimer.isActive(timer))
    error(Bool, 116, stale)

def timer(+value: Qt.QTimer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QVariant.with(Unit, Qt.QVariant.fromInt32(Qt.Int32{100000}), variant => start_variant(value, variant))
    Qt.QGenericArgument.with(Unit, Qt.QGenericArgument.new(), empty => delete_later(value, empty))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QTimer.with(Unit, Qt.QTimer.new(), value => timer(value))
    objects: U32 <- Qt.Runtime.liveObjects()
    pins: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(pins, 0), "Generic invocation leaked typed storage")
    Qt.Action.lift(Unit, IO.print("QT612_GENERIC_INVOCATION_OK typed=1 readonly=1 deadlock_rejected=1 checked_delete=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
