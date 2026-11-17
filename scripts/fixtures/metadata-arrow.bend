import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def named(value: Maybe<&2, String>) -> Qt.Action(Unit):
  match value:
    case Some{name}: require(String.eq(name, "QAbstractButton"), "Metadata arrow resolved the wrong superclass")
    case None{}: Qt.Action.fail(Unit, 1, "Superclass metadata name disappeared")

def objects() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +source: Qt.QPushButton <- Qt.QPushButton.new()
    +meta: Qt.QMetaObject <- Qt.QPushButton.metaObject(source)
    +data: Qt.QMetaObject.Data <- Qt.QMetaObject.Fields.d(meta)
    +super: Qt.QMetaObject.SuperData <- Qt.QMetaObject.Data.Fields.superdata(data)
    +arrow: Qt.QMetaObject <- Qt.QMetaObject.SuperData.get(super)
    +direct: Qt.QMetaObject <- Qt.QMetaObject.SuperData.Fields.direct(super)
    +base: Qt.QMetaObject <- Qt.QMetaObject.superClass(meta)
    name: Maybe<&2, String> <- Qt.QMetaObject.className(arrow)
    named(name)
    name: Maybe<&2, String> <- Qt.QMetaObject.className(direct)
    named(name)
    name: Maybe<&2, String> <- Qt.QMetaObject.className(base)
    named(name)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, objects())
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Metadata arrow leaked handles")
    Qt.Action.lift(Unit, IO.print("QT612_METADATA_ARROW_OK native_operator=1 superclass=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
