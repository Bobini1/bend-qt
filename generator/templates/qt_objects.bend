def ObjectType.new(~object: ObjectType) -> Action(ObjectType.Instance(object)):
  do Action<ObjectType.Instance(object)>:
    schema: Wire <- ObjectType.schema(object)
    word: U32 <- ObjectType.create_raw(schema)
    return QtInstance{word}

def ObjectType.attach(~object: ObjectType, value: QtBase.Value(ObjectType.nativeBase(object))) -> Action(ObjectType.Instance(object)):
  do Action<ObjectType.Instance(object)>:
    schema: Wire <- ObjectType.schema(object)
    word: U32 <- ObjectType.attach_raw(QtBase.word(ObjectType.nativeBase(object), value), schema)
    return QtInstance{word}

def ObjectType.attachUsing(~object: ObjectType, acquire: Action(QtBase.Value(ObjectType.nativeBase(object)))) -> Action(ObjectType.Instance(object)):
  Action.bind(QtBase.Value(ObjectType.nativeBase(object)), ObjectType.Instance(object), acquire,
    value => ObjectType.attach(~object, value))

def ObjectType.cast(~object: ObjectType, value: QObject) -> Action(ObjectType.Instance(object)):
  do Action<ObjectType.Instance(object)>:
    schema: Wire <- ObjectType.schema(object)
    word: U32 <- ObjectType.cast_raw(value, schema)
    return QtInstance{word}

def ObjectType.release(~object: ObjectType, value: ObjectType.Instance(object)) -> Action(Unit):
  QObject.release(ObjectType.as_QObject(~object, value))

def ObjectType.destroy(~object: ObjectType, value: ObjectType.Instance(object)) -> Action(Unit):
  QObject.destroy(ObjectType.as_QObject(~object, value))

def ObjectType.moveToParentScope(~object: ObjectType, value: ObjectType.Instance(object)) -> Action(ObjectType.Instance(object)):
  do Action.Raw<Result<&1, &1, U32 & String, ObjectType.Instance(object)>>:
    result: Result<&1, &1, U32 & String, U32> <- Scope.transfer_raw(0, ObjectType.word(~object, value), 0)
    return ObjectType.wrap(~object, result)

def ObjectType.detachFromScope(~object: ObjectType, value: ObjectType.Instance(object)) -> Action(ObjectType.Instance(object)):
  do Action.Raw<Result<&1, &1, U32 & String, ObjectType.Instance(object)>>:
    result: Result<&1, &1, U32 & String, U32> <- Scope.transfer_raw(0, ObjectType.word(~object, value), 1)
    return ObjectType.wrap(~object, result)

def ObjectType.with(~object: ObjectType, -A: Type, acquire: Action(ObjectType.Instance(object)), body: ObjectType.Instance(object) -> Action(A)) -> Action(A):
  Action.using(ObjectType.Instance(object), A, acquire, value => Action.cleanup(ObjectType.release(~object, value)), body)

def Property.get(~property: Property, self: QObject) -> Action(Property.Value(property)):
  do Action<Property.Value(property)>:
    schema: Wire <- Property.schema(property)
    Wire.withData(Property.Value(property), ObjectType.get_raw(self, schema, 0),
      wire => TypeDescriptor.decode(Property.argument(property), wire))

def Property.readStorage(~property: Property, self: QObject) -> Action(Property.Value(property)):
  do Action<Property.Value(property)>:
    schema: Wire <- Property.schema(property)
    Wire.withData(Property.Value(property), ObjectType.get_raw(self, schema, 1),
      wire => TypeDescriptor.decode(Property.argument(property), wire))

def Property.set(~property: Property, self: QObject, value: Property.Value(property)) -> Action(Unit):
  do Action<Unit>:
    schema: Wire <- Property.schema(property)
    Wire.withData(Unit, TypeDescriptor.encode(Property.argument(property), value),
      wire => ObjectType.set_raw(self, schema, wire, 0))

def Property.writeStorage(~property: Property, self: QObject, value: Property.Value(property)) -> Action(Unit):
  do Action<Unit>:
    schema: Wire <- Property.schema(property)
    Wire.withData(Unit, TypeDescriptor.encode(Property.argument(property), value),
      wire => ObjectType.set_raw(self, schema, wire, 1))

def Property.notify(~property: Property, self: QObject) -> Action(Unit):
  do Action<Unit>:
    schema: Wire <- Property.schema(property)
    ObjectType.notify_raw(self, schema)

def Property.reset(~property: Property, self: QObject) -> Action(Unit):
  do Action<Unit>:
    schema: Wire <- Property.schema(property)
    ObjectType.reset_raw(self, schema)

def Property.bind(~property: Property, ~source: Property, self: QObject, other: QObject) -> Action(Unit):
  do Action<Unit>:
    target: Wire <- Property.schema(property)
    origin: Wire <- Property.schema(source)
    ObjectType.bind_raw(self, target, other, origin)

