def QQmlEngine.singletonInstance(~argument: SignalArgument, self: QQmlEngine, uri: String, name: String) -> Action(SignalArgument.Value(argument)):
  do Action<SignalArgument.Value(argument)>:
    schema: Wire <- SignalArgument.schema(argument)
    Wire.withData(SignalArgument.Value(argument), Internal.Qml.singleton_raw(self, schema, 1, Int32{0}, uri, name),
      wire => SignalArgument.decode(argument, wire))

def QQmlEngine.singletonInstanceById(~argument: SignalArgument, self: QQmlEngine, id: Int32) -> Action(SignalArgument.Value(argument)):
  do Action<SignalArgument.Value(argument)>:
    schema: Wire <- SignalArgument.schema(argument)
    Wire.withData(SignalArgument.Value(argument), Internal.Qml.singleton_raw(self, schema, 0, id, "", ""),
      wire => SignalArgument.decode(argument, wire))
