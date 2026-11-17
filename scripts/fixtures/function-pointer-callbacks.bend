import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def scaled(state: String, progress: Qt.F64) -> Qt.Action(Qt.F64):
  do Qt.Action<Qt.F64>:
    factor: Qt.F64 <- Qt.F64.fromString(state)
    Qt.F64.multiply(progress, factor)

def refused(state: Unit, progress: Qt.F64) -> Qt.Action(Qt.F64):
  Qt.Action.fail(Qt.F64, 82, "Expected custom easing failure")

def expected(~A: Data, result: Result<&1, &1, U32 & String, A>, code: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(actual, message)}: require(U32.is_eq(actual, code), message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected callback failure")

def same_function(+original: Qt.QEasingCurve.EasingFunction, other: Qt.QEasingCurve.EasingFunction) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    same: Bool <- Qt.QEasingCurve.EasingFunction.isSame(original, other)
    require(same, "A copied curve lost its native function identity")

def custom_function(value: Maybe<&2, Qt.QEasingCurve.EasingFunction>, original: Qt.QEasingCurve.EasingFunction) -> Qt.Action(Unit):
  match value:
    case Some{function}: same_function(original, function)
    case None{}: Qt.Action.fail(Unit, 1, "A custom easing function disappeared")

def no_function(value: Maybe<&2, Qt.QEasingCurve.EasingFunction>) -> Qt.Action(Unit):
  match value:
    case None{}: Qt.Action.pure(Unit, Unit{})
    case Some{function}: Qt.Action.fail(Unit, 1, "A linear curve reported a custom function")

def easing() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +curve: Qt.QEasingCurve <- Qt.QEasingCurve.new()
    empty: Maybe<&2, Qt.QEasingCurve.EasingFunction> <- Qt.QEasingCurve.customType(curve)
    no_function(empty)
    +function: Qt.QEasingCurve.EasingFunction <- Qt.QEasingCurve.EasingFunction.new(~String, ~scaled, "2")
    Qt.QEasingCurve.setCustomType(curve, function)
    +progress: Qt.F64 <- Qt.F64.fromString("0.25")
    +expectedValue: Qt.F64 <- Qt.F64.fromString("0.5")
    actual: Qt.F64 <- Qt.QEasingCurve.EasingFunction.call(function, progress)
    ok: Bool <- Qt.F64.equal(actual, expectedValue)
    require(ok, "A typed easing function did not execute")
    +animation: Qt.QVariantAnimation <- Qt.QVariantAnimation.new()
    Qt.QVariantAnimation.setEasingCurve(animation, curve)
    +copy: Qt.QEasingCurve <- Qt.QVariantAnimation.easingCurve(animation)
    view: Maybe<&2, Qt.QEasingCurve.EasingFunction> <- Qt.QEasingCurve.customType(copy)
    custom_function(view, function)
    Qt.QEasingCurve.destroy(curve)
    Qt.QEasingCurve.EasingFunction.release(function)
    actual: Qt.F64 <- Qt.QEasingCurve.valueForProgress(copy, progress)
    ok: Bool <- Qt.F64.equal(actual, expectedValue)
    require(ok, "Destroying the source curve or function view invalidated a native copied curve")
    +failed: Qt.QEasingCurve <- Qt.QEasingCurve.new()
    Qt.QEasingCurve.setCustomHandler(~Unit, ~refused, failed, Unit{})
    result: Result<&1, &1, U32 & String, Qt.F64> <- Qt.Action.attempt(Qt.F64, Qt.QEasingCurve.valueForProgress(failed, progress))
    expected(~Qt.F64, result, 82)

def many_functions(count: Nat) -> Qt.Action(Unit):
  match count:
    case Zero{}: Qt.Action.pure(Unit, Unit{})
    case Succ{previous}: Qt.Action.bind(Unit, Unit,
      Qt.QEasingCurve.with(Unit, Qt.QEasingCurve.new(), curve => Qt.QEasingCurve.setCustomHandler(~String, ~scaled, curve, "2")),
      unit => many_functions(previous))

type FactoryState is Data:
  FactoryState{widget: Qt.QWidget, label: String}

def build_interface(+widget: Qt.QWidget, label: String) -> Qt.Action(Qt.QAccessibleInterface):
  do Qt.Action<Qt.QAccessibleInterface>:
    value: Qt.QAccessibleWidget <- Qt.QAccessibleWidget.newOverride__QWidget_QAccessible_Role_String(widget, Qt.QAccessible.Role.Client(), label)
    return Qt.QAccessibleWidget.as_QAccessibleInterface(value)

def selected_factory(ok: Bool, widget: Qt.QWidget, label: String) -> Qt.Action(Qt.QAccessibleInterface):
  match ok:
    case True{}: build_interface(widget, label)
    case False{}: Qt.Action.pure(Qt.QAccessibleInterface, Qt.QAccessibleInterface{0})

def factory(state: FactoryState, key: String, object: Qt.QObject) -> Qt.Action(Qt.QAccessibleInterface):
  match state:
    case FactoryState{+widget, label}: selected_factory(U32.is_eq(Qt.QWidget.word(widget), Qt.QObject.word(object)), widget, label)

def refused_factory(state: Unit, key: String, object: Qt.QObject) -> Qt.Action(Qt.QAccessibleInterface):
  Qt.Action.fail(Qt.QAccessibleInterface, 83, "Expected accessibility factory failure")

def accessible_defaults() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +constantWidget: Qt.QWidget <- Qt.QWidget.new()
    +constant: Qt.QAccessibleInterface <- Qt.CallbackProbe.constAccessible(constantWidget)
    _: String <- Qt.QAccessibleInterface.text(constant, Qt.QAccessible.Text.Name())
    forbidden: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QAccessibleInterface.setText(constant, Qt.QAccessible.Text.Name(), "constant"))
    expected(~Unit, forbidden, 1)
    +mutable: Qt.QAccessibleInterface <- Qt.QAccessible.queryAccessibleInterface(Qt.QWidget.as_QObject(constantWidget))
    Qt.QAccessibleInterface.setText(mutable, Qt.QAccessible.Text.Name(), "mutable")
    +widget: Qt.QWidget <- Qt.QWidget.new()
    +value: Qt.QAccessibleInterface <- Qt.QAccessible.queryAccessibleInterface(Qt.QWidget.as_QObject(widget))
    valid: Bool <- Qt.QAccessibleInterface.isValid(value)
    require(valid, "A default Qt accessibility interface could not be borrowed")
    id: U32 <- Qt.QAccessible.uniqueId(value)
    Qt.QAccessible.deleteAccessibleInterface(id)
    stale: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.QAccessibleInterface.isValid(value))
    expected(~Bool, stale, 116)
    +owned: Qt.QAccessibleWidget <- Qt.QAccessibleWidget.new__QWidget_QAccessible_Role_String(widget, Qt.QAccessible.Role.Client(), "registered")
    +id: U32 <- Qt.QAccessible.registerAccessibleInterface(Qt.QAccessibleWidget.as_QAccessibleInterface(owned))
    +cached: Qt.QAccessibleInterface <- Qt.QAccessible.accessibleInterface(id)
    text: String <- Qt.QAccessibleInterface.text(cached, Qt.QAccessible.Text.Name())
    require(String.eq(text, "registered"), "Explicit interface registration lost its native object")
    Qt.QAccessible.deleteAccessibleInterface(id)
    +owned: Qt.QAccessibleWidget <- Qt.QAccessibleWidget.newOverride__QWidget_QAccessible_Role_String(widget, Qt.QAccessible.Role.Client(), "implicit")
    +id: U32 <- Qt.QAccessible.uniqueId(Qt.QAccessibleWidget.as_QAccessibleInterface(owned))
    +cached: Qt.QAccessibleInterface <- Qt.QAccessible.accessibleInterface(id)
    text: String <- Qt.QAccessibleInterface.text(cached, Qt.QAccessible.Text.Name())
    require(String.eq(text, "implicit"), "uniqueId did not register and transfer its interface")
    Qt.QAccessible.deleteAccessibleInterface(id)

