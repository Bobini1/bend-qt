import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def contains(+name: String, names: List<&2, String>) -> Bool:
  match names:
    case Nil{}: False{}
    case head <> tail: String.eq(name, head) || contains(name, tail)

def names(reply: Qt.DBusReply_List_String) -> Qt.Action(Unit):
  match reply:
    case Qt.DBusReply_List_String{Some{values}, failure}: require(contains("org.freedesktop.DBus", values), "DBus service list lost its typed values")
    case Qt.DBusReply_List_String{None{}, failure}: Qt.Action.fail(Unit, 1, "DBus service list failed")

def rejected(result: Result<&1, &1, U32 & String, Unit>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 18), "Wrong DBus affinity error")
    case Done{value}: Qt.Action.fail(Unit, 1, "Foreign DBus QObject method bypassed affinity")

def copied_connection(value: Qt.QDBusConnection) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    connected: Bool <- Qt.QDBusConnection.isConnected(value)
    require(connected, "Copied DBus lease connection was disconnected")

def credentials(reply: Qt.DBusReply_List_Pair_String_QVariant) -> Qt.Action(Unit):
  require(Qt.DBusReply_List_Pair_String_QVariant.isValid(reply), "Typed DBus credentials map failed")

def interface(+value: Qt.QDBusConnectionInterface) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    # Removing the named connection prevents new name lookups. The interface
    # lease owns a native connection copy until this scope finishes.
    Qt.QDBusConnection.disconnectFromBus("bend-qt-replies")
    denied: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QDBusConnectionInterface.setObjectName(value, "foreign"))
    rejected(denied)
    Qt.QDBusConnection.with(Unit, Qt.QDBusConnectionInterface.connection(value), copy => copied_connection(copy))
    reply: Qt.DBusReply_List_String <- Qt.QDBusConnectionInterface.registeredServiceNames(value)
    names(reply)
    registered: Qt.DBusReply_Bool <- Qt.QDBusConnectionInterface.isServiceRegistered(value, "org.freedesktop.DBus")
    require(Qt.DBusReply_Bool.isValid(registered), "Typed bool reply failed")
    uid: Qt.DBusReply_U32 <- Qt.QDBusConnectionInterface.serviceUid(value, "org.freedesktop.DBus")
    require(Qt.DBusReply_U32.isValid(uid), "Typed unsigned reply failed")
    Qt.Convert_DBusReply_List_Pair_String_QVariant.with(Unit, Qt.QDBusConnectionInterface.serviceCredentials(value, "org.freedesktop.DBus"), credentials)
    owner: Qt.DBusReply_String <- Qt.QDBusConnectionInterface.serviceOwner(value, "org.freedesktop.DBus")
    require(Qt.DBusReply_String.isValid(owner), "Typed string reply failed")
    +missing: Qt.DBusReply_String <- Qt.QDBusConnectionInterface.serviceOwner(value, "org.bendqt.NoSuchService")
    require(Bool.not(Qt.DBusReply_String.isValid(missing)), "DBus error became a successful value")
    +failure: Qt.DBusError = Qt.DBusReply_String.error(missing)
    require(U32.is_ne(Qt.DBusError.code(failure), 0), "DBus error code was lost")
    require(String.eq(Qt.DBusError.name(failure), "org.freedesktop.DBus.Error.NameHasNoOwner"), "DBus error name was lost")
    empty: Qt.DBusReply_Unit <- Qt.QDBusConnectionInterface.startService(value, "org.bendqt.NoSuchService")
    require(Bool.not(Qt.DBusReply_Unit.isValid(empty)), "Void DBus failure became success")

def connection(+value: Qt.QDBusConnection) -> Qt.Action(Qt.QDBusConnectionInterface):
  do Qt.Action<Qt.QDBusConnectionInterface>:
    connected: Bool <- Qt.QDBusConnection.isConnected(value)
    require(connected, "No test session bus")
    bus: Qt.QDBusConnectionInterface <- Qt.QDBusConnection.interface(value)
    return bus

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QDBusConnectionInterface.with(Unit,
      Qt.QDBusConnection.with(Qt.QDBusConnectionInterface, Qt.QDBusConnection.connectToBus__QDBusConnection_BusType_String(Qt.QDBusConnection.BusType.SessionBus(), "bend-qt-replies"), value => connection(value)), value => interface(value))
    pins: U32 <- Qt.Runtime.liveRetentions()
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(pins, 0) && U32.is_eq(objects, 0), "DBus reply scopes leaked leases")
    Qt.Action.lift(Unit, IO.print("QT612_DBUS_OK list=1 bool=1 unsigned=1 string=1 structured_error=1 void_error=1 connection_copy=1 disconnect=1 affinity=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
