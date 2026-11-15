import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def output_value(present: Maybe<&2, Qt.Int32>, value: U32) -> Maybe<&2, Qt.Int32>:
  match present:
    case Some{old}: Some{Qt.Int32{value}}
    case None{}: None{}

# Outputs keep Qt's null pointers null.
def attributes(state: Unit, offset: Qt.Int32, start: Maybe<&2, Qt.Int32>, end: Maybe<&2, Qt.Int32>) -> Qt.Action(Qt.CallbackReply_String_Optional_Int32_Optional_Int32):
  Qt.Action.pure(Qt.CallbackReply_String_Optional_Int32_Optional_Int32, Qt.CallbackReply_String_Optional_Int32_Optional_Int32{"weight:bold", output_value(start, 2), output_value(end, 9)})

# Index 99 answers outputs Qt did not ask for, so the whole reply is rejected.
def selection_reply(index: U32, start: Maybe<&2, Qt.Int32>, end: Maybe<&2, Qt.Int32>) -> Qt.CallbackReply_Optional_Int32_Optional_Int32:
  match index:
    case 99: Qt.CallbackReply_Optional_Int32_Optional_Int32{Some{Qt.Int32{1}}, Some{Qt.Int32{4}}}
    case _: Qt.CallbackReply_Optional_Int32_Optional_Int32{output_value(start, 1), output_value(end, 4)}

def selection(state: Unit, index: Qt.Int32, start: Maybe<&2, Qt.Int32>, end: Maybe<&2, Qt.Int32>) -> Qt.Action(Qt.CallbackReply_Optional_Int32_Optional_Int32):
  Qt.Action.pure(Qt.CallbackReply_Optional_Int32_Optional_Int32, selection_reply(Qt.Int32.word(index), start, end))

# Each answer is two new interfaces; the selection interface retains them.
def items(invalid: Bool) -> Qt.Action(List<&2, Qt.QAccessibleInterface>):
  match invalid:
    case True{}:
      do Qt.Action<List<&2, Qt.QAccessibleInterface>>:
        first: Qt.QAccessibleInterface <- Qt.QAccessibleInterface.newOverride()
        return first <> Qt.QAccessibleInterface{4294967295} <> Nil{}
    case False{}:
      do Qt.Action<List<&2, Qt.QAccessibleInterface>>:
        first: Qt.QAccessibleInterface <- Qt.QAccessibleInterface.newOverride()
        second: Qt.QAccessibleInterface <- Qt.QAccessibleInterface.newOverride()
        return first <> second <> Nil{}

def rejected(expected: U32, result: Result<&1, &1, U32 & String, U32>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong accessible reply rejection: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "A malformed accessibility reply was accepted")

def text_demo(+text: Qt.QAccessibleTextInterface) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QAccessibleTextInterface.Virtual.attributes.handle(~Unit, ~attributes, text, Unit{})
    Qt.QAccessibleTextInterface.Virtual.selection.handle(~Unit, ~selection, text, Unit{})
    +answered: Qt.Outputs_String_Int32_Int32 <- Qt.QAccessibleTextInterface.attributes(text, Qt.Int32{3})
    require(String.eq(Qt.Outputs_String_Int32_Int32.arg0(answered), "weight:bold"), "Forward attributes lost the handler string")
    require(U32.is_eq(Qt.Int32.word(Qt.Outputs_String_Int32_Int32.arg1(answered)), 2), "Forward attributes lost the first output")
    require(U32.is_eq(Qt.Int32.word(Qt.Outputs_String_Int32_Int32.arg2(answered)), 9), "Forward attributes lost the second output")
    +selected: Qt.Outputs_Int32_Int32 <- Qt.QAccessibleTextInterface.selection(text, Qt.Int32{0})
    require(U32.is_eq(Qt.Int32.word(Qt.Outputs_Int32_Int32.arg0(selected)), 1), "Forward selection lost its start")
    require(U32.is_eq(Qt.Int32.word(Qt.Outputs_Int32_Int32.arg1(selected)), 4), "Forward selection lost its end")
    valid: U32 <- Qt.CallbackProbe.accessibleText(text, 0)
    require(U32.is_eq(valid, 1), "Scalar outputs were not written")
    invalid: Result<&1, &1, U32 & String, U32> <- Qt.Action.attempt(U32, Qt.CallbackProbe.accessibleText(text, 1))
    rejected(22, invalid)

def list_demo(+selection: Qt.QAccessibleSelectionInterface) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QAccessibleSelectionInterface.Virtual.selectedItems.handle(~Bool, ~items, selection, False{})
    valid: U32 <- Qt.CallbackProbe.accessibleItems(selection)
    require(U32.is_eq(valid, 1), "Pointer list results did not survive the native calls")
    retained: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(retained, 4), "Every distinct pointer result must stay retained")

def list_rejected(+selection: Qt.QAccessibleSelectionInterface) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QAccessibleSelectionInterface.Virtual.selectedItems.handle(~Bool, ~items, selection, True{})
    invalid: Result<&1, &1, U32 & String, U32> <- Qt.Action.attempt(U32, Qt.CallbackProbe.accessibleItems(selection))
    rejected(116, invalid)
    retained: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(retained, 0), "A malformed pointer list retained some elements")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QAccessibleTextInterface.with(Unit, Qt.QAccessibleTextInterface.newOverride(), text => text_demo(text))
    Qt.QAccessibleSelectionInterface.with(Unit, Qt.QAccessibleSelectionInterface.newOverride(), selection => list_demo(selection))
    Qt.QAccessibleSelectionInterface.with(Unit, Qt.QAccessibleSelectionInterface.newOverride(), selection => list_rejected(selection))
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Accessibility handlers leaked native handles")
    Qt.Action.lift(Unit, IO.print("QT612_ACCESSIBLE_CALLBACKS_OK scalar_outputs=1 null_preserved=1 atomic_rejection=1 retained_pointer_lists=1 protected_destructor=1 malformed_list_rejected=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
