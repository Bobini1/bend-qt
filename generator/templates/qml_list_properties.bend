def qmlList(element: TypeDescriptor) -> TypeDescriptor:
  QmlListArgument{element}

def Property.qmlList(name: String, element: TypeDescriptor) -> Property:
  Property.readOnly(name, qmlList(element))

def Internal.ListProperty.element(argument: TypeDescriptor) -> TypeDescriptor:
  match argument:
    case QmlListArgument{element}: element
    case _: unit()

def ListProperty.element(property: Property) -> TypeDescriptor:
  Internal.ListProperty.element(Property.argument(property))

def ListProperty.Element(property: Property) -> Data:
  TypeDescriptor.Value(ListProperty.element(property))

def ListProperty.withAppend(property: Property, enabled: Bool) -> Property:
  Property.withFlag(property, 65536, Bool.not(enabled))

def ListProperty.withCount(property: Property, enabled: Bool) -> Property:
  Property.withFlag(property, 131072, Bool.not(enabled))

def ListProperty.withAt(property: Property, enabled: Bool) -> Property:
  Property.withFlag(property, 262144, Bool.not(enabled))

def ListProperty.withClear(property: Property, enabled: Bool) -> Property:
  Property.withFlag(property, 524288, Bool.not(enabled))

def ListProperty.withReplace(property: Property, enabled: Bool) -> Property:
  Property.withFlag(property, 1048576, Bool.not(enabled))

def ListProperty.withRemoveLast(property: Property, enabled: Bool) -> Property:
  Property.withFlag(property, 2097152, Bool.not(enabled))

def ListProperty.appendMethod(property: Property) -> Method:
  match property:
    case Property{name, argument, flags, major, minor, notify}: Method.define(name, [Internal.ListProperty.element(argument)], unit())

def ListProperty.countMethod(property: Property) -> Method:
  Method.define(Property.name(property), Nil{}, int64())

def ListProperty.atMethod(property: Property) -> Method:
  match property:
    case Property{name, argument, flags, major, minor, notify}: Method.define(name, [int64()], Internal.ListProperty.element(argument))

def ListProperty.clearMethod(property: Property) -> Method:
  Method.define(Property.name(property), Nil{}, unit())

def ListProperty.replaceMethod(property: Property) -> Method:
  match property:
    case Property{name, argument, flags, major, minor, notify}: Method.define(name, [int64(), Internal.ListProperty.element(argument)], unit())

def ListProperty.removeLastMethod(property: Property) -> Method:
  Method.define(Property.name(property), Nil{}, unit())

def Internal.ListProperty.call(~property: Property, self: QObject, kind: U32, storage: U32, index: Int64, value: Wire) -> Action(Wire):
  do Action<Wire>:
    schema: Wire <- Property.schema(property)
    Internal.ListProperty.operate(self, schema, kind, storage, Convert_Int64.encode(index), value)

def Internal.ListProperty.change(~property: Property, self: QObject, kind: U32, storage: U32, index: Int64, value: ListProperty.Element(property)) -> Action(Unit):
  Wire.withData(Unit, TypeDescriptor.encode(ListProperty.element(property), value), encoded =>
    Wire.withData(Unit, Internal.ListProperty.call(~property, self, kind, storage, index, encoded), wire => Action.pure(Unit, Unit{})))

def Internal.ListProperty.count(~property: Property, self: QObject, storage: U32) -> Action(Int64):
  Wire.withData(Int64, Internal.ListProperty.call(~property, self, 1, storage, Int64{0, 0}, WireScalar{0, 0}),
    wire => TypeDescriptor.decode(int64(), wire))

def Internal.ListProperty.at(~property: Property, self: QObject, storage: U32, index: Int64) -> Action(ListProperty.Element(property)):
  Wire.withData(ListProperty.Element(property), Internal.ListProperty.call(~property, self, 2, storage, index, WireScalar{0, 0}),
    wire => TypeDescriptor.decode(ListProperty.element(property), wire))

def Internal.ListProperty.unit(~property: Property, self: QObject, kind: U32, storage: U32) -> Action(Unit):
  Wire.withData(Unit, Internal.ListProperty.call(~property, self, kind, storage, Int64{0, 0}, WireScalar{0, 0}), wire => Action.pure(Unit, Unit{}))

def ListProperty.append(~property: Property, self: QObject, value: ListProperty.Element(property)) -> Action(Unit):
  Internal.ListProperty.change(~property, self, 0, 0, Int64{0, 0}, value)

def ListProperty.count(~property: Property, self: QObject) -> Action(Int64):
  Internal.ListProperty.count(~property, self, 0)

def ListProperty.at(~property: Property, self: QObject, index: Int64) -> Action(ListProperty.Element(property)):
  Internal.ListProperty.at(~property, self, 0, index)

def ListProperty.clear(~property: Property, self: QObject) -> Action(Unit):
  Internal.ListProperty.unit(~property, self, 3, 0)

def ListProperty.replace(~property: Property, self: QObject, index: Int64, value: ListProperty.Element(property)) -> Action(Unit):
  Internal.ListProperty.change(~property, self, 4, 0, index, value)

def ListProperty.removeLast(~property: Property, self: QObject) -> Action(Unit):
  Internal.ListProperty.unit(~property, self, 5, 0)

def ListProperty.appendStorage(~property: Property, self: QObject, value: ListProperty.Element(property)) -> Action(Unit):
  Internal.ListProperty.change(~property, self, 0, 1, Int64{0, 0}, value)

def ListProperty.countStorage(~property: Property, self: QObject) -> Action(Int64):
  Internal.ListProperty.count(~property, self, 1)

def ListProperty.atStorage(~property: Property, self: QObject, index: Int64) -> Action(ListProperty.Element(property)):
  Internal.ListProperty.at(~property, self, 1, index)

def ListProperty.clearStorage(~property: Property, self: QObject) -> Action(Unit):
  Internal.ListProperty.unit(~property, self, 3, 1)

def ListProperty.replaceStorage(~property: Property, self: QObject, index: Int64, value: ListProperty.Element(property)) -> Action(Unit):
  Internal.ListProperty.change(~property, self, 4, 1, index, value)

def ListProperty.removeLastStorage(~property: Property, self: QObject) -> Action(Unit):
  Internal.ListProperty.unit(~property, self, 5, 1)

def QmlListView.reference(~element: TypeDescriptor, value: QmlListView<TypeDescriptor.name(element)>) -> Action(QQmlListReference):
  match value:
    case QmlListView{word}: Internal.QmlListView.reference(word)

def QmlListView.release(-element: String, value: QmlListView<element>) -> Action(Unit):
  match value:
    case QmlListView{word}: QVariant.release(QVariant{word})

def QmlListView.with(-element: String, -A: Type, acquire: Action(QmlListView<element>), body: QmlListView<element> -> Action(A)) -> Action(A):
  Action.using(QmlListView<element>, A, acquire, value => Action.cleanup(QmlListView.release(element, value)), body)
