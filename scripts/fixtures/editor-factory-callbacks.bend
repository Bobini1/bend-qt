import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def create_widget(state: Unit, parent: Qt.QWidget) -> Qt.Action(Qt.QWidget):
  Qt.QWidget.new()

def property_name(state: Unit) -> Qt.Action(Qt.QByteArray):
  Qt.QByteArray.fromBytes(116 <> 101 <> 115 <> 116 <> Nil{})

def creator(+value: Qt.QItemEditorCreatorBase) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QItemEditorCreatorBase.Virtual.createWidget.handle(~Unit, ~create_widget, value, Unit{})
    Qt.QItemEditorCreatorBase.Virtual.valuePropertyName.handle(~Unit, ~property_name, value, Unit{})

def replaced(result: Result<&1, &1, U32 & String, Unit>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 116), "Wrong replaced creator error: " ++ message)
    case Done{unit}: Qt.Action.fail(Unit, 1, "Replacing a creator did not delete the old one")

def registrations(+factory: Qt.QItemEditorFactory, +first: Qt.QItemEditorCreatorBase, +second: Qt.QItemEditorCreatorBase) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    creator(first)
    creator(second)
    Qt.QItemEditorFactory.registerEditor(factory, Qt.Int32{7}, first)
    Qt.QItemEditorFactory.registerEditor(factory, Qt.Int32{7}, first)
    Qt.QItemEditorFactory.registerEditor(factory, Qt.Int32{8}, first)
    Qt.QItemEditorFactory.registerEditor(factory, Qt.Int32{7}, second)
    Qt.QItemEditorFactory.registerEditor(factory, Qt.Int32{8}, second)
    gone: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QItemEditorCreatorBase.destroy(first))
    replaced(gone)
    valid: U32 <- Qt.CallbackProbe.editorFactory(factory)
    require(U32.is_eq(valid, 1), "The native factory did not run the creator handlers")

def creators(+factory: Qt.QItemEditorFactory) -> Qt.Action(Unit):
  Qt.QItemEditorCreatorBase.with(Unit, Qt.QItemEditorCreatorBase.newOverride(), first =>
    Qt.QItemEditorCreatorBase.with(Unit, Qt.QItemEditorCreatorBase.newOverride(), second => registrations(factory, first, second)))

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QItemEditorFactory.with(Unit, Qt.QItemEditorFactory.new(), factory => creators(factory))
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Creator ownership leaked native handles")
    Qt.Action.lift(Unit, IO.print("QT612_EDITOR_FACTORY_CALLBACKS_OK ownership=1 idempotent=1 multiple_keys=1 replacement_deletion=1 native_creation=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
