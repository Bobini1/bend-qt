import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def finished() -> Qt.Signal:
  Qt.Signal.define("finished", [])

type ProviderState is Data:
  ProviderState{probe: Qt.QObject, image: Qt.QImage}

type CancelState is Data:
  CancelState{probe: Qt.QObject, response: Qt.QQuickImageResponse}

def texture(image: Qt.QImage) -> Qt.Action(Qt.QQuickTextureFactory):
  Qt.QQuickTextureFactory.textureFactoryForImage(image)

def cancel_response(+probe: Qt.QObject, response: Qt.QQuickImageResponse) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QObject.setObjectName(probe, "cancelled")
    Qt.Signal.emit(~finished(), Qt.QQuickImageResponse.as_QObject(response))

def cancelled(state: CancelState) -> Qt.Action(Unit):
  match state:
    case CancelState{probe, response}: cancel_response(probe, response)

def pending(+probe: Qt.QObject, response: Qt.QQuickImageResponse) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    stored: Bool <- Qt.QVariant.with(Bool, Qt.QVariant.fromUInt32(Qt.QQuickImageResponse.word(response)), value => Qt.QObject.setProperty(probe, "pendingResponse", value))
    Qt.QObject.setObjectName(probe, "pending")

def complete_or_wait(probe: Qt.QObject, +response: Qt.QQuickImageResponse, ready: Bool) -> Qt.Action(Unit):
  match ready:
    case True{}: Qt.Signal.emit(~finished(), Qt.QQuickImageResponse.as_QObject(response))
    case False{}: pending(probe, response)

def response(+probe: Qt.QObject, image: Qt.QImage, id: String) -> Qt.Action(Qt.QQuickImageResponse):
  do Qt.Action<Qt.QQuickImageResponse>:
    +value: Qt.QQuickImageResponse <- Qt.QQuickImageResponse.newOverride()
    Qt.QQuickImageResponse.Virtual.textureFactory.handle(~Qt.QImage, ~texture, value, image)
    Qt.QQuickImageResponse.Virtual.cancel.handle(~CancelState, ~cancelled, value, CancelState{probe, value})
    complete_or_wait(probe, value, String.eq(id, "ready"))
    return value

def requested(state: ProviderState, id: String, requestedSize: Qt.QSize) -> Qt.Action(Qt.QQuickImageResponse):
  match state:
    case ProviderState{probe, image}: response(probe, image, id)

def provider(+probe: Qt.QObject, image: Qt.QImage, +engine: Qt.QQmlEngine, +value: Qt.QQuickAsyncImageProvider) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQuickAsyncImageProvider.Virtual.requestImageResponse.handle(~ProviderState, ~requested, value, ProviderState{probe, image})
    Qt.QQmlEngine.addImageProvider(engine, "bend-async", Qt.QQuickAsyncImageProvider.as_QQmlImageProviderBase(value))
    valid: Bool <- Qt.CallbackProbe.asyncImage(engine, probe)
    require(valid, "Asynchronous QML image loading, pixels, cancellation or deletion failed")

def engine(probe: Qt.QObject, image: Qt.QImage, engine: Qt.QQmlEngine) -> Qt.Action(Unit):
  Qt.QQuickAsyncImageProvider.with(Unit, Qt.QQuickAsyncImageProvider.newOverride(), value => provider(probe, image, engine, value))

def image(probe: Qt.QObject, +value: Qt.QImage) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QColor.with(Unit, Qt.QColor.fromString("red"), color => Qt.QImage.fill__QColor(value, color))
    Qt.QQmlEngine.with(Unit, Qt.QQmlEngine.new(), qml => engine(probe, value, qml))

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Render.useGuiThread()
    Qt.QObject.with(Unit, Qt.QObject.new(), probe => Qt.QImage.with(Unit, Qt.QImage.new__Int32_Int32_QImage_Format(Qt.Int32{8}, Qt.Int32{8}, Qt.QImage.Format.Format_ARGB32()), value => image(probe, value)))
    objects: U32 <- Qt.Runtime.liveObjects()
    data: U32 <- Qt.Runtime.liveData()
    require(U32.is_eq(objects, 0) && U32.is_eq(data, 0), "Asynchronous image callbacks leaked handles or Bend data")
    Qt.Action.lift(Unit, IO.print("QT612_ASYNC_IMAGE_PROVIDER_OK qml_loader=1 early_finished=1 red_pixels=1 cancel_finished=1 response_deleted=1 objects=0 data=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
