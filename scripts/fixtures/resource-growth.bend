import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def allocate(remaining: Nat) -> Qt.Action(Unit):
  match remaining:
    case 0n: Qt.Action.pure(Unit, Unit{})
    case 1n+rest:
      do Qt.Action<Unit>:
        object: Qt.QObject <- Qt.QObject.new()
        allocate(rest)

def grow(probe: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    allocate(5000n)
    count: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_gt(count, 5000), "The registry did not grow beyond 4096 objects")
    Qt.QObject.setObjectName(probe, "grown")

def grow_on_destruction(probe: Qt.QObject, identity: Qt.ObjectIdentity) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    allocate(5000n)
    Qt.QObject.setObjectName(probe, "destruction growth")

def destruction_body(probe: Qt.QObject, source: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    connection: Qt.Connection <- Qt.Signal.connect(~Qt.QObject.destroyed(), ~Qt.QObject, ~grow_on_destruction, source, probe)
    return Unit{}

def noop(state: Unit, text: String) -> Qt.Action(Unit):
  Qt.Action.pure(Unit, Unit{})

def connections(remaining: Nat, +sender: Qt.QObject) -> Qt.Action(Unit):
  match remaining:
    case 0n: Qt.Action.pure(Unit, Unit{})
    case 1n+rest:
      do Qt.Action<Unit>:
        connection: Qt.Connection <- Qt.Signal.connect(~Qt.QObject.objectNameChanged(), ~Unit, ~noop, sender, Unit{})
        connections(rest, sender)

def resize_signal() -> Qt.Signal:
  Qt.Signal.define("resizeRegistry", [])

def objects() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +source: Qt.QObject <- Qt.QObject.newWithSignals("RegistryGrowth", [resize_signal()])
    +probe: Qt.QObject <- Qt.QObject.new()
    Qt.QObject.with(Unit, Qt.QObject.new(), source => destruction_body(probe, source))
    destroyed: String <- Qt.QObject.objectName(probe)
    require(String.eq(destroyed, "destruction growth"), "Registry iteration did not survive destruction-handler growth")
    +value: Qt.QVariant <- Qt.QVariant.fromString("retained before growth")
    connection: Qt.Connection <- Qt.Signal.connect(~resize_signal(), ~Qt.QObject, ~grow, source, probe)
    Qt.Signal.emit(~resize_signal(), source)
    name: String <- Qt.QObject.objectName(probe)
    require(String.eq(name, "grown"), "An active native call was invalidated by registry growth")
    text: String <- Qt.QVariant.toString(value)
    require(String.eq(text, "retained before growth"), "A value sidecar moved during registry growth")
    connections(8500n, probe)
    live: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_gt(live, 8500), "The connection registry did not grow")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, objects())
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "A grown registry did not clean up")
    Qt.Action.lift(Unit, IO.print("QT612_RESOURCE_GROWTH_OK objects=5000 connections=8501 reentrant=1 destruction=1 stable_entries=1 stable_iteration=1 sidecars=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
