import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def present(expected: U32, value: Maybe<&2, Qt.UInt64>) -> Qt.Action(Unit):
  match value:
    case Some{+word}: require(U32.is_eq(Qt.UInt64.lo(word), expected) && U32.is_eq(Qt.UInt64.hi(word), 0), "Optional changed its 64-bit value")
    case None{}: Qt.Action.fail(Unit, 1, "Present Qt optional became absent")

def absent(value: Maybe<&2, Qt.UInt64>) -> Qt.Action(Unit):
  match value:
    case None{}: Qt.Action.pure(Unit, Unit{})
    case Some{word}: Qt.Action.fail(Unit, 1, "Absent Qt optional became present")

def orientation(+value: Qt.QMetaEnum) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    horizontal: Maybe<&2, Qt.UInt64> <- Qt.QMetaEnum.keyToValue64(value, "Horizontal")
    present(1, horizontal)
    missing: Maybe<&2, Qt.UInt64> <- Qt.QMetaEnum.keyToValue64(value, "not_a_Qt_enum_key")
    absent(missing)
    invalid_index: Maybe<&2, Qt.UInt64> <- Qt.QMetaEnum.value64(value, Qt.Int32.neg(1))
    absent(invalid_index)

def zero(value: Qt.QMetaEnum) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    result: Maybe<&2, Qt.UInt64> <- Qt.QMetaEnum.keyToValue64(value, "Widget")
    present(0, result)

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QMetaEnum.with(Unit, Qt.QMetaEnum.fromQtName("Orientation"), value => orientation(value))
    Qt.QMetaEnum.with(Unit, Qt.QMetaEnum.fromQtName("WindowType"), zero)
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "Optional conversion leaked native handles")
    Qt.Action.lift(Unit, IO.print("QT612_OPTIONAL_OK present=1 absent=1 zero_present=1 invalid_index=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
