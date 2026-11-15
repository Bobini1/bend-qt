import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def read_count(capacity: U32) -> U32:
  match capacity:
    case 2: 1
    case _: 3

def read_reply(+capacity: U32) -> Qt.Action(Qt.CallbackReply_Int64_QByteArray):
  match capacity:
    case 0:
      do Qt.Action<Qt.CallbackReply_Int64_QByteArray>:
        bytes: Qt.QByteArray <- Qt.QByteArray.fromBytes(Nil{})
        return Qt.CallbackReply_Int64_QByteArray{Qt.Int64{0, 0}, bytes}
    case 4:
      do Qt.Action<Qt.CallbackReply_Int64_QByteArray>:
        bytes: Qt.QByteArray <- Qt.QByteArray.fromBytes(Nil{})
        return Qt.CallbackReply_Int64_QByteArray{Qt.Int64{4294967295, 4294967295}, bytes}
    case _:
      do Qt.Action<Qt.CallbackReply_Int64_QByteArray>:
        bytes: Qt.QByteArray <- Qt.QByteArray.fromBytes(97 <> 0 <> 98 <> Nil{})
        return Qt.CallbackReply_Int64_QByteArray{Qt.Int64{read_count(capacity), 0}, bytes}

# Capacity 1 and 2 get replies that do not fit; 4 reports a native error.
def read_data(state: Unit, capacity: Qt.Int64) -> Qt.Action(Qt.CallbackReply_Int64_QByteArray):
  read_reply(Qt.Int64.lo(capacity))

def expected_bytes(bytes: List<&2, U32>) -> Bool:
  match bytes:
    case a <> b <> c <> Nil{}: U32.is_eq(a, 120) && U32.is_eq(b, 0) && U32.is_eq(c, 121)
    case _: False{}

def write_reply(bytes: Qt.QByteArray, capacity: U32) -> Qt.Action(Qt.Int64):
  match capacity:
    case 1: Qt.Action.pure(Qt.Int64, Qt.Int64{2, 0})
    case _:
      do Qt.Action<Qt.Int64>:
        data: List<&2, U32> <- Qt.QByteArray.toBytes(bytes)
        require(expected_bytes(data), "The write handler did not get the embedded NUL byte")
        return Qt.Int64{3, 0}

def write_data(state: Unit, bytes: Qt.QByteArray, capacity: Qt.Int64) -> Qt.Action(Qt.Int64):
  write_reply(bytes, Qt.Int64.lo(capacity))

def rejected(result: Result<&1, &1, U32 & String, U32>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 22), "Wrong device buffer rejection: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "A malformed byte reply was accepted")

def device_demo(+device: Qt.QIODevice) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QIODevice.Virtual.readData.handle(~Unit, ~read_data, device, Unit{})
    Qt.QIODevice.Virtual.writeData.handle(~Unit, ~write_data, device, Unit{})
    valid: U32 <- Qt.CallbackProbe.device(device, 0)
    require(U32.is_eq(valid, 1), "Native read, write or canary bytes failed")
    overflow: Result<&1, &1, U32 & String, U32> <- Qt.Action.attempt(U32, Qt.CallbackProbe.device(device, 1))
    rejected(overflow)
    mismatch: Result<&1, &1, U32 & String, U32> <- Qt.Action.attempt(U32, Qt.CallbackProbe.device(device, 2))
    rejected(mismatch)
    write_overflow: Result<&1, &1, U32 & String, U32> <- Qt.Action.attempt(U32, Qt.CallbackProbe.device(device, 3))
    rejected(write_overflow)
    native_error: U32 <- Qt.CallbackProbe.device(device, 4)
    require(U32.is_eq(native_error, 1), "The native -1 device result was lost")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QIODevice.with(Unit, Qt.QIODevice.newOverride(), device => device_demo(device))
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "The device handlers leaked byte array handles")
    Qt.Action.lift(Unit, IO.print("QT612_DEVICE_CALLBACKS_OK read=1 write=1 embedded_nul=1 bounds_rejected=1 mismatched_count_rejected=1 canaries=1 native_error=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
