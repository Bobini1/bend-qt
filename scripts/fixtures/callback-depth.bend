import Base
import ../../packages/qt612/qt.bend as Qt

def descend() -> Qt.Signal:
  Qt.Signal.define("descend", [Qt.u32()])

def step_case(object: Qt.QObject, depth: U32, done: Bool) -> Qt.Action(Unit):
  match done:
    case True{}: Qt.QObject.setObjectName(object, "done")
    case False{}: Qt.Signal.emit(~descend(), object, U32.sub(depth, 1))

def step(object: Qt.QObject, depth: U32) -> Qt.Action(Unit):
  +n = depth
  step_case(object, n, U32.is_eq(n, 0))

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def objects() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +object: Qt.QObject <- Qt.QObject.newWithSignals("DeepCallbacks", [descend()])
    connection: Qt.Connection <- Qt.Signal.connect(~descend(), ~Qt.QObject, ~step, object, object)
    Qt.Signal.emit(~descend(), object, 300)
    name: String <- Qt.QObject.objectName(object)
    require(String.eq(name, "done"), "A deeply nested signal handler was skipped")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, objects())
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Deep callbacks leaked")
    Qt.Action.lift(Unit, IO.print("QT612_CALLBACK_DEPTH_OK nested=301 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
