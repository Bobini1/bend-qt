import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def error(-A: Type, result: Result<&1, &1, U32 & String, A>, expected: U32) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, expected), "Wrong HTTP retention error: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "Expected HTTP dependency rejection")

def held(device: Qt.QBuffer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    denied: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QBuffer.destroy(device))
    error(Unit, denied, 16)

def copy_source(+source: Qt.QHttpPart, device: Qt.QIODevice) -> Qt.Action(Qt.QHttpPart):
  do Qt.Action<Qt.QHttpPart>:
    Qt.QHttpPart.setBodyDevice(source, device)
    Qt.QHttpPart.new__QHttpPart(source)

def copied(+copy: Qt.QHttpPart, +device: Qt.QBuffer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    held(device)
    Qt.QHttpPart.setBodyDevice(copy, Qt.QIODevice{0})
    Qt.QBuffer.destroy(device)

def returned(+result: Qt.QHttpPart, +target: Qt.QHttpPart, +source: Qt.QHttpPart, +device: Qt.QBuffer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QHttpPart.destroy(target)
    Qt.QHttpPart.setBodyDevice(source, Qt.QIODevice{0})
    held(device)
    Qt.QHttpPart.setBodyDevice(result, Qt.QIODevice{0})
    Qt.QBuffer.destroy(device)

def assignment(+target: Qt.QHttpPart, +source: Qt.QHttpPart, +device: Qt.QBuffer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QHttpPart.setBodyDevice(source, Qt.QBuffer.as_QIODevice(device))
    Qt.QHttpPart.with(Unit, Qt.QHttpPart.op_assign(target, source), result => returned(result, target, source, device))

def append_source(+part: Qt.QHttpPart, multipart: Qt.QHttpMultiPart, device: Qt.QIODevice) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QHttpPart.setBodyDevice(part, device)
    Qt.QHttpMultiPart.append(multipart, part)

def multipart(+value: Qt.QHttpMultiPart, +device: Qt.QBuffer) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QHttpPart.with(Unit, Qt.QHttpPart.new(), part => append_source(part, value, Qt.QBuffer.as_QIODevice(device)))
    held(device)
    Qt.QHttpMultiPart.destroy(value)
    Qt.QBuffer.destroy(device)

def post(+manager: Qt.QNetworkAccessManager, +request: Qt.QNetworkRequest, +multipart: Qt.QHttpMultiPart) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    reply: Qt.QNetworkReply <- Qt.QNetworkAccessManager.post__QNetworkRequest_QHttpMultiPart(manager, request, multipart)
    Qt.QNetworkReply.abort(reply)
    denied: Result<&1, &1, U32 & String, Unit> <- Qt.Action.attempt(Unit, Qt.QHttpMultiPart.destroy(multipart))
    error(Unit, denied, 16)
    Qt.QHttpMultiPart.release(multipart)
    Qt.QNetworkAccessManager.destroy(manager)
    stale: Result<&1, &1, U32 & String, Qt.QByteArray> <- Qt.Action.attempt(Qt.QByteArray, Qt.QHttpMultiPart.boundary(multipart))
    error(Qt.QByteArray, stale, 116)

def request(url: Qt.QUrl) -> Qt.Action(Unit):
  Qt.QNetworkRequest.with(Unit, Qt.QNetworkRequest.new__QUrl(url), request =>
    Qt.QNetworkAccessManager.with(Unit, Qt.QNetworkAccessManager.new(), manager =>
      Qt.QHttpMultiPart.with(Unit, Qt.QHttpMultiPart.new(), multipart => post(manager, request, multipart))))

def copying(+device: Qt.QBuffer) -> Qt.Action(Unit):
  Qt.QHttpPart.with(Unit, Qt.QHttpPart.with(Qt.QHttpPart, Qt.QHttpPart.new(), source => copy_source(source, Qt.QBuffer.as_QIODevice(device))), copy => copied(copy, device))

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QBuffer.with(Unit, Qt.QBuffer.new(), device => copying(device))
    Qt.QBuffer.with(Unit, Qt.QBuffer.new(), device =>
      Qt.QHttpPart.with(Unit, Qt.QHttpPart.new(), target =>
        Qt.QHttpPart.with(Unit, Qt.QHttpPart.new(), source => assignment(target, source, device))))
    Qt.QBuffer.with(Unit, Qt.QBuffer.new(), device =>
      Qt.QHttpMultiPart.with(Unit, Qt.QHttpMultiPart.new(), value => multipart(value, device)))
    Qt.QUrl.with(Unit, Qt.QUrl.new__String_QUrl_ParsingMode("http://127.0.0.1:1/", Qt.QUrl.ParsingMode.TolerantMode()), value => request(value))
    objects: U32 <- Qt.Runtime.liveObjects()
    pins: U32 <- Qt.Runtime.liveRetentions()
    require(U32.is_eq(objects, 0) && U32.is_eq(pins, 0), "HTTP multipart dependencies leaked")
    Qt.Action.lift(Unit, IO.print("QT612_NETWORK_RETENTION_OK copy=1 assignment=1 result_copy=1 append=1 reply_body=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
