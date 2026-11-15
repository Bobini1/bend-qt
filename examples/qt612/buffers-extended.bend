import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def bytes_equal(expected: List<&2, U32>, actual: List<&2, U32>) -> Bool:
  match expected actual:
    case Nil{} Nil{}: True{}
    case a <> rest b <> tail: U32.is_eq(a, b) && bytes_equal(rest, tail)
    case _ _: False{}

def error(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong bounded-buffer error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected bounded-buffer failure")

def check_bytes(expected: List<&2, U32>, value: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    actual: List<&2, U32> <- Qt.QByteArray.toBytes(value)
    require(bytes_equal(expected, actual), "Native bounded buffer bytes changed")

def compressed(+value: Qt.QByteArray) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    size: Qt.Int64 <- Qt.QByteArray.size(value)
    Qt.QByteArray.with(Unit, Qt.Global.qUncompress__QByteArray_Int64(value, size), decoded => check_bytes(0 <> 255 <> 65 <> 0 <> Nil{}, decoded))

def compression(value: Qt.QByteArray) -> Qt.Action(Unit):
  Qt.QByteArray.with(Unit, Qt.Global.qCompress__QByteArray_Int64_Int32(value, Qt.Int64{4, 0}, Qt.Int32.neg(1)), encoded => compressed(encoded))

def read_alias(+source: Qt.QByteArray, +device: Qt.QBuffer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    opened: Bool <- Qt.QBuffer.open(device, Qt.Flags_QIODeviceBase__OpenModeFlag{1})
    require(opened, "Could not open retained input buffer")
    seeked: Bool <- Qt.QBuffer.seek(device, Qt.Int64{1, 0})
    require(seeked, "Could not seek retained input buffer")
    bad: Result<&1, &1, U32 & String, Qt.Int64> <- Qt.Action.attempt(Qt.Int64, Qt.QBuffer.read__QByteArray_Int64(device, source, Qt.Int64{5, 0}))
    error(Qt.Int64, bad, 34)
    count: Qt.Int64 <- Qt.QBuffer.read__QByteArray_Int64(device, source, Qt.Int64{3, 0})
    require(U32.is_eq(Qt.Int64.lo(count), 3), "Mutable output did not read all available bytes")
    check_bytes(66 <> 67 <> 68 <> 68 <> Nil{}, source)

def aliased(+source: Qt.QByteArray) -> Qt.Action(Unit):
  Qt.QBuffer.with(Unit, Qt.QBuffer.new__QByteArray_QObject(source, Qt.QObject{0}), device => read_alias(source, device))

def matrix_result(result: Qt.Outputs_List_F64) -> Qt.Action(Unit):
  match result:
    case Qt.Outputs_List_F64{a <> b <> c <> d <> Nil{}}:
      do Qt.Action<Unit>:
        first: Bool <- Qt.F64.equal(a, Qt.F64{0, 1072693248})
        second: Bool <- Qt.F64.equal(b, Qt.F64{0, 1073741824})
        third: Bool <- Qt.F64.equal(c, Qt.F64{0, 1074266112})
        fourth: Bool <- Qt.F64.equal(d, Qt.F64{0, 1074790400})
        require(first && second && third && fourth, "Typed array output lost matrix values")
    case _: Qt.Action.fail(Unit, 1, "Typed array output changed its shape")

def matrix(+value: Qt.QMatrix2x2) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    bad: Result<&1, &1, U32 & String, Qt.Outputs_List_F64> <- Qt.Action.attempt(Qt.Outputs_List_F64, Qt.QMatrix2x2.copyDataTo(value, Nil{}))
    error(Qt.Outputs_List_F64, bad, 22)
    Qt.Outputs_List_F64.with(Unit, Qt.QMatrix2x2.copyDataTo(value, Qt.F64{0, 0} <> Qt.F64{0, 0} <> Qt.F64{0, 0} <> Qt.F64{0, 0} <> Nil{}), matrix_result)

def connected(+source: Qt.QObject, +target: Qt.QTimer, connection: Qt.QMetaObject.Connection) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QTimer.setInterval__Int32(target, Qt.Int32{10000})
    Qt.QTimer.setSingleShot(target, True{})
    Qt.QObject.setObjectName(source, "Native slot 🎵")
    active: Bool <- Qt.QTimer.isActive(target)
    require(active, "Native string-signature connection did not invoke its slot")
    disconnected: Bool <- Qt.QObject.disconnect__QMetaObject_Connection(connection)
    require(disconnected, "Native connection handle did not disconnect")
    Qt.QTimer.stop(target)
    Qt.QObject.setObjectName(source, "Disconnected")
    last: Bool <- Qt.QTimer.isActive(target)
    require(Bool.not(last), "Native slot remained connected")

def connect(+source: Qt.QObject, +target: Qt.QTimer) -> Qt.Action(Unit):
  Qt.QMetaObject.Connection.with(Unit, Qt.QObject.connect__QObject_String_QObject_String_Qt_ConnectionType(source, "2objectNameChanged(QString)", Qt.QTimer.as_QObject(target), "1start()", Qt.Qt.ConnectionType.AutoConnection()), connection => connected(source, target, connection))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes(0 <> 255 <> 65 <> 0 <> Nil{}), compression)
    Qt.QByteArray.with(Unit, Qt.QByteArray.fromBytes(65 <> 66 <> 67 <> 68 <> Nil{}), value => aliased(value))
    Qt.QMatrix2x2.with(Unit, Qt.QMatrix2x2.fromValues(Qt.F64{0, 1072693248} <> Qt.F64{0, 1073741824} <> Qt.F64{0, 1074266112} <> Qt.F64{0, 1074790400} <> Nil{}), value => matrix(value))
    Qt.QObject.with(Unit, Qt.QObject.new(), source => Qt.QTimer.with(Unit, Qt.QTimer.new(), target => connect(source, target)))
    count: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(count, 0), "Extended buffer scopes leaked handles")
    Qt.Action.lift(Unit, IO.print("QT612_BUFFERS_EXTENDED_OK compression=1 bounded_output=1 alias_scratch=1 typed_array_output=1 native_string_slot=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
