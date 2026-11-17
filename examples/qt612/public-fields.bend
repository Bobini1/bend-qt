import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def rejected(result: Result<&1, &1, U32 & String, Unit>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 22), "Wrong fixed-array field error: " ++ message)
    case Done{unit}: Qt.Action.fail(Unit, 1, "Wrong fixed-array field size was accepted")

def read_width(value: Qt.QRect) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    width: Qt.Int32 <- Qt.QRect.width(value)
    require(U32.is_eq(Qt.Int32.word(width), 100), "A public field value was aliased instead of copied")

def source_rectangle(+option: Qt.QStyleOptionButton, +rectangle: Qt.QRect) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QStyleOptionButton.Fields.set_rect(option, rectangle)
    Qt.QRect.setWidth(rectangle, Qt.Int32{999})
    Qt.QRect.with(Unit, Qt.QStyleOptionButton.Fields.rect(option), read_width)
    Qt.QRect.with(Unit, Qt.QStyleOptionButton.Fields.rect(option), copy => Qt.QRect.setWidth(copy, Qt.Int32{333}))
    Qt.QRect.with(Unit, Qt.QStyleOptionButton.Fields.rect(option), read_width)

def option_case(+option: Qt.QStyleOptionButton) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QStyleOptionButton.Fields.set_text(option, "Public field text 🎵")
    text: String <- Qt.QStyleOptionButton.Fields.text(option)
    require(String.eq(text, "Public field text 🎵"), "QString field did not round trip")
    Qt.QStyleOptionButton.Fields.set_state(option, Qt.Flags_QStyle__StateFlag{1})
    state: Qt.Flags_QStyle__StateFlag <- Qt.QStyleOptionButton.Fields.state(option)
    require(U32.is_eq(Qt.Flags_QStyle__StateFlag.word(state), 1), "Inherited flags field did not round trip")
    Qt.QStyleOptionButton.Fields.set_version(option, Qt.Int32{42})
    version: Qt.Int32 <- Qt.QStyleOptionButton.Fields.version(option)
    require(U32.is_eq(Qt.Int32.word(version), 42), "Inherited primitive field did not round trip")
    Qt.QRect.with(Unit, Qt.QRect.new__Int32_Int32_Int32_Int32(Qt.Int32{0}, Qt.Int32{0}, Qt.Int32{100}, Qt.Int32{50}), rectangle => source_rectangle(option, rectangle))

def array_case(+parameters: Qt.QProcess.UnixProcessParameters) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    # The header reserves these words. Keep their required zero values; this
    # fixture exercises only the generated fixed-array shape and copy policy.
    Qt.QProcess.UnixProcessParameters.Fields.set__reserved(parameters, [0, 0, 0, 0, 0, 0])
    values: List<&2, U32> <- Qt.QProcess.UnixProcessParameters.Fields._reserved(parameters)
    require(U32.is_eq(U32.from_nat(List.length(&2, U32, values)), 6), "Fixed-array field getter lost its shape")
    wrong: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QProcess.UnixProcessParameters.Fields.set__reserved(parameters, [0]))
    rejected(wrong)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QStyleOptionButton.with(Unit, Qt.QStyleOptionButton.new(), option => option_case(option))
    Qt.QProcess.UnixProcessParameters.with(Unit, Qt.QProcess.UnixProcessParameters.new(), parameters => array_case(parameters))
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Public field copies leaked handles")
    Qt.Action.lift(Unit, IO.print("QT612_PUBLIC_FIELDS_OK inherited=1 scalar=1 flags=1 string=1 value_copies=1 fixed_array=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
