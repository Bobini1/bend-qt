# Schema-aware member access preserves the instance type at the call site.
def ObjectType.get(~object: ObjectType, ~property: Property, self: ObjectType.Instance(object)) -> Action(Property.Value(property)):
  Property.get(~property, ObjectType.as_QObject(~object, self))

def ObjectType.set(~object: ObjectType, ~property: Property, self: ObjectType.Instance(object), value: Property.Value(property)) -> Action(Unit):
  Property.set(~property, ObjectType.as_QObject(~object, self), value)

def ObjectType.readStorage(~object: ObjectType, ~property: Property, self: ObjectType.Instance(object)) -> Action(Property.Value(property)):
  Property.readStorage(~property, ObjectType.as_QObject(~object, self))

def ObjectType.writeStorage(~object: ObjectType, ~property: Property, self: ObjectType.Instance(object), value: Property.Value(property)) -> Action(Unit):
  Property.writeStorage(~property, ObjectType.as_QObject(~object, self), value)

def ObjectType.notify(~object: ObjectType, ~property: Property, self: ObjectType.Instance(object)) -> Action(Unit):
  Property.notify(~property, ObjectType.as_QObject(~object, self))

def ObjectType.reset(~object: ObjectType, ~property: Property, self: ObjectType.Instance(object)) -> Action(Unit):
  Property.reset(~property, ObjectType.as_QObject(~object, self))

def ObjectType.unbind(~object: ObjectType, ~property: Property, self: ObjectType.Instance(object)) -> Action(Unit):
  Property.unbind(~property, ObjectType.as_QObject(~object, self))

def ObjectType.hasBinding(~object: ObjectType, ~property: Property, self: ObjectType.Instance(object)) -> Action(Bool):
  Property.hasBinding(~property, ObjectType.as_QObject(~object, self))

def ObjectType.bind(~object: ObjectType, ~property: Property, ~source: ObjectType, ~sourceProperty: Property, self: ObjectType.Instance(object), other: ObjectType.Instance(source)) -> Action(Unit):
  Property.bind(~property, ~sourceProperty, ObjectType.as_QObject(~object, self), ObjectType.as_QObject(~source, other))

def ObjectType.call(~object: ObjectType, ~method: Method, self: ObjectType.Instance(object)) -> Method.Handler(~method):
  Method.call(~method, ObjectType.as_QObject(~object, self))

def ObjectType.handle(~object: ObjectType, ~method: Method, ~S: Data, ~f: S -> Method.Handler(~method), self: ObjectType.Instance(object), state: S) -> Action(Unit):
  Method.handle(~method, ~S, ~f, ObjectType.as_QObject(~object, self), state)

def ObjectType.handleGetter(~object: ObjectType, ~property: Property, ~S: Data, ~f: S -> Method.Handler(~Property.getter(property)), self: ObjectType.Instance(object), state: S) -> Action(Unit):
  Property.handleGetter(~property, ~S, ~f, ObjectType.as_QObject(~object, self), state)

def ObjectType.handleSetter(~object: ObjectType, ~property: Property, ~S: Data, ~f: S -> Method.Handler(~Property.setter(property)), self: ObjectType.Instance(object), state: S) -> Action(Unit):
  Property.handleSetter(~property, ~S, ~f, ObjectType.as_QObject(~object, self), state)

def ObjectType.handleResetter(~object: ObjectType, ~property: Property, ~S: Data, ~f: S -> Method.Handler(~Property.resetter(property)), self: ObjectType.Instance(object), state: S) -> Action(Unit):
  Property.handleResetter(~property, ~S, ~f, ObjectType.as_QObject(~object, self), state)

def ObjectType.handleBinding(~object: ObjectType, ~property: Property, ~S: Data, ~f: S -> Method.Handler(~Property.getter(property)), self: ObjectType.Instance(object), state: S) -> Action(Unit):
  Property.handleBinding(~property, ~S, ~f, ObjectType.as_QObject(~object, self), state)

def ObjectType.emit(~object: ObjectType, ~signal: Signal, self: ObjectType.Instance(object)) -> SignalArguments.Handler(Signal.arguments(signal)):
  Signal.emit(~signal, ObjectType.as_QObject(~object, self))

def ObjectType.connect(~object: ObjectType, ~signal: Signal, ~S: Data, ~f: S -> SignalArguments.Handler(Signal.arguments(signal)), self: ObjectType.Instance(object), state: S) -> Action(Connection):
  Signal.connect(~signal, ~S, ~f, ObjectType.as_QObject(~object, self), state)

def ObjectType.connectWith(~object: ObjectType, ~signal: Signal, ~S: Data, ~f: S -> SignalArguments.Handler(Signal.arguments(signal)), self: ObjectType.Instance(object), connectionType: Qt.ConnectionType, state: S) -> Action(Connection):
  Signal.connectWith(~signal, ~S, ~f, ObjectType.as_QObject(~object, self), connectionType, state)

def ObjectType.connectMethod(~object: ObjectType, ~signal: Signal, ~receiver: ObjectType, ~method: Method, self: ObjectType.Instance(object), target: ObjectType.Instance(receiver)) -> Action(Connection):
  Signal.connectMethod(~signal, ~method, ObjectType.as_QObject(~object, self), ObjectType.as_QObject(~receiver, target))

def ObjectType.connectSignal(~object: ObjectType, ~signal: Signal, ~receiver: ObjectType, ~destination: Signal, self: ObjectType.Instance(object), target: ObjectType.Instance(receiver)) -> Action(Connection):
  Signal.connectSignal(~signal, ~destination, ObjectType.as_QObject(~object, self), ObjectType.as_QObject(~receiver, target))

def ObjectType.connectMethodWith(~object: ObjectType, ~signal: Signal, ~receiver: ObjectType, ~method: Method, self: ObjectType.Instance(object), target: ObjectType.Instance(receiver), connectionType: Qt.ConnectionType) -> Action(Connection):
  Signal.connectMethodWith(~signal, ~method, ObjectType.as_QObject(~object, self), ObjectType.as_QObject(~receiver, target), connectionType)

def ObjectType.connectSignalWith(~object: ObjectType, ~signal: Signal, ~receiver: ObjectType, ~destination: Signal, self: ObjectType.Instance(object), target: ObjectType.Instance(receiver), connectionType: Qt.ConnectionType) -> Action(Connection):
  Signal.connectSignalWith(~signal, ~destination, ObjectType.as_QObject(~object, self), ObjectType.as_QObject(~receiver, target), connectionType)
