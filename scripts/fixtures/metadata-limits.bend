import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def arguments(count: Nat) -> List<&1, Qt.TypeDescriptor>:
  match count:
    case 0n: Nil{}
    case 1n+rest: Qt.int32() <> arguments(rest)

def large_signal() -> Qt.Signal:
  Qt.Signal.define("manyArguments", arguments(65n))

def received(probe: Qt.QObject, arg0: Qt.Int32, arg1: Qt.Int32, arg2: Qt.Int32, arg3: Qt.Int32, arg4: Qt.Int32, arg5: Qt.Int32, arg6: Qt.Int32, arg7: Qt.Int32, arg8: Qt.Int32, arg9: Qt.Int32, arg10: Qt.Int32, arg11: Qt.Int32, arg12: Qt.Int32, arg13: Qt.Int32, arg14: Qt.Int32, arg15: Qt.Int32, arg16: Qt.Int32, arg17: Qt.Int32, arg18: Qt.Int32, arg19: Qt.Int32, arg20: Qt.Int32, arg21: Qt.Int32, arg22: Qt.Int32, arg23: Qt.Int32, arg24: Qt.Int32, arg25: Qt.Int32, arg26: Qt.Int32, arg27: Qt.Int32, arg28: Qt.Int32, arg29: Qt.Int32, arg30: Qt.Int32, arg31: Qt.Int32, arg32: Qt.Int32, arg33: Qt.Int32, arg34: Qt.Int32, arg35: Qt.Int32, arg36: Qt.Int32, arg37: Qt.Int32, arg38: Qt.Int32, arg39: Qt.Int32, arg40: Qt.Int32, arg41: Qt.Int32, arg42: Qt.Int32, arg43: Qt.Int32, arg44: Qt.Int32, arg45: Qt.Int32, arg46: Qt.Int32, arg47: Qt.Int32, arg48: Qt.Int32, arg49: Qt.Int32, arg50: Qt.Int32, arg51: Qt.Int32, arg52: Qt.Int32, arg53: Qt.Int32, arg54: Qt.Int32, arg55: Qt.Int32, arg56: Qt.Int32, arg57: Qt.Int32, arg58: Qt.Int32, arg59: Qt.Int32, arg60: Qt.Int32, arg61: Qt.Int32, arg62: Qt.Int32, arg63: Qt.Int32, arg64: Qt.Int32) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    require(U32.is_eq(Qt.Int32.word(arg0), 0) && U32.is_eq(Qt.Int32.word(arg64), 64), "Large signal arguments were truncated")
    Qt.QObject.setObjectName(probe, "65 arguments")

def properties(count: Nat, +index: U32) -> List<&1, Qt.Property>:
  match count:
    case 0n: Nil{}
    case 1n+rest: Qt.Property.define("p" ++ U32.show(index), Qt.int32()) <> properties(rest, U32.add(index, 1))

def Large() -> Qt.ObjectType:
  Qt.QObject.define("LargePropertySchema", properties(200n, 0))

def classes(remaining: Nat, +index: U32) -> Qt.Action(Unit):
  match remaining:
    case 0n: Qt.Action.pure(Unit, Unit{})
    case 1n+rest:
      do Qt.Action<Unit>:
        Qt.QObject.with(Unit, Qt.QObject.newWithSignals("MetadataClass" ++ U32.show(index), []),
          object => Qt.Action.pure(Unit, Unit{}))
        classes(rest, U32.add(index, 1))

def objects() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +object: Qt.QObject <- Qt.QObject.newWithSignals("LargeSignalSchema", [large_signal()])
    +probe: Qt.QObject <- Qt.QObject.new()
    connection: Qt.Connection <- Qt.Signal.connect(~large_signal(), ~Qt.QObject, ~received, object, probe)
    Qt.Signal.emit(~large_signal(), object, Qt.Int32{0}, Qt.Int32{1}, Qt.Int32{2}, Qt.Int32{3}, Qt.Int32{4}, Qt.Int32{5}, Qt.Int32{6}, Qt.Int32{7}, Qt.Int32{8}, Qt.Int32{9}, Qt.Int32{10}, Qt.Int32{11}, Qt.Int32{12}, Qt.Int32{13}, Qt.Int32{14}, Qt.Int32{15}, Qt.Int32{16}, Qt.Int32{17}, Qt.Int32{18}, Qt.Int32{19}, Qt.Int32{20}, Qt.Int32{21}, Qt.Int32{22}, Qt.Int32{23}, Qt.Int32{24}, Qt.Int32{25}, Qt.Int32{26}, Qt.Int32{27}, Qt.Int32{28}, Qt.Int32{29}, Qt.Int32{30}, Qt.Int32{31}, Qt.Int32{32}, Qt.Int32{33}, Qt.Int32{34}, Qt.Int32{35}, Qt.Int32{36}, Qt.Int32{37}, Qt.Int32{38}, Qt.Int32{39}, Qt.Int32{40}, Qt.Int32{41}, Qt.Int32{42}, Qt.Int32{43}, Qt.Int32{44}, Qt.Int32{45}, Qt.Int32{46}, Qt.Int32{47}, Qt.Int32{48}, Qt.Int32{49}, Qt.Int32{50}, Qt.Int32{51}, Qt.Int32{52}, Qt.Int32{53}, Qt.Int32{54}, Qt.Int32{55}, Qt.Int32{56}, Qt.Int32{57}, Qt.Int32{58}, Qt.Int32{59}, Qt.Int32{60}, Qt.Int32{61}, Qt.Int32{62}, Qt.Int32{63}, Qt.Int32{64})
    name: String <- Qt.QObject.objectName(probe)
    require(String.eq(name, "65 arguments"), "A signal with more than 64 arguments was not delivered")
    instance: Qt.ObjectType.Instance(Large()) <- Qt.ObjectType.new(~Large())
    +self: Qt.QObject = Qt.ObjectType.as_QObject(~Large(), instance)
    Qt.Property.set(~Qt.Property.define("p199", Qt.int32()), self, Qt.Int32{42})
    value: Qt.Int32 <- Qt.Property.get(~Qt.Property.define("p199", Qt.int32()), self)
    require(U32.is_eq(Qt.Int32.word(value), 42), "A schema with more than 128 properties failed")
    classes(1050n, 0)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, objects())
    live: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(live, 0), "Large metadata schemas leaked native objects")
    Qt.Action.lift(Unit, IO.print("QT612_METADATA_LIMITS_OK arguments=65 properties=200 class_schemas=1050 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
