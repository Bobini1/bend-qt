import Base
import ../../packages/qt612/qt.bend as Qt

# Plain list properties work in QML as C++ QList properties do: as arrays and
# as view models, refreshed when Bend sets a new list. That includes lists of
# Bend-declared objects, lists of Bend-declared values that were never
# registered with QML, and nested lists.

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expected(-A: Type, result: Result<&1, &1, U32 & String, A>, code: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(+actual, message)}: require(U32.is_eq(actual, code), "Wrong list error " ++ U32.show(actual) ++ ": " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "An invalid list operation succeeded")

def title() -> Qt.Property:
  Qt.Property.define("title", Qt.string())

def Card() -> Qt.ObjectType:
  Qt.QObject.define("ListModelCard", [title()])

def tick() -> Qt.Property:
  Qt.Property.define("tick", Qt.int32())

def label() -> Qt.Property:
  Qt.Property.define("label", Qt.string())

# Never registered with QML, like a plain Q_GADGET.
def Change() -> Qt.ValueType:
  Qt.ValueType.define("ListModelChange", [tick(), label()])

def numbers() -> Qt.Property:
  Qt.Property.define("numbers", Qt.list(~Qt.int32()))

def wides() -> Qt.Property:
  Qt.Property.define("wides", Qt.list(~Qt.int64()))

def names() -> Qt.Property:
  Qt.Property.define("names", Qt.list(~Qt.string()))

def cards() -> Qt.Property:
  Qt.Property.define("cards", Qt.list(~Qt.ObjectType.arg(~Card())))

def changes() -> Qt.Property:
  Qt.Property.define("changes", Qt.list(~Qt.value(~Change())))

def rows() -> Qt.Property:
  Qt.Property.define("rows", Qt.list(~Qt.list(~Qt.int32())))

def lanes() -> Qt.Property:
  Qt.Property.define("lanes", Qt.list(~Qt.list(~Qt.value(~Change()))))

def Backend() -> Qt.ObjectType:
  Qt.QObject.define("ListModelBackend", [numbers(), wides(), names(), cards(), changes(), rows(), lanes()])

def qml() -> String:
  "import QtQuick\n" ++
  "Item {\n" ++
  "  property int step: 0\n" ++
  "  onStepChanged: { backend.cards = [backend.cards[1]]; backend.numbers = [7, 8] }\n" ++
  "  Repeater { id: numberView; model: backend.numbers; Item { required property int modelData } }\n" ++
  "  ListView { id: nameView; model: backend.names; delegate: Item { required property string modelData } }\n" ++
  "  Repeater { id: cardView; model: backend.cards; Item { required property var modelData; property string text: modelData.title } }\n" ++
  "  Repeater { id: changeView; model: backend.changes; Item { required property var modelData; property string text: modelData.label + '=' + modelData.tick } }\n" ++
  "  Repeater { id: laneView; model: backend.lanes; Item { required property var modelData; property string text: String(modelData.length) } }\n" ++
  "  function texts(view) { var r = []; for (var i = 0; i < view.count; i++) r.push(view.itemAt(i).text); return r.join(',') }\n" ++
  "  property string summary: [numberView.count, backend.numbers.reduce(function(a, b) { return a + b }, 0), String(backend.wides[0]),\n" ++
  "    nameView.count, backend.names.join('+'), cardView.count, texts(cardView), changeView.count, texts(changeView),\n" ++
  "    JSON.stringify(backend.rows), laneView.count, texts(laneView),\n" ++
  "    backend.lanes.length > 1 ? backend.lanes[1].map(function(c) { return c.label }).join('+') : ''].join(' ')\n" ++
  "}\n"

def summary(+root: Qt.QObject) -> Qt.Action(String):
  Qt.QVariant.with(String, Qt.QQmlProperty.read__QObject_String(root, "summary"), Qt.QVariant.toString)

