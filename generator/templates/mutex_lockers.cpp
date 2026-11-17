namespace NativeMutexLockers {
struct Locker {
    uint32_t source;
    const unsigned kind;
    Locker(uint32_t mutex, unsigned type) : source(mutex), kind(type) {}
    virtual ~Locker() = default;
    virtual bool locked() const = 0;
    virtual void unlock() = 0;
    virtual void relock() = 0;
    virtual void swap(Locker &) = 0;
};
template<class Mutex, unsigned Kind> struct TypedLocker final : Locker {
    QMutexLocker<Mutex> value;
    TypedLocker(Mutex *mutex, uint32_t source) : Locker(source, Kind), value(mutex) {}
    bool locked() const override { return value.isLocked(); }
    // Qt 6.10+ only asserts these preconditions: unlock() on an unlocked or
    // null locker dereferences or double-unlocks its mutex. Keep the earlier
    // documented Qt 6 behavior, where both are no-ops in that state.
    void unlock() override { if (value.isLocked()) value.unlock(); }
    void relock() override { if (!value.isLocked() && value.mutex()) value.relock(); }
    void swap(Locker &other) override {
        value.swap(static_cast<TypedLocker &>(other).value);
        std::swap(source, other.source);
    }
};
static void delete_locker(void *pointer) { delete static_cast<Locker *>(pointer); }
static Locker *get_locker(BqtRequest *r, uint32_t id, unsigned kind, bool pin = true) {
    auto *record = entry(id);
    if (!record || record->destroy != delete_locker) {
        fail(r, ESTALE, "The mutex locker has expired"); return nullptr;
    }
    if (record->destroying) { fail(r, EBUSY, "The mutex locker is being destroyed"); return nullptr; }
    if (static_cast<Locker *>(record->value)->kind != kind) {
        fail(r, EINVAL, "The mutex locker has a different native specialization"); return nullptr;
    }
    if (QThread::currentThread() != main_thread) {
        fail(r, EXDEV, "A mutex locker must be used on its locking thread"); return nullptr;
    }
    if (pin && native_call_scope) native_call_scope->pin(r, id);
    return r->error ? nullptr : static_cast<Locker *>(record->value);
}
static bool validate_source(BqtRequest *r, const Locker &value) {
    if (value.kind == 0) get<QMutex>(r, value.source, @QMutex@, true, true);
    else get<QRecursiveMutex>(r, value.source, @QRecursiveMutex@, true, true);
    return !r->error;
}
template<class Mutex, unsigned Kind> static bool create(BqtRequest *r) {
    NativeCallScope scope;
    constexpr uint16_t type = Kind == 0 ? @QMutex@ : @QRecursiveMutex@;
    auto *mutex = get<Mutex>(r, r->arguments[0].word, type, true, true);
    if (r->error) return true;
    auto *value = new TypedLocker<Mutex, Kind>(mutex, r->arguments[0].word);
    try { r->result.word = insert(r, value, nullptr, 0, delete_locker, true); }
    catch (...) {
        for (uint32_t i = 1; i < capacity; ++i)
            if (entries[i].value == value) invalidate(token(i, entries[i].generation));
        delete value;
        throw;
    }
    r->result.owned_handle = r->result.word;
    if (r->error || !r->result.word) return true;
    BqtRequest claim{}; claim.self = r->result.word;
    const int edge = prepare_retention(&claim, @RETENTION_SLOT@, 0, r->arguments[0].word);
    if (claim.error) return fail(r, claim.error, claim.message);
    commit_retention(edge, r->result.word, @RETENTION_SLOT@, 0, r->arguments[0].word, nullptr);
    return true;
}
static bool destroy_strict(BqtRequest *r, unsigned kind) {
    if (!get_locker(r, r->self, kind, false)) return true;
    return destroy_object(r);
}
static bool release(BqtRequest *r, unsigned kind) {
    if (!get_locker(r, r->self, kind, false)) return true;
    return release_object(r);
}
static bool locked(BqtRequest *r, unsigned kind) {
    NativeCallScope scope;
    auto *value = get_locker(r, r->self, kind);
    if (value) r->result.word = value->locked();
    return true;
}
static bool unlock(BqtRequest *r, unsigned kind) {
    NativeCallScope scope;
    auto *value = get_locker(r, r->self, kind);
    if (value && validate_source(r, *value)) value->unlock();
    return true;
}
static bool relock(BqtRequest *r, unsigned kind) {
    NativeCallScope scope;
    auto *value = get_locker(r, r->self, kind);
    if (value && validate_source(r, *value)) value->relock();
    return true;
}
static bool mutex(BqtRequest *r, unsigned kind) {
    NativeCallScope scope;
    auto *value = get_locker(r, r->self, kind);
    if (value && validate_source(r, *value)) {
        r->result.word = value->source;
        r->result.borrowed_handle = r->result.word;
    }
    return true;
}
static bool swap(BqtRequest *r, unsigned kind) {
    NativeCallScope scope;
    auto *first = get_locker(r, r->self, kind);
    auto *second = get_locker(r, r->arguments[0].word, kind);
    if (!first || !second) return true;
    if (first->kind != second->kind) return fail(r, EINVAL, "Mutex locker specializations must match");
    if (!validate_source(r, *first) || !validate_source(r, *second)) return true;
    RetentionBatch updates;
    if (!updates.add(r, r->self, @RETENTION_SLOT@, second->source, nullptr, false, false, 0)
            || !updates.add(r, r->arguments[0].word, @RETENTION_SLOT@, first->source, nullptr, false, false, 0)
            || !updates.finish(r)) return true;
    first->swap(*second);
    return true;
}
} // namespace NativeMutexLockers