def accessible() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +widget: Qt.QWidget <- Qt.QWidget.new()
    +first: Qt.QAccessible.InterfaceFactory <- Qt.QAccessible.installFactory(~FactoryState, ~factory, FactoryState{widget, "first"})
    +second: Qt.QAccessible.InterfaceFactory <- Qt.QAccessible.installFactory(~FactoryState, ~factory, FactoryState{widget, "second"})
    ok: Bool <- Qt.CallbackProbe.accessibleFactoryNamed(widget, "second", True{})
    require(ok, "QAccessible did not call its newest factory first")
    Qt.QAccessible.removeFactory(second)
    ok: Bool <- Qt.CallbackProbe.accessibleFactoryNamed(widget, "first", True{})
    require(ok, "Removing a factory did not restore the preceding factory")
    Qt.QAccessible.removeFactory(first)
    ok: Bool <- Qt.CallbackProbe.accessibleFactoryNamed(widget, "first", False{})
    require(ok, "Removing its factory destroyed a Qt-owned cached interface")
    +cached: Qt.QAccessibleInterface <- Qt.QAccessible.queryAccessibleInterface(Qt.QWidget.as_QObject(widget))
    Qt.QWidget.destroy(widget)
    expired: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.QAccessibleInterface.isValid(cached))
    expected(~Bool, expired, 116)
    stale: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QAccessible.removeFactory(first))
    expected(~Unit, stale, 116)
    +failed: Qt.QAccessible.InterfaceFactory <- Qt.QAccessible.installFactory(~Unit, ~refused_factory, Unit{})
    +other: Qt.QWidget <- Qt.QWidget.new()
    result: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.CallbackProbe.accessibleFactoryNamed(other, "never", True{}))
    expected(~Bool, result, 83)
    Qt.QAccessible.removeFactory(failed)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, easing())
    many_functions(U32.to_nat(12))
    Qt.scoped(Unit, accessible_defaults())
    Qt.scoped(Unit, accessible())
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Function views or accessibility factories leaked registry objects")
    Qt.Action.lift(Unit, IO.print("QT612_FUNCTION_POINTER_CALLBACKS_OK easing=1 native_copy=1 views=1 more_than_ten=1 pool=application factories=1 ownership=qt failures=82_83"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
