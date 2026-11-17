import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expected(code: U32, result: Result<&1, &1, U32 & String, Unit>) -> Qt.Action(Unit):
  match result:
    case Fail{(actual, message)}: require(U32.is_eq(code, actual), "Wrong incubation error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Unsafe incubation operation succeeded")

def complete(result: Result<&1, &1, U32 & String, Unit>) -> Qt.Action(Unit):
  match result:
    case Done{value}: Qt.Action.pure(Unit, value)
    case Fail{(code, message)}: Qt.Action.fail(Unit, code, message)

def loading_message(ready: Bool) -> String:
  match ready:
    case True{}: "One-millisecond deadline ran the whole incubation"
    case False{}: "Incubation failed with a native QML error"

def objects(depth: Nat) -> String:
  match depth:
    case 0n: "Item { width: { var sum = 0; for (var i = 0; i < 10000; ++i) sum += i; return parent.width + sum; } }\n"
    case 1n+n:
      +half = objects(n)
      half ++ half

def root(value: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    name: String <- Qt.QObject.objectName(value)
    require(String.eq(name, "incubated"), "Asynchronous QML object was not created")

def changed_controller(+engine: Qt.QQmlEngine, +controller: Qt.QQmlIncubationController, +flag: Qt.IncubationFlag) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.IncubationFlag.store(flag, True{})
    waiting: Chan(Result<&1, &1, U32 & String, Unit>) <- Qt.Action.lift(Chan(Result<&1, &1, U32 & String, Unit>), IO.fork(Result<&1, &1, U32 & String, Unit>, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => Qt.QQmlIncubationController.incubateWhile__IncubationFlag(controller, flag)))))
    Qt.Action.lift(Unit, IO.sleep(2))
    Qt.QQmlEngine.setIncubationController(engine, Qt.QQmlIncubationController{0})
    detached: Qt.QQmlEngine <- Qt.QQmlIncubationController.engine(controller)
    require(U32.is_eq(Qt.QQmlEngine.word(detached), 0), "Detached controller returned an engine")
    result: Result<&1, &1, U32 & String, Unit> <- Qt.Action.lift(Result<&1, &1, U32 & String, Unit>, IO.join(Result<&1, &1, U32 & String, Unit>, waiting))
    expected(116, result)
    Qt.QQmlEngine.setIncubationController(engine, controller)

def canceled(+engine: Qt.QQmlEngine, +controller: Qt.QQmlIncubationController, +incubator: Qt.QQmlIncubator, +flag: Qt.IncubationFlag) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    waiting: Chan(Result<&1, &1, U32 & String, Unit>) <- Qt.Action.lift(Chan(Result<&1, &1, U32 & String, Unit>), IO.fork(Result<&1, &1, U32 & String, Unit>, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => Qt.QQmlIncubationController.incubateWhile__IncubationFlag_Int32(controller, flag, Qt.Int32{4294967295})))))
    Qt.Action.lift(Unit, IO.sleep(2))
    busy_engine: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QQmlEngine.destroy(engine))
    expected(16, busy_engine)
    busy_flag: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.IncubationFlag.destroy(flag))
    expected(16, busy_flag)
    Qt.IncubationFlag.store(flag, False{})
    result: Result<&1, &1, U32 & String, Unit> <- Qt.Action.lift(Result<&1, &1, U32 & String, Unit>, IO.join(Result<&1, &1, U32 & String, Unit>, waiting))
    complete(result)
    loading: Bool <- Qt.QQmlIncubator.isLoading(incubator)
    require(loading, "Cancellation did not interrupt pending incubation")
    changed_controller(engine, controller, flag)
    Qt.QQmlIncubationController.incubateWhile__IncubationFlag(controller, flag)
    ready: Bool <- Qt.QQmlIncubator.isReady(incubator)
    require(ready, "Incubation did not resume to Ready")
    Qt.QObject.with(Unit, Qt.QQmlIncubator.object(incubator), root)
    Qt.QQmlEngine.setIncubationController(engine, Qt.QQmlIncubationController{0})

def flag(+engine: Qt.QQmlEngine, +controller: Qt.QQmlIncubationController, +incubator: Qt.QQmlIncubator, +flag: Qt.IncubationFlag) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQmlIncubationController.incubateWhile__IncubationFlag_Int32(controller, flag, Qt.Int32{1})
    loading: Bool <- Qt.QQmlIncubator.isLoading(incubator)
    ready: Bool <- Qt.QQmlIncubator.isReady(incubator)
    require(loading, loading_message(ready))
    canceled(engine, controller, incubator, flag)

def incubator(engine: Qt.QQmlEngine, controller: Qt.QQmlIncubationController, component: Qt.QQmlComponent, +incubator: Qt.QQmlIncubator) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQmlComponent.create__QQmlIncubator_QQmlContext_QQmlContext(component, incubator, Qt.QQmlContext{0}, Qt.QQmlContext{0})
    loading: Bool <- Qt.QQmlIncubator.isLoading(incubator)
    require(loading, "QML creation unexpectedly ran synchronously")
    Qt.IncubationFlag.with(Unit, Qt.IncubationFlag.new(True{}), value => flag(engine, controller, incubator, value))

def loaded(engine: Qt.QQmlEngine, controller: Qt.QQmlIncubationController, +component: Qt.QQmlComponent, data: Qt.QByteArray, url: Qt.QUrl) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQmlComponent.setData(component, data, url)
    ready: Bool <- Qt.QQmlComponent.isReady(component)
    require(ready, "Incubation component did not compile")
    Qt.QQmlIncubator.with(Unit, Qt.QQmlIncubator.new(), value => incubator(engine, controller, component, value))

def component(engine: Qt.QQmlEngine, controller: Qt.QQmlIncubationController, +component: Qt.QQmlComponent) -> Qt.Action(Unit):
  Qt.QByteArray.with(Unit, Qt.QByteArray.fromUtf8("import QtQuick\nItem { objectName: \"incubated\"\n" ++ objects(12n) ++ "}"), data =>
    Qt.QUrl.with(Unit, Qt.QUrl.new(), url => loaded(engine, controller, component, data, url)))

def controller(+engine: Qt.QQmlEngine, +controller: Qt.QQmlIncubationController) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQmlEngine.setIncubationController(engine, controller)
    attached: Qt.QQmlEngine <- Qt.QQmlIncubationController.engine(controller)
    require(U32.is_eq(Qt.QQmlEngine.word(attached), Qt.QQmlEngine.word(engine)), "Idle controller lost its engine association")
    Qt.QQmlComponent.with(Unit, Qt.QQmlComponent.new__QQmlEngine_QObject(engine, Qt.QObject{0}), value => component(engine, controller, value))

def engine(+engine: Qt.QQmlEngine) -> Qt.Action(Unit):
  Qt.QQmlIncubationController.with(Unit, Qt.QQmlIncubationController.new(), value => controller(engine, value))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQmlEngine.with(Unit, Qt.QQmlEngine.new(), value => engine(value))
    objects: U32 <- Qt.Runtime.liveObjects()
    pins: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(pins, 0), "Incubation retained native state after completion")
    Qt.Action.lift(Unit, IO.print("QT612_INCUBATION_OK asynchronous=1 cancel=1 deadline=1 flag_pin=1 engine_pin=1 association=1 resume=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
