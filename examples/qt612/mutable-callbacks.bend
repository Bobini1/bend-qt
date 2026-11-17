import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expect_error(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Unexpected handler error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected handler failure")

# validate takes the text and position by reference. The reply holds the
# result and the new values of both.
def validate(state: Unit, text: String, position: Qt.Int32) -> Qt.Action(Qt.CallbackReply_QValidator_State_String_Int32):
  Qt.Action.pure(Qt.CallbackReply_QValidator_State_String_Int32,
    Qt.CallbackReply_QValidator_State_String_Int32{Qt.QValidator.State.Acceptable(), text ++ " changed by Bend", Qt.Int32{(Qt.Int32.word(position) + 8 : U32)}})

def refuse(code: U32, text: String, position: Qt.Int32) -> Qt.Action(Qt.CallbackReply_QValidator_State_String_Int32):
  Qt.Action.fail(Qt.CallbackReply_QValidator_State_String_Int32, code, "Intentional validator failure")

def inspect(result: Qt.Outputs_QValidator_State_String_Int32) -> Qt.Action(Unit):
  match result:
    case Qt.Outputs_QValidator_State_String_Int32{state, text, position}:
      require(U32.is_eq(Qt.QValidator.State.word(state), Qt.QValidator.State.word(Qt.QValidator.State.Acceptable())) && String.eq(text, "input changed by Bend") && U32.is_eq(Qt.Int32.word(position), 9), "Reference outputs were not committed")

def run_validator(+validator: Qt.QValidator) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QValidator.Virtual.validate.handle(~Unit, ~validate, validator, Unit{})
    result: Qt.Outputs_QValidator_State_String_Int32 <- Qt.QValidator.validate(validator, "input", Qt.Int32{1})
    inspect(result)
    Qt.QValidator.Virtual.validate.handle(~U32, ~refuse, validator, 45)
    failed: Result<&1, &1, U32 & String, Qt.Outputs_QValidator_State_String_Int32> <- Qt.Action.attempt(Qt.Outputs_QValidator_State_String_Int32, Qt.QValidator.validate(validator, "input", Qt.Int32{1}))
    expect_error(Qt.Outputs_QValidator_State_String_Int32, failed, 45)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QValidator.with(Unit, Qt.QValidator.newOverride(), validator => run_validator(validator))
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Validator handler test leaked objects")
    Qt.Action.lift(Unit, IO.print("QT612_MUTABLE_CALLBACKS_OK abstract_validator=1 return=1 string_ref=1 integer_ref=1 handler_failure=1 objects=0 connections=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
