# Schemas and codecs are ordinary closed Bend declarations. No application
# C++ or numeric handler dispatch is required.
type QtBase is Type:
  QtBase{Value: Data, native: U32, parent: Action(Wire), encode: Value -> U32, decode: U32 -> Value}

def QtBase.Value(base: QtBase) -> Data:
  match base:
    case QtBase{Value, native, parent, encode, decode}: Value

type Property is Type:
  Property{name: String, argument: SignalArgument, flags: U32, major: U32, minor: U32, notify: List<&1, Signal>}

def Property.define(name: String, argument: SignalArgument) -> Property:
  Property{name, argument, 0, 0, 0, Nil{}}

def Property.readOnly(name: String, argument: SignalArgument) -> Property:
  Property{name, argument, 1, 0, 0, Nil{}}

def Property.constant(name: String, argument: SignalArgument) -> Property:
  Property{name, argument, 2, 0, 0, Nil{}}

def Property.withFlag(property: Property, +flag: U32, enabled: Bool) -> Property:
  match property enabled:
    case Property{name, argument, flags, major, minor, notify} True{}:
      Property{name, argument, U32.or(flags, flag), major, minor, notify}
    case Property{name, argument, flags, major, minor, notify} False{}:
      Property{name, argument, U32.and(flags, U32.sub(4294967295, flag)), major, minor, notify}

def Property.withReset(property: Property) -> Property:
  Property.withFlag(property, 4, True{})

def Property.withStored(property: Property, enabled: Bool) -> Property:
  Property.withFlag(property, 8, Bool.not(enabled))

def Property.withDesignable(property: Property, enabled: Bool) -> Property:
  Property.withFlag(property, 16, Bool.not(enabled))

def Property.withScriptable(property: Property, enabled: Bool) -> Property:
  Property.withFlag(property, 32, Bool.not(enabled))

def Property.withUser(property: Property, enabled: Bool) -> Property:
  Property.withFlag(property, 64, enabled)

def Property.withFinal(property: Property, enabled: Bool) -> Property:
  Property.withFlag(property, 128, enabled)

def Property.withRequired(property: Property, enabled: Bool) -> Property:
  Property.withFlag(property, 256, enabled)

def Property.withVirtual(property: Property, enabled: Bool) -> Property:
  Property.withFlag(property, 512, enabled)

def Property.withOverride(property: Property, enabled: Bool) -> Property:
  Property.withFlag(property, 1024, enabled)

def Property.withBindable(property: Property, enabled: Bool) -> Property:
  Property.withFlag(property, 2048, enabled)

def Property.withRevision(property: Property, minor: U32) -> Property:
  match property:
    case Property{name, argument, flags, previousMajor, previousMinor, notify}:
      Property{name, argument, U32.or(flags, 8192), 65535, minor, notify}

def Property.withVersionRevision(property: Property, major: U32, minor: U32) -> Property:
  match property:
    case Property{name, argument, flags, previousMajor, previousMinor, notify}:
      Property{name, argument, U32.or(flags, 8192), Internal.Revision.major(major), minor, notify}

def Property.withNotify(property: Property, signal: Signal) -> Property:
  match property:
    case Property{name, argument, flags, major, minor, previous}:
      Property{name, argument, U32.or(U32.and(flags, 4294963199), 16384), major, minor, [signal]}

def Property.withoutNotify(property: Property) -> Property:
  match property:
    case Property{name, argument, flags, major, minor, previous}:
      Property{name, argument, U32.or(U32.and(flags, 4294950911), 4096), major, minor, Nil{}}

def Property.argument(property: Property) -> SignalArgument:
  match property:
    case Property{name, argument, flags, major, minor, notify}: argument

def Property.name(property: Property) -> String:
  match property:
    case Property{name, argument, flags, major, minor, notify}: name

def Property.Value(property: Property) -> Data:
  SignalArgument.Value(Property.argument(property))

def Property.schema(property: Property) -> Action(Wire):
  match property:
    case Property{name, argument, flags, major, minor, notify}:
      do Action<Wire>:
        declared: Wire <- SignalArgument.schema(argument)
        change: Wire <- SignalSchemas.encode(notify)
        return WireSequence{[WireText{name}, declared, WireScalar{flags, 0}, WireScalar{major, minor}, change]}

