import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def error(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong ownership error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected a checked ownership error")

def insert_set(+series: Qt.QBarSeries, +item: Qt.QBarSet) -> Qt.Action(Qt.QBarSet):
  do Qt.Action<Qt.QBarSet>:
    accepted: Bool <- Qt.QBarSeries.insert(series, Qt.Int64{0, 0}, item)
    require(accepted, "Series insertion failed")
    denied: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QBarSet.destroy(item))
    error(Unit, denied, 1)
    return item

def append_set(+series: Qt.QBarSeries, +item: Qt.QBarSet) -> Qt.Action(Qt.QBarSet):
  do Qt.Action<Qt.QBarSet>:
    accepted: Bool <- Qt.QBarSeries.append__List_QBarSet(series, item <> Nil{})
    require(accepted, "Bulk series append failed")
    duplicate: Bool <- Qt.QBarSeries.append__QBarSet(series, item)
    require(Bool.not(duplicate), "Duplicate native append unexpectedly succeeded")
    return item

def replace_sets(+series: Qt.QBarSeries, +item: Qt.QBarSet) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    accepted: Bool <- Qt.QBarSeries.replace__List_QBarSet(series, item <> Nil{})
    require(accepted, "Bulk series replacement failed")

def bars(+series: Qt.QBarSeries) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +inserted: Qt.QBarSet <- Qt.QBarSet.with(Qt.QBarSet, Qt.QBarSet.new__String_QObject("inserted", Qt.QObject{0}), item => insert_set(series, item))
    label: String <- Qt.QBarSet.label(inserted)
    require(String.eq(label, "inserted"), "Non-parented series insertion lost scoped member")
    taken: Bool <- Qt.QBarSeries.take(series, inserted)
    require(taken, "Taking inserted set failed")
    # Native ownership transfer ends the initial scope's cleanup obligation.
    Qt.QBarSet.destroy(inserted)
    stale: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QBarSet.label(inserted))
    error(String, stale, 116)
    +appended: Qt.QBarSet <- Qt.QBarSet.with(Qt.QBarSet, Qt.QBarSet.new__String_QObject("appended", Qt.QObject{0}), item => append_set(series, item))
    released: Bool <- Qt.QBarSeries.take(series, appended)
    require(released, "Taking appended set failed")
    Qt.QBarSet.destroy(appended)
    gone: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QBarSet.label(appended))
    error(String, gone, 116)
    +old: Qt.QBarSet <- Qt.QBarSet.with(Qt.QBarSet, Qt.QBarSet.new__String_QObject("old", Qt.QObject{0}), item => append_set(series, item))
    Qt.QBarSet.with(Unit, Qt.QBarSet.new__String_QObject("new", Qt.QObject{0}), item => replace_sets(series, item))
    replaced: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QBarSet.label(old))
    error(String, replaced, 116)

def obsolete(+stack: Qt.QUndoStack, +command: Qt.QUndoCommand) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QUndoCommand.setObsolete(command, True{})
    Qt.QUndoStack.push(stack, command)
    stale: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QUndoCommand.text(command))
    error(String, stale, 116)

def push_command(+stack: Qt.QUndoStack, +command: Qt.QUndoCommand) -> Qt.Action(Qt.QUndoCommand):
  do Qt.Action<Qt.QUndoCommand>:
    Qt.QUndoStack.push(stack, command)
    return command

def undo_stack(+stack: Qt.QUndoStack) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QUndoCommand.with(Unit, Qt.QUndoCommand.new(), command => obsolete(stack, command))
    Qt.QUndoStack.beginMacro(stack, "native macro")
    +command: Qt.QUndoCommand <- Qt.QUndoCommand.with(Qt.QUndoCommand, Qt.QUndoCommand.new__String_QUndoCommand("command", Qt.QUndoCommand{0}), value => push_command(stack, value))
    Qt.QUndoStack.endMacro(stack)
    +macro: Qt.QUndoCommand <- Qt.QUndoStack.command(stack, Qt.Int32{0})
    label: String <- Qt.QUndoCommand.text(macro)
    require(String.eq(label, "native macro"), "Native-created macro observation failed")
    Qt.QUndoStack.clear(stack)
    stale: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QUndoCommand.text(command))
    error(String, stale, 116)
    macro_stale: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QUndoCommand.text(macro))
    error(String, macro_stale, 116)

