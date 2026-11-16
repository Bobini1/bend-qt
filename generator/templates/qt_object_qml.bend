def Qml.factoryMethod(object: ObjectType) -> Method:
  Method.define("createSingleton", [QQmlEngine.arg()], ObjectType.argument(object))

def Qml.creationMethod(object: ObjectType) -> Method:
  Method.define("initialize", [ObjectType.argument(object)], unit())

def Qml.constructorMethod(object: ObjectType) -> Method:
  Method.define("construct", [], ObjectType.argument(object))

def Qml.attachedMethod(object: ObjectType) -> Method:
  Method.define("createAttached", [QObject.arg()], ObjectType.argument(ObjectType.attachedType(object)))

def Qml.extensionMethod(object: ObjectType) -> Method:
  Method.define("createExtension", [QObject.arg()], ObjectType.argument(ObjectType.extensionType(object)))

def Qml.registerType(~object: ObjectType, uri: String, major: U32, minor: U32, name: String) -> Action(Qml.Registration(object)):
  do Action<Qml.Registration(object)>:
    schema: Wire <- ObjectType.qmlSchema(object)
    Internal.Qml.registrationResult(ObjectType.name(object), Qml.type_raw(schema, uri, major, minor, name))

def Qml.registerTypeRevision(~object: ObjectType, uri: String, major: U32, minor: U32, name: String, revision: U32) -> Action(Qml.Registration(object)):
  do Action<Qml.Registration(object)>:
    schema: Wire <- ObjectType.qmlSchema(object)
    Internal.Qml.registrationResult(ObjectType.name(object), Qml.type_revision_raw(schema, uri, major, minor, name, WireScalar{65535, revision}))

def Qml.registerTypeVersionRevision(~object: ObjectType, uri: String, major: U32, minor: U32, name: String, revisionMajor: U32, revisionMinor: U32) -> Action(Qml.Registration(object)):
  do Action<Qml.Registration(object)>:
    schema: Wire <- ObjectType.qmlSchema(object)
    Internal.Qml.registrationResult(ObjectType.name(object), Qml.type_revision_raw(schema, uri, major, minor, name, WireScalar{Internal.Revision.major(revisionMajor), revisionMinor}))

def Qml.registerUncreatable(~object: ObjectType, uri: String, major: U32, minor: U32, name: String, reason: String) -> Action(Qml.Registration(object)):
  do Action<Qml.Registration(object)>:
    schema: Wire <- ObjectType.qmlSchema(object)
    Internal.Qml.registrationResult(ObjectType.name(object), Qml.type_mode_raw(schema, uri, major, minor, name, 1, reason))

def Qml.registerAnonymous(~object: ObjectType, uri: String, major: U32) -> Action(Qml.Registration(object)):
  do Action<Qml.Registration(object)>:
    schema: Wire <- ObjectType.qmlSchema(object)
    Internal.Qml.registrationResult(ObjectType.name(object), Qml.type_mode_raw(schema, uri, major, 0, "", 2, ""))

def Qml.registerUnavailable(uri: String, major: U32, minor: U32, name: String, reason: String) -> Action(Qml.RegistrationHandle):
  Internal.Qml.registrationHandleResult(Qml.unavailable_raw(uri, major, minor, name, reason))

def Qml.attached(~object: ObjectType, registration: Qml.Registration(object), target: QObject) -> Action(ObjectType.Instance(ObjectType.attachedType(object))):
  do Action<ObjectType.Instance(ObjectType.attachedType(object))>:
    schema: Wire <- ObjectType.qmlSchema(object)
    word: U32 <- Qml.related_raw(Internal.Qml.registrationObject(~object, registration), target, schema, 0)
    return QtInstance{word}

def Qml.extension(~object: ObjectType, registration: Qml.Registration(object), target: ObjectType.Instance(object)) -> Action(ObjectType.Instance(ObjectType.extensionType(object))):
  do Action<ObjectType.Instance(ObjectType.extensionType(object))>:
    schema: Wire <- ObjectType.qmlSchema(object)
    word: U32 <- Qml.related_raw(Internal.Qml.registrationObject(~object, registration), ObjectType.as_QObject(~object, target), schema, 1)
    return QtInstance{word}

def Qml.registerSingletonVersionRevision(~object: ObjectType, uri: String, major: U32, minor: U32, name: String, revisionMajor: U32, revisionMinor: U32) -> Action(Qml.Registration(object)):
  do Action<Qml.Registration(object)>:
    schema: Wire <- ObjectType.qmlSchema(object)
    Internal.Qml.registrationResult(ObjectType.name(object), Qml.singleton_raw(schema, uri, major, minor, name, QObject{0}, 0, WireScalar{Internal.Revision.major(revisionMajor), revisionMinor}))

def Qml.registerSingletonRevision(~object: ObjectType, uri: String, major: U32, minor: U32, name: String, revision: U32) -> Action(Qml.Registration(object)):
  do Action<Qml.Registration(object)>:
    schema: Wire <- ObjectType.qmlSchema(object)
    Internal.Qml.registrationResult(ObjectType.name(object), Qml.singleton_raw(schema, uri, major, minor, name, QObject{0}, 0, WireScalar{65535, revision}))

def Qml.registerSingleton(~object: ObjectType, uri: String, major: U32, minor: U32, name: String) -> Action(Qml.Registration(object)):
  do Action<Qml.Registration(object)>:
    schema: Wire <- ObjectType.qmlSchema(object)
    Internal.Qml.registrationResult(ObjectType.name(object), Qml.singleton_raw(schema, uri, major, minor, name, QObject{0}, 0, WireScalar{65535, 0}))

def Qml.registerSingletonInstanceVersionRevision(~object: ObjectType, uri: String, major: U32, minor: U32, name: String, revisionMajor: U32, revisionMinor: U32, instance: ObjectType.Instance(object)) -> Action(Qml.Registration(object)):
  do Action<Qml.Registration(object)>:
    schema: Wire <- ObjectType.qmlSchema(object)
    Internal.Qml.registrationResult(ObjectType.name(object), Qml.singleton_raw(schema, uri, major, minor, name, ObjectType.as_QObject(~object, instance), 1, WireScalar{Internal.Revision.major(revisionMajor), revisionMinor}))

def Qml.registerSingletonInstanceRevision(~object: ObjectType, uri: String, major: U32, minor: U32, name: String, revision: U32, instance: ObjectType.Instance(object)) -> Action(Qml.Registration(object)):
  do Action<Qml.Registration(object)>:
    schema: Wire <- ObjectType.qmlSchema(object)
    Internal.Qml.registrationResult(ObjectType.name(object), Qml.singleton_raw(schema, uri, major, minor, name, ObjectType.as_QObject(~object, instance), 1, WireScalar{65535, revision}))

def Qml.registerSingletonInstance(~object: ObjectType, uri: String, major: U32, minor: U32, name: String, instance: ObjectType.Instance(object)) -> Action(Qml.Registration(object)):
  do Action<Qml.Registration(object)>:
    schema: Wire <- ObjectType.qmlSchema(object)
    Internal.Qml.registrationResult(ObjectType.name(object), Qml.singleton_raw(schema, uri, major, minor, name, ObjectType.as_QObject(~object, instance), 1, WireScalar{65535, 0}))