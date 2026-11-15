def Qml.factoryMethod(object: QtObject) -> Method:
  Method.define("createSingleton", [QQmlEngine.arg()], QtObject.argument(object))

def Qml.creationMethod(object: QtObject) -> Method:
  Method.define("initialize", [QtObject.argument(object)], unit())

def Qml.constructorMethod(object: QtObject) -> Method:
  Method.define("construct", [], QtObject.argument(object))

def Qml.attachedMethod(object: QtObject) -> Method:
  Method.define("createAttached", [QObject.arg()], QtObject.argument(QtObject.attachedType(object)))

def Qml.extensionMethod(object: QtObject) -> Method:
  Method.define("createExtension", [QObject.arg()], QtObject.argument(QtObject.extensionType(object)))

def Qml.registerType(~object: QtObject, uri: String, major: U32, minor: U32, name: String) -> Action(QObject):
  do Action<QObject>:
    schema: Wire <- QtObject.qmlSchema(object)
    Qml.type_raw(schema, uri, major, minor, name)

def Qml.registerTypeRevision(~object: QtObject, uri: String, major: U32, minor: U32, name: String, revision: U32) -> Action(QObject):
  do Action<QObject>:
    schema: Wire <- QtObject.qmlSchema(object)
    Qml.type_revision_raw(schema, uri, major, minor, name, WireScalar{65535, revision})

def Qml.registerTypeVersionRevision(~object: QtObject, uri: String, major: U32, minor: U32, name: String, revisionMajor: U32, revisionMinor: U32) -> Action(QObject):
  do Action<QObject>:
    schema: Wire <- QtObject.qmlSchema(object)
    Qml.type_revision_raw(schema, uri, major, minor, name, WireScalar{Internal.Revision.major(revisionMajor), revisionMinor})

def Qml.registerUncreatable(~object: QtObject, uri: String, major: U32, minor: U32, name: String, reason: String) -> Action(QObject):
  do Action<QObject>:
    schema: Wire <- QtObject.qmlSchema(object)
    Qml.type_mode_raw(schema, uri, major, minor, name, 1, reason)

def Qml.registerAnonymous(~object: QtObject, uri: String, major: U32) -> Action(QObject):
  do Action<QObject>:
    schema: Wire <- QtObject.qmlSchema(object)
    Qml.type_mode_raw(schema, uri, major, 0, "", 2, "")

def Qml.registerUnavailable(uri: String, major: U32, minor: U32, name: String, reason: String) -> Action(QObject):
  Qml.unavailable_raw(uri, major, minor, name, reason)

def Qml.attached(~object: QtObject, registration: QObject, target: QObject) -> Action(QtObject.Instance(QtObject.attachedType(object))):
  do Action<QtObject.Instance(QtObject.attachedType(object))>:
    schema: Wire <- QtObject.qmlSchema(object)
    word: U32 <- Qml.related_raw(registration, target, schema, 0)
    return QtInstance{word}

def Qml.extension(~object: QtObject, registration: QObject, target: QtObject.Instance(object)) -> Action(QtObject.Instance(QtObject.extensionType(object))):
  do Action<QtObject.Instance(QtObject.extensionType(object))>:
    schema: Wire <- QtObject.qmlSchema(object)
    word: U32 <- Qml.related_raw(registration, QtObject.as_QObject(~object, target), schema, 1)
    return QtInstance{word}

def Qml.registerSingletonVersionRevision(~object: QtObject, uri: String, major: U32, minor: U32, name: String, revisionMajor: U32, revisionMinor: U32) -> Action(QObject):
  do Action<QObject>:
    schema: Wire <- QtObject.qmlSchema(object)
    Qml.singleton_raw(schema, uri, major, minor, name, QObject{0}, 0, WireScalar{Internal.Revision.major(revisionMajor), revisionMinor})

def Qml.registerSingletonRevision(~object: QtObject, uri: String, major: U32, minor: U32, name: String, revision: U32) -> Action(QObject):
  do Action<QObject>:
    schema: Wire <- QtObject.qmlSchema(object)
    Qml.singleton_raw(schema, uri, major, minor, name, QObject{0}, 0, WireScalar{65535, revision})

def Qml.registerSingleton(~object: QtObject, uri: String, major: U32, minor: U32, name: String) -> Action(QObject):
  do Action<QObject>:
    schema: Wire <- QtObject.qmlSchema(object)
    Qml.singleton_raw(schema, uri, major, minor, name, QObject{0}, 0, WireScalar{65535, 0})

def Qml.registerSingletonInstanceVersionRevision(~object: QtObject, uri: String, major: U32, minor: U32, name: String, revisionMajor: U32, revisionMinor: U32, instance: QtObject.Instance(object)) -> Action(QObject):
  do Action<QObject>:
    schema: Wire <- QtObject.qmlSchema(object)
    Qml.singleton_raw(schema, uri, major, minor, name, QtObject.as_QObject(~object, instance), 1, WireScalar{Internal.Revision.major(revisionMajor), revisionMinor})

def Qml.registerSingletonInstanceRevision(~object: QtObject, uri: String, major: U32, minor: U32, name: String, revision: U32, instance: QtObject.Instance(object)) -> Action(QObject):
  do Action<QObject>:
    schema: Wire <- QtObject.qmlSchema(object)
    Qml.singleton_raw(schema, uri, major, minor, name, QtObject.as_QObject(~object, instance), 1, WireScalar{65535, revision})

def Qml.registerSingletonInstance(~object: QtObject, uri: String, major: U32, minor: U32, name: String, instance: QtObject.Instance(object)) -> Action(QObject):
  do Action<QObject>:
    schema: Wire <- QtObject.qmlSchema(object)
    Qml.singleton_raw(schema, uri, major, minor, name, QtObject.as_QObject(~object, instance), 1, WireScalar{65535, 0})