def Property.unbind(~property: Property, self: QObject) -> Action(Unit):
  do Action<Unit>:
    schema: Wire <- Property.schema(property)
    ObjectType.unbind_raw(self, schema)

def Property.hasBinding(~property: Property, self: QObject) -> Action(Bool):
  do Action<Bool>:
    schema: Wire <- Property.schema(property)
    ObjectType.hasBinding_raw(self, schema)

def Property.getter(property: Property) -> Method:
  match property:
    case Property{name, argument, flags, major, minor, notify}: Method.define(name, Nil{}, argument)

def Property.setter(property: Property) -> Method:
  match property:
    case Property{name, argument, flags, major, minor, notify}: Method.define(name, [argument], unit())

def Property.resetter(property: Property) -> Method:
  Method.define(Property.name(property), Nil{}, unit())

def Method.arguments(method: Method) -> SignalArguments:
  match method:
    case Method{name, arguments, result, names, tag, flags, access, major, minor}: arguments

def Method.result(method: Method) -> TypeDescriptor:
  match method:
    case Method{name, arguments, result, names, tag, flags, access, major, minor}: result

def MethodArguments.Handler(arguments: SignalArguments, result: TypeDescriptor) -> Type:
  match arguments:
    case NoSignalArguments{}: Action(TypeDescriptor.Value(result))
    case MoreSignalArguments{argument, rest}: TypeDescriptor.Value(argument) -> MethodArguments.Handler(rest, result)

def Method.Handler(~method: Method) -> Type:
  MethodArguments.Handler(Method.arguments(method), Method.result(method))

def MethodArguments.call(~result: TypeDescriptor, arguments: SignalArguments, sink: List<&2, Wire> -> Action(TypeDescriptor.Value(result)), values: EncodedArguments(TypeDescriptor.Value(result))) -> MethodArguments.Handler(arguments, result):
  match arguments:
    case NoSignalArguments{}: values(encoded => sink(List.reverse(&2, Wire, encoded)))
    case MoreSignalArguments{argument, rest}:
      value => MethodArguments.call(~result, rest, sink, EncodedArguments.add(TypeDescriptor.Value(result), argument, value, values))

def Method.call_values(~method: Method, self: QObject, values: List<&2, Wire>) -> Action(TypeDescriptor.Value(Method.result(method))):
  do Action<TypeDescriptor.Value(Method.result(method))>:
    schema: Wire <- Method.schema(method)
    Wire.withData(TypeDescriptor.Value(Method.result(method)), ObjectType.call_raw(self, schema, WireSequence{values}),
      wire => TypeDescriptor.decode(Method.result(method), wire))

def Method.call(~method: Method, self: QObject) -> Method.Handler(~method):
  MethodArguments.call(~Method.result(method), Method.arguments(method), values => Method.call_values(~method, self, values),
    EncodedArguments.empty(TypeDescriptor.Value(Method.result(method))))

def Method.answer(~result: TypeDescriptor, call: U32, action: Action(TypeDescriptor.Value(result))) -> Action(Unit):
  do Action<Unit>:
    value: TypeDescriptor.Value(result) <- action
    Wire.withData(Unit, TypeDescriptor.encode(result, value), wire => Handler.answer(call, wire))

def MethodArguments.apply(~result: TypeDescriptor, arguments: SignalArguments, handler: MethodArguments.Handler(arguments, result), values: SignalArguments.Values(arguments), call: U32) -> Action(Unit):
  match arguments values:
    case NoSignalArguments{} Unit{}: Method.answer(~result, call, handler)
    case MoreSignalArguments{argument, rest} PairValue{head, tail}: MethodArguments.apply(~result, rest, handler(head), tail, call)

def MethodArguments.deliver(~result: TypeDescriptor, arguments: SignalArguments, handler: MethodArguments.Handler(arguments, result), values: Action(SignalArguments.Values(arguments)), call: U32) -> Action(Unit):
  Action.bind(SignalArguments.Values(arguments), Unit, values, value => MethodArguments.apply(~result, arguments, handler, value, call))

def Method.deliver(~method: Method, ~S: Data, ~f: S -> Method.Handler(~method), state: S, call: U32, wires: Maybe<&2, List<&2, Wire>>) -> Action(Unit):
  match wires:
    case None{}: Handler.malformed(Unit)
    case Some{values}: MethodArguments.deliver(~Method.result(method), Method.arguments(method), f(state), SignalArguments.decode(Method.arguments(method), values), call)

def Method.request(~method: Method, ~S: Data, ~f: S -> Method.Handler(~method), state: S, request: Maybe<&2, HandlerRequest>) -> Action(Unit):
  match request:
    case None{}: Handler.malformed(Unit)
    case Some{HandlerRequest{call, arguments}}: Method.deliver(~method, ~S, ~f, state, call, Codec.read_sequence(arguments))

def Method.invoke(~method: Method, ~S: Data, ~f: S -> Method.Handler(~method), pair: S & Wire) -> Action(Unit):
  match pair:
    case (state, wire): Method.request(~method, ~S, ~f, state, HandlerRequest.decode(wire))