def card(text: String) -> Qt.Action(Qt.ObjectType.Instance(Card())):
  do Qt.Action<Qt.ObjectType.Instance(Card())>:
    +made: Qt.ObjectType.Instance(Card()) <- Qt.ObjectType.new(~Card())
    Qt.Property.set(~title(), Qt.ObjectType.as_QObject(~Card(), made), text)
    return made

def change(number: U32, text: String) -> Qt.Action(Qt.ValueType.Instance(Change())):
  Qt.ValueType.make(~Change(), Qt.Int32{number}, text)

def initial(+object: Qt.QObject, +first: Qt.ObjectType.Instance(Card()), +second: Qt.ObjectType.Instance(Card())) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +one: Qt.ValueType.Instance(Change()) <- change(1, "one")
    +two: Qt.ValueType.Instance(Change()) <- change(2, "two")
    +three: Qt.ValueType.Instance(Change()) <- change(3, "three")
    Qt.Property.set(~numbers(), object, [Qt.Int32{1}, Qt.Int32{2}])
    Qt.Property.set(~wides(), object, [Qt.Int64{5, 1}])
    Qt.Property.set(~names(), object, ["a", "b"])
    Qt.Property.set(~cards(), object, [first, second])
    Qt.Property.set(~changes(), object, [one, two])
    Qt.Property.set(~rows(), object, [[Qt.Int32{1}], [Qt.Int32{2}, Qt.Int32{3}]])
    Qt.Property.set(~lanes(), object, [[one], [two, three]])

def updated(+object: Qt.QObject, +second: Qt.ObjectType.Instance(Card())) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +three: Qt.ValueType.Instance(Change()) <- change(3, "three")
    Qt.Property.set(~numbers(), object, [Qt.Int32{4}, Qt.Int32{5}, Qt.Int32{6}])
    Qt.Property.set(~names(), object, ["c"])
    Qt.Property.set(~cards(), object, [second])
    Qt.Property.set(~changes(), object, [three])
    Qt.Property.set(~rows(), object, [[Qt.Int32{9}]])
    Qt.Property.set(~lanes(), object, [[three]])

def card_titles(cards: List<&2, Qt.ObjectType.Instance(Card())>) -> Qt.Action(String):
  match cards:
    case Nil{}: Qt.Action.pure(String, "")
    case head <> tail:
      do Qt.Action<String>:
        text: String <- Qt.Property.get(~title(), Qt.ObjectType.as_QObject(~Card(), head))
        rest: String <- card_titles(tail)
        return text ++ rest

def number_total(values: List<&2, Qt.Int32>) -> U32:
  match values:
    case Nil{}: 0
    case head <> tail: U32.add(Qt.Int32.word(head), number_total(tail))

def named(value: Maybe<&2, String>, expected: String) -> Bool:
  match value:
    case Some{name}: String.eq(name, expected)
    case None{}: False{}

def qml_writes(+object: Qt.QObject, +root: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +step: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.int32(), Qt.Int32{1})
    written: Bool <- Qt.QQmlProperty.write__QObject_String_QVariant(root, "step", step)
    require(written, "QML did not accept the step property")
    held: List<&2, Qt.ObjectType.Instance(Card())> <- Qt.Property.get(~cards(), object)
    +titles: String <- card_titles(held)
    require(String.eq(titles, "second"), "QML did not write a typed object list: " ++ titles)
    values: List<&2, Qt.Int32> <- Qt.Property.get(~numbers(), object)
    require(U32.is_eq(number_total(values), 15), "QML did not write an int list")

