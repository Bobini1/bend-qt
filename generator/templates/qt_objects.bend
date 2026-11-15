def QtObject.new(~object: QtObject) -> Action(QtObject.Instance(object)):
  do Action<QtObject.Instance(object)>:
    schema: Wire <- QtObject.schema(object)
    word: U32 <- QtObject.create_raw(schema)
    return QtInstance{word}

def QtObject.attach(~object: QtObject, value: QtBase.Value(QtObject.nativeBase(object))) -> Action(QtObject.Instance(object)):
  do Action<QtObject.Instance(object)>:
    schema: Wire <- QtObject.schema(object)
    word: U32 <- QtObject.attach_raw(QtBase.word(QtObject.nativeBase(object), value), schema)
    return QtInstance{word}

def QtObject.newWith(~object: QtObject, acquire: Action(QtBase.Value(QtObject.nativeBase(object)))) -> Action(QtObject.Instance(object)):
  Action.bind(QtBase.Value(QtObject.nativeBase(object)), QtObject.Instance(object), acquire,
    value => QtObject.attach(~object, value))

def QtObject.cast(~object: QtObject, value: QObject) -> Action(QtObject.Instance(object)):
  do Action<QtObject.Instance(object)>:
    schema: Wire <- QtObject.schema(object)
    word: U32 <- QtObject.cast_raw(value, schema)
    return QtInstance{word}

def QtObject.release(~object: QtObject, value: QtObject.Instance(object)) -> Action(Unit):
  QObject.release(QtObject.as_QObject(~object, value))

def QtObject.destroy(~object: QtObject, value: QtObject.Instance(object)) -> Action(Unit):
  QObject.destroy(QtObject.as_QObject(~object, value))

def QtObject.keep(~object: QtObject, value: QtObject.Instance(object)) -> Action(QtObject.Instance(object)):
  do Action.Raw<Result<&1, &1, U32 & String, QtObject.Instance(object)>>:
    result: Result<&1, &1, U32 & String, U32> <- Scope.keep_raw(0, QtObject.word(~object, value))
    return QtObject.wrap(~object, result)

def QtObject.with(~object: QtObject, -A: Type, acquire: Action(QtObject.Instance(object)), body: QtObject.Instance(object) -> Action(A)) -> Action(A):
  Action.using(QtObject.Instance(object), A, acquire, value => Action.cleanup(QtObject.release(~object, value)), body)

def Property.get(~property: Property, self: QObject) -> Action(Property.Value(property)):
  do Action<Property.Value(property)>:
    schema: Wire <- Property.schema(property)
    Wire.withData(Property.Value(property), QtObject.get_raw(self, schema, 0),
      wire => SignalArgument.decode(Property.argument(property), wire))

def Property.readStorage(~property: Property, self: QObject) -> Action(Property.Value(property)):
  do Action<Property.Value(property)>:
    schema: Wire <- Property.schema(property)
    Wire.withData(Property.Value(property), QtObject.get_raw(self, schema, 1),
      wire => SignalArgument.decode(Property.argument(property), wire))

def Property.set(~property: Property, self: QObject, value: Property.Value(property)) -> Action(Unit):
  do Action<Unit>:
    schema: Wire <- Property.schema(property)
    Wire.withData(Unit, SignalArgument.encode(Property.argument(property), value),
      wire => QtObject.set_raw(self, schema, wire, 0))

def Property.store(~property: Property, self: QObject, value: Property.Value(property)) -> Action(Unit):
  do Action<Unit>:
    schema: Wire <- Property.schema(property)
    Wire.withData(Unit, SignalArgument.encode(Property.argument(property), value),
      wire => QtObject.set_raw(self, schema, wire, 1))

def Property.notify(~property: Property, self: QObject) -> Action(Unit):
  do Action<Unit>:
    schema: Wire <- Property.schema(property)
    QtObject.notify_raw(self, schema)

def Property.reset(~property: Property, self: QObject) -> Action(Unit):
  do Action<Unit>:
    schema: Wire <- Property.schema(property)
    QtObject.reset_raw(self, schema)

def Property.bind(~property: Property, ~source: Property, self: QObject, other: QObject) -> Action(Unit):
  do Action<Unit>:
    target: Wire <- Property.schema(property)
    origin: Wire <- Property.schema(source)
    QtObject.bind_raw(self, target, other, origin)

def Property.unbind(~property: Property, self: QObject) -> Action(Unit):
  do Action<Unit>:
    schema: Wire <- Property.schema(property)
    QtObject.unbind_raw(self, schema)

def Property.hasBinding(~property: Property, self: QObject) -> Action(Bool):
  do Action<Bool>:
    schema: Wire <- Property.schema(property)
    QtObject.hasBinding_raw(self, schema)

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

def Method.result(method: Method) -> SignalArgument:
  match method:
    case Method{name, arguments, result, names, tag, flags, access, major, minor}: result

def MethodArguments.Handler(arguments: SignalArguments, result: SignalArgument) -> Type:
  match arguments:
    case NoSignalArguments{}: Action(SignalArgument.Value(result))
    case MoreSignalArguments{argument, rest}: SignalArgument.Value(argument) -> MethodArguments.Handler(rest, result)

def Method.Handler(~method: Method) -> Type:
  MethodArguments.Handler(Method.arguments(method), Method.result(method))

def MethodArguments.call(~result: SignalArgument, arguments: SignalArguments, sink: List<&2, Wire> -> Action(SignalArgument.Value(result)), values: EncodedArguments(SignalArgument.Value(result))) -> MethodArguments.Handler(arguments, result):
  match arguments:
    case NoSignalArguments{}: values(encoded => sink(List.reverse(&2, Wire, encoded)))
    case MoreSignalArguments{argument, rest}:
      value => MethodArguments.call(~result, rest, sink, EncodedArguments.add(SignalArgument.Value(result), argument, value, values))

def Method.call_values(~method: Method, self: QObject, values: List<&2, Wire>) -> Action(SignalArgument.Value(Method.result(method))):
  do Action<SignalArgument.Value(Method.result(method))>:
    schema: Wire <- Method.schema(method)
    Wire.withData(SignalArgument.Value(Method.result(method)), QtObject.call_raw(self, schema, WireSequence{values}),
      wire => SignalArgument.decode(Method.result(method), wire))

def Method.call(~method: Method, self: QObject) -> Method.Handler(~method):
  MethodArguments.call(~Method.result(method), Method.arguments(method), values => Method.call_values(~method, self, values),
    EncodedArguments.empty(SignalArgument.Value(Method.result(method))))

def Method.answer(~result: SignalArgument, call: U32, action: Action(SignalArgument.Value(result))) -> Action(Unit):
  do Action<Unit>:
    value: SignalArgument.Value(result) <- action
    Wire.withData(Unit, SignalArgument.encode(result, value), wire => Handler.answer(call, wire))

def MethodArguments.apply(~result: SignalArgument, arguments: SignalArguments, handler: MethodArguments.Handler(arguments, result), values: SignalArguments.Values(arguments), call: U32) -> Action(Unit):
  match arguments values:
    case NoSignalArguments{} Unit{}: Method.answer(~result, call, handler)
    case MoreSignalArguments{argument, rest} PairValue{head, tail}: MethodArguments.apply(~result, rest, handler(head), tail, call)

def MethodArguments.deliver(~result: SignalArgument, arguments: SignalArguments, handler: MethodArguments.Handler(arguments, result), values: Action(SignalArguments.Values(arguments)), call: U32) -> Action(Unit):
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
