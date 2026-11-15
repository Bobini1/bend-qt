def Internal.Revision.checkedMajor(valid: Bool, major: U32) -> U32:
  match valid:
    case True{}: major
    case False{}: 65536

def Internal.Revision.major(+major: U32) -> U32:
  Internal.Revision.checkedMajor(U32.is_lt(major, 255), major)

type SignalArgument is Type:
  SignalArgument{Value: Data, name: String, encode: Value -> Wire, decode: Wire -> Maybe<&2, Value>, dependency: Action(Wire)}
  BendArgument{Value: Data, witness: Value -> Value}
  QmlListArgument{element: SignalArgument}

type QmlListView<-Element: String> is Data:
  QmlListView{word: U32}

def Internal.QmlListView.encode(-element: String, value: QmlListView<element>) -> Wire:
  match value:
    case QmlListView{word}: WireScalar{word, 0}

def Internal.QmlListView.decode(-element: String, wire: Wire) -> Maybe<&2, QmlListView<element>>:
  match wire:
    case WireScalar{word, 0}: Some{QmlListView{word}}
    case _: None{}

def Internal.QmlList.elementName(name: String) -> String:
  match name:
    case SNil{}: SNil{}
    case SCon{Chr{42}, SNil{}}: SNil{}
    case SCon{head, tail}: SCon{head, Internal.QmlList.elementName(tail)}

def SignalArgument.name(argument: SignalArgument) -> String:
  match argument:
    case SignalArgument{Value, name, encode, decode, dependency}: name
    case BendArgument{Value, witness}: "BendData"
    case QmlListArgument{element}: "QQmlListProperty<" ++ Internal.QmlList.elementName(SignalArgument.name(element)) ++ ">"

def SignalArgument.Value(argument: SignalArgument) -> Data:
  match argument:
    case SignalArgument{Value, name, encode, decode, dependency}: Value
    case BendArgument{Value, witness}: Value
    case QmlListArgument{element}: QmlListView<SignalArgument.name(element)>

def Internal.QmlList.name(element: SignalArgument) -> String:
  "QQmlListProperty<" ++ Internal.QmlList.elementName(SignalArgument.name(element)) ++ ">"

# Native container declarations use closed argument codecs. Opaque Bend Data
# stays available as Qt.arg(~List<...>); it is not silently made a native QList.
def Internal.NativeArgument.encode(argument: SignalArgument, value: SignalArgument.Value(argument)) -> Wire:
  match argument:
    case SignalArgument{Value, name, encode, decode, dependency}: encode(value)
    case BendArgument{Value, witness}: WireScalar{0, 0}
    case QmlListArgument{element}: Internal.QmlListView.encode(SignalArgument.name(element), value)

def Internal.NativeArgument.decode(argument: SignalArgument, value: Wire) -> Maybe<&2, SignalArgument.Value(argument)>:
  match argument:
    case SignalArgument{Value, name, encode, decode, dependency}: decode(value)
    case BendArgument{Value, witness}: None{}
    case QmlListArgument{element}: Internal.QmlListView.decode(SignalArgument.name(element), value)

def Internal.QmlList.schema(wire: Wire) -> Wire:
  match wire:
    case WireSequence{WireText{+name} <> tail}:
      WireSequence{[WireText{"QQmlListProperty<" ++ Internal.QmlList.elementName(name) ++ ">"},
        WireSequence{[WireText{"qml_list"}, WireSequence{WireText{name} <> tail}]}]}
    case _: WireScalar{0, 0}

def SignalArgument.schema(argument: SignalArgument) -> Action(Wire):
  match argument:
    case SignalArgument{Value, name, encode, decode, dependency}:
      do Action<Wire>:
        wire: Wire <- dependency
        return WireSequence{[WireText{name}, wire]}
    case BendArgument{Value, witness}: Action.pure(Wire, WireSequence{[WireText{"BendData"}, WireScalar{0, 0}]})
    case QmlListArgument{element}:
      do Action<Wire>:
        wire: Wire <- SignalArgument.schema(element)
        return Internal.QmlList.schema(wire)

def Internal.NativeArgument.dependencies(arguments: List<&1, SignalArgument>) -> Action(Wire):
  match arguments:
    case Nil{}: Action.pure(Wire, WireScalar{0, 0})
    case argument <> rest:
      do Action<Wire>:
        wire: Wire <- SignalArgument.schema(argument)
        Internal.NativeArgument.dependencies(rest)

def Internal.NativeArgument.sequence(element: SignalArgument) -> Action(Wire):
  do Action<Wire>:
    wire: Wire <- SignalArgument.schema(element)
    return WireSequence{[WireText{"Bend.Sequence"}, wire]}

