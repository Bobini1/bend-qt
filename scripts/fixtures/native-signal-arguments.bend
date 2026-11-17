import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expect_error(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected native signal argument rejection")

def nativeValues() -> Qt.Signal:
  Qt.Signal.define("nativeValues", [Qt.QPushButton.arg(), Qt.QColor.arg(), Qt.variantMap(), Qt.variant(), Qt.variantList()])

def buttonReady() -> Qt.Signal:
  Qt.Signal.define("buttonReady", [Qt.QPushButton.arg()])

def inspect_map(values: List<&2, Qt.PairValue<String, Qt.QVariant>>) -> Qt.Action(Unit):
  match values:
    case Qt.PairValue{count_key, count} <> Qt.PairValue{title_key, +title} <> Nil{}:
      do Qt.Action<Unit>:
        require(String.eq(count_key, "count") && String.eq(title_key, "title"), "Map keys changed")
        number: Qt.Int32 <- Qt.QVariant.toInt32(count)
        text: String <- Qt.QVariant.toString(title)
        require(U32.is_eq(Qt.Int32.word(number), 42) && String.eq(text, "Map"), "Map values changed")
        Qt.CallbackProbe.nativeSaveVariant(title)
    case _: Qt.Action.fail(Unit, 1, "Unexpected QVariantMap shape")

def inspect_list(values: List<&2, Qt.QVariant>) -> Qt.Action(Unit):
  match values:
    case value <> Nil{}:
      do Qt.Action<Unit>:
        number: Qt.Int32 <- Qt.QVariant.toInt32(value)
        require(U32.is_eq(Qt.Int32.word(number), 42), "Variant list changed")
    case _: Qt.Action.fail(Unit, 1, "Unexpected QVariantList shape")

def received(probe: Qt.QObject, button: Qt.QPushButton, color: Qt.QColor,
    values: List<&2, Qt.PairValue<String, Qt.QVariant>>, variant: Qt.QVariant,
    list: List<&2, Qt.QVariant>) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QPushButton.setText(button, "typed")
    name: String <- Qt.QColor.name(color)
    require(String.eq(name, "#ff0000"), "QColor was not copied")
    inspect_map(values)
    text: String <- Qt.QVariant.toString(variant)
    require(String.eq(text, "Map"), "QVariant argument changed")
    inspect_list(list)
    Qt.QObject.setObjectName(probe, "received")

def failed(state: Unit, button: Qt.QPushButton, color: Qt.QColor,
    values: List<&2, Qt.PairValue<String, Qt.QVariant>>, variant: Qt.QVariant,
    list: List<&2, Qt.QVariant>) -> Qt.Action(Unit):
  Qt.Action.fail(Unit, 47, "Intentional native argument handler failure")

def emitted(+object: Qt.QObject, +button: Qt.QPushButton, color: Qt.QColor, +title: Qt.QVariant, +count: Qt.QVariant) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Signal.emit(~nativeValues(), object, button, color,
      [Qt.PairValue{"count", count}, Qt.PairValue{"title", title}], title, [count])
    text: String <- Qt.QPushButton.text(button)
    require(String.eq(text, "typed"), "Handler lost the QPushButton type or identity")
    expired: Bool <- Qt.CallbackProbe.nativeSavedVariantExpired()
    require(expired, "Native argument copies outlived their callback scope")

def emit_values(+object: Qt.QObject, button: Qt.QPushButton) -> Qt.Action(Unit):
  Qt.QColor.with(Unit, Qt.QColor.new__String("red"), color =>
    Qt.QVariant.with(Unit, Qt.QVariant.fromString("Map"), title =>
      Qt.QVariant.with(Unit, Qt.QVariant.fromInt32(Qt.Int32{42}),
        count => emitted(object, button, color, title, count))))

def failed_emit(+object: Qt.QObject, button: Qt.QPushButton) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    result: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, emit_values(object, button))
    expect_error(Unit, result, 47)

def nullable(probe: Qt.QObject, button: Qt.QPushButton) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    require(U32.is_eq(Qt.QPushButton.word(button), 0), "Null QObject argument was lost")
    Qt.QObject.setObjectName(probe, "null")

def rejected(+object: Qt.QObject, +probe: Qt.QObject, +button: Qt.QPushButton) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    wrong: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit,
      Qt.Signal.emit(~buttonReady(), object, Qt.QPushButton{Qt.QObject.word(probe)}))
    expect_error(Unit, wrong, 22)
    Qt.QPushButton.destroy(button)
    stale: Result<&1, &1, U32 &String, Unit> <- Qt.Action.attempt(Unit, Qt.Signal.emit(~buttonReady(), object, button))
    expect_error(Unit, stale, 116)

def forbidden(state: Unit, button: Qt.QPushButton) -> Qt.Action(Unit):
  Qt.Action.fail(Unit, 99, "Queued deleted QObject reached a Bend handler")

def queued_deleted(+object: Qt.QObject, nested: Bool) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    result: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit,
      Qt.CallbackProbe.nativeSignalDeletedArgument(object, nested))
    expect_error(Unit, result, 116)

def connected(+object: Qt.QObject, +probe: Qt.QObject, +button: Qt.QPushButton) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    emit_values(object, button)
    Qt.CallbackProbe.nativeSignalFromWorker(object, button)
    interop: Bool <- Qt.CallbackProbe.nativeSignalInterop(object, button)
    require(interop, "Typed Qt slot or QML QObject/map conversion failed")
    Qt.CallbackProbe.nativeSignalQueuedDisconnect(object, button)

def native_demo(+object: Qt.QObject, +probe: Qt.QObject, +button: Qt.QPushButton) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Connection.with(Unit, Qt.Signal.connect(~nativeValues(), ~Qt.QObject, ~received, object, probe),
      connection => do Qt.Action<Unit>:
        Qt.CallbackProbe.customRememberConnection(connection)
        connected(object, probe, button))
    Qt.Connection.with(Unit, Qt.Signal.connect(~nativeValues(), ~Unit, ~failed, object, Unit{}),
      connection => failed_emit(object, button))
    Qt.Connection.with(Unit, Qt.Signal.connect(~buttonReady(), ~Qt.QObject, ~nullable, object, probe),
      connection => Qt.Signal.emit(~buttonReady(), object, Qt.QPushButton{0}))
    null_label: String <- Qt.QObject.objectName(probe)
    require(String.eq(null_label, "null"), "Null QObject argument handler did not run")
    Qt.Connection.with(Unit, Qt.Signal.connect(~buttonReady(), ~Unit, ~forbidden, object, Unit{}),
      connection => queued_deleted(object, False{}))
    Qt.Connection.with(Unit, Qt.Signal.connect(~nativeValues(), ~Unit, ~failed, object, Unit{}),
      connection => queued_deleted(object, True{}))
    rejected(object, probe, button)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QObject.with(Unit, Qt.QObject.new(), probe =>
      Qt.QPushButton.with(Unit, Qt.QPushButton.new(), button =>
        Qt.QObject.with(Unit, Qt.QObject.newWithSignals("NativeArguments", [nativeValues(), buttonReady()]),
          object => native_demo(object, probe, button))))
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Native signal arguments leaked objects or connections")
    Qt.Action.lift(Unit, IO.print("QT612_NATIVE_SIGNAL_ARGUMENTS_OK typed=1 class_check=1 null=1 maps=1 variants=1 queued=1 qml=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