def Property.schemas(properties: List<&1, Property>) -> Action(List<&2, Wire>):
  match properties:
    case Nil{}: Action.pure(List<&2, Wire>, Nil{})
    case property <> rest:
      do Action<List<&2, Wire>>:
        wire: Wire <- Property.schema(property)
        tail: List<&2, Wire> <- Property.schemas(rest)
        return wire <> tail

type Method is Type:
  Method{name: String, arguments: SignalArguments, result: SignalArgument, names: List<&1, String>, tag: String, flags: U32, access: QMetaMethod.Access, major: U32, minor: U32}

def Method.define(name: String, arguments: List<&1, SignalArgument>, result: SignalArgument) -> Method:
  Method{name, SignalArguments.fromList(arguments), result, Nil{}, "", 0, QMetaMethod.Access.Public(), 0, 0}

def Method.withArgumentNames(method: Method, names: List<&1, String>) -> Method:
  match method:
    case Method{name, arguments, result, previous, tag, flags, access, major, minor}:
      Method{name, arguments, result, names, tag, flags, access, major, minor}

def Method.withTag(method: Method, tag: String) -> Method:
  match method:
    case Method{name, arguments, result, names, previous, flags, access, major, minor}:
      Method{name, arguments, result, names, tag, flags, access, major, minor}

def Method.withAccess(method: Method, access: QMetaMethod.Access) -> Method:
  match method:
    case Method{name, arguments, result, names, tag, flags, previous, major, minor}:
      Method{name, arguments, result, names, tag, flags, access, major, minor}

def Method.withInvokable(method: Method, enabled: Bool) -> Method:
  match method enabled:
    case Method{name, arguments, result, names, tag, flags, access, major, minor} True{}:
      Method{name, arguments, result, names, tag, U32.or(flags, 2), access, major, minor}
    case Method{name, arguments, result, names, tag, flags, access, major, minor} False{}:
      Method{name, arguments, result, names, tag, U32.and(flags, 4294967293), access, major, minor}

def Method.withRevision(method: Method, minor: U32) -> Method:
  match method:
    case Method{name, arguments, result, names, tag, flags, access, previousMajor, previousMinor}:
      Method{name, arguments, result, names, tag, U32.or(flags, 1), access, 65535, minor}

def Method.withVersionRevision(method: Method, major: U32, minor: U32) -> Method:
  match method:
    case Method{name, arguments, result, names, tag, flags, access, previousMajor, previousMinor}:
      Method{name, arguments, result, names, tag, U32.or(flags, 1), access, Internal.Revision.major(major), minor}

def Method.argumentNamesWire(names: List<&1, String>) -> List<&2, Wire>:
  match names:
    case Nil{}: Nil{}
    case name <> rest: WireText{name} <> Method.argumentNamesWire(rest)

def Method.schema(method: Method) -> Action(Wire):
  match method:
    case Method{name, arguments, result, names, tag, flags, access, major, minor}:
      do Action<Wire>:
        types: List<&2, Wire> <- SignalArguments.names(arguments)
        output: Wire <- SignalArgument.schema(result)
        return WireSequence{[WireText{name}, WireSequence{types}, output,
          WireSequence{[WireSequence{Method.argumentNamesWire(names)}, WireText{tag}, WireScalar{flags, QMetaMethod.Access.word(access)}, WireScalar{major, minor}]}]}

def Method.schemas(methods: List<&1, Method>) -> Action(List<&2, Wire>):
  match methods:
    case Nil{}: Action.pure(List<&2, Wire>, Nil{})
    case method <> rest:
      do Action<List<&2, Wire>>:
        wire: Wire <- Method.schema(method)
        tail: List<&2, Wire> <- Method.schemas(rest)
        return wire <> tail

type QtObject is Type:
  QtObject{name: String, base: QtBase, properties: List<&1, Property>, signals: List<&1, Signal>, methods: List<&1, Method>, attached: List<&1, QtObject>, extension: List<&1, QtObject>, info: List<&1, PairValue<String, String>>, enums: List<&1, Enum>}