def list(~element: SignalArgument) -> SignalArgument:
  SignalArgument{List<&2, SignalArgument.Value(element)>, "QList<" ++ SignalArgument.name(element) ++ ">",
    values => Codec.encode_list(~SignalArgument.Value(element), ~(value => Internal.NativeArgument.encode(element, value)), values),
    wire => Codec.decode_list(~SignalArgument.Value(element), ~(value => Internal.NativeArgument.decode(element, value)), wire),
    Internal.NativeArgument.sequence(element)}

def set(~element: SignalArgument) -> SignalArgument:
  SignalArgument{List<&2, SignalArgument.Value(element)>, "QSet<" ++ SignalArgument.name(element) ++ ">",
    values => Codec.encode_list(~SignalArgument.Value(element), ~(value => Internal.NativeArgument.encode(element, value)), values),
    wire => Codec.decode_list(~SignalArgument.Value(element), ~(value => Internal.NativeArgument.decode(element, value)), wire), Internal.NativeArgument.dependencies([element])}

def vector(~element: SignalArgument) -> SignalArgument:
  list(~element)

def array(~element: SignalArgument, ~count: U32) -> SignalArgument:
  SignalArgument{List<&2, SignalArgument.Value(element)>, "std::array<" ++ SignalArgument.name(element) ++ "," ++ U32.show(count) ++ ">",
    values => Codec.encode_list(~SignalArgument.Value(element), ~(value => Internal.NativeArgument.encode(element, value)), values),
    wire => Codec.decode_array(~SignalArgument.Value(element), ~(value => Internal.NativeArgument.decode(element, value)), count, wire), Internal.NativeArgument.dependencies([element])}

def Internal.NativeArgument.encodePair(~first: SignalArgument, ~second: SignalArgument, value: PairValue<SignalArgument.Value(first), SignalArgument.Value(second)>) -> Wire:
  match value:
    case PairValue{left, right}: Codec.pair(Internal.NativeArgument.encode(first, left), Internal.NativeArgument.encode(second, right))

def Internal.NativeArgument.pairDecoded(-A: Data, -B: Data, first: Maybe<&2, A>, second: Maybe<&2, B>) -> Maybe<&2, PairValue<A, B>>:
  match first second:
    case Some{first} Some{second}: Some{PairValue{first, second}}
    case _ _: None{}

def Internal.NativeArgument.decodePair(~first: SignalArgument, ~second: SignalArgument, wire: Wire) -> Maybe<&2, PairValue<SignalArgument.Value(first), SignalArgument.Value(second)>>:
  match wire:
    case WireSequence{left <> right <> Nil{}}:
      Internal.NativeArgument.pairDecoded(SignalArgument.Value(first), SignalArgument.Value(second),
        Internal.NativeArgument.decode(first, left), Internal.NativeArgument.decode(second, right))
    case _: None{}

def pair(~first: SignalArgument, ~second: SignalArgument) -> SignalArgument:
  SignalArgument{PairValue<SignalArgument.Value(first), SignalArgument.Value(second)>,
    "std::pair<" ++ SignalArgument.name(first) ++ "," ++ SignalArgument.name(second) ++ ">",
    value => Internal.NativeArgument.encodePair(~first, ~second, value),
    wire => Internal.NativeArgument.decodePair(~first, ~second, wire), Internal.NativeArgument.dependencies([first, second])}

def Internal.NativeArgument.map(~key: SignalArgument, ~value: SignalArgument, name: String) -> SignalArgument:
  SignalArgument{List<&2, PairValue<SignalArgument.Value(key), SignalArgument.Value(value)>>,
    name ++ "<" ++ SignalArgument.name(key) ++ "," ++ SignalArgument.name(value) ++ ">",
    entries => Codec.encode_list(~PairValue<SignalArgument.Value(key), SignalArgument.Value(value)>,
      ~(entry => Internal.NativeArgument.encodePair(~key, ~value, entry)), entries),
    wire => Codec.decode_list(~PairValue<SignalArgument.Value(key), SignalArgument.Value(value)>,
      ~(entry => Internal.NativeArgument.decodePair(~key, ~value, entry)), wire), Internal.NativeArgument.dependencies([key, value])}

def map(~key: SignalArgument, ~value: SignalArgument) -> SignalArgument:
  Internal.NativeArgument.map(~key, ~value, "QMap")

def hash(~key: SignalArgument, ~value: SignalArgument) -> SignalArgument:
  Internal.NativeArgument.map(~key, ~value, "QHash")

def multiMap(~key: SignalArgument, ~value: SignalArgument) -> SignalArgument:
  Internal.NativeArgument.map(~key, ~value, "QMultiMap")

def multiHash(~key: SignalArgument, ~value: SignalArgument) -> SignalArgument:
  Internal.NativeArgument.map(~key, ~value, "QMultiHash")

