import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def check_interface(+widget: Qt.QWidget, value: Qt.QAccessibleWidget, mode: Bool) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QWidget.release(widget)
    Qt.CallbackProbe.accessibleOwnership(value, mode)

def widget(+widget: Qt.QWidget, mode: Bool) -> Qt.Action(Unit):
  Qt.QAccessibleWidget.with(Unit, Qt.QAccessibleWidget.new__QWidget(widget), value => check_interface(widget, value, mode))

def stale(result: Result<&1, &1, U32 & String, Bool>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 116), "Wrong moved base error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Moved decoder alias stayed live")

def encoding_name(value: Maybe<&2, String>) -> Qt.Action(Unit):
  match value:
    case Some{name}: require(String.eq(name, "UTF-8"), "Move changed converter encoding")
    case None{}: Qt.Action.fail(Unit, 1, "Moved converter lost its encoding name")

def moved_base(+value: Qt.QStringConverter, source: Qt.QStringDecoder) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    valid: Bool <- Qt.QStringConverter.isValid(value)
    require(valid, "Protected nonvirtual base lost decoder state")
    name: Maybe<&2, String> <- Qt.QStringConverter.name(value)
    encoding_name(name)
    gone: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.QStringDecoder.isValid(source))
    stale(gone)

def move_base(+source: Qt.QStringDecoder) -> Qt.Action(Unit):
  Qt.QStringConverter.with(Unit, Qt.QStringConverter.new(Qt.QStringDecoder.as_QStringConverter(source)), value => moved_base(value, source))

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QWidget.with(Unit, Qt.QWidget.new(), value => widget(value, False{}))
    Qt.QWidget.with(Unit, Qt.QWidget.new(), value => widget(value, True{}))
    Qt.QIODeviceBase.with(Unit, Qt.QIODeviceBase.new(), value => Qt.Action.pure(Unit, Unit{}))
    Qt.QStringDecoder.with(Unit, Qt.QStringDecoder.new__String("UTF-8"), source => move_base(source))
    objects: U32 <- Qt.Runtime.liveObjects()
    edges: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(edges, 0), "Protected destructor construction leaked native objects")
    Qt.Action.lift(Unit, IO.print("QT612_PROTECTED_DESTRUCTORS_OK ordinary_constructor=1 dependency=1 derived_delete=1 native_delete_observed=1 nonvirtual_owned=1 base_move=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
