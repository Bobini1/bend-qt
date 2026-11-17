import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, "Pooled effect transport changed a value")

def invalid(~A: Type, value: Result<&1, &1, U32 & String, A>) -> Qt.Action(Unit):
  match value:
    case Fail{(code, message)}: require(U32.is_eq(code, 22))
    case Done{value}: Qt.Action.fail(Unit, 1, "Malformed raw layout reached native code")

def wire_ok(value: Qt.Wire) -> Bool:
  match value:
    case Qt.WireSequence{Qt.WireScalar{42, 3} <> Qt.WireText{text} <> Nil{}}: String.eq(text, "bytes\0λ")
    case _: False{}

def deep(depth: Nat) -> Qt.Wire:
  match depth:
    case 0n: Qt.WireScalar{0, 0}
    case 1n+n: Qt.WireSequence{[deep(n)]}

def wide_ok(value: Qt.UInt64) -> Bool:
  match value:
    case Qt.UInt64{lo, hi}: U32.is_eq(lo, 4294967295) && U32.is_eq(hi, 123)

def malformed() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    before: U32 <- Qt.Probe.calls()
    wrong_args: Result<&1, &1, U32 & String, U32> <- Qt.Action.attempt(U32, Qt.raw_Qt_s_to_word(10, 0, "wrong"))
    invalid(U32, wrong_args)
    missing_args: Result<&1, &1, U32 & String, U32> <- Qt.Action.attempt(U32, Qt.raw_Qt_none_to_word(10, 0))
    invalid(U32, missing_args)
    wrong_return: Result<&1, &1, U32 & String, U32> <- Qt.Action.attempt(U32, Qt.raw_Qt_none_to_word(16, 0))
    invalid(U32, wrong_return)
    wrong_self: Result<&1, &1, U32 & String, U32> <- Qt.Action.attempt(U32, Qt.raw_Qt_w_to_word(10, 9, 1))
    invalid(U32, wrong_self)
    unknown: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.raw_Qt_none_to_unit(4294967295, 0))
    invalid(Unit, unknown)
    excessive: Result<&1, &1, U32 & String, Qt.Wire> <- Qt.Action.attempt(Qt.Wire, Qt.Probe.wire(deep(130n)))
    invalid(Qt.Wire, excessive)
    after: U32 <- Qt.Probe.calls()
    require(U32.is_eq(before, after))

# Qt runs the handler during Probe.handled; the handler itself calls Qt.
def offset(base: U32, value: U32) -> Qt.Action(Unit):
  Qt.Probe.store(U32.add(base, value))

def refuse(code: U32, value: U32) -> Qt.Action(Unit):
  Qt.Action.fail(Unit, code, "handler refused")

def handler_failed(result: Result<&1, &1, U32 & String, Unit>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 44) && String.eq(message, "handler refused"))
    case Done{value}: Qt.Action.fail(Unit, 1, "A failed handler did not fail its Qt call")

def handlers() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Probe.handled(~U32, ~offset, 100, 23)
    stored: U32 <- Qt.Probe.stored()
    require(U32.is_eq(stored, 123))
    refused: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.Probe.handled(~U32, ~refuse, 44, 0))
    handler_failed(refused)

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    a: U32 <- Qt.Probe.add(40)
    b: U32 <- Qt.Probe.addAlias(41)
    c: U32 <- Qt.Probe.addTwo(40)
    require(U32.is_eq(a, 41) && U32.is_eq(b, 42) && U32.is_eq(c, 42))
    text: String <- Qt.Probe.text("native\0text")
    require(String.eq(text, "native\0text λ"))
    length: U32 <- Qt.Probe.textLength("λ")
    require(U32.is_eq(length, 1))
    wide: Qt.UInt64 <- Qt.Probe.wide(Qt.UInt64{123, 4294967295})
    require(wide_ok(wide))
    wire: Qt.Wire <- Qt.Probe.wire(Qt.WireSequence{[Qt.WireScalar{42, 3}, Qt.WireText{"bytes\0λ"}]})
    require(wire_ok(wire))
    receiver: U32 <- Qt.Probe.receiver(91)
    require(U32.is_eq(receiver, 91))
    Qt.Probe.unit()
    handlers()
    malformed()
    Qt.Action.lift(Unit, IO.print("QT612_EFFECT_TRANSPORT_OK alias=1 shapes=1 handlers=1 rejected_before_native=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