def optional(~element: SignalArgument) -> SignalArgument:
  SignalArgument{Maybe<&2, SignalArgument.Value(element)>, "std::optional<" ++ SignalArgument.name(element) ++ ">",
    value => Codec.encode_optional(~SignalArgument.Value(element), ~(value => Internal.NativeArgument.encode(element, value)), value),
    wire => Codec.decode_optional(~SignalArgument.Value(element), ~(value => Internal.NativeArgument.decode(element, value)), wire), Internal.NativeArgument.dependencies([element])}

def SignalArgument.encode(argument: SignalArgument, value: SignalArgument.Value(argument)) -> Action(Wire):
  match argument:
    case SignalArgument{Value, name, encode, decode, dependency}: Action.pure(Wire, encode(value))
    case BendArgument{Value, witness}: Internal.Data.encode(Value, witness, value)
    case QmlListArgument{element}: Action.pure(Wire, Internal.QmlListView.encode(SignalArgument.name(element), value))

def SignalArgument.decoded(-A: Data, value: Maybe<&2, A>) -> Action(A):
  match value:
    case Some{value}: Action.pure(A, value)
    case None{}: Action.fail(A, 22, "Qt value has the wrong declared type")

def SignalArgument.decode(argument: SignalArgument, value: Wire) -> Action(SignalArgument.Value(argument)):
  match argument:
    case SignalArgument{Value, name, encode, decode, dependency}: SignalArgument.decoded(Value, decode(value))
    case BendArgument{Value, witness}: Internal.Data.decode(Value, witness, value)
    case QmlListArgument{element}: SignalArgument.decoded(QmlListView<SignalArgument.name(element)>, Internal.QmlListView.decode(SignalArgument.name(element), value))

def EncodedArguments.add(-A: Type, argument: SignalArgument, value: SignalArgument.Value(argument), previous: EncodedArguments(A)) -> EncodedArguments(A):
  next => previous(values => Wire.withData(A, SignalArgument.encode(argument, value), wire => next(wire <> values)))

type SignalArguments is Type:
  NoSignalArguments{}
  MoreSignalArguments{argument: SignalArgument, rest: SignalArguments}

def SignalArguments.fromList(arguments: List<&1, SignalArgument>) -> SignalArguments:
  match arguments:
    case Nil{}: NoSignalArguments{}
    case argument <> rest: MoreSignalArguments{argument, SignalArguments.fromList(rest)}

def SignalArguments.Values(arguments: SignalArguments) -> Data:
  match arguments:
    case NoSignalArguments{}: Unit
    case MoreSignalArguments{argument, rest}: PairValue<SignalArgument.Value(argument), SignalArguments.Values(rest)>

def SignalArguments.Handler(arguments: SignalArguments) -> Type:
  match arguments:
    case NoSignalArguments{}: Action(Unit)
    case MoreSignalArguments{argument, rest}: SignalArgument.Value(argument) -> SignalArguments.Handler(rest)

def SignalArguments.pair(-A: Data, -B: Data, head: Maybe<&2, A>, tail: Maybe<&2, B>) -> Maybe<&2, PairValue<A, B>>:
  match head tail:
    case Some{head} Some{tail}: Some{PairValue{head, tail}}
    case _ _: None{}

def SignalArguments.decode(arguments: SignalArguments, wires: List<&2, Wire>) -> Action(SignalArguments.Values(arguments)):
  match arguments wires:
    case NoSignalArguments{} Nil{}: Action.pure(Unit, Unit{})
    case MoreSignalArguments{argument, rest} head <> tail:
      Action.bind(SignalArgument.Value(argument), SignalArguments.Values(MoreSignalArguments{argument, rest}),
        SignalArgument.decode(argument, head), first =>
          Action.bind(SignalArguments.Values(rest), PairValue<SignalArgument.Value(argument), SignalArguments.Values(rest)>,
            SignalArguments.decode(rest, tail), last =>
              Action.pure(PairValue<SignalArgument.Value(argument), SignalArguments.Values(rest)>, PairValue{first, last})))
    case _ _: Action.fail(SignalArguments.Values(arguments), 22, "Signal argument mismatch")

def SignalArguments.apply(arguments: SignalArguments, handler: SignalArguments.Handler(arguments), values: SignalArguments.Values(arguments)) -> Action(Unit):
  match arguments values:
    case NoSignalArguments{} Unit{}: handler
    case MoreSignalArguments{argument, rest} PairValue{head, tail}: SignalArguments.apply(rest, handler(head), tail)

def SignalArguments.run(arguments: SignalArguments, handler: SignalArguments.Handler(arguments), values: Action(SignalArguments.Values(arguments))) -> Action(Unit):
  Action.bind(SignalArguments.Values(arguments), Unit, values, value => SignalArguments.apply(arguments, handler, value))

