import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def error(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong native-item error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected checked native-item failure")

def insert_standard(+model: Qt.QStandardItemModel, +item: Qt.QStandardItem) -> Qt.Action(Qt.QStandardItem):
  do Qt.Action<Qt.QStandardItem>:
    Qt.QStandardItemModel.setItem__Int32_QStandardItem(model, Qt.Int32{0}, item)
    strict: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QStandardItem.destroy(item))
    error(Unit, strict, 1)
    return item

def invalid_position(+model: Qt.QStandardItemModel, +item: Qt.QStandardItem) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    rejected: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QStandardItemModel.setItem__Int32_QStandardItem(model, Qt.Int32.neg(1), item))
    error(Unit, rejected, 22)
    # Qt rejected the mutation; the argument must still belong to its caller.
    Qt.QStandardItem.destroy(item)

def duplicate_standard(+model: Qt.QStandardItemModel, original: Qt.QStandardItem, +candidate: Qt.QStandardItem) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QStandardItemModel.setItem__Int32_QStandardItem(model, Qt.Int32{1}, candidate)
    rejected: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QStandardItemModel.setItem__Int32_QStandardItem(model, Qt.Int32{0}, candidate))
    error(Unit, rejected, 16)
    text: String <- Qt.QStandardItem.text(original)
    require(String.eq(text, "Native item"), "Rejected duplicate insertion invalidated the existing item")

def standard_case(+model: Qt.QStandardItemModel) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QStandardItem.with(Unit, Qt.QStandardItem.new(), value => invalid_position(model, value))
    +item: Qt.QStandardItem <- Qt.QStandardItem.with(Qt.QStandardItem, Qt.QStandardItem.new__String("Native item"), value => insert_standard(model, value))
    alias: Qt.QStandardItem <- Qt.QStandardItemModel.item__Int32_Int32(model, Qt.Int32{0}, Qt.Int32{0})
    require(U32.is_eq(Qt.QStandardItem.word(item), Qt.QStandardItem.word(alias)), "Model item alias changed identity")
    Qt.QStandardItem.with(Unit, Qt.QStandardItem.new(), value => duplicate_standard(model, item, value))
    +taken: Qt.QStandardItem <- Qt.QStandardItemModel.takeItem(model, Qt.Int32{0}, Qt.Int32{0})
    text: String <- Qt.QStandardItem.text(taken)
    require(String.eq(text, "Native item"), "Taking an item invalidated the surviving native object")
    Qt.QStandardItem.destroy(taken)
    gone: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QStandardItem.text(item))
    error(String, gone, 116)
    +replacement: Qt.QStandardItem <- Qt.QStandardItem.with(Qt.QStandardItem, Qt.QStandardItem.new__String("Delete on clear"), value => insert_standard(model, value))
    Qt.QStandardItemModel.clear(model)
    cleared: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QStandardItem.text(replacement))
    error(String, cleared, 116)

def list_case(+list: Qt.QListWidget) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    # addItem(String) creates its item in Qt, without a binding destructor shim.
    Qt.QListWidget.addItem__String(list, "Created by Qt")
    +item: Qt.QListWidgetItem <- Qt.QListWidget.item(list, Qt.Int32{0})
    +taken: Qt.QListWidgetItem <- Qt.QListWidget.takeItem(list, Qt.Int32{0})
    require(U32.is_eq(Qt.QListWidgetItem.word(item), Qt.QListWidgetItem.word(taken)), "Native-created item take lost identity")
    text: String <- Qt.QListWidgetItem.text(taken)
    require(String.eq(text, "Created by Qt"), "Native-created item was invalidated while taken")
    Qt.QListWidgetItem.destroy(taken)
    Qt.QListWidget.addItem__String(list, "Observe model deletion")
    +removed: Qt.QListWidgetItem <- Qt.QListWidget.item(list, Qt.Int32{0})
    +model: Qt.QAbstractItemModel <- Qt.QListWidget.model(list)
    accepted: Bool <- Qt.QModelIndex.with(Bool, Qt.QModelIndex.new(), parent => Qt.QAbstractItemModel.removeRow(model, Qt.Int32{0}, parent))
    require(accepted, "Native model rejected row removal")
    gone: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QListWidgetItem.text(removed))
    error(String, gone, 116)

def insert_graphic(+scene: Qt.QGraphicsScene, +item: Qt.QGraphicsRectItem) -> Qt.Action(Qt.QGraphicsRectItem):
  do Qt.Action<Qt.QGraphicsRectItem>:
    Qt.QGraphicsScene.addItem(scene, Qt.QGraphicsRectItem.as_QGraphicsItem(item))
    strict: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QGraphicsRectItem.destroy(item))
    error(Unit, strict, 1)
    return item

