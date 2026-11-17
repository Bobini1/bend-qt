import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expect_error(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong object-signal error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected an object-signal failure")

def empty() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    retentions: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0) && U32.is_eq(retentions, 0), "Object-signal test leaked resources")

def recorded(+probe: Qt.QObject, expected: String, message: String) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    seen: String <- Qt.QObject.objectName(probe)
    require(String.eq(seen, expected), message)

def named_action(group: Qt.QActionGroup, +action: Qt.QAction) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QAction.setObjectName(action, "Borrowed action🎵")
    Qt.QAction.setActionGroup(action, group)

def describe_action(+action: Qt.QAction) -> Qt.Action(String):
  do Qt.Action<String>:
    name: String <- Qt.QAction.objectName(action)
    return U32.show(Qt.QAction.word(action)) ++ "|" ++ name

# The handler gets the triggered action as a borrowed handle and records its
# identity and name in the probe.
def triggered(probe: Qt.QObject, action: Qt.QAction) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    text: String <- describe_action(action)
    Qt.QObject.setObjectName(probe, text)

def live_event(group: Qt.QActionGroup, +probe: Qt.QObject, +action: Qt.QAction) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    named_action(group, action)
    Qt.QAction.trigger(action)
    recorded(probe, U32.show(Qt.QAction.word(action)) ++ "|Borrowed action🎵", "Signal changed the borrowed action identity")

def expire_action(+group: Qt.QActionGroup, +action: Qt.QAction) -> Qt.Action(U32):
  do Qt.Action<U32>:
    named_action(group, action)
    Qt.QAction.trigger(action)
    Qt.QActionGroup.removeAction(group, action)
    return Qt.QAction.word(action)

# A destroyed action's slot is reused with a new generation; the handler sees
# the new handle.
def reused_action(group: Qt.QActionGroup, +probe: Qt.QObject, +old: U32, +action: Qt.QAction) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +current: U32 = Qt.QAction.word(action)
    require(U32.is_eq(U32.and(old, 65535), U32.and(current, 65535)) && U32.is_ne(old, current), "Fixture did not reuse the slot with a new generation")
    named_action(group, action)
    Qt.QAction.trigger(action)
    recorded(probe, U32.show(current) ++ "|Borrowed action🎵", "Handler received a stale action handle")
    stale: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QAction.objectName(Qt.QAction{old}))
    expect_error(String, stale, 116)

def watching(+group: Qt.QActionGroup, +probe: Qt.QObject, connection: Qt.Connection) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QAction.with(Unit, Qt.QAction.new(), action => live_event(group, probe, action))
    old: U32 <- Qt.QAction.with(U32, Qt.QAction.new(), action => expire_action(group, action))
    Qt.QAction.with(Unit, Qt.QAction.new(), action => reused_action(group, probe, old, action))

