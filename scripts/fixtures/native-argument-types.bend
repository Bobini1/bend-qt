import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, text: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, text)

def rejected(result: Result<&1, &1, U32 & String, Unit>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, text)}: require(U32.is_eq(code, 34), text)
    case Done{value}: Qt.Action.fail(Unit, 1, "Native narrow integer was truncated")

def expected(-A: Type, result: Result<&1, &1, U32 & String, A>, code: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(actual, text)}: require(U32.is_eq(actual, code), text)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected native argument rejection")

def numbers() -> Qt.Signal:
  Qt.Signal.define("numbers", [Qt.int8(), Qt.u8(), Qt.int16(), Qt.u16(), Qt.int64(), Qt.u64(),
    Qt.f32(), Qt.f64(), Qt.Qt.DayOfWeek.arg(), Qt.Flags_Qt__AlignmentFlag.arg(), Qt.QCborTag.arg(), Qt.qchar(), Qt.nullptr()])

def received(probe: Qt.QObject, signed8: Qt.Int32, unsigned8: U32, signed16: Qt.Int32, unsigned16: U32,
  signed64: Qt.Int64, unsigned64: Qt.UInt64, single: Qt.F64, real: Qt.F64,
  day: Qt.Qt.DayOfWeek, alignment: Qt.Flags_Qt__AlignmentFlag, tag: Qt.QCborTag, character: U32, empty: Unit) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +signed: Qt.Int64 = signed64
    +unsigned: Qt.UInt64 = unsigned64
    +rounded: Qt.F64 = single
    +exact: Qt.F64 = real
    +wide_enum: Qt.QCborTag = tag
    require(U32.is_eq(Qt.Int32.word(signed8), 4294967168) && U32.is_eq(unsigned8, 255), "8-bit native signal values changed")
    require(U32.is_eq(Qt.Int32.word(signed16), 4294934528) && U32.is_eq(unsigned16, 65535), "16-bit native signal values changed")
    require(U32.is_eq(Qt.Int64.lo(signed), 1) && U32.is_eq(Qt.Int64.hi(signed), 2147483648), "Signed 64-bit signal lost bits")
    require(U32.is_eq(Qt.UInt64.lo(unsigned), 4294967295) && U32.is_eq(Qt.UInt64.hi(unsigned), 4294967295), "Unsigned 64-bit signal lost bits")
    require(U32.is_eq(Qt.F64.lo(rounded), 0) && U32.is_eq(Qt.F64.hi(rounded), 1072955392), "Float signal changed")
    require(U32.is_eq(Qt.F64.lo(exact), 1) && U32.is_eq(Qt.F64.hi(exact), 1072693248), "Double signal lost precision")
    require(U32.is_eq(Qt.Qt.DayOfWeek.word(day), 1) && U32.is_eq(Qt.Flags_Qt__AlignmentFlag.word(alignment), 3), "Enum or flags native signal changed")
    require(U32.is_eq(Qt.QCborTag.lo(wide_enum), 7) && U32.is_eq(Qt.QCborTag.hi(wide_enum), 1), "64-bit native enum signal was truncated")
    require(U32.is_eq(character, 955), "Native QChar signal changed its UTF-16 code unit")
    Qt.QObject.setObjectName(probe, "numbers")

def emit_payload(object: Qt.QObject, character: U32) -> Qt.Action(Unit):
  Qt.Signal.emit(~numbers(), object, Qt.Int32.neg(128), 255, Qt.Int32.neg(32768), 65535,
    Qt.Int64{1, 2147483648}, Qt.UInt64{4294967295, 4294967295}, Qt.F64{0, 1072955392},
    Qt.F64{1, 1072693248}, Qt.Qt.DayOfWeek.Monday(), Qt.Flags_Qt__AlignmentFlag{3}, Qt.QCborTag{7, 1}, character, Unit{})

def emit_numbers(+object: Qt.QObject, +probe: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    connection: Qt.Connection <- Qt.Signal.connect(~numbers(), ~Qt.QObject, ~received, object, probe)
    emit_payload(object, 955)
    invalid: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, emit_payload(object, 65536))
    rejected(invalid)
    text: String <- Qt.QObject.objectName(probe)
    require(String.eq(text, "numbers"), "Native argument handler did not execute")

def byte() -> Qt.Property:
  Qt.Property.define("byte", Qt.int8())

def small() -> Qt.Property:
  Qt.Property.define("small", Qt.u16())

def wide() -> Qt.Property:
  Qt.Property.define("wide", Qt.int64())

