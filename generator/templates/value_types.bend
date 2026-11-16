type ValueType is Type:
  ValueType{name: String, fields: List<&1, Property>}

def ValueType.define(name: String, fields: List<&1, Property>) -> ValueType:
  ValueType{name, fields}

def ValueType.name(schema: ValueType) -> String:
  match schema:
    case ValueType{name, fields}: name

def ValueType.fields(schema: ValueType) -> List<&1, Property>:
  match schema:
    case ValueType{name, fields}: fields

def ValueType.schema(schema: ValueType) -> Action(Wire):
  match schema:
    case ValueType{name, fields}:
      do Action<Wire>:
        properties: List<&2, Wire> <- Property.schemas(fields)
        return WireSequence{[WireScalar{1447119957, 0}, WireText{name}, WireSequence{properties}]}

type ValueInstance<-Name: String> is Data:
  ValueInstance{word: U32}

def ValueType.Instance(-schema: ValueType) -> Data:
  ValueInstance<ValueType.name(schema)>

def ValueType.word(~schema: ValueType, self: ValueType.Instance(schema)) -> U32:
  match self:
    case ValueInstance{word}: word

def ValueType.wrap(~schema: ValueType, result: Result<&1, &1, U32 & String, U32>) -> Result<&1, &1, U32 & String, ValueType.Instance(schema)>:
  match result:
    case Fail{error}: Fail{error}
    case Done{word}: Done{ValueInstance{word}}

def ValueType.decode(~schema: ValueType, wire: Wire) -> Maybe<&2, ValueType.Instance(schema)>:
  match wire:
    case WireScalar{word, 0}: Some{ValueInstance{word}}
    case _: None{}

def value(~schema: ValueType) -> TypeDescriptor:
  TypeDescriptor{ValueType.Instance(schema), ValueType.name(schema),
    self => WireScalar{ValueType.word(~schema, self), 0},
    wire => ValueType.decode(~schema, wire), ValueType.schema(schema)}

def ValueType.new(~schema: ValueType) -> Action(ValueType.Instance(schema)):
  do Action<ValueType.Instance(schema)>:
    declaration: Wire <- ValueType.schema(schema)
    word: U32 <- Internal.ValueType.create(declaration, WireSequence{Nil{}}, 0)
    return ValueInstance{word}

def ValueType.argumentList(fields: List<&1, Property>) -> List<&1, TypeDescriptor>:
  match fields:
    case Nil{}: Nil{}
    case field <> rest: Property.argument(field) <> ValueType.argumentList(rest)

def ValueType.arguments(schema: ValueType) -> SignalArguments:
  SignalArguments.fromList(ValueType.argumentList(ValueType.fields(schema)))

def ValueType.makeValues(~schema: ValueType, values: List<&2, Wire>) -> Action(ValueType.Instance(schema)):
  do Action<ValueType.Instance(schema)>:
    declaration: Wire <- ValueType.schema(schema)
    word: U32 <- Internal.ValueType.create(declaration, WireSequence{values}, 1)
    return ValueInstance{word}

def ValueType.make(~schema: ValueType) -> MethodArguments.Handler(ValueType.arguments(schema), value(~schema)):
  MethodArguments.call(~value(~schema), ValueType.arguments(schema), values => ValueType.makeValues(~schema, values), EncodedArguments.empty(ValueType.Instance(schema)))

def ValueType.get(~schema: ValueType, ~field: Property, self: ValueType.Instance(schema)) -> Action(Property.Value(field)):
  do Action<Property.Value(field)>:
    declaration: Wire <- ValueType.schema(schema)
    property: Wire <- Property.schema(field)
    Wire.withData(Property.Value(field), Internal.ValueType.get(declaration, ValueType.word(~schema, self), property),
      wire => TypeDescriptor.decode(Property.argument(field), wire))

# Values copy independently. An update returns another owning value.
def ValueType.updateWire(~schema: ValueType, ~field: Property, self: ValueType.Instance(schema), wire: Wire) -> Action(ValueType.Instance(schema)):
  do Action<ValueType.Instance(schema)>:
    declaration: Wire <- ValueType.schema(schema)
    property: Wire <- Property.schema(field)
    word: U32 <- Internal.ValueType.updated(declaration, ValueType.word(~schema, self), property, wire)
    return ValueInstance{word}

def ValueType.updated(~schema: ValueType, ~field: Property, self: ValueType.Instance(schema), data: Property.Value(field)) -> Action(ValueType.Instance(schema)):
  Wire.withData(ValueType.Instance(schema), TypeDescriptor.encode(Property.argument(field), data),
    wire => ValueType.updateWire(~schema, ~field, self, wire))

def ValueType.as_QVariant(~schema: ValueType, self: ValueType.Instance(schema)) -> QVariant:
  QVariant{ValueType.word(~schema, self)}

def ValueType.copy(~schema: ValueType, self: ValueType.Instance(schema)) -> Action(ValueType.Instance(schema)):
  QVariant.toValue(~value(~schema), ValueType.as_QVariant(~schema, self))

def ValueType.release(~schema: ValueType, self: ValueType.Instance(schema)) -> Action(Unit):
  QVariant.release(ValueType.as_QVariant(~schema, self))

def ValueType.destroy(~schema: ValueType, self: ValueType.Instance(schema)) -> Action(Unit):
  QVariant.destroy(ValueType.as_QVariant(~schema, self))

def ValueType.moveToParentScope(~schema: ValueType, self: ValueType.Instance(schema)) -> Action(ValueType.Instance(schema)):
  do Action<ValueType.Instance(schema)>:
    kept: QVariant <- QVariant.moveToParentScope(ValueType.as_QVariant(~schema, self))
    return ValueInstance{QVariant.word(kept)}

def ValueType.detachFromScope(~schema: ValueType, self: ValueType.Instance(schema)) -> Action(ValueType.Instance(schema)):
  do Action<ValueType.Instance(schema)>:
    detached: QVariant <- QVariant.detachFromScope(ValueType.as_QVariant(~schema, self))
    return ValueInstance{QVariant.word(detached)}

def ValueType.with(~schema: ValueType, -A: Type, acquire: Action(ValueType.Instance(schema)), body: ValueType.Instance(schema) -> Action(A)) -> Action(A):
  Action.using(ValueType.Instance(schema), A, acquire, self => Action.cleanup(ValueType.release(~schema, self)), body)

def ValueType.register(~schema: ValueType, uri: String, major: U32, minor: U32, name: String) -> Action(U32):
  do Action<U32>:
    declaration: Wire <- ValueType.schema(schema)
    Internal.ValueType.register(declaration, uri, major, minor, name)
