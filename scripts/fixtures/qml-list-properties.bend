import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expected(-A: Type, result: Result<&1, &1, U32 & String, A>, code: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(+actual, text)}: require(U32.is_eq(actual, code), "List error " ++ U32.show(actual) ++ ": " ++ text)
    case Done{value}: Qt.Action.fail(Unit, 1, "Invalid QML list operation succeeded")

def name_is(name: Maybe<&2, String>, expected: String) -> Qt.Action(Unit):
  match name:
    case Some{name}: require(String.eq(name, expected), "Native list element metadata was erased")
    case None{}: Qt.Action.fail(Unit, 1, "Native list element has no metadata name")

def buttons() -> Qt.Property:
  Qt.Property.qmlList("buttons", Qt.QPushButton.arg())

def items() -> Qt.Property:
  Qt.Property.qmlList("items", Qt.ObjectType.reference("AuthoredListItem"))

def nodes() -> Qt.Property:
  Qt.Property.qmlList("nodes", Qt.ObjectType.reference("AuthoredListNode"))

def title() -> Qt.Property:
  Qt.Property.define("title", Qt.string())

def list_signal() -> Qt.Signal:
  Qt.Signal.define("listReady", [Qt.qmlList(Qt.QPushButton.arg())])

def Item() -> Qt.ObjectType:
  Qt.QObject.define("AuthoredListItem", [title()])

def Node() -> Qt.ObjectType:
  Qt.ObjectType.withDefaultProperty(Qt.QObject.define("AuthoredListNode", [items(), nodes(), buttons()]), "items")

def equal_count(+count: Qt.Int64, expected: U32) -> Qt.Action(Unit):
  require(U32.is_eq(Qt.Int64.lo(count), expected) && U32.is_eq(Qt.Int64.hi(count), 0), "Authored list count changed")

def append_storage(+self: Qt.QObject, button: Qt.QPushButton) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.ListProperty.appendStorage(~buttons(), self, button)
    Qt.QObject.setObjectName(self, "append callback")

def append(self: Qt.QObject, button: Qt.QPushButton) -> Qt.Action(Unit):
  append_storage(self, button)

def count(self: Qt.QObject) -> Qt.Action(Qt.Int64):
  Qt.ListProperty.countStorage(~buttons(), self)

def rejected_append(self: Qt.QObject, button: Qt.QPushButton) -> Qt.Action(Unit):
  Qt.Action.fail(Unit, 73, "list append failed")

def button_name(button: Qt.QPushButton, expected: String) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    name: String <- Qt.QObject.objectName(Qt.QPushButton.as_QObject(button))
    require(String.eq(name, expected), "Typed QML list element identity changed")

def copied_getter(self: Qt.QObject) -> Qt.Action(Qt.Property.Value(buttons())):
  Qt.Property.get(~buttons(), self)

def delivered(probe: Qt.QObject, view: Qt.QmlListView<"QPushButton*">) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +reference: Qt.QQmlListReference <- Qt.QmlListView.reference(~Qt.QPushButton.arg(), view)
    count: Qt.Int64 <- Qt.QQmlListReference.count(reference)
    equal_count(count, 1)
    Qt.QObject.setObjectName(probe, "queued list")

def queued_view() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +source: Qt.ObjectType.Instance(Node()) <- Qt.ObjectType.new(~Node())
    +owner: Qt.QObject = Qt.ObjectType.as_QObject(~Node(), source)
    +button: Qt.QPushButton <- Qt.QPushButton.new()
    Qt.ListProperty.append(~buttons(), owner, button)
    +emitter: Qt.QObject <- Qt.QObject.newWithSignals("AuthoredListEmitter", [list_signal()])
    +probe: Qt.QObject <- Qt.QObject.new()
    connection: Qt.Connection <- Qt.Signal.connectWith(~list_signal(), ~Qt.QObject, ~delivered,
      emitter, Qt.Qt.ConnectionType.QueuedConnection(), probe)
    +view: Qt.Property.Value(buttons()) <- Qt.Property.get(~buttons(), owner)
    Qt.Signal.emit(~list_signal(), emitter, view)
    Qt.QmlListView.release("QPushButton*", view)
    Qt.QObject.release(owner)
    Qt.QCoreApplication.processEvents()
    name: String <- Qt.QObject.objectName(probe)
    require(String.eq(name, "queued list"), "Queued list view lost its released source owner")

