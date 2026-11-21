import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def expected(-A: Type, result: Result<&1, &1, U32 & String, A>, code: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(actual, message)}: require(U32.is_eq(actual, code), message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected callback lifetime rejection")

def calls() -> Qt.Property:
  Qt.Property.define("calls", Qt.u32())

def saved() -> Qt.Property:
  Qt.Property.define("saved", Qt.u32())

def body() -> Qt.Property:
  Qt.Property.define("body", Qt.string())

def Model() -> Qt.ObjectType:
  Qt.QObject.define("CallbackSurfaceState", [calls(), saved(), body()])

def increment(+state: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    count: U32 <- Qt.Property.get(~calls(), state)
    Qt.Property.writeStorage(~calls(), state, U32.add(count, 1))

def permission_body(+state: Qt.QObject, result: Qt.QPermission) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    status: Qt.Qt.PermissionStatus <- Qt.QPermission.status(result)
    require(Bool.not(U32.is_eq(Qt.Qt.PermissionStatus.word(status), 0)), "A permission callback returned Undetermined")
    increment(state)

def permission(state: Qt.QObject, result: Qt.QPermission) -> Qt.Action(Unit):
  permission_body(state, result)

def completed_body(+state: Qt.QObject, +reply: Qt.QRestReply) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    text: String <- Qt.QRestReply.readText(reply)
    Qt.Property.writeStorage(~body(), state, text)
    Qt.Property.writeStorage(~saved(), state, Qt.QRestReply.word(reply))
    increment(state)

def completed(state: Qt.QObject, reply: Qt.QRestReply) -> Qt.Action(Unit):
  completed_body(state, reply)

def failed(state: Unit, reply: Qt.QRestReply) -> Qt.Action(Unit):
  Qt.Action.fail(Unit, 94, "Expected REST callback failure")

def tick(state: Qt.QObject) -> Qt.Action(Unit):
  increment(state)

def failed_tick(state: Unit) -> Qt.Action(Unit):
  Qt.Action.fail(Unit, 96, "Expected single-shot failure")

def resolved_body(+state: Qt.QObject, +result: Qt.QHostInfo) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    error: Qt.QHostInfo.HostInfoError <- Qt.QHostInfo.error(result)
    require(U32.is_eq(Qt.QHostInfo.HostInfoError.word(error), 0), "Resolving localhost failed")
    name: String <- Qt.QHostInfo.hostName(result)
    Qt.Property.writeStorage(~body(), state, name)
    increment(state)

def resolved(state: Qt.QObject, result: Qt.QHostInfo) -> Qt.Action(Unit):
  resolved_body(state, result)

def timers_and_lookup() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +instance: Qt.ObjectType.Instance(Model()) <- Qt.ObjectType.new(~Model())
    +state: Qt.QObject = Qt.ObjectType.as_QObject(~Model(), instance)
    Qt.QTimer.singleShotWithHandler__Int32(~Qt.QObject, ~tick, Qt.Int32{0}, state)
    Qt.QTimer.singleShotWithHandler__Int32_QObject(~Qt.QObject, ~tick, Qt.Int32{0}, state, state)
    done: Bool <- Qt.CallbackProbe.waitCalls(state, 2)
    require(done, "The static single-shot callbacks did not run")
    +cancelled: Qt.QObject <- Qt.QObject.new()
    Qt.QTimer.singleShotWithHandler__Int32_QObject(~Unit, ~failed_tick, Qt.Int32{0}, cancelled, Unit{})
    Qt.QObject.destroy(cancelled)
    Qt.QCoreApplication.processEvents()
    _: Qt.Int32 <- Qt.QHostInfo.lookupHostWithHandler(~Qt.QObject, ~resolved, "localhost", state)
    done: Bool <- Qt.CallbackProbe.waitCalls(state, 3)
    require(done, "The static host lookup callback did not run")
    Qt.QTimer.singleShotWithHandler__Int32(~Unit, ~failed_tick, Qt.Int32{0}, Unit{})
    result: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.CallbackProbe.waitCalls(state, 4))
    expected(Bool, result, 96)

def permissions() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +instance: Qt.ObjectType.Instance(Model()) <- Qt.ObjectType.new(~Model())
    +state: Qt.QObject = Qt.ObjectType.as_QObject(~Model(), instance)
    app: Qt.QCoreApplication <- Qt.QCoreApplication.instance()
    camera: Qt.QCameraPermission <- Qt.QCameraPermission.new()
    Qt.QCoreApplication.requestPermissionWithHandler__QCameraPermission_QObject(~Qt.QObject, ~permission, app, camera, state, state)
    done: Bool <- Qt.CallbackProbe.waitCalls(state, 1)
    require(done, "The permission callback did not run")

def rest() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    +server: Qt.QTcpServer <- Qt.CallbackProbe.restServer()
    address: String <- Qt.CallbackProbe.restUrl(server)
    url: Qt.QUrl <- Qt.QUrl.new__String_QUrl_ParsingMode(address, Qt.QUrl.ParsingMode.TolerantMode())
    +request: Qt.QNetworkRequest <- Qt.QNetworkRequest.new__QUrl(url)
    +network: Qt.QNetworkAccessManager <- Qt.QNetworkAccessManager.new()
    +manager: Qt.QRestAccessManager <- Qt.QRestAccessManager.new__QNetworkAccessManager(network)
    +instance: Qt.ObjectType.Instance(Model()) <- Qt.ObjectType.new(~Model())
    +state: Qt.QObject = Qt.ObjectType.as_QObject(~Model(), instance)
    +reply: Qt.QNetworkReply <- Qt.QRestAccessManager.getWithHandler__QNetworkRequest_QObject(~Qt.QObject, ~completed, manager, request, state, state)
    done: Bool <- Qt.CallbackProbe.waitCalls(state, 1)
    require(done, "The REST GET callback did not run")
    text: String <- Qt.Property.get(~body(), state)
    require(String.eq(text, "rest-ok"), "A REST callback did not read the actual response")
    id: U32 <- Qt.Property.get(~saved(), state)
    expired: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.QRestReply.isSuccess(Qt.QRestReply{id}))
    expected(Bool, expired, 116)
    bytes: Qt.QByteArray <- Qt.QByteArray.fromUtf8("post-body")
    +device: Qt.QBuffer <- Qt.QBuffer.new()
    Qt.QBuffer.setData__QByteArray(device, bytes)
    opened: Bool <- Qt.QBuffer.open(device, Qt.QIODeviceBase.OpenModeFlag.ReadOnly())
    require(opened, "Cannot open the REST upload body")
    +posted: Qt.QNetworkReply <- Qt.QRestAccessManager.postWithHandler__QNetworkRequest_QIODevice_QObject(~Qt.QObject, ~completed, manager, request, Qt.QBuffer.as_QIODevice(device), state, state)
    held: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QBuffer.destroy(device))
    expected(Unit, held, 16)
    done: Bool <- Qt.CallbackProbe.waitCalls(state, 2)
    require(done, "The REST POST callback did not run")
    +withoutContext: Qt.QNetworkReply <- Qt.QRestAccessManager.getWithHandler__QNetworkRequest_QObject(~Qt.QObject, ~completed, manager, request, Qt.QObject{0}, state)
    done: Bool <- Qt.CallbackProbe.waitCalls(state, 3)
    require(done, "A REST callback without a context object lost its temporary reply")
    +bad: Qt.QNetworkReply <- Qt.QRestAccessManager.getWithHandler__QNetworkRequest_QObject(~Unit, ~failed, manager, request, state, Unit{})
    result: Result<&1, &1, U32 & String, Bool> <- Qt.Action.attempt(Bool, Qt.CallbackProbe.finishReply(bad))
    expected(Bool, result, 94)
    +cancelledContext: Qt.QObject <- Qt.QObject.new()
    cancelled: Qt.QNetworkReply <- Qt.QRestAccessManager.getWithHandler__QNetworkRequest_QObject(~Unit, ~failed, manager, request, cancelledContext, Unit{})
    Qt.QObject.destroy(cancelledContext)
    done: Bool <- Qt.CallbackProbe.finishReply(cancelled)
    require(done, "Destroying a REST callback context cancelled the HTTP request itself")
    Qt.QRestAccessManager.destroy(manager)
    Qt.QNetworkAccessManager.destroy(network)
    Qt.QBuffer.destroy(device)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, timers_and_lookup())
    Qt.scoped(Unit, permissions())
    Qt.scoped(Unit, rest())
    Qt.Action.lift(Unit, IO.print("QT612_CALLBACK_SURFACES_OK timers=1 lookup=1 permissions=1 rest=1 body_retention=1 temporary_reply=1 cancellation=1 errors=94_96"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
