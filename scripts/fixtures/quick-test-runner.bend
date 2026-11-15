import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def application() -> Qt.Method:
  Qt.Method.define("applicationAvailable", [], Qt.unit())

def engine() -> Qt.Method:
  Qt.Method.define("qmlEngineAvailable", [Qt.QQmlEngine.arg()], Qt.unit())

def cleanup() -> Qt.Method:
  Qt.Method.define("cleanupTestCase", [], Qt.unit())

def Setup() -> Qt.QtObject:
  Qt.QtObject.withMethods(Qt.QObject.define("BendQuickTestSetup", []), [application(), engine(), cleanup()])

def mark(+object: Qt.QObject, suffix: String) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    value: String <- Qt.QObject.objectName(object)
    Qt.QObject.setObjectName(object, value ++ suffix)

def available(object: Qt.QObject) -> Qt.Action(Unit):
  mark(object, "A")

def prepared(object: Qt.QObject, engine: Qt.QQmlEngine) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    mark(object, "E")
    context: Qt.QQmlContext <- Qt.QQmlEngine.rootContext(engine)
    answer: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.int32(), Qt.Int32{42})
    Qt.QQmlContext.setContextProperty__String_QVariant(context, "bendAnswer", answer)

def finished(object: Qt.QObject) -> Qt.Action(Unit):
  mark(object, "C")

def write(path: String) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +file: Qt.QFile <- Qt.QFile.new__String(path)
    opened: Bool <- Qt.QFile.open__Flags_QIODeviceBase__OpenModeFlag(file, Qt.Flags_QIODeviceBase__OpenModeFlag{2})
    require(opened, "Quick Test fixture file did not open")
    source: Qt.QByteArray <- Qt.QByteArray.fromUtf8("import QtQuick\nimport QtTest\nTestCase { name: 'BendRunner'; function test_value() { compare(typeof bendAnswer === 'undefined' ? 42 : bendAnswer, 42) } }\n")
    size: Qt.Int64 <- Qt.QFile.write__QByteArray(file, source)
    Qt.QFile.close(file)

def values() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +directory: Qt.QTemporaryDir <- Qt.QTemporaryDir.new()
    +path: String <- Qt.QTemporaryDir.path(directory)
    write(path ++ "/tst_bend.qml")
    result: Qt.Int32 <- Qt.QuickTest.run("BendPlainQuickTest", [], path)
    require(U32.is_eq(Qt.Int32.word(result), 0), "Native plain Qt Quick Test runner failed")
    +setup: Qt.QtObject.Instance(Setup()) <- Qt.QtObject.new(~Setup())
    +object: Qt.QObject = Qt.QtObject.as_QObject(~Setup(), setup)
    Qt.Method.handle(~application(), ~Qt.QObject, ~available, object, object)
    Qt.Method.handle(~engine(), ~Qt.QObject, ~prepared, object, object)
    Qt.Method.handle(~cleanup(), ~Qt.QObject, ~finished, object, object)
    result: Qt.Int32 <- Qt.QuickTest.runWithSetup("BendSetupQuickTest", ["bend-quick-test"], path, object)
    require(U32.is_eq(Qt.Int32.word(result), 0), "Native setup Qt Quick Test runner failed")
    name: String <- Qt.QObject.objectName(object)
    require(String.eq(name, "AEC"), "Qt Quick Test did not invoke every Bend setup method")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, values())
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Quick Test setup handles leaked")
    Qt.Action.lift(Unit, IO.print("QT612_QUICK_TEST_RUNNER_OK native=1 reuse=1 setup=1 engines=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