def graphics_case(+scene: Qt.QGraphicsScene) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +item: Qt.QGraphicsRectItem <- Qt.QGraphicsRectItem.with(Qt.QGraphicsRectItem, Qt.QGraphicsRectItem.new(), value => insert_graphic(scene, value))
    Qt.QGraphicsScene.removeItem(scene, Qt.QGraphicsRectItem.as_QGraphicsItem(item))
    Qt.QGraphicsRectItem.destroy(item)
    +second: Qt.QGraphicsRectItem <- Qt.QGraphicsRectItem.with(Qt.QGraphicsRectItem, Qt.QGraphicsRectItem.new(), value => insert_graphic(scene, value))
    Qt.QGraphicsScene.clear(scene)
    gone: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QGraphicsRectItem.destroy(second))
    error(Unit, gone, 116)

def layout_widget(+layout: Qt.QVBoxLayout, +widget: Qt.QWidget) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QVBoxLayout.addWidget__QWidget(layout, widget)
    +borrowed: Qt.QLayoutItem <- Qt.QVBoxLayout.itemAt(layout, Qt.Int32{0})
    +taken: Qt.QLayoutItem <- Qt.QVBoxLayout.takeAt(layout, Qt.Int32{0})
    require(U32.is_eq(Qt.QLayoutItem.word(borrowed), Qt.QLayoutItem.word(taken)), "Layout take changed item identity")
    Qt.QLayoutItem.destroy(taken)
    Qt.QWidget.setObjectName(widget, "Layout item did not own the widget")
    Qt.QVBoxLayout.addWidget__QWidget(layout, widget)
    +removed: Qt.QLayoutItem <- Qt.QVBoxLayout.itemAt(layout, Qt.Int32{0})
    Qt.QVBoxLayout.removeWidget(layout, widget)
    stale: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.QLayoutItem.isEmpty(removed))
    error(Bool, stale, 116)

def layout_case(layout: Qt.QVBoxLayout) -> Qt.Action(Unit):
  Qt.QWidget.with(Unit, Qt.QWidget.new(), widget => layout_widget(layout, widget))

def occupied_form(+layout: Qt.QFormLayout, +original: Qt.QSpacerItem, +candidate: Qt.QSpacerItem) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QFormLayout.setItem(layout, Qt.Int32{0}, Qt.QFormLayout.ItemRole.SpanningRole(), Qt.QSpacerItem.as_QLayoutItem(original))
    rejected: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QFormLayout.setItem(layout, Qt.Int32{0}, Qt.QFormLayout.ItemRole.SpanningRole(), Qt.QSpacerItem.as_QLayoutItem(candidate)))
    error(Unit, rejected, 16)
    alias: Qt.QLayoutItem <- Qt.QFormLayout.itemAt__Int32_QFormLayout_ItemRole(layout, Qt.Int32{0}, Qt.QFormLayout.ItemRole.SpanningRole())
    require(U32.is_eq(Qt.QLayoutItem.word(alias), Qt.QSpacerItem.word(original)), "Rejected form insertion invalidated its existing item")
    Qt.QSpacerItem.destroy(candidate)

def form_case(+layout: Qt.QFormLayout) -> Qt.Action(Unit):
  Qt.QSpacerItem.with(Unit, Qt.QSpacerItem.new__Int32_Int32(Qt.Int32{10}, Qt.Int32{10}), original =>
    Qt.QSpacerItem.with(Unit, Qt.QSpacerItem.new__Int32_Int32(Qt.Int32{20}, Qt.Int32{20}), candidate => occupied_form(layout, original, candidate)))

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QStandardItemModel.with(Unit, Qt.QStandardItemModel.new(), value => standard_case(value))
    Qt.QListWidget.with(Unit, Qt.QListWidget.new(), value => list_case(value))
    Qt.QGraphicsScene.with(Unit, Qt.QGraphicsScene.new(), value => graphics_case(value))
    Qt.QVBoxLayout.with(Unit, Qt.QVBoxLayout.new(), layout_case)
    Qt.QFormLayout.with(Unit, Qt.QFormLayout.new(), value => form_case(value))
    objects: U32 <- Qt.Runtime.liveObjects()
    pins: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(pins, 0), "Native item ownership leaked handles")
    Qt.Action.lift(Unit, IO.print("QT612_NATIVE_ITEMS_OK model=1 take=1 native_created=1 model_remove=1 scene=1 layout=1 objects=0 pins=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