def precise() -> Qt.Property:
  Qt.Property.define("precise", Qt.f32())

def day() -> Qt.Property:
  Qt.Property.define("day", Qt.Qt.DayOfWeek.arg())

def alignment() -> Qt.Property:
  Qt.Property.define("alignment", Qt.Flags_Qt__AlignmentFlag.arg())

def items() -> Qt.Property:
  Qt.Property.define("items", Qt.list(~Qt.int32()))

def labels() -> Qt.Property:
  Qt.Property.define("labels", Qt.list(~Qt.string()))

def mapping() -> Qt.Property:
  Qt.Property.define("mapping", Qt.map(~Qt.string(), ~Qt.variant()))

def character() -> Qt.Property:
  Qt.Property.define("character", Qt.QChar.arg())

def empty() -> Qt.Property:
  Qt.Property.define("empty", Qt.nullptr())

def Settings() -> Qt.QtObject:
  Qt.QObject.define("NativeArgumentSettings", [byte(), small(), wide(), precise(), day(), alignment(), items(), labels(), mapping(), character(), empty()])

def inspect_items(values: List<&2, Qt.Int32>) -> Qt.Action(Unit):
  match values:
    case one <> two <> Nil{}:
      require(U32.is_eq(Qt.Int32.word(one), 1) && U32.is_eq(Qt.Int32.word(two), 2), "Native QList<int> changed")
    case _: Qt.Action.fail(Unit, 1, "Native QList<int> has the wrong shape")

def inspect_labels(values: List<&2, String>) -> Qt.Action(Unit):
  match values:
    case label <> Nil{}: require(String.eq(label, "Bend"), "QStringList alias changed")
    case _: Qt.Action.fail(Unit, 1, "QStringList has the wrong shape")

def inspect_mapping(values: List<&2, Qt.PairValue<String, Qt.QVariant>>) -> Qt.Action(Unit):
  match values:
    case Qt.PairValue{key, value} <> Nil{}:
      do Qt.Action<Unit>:
        text: String <- Qt.QVariant.toString(value)
        require(String.eq(key, "language") && String.eq(text, "Bend"), "Native typed map changed")
    case _: Qt.Action.fail(Unit, 1, "Native typed map has the wrong shape")

def native_name(value: Maybe<&2, String>, expected: String) -> Qt.Action(Unit):
  match value:
    case Some{name}: require(String.eq(name, expected), "Native argument QVariant metatype changed")
    case None{}: Qt.Action.fail(Unit, 1, "Native argument QVariant has no metatype name")

def variant_type(value: Qt.QVariant, expected: String) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    meta: Qt.QMetaType <- Qt.QVariant.metaType(value)
    name: Maybe<&2, String> <- Qt.QMetaType.name(meta)
    native_name(name, expected)