def target(+source: Qt.QState, +state: Qt.QState) -> Qt.Action(Qt.QState & Qt.QAbstractTransition):
  do Qt.Action<Qt.QState & Qt.QAbstractTransition>:
    Qt.QState.setObjectName(state, "retained target")
    +transition: Qt.QAbstractTransition <- Qt.QState.addTransition__QAbstractState(source, Qt.QState.as_QAbstractState(state))
    Qt.QAbstractTransition.setTargetStates(transition, Qt.QState.as_QAbstractState(state) <> Nil{})
    return (state, transition)

def check_target(pair: Qt.QState & Qt.QAbstractTransition) -> Qt.Action(Unit):
  (+state, +transition) = pair
  do Qt.Action<Unit>:
    label: String <- Qt.QState.objectName(state)
    require(String.eq(label, "retained target"), "Transition did not retain scoped target")
    Qt.QAbstractTransition.setTargetState(transition, Qt.QAbstractState{0})
    stale: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QState.objectName(state))
    error(String, stale, 116)

def states(+source: Qt.QState) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    pair: Qt.QState & Qt.QAbstractTransition <- Qt.QState.with(Qt.QState & Qt.QAbstractTransition, Qt.QState.new(), value => target(source, value))
    check_target(pair)

def aspect(+engine: Qt.Qt3DCore.QAspectEngine, +value: Qt.Qt3DCore.QAbstractAspect) -> Qt.Action(Qt.Qt3DCore.QAbstractAspect):
  do Qt.Action<Qt.Qt3DCore.QAbstractAspect>:
    Qt.Qt3DCore.QAspectEngine.registerAspect__Qt3DCore_QAbstractAspect(engine, value)
    denied: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.Qt3DCore.QAbstractAspect.destroy(value))
    error(Unit, denied, 1)
    return value

def engine(+value: Qt.Qt3DCore.QAspectEngine) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +child: Qt.Qt3DCore.QAbstractAspect <- Qt.Qt3DCore.QAbstractAspect.with(Qt.Qt3DCore.QAbstractAspect, Qt.Qt3DCore.QAbstractAspect.new__QObject(Qt.QObject{0}), member => aspect(value, member))
    Qt.Qt3DCore.QAbstractAspect.setObjectName(child, "owned aspect")
    Qt.Qt3DCore.QAspectEngine.destroy(value)
    stale: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.Qt3DCore.QAbstractAspect.objectName(child))
    error(String, stale, 116)

def component(+entity: Qt.Qt3DCore.QEntity, +holder: Qt.Qt3DCore.QEntity, +value: Qt.Qt3DCore.QTransform) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Qt3DCore.QEntity.addComponent(entity, Qt.Qt3DCore.QTransform.as_Qt3DCore__QComponent(value))
    denied: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.Qt3DCore.QEntity.destroy(holder))
    error(Unit, denied, 16)
    Qt.Qt3DCore.QEntity.removeComponent(entity, Qt.Qt3DCore.QTransform.as_Qt3DCore__QComponent(value))
    Qt.Qt3DCore.QEntity.destroy(holder)

def entities(+entity: Qt.Qt3DCore.QEntity) -> Qt.Action(Unit):
  Qt.Qt3DCore.QEntity.with(Unit, Qt.Qt3DCore.QEntity.new(), +holder =>
    Qt.Qt3DCore.QTransform.with(Unit, Qt.Qt3DCore.QTransform.new__Qt3DCore_QNode(Qt.Qt3DCore.QEntity.as_Qt3DCore__QNode(holder)), value => component(entity, holder, value)))

def graphics_member(+layout: Qt.QGraphicsLinearLayout, +widget: Qt.QGraphicsWidget) -> Qt.Action(Qt.QGraphicsWidget):
  do Qt.Action<Qt.QGraphicsWidget>:
    Qt.QGraphicsLinearLayout.addItem(layout, Qt.QGraphicsWidget.as_QGraphicsLayoutItem(widget))
    denied: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QGraphicsWidget.destroy(widget))
    error(Unit, denied, 16)
    return widget

