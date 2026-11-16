def QVariant.fromValue(~argument: TypeDescriptor, value: TypeDescriptor.Value(argument)) -> Action(QVariant):
  do Action<QVariant>:
    schema: Wire <- TypeDescriptor.schema(argument)
    Wire.withData(QVariant, TypeDescriptor.encode(argument, value),
      wire => QVariant.from_value_raw(schema, wire))

def QVariant.toValue(~argument: TypeDescriptor, value: QVariant) -> Action(TypeDescriptor.Value(argument)):
  do Action<TypeDescriptor.Value(argument)>:
    schema: Wire <- TypeDescriptor.schema(argument)
    Wire.withData(TypeDescriptor.Value(argument), QVariant.to_value_raw(value, schema),
      wire => TypeDescriptor.decode(argument, wire))

def QVariant.canConvert(~argument: TypeDescriptor, value: QVariant) -> Action(Bool):
  do Action<Bool>:
    schema: Wire <- TypeDescriptor.schema(argument)
    QVariant.conversion_raw(value, schema, 0)

def QVariant.convert(~argument: TypeDescriptor, value: QVariant) -> Action(Bool):
  do Action<Bool>:
    schema: Wire <- TypeDescriptor.schema(argument)
    QVariant.conversion_raw(value, schema, 1)
