import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

# Handlers record what they saw in the probe's object name. Qt calls them
# during the operation that emits the signal, with arguments valid for the
# duration of the call.
def range_changed(probe: Qt.QObject, low: Qt.Int32, high: Qt.Int32) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    require(U32.is_eq(Qt.Int32.word(low), Qt.Int32.word(Qt.Int32.neg(10))) && U32.is_eq(Qt.Int32.word(high), 42), "Signal argument order changed")
    Qt.QObject.setObjectName(probe, "range")

def connected_slider(+slider: Qt.QSlider, +probe: Qt.QObject, connection: Qt.Connection) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QSlider.setRange(slider, Qt.Int32.neg(10), Qt.Int32{42})
    name: String <- Qt.QObject.objectName(probe)
    require(String.eq(name, "range"), "rangeChanged did not run during setRange")

def slider_case(+probe: Qt.QObject, +slider: Qt.QSlider) -> Qt.Action(Unit):
  Qt.Connection.with(Unit, Qt.QSlider.connect_rangeChanged(~Qt.QObject, ~range_changed, slider, probe),
    connection => connected_slider(slider, probe, connection))

def data_changed(probe: Qt.QObject, first: Qt.QModelIndex, last: Qt.QModelIndex, roles: List<&2, Qt.Int32>) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    a: Qt.Int32 <- Qt.QModelIndex.row(first)
    b: Qt.Int32 <- Qt.QModelIndex.column(last)
    require(U32.is_eq(Qt.Int32.word(a), 0) && U32.is_eq(Qt.Int32.word(b), 0), "Signal indexes are wrong")
    require(U32.is_ne(U32.from_nat(List.length(&2, Qt.Int32, roles)), 0), "Signal lost the role list")
    Qt.QObject.setObjectName(probe, "data")

def changed_model(+model: Qt.QStandardItemModel, +index: Qt.QModelIndex, +value: Qt.QVariant, +probe: Qt.QObject, connection: Qt.Connection) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    good: Bool <- Qt.QStandardItemModel.setData__QModelIndex_QVariant_Int32(model, index, value, Qt.Int32{256})
    require(good, "setData failed")
    name: String <- Qt.QObject.objectName(probe)
    require(String.eq(name, "data"), "dataChanged did not run during setData")
    # After disconnecting, a change reaches no handler.
    Qt.Connection.disconnect(connection)
    Qt.QObject.setObjectName(probe, "")
    again: Bool <- Qt.QStandardItemModel.setData__QModelIndex_QVariant_Int32(model, index, value, Qt.Int32{257})
    after: String <- Qt.QObject.objectName(probe)
    require(again && String.eq(after, ""), "A disconnected handler still ran")

def model_index(+model: Qt.QStandardItemModel, +probe: Qt.QObject, +index: Qt.QModelIndex) -> Qt.Action(Unit):
  Qt.QVariant.with(Unit, Qt.QVariant.fromString("first 🎵"), value =>
    Qt.Connection.with(Unit, Qt.QStandardItemModel.connect_dataChanged(~Qt.QObject, ~data_changed, model, probe),
      connection => changed_model(model, index, value, probe, connection)))

def invalid_parent(+model: Qt.QStandardItemModel, +probe: Qt.QObject, parent: Qt.QModelIndex) -> Qt.Action(Unit):
  Qt.QModelIndex.with(Unit, Qt.QStandardItemModel.index__Int32_Int32_QModelIndex(model, Qt.Int32{0}, Qt.Int32{0}, parent), index => model_index(model, probe, index))

def model_case(+probe: Qt.QObject, +model: Qt.QStandardItemModel) -> Qt.Action(Unit):
  Qt.QModelIndex.with(Unit, Qt.QModelIndex.new(), parent => invalid_parent(model, probe, parent))

def activated_text(probe: Qt.QObject, text: String) -> Qt.Action(Unit):
  Qt.QObject.setObjectName(probe, "text")

def activated_index(probe: Qt.QObject, index: Qt.QModelIndex) -> Qt.Action(Unit):
  Qt.QObject.setObjectName(probe, "index")

# Overloaded signals have one connect per argument list.
def completer_case(+probe: Qt.QObject, +completer: Qt.QCompleter) -> Qt.Action(Unit):
  Qt.Connection.with(Unit, Qt.QCompleter.connect_activated__String(~Qt.QObject, ~activated_text, completer, probe), text =>
    Qt.Connection.with(Unit, Qt.QCompleter.connect_activated__QModelIndex(~Qt.QObject, ~activated_index, completer, probe),
      index => Qt.Action.pure(Unit, Unit{})))

def cases(+probe: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QSlider.with(Unit, Qt.QSlider.new(), slider => slider_case(probe, slider))
    Qt.QStandardItemModel.with(Unit, Qt.QStandardItemModel.new__Int32_Int32_QObject(Qt.Int32{1}, Qt.Int32{1}, Qt.QObject{0}), model => model_case(probe, model))
    Qt.QCompleter.with(Unit, Qt.QCompleter.new(), completer => completer_case(probe, completer))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QObject.with(Unit, Qt.QObject.new(), probe => cases(probe))
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Signal connections or arguments leaked handles")
    Qt.Action.lift(Unit, IO.print("QT612_SIGNALS_OK two_args=1 three_args=1 value_arguments=1 nested_list=1 disconnect=1 overloaded_connect=1 objects=0 connections=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