def worker_view() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +source: Qt.ObjectType.Instance(Node()) <- Qt.ObjectType.new(~Node())
    +owner: Qt.QObject = Qt.ObjectType.as_QObject(~Node(), source)
    +button: Qt.QPushButton <- Qt.QPushButton.new()
    Qt.ListProperty.append(~buttons(), owner, button)
    Qt.ListProperty.handleCount(~buttons(), ~Qt.QObject, ~count, owner, owner)
    +emitter: Qt.QObject <- Qt.QObject.newWithSignals("AuthoredListEmitter", [list_signal()])
    +probe: Qt.QObject <- Qt.QObject.new()
    connection: Qt.Connection <- Qt.Signal.connect(~list_signal(), ~Qt.QObject, ~delivered, emitter, probe)
    +view: Qt.Property.Value(buttons()) <- Qt.Property.get(~buttons(), owner)
    +boxed: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.qmlList(Qt.QPushButton.arg()), view)
    ok: Bool <- Qt.CallbackProbe.qmlListCallbacksFromWorker(boxed)
    require(ok, "Native worker list callbacks did not reach Bend")
    Qt.CallbackProbe.qmlListSignalFromWorker(emitter, boxed)
    Qt.QmlListView.release("QPushButton*", view)
    Qt.QVariant.release(boxed)
    Qt.QObject.release(owner)
    Qt.QCoreApplication.processEvents()
    name: String <- Qt.QObject.objectName(probe)
    require(String.eq(name, "queued list"), "Worker list signal lost its released owner")

def basic() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +item: Qt.ObjectType.Instance(Item()) <- Qt.ObjectType.new(~Item())
    Qt.ObjectType.set(~Item(), ~title(), item, "first")
    +node: Qt.ObjectType.Instance(Node()) <- Qt.ObjectType.new(~Node())
    +self: Qt.QObject = Qt.ObjectType.as_QObject(~Node(), node)
    Qt.ListProperty.append(~items(), self, item)
    +returned: Qt.ObjectType.Instance(Item()) <- Qt.ListProperty.at(~items(), self, Qt.Int64{0, 0})
    title: String <- Qt.ObjectType.get(~Item(), ~title(), returned)
    require(String.eq(title, "first"), "Runtime element class lost its type")
    Qt.ListProperty.append(~nodes(), self, node)
    returned: Qt.ObjectType.Instance(Node()) <- Qt.ListProperty.at(~nodes(), self, Qt.Int64{0, 0})
    require(U32.is_eq(Qt.ObjectType.word(~Node(), returned), Qt.ObjectType.word(~Node(), node)), "List self-reference changed identity")
    Qt.ListProperty.clear(~nodes(), self)
    +first: Qt.QPushButton <- Qt.QPushButton.new()
    Qt.QObject.setObjectName(Qt.QPushButton.as_QObject(first), "first")
    +second: Qt.QPushButton <- Qt.QPushButton.new()
    Qt.QObject.setObjectName(Qt.QPushButton.as_QObject(second), "second")
    Qt.ListProperty.handleAppend(~buttons(), ~Qt.QObject, ~append, self, self)
    Qt.ListProperty.handleCount(~buttons(), ~Qt.QObject, ~count, self, self)
    Qt.ListProperty.append(~buttons(), self, first)
    Qt.QPushButton.release(first)
    kept: Qt.QPushButton <- Qt.ListProperty.at(~buttons(), self, Qt.Int64{0, 0})
    button_name(kept, "first")
    count: Qt.Int64 <- Qt.ListProperty.count(~buttons(), self)
    equal_count(count, 1)
    name: String <- Qt.QObject.objectName(self)
    require(String.eq(name, "append callback"), "List append callback did not run")
    Qt.ListProperty.replace(~buttons(), self, Qt.Int64{0, 0}, second)
    button: Qt.QPushButton <- Qt.ListProperty.at(~buttons(), self, Qt.Int64{0, 0})
    button_name(button, "second")
    +view: Qt.Property.Value(buttons()) <- Qt.Property.get(~buttons(), self)
    +reference: Qt.QQmlListReference <- Qt.QmlListView.reference(~Qt.QPushButton.arg(), view)
    valid: Bool <- Qt.QQmlListReference.isValid(reference)
    require(valid, "Authored native QQmlListReference is invalid")
    element: Qt.QMetaObject <- Qt.QQmlListReference.listElementType(reference)
    name: Maybe<&2, String> <- Qt.QMetaObject.className(element)
    name_is(name, "QPushButton")
    Qt.ListProperty.handleAppend(~buttons(), ~Qt.QObject, ~rejected_append, self, self)
    rejected: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.ListProperty.append(~buttons(), self, second))
    expected(Unit, rejected, 73)
    count: Qt.Int64 <- Qt.ListProperty.count(~buttons(), self)
    equal_count(count, 1)
    Qt.ListProperty.removeLast(~buttons(), self)
    count: Qt.Int64 <- Qt.ListProperty.count(~buttons(), self)
    equal_count(count, 0)
    invalid: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.ListProperty.removeLast(~buttons(), self))
    expected(Unit, invalid, 34)
    invalid: Result<&1, &1, U32 & String, Qt.QPushButton> <- Qt.Action.attempt(Qt.QPushButton, Qt.ListProperty.at(~buttons(), self, Qt.Int64{0, 0}))
    expected(Qt.QPushButton, invalid, 34)

