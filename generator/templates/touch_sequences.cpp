namespace NativeTouchSequences {
class Sequence final : public QTest::QTouchEventSequence {
public:
    QPointer<QObject> target;
    QPointer<QPointingDevice> source;
    const bool widget_target;
    const bool auto_commit;
    const bool had_target;
    bool committing = false;
    bool armed = false;
    Sequence(QObject *object, QPointingDevice *device, bool widget, bool automatic)
        : QTest::QTouchEventSequence(widget ? nullptr : static_cast<QWindow *>(object), device, false),
          target(object), source(device), widget_target(widget), auto_commit(automatic), had_target(object != nullptr) {}
    ~Sequence() override {
        if (armed && auto_commit && source && (!had_target || target)) perform_commit(true);
    }
    bool live() const { return source && (!had_target || target); }
    bool perform_commit(bool process) {
        if (committing) return false;
        committing = true;
        struct Reset { bool &value; ~Reset() { value = false; } } reset{committing};
        if (widget_target) {
            auto *widget = static_cast<QWidget *>(target.data());
            targetWindow = widget ? widget->windowHandle() : nullptr;
        }
        const bool result = QTest::QTouchEventSequence::commit(process);
        return result;
    }
    void update_point(int id, const QPoint &position, QEventPoint::State state, QObject *coordinates) {
        if (state != QEventPoint::Updated && points.contains(id)) return;
        QObject *mapping = coordinates ? coordinates : target.data();
        QPointF global = position;
        if (auto *widget = qobject_cast<QWidget *>(mapping)) global = widget->mapToGlobal(position);
        else if (auto *window = qobject_cast<QWindow *>(mapping)) global = window->mapToGlobal(position);
        points[id] = QEventPoint(id, state, position, global);
    }
};
static void delete_sequence(void *value) { delete static_cast<Sequence *>(value); }
static bool create_device(BqtRequest *r) {
    NativeCallScope scope;
    auto *device = QTest::createTouchDevice(QInputDevice::DeviceType(r->arguments[0].word),
        QInputDevice::Capabilities(QFlag(int(r->arguments[1].word))));
    const auto id = borrow(r, device, @QPointingDevice@);
    // Qt owns registered test devices until application shutdown. This scope
    // owns only its observed QObject view, and can never transfer the device.
    if (auto *record = entry(id); record && !record->owned) {
        record->destroy = release_static_native_view;
        if (!record->scope_owner) record->scope_owner = scope_track(r, id, 0);
    }
    r->result.word = id;
    return true;
}
static Sequence *get_sequence(BqtRequest *r, bool pin = true) {
    auto *record = entry(r->self);
    if (!record || record->destroy != delete_sequence) {
        fail(r, ESTALE, "The touch sequence has expired"); return nullptr;
    }
    if (record->destroying) { fail(r, EBUSY, "The touch sequence is being destroyed"); return nullptr; }
    if (QThread::currentThread() != main_thread) { fail(r, EXDEV, "A touch sequence must run on the Qt main thread"); return nullptr; }
    if (pin && native_call_scope) native_call_scope->pin(r, r->self);
    return r->error ? nullptr : static_cast<Sequence *>(record->value);
}
static bool create(BqtRequest *r, bool widget) {
    NativeCallScope scope;
    QObject *target = widget ? static_cast<QObject *>(get<QWidget>(r, r->arguments[0].word, @QWidget@, true, true))
                             : static_cast<QObject *>(get<QWindow>(r, r->arguments[0].word, @QWindow@, true, true));
    auto *device = get<QPointingDevice>(r, r->arguments[1].word, @QPointingDevice@);
    if (r->error) return true;
    if (!device) return fail(r, EINVAL, "Touch event synthesis requires a pointing device");
    auto *value = new Sequence(target, device, widget, r->arguments[2].word != 0);
    // The native destructor must not dispatch a half-registered sequence.
    uint32_t id = 0;
    try { id = insert(r, value, nullptr, 0, delete_sequence, true); }
    catch (...) {
        for (uint32_t i = 1; i < capacity; ++i)
            if (entries[i].value == value) invalidate(token(i, entries[i].generation));
        delete value;
        throw;
    }
    r->result.word = id; r->result.owned_handle = id;
    if (!id || r->error) return true;
    RetentionBatch sources;
    if (!sources.add(r, id, @RETENTION_SLOT@, r->arguments[0].word, nullptr, false, false, 0)
            || !sources.add(r, id, @RETENTION_SLOT@, r->arguments[1].word, nullptr, false, false, 1)
            || !sources.finish(r)) return true;
    value->armed = true;
    return true;
}
static bool destroy(BqtRequest *r, bool release) {
    if (!get_sequence(r, false)) return true;
    return release ? release_object(r) : destroy_object(r);
}
static bool validate(BqtRequest *r, Sequence *value) {
    if (!value->live()) { fail(r, ESTALE, "A native touch sequence source has expired"); return false; }
    if (value->committing) { fail(r, EBUSY, "The touch sequence is already committing"); return false; }
    return true;
}
static bool commit(BqtRequest *r) {
    NativeCallScope scope;
    auto *value = get_sequence(r);
    if (value && validate(r, value)) r->result.word = value->perform_commit(r->arguments[0].word != 0);
    return true;
}
static bool stationary(BqtRequest *r) {
    NativeCallScope scope;
    auto *value = get_sequence(r);
    if (value && validate(r, value)) value->stationary(int32_t(r->arguments[0].word));
    return true;
}
static bool update(BqtRequest *r, QEventPoint::State state, unsigned mapping) {
    NativeCallScope scope;
    auto *value = get_sequence(r);
    auto *position = get<QPoint>(r, r->arguments[1].word, @QPoint@);
    QObject *coordinates = nullptr;
    if (mapping == 1) coordinates = get<QWindow>(r, r->arguments[2].word, @QWindow@, true, true);
    else if (mapping == 2) coordinates = get<QWidget>(r, r->arguments[2].word, @QWidget@, true, true);
    if (r->error || !value || !validate(r, value)) return true;
    value->update_point(int32_t(r->arguments[0].word), *position, state, coordinates);
    return true;
}
} // namespace NativeTouchSequences
