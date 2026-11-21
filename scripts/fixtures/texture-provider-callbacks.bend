import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)

def factory_image(image: Qt.QImage, requested: Qt.QSize) -> Qt.Action(Qt.CallbackReply_Owned_QQuickTextureFactory_QSize):
  do Qt.Action<Qt.CallbackReply_Owned_QQuickTextureFactory_QSize>:
    factory: Qt.QQuickTextureFactory <- Qt.QQuickTextureFactory.textureFactoryForImage(image)
    size: Qt.QSize <- Qt.QSize.new__QSize(requested)
    return Qt.CallbackReply_Owned_QQuickTextureFactory_QSize{factory, size}

def factory_reply(+requested: Qt.QSize) -> Qt.Action(Qt.CallbackReply_Owned_QQuickTextureFactory_QSize):
  Qt.QImage.with(Qt.CallbackReply_Owned_QQuickTextureFactory_QSize, Qt.QImage.new__QSize_QImage_Format(requested, Qt.QImage.Format.Format_ARGB32()), image => factory_image(image, requested))

# Qt takes the factory together with its size output.
def requested_texture(state: Unit, id: String, size: Qt.QSize, requested: Qt.QSize) -> Qt.Action(Qt.CallbackReply_Owned_QQuickTextureFactory_QSize):
  factory_reply(requested)

def provider_demo(+provider: Qt.QQuickImageProvider) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQuickImageProvider.Virtual.requestTexture.handle(~Unit, ~requested_texture, provider, Unit{})
    valid: U32 <- Qt.CallbackProbe.textureProvider(provider)
    require(U32.is_eq(valid, 1), "The texture factory and its size output were not committed together")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QQuickImageProvider.with(Unit, Qt.QQuickImageProvider.newOverride(Qt.QQmlImageProviderBase.ImageType.Texture(), Qt.QQmlImageProviderBase.Flag{0}), provider => provider_demo(provider))
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "The texture factory handler leaked handles")
    Qt.Action.lift(Unit, IO.print("QT612_TEXTURE_PROVIDER_CALLBACKS_OK native_factory=1 output_size=1 ownership_transfer=1 native_destruction=1 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