def SignalArguments.emit(arguments: SignalArguments, sink: List<&2, Wire> -> Action(Unit), values: EncodedArguments(Unit)) -> SignalArguments.Handler(arguments):
  match arguments:
    case NoSignalArguments{}: values(encoded => sink(List.reverse(&2, Wire, encoded)))
    case MoreSignalArguments{argument, rest}:
      value => SignalArguments.emit(rest, sink, EncodedArguments.add(Unit, argument, value, values))

type Signal is Type:
  Signal{name: String, arguments: SignalArguments, names: List<&1, String>, flags: U32, major: U32, minor: U32}

def Signal.define(name: String, arguments: List<&1, SignalArgument>) -> Signal:
  Signal{name, SignalArguments.fromList(arguments), Nil{}, 0, 0, 0}

def Signal.withArgumentNames(signal: Signal, names: List<&1, String>) -> Signal:
  match signal:
    case Signal{name, arguments, previous, flags, major, minor}: Signal{name, arguments, names, flags, major, minor}

def Signal.withRevision(signal: Signal, minor: U32) -> Signal:
  match signal:
    case Signal{name, arguments, names, flags, major, previous}: Signal{name, arguments, names, U32.or(flags, 1), 65535, minor}

def Signal.withVersionRevision(signal: Signal, major: U32, minor: U32) -> Signal:
  match signal:
    case Signal{name, arguments, names, flags, previousMajor, previousMinor}: Signal{name, arguments, names, U32.or(flags, 1), Internal.Revision.major(major), minor}

def Signal.arguments(signal: Signal) -> SignalArguments:
  match signal:
    case Signal{name, arguments, names, flags, major, minor}: arguments

def Signal.deliver(~signal: Signal, ~S: Data, ~handler: S -> SignalArguments.Handler(Signal.arguments(signal)), state: S, values: List<&2, Wire>) -> Action(Unit):
  SignalArguments.run(Signal.arguments(signal), handler(state), SignalArguments.decode(Signal.arguments(signal), values))

def SignalArguments.names(arguments: SignalArguments) -> Action(List<&2, Wire>):
  match arguments:
    case NoSignalArguments{}: Action.pure(List<&2, Wire>, Nil{})
    case MoreSignalArguments{argument, rest}:
      do Action<List<&2, Wire>>:
        wire: Wire <- SignalArgument.schema(argument)
        tail: List<&2, Wire> <- SignalArguments.names(rest)
        return wire <> tail

def Signal.argumentNamesWire(names: List<&1, String>) -> List<&2, Wire>:
  match names:
    case Nil{}: Nil{}
    case name <> rest: WireText{name} <> Signal.argumentNamesWire(rest)

def Signal.schema(signal: Signal) -> Action(Wire):
  match signal:
    case Signal{name, arguments, names, flags, major, minor}:
      do Action<Wire>:
        types: List<&2, Wire> <- SignalArguments.names(arguments)
        return WireSequence{[WireText{name}, WireSequence{types},
          WireSequence{[WireSequence{Signal.argumentNamesWire(names)}, WireScalar{flags, 0}, WireScalar{major, minor}]}]}

def SignalSchemas.items(signals: List<&1, Signal>) -> Action(List<&2, Wire>):
  match signals:
    case Nil{}: Action.pure(List<&2, Wire>, Nil{})
    case signal <> rest:
      do Action<List<&2, Wire>>:
        wire: Wire <- Signal.schema(signal)
        tail: List<&2, Wire> <- SignalSchemas.items(rest)
        return wire <> tail

def SignalSchemas.encode(signals: List<&1, Signal>) -> Action(Wire):
  do Action<Wire>:
    values: List<&2, Wire> <- SignalSchemas.items(signals)
    return WireSequence{values}

def Signal.invoke_arguments(~signal: Signal, ~S: Data, ~handler: S -> SignalArguments.Handler(Signal.arguments(signal)), state: S, arguments: Maybe<&2, List<&2, Wire>>) -> Action(Unit):
  match arguments:
    case None{}: Handler.malformed(Unit)
    case Some{values}: Signal.deliver(~signal, ~S, ~handler, state, values)

def Signal.invoke_request(~signal: Signal, ~S: Data, ~handler: S -> SignalArguments.Handler(Signal.arguments(signal)), state: S, request: Maybe<&2, HandlerRequest>) -> Action(Unit):
  match request:
    case None{}: Handler.malformed(Unit)
    case Some{HandlerRequest{call, arguments}}:
      Signal.invoke_arguments(~signal, ~S, ~handler, state, Codec.read_sequence(arguments))

def Signal.invoke(~signal: Signal, ~S: Data, ~handler: S -> SignalArguments.Handler(Signal.arguments(signal)), pair: S & Wire) -> Action(Unit):
  match pair:
    case (state, wire): Signal.invoke_request(~signal, ~S, ~handler, state, HandlerRequest.decode(wire))