def Internal.QtObject.define(name: String, base: QtBase, properties: List<&1, Property>) -> QtObject:
  QtObject{name, base, properties, Nil{}, Nil{}, Nil{}, Nil{}, Nil{}, Nil{}}

def QtObject.withSignals(object: QtObject, signals: List<&1, Signal>) -> QtObject:
  match object:
    case QtObject{name, base, properties, previous, methods, attached, extension, info, enums}: QtObject{name, base, properties, signals, methods, attached, extension, info, enums}

def QtObject.withMethods(object: QtObject, methods: List<&1, Method>) -> QtObject:
  match object:
    case QtObject{name, base, properties, signals, previous, attached, extension, info, enums}: QtObject{name, base, properties, signals, methods, attached, extension, info, enums}

def QtObject.withAttached(object: QtObject, attached: QtObject) -> QtObject:
  match object:
    case QtObject{name, base, properties, signals, methods, previous, extension, info, enums}: QtObject{name, base, properties, signals, methods, [attached], extension, info, enums}

def QtObject.withExtension(object: QtObject, extension: QtObject) -> QtObject:
  match object:
    case QtObject{name, base, properties, signals, methods, attached, previous, info, enums}: QtObject{name, base, properties, signals, methods, attached, [extension], info, enums}

def QtObject.withClassInfo(object: QtObject, key: String, value: String) -> QtObject:
  match object:
    case QtObject{name, base, properties, signals, methods, attached, extension, info, enums}:
      QtObject{name, base, properties, signals, methods, attached, extension, PairValue{key, value} <> info, enums}

def QtObject.withEnums(object: QtObject, enums: List<&1, Enum>) -> QtObject:
  match object:
    case QtObject{name, base, properties, signals, methods, attached, extension, info, previous}:
      QtObject{name, base, properties, signals, methods, attached, extension, info, enums}

def QtObject.withDefaultProperty(object: QtObject, name: String) -> QtObject:
  QtObject.withClassInfo(object, "DefaultProperty", name)

def QtObject.attachedType(object: QtObject) -> QtObject:
  match object:
    case QtObject{name, base, properties, signals, methods, attached <> rest, extension, info, enums}: attached
    case QtObject{name, base, properties, signals, methods, Nil{}, extension, info, enums}: QtObject{name ++ "Attached", base, Nil{}, Nil{}, Nil{}, Nil{}, Nil{}, Nil{}, Nil{}}

def QtObject.extensionType(object: QtObject) -> QtObject:
  match object:
    case QtObject{name, base, properties, signals, methods, attached, extension <> rest, info, enums}: extension
    case QtObject{name, base, properties, signals, methods, attached, Nil{}, info, enums}: QtObject{name ++ "Extension", base, Nil{}, Nil{}, Nil{}, Nil{}, Nil{}, Nil{}, Nil{}}

def QtObject.name(object: QtObject) -> String:
  match object:
    case QtObject{name, base, properties, signals, methods, attached, extension, info, enums}: name

def QtObject.nativeBase(object: QtObject) -> QtBase:
  match object:
    case QtObject{name, base, properties, signals, methods, attached, extension, info, enums}: base

def QtObject.classInfos(info: List<&1, PairValue<String, String>>) -> List<&2, Wire>:
  match info:
    case Nil{}: Nil{}
    case PairValue{key, value} <> rest: WireSequence{[WireText{key}, WireText{value}]} <> QtObject.classInfos(rest)

def QtObject.schema(object: QtObject) -> Action(Wire):
  match object:
    case QtObject{name, QtBase{Value, native, parent, encode, decode}, properties, signals, methods, attached, extension, info, enums}:
      do Action<Wire>:
        inherited: Wire <- parent
        fields: List<&2, Wire> <- Property.schemas(properties)
        events: Wire <- SignalSchemas.encode(signals)
        functions: List<&2, Wire> <- Method.schemas(methods)
        return WireSequence{[WireText{name}, WireScalar{native, 0}, inherited,
          WireSequence{fields}, events, WireSequence{functions}, WireSequence{QtObject.classInfos(info)}, WireSequence{Enum.schemas(enums)}]}

