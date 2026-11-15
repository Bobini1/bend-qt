def QVariant.fromValue(~argument: SignalArgument, value: SignalArgument.Value(argument)) -> Action(QVariant):
  do Action<QVariant>:
    schema: Wire <- SignalArgument.schema(argument)
    Wire.withData(QVariant, SignalArgument.encode(argument, value),
      wire => QVariant.from_value_raw(schema, wire))

def QVariant.toValue(~argument: SignalArgument, value: QVariant) -> Action(SignalArgument.Value(argument)):
  do Action<SignalArgument.Value(argument)>:
    schema: Wire <- SignalArgument.schema(argument)
    Wire.withData(SignalArgument.Value(argument), QVariant.to_value_raw(value, schema),
      wire => SignalArgument.decode(argument, wire))

def QVariant.canConvert(~argument: SignalArgument, value: QVariant) -> Action(Bool):
  do Action<Bool>:
    schema: Wire <- SignalArgument.schema(argument)
    QVariant.conversion_raw(value, schema, 0)

def QVariant.convert(~argument: SignalArgument, value: QVariant) -> Action(Bool):
  do Action<Bool>:
    schema: Wire <- SignalArgument.schema(argument)
    QVariant.conversion_raw(value, schema, 1)
