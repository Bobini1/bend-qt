# Registration controllers are distinct from the objects QML creates.
type QmlRegistration<-Name: String> is Data:
  QmlRegistration{word: U32}

def Qml.Registration(-object: ObjectType) -> Data:
  QmlRegistration<ObjectType.name(object)>

type Qml.RegistrationHandle is Data:
  QmlRegistrationHandle{word: U32}

def Internal.Qml.registrationWord(-name: String, value: QmlRegistration<name>) -> U32:
  match value:
    case QmlRegistration{word}: word

def Qml.Registration.word(~object: ObjectType, value: Qml.Registration(object)) -> U32:
  Internal.Qml.registrationWord(ObjectType.name(object), value)

def Internal.Qml.registrationObject(~object: ObjectType, value: Qml.Registration(object)) -> QObject:
  QObject{Internal.Qml.registrationWord(ObjectType.name(object), value)}

def Internal.Qml.registrationResult(-name: String, acquire: Action(QObject)) -> Action(QmlRegistration<name>):
  Action.bind(QObject, QmlRegistration<name>, acquire,
    value => Action.pure(QmlRegistration<name>, QmlRegistration{QObject.word(value)}))

def Internal.Qml.registrationHandleResult(acquire: Action(QObject)) -> Action(Qml.RegistrationHandle):
  Action.bind(QObject, Qml.RegistrationHandle, acquire,
    value => Action.pure(Qml.RegistrationHandle, QmlRegistrationHandle{QObject.word(value)}))

def Qml.Registration.release(~object: ObjectType, value: Qml.Registration(object)) -> Action(Unit):
  QObject.release(Internal.Qml.registrationObject(~object, value))

def Qml.Registration.destroy(~object: ObjectType, value: Qml.Registration(object)) -> Action(Unit):
  QObject.destroy(Internal.Qml.registrationObject(~object, value))

def Qml.Registration.moveToParentScope(~object: ObjectType, value: Qml.Registration(object)) -> Action(Qml.Registration(object)):
  Internal.Qml.registrationResult(ObjectType.name(object),
    QObject.moveToParentScope(Internal.Qml.registrationObject(~object, value)))

def Qml.Registration.detachFromScope(~object: ObjectType, value: Qml.Registration(object)) -> Action(Qml.Registration(object)):
  Internal.Qml.registrationResult(ObjectType.name(object),
    QObject.detachFromScope(Internal.Qml.registrationObject(~object, value)))

def Qml.Registration.with(~object: ObjectType, -A: Type, acquire: Action(Qml.Registration(object)), body: Qml.Registration(object) -> Action(A)) -> Action(A):
  Action.using(Qml.Registration(object), A, acquire,
    value => Action.cleanup(Qml.Registration.release(~object, value)), body)

def Qml.RegistrationHandle.word(value: Qml.RegistrationHandle) -> U32:
  match value:
    case QmlRegistrationHandle{word}: word

def Qml.RegistrationHandle.wrap(result: Result<&1, &1, U32 & String, U32>) -> Result<&1, &1, U32 & String, Qml.RegistrationHandle>:
  match result:
    case Fail{error}: Fail{error}
    case Done{word}: Done{QmlRegistrationHandle{word}}

def Qml.RegistrationHandle.release(value: Qml.RegistrationHandle) -> Action(Unit):
  QObject.release(QObject{Qml.RegistrationHandle.word(value)})

def Qml.RegistrationHandle.destroy(value: Qml.RegistrationHandle) -> Action(Unit):
  QObject.destroy(QObject{Qml.RegistrationHandle.word(value)})

def Qml.RegistrationHandle.moveToParentScope(value: Qml.RegistrationHandle) -> Action(Qml.RegistrationHandle):
  Internal.Qml.registrationHandleResult(QObject.moveToParentScope(QObject{Qml.RegistrationHandle.word(value)}))

def Qml.RegistrationHandle.detachFromScope(value: Qml.RegistrationHandle) -> Action(Qml.RegistrationHandle):
  Internal.Qml.registrationHandleResult(QObject.detachFromScope(QObject{Qml.RegistrationHandle.word(value)}))

def Qml.RegistrationHandle.with(-A: Type, acquire: Action(Qml.RegistrationHandle), body: Qml.RegistrationHandle -> Action(A)) -> Action(A):
  Action.using(Qml.RegistrationHandle, A, acquire,
    value => Action.cleanup(Qml.RegistrationHandle.release(value)), body)