def QtObject.optionalSchema(objects: List<&1, QtObject>) -> Action(Wire):
  match objects:
    case Nil{}: Action.pure(Wire, WireScalar{0, 0})
    case object <> rest: QtObject.schema(object)

def QtObject.attachedSchema(object: QtObject) -> Action(Wire):
  match object:
    case QtObject{name, base, properties, signals, methods, attached, extension, info, enums}: QtObject.optionalSchema(attached)

def QtObject.extensionSchema(object: QtObject) -> Action(Wire):
  match object:
    case QtObject{name, base, properties, signals, methods, attached, extension, info, enums}: QtObject.optionalSchema(extension)

def QtObject.qmlSchema(~object: QtObject) -> Action(Wire):
  do Action<Wire>:
    schema: Wire <- QtObject.schema(object)
    attached: Wire <- QtObject.attachedSchema(object)
    extension: Wire <- QtObject.extensionSchema(object)
    return WireSequence{[schema, attached, extension]}

type QtInstance<-Name: String> is Data:
  QtInstance{word: U32}

def QtObject.Instance(-object: QtObject) -> Data:
  QtInstance<QtObject.name(object)>

def QtObject.word(~object: QtObject, value: QtObject.Instance(object)) -> U32:
  match value:
    case QtInstance{word}: word

def QtObject.wrap(~object: QtObject, result: Result<&1, &1, U32 & String, U32>) -> Result<&1, &1, U32 & String, QtObject.Instance(object)>:
  match result:
    case Fail{error}: Fail{error}
    case Done{word}: Done{QtInstance{word}}

def QtObject.as_QObject(~object: QtObject, value: QtObject.Instance(object)) -> QObject:
  QObject{QtObject.word(~object, value)}

def QtBase.decode(base: QtBase, word: U32) -> QtBase.Value(base):
  match base:
    case QtBase{Value, native, parent, encode, decode}: decode(word)

def QtBase.word(base: QtBase, value: QtBase.Value(base)) -> U32:
  match base:
    case QtBase{Value, native, parent, encode, decode}: encode(value)

def QtObject.asNativeBase(~object: QtObject, value: QtObject.Instance(object)) -> QtBase.Value(QtObject.nativeBase(object)):
  QtBase.decode(QtObject.nativeBase(object), QtObject.word(~object, value))

def QtObject.base_value(~object: QtObject, base: QtBase) -> QtBase:
  match base:
    case QtBase{Value, native, parent, encode, decode}:
      QtBase{Value, native, QtObject.schema(object), encode, decode}

def QtObject.derive(~parent: QtObject, name: String, properties: List<&1, Property>) -> QtObject:
  Internal.QtObject.define(name, QtObject.base_value(~parent, QtObject.nativeBase(parent)), properties)

def QtInstance.encode(-name: String, value: QtInstance<name>) -> Wire:
  match value:
    case QtInstance{word}: WireScalar{word, 0}

def QtInstance.decode(-name: String, wire: Wire) -> Maybe<&2, QtInstance<name>>:
  match wire:
    case WireScalar{word, 0}: Some{QtInstance{word}}
    case _: None{}

def QtObject.reference(+name: String) -> SignalArgument:
  SignalArgument{QtInstance<name>, name ++ "*", value => QtInstance.encode(name, value),
    wire => QtInstance.decode(name, wire), Action.pure(Wire, WireScalar{0, 0})}

def QtObject.argument(object: QtObject) -> SignalArgument:
  match object:
    case QtObject{+name, base, properties, signals, methods, attached, extension, info, enums}:
      SignalArgument{QtInstance<name>, name ++ "*", value => QtInstance.encode(name, value),
        wire => QtInstance.decode(name, wire), QtObject.schema(QtObject{name, base, properties, signals, methods, attached, extension, info, enums})}

def QtObject.arg(~object: QtObject) -> SignalArgument:
  QtObject.argument(object)

def UnitArgument.decode(wire: Wire) -> Maybe<&2, Unit>:
  match wire:
    case WireScalar{0, 0}: Some{Unit{}}
    case _: None{}

def unit() -> SignalArgument:
  SignalArgument{Unit, "void", value => WireScalar{0, 0}, UnitArgument.decode, Action.pure(Wire, WireScalar{0, 0})}
