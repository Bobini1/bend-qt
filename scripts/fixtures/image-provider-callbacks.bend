import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def output_size(requested: Qt.QSize, present: Bool) -> Qt.Action(Qt.QSize):
  match present:
    case True{}: Qt.QSize.new__QSize(requested)
    case False{}: Qt.Action.pure(Qt.QSize, Qt.QSize{0})

def image_reply(id: String, size: Qt.QSize, +requested: Qt.QSize) -> Qt.Action(Qt.CallbackReply_QImage_QSize):
  do Qt.Action<Qt.CallbackReply_QImage_QSize>:
    image: Qt.QImage <- Qt.QImage.new__QSize_QImage_Format(requested, Qt.QImage.Format.Format_ARGB32())
    output: Qt.QSize <- output_size(requested, U32.is_ne(Qt.QSize.word(size), 0) || String.eq(id, "null-invalid"))
    return Qt.CallbackReply_QImage_QSize{image, output}

# A null size pointer needs a null size reply; "null-invalid" breaks that rule.
def requested_image(state: Unit, id: String, size: Qt.QSize, requested: Qt.QSize) -> Qt.Action(Qt.CallbackReply_QImage_QSize):
  image_reply(id, size, requested)

def rejected(result: Result<&1, &1, U32 & String, U32>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 22), "Wrong null output rejection: " ++ message)
    case Done{value}: Qt.Action.fail(Unit, 1, "A size reply for a null native pointer was accepted")

def provider_demo(+provider: Qt.QQuickImageProvider) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQuickImageProvider.Virtual.requestImage.handle(~Unit, ~requested_image, provider, Unit{})
    valid: U32 <- Qt.CallbackProbe.imageProvider(provider, 0)
    require(U32.is_eq(valid, 1), "Image output, size output or null size failed")
    invalid: Result<&1, &1, U32 & String, U32> <- Qt.Action.attempt(U32, Qt.CallbackProbe.imageProvider(provider, 1))
    rejected(invalid)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQuickImageProvider.with(Unit, Qt.QQuickImageProvider.newOverride(Qt.QQmlImageProviderBase.ImageType.Image(), Qt.QQmlImageProviderBase.Flag{0}), provider => provider_demo(provider))
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "The image provider handler leaked handles")
    Qt.Action.lift(Unit, IO.print("QT612_IMAGE_PROVIDER_CALLBACKS_OK image=1 output_size=1 null_preserved=1 invalid_reply_rejected=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
