// Native implementation of the public duplex pipe helper exposed by PySide.
// Endpoints use Qt's ordinary sequential device and signal semantics.
QT_BEGIN_NAMESPACE
namespace QtCoreHelper {
class BendPipeEndpoint final : public QIODevice {
    QByteArray bytes;
    QPointer<BendPipeEndpoint> peer;
public:
    void connectPeer(BendPipeEndpoint *value) { peer = value; }
    bool isSequential() const override { return true; }
    qint64 bytesAvailable() const override { return bytes.size() + QIODevice::bytesAvailable(); }
protected:
    qint64 readData(char *output, qint64 maximum) override {
        const auto count = qMin(maximum, qint64(bytes.size()));
        if (count <= 0) return 0;
        memcpy(output, bytes.constData(), size_t(count));
        bytes.remove(0, qsizetype(count));
        return count;
    }
    qint64 writeData(const char *input, qint64 length) override {
        if (!peer) return -1;
        if (length <= 0) return 0;
        const auto count = qMin(length, qint64(std::numeric_limits<int>::max()) - peer->bytes.size());
        if (count <= 0) return 0;
        peer->bytes.append(input, qsizetype(count));
        // A handler may delete either endpoint during signal delivery.
        QPointer<BendPipeEndpoint> destination = peer;
        Q_EMIT bytesWritten(count);
        if (destination) Q_EMIT destination->readyRead();
        return count;
    }
};
QIOPipe::QIOPipe(QObject *parent) : QObject(parent) {
    auto left = std::make_unique<BendPipeEndpoint>();
    auto right = std::make_unique<BendPipeEndpoint>();
    left->connectPeer(right.get()); right->connectPeer(left.get());
    first = left.release(); second = right.release();
}
QIOPipe::~QIOPipe() { delete first.data(); delete second.data(); }
bool QIOPipe::open(QIODeviceBase::OpenMode mode) {
    if (!first || !second || !first->open(mode)) return false;
    const auto access = mode & QIODeviceBase::ReadWrite;
    const auto remote = access == QIODeviceBase::ReadOnly || access == QIODeviceBase::WriteOnly
        ? mode ^ QIODeviceBase::ReadWrite : mode;
    return second->open(remote);
}
QIODevice *QIOPipe::end1() const { return first.data(); }
QIODevice *QIOPipe::end2() const { return second.data(); }
}
QT_END_NAMESPACE