def property_cases(+self: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Property.set(~empty(), self, Unit{})
    empty_value: Unit <- Qt.Property.get(~empty(), self)
    +boxed_empty: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.nullptr(), Unit{})
    empty_value: Unit <- Qt.QVariant.toValue(~Qt.nullptr(), boxed_empty)
    valid_empty: Bool <- Qt.QVariant.isValid(boxed_empty)
    null_empty: Bool <- Qt.QVariant.isNull(boxed_empty)
    require(valid_empty && null_empty, "Native nullptr QVariant must be a valid null value")
    variant_type(boxed_empty, "std::nullptr_t")
    Qt.Property.set(~character(), self, 955)
    unit: U32 <- Qt.Property.get(~character(), self)
    require(U32.is_eq(unit, 955), "Native QChar property changed its UTF-16 code unit")
    invalid: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.Property.set(~character(), self, 65536))
    rejected(invalid)
    +boxed_character: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.qchar(), 955)
    variant_type(boxed_character, "QChar")
    unit: U32 <- Qt.QVariant.toValue(~Qt.QChar.arg(), boxed_character)
    require(U32.is_eq(unit, 955), "QChar QVariant changed its UTF-16 code unit")
    invalid_box: Result<&1, &1, U32 & String, Qt.QVariant> <- Qt.Action.attempt(Qt.QVariant, Qt.QVariant.fromValue(~Qt.qchar(), 65536))
    expected(Qt.QVariant, invalid_box, 34)
    wrong: Result<&1, &1, U32 & String, U32> <- Qt.Action.attempt(U32, Qt.QVariant.toValue(~Qt.char16(), boxed_character))
    expected(U32, wrong, 22)
    Qt.Property.set(~byte(), self, Qt.Int32.neg(128))
    number: Qt.Int32 <- Qt.Property.get(~byte(), self)
    require(U32.is_eq(Qt.Int32.word(number), 4294967168), "Signed byte property changed")
    invalid: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.Property.set(~byte(), self, Qt.Int32{128}))
    rejected(invalid)
    Qt.Property.set(~small(), self, 65535)
    number: U32 <- Qt.Property.get(~small(), self)
    require(U32.is_eq(number, 65535), "Unsigned short property changed")
    invalid: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.Property.set(~small(), self, 65536))
    rejected(invalid)
    Qt.Property.set(~wide(), self, Qt.Int64{7, 1})
    +number: Qt.Int64 <- Qt.Property.get(~wide(), self)
    require(U32.is_eq(Qt.Int64.lo(number), 7) && U32.is_eq(Qt.Int64.hi(number), 1), "64-bit property lost bits")
    Qt.Property.set(~precise(), self, Qt.F64{0, 1072955392})
    +number: Qt.F64 <- Qt.Property.get(~precise(), self)
    require(U32.is_eq(Qt.F64.lo(number), 0) && U32.is_eq(Qt.F64.hi(number), 1072955392), "Float property changed")
    Qt.Property.set(~day(), self, Qt.Qt.DayOfWeek.Monday())
    value: Qt.Qt.DayOfWeek <- Qt.Property.get(~day(), self)
    require(U32.is_eq(Qt.Qt.DayOfWeek.word(value), 1), "Native enum property changed")
    Qt.Property.set(~alignment(), self, Qt.Flags_Qt__AlignmentFlag{3})
    flags: Qt.Flags_Qt__AlignmentFlag <- Qt.Property.get(~alignment(), self)
    require(U32.is_eq(Qt.Flags_Qt__AlignmentFlag.word(flags), 3), "Native QFlags property changed")
    Qt.Property.set(~items(), self, [Qt.Int32{1}, Qt.Int32{2}])
    values: List<&2, Qt.Int32> <- Qt.Property.get(~items(), self)
    inspect_items(values)
    Qt.Property.set(~labels(), self, ["Bend"])
    text_values: List<&2, String> <- Qt.Property.get(~labels(), self)
    inspect_labels(text_values)
    +boxed_labels: Qt.QVariant <- Qt.QVariant.fromValue(~Qt.list(~Qt.string()), ["Bend"])
    variant_type(boxed_labels, "QStringList")
    text_values: List<&2, String> <- Qt.QVariant.toValue(~Qt.list(~Qt.string()), boxed_labels)
    inspect_labels(text_values)
    value: Qt.QVariant <- Qt.QVariant.fromString("Bend")
    Qt.Property.set(~mapping(), self, [Qt.PairValue{"language", value}])
    entries: List<&2, Qt.PairValue<String, Qt.QVariant>> <- Qt.Property.get(~mapping(), self)
    inspect_mapping(entries)

def clicked() -> Qt.Signal:
  Qt.Signal.define("clicked", [Qt.bool()])

def on_clicked(probe: Qt.QObject, checked: Bool) -> Qt.Action(Unit):
  Qt.QObject.setObjectName(probe, "native signal")

def native_emission(+button: Qt.QPushButton, +probe: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    connection: Qt.Connection <- Qt.QPushButton.connect_clicked(~Qt.QObject, ~on_clicked, button, probe)
    Qt.Signal.emit(~clicked(), Qt.QPushButton.as_QObject(button), True{})
    text: String <- Qt.QObject.objectName(probe)
    require(String.eq(text, "native signal"), "Emitting a native QObject signal failed")

def objects() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +probe: Qt.QObject <- Qt.QObject.new()
    object: Qt.QObject <- Qt.QObject.newWithSignals("NativeNumericSignals", [numbers()])
    emit_numbers(object, probe)
    settings: Qt.QtObject.Instance(Settings()) <- Qt.QtObject.new(~Settings())
    property_cases(Qt.QtObject.as_QObject(~Settings(), settings))
    button: Qt.QPushButton <- Qt.QPushButton.new()
    native_emission(button, probe)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, objects())
    objects: U32 <- Qt.Runtime.liveObjects()
    connections: U32 <- Qt.Runtime.liveConnections()
    require(U32.is_eq(objects, 0) && U32.is_eq(connections, 0), "Native argument types leaked resources")
    Qt.Action.lift(Unit, IO.print("QT612_NATIVE_ARGUMENT_TYPES_OK numeric=1 enum=1 flags=1 containers=1 native_emit=1 bounds=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