def graphics_layout(+layout: Qt.QGraphicsLinearLayout) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +widget: Qt.QGraphicsWidget <- Qt.QGraphicsWidget.with(Qt.QGraphicsWidget, Qt.QGraphicsWidget.new(), value => graphics_member(layout, value))
    Qt.QGraphicsWidget.setObjectName(widget, "layout pin")
    Qt.QGraphicsLinearLayout.removeItem(layout, Qt.QGraphicsWidget.as_QGraphicsLayoutItem(widget))
    stale: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QGraphicsWidget.objectName(widget))
    error(String, stale, 116)

def nested_layout(+outer: Qt.QGraphicsLinearLayout, +inner: Qt.QGraphicsLinearLayout) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QGraphicsLinearLayout.addItem(outer, Qt.QGraphicsLinearLayout.as_QGraphicsLayoutItem(inner))
    denied: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QGraphicsLinearLayout.destroy(inner))
    error(Unit, denied, 1)
    Qt.QGraphicsLinearLayout.removeItem(outer, Qt.QGraphicsLinearLayout.as_QGraphicsLayoutItem(inner))
    Qt.QGraphicsLinearLayout.destroy(inner)

def nested_layouts(+outer: Qt.QGraphicsLinearLayout) -> Qt.Action(Unit):
  Qt.QGraphicsLinearLayout.with(Unit, Qt.QGraphicsLinearLayout.new__QGraphicsLayoutItem(Qt.QGraphicsLinearLayout.as_QGraphicsLayoutItem(outer)), inner => nested_layout(outer, inner))

def install_layout(+widget: Qt.QGraphicsWidget, +layout: Qt.QGraphicsLinearLayout) -> Qt.Action(Qt.QGraphicsLinearLayout):
  do Qt.Action<Qt.QGraphicsLinearLayout>:
    Qt.QGraphicsWidget.setLayout(widget, Qt.QGraphicsLinearLayout.as_QGraphicsLayout(layout))
    return layout

def installed_layouts(+widget: Qt.QGraphicsWidget) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +first: Qt.QGraphicsLinearLayout <- Qt.QGraphicsLinearLayout.with(Qt.QGraphicsLinearLayout, Qt.QGraphicsLinearLayout.new(), value => install_layout(widget, value))
    +second: Qt.QGraphicsLinearLayout <- Qt.QGraphicsLinearLayout.with(Qt.QGraphicsLinearLayout, Qt.QGraphicsLinearLayout.new(), value => install_layout(widget, value))
    stale: Result<&1, &1, U32 & String, Qt.Int32> <- Qt.Action.attempt(Qt.Int32, Qt.QGraphicsLinearLayout.count(first))
    error(Qt.Int32, stale, 116)
    Qt.QGraphicsWidget.setLayout(widget, Qt.QGraphicsLayout{0})
    gone: Result<&1, &1, U32 & String, Qt.Int32> <- Qt.Action.attempt(Qt.Int32, Qt.QGraphicsLinearLayout.count(second))
    error(Qt.Int32, gone, 116)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QBarSeries.with(Unit, Qt.QBarSeries.new(), value => bars(value))
    Qt.QUndoStack.with(Unit, Qt.QUndoStack.new(), value => undo_stack(value))
    Qt.QState.with(Unit, Qt.QState.new(), value => states(value))
    Qt.Qt3DCore.QAspectEngine.with(Unit, Qt.Qt3DCore.QAspectEngine.new(), value => engine(value))
    Qt.Qt3DCore.QEntity.with(Unit, Qt.Qt3DCore.QEntity.new(), value => entities(value))
    Qt.QGraphicsLinearLayout.with(Unit, Qt.QGraphicsLinearLayout.new(), value => graphics_layout(value))
    Qt.QGraphicsLinearLayout.with(Unit, Qt.QGraphicsLinearLayout.new(), value => nested_layouts(value))
    Qt.QGraphicsWidget.with(Unit, Qt.QGraphicsWidget.new(), value => installed_layouts(value))
    count: U32 <- Qt.Runtime.liveObjects()
    pins: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(count, 0) && U32.is_eq(pins, 0), "Owning collections leaked native resources")
    Qt.Action.lift(Unit, IO.print("QT612_OWNING_COLLECTIONS_OK bars=1 undo=1 state=1 aspect=1 component=1 objects=0 pins=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
