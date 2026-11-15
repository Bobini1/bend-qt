import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def nonzero(value: Qt.UInt64) -> Bool:
  match value:
    case Qt.UInt64{lo, hi}:
      U32.is_gt(lo, 0) || U32.is_gt(hi, 0)

def pinned(result: Result<&1, &1, U32 & String, Bool>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 16), "Unexpected library retention error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Library unloaded while a function capability was live")

def function(library: Qt.QLibrary, +value: Qt.NativeFunction) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    address: Qt.UInt64 <- Qt.NativeFunction.address(value)
    require(nonzero(address), "Native function resolution returned a null address")
    blocked: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.QLibrary.unload(library))
    pinned(blocked)

def library(+value: Qt.QLibrary) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.NativeFunction.with(Unit, Qt.QLibrary.resolve__String(value, "abs"), fn => function(value, fn))
    unloaded: Bool <- Qt.QLibrary.unload(value)
    Qt.Action.pure(Unit, Unit{})

def key(+value: Qt.QSslKey, +native: Qt.NativeSslKey) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    kind: Qt.QSsl.KeyType <- Qt.QSslKey.type(value)
    Qt.QSslKey.clear(value)
    null: Bool <- Qt.NativeSslKey.isNull(native)
    require(null, "Empty SSL key native snapshot was not null")
    Qt.QSslKey.with(Unit, Qt.QSslKey.new__NativeSslKey_QSsl_KeyType(native, kind), copy => Qt.Action.pure(Unit, Unit{}))

def key_owner(+value: Qt.QSslKey) -> Qt.Action(Unit):
  Qt.NativeSslKey.with(Unit, Qt.QSslKey.handle(value), native => key(value, native))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QLibrary.with(Unit, Qt.QLibrary.new__String_QObject("libc.so.6", Qt.QObject{0}), value => library(value))
    Qt.QSslKey.with(Unit, Qt.QSslKey.new(), value => key_owner(value))
    count: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(count, 0), "Native interoperability scopes leaked handles")
    Qt.Action.lift(Unit, IO.print("QT612_NATIVE_INTEROP_OK function=1 scoped_owner=1 library_guard=1 ssl_snapshot=1 copied_key=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
