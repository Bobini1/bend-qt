import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

# Qt asks the widget interface for its specialized interfaces.
def facet(action: Qt.QAccessibleActionInterface, kind: Qt.QAccessible.InterfaceType) -> Qt.Action(Qt.AccessibleFacet):
  Qt.AccessibleFacet.fromActionInterface(action)

def action_names(state: Unit) -> Qt.Action(List<&2, String>):
  Qt.Action.pure(List<&2, String>, ["facet action"])

def names(values: List<&2, String>) -> Qt.Action(Unit):
  match values:
    case value <> Nil{}: require(String.eq(value, "facet action"), "The specialized interface returned the wrong action")
    case _: Qt.Action.fail(Unit, 1, "The specialized interface lost its actions")

def wrong(result: Result<&1, &1, U32 & String, Qt.QAccessibleTextInterface>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 22), "Wrong interface mismatch error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "A mismatched accessible interface was accepted")

def cast(+source: Qt.QAccessibleInterface, +action: Qt.QAccessibleActionInterface) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QAccessibleInterface.Virtual.interface_cast.handle(~Qt.QAccessibleActionInterface, ~facet, source, action)
    acquired: Qt.QAccessibleActionInterface <- Qt.QAccessibleInterface.actionInterface(source)
    Qt.QAccessibleActionInterface.release(action)
    result: List<&2, String> <- Qt.QAccessibleActionInterface.actionNames(acquired)
    names(result)
    failure: Result<&1, &1, U32 & String, Qt.QAccessibleTextInterface> <- Qt.Action.attempt(Qt.QAccessibleTextInterface, Qt.QAccessibleInterface.textInterface(source))
    wrong(failure)

def widget(+action: Qt.QAccessibleActionInterface, widget: Qt.QWidget) -> Qt.Action(Unit):
  Qt.QAccessibleWidget.with(Unit, Qt.QAccessibleWidget.newOverride__QWidget_QAccessible_Role(widget, Qt.QAccessible.Role.Client()), source => cast(Qt.QAccessibleWidget.as_QAccessibleInterface(source), action))

def action_scope(+action: Qt.QAccessibleActionInterface) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QAccessibleActionInterface.Virtual.actionNames.handle(~Unit, ~action_names, action, Unit{})
    Qt.QWidget.with(Unit, Qt.QWidget.new(), value => widget(action, value))

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QAccessibleActionInterface.with(Unit, Qt.QAccessibleActionInterface.newOverride(), action => action_scope(action))
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Accessible facets leaked native handles")
    Qt.Action.lift(Unit, IO.print("QT612_ACCESSIBLE_FACETS_OK native_specialization=1 typed_reply=1 retained=1 mismatch_rejected=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