def bump(+counter: Qt.QTimer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    count: Qt.Int32 <- Qt.QTimer.interval(counter)
    Qt.QTimer.setInterval__Int32(counter, Qt.Int32{(Qt.Int32.word(count) + 1 : U32)})

def count_trigger(counter: Qt.QTimer, action: Qt.QAction) -> Qt.Action(Unit):
  bump(counter)

def burst(count: Nat, +action: Qt.QAction) -> Qt.Action(Unit):
  match count:
    case Zero{}: Qt.Action.pure(Unit, Unit{})
    case Succ{rest}:
      do Qt.Action<Unit>:
        Qt.QAction.trigger(action)
        burst(rest, action)

def counted(+action: Qt.QAction, +counter: Qt.QTimer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    count: Qt.Int32 <- Qt.QTimer.interval(counter)
    require(U32.is_eq(Qt.Int32.word(count), 65), "A trigger did not run its handler exactly once")

def burst_connected(+action: Qt.QAction, +counter: Qt.QTimer, connection: Qt.Connection) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    burst(65n, action)
    counted(action, counter)
    Qt.Connection.disconnect(connection)
    Qt.QAction.trigger(action)
    counted(action, counter)
    name: String <- Qt.QAction.objectName(action)
    require(String.eq(name, "Borrowed action🎵"), "Handler arguments destroyed their action")

def burst_counter(+group: Qt.QActionGroup, +action: Qt.QAction, +counter: Qt.QTimer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    named_action(group, action)
    Qt.QTimer.setInterval__Int32(counter, Qt.Int32{0})
    Qt.Connection.with(Unit, Qt.QActionGroup.connect_triggered(~Qt.QTimer, ~count_trigger, group, counter),
      connection => burst_connected(action, counter, connection))

def burst_action(+group: Qt.QActionGroup, +action: Qt.QAction) -> Qt.Action(Unit):
  Qt.QTimer.with(Unit, Qt.QTimer.new(), counter => burst_counter(group, action, counter))

# After its scope ends, the connection runs no handler.
def after_scope(+group: Qt.QActionGroup, +probe: Qt.QObject, +action: Qt.QAction) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    named_action(group, action)
    Qt.QObject.setObjectName(probe, "")
    Qt.QAction.trigger(action)
    recorded(probe, "", "A closed connection still ran its handler")

def group_probe(+group: Qt.QActionGroup, +probe: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Connection.with(Unit, Qt.QActionGroup.connect_triggered(~Qt.QObject, ~triggered, group, probe),
      connection => watching(group, probe, connection))
    Qt.QAction.with(Unit, Qt.QAction.new(), action => burst_action(group, action))
    Qt.QAction.with(Unit, Qt.QAction.new(), action => after_scope(group, probe, action))

def action_group_case(+group: Qt.QActionGroup) -> Qt.Action(Unit):
  Qt.QObject.with(Unit, Qt.QObject.new(), probe => group_probe(group, probe))

def good_qml() -> String:
  "import QtQml\nQtObject { objectName: 'Object signal🎵' }"

def load_source(engine: Qt.QQmlApplicationEngine, source: String, path: String) -> Qt.Action(Unit):
  Qt.QByteArray.with(Unit, Qt.QByteArray.fromUtf8(source), data =>
    Qt.QUrl.with(Unit, Qt.QUrl.new__String(path), url => Qt.QQmlApplicationEngine.loadData__QByteArray_QUrl(engine, data, url)))

def object_text(+object: Qt.QObject, null: Bool) -> Qt.Action(String):
  match null:
    case True{}: Qt.Action.pure(String, "0|null")
    case False{}:
      do Qt.Action<String>:
        name: String <- Qt.QObject.objectName(object)
        return U32.show(Qt.QObject.word(object)) ++ "|" ++ name

def describe_object(+object: Qt.QObject) -> Qt.Action(String):
  object_text(object, U32.is_eq(Qt.QObject.word(object), 0))

# objectCreated passes a borrowed object, possibly null, and a QUrl copy owned
# by the call.
def created(probe: Qt.QObject, object: Qt.QObject, url: Qt.QUrl) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    described: String <- describe_object(object)
    text: String <- Qt.QUrl.toString(url)
    Qt.QObject.setObjectName(probe, described ++ "|" ++ text)

def single_root(roots: List<&2, Qt.QObject>) -> Qt.Action(Qt.QObject):
  match roots:
    case object <> Nil{}: Qt.Action.pure(Qt.QObject, object)
    case _: Qt.Action.fail(Qt.QObject, 1, "Expected one QML root")

def created_root(+engine: Qt.QQmlApplicationEngine, +probe: Qt.QObject, path: String) -> Qt.Action(Qt.QObject):
  do Qt.Action<Qt.QObject>:
    roots: List<&2, Qt.QObject> <- Qt.QQmlApplicationEngine.rootObjects(engine)
    +root: Qt.QObject <- single_root(roots)
    recorded(probe, U32.show(Qt.QObject.word(root)) ++ "|Object signal🎵|" ++ path, "Mixed QObject/value arguments changed their fields")
    return root

def same_count(+before: U32, message: String) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    after: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(after, before), message)

def qml_events(+engine: Qt.QQmlApplicationEngine, +probe: Qt.QObject, connection: Qt.Connection) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    load_source(engine, good_qml(), "file:///bend-object-signal.qml")
    root: Qt.QObject <- created_root(engine, probe, "file:///bend-object-signal.qml")
    # The handler's QUrl copy ends with the call; the borrowed root stays.
    +baseline: U32 <- Qt.Runtime.liveObjects()
    name: String <- Qt.QObject.objectName(root)
    require(String.eq(name, "Object signal🎵"), "Argument cleanup destroyed the borrowed object")
    load_source(engine, "import QtQml\nQtObject { notAProperty: true }", "file:///bend-bad-object-signal.qml")
    recorded(probe, "0|null|file:///bend-bad-object-signal.qml", "Null object argument was not preserved")
    same_count(baseline, "Null mixed arguments leaked a value")

def qml_probe(+engine: Qt.QQmlApplicationEngine, +probe: Qt.QObject) -> Qt.Action(Unit):
  Qt.Connection.with(Unit, Qt.QQmlApplicationEngine.connect_objectCreated(~Qt.QObject, ~created, engine, probe),
    connection => qml_events(engine, probe, connection))

def qml_case(+engine: Qt.QQmlApplicationEngine) -> Qt.Action(Unit):
  Qt.QObject.with(Unit, Qt.QObject.new(), probe => qml_probe(engine, probe))

# A borrowed argument follows Qt's lifetime: once a native parent deletes the
# root, the handle the handler saw is stale.
def stale_qml_events(+engine: Qt.QQmlApplicationEngine, +probe: Qt.QObject, connection: Qt.Connection) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    load_source(engine, good_qml(), "file:///bend-expired-object-signal.qml")
    +root: Qt.QObject <- created_root(engine, probe, "file:///bend-expired-object-signal.qml")
    Qt.QObject.with(Unit, Qt.QObject.new(), parent => Qt.QObject.setParent(root, parent))
    stale: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QObject.objectName(root))
    expect_error(String, stale, 116)
    load_source(engine, good_qml(), "file:///bend-object-signal.qml")
    recorded_name: String <- Qt.QObject.objectName(probe)
    require(String.ends_with(recorded_name, "|Object signal🎵|file:///bend-object-signal.qml"), "Handler did not run after a root expired")

def stale_qml_probe(+engine: Qt.QQmlApplicationEngine, +probe: Qt.QObject) -> Qt.Action(Unit):
  Qt.Connection.with(Unit, Qt.QQmlApplicationEngine.connect_objectCreated(~Qt.QObject, ~created, engine, probe),
    connection => stale_qml_events(engine, probe, connection))

def stale_qml_case(+engine: Qt.QQmlApplicationEngine) -> Qt.Action(Unit):
  Qt.QObject.with(Unit, Qt.QObject.new(), probe => stale_qml_probe(engine, probe))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QActionGroup.with(Unit, Qt.QActionGroup.new(Qt.QObject{0}), group => action_group_case(group))
    empty()
    Qt.QQmlApplicationEngine.with(Unit, Qt.QQmlApplicationEngine.new(), engine => qml_case(engine))
    empty()
    Qt.QQmlApplicationEngine.with(Unit, Qt.QQmlApplicationEngine.new(), engine => stale_qml_case(engine))
    empty()
    Qt.Action.lift(Unit, IO.print("QT612_OBJECT_SIGNALS_OK borrowed_identity=1 generation_reuse=1 burst=1 disconnect=1 scope_end=1 mixed_value=1 null=1 argument_cleanup=1 stale_object=1 objects=0 connections=0 retentions=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