def copied_views() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +source: Qt.ObjectType.Instance(Node()) <- Qt.ObjectType.new(~Node())
    +source_object: Qt.QObject = Qt.ObjectType.as_QObject(~Node(), source)
    +target: Qt.ObjectType.Instance(Node()) <- Qt.ObjectType.new(~Node())
    +target_object: Qt.QObject = Qt.ObjectType.as_QObject(~Node(), target)
    +button: Qt.QPushButton <- Qt.QPushButton.new()
    Qt.QObject.setObjectName(Qt.QPushButton.as_QObject(button), "kept")
    Qt.ListProperty.append(~buttons(), source_object, button)
    +view: Qt.Property.Value(buttons()) <- Qt.Property.get(~buttons(), source_object)
    +box: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.qmlList(Qt.QPushButton.arg()), view)
    +copy: Qt.QVariant <- Qt.QVariant.copy(box)
    +copied: Qt.Property.Value(buttons()) <- Qt.QVariant.toValue(~Qt.qmlList(Qt.QPushButton.arg()), copy)
    Qt.Property.writeStorage(~buttons(), target_object, copied)
    Qt.QmlListView.release("QPushButton*", copied)
    Qt.QVariant.release(box)
    Qt.QVariant.release(copy)
    Qt.QmlListView.release("QPushButton*", view)
    Qt.QObject.release(source_object)
    count: Qt.Int64 <- Qt.ListProperty.count(~buttons(), target_object)
    equal_count(count, 1)
    element: Qt.QPushButton <- Qt.ListProperty.at(~buttons(), target_object, Qt.Int64{0, 0})
    button_name(element, "kept")
    +other: Qt.ObjectType.Instance(Node()) <- Qt.ObjectType.new(~Node())
    Qt.Property.handleGetter(~buttons(), ~Qt.QObject, ~copied_getter, Qt.ObjectType.as_QObject(~Node(), other), target_object)
    count: Qt.Int64 <- Qt.ListProperty.count(~buttons(), Qt.ObjectType.as_QObject(~Node(), other))
    equal_count(count, 1)
    Qt.ListProperty.clear(~buttons(), target_object)

def component(engine: Qt.QQmlEngine, text: String) -> Qt.Action(Qt.QQmlComponent):
  do Qt.Action<Qt.QQmlComponent>:
    +component: Qt.QQmlComponent <- Qt.QQmlComponent.new__QQmlEngine_QObject(engine, Qt.QObject{0})
    bytes: Qt.QByteArray <- Qt.QByteArray.fromUtf8(text)
    url: Qt.QUrl <- Qt.QUrl.new()
    Qt.QQmlComponent.setData(component, bytes, url)
    ready: Bool <- Qt.QQmlComponent.isReady(component)
    require(ready, "QML authored list document did not compile")
    return component

def qml() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    item_registration: Qt.Qml.Registration(Item()) <- Qt.Qml.registerType(~Item(), "Bend.AuthoredLists", 1, 0, "Item")
    node_registration: Qt.Qml.Registration(Node()) <- Qt.Qml.registerType(~Node(), "Bend.AuthoredLists", 1, 0, "Node")
    +engine: Qt.QQmlEngine <- Qt.QQmlEngine.new()
    +component: Qt.QQmlComponent <- component(engine, "import QtQml\nimport Bend.AuthoredLists 1.0\nNode { Item { title: 'first' } Item { title: 'second' } property string summary: items.length + ':' + items[0].title; Component.onCompleted: { items[0] = items[1]; items.pop(); } }")
    +root: Qt.QObject <- Qt.QQmlComponent.create__QQmlContext(component, Qt.QQmlContext{0})
    require(U32.is_ne(Qt.QObject.word(root), 0), "QML authored list construction failed")
    count: Qt.Int64 <- Qt.ListProperty.count(~items(), root)
    equal_count(count, 1)
    item: Qt.ObjectType.Instance(Item()) <- Qt.ListProperty.at(~items(), root, Qt.Int64{0, 0})
    text: String <- Qt.ObjectType.get(~Item(), ~title(), item)
    require(String.eq(text, "second"), "QML default list replace/remove failed")
    +reference: Qt.QQmlListReference <- Qt.QQmlListReference.new__QObject_String(root, "items")
    element: Qt.QMetaObject <- Qt.QQmlListReference.listElementType(reference)
    name: Maybe<&2, String> <- Qt.QMetaObject.className(element)
    name_is(name, "AuthoredListItem")
    Qt.ListProperty.clear(~items(), root)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, basic())
    Qt.scoped(Unit, copied_views())
    Qt.scoped(Unit, queued_view())
    Qt.scoped(Unit, worker_view())
    Qt.scoped(Unit, qml())
    live: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(live, 0) && U32.is_eq(connections, 0), "Authored QML lists leaked resources")
    Qt.Action.lift(Unit, IO.print("QT612_QML_LIST_PROPERTIES_OK native=1 runtime=1 callbacks=1 worker=1 views=1 queued=1 qml=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
