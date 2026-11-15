// Keep a plugin's concrete engine intact. The public virtual interface is
// forwarded completely, and Qt can delete this observing owner normally.
class ObservedIconEngine final : public QIconEngine {
    std::unique_ptr<QIconEngine> inner;
public:
    explicit ObservedIconEngine(std::unique_ptr<QIconEngine> value) : inner(std::move(value)) {}
    ~ObservedIconEngine() override {
        native_pointer_destroying(static_cast<QIconEngine *>(this));
        inner.reset();
        native_deleted(static_cast<QIconEngine *>(this));
    }
    void paint(QPainter *painter, const QRect &rect, QIcon::Mode mode, QIcon::State state) override {
        inner->paint(painter, rect, mode, state);
    }
    QSize actualSize(const QSize &size, QIcon::Mode mode, QIcon::State state) override {
        return inner->actualSize(size, mode, state);
    }
    QPixmap pixmap(const QSize &size, QIcon::Mode mode, QIcon::State state) override {
        return inner->pixmap(size, mode, state);
    }
    void addPixmap(const QPixmap &pixmap, QIcon::Mode mode, QIcon::State state) override {
        inner->addPixmap(pixmap, mode, state);
    }
    void addFile(const QString &fileName, const QSize &size, QIcon::Mode mode, QIcon::State state) override {
        inner->addFile(fileName, size, mode, state);
    }
    QString key() const override { return inner->key(); }
    QIconEngine *clone() const override {
        std::unique_ptr<QIconEngine> value(inner->clone());
        if (!value) return nullptr;
        return new ObservedIconEngine(std::move(value));
    }
    bool read(QDataStream &stream) override { return inner->read(stream); }
    bool write(QDataStream &stream) const override { return inner->write(stream); }
    QList<QSize> availableSizes(QIcon::Mode mode, QIcon::State state) override { return inner->availableSizes(mode, state); }
    QString iconName() override { return inner->iconName(); }
    bool isNull() override { return inner->isNull(); }
    QPixmap scaledPixmap(const QSize &size, QIcon::Mode mode, QIcon::State state, qreal scale) override {
        return inner->scaledPixmap(size, mode, state, scale);
    }
    void virtual_hook(int id, void *data) override { inner->virtual_hook(id, data); }
};
static uint32_t observe_cloned_icon_engine(BqtRequest *r, QIconEngine *pointer, uint16_t type) {
    if (!pointer) return 0;
    for (uint32_t i = 1; i < capacity; ++i) {
        auto &record = entries[i];
        if (record.value && record.cast && record.cast(record.value, type) == pointer)
            return own(r, pointer, type);
    }
    if (auto *observed = dynamic_cast<ObservedIconEngine *>(pointer))
        return own_derived<QIconEngine>(r, observed, type);
    auto value = std::make_unique<ObservedIconEngine>(std::unique_ptr<QIconEngine>(pointer));
    return own_derived<QIconEngine>(r, value.release(), type);
}
