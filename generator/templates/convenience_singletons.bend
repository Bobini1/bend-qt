def QQmlEngine.singletonInstance(~argument: TypeDescriptor, self: QQmlEngine, uri: String, name: String) -> Action(TypeDescriptor.Value(argument)):
  do Action<TypeDescriptor.Value(argument)>:
    schema: Wire <- TypeDescriptor.schema(argument)
    Wire.withData(TypeDescriptor.Value(argument), Internal.Qml.singleton_raw(self, schema, 1, Int32{0}, uri, name),
      wire => TypeDescriptor.decode(argument, wire))

def QQmlEngine.singletonInstanceById(~argument: TypeDescriptor, self: QQmlEngine, id: Int32) -> Action(TypeDescriptor.Value(argument)):
  do Action<TypeDescriptor.Value(argument)>:
    schema: Wire <- TypeDescriptor.schema(argument)
    Wire.withData(TypeDescriptor.Value(argument), Internal.Qml.singleton_raw(self, schema, 0, id, "", ""),
      wire => TypeDescriptor.decode(argument, wire))
