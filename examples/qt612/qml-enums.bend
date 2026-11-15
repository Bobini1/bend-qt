import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def rejected(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Unexpected QML registration error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "QML registration accepted an invalid operation")

def register(+meta: Qt.QMetaObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    bad: Result<&1, &1, U32 & String, Qt.Int32> <- Qt.Action.attempt(Qt.Int32, Qt.Global.qmlRegisterUncreatableMetaObject(meta, "Bend.Enums\0suffix", Qt.Int32{1}, Qt.Int32{0}, "NativeEnums", "Enums only"))
    rejected(Qt.Int32, bad, 22)
    identifier: Qt.Int32 <- Qt.Global.qmlRegisterUncreatableMetaObject(meta, "Bend.Enums", Qt.Int32{1}, Qt.Int32{0}, "NativeEnums", "Enums only")
    require(Bool.not(U32.is_eq(Qt.Int32.word(identifier), 4294967295)), "Native metaobject registration failed")

def dialog(value: Qt.QFileDialog) -> Qt.Action(Unit):
  Qt.QMetaObject.with(Unit, Qt.QFileDialog.metaObject(value), meta => register(meta))

def inspect(value: Qt.QVariant) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    number: Qt.Int32 <- Qt.QVariant.toInt32(value)
    require(U32.is_eq(Qt.Int32.word(number), Qt.QFileDialog.FileMode.word(Qt.QFileDialog.FileMode.ExistingFiles)), "QML did not resolve native enum metadata")

def root(value: Qt.QObject) -> Qt.Action(Unit):
  Qt.QVariant.with(Unit, Qt.QObject.property(value, "picked"), inspect)

def load(+component: Qt.QQmlComponent, data: Qt.QByteArray, url: Qt.QUrl) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQmlComponent.setData(component, data, url)
    ready: Bool <- Qt.QQmlComponent.isReady(component)
    require(ready, "Registered enum QML component was not ready")
    Qt.QObject.with(Unit, Qt.QQmlComponent.create__QQmlContext(component, Qt.QQmlContext{0}), root)

def component(+value: Qt.QQmlComponent) -> Qt.Action(Unit):
  Qt.QByteArray.with(Unit, Qt.QByteArray.fromUtf8("import QtQml\nimport Bend.Enums 1.0\nQtObject { property int picked: NativeEnums.ExistingFiles }"), data =>
    Qt.QUrl.with(Unit, Qt.QUrl.new(), url => load(value, data, url)))

def engine(+value: Qt.QQmlEngine) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    busy: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.Global.qmlClearTypeRegistrations())
    rejected(Unit, busy, 16)
    Qt.QQmlComponent.with(Unit, Qt.QQmlComponent.new__QQmlEngine_QObject(value, Qt.QObject{0}), item => component(item))

def dynamic(meta: Qt.QMetaObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    unsupported: Result<&1, &1, U32 & String, Qt.Int32> <- Qt.Action.attempt(Qt.Int32, Qt.Global.qmlRegisterUncreatableMetaObject(meta, "Bend.Dynamic", Qt.Int32{1}, Qt.Int32{0}, "Mutable", "Dynamic"))
    rejected(Qt.Int32, unsupported, 95)

def map(value: Qt.QQmlPropertyMap) -> Qt.Action(Unit):
  Qt.QMetaObject.with(Unit, Qt.QQmlPropertyMap.metaObject(value), dynamic)

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QFileDialog.with(Unit, Qt.QFileDialog.new(), dialog)
    Qt.QQmlPropertyMap.with(Unit, Qt.QQmlPropertyMap.new(), map)
    Qt.QQmlEngine.with(Unit, Qt.QQmlEngine.new(), value => engine(value))
    Qt.Global.qmlClearTypeRegistrations()
    objects: U32 <- Qt.Runtime.liveObjects()
    pins: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(pins, 0), "Enum registration leaked native handles")
    Qt.Action.lift(Unit, IO.print("QT612_QML_ENUMS_OK static_metadata=1 source_destroyed=1 real_qml=1 engine_guard=1 dynamic_rejected=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
