import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def stored() -> Qt.Property:
  Qt.Property.define("stored", Qt.int32())

def computed() -> Qt.Property:
  Qt.Property.readOnly("computed", Qt.int32())

def written() -> Qt.Property:
  Qt.Property.define("written", Qt.int32())

def storedChanged() -> Qt.Signal:
  Qt.Signal.define("storedChanged", [])

def increment() -> Qt.Method:
  Qt.Method.define("increment", [Qt.int32()], Qt.int32())

def failWork() -> Qt.Method:
  Qt.Method.define("failWork", [], Qt.unit())

def WorkerObject() -> Qt.QtObject:
  Qt.QtObject.withMethods(Qt.QObject.define("BendWorkerMembers", [stored(), computed(), written()]), [increment(), failWork()])

def on_main() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    main: Bool <- Qt.CallbackProbe.memberOnMain()
    require(main, "A QObject member handler ran outside main")

def getter(state: Unit) -> Qt.Action(Qt.Int32):
  do Qt.Action<Qt.Int32>:
    on_main()
    return Qt.Int32{43}

def setter(probe: Qt.QObject, value: Qt.Int32) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    on_main()
    Qt.QObject.setObjectName(probe, U32.show(Qt.Int32.word(value)))

def add_one(state: Unit, value: Qt.Int32) -> Qt.Action(Qt.Int32):
  do Qt.Action<Qt.Int32>:
    on_main()
    return Qt.Int32{U32.add(Qt.Int32.word(value), 1)}

def reject(state: Unit) -> Qt.Action(Unit):
  Qt.Action.fail(Unit, 73, "Expected worker member failure")

def notified(probe: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    on_main()
    Qt.QObject.setObjectName(probe, "notified")

def expected(result: Result<&1, &1, U32 & String, Bool>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 73), "The worker member lost its original error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "The worker member failure was ignored")

def objects() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +value: Qt.QtObject.Instance(WorkerObject()) <- Qt.QtObject.new(~WorkerObject())
    +self: Qt.QObject = Qt.QtObject.as_QObject(~WorkerObject(), value)
    +setter_probe: Qt.QObject <- Qt.QObject.new__QObject(Qt.QObject{0})
    +notify_probe: Qt.QObject <- Qt.QObject.new__QObject(Qt.QObject{0})
    Qt.Property.set(~stored(), self, Qt.Int32{5})
    Qt.Property.handleGetter(~computed(), ~Unit, ~getter, self, Unit{})
    Qt.Property.handleSetter(~written(), ~Qt.QObject, ~setter, self, setter_probe)
    Qt.Method.handle(~increment(), ~Unit, ~add_one, self, Unit{})
    Qt.Method.handle(~failWork(), ~Unit, ~reject, self, Unit{})
    connection: Qt.Connection <- Qt.Signal.connect(~storedChanged(), ~Qt.QObject, ~notified, self, notify_probe)
    good: Bool <- Qt.CallbackProbe.membersFromWorker(self, False{})
    require(good, "Worker QObject members returned incorrect values")
    result: Qt.Int32 <- Qt.Property.get(~stored(), self)
    require(U32.is_eq(Qt.Int32.word(result), 41), "A worker write did not persist")
    setter_text: String <- Qt.QObject.objectName(setter_probe)
    require(String.eq(setter_text, "9"), "The worker setter handler did not finish synchronously")
    notify_text: String <- Qt.QObject.objectName(notify_probe)
    require(String.eq(notify_text, "notified"), "The worker write did not notify")
    failure: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.CallbackProbe.membersFromWorker(self, True{}))
    expected(failure)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, objects())
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Worker QObject members leaked")
    Qt.Action.lift(Unit, IO.print("QT612_QT_OBJECT_WORKER_OK storage=1 getters=1 setters=1 methods=1 notify=1 metadata=1 main_thread=1 failure=73 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
