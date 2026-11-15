type EnumEntry is Data:
  EnumEntry{name: String, lo: U32, hi: U32}

type Enum is Type:
  Enum{name: String, entries: List<&1, EnumEntry>, flags: U32, alias: String}

def Enum.key(name: String, value: U32) -> EnumEntry:
  EnumEntry{name, value, 0}

def Enum.signedKey(name: String, value: Int32) -> EnumEntry:
  +word: U32 = Int32.word(value)
  EnumEntry{name, word, U32.sub(0, U32.div(word, 2147483648))}

def Enum.wideKey(name: String, value: UInt64) -> EnumEntry:
  match value:
    case UInt64{lo, hi}: EnumEntry{name, lo, hi}

def Enum.signedWideKey(name: String, value: Int64) -> EnumEntry:
  match value:
    case Int64{lo, hi}: EnumEntry{name, lo, hi}

def Enum.define(name: String, entries: List<&1, EnumEntry>) -> Enum:
  Enum{name, entries, 2, ""}

def Enum.withFlag(enum: Enum, +flag: U32, enabled: Bool) -> Enum:
  match enum enabled:
    case Enum{name, entries, flags, alias} True{}: Enum{name, entries, U32.or(flags, flag), alias}
    case Enum{name, entries, flags, alias} False{}: Enum{name, entries, U32.and(flags, U32.sub(4294967295, flag)), alias}

def Enum.withFlags(enum: Enum, enabled: Bool) -> Enum:
  Enum.withFlag(enum, 1, enabled)

def Enum.withScoped(enum: Enum, enabled: Bool) -> Enum:
  Enum.withFlag(enum, 2, enabled)

def Enum.with64Bit(enum: Enum, enabled: Bool) -> Enum:
  Enum.withFlag(enum, 4, enabled)

def Enum.withUnsigned(enum: Enum, enabled: Bool) -> Enum:
  Enum.withFlag(enum, 8, enabled)

def Enum.withAlias(enum: Enum, alias: String) -> Enum:
  match enum:
    case Enum{name, entries, flags, previous}: Enum{name, entries, U32.or(flags, 1), alias}

def Enum.name(enum: Enum) -> String:
  match enum:
    case Enum{name, entries, flags, alias}: name

def Enum.entries(enum: Enum) -> List<&1, EnumEntry>:
  match enum:
    case Enum{name, entries, flags, alias}: entries

def Enum.entrySchemas(entries: List<&1, EnumEntry>) -> List<&2, Wire>:
  match entries:
    case Nil{}: Nil{}
    case EnumEntry{name, lo, hi} <> rest:
      WireSequence{[WireText{name}, WireScalar{lo, hi}]} <> Enum.entrySchemas(rest)

def Enum.schema(enum: Enum) -> Wire:
  match enum:
    case Enum{name, entries, flags, alias}:
      WireSequence{[WireText{"enum"}, WireText{name}, WireScalar{flags, 0}, WireText{alias}, WireSequence{Enum.entrySchemas(entries)}]}

def Enum.schemas(enums: List<&1, Enum>) -> List<&2, Wire>:
  match enums:
    case Nil{}: Nil{}
    case enum <> rest: Enum.schema(enum) <> Enum.schemas(rest)

type EnumValue<-Name: String> is Data:
  EnumValue{lo: U32, hi: U32}

def Enum.Value(-enum: Enum) -> Data:
  EnumValue<Enum.name(enum)>

def Enum.fromU32(~enum: Enum, lo: U32) -> Enum.Value(enum):
  EnumValue{lo, 0}

def Enum.fromInt32(~enum: Enum, value: Int32) -> Enum.Value(enum):
  +lo: U32 = Int32.word(value)
  EnumValue{lo, U32.sub(0, U32.div(lo, 2147483648))}

def Enum.fromU64(~enum: Enum, value: UInt64) -> Enum.Value(enum):
  match value:
    case UInt64{lo, hi}: EnumValue{lo, hi}

def Enum.fromInt64(~enum: Enum, value: Int64) -> Enum.Value(enum):
  match value:
    case Int64{lo, hi}: EnumValue{lo, hi}

def Enum.bits(~enum: Enum, value: Enum.Value(enum)) -> UInt64:
  match value:
    case EnumValue{lo, hi}: UInt64{lo, hi}

def Enum.signed(~enum: Enum, value: Enum.Value(enum)) -> Int64:
  match value:
    case EnumValue{lo, hi}: Int64{lo, hi}

def Enum.or(~enum: Enum, left: Enum.Value(enum), right: Enum.Value(enum)) -> Enum.Value(enum):
  match left right:
    case EnumValue{a, b} EnumValue{c, d}: EnumValue{U32.or(a, c), U32.or(b, d)}

def Enum.and(~enum: Enum, left: Enum.Value(enum), right: Enum.Value(enum)) -> Enum.Value(enum):
  match left right:
    case EnumValue{a, b} EnumValue{c, d}: EnumValue{U32.and(a, c), U32.and(b, d)}

def Enum.xor(~enum: Enum, left: Enum.Value(enum), right: Enum.Value(enum)) -> Enum.Value(enum):
  match left right:
    case EnumValue{a, b} EnumValue{c, d}: EnumValue{U32.xor(a, c), U32.xor(b, d)}

def Enum.pick(~enum: Enum, found: Bool, lo: U32, hi: U32, next: Unit -> Action(Enum.Value(enum))) -> Action(Enum.Value(enum)):
  match found:
    case True{}: Action.pure(Enum.Value(enum), EnumValue{lo, hi})
    case False{}: next(Unit{})

def Enum.find(~enum: Enum, +key: String, entries: List<&1, EnumEntry>) -> Action(Enum.Value(enum)):
  match entries:
    case Nil{}: Action.fail(Enum.Value(enum), 2, "Qt enum key is not declared: " ++ key)
    case EnumEntry{name, lo, hi} <> rest:
      Enum.pick(~enum, String.eq(name, key), lo, hi, unit => Enum.find(~enum, key, rest))

def Enum.value(~enum: Enum, key: String) -> Action(Enum.Value(enum)):
  Enum.find(~enum, key, Enum.entries(enum))

def EnumValue.encode(-name: String, value: EnumValue<name>) -> Wire:
  match value:
    case EnumValue{lo, hi}: WireScalar{lo, hi}

def EnumValue.decode(-name: String, value: Wire) -> Maybe<&2, EnumValue<name>>:
  match value:
    case WireScalar{lo, hi}: Some{EnumValue{lo, hi}}
    case _: None{}

def Enum.argument(enum: Enum) -> SignalArgument:
  match enum:
    case Enum{+name, entries, flags, alias}:
      SignalArgument{EnumValue<name>, name, value => EnumValue.encode(name, value),
        wire => EnumValue.decode(name, wire), Action.pure(Wire, Enum.schema(Enum{name, entries, flags, alias}))}

def Enum.arg(~enum: Enum) -> SignalArgument:
  Enum.argument(enum)
