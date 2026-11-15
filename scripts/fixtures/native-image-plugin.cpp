#include <QtGui/QImageIOPlugin>
#include <QtGui/QImage>
#include <QtCore/QIODevice>

class BendImageHandler final : public QImageIOHandler {
public:
    bool canRead() const override { return device() && device()->peek(4) == "BQT1"; }
    bool read(QImage *image) override {
        if (!canRead()) return false;
        *image = QImage(2, 2, QImage::Format_ARGB32);
        image->fill(Qt::red);
        return true;
    }
};
class BendImagePlugin final : public QImageIOPlugin {
    Q_OBJECT
    Q_PLUGIN_METADATA(IID "org.qt-project.Qt.QImageIOHandlerFactoryInterface" FILE "native-image-plugin.json")
public:
    Capabilities capabilities(QIODevice *device, const QByteArray &format) const override {
        return format == "bqtrg" || (format.isEmpty() && device && device->peek(4) == "BQT1")
            ? CanRead : Capabilities{};
    }
    QImageIOHandler *create(QIODevice *device, const QByteArray &format = {}) const override {
        auto *handler = new BendImageHandler;
        handler->setDevice(device); handler->setFormat(format);
        return handler;
    }
};
#include "native-image-plugin.moc"
