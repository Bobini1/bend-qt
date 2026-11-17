import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expect(-A: Type, code: U32, result: Result<&1, &1, U32 & String, A>) -> Qt.Action(Unit):
  match result:
    case Fail{(actual, message)}: require(U32.is_eq(code, actual), "Wrong list lifetime error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Unsafe QML list access succeeded")

def append_member(+list: Qt.QQmlListReference, +member: Qt.QObject) -> Qt.Action(Qt.QObject):
  do Qt.Action<Qt.QObject>:
    Qt.QObject.setObjectName(member, "retained member")
    added: Bool <- Qt.QQmlListReference.append(list, member)
    require(added, "QML list append failed")
    parent: Qt.QObject <- Qt.QObject.parent(member)
    require(U32.is_eq(Qt.QObject.word(parent), 0), "Fixture list unexpectedly parented its member")
    Qt.Action.pure(Qt.QObject, member)

def append_scoped(+list: Qt.QQmlListReference) -> Qt.Action(Qt.QObject):
  Qt.QObject.with(Qt.QObject, Qt.QObject.new(), member => append_member(list, member))

def replace_member(+list: Qt.QQmlListReference, +member: Qt.QObject) -> Qt.Action(Qt.QObject):
  do Qt.Action<Qt.QObject>:
    changed: Bool <- Qt.QQmlListReference.replace(list, Qt.Int64{0, 0}, member)
    require(changed, "QML list replace failed")
    Qt.Action.pure(Qt.QObject, member)

def mutate(+list: Qt.QQmlListReference, +old: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +replacement: Qt.QObject <- Qt.QObject.with(Qt.QObject, Qt.QObject.new(), member => replace_member(list, member))
    previous: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QObject.objectName(old))
    expect(String, 116, previous)
    current: Qt.QObject <- Qt.QQmlListReference.at(list, Qt.Int64{0, 0})
    require(U32.is_eq(Qt.QObject.word(current), Qt.QObject.word(replacement)), "QML list alias identity changed")
    outside: Result<&1, &1, U32 & String, Qt.QObject> <- Qt.Action.attempt(Qt.QObject, Qt.QQmlListReference.at(list, Qt.Int64{1, 0}))
    expect(Qt.QObject, 34, outside)
    cleared: Bool <- Qt.QQmlListReference.clear(list)
    require(cleared, "QML list clear failed")
    expired: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QObject.objectName(replacement))
    expect(String, 116, expired)

def deleted_owner(+root: Qt.QObject, +list: Qt.QQmlListReference) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +member: Qt.QObject <- append_scoped(list)
    Qt.QObject.destroy(root)
    valid: Bool <- Qt.QQmlListReference.isValid(list)
    require(Bool.not(valid), "QML list reference failed to observe owner destruction")
    expired: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QObject.objectName(member))
    expect(String, 116, expired)

def detach_owner(+root: Qt.QObject, +ancestor: Qt.QObject, +list: Qt.QQmlListReference) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QObject.setParent(root, ancestor)
    appended: Bool <- Qt.QQmlListReference.append(list, ancestor)
    require(appended, "QML list rejected its native ancestor")
    Qt.QObject.setParent(root, Qt.QObject{0})
    blocked: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QObject.destroy(ancestor))
    expect(Unit, 16, blocked)
    cleared: Bool <- Qt.QQmlListReference.clear(list)
    require(cleared, "Clearing former ancestor failed")

def ancestor_list(+root: Qt.QObject, +ancestor: Qt.QObject) -> Qt.Action(Unit):
  Qt.QQmlListReference.with(Unit, Qt.QQmlListReference.new__QObject_String(root, "items"), list => detach_owner(root, ancestor, list))

def root_demo(+root: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +member: Qt.QObject <- Qt.QQmlListReference.with(Qt.QObject, Qt.QQmlListReference.new__QObject_String(root, "items"), list => append_scoped(list))
    name: String <- Qt.QObject.objectName(member)
    require(String.eq(name, "retained member"), "Closing reference scope lost its list member")
    blocked: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QObject.destroy(member))
    expect(Unit, 16, blocked)
    Qt.QQmlListReference.with(Unit, Qt.QQmlListReference.new__QObject_String(root, "items"), list => mutate(list, member))
    Qt.QObject.with(Unit, Qt.QObject.new(), ancestor => ancestor_list(root, ancestor))
    Qt.QQmlListReference.with(Unit, Qt.QQmlListReference.new__QObject_String(root, "items"), list => deleted_owner(root, list))

def load(+component: Qt.QQmlComponent, data: Qt.QByteArray, url: Qt.QUrl) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQmlComponent.setData(component, data, url)
    ready: Bool <- Qt.QQmlComponent.isReady(component)
    require(ready, "List fixture QML failed to load")
    Qt.QObject.with(Unit, Qt.QQmlComponent.create__QQmlContext(component, Qt.QQmlContext{0}), root => root_demo(root))

def component(+value: Qt.QQmlComponent) -> Qt.Action(Unit):
  Qt.QByteArray.with(Unit, Qt.QByteArray.fromUtf8("import QtQml\nQtObject { property list<QtObject> items: [] }"), data =>
    Qt.QUrl.with(Unit, Qt.QUrl.new(), url => load(value, data, url)))

def engine(value: Qt.QQmlEngine) -> Qt.Action(Unit):
  Qt.QQmlComponent.with(Unit, Qt.QQmlComponent.new__QQmlEngine_QObject(value, Qt.QObject{0}), item => component(item))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQmlEngine.with(Unit, Qt.QQmlEngine.new(), engine)
    objects: U32 <- Qt.Runtime.liveObjects()
    pins: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(pins, 0), "QML list leases leaked objects")
    Qt.Action.lift(Unit, IO.print("QT612_QML_LISTS_OK retained=1 reference_scope=1 replace=1 clear=1 bounds=1 owner_deletion=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