def views(+object: Qt.QObject, +first: Qt.ObjectType.Instance(Card()), +second: Qt.ObjectType.Instance(Card())) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +engine: Qt.QQmlEngine <- Qt.QQmlEngine.new()
    +context: Qt.QQmlContext <- Qt.QQmlEngine.rootContext(engine)
    Qt.QQmlContext.setContextProperty__String_QObject(context, "backend", object)
    +component: Qt.QQmlComponent <- Qt.QQmlComponent.new__QQmlEngine_QObject(engine, Qt.QObject{0})
    source: Qt.QByteArray <- Qt.QByteArray.fromUtf8(qml())
    url: Qt.QUrl <- Qt.QUrl.new()
    Qt.QQmlComponent.setData(component, source, url)
    errors: String <- Qt.QQmlComponent.errorString(component)
    ready: Bool <- Qt.QQmlComponent.isReady(component)
    require(ready, "List model QML did not compile: " ++ errors)
    +root: Qt.QObject <- Qt.QQmlComponent.create__QQmlContext(component, Qt.QQmlContext{0})
    +before: String <- summary(root)
    require(String.eq(before, "2 3 4294967301 2 a+b 2 first,second 2 one=1,two=2 [[1],[2,3]] 2 1,2 two+three"),
      "QML did not read the lists: " ++ before)
    updated(object, second)
    +after: String <- summary(root)
    require(String.eq(after, "3 15 4294967301 1 c 1 second 1 three=3 [[9]] 1 1 "),
      "QML views did not follow the new lists: " ++ after)
    Qt.Property.set(~cards(), object, [first, second])
    qml_writes(object, root)
    Qt.QObject.destroy(root)

# A destroyed object inside a stored list makes the list stale, as a destroyed
# object inside any stored container does.
def stale(+object: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +gone: Qt.ObjectType.Instance(Card()) <- card("gone")
    Qt.Property.set(~cards(), object, [gone])
    Qt.QObject.destroy(Qt.ObjectType.as_QObject(~Card(), gone))
    read: Result<&1, &1, U32 & String, List<&2, Qt.ObjectType.Instance(Card())>> <-
      Qt.Action.attempt(List<&2, Qt.ObjectType.Instance(Card())>, Qt.Property.get(~cards(), object))
    expected(List<&2, Qt.ObjectType.Instance(Card())>, read, 116)
    Qt.Property.set(~cards(), object, [])

def variants(+first: Qt.ObjectType.Instance(Card())) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +boxed: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.list(~Qt.ObjectType.arg(~Card())), [first])
    meta: Qt.QMetaType <- Qt.QVariant.metaType(boxed)
    name: Maybe<&2, String> <- Qt.QMetaType.name(meta)
    require(named(name, "QList<ListModelCard*>"), "A typed object list has the wrong metatype")
    copied: List<&2, Qt.ObjectType.Instance(Card())> <- Qt.QVariant.toValue(~Qt.list(~Qt.ObjectType.arg(~Card())), boxed)
    titles: String <- card_titles(copied)
    require(String.eq(titles, "first"), "A typed object list did not round-trip through QVariant")

# List operations must leave the application in place. Qt aborts a QML engine
# constructed without one, so each step is checked before the engine.
def alive(step: String) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    exists: Bool <- Qt.QCoreApplication.instanceExists()
    require(exists, "The Qt application no longer exists " ++ step)

def run(+backend: Qt.ObjectType.Instance(Backend())) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +object: Qt.QObject = Qt.ObjectType.as_QObject(~Backend(), backend)
    alive("after creating the backend")
    +first: Qt.ObjectType.Instance(Card()) <- card("first")
    +second: Qt.ObjectType.Instance(Card()) <- card("second")
    alive("after creating the cards")
    initial(object, first, second)
    alive("after setting the lists")
    views(object, first, second)
    variants(first)
    stale(object)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    alive("before the list model checks")
    Qt.scoped(Unit, Qt.ObjectType.with(~Backend(), Unit, Qt.ObjectType.new(~Backend()), backend => run(backend)))
    live: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(live, 0), "List models leaked native handles")
    Qt.Action.lift(Unit, IO.print("QT612_LIST_MODELS_OK arrays=1 views=1 updates=1 typed_objects=1 unregistered_values=1 nested=1 qml_writes=1 stale=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
