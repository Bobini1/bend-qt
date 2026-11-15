import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expect_error(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong destruction error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected a destruction error")

# QObject.destroyed passes the identity of the object being destroyed: its
# handle is no longer usable when the handler runs. The handler records the
# identity in the probe's name.
def destroyed(probe: Qt.QObject, identity: Qt.ObjectIdentity) -> Qt.Action(Unit):
  Qt.QObject.setObjectName(probe, U32.show(Qt.ObjectIdentity.word(identity)))

def watched(+object: Qt.QObject, +probe: Qt.QObject, connection: Qt.Connection) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +identity: U32 = Qt.QObject.word(object)
    Qt.QObject.destroy(object)
    seen: String <- Qt.QObject.objectName(probe)
    require(String.eq(seen, U32.show(identity)), "Destruction did not run the handler with the object's identity")
    stale: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QObject.objectName(object))
    expect_error(String, stale, 116)
    # The connection ended with its sender.
    ended: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.Connection.disconnect(connection))
    expect_error(Unit, ended, 116)

def watch(+probe: Qt.QObject, +object: Qt.QObject) -> Qt.Action(Unit):
  Qt.Connection.with(Unit, Qt.QObject.connect_destroyed(~Qt.QObject, ~destroyed, object, probe),
    connection => watched(object, probe, connection))

def parent_watched(+parent: Qt.QObject, +child: Qt.QObject, +probe: Qt.QObject, connection: Qt.Connection) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +identity: U32 = Qt.QObject.word(child)
    Qt.QObject.destroy(parent)
    seen: String <- Qt.QObject.objectName(probe)
    require(String.eq(seen, U32.show(identity)), "Parent destruction did not report the child")

def watch_child(+probe: Qt.QObject, +parent: Qt.QObject, +child: Qt.QObject) -> Qt.Action(Unit):
  Qt.Connection.with(Unit, Qt.QObject.connect_destroyed(~Qt.QObject, ~destroyed, child, probe),
    connection => parent_watched(parent, child, probe, connection))

def watch_parent(+probe: Qt.QObject, +parent: Qt.QObject) -> Qt.Action(Unit):
  Qt.QObject.with(Unit, Qt.QObject.new__QObject(parent), child => watch_child(probe, parent, child))

def cases(+probe: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QObject.with(Unit, Qt.QObject.new(), object => watch(probe, object))
    Qt.QObject.with(Unit, Qt.QObject.new(), parent => watch_parent(probe, parent))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QObject.with(Unit, Qt.QObject.new(), probe => cases(probe))
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Destruction test leaked resources")
    Qt.Action.lift(Unit, IO.print("QT612_DESTRUCTION_OK"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
