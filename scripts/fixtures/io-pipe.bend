import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def mark(+probe: Qt.QObject, suffix: String) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    old: String <- Qt.QObject.objectName(probe)
    Qt.QObject.setObjectName(probe, old ++ suffix)

def readable(probe: Qt.QObject) -> Qt.Action(Unit):
  mark(probe, "R")

def written_count(probe: Qt.QObject, +bytes: Qt.Int64) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    require(U32.is_eq(Qt.Int64.lo(bytes), 8) && U32.is_eq(Qt.Int64.hi(bytes), 0), "Pipe bytesWritten changed its exact byte count")
    mark(probe, "W")

def written(probe: Qt.QObject, bytes: Qt.Int64) -> Qt.Action(Unit):
  written_count(probe, bytes)

def received(bytes: Qt.QByteArray, expected: String) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    text: String <- Qt.QByteArray.utf8(bytes)
    require(String.eq(text, expected), "A duplex pipe changed its buffered bytes")

def transfer(+probe: Qt.QObject, +first: Qt.QIODevice, +second: Qt.QIODevice) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +count: Qt.Int64 <- Qt.QIODevice.write__String(first, "hello λ")
    require(U32.is_eq(Qt.Int64.lo(count), 8) && U32.is_eq(Qt.Int64.hi(count), 0), "Pipe write lost a UTF-8 byte")
    Qt.QByteArray.with(Unit, Qt.QIODevice.readAll(second), bytes => received(bytes, "hello λ"))
    back: Qt.Int64 <- Qt.QIODevice.write__String(second, "response")
    Qt.QByteArray.with(Unit, Qt.QIODevice.readAll(first), bytes => received(bytes, "response"))
    seen: String <- Qt.QObject.objectName(probe)
    require(String.eq(seen, "WR"), "Pipe native signals changed delivery order")

def signals(+probe: Qt.QObject, +first: Qt.QIODevice, +second: Qt.QIODevice) -> Qt.Action(Unit):
  Qt.Connection.with(Unit, Qt.Signal.connect(~Qt.QIODevice.readyRead(), ~Qt.QObject, ~readable, second, probe), connection =>
    Qt.Connection.with(Unit, Qt.Signal.connect(~Qt.QIODevice.bytesWritten(), ~Qt.QObject, ~written, first, probe), connection => transfer(probe, first, second)))

def opened(+probe: Qt.QObject, +pipe: Qt.QtCoreHelper.QIOPipe) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    ok: Bool <- Qt.QtCoreHelper.QIOPipe.open(pipe, Qt.QIODeviceBase.OpenModeFlag.ReadWrite())
    require(ok, "QIOPipe did not open")
    Qt.QIODevice.with(Unit, Qt.QtCoreHelper.QIOPipe.end1(pipe), first =>
      Qt.QIODevice.with(Unit, Qt.QtCoreHelper.QIOPipe.end2(pipe), second => signals(probe, first, second)))

def retained_view(+pipe: Qt.QtCoreHelper.QIOPipe) -> Qt.Action(Qt.QIODevice):
  do Qt.Action<Qt.QIODevice>:
    ok: Bool <- Qt.QtCoreHelper.QIOPipe.open(pipe, Qt.QIODeviceBase.OpenModeFlag.ReadWrite())
    require(ok, "QIOPipe lifetime test did not open")
    Qt.QtCoreHelper.QIOPipe.end1(pipe)

def retained(pipe: Qt.QtCoreHelper.QIOPipe) -> Qt.Action(Qt.QIODevice):
  retained_view(pipe)

def expired(result: Result<&1, &1, U32 & String, Bool>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 116), "A deleted pipe endpoint reported the wrong error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "A pipe endpoint outlived its native owner")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QObject.with(Unit, Qt.QObject.new(), probe =>
      Qt.QtCoreHelper.QIOPipe.with(Unit, Qt.QtCoreHelper.QIOPipe.new(), pipe => opened(probe, pipe)))
    escaped: Qt.QIODevice <- Qt.QtCoreHelper.QIOPipe.with(Qt.QIODevice, Qt.QtCoreHelper.QIOPipe.new(), retained)
    validity: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.QIODevice.isOpen(escaped))
    expired(validity)
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "QIOPipe leaked native state")
    Qt.Action.lift(Unit, IO.print("QT612_IO_PIPE_OK duplex=1 signals=1 endpoint_lifetime=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
