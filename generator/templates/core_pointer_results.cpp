// These scopes own the registry view, never the process-wide Qt object.
static void release_static_native_view(void *) {}
struct StaticNativeView {
    uint32_t token = 0;
    const void *pointer = nullptr;
    std::function<const void *(BqtRequest *)> current;
    bool checking = false;
};
static SlotTable<StaticNativeView> static_native_views;
static void static_native_view_forget(uint32_t id) {
    auto &value = static_native_views[id & 65535u];
    if (value.token == id) value = {};
}
static bool validate_static_native_view(BqtRequest *r, uint32_t id) {
    const auto view = static_native_views[id & 65535u];
    if (view.token != id || !entry(id)) {
        fail(r, ESTALE, "The static Qt view has expired"); return false;
    }
    if (!view.current) return true;
    if (view.checking) { fail(r, EBUSY, "The static Qt view is already being checked"); return false; }
    static_native_views[id & 65535u].checking = true;
    struct Checking {
        uint32_t id;
        ~Checking() {
            auto &view = static_native_views[id & 65535u];
            if (view.token == id) view.checking = false;
        }
    } checking{id};
    const auto pointer = view.current(r);
    if (r->error || pointer != view.pointer) {
        if (!r->error) fail(r, ESTALE, "The static Qt object has been replaced");
        if (r->error == ESTALE) invalidate(id);
        return false;
    }
    return true;
}
template<class T> static uint32_t borrow_static_native_view(BqtRequest *r, T *pointer, uint16_t type,
        std::function<const void *(BqtRequest *)> current, bool readonly) {
    if (!pointer) return 0;
    using Value = std::remove_const_t<T>;
    for (uint32_t i = 1; i < capacity; ++i) {
        auto &record = entries[i];
        if (!record.value || !record.cast) continue;
        const auto id = token(i, record.generation);
        if (record.destroy == release_static_native_view) {
            BqtRequest probe{};
            if (!validate_static_native_view(&probe, id)) continue;
        }
        if (record.cast(record.value, type) == pointer) return id;
    }
    const auto id = insert(r, const_cast<Value *>(pointer), nullptr, type,
                           release_static_native_view, false, NativeTraits<Value>::cast);
    if (auto *record = entry(id)) {
        try {
            static_native_views[id & 65535u] = StaticNativeView{id, pointer, std::move(current)};
            record->validate = validate_static_native_view;
            record->read_only = readonly || std::is_const_v<T>;
            record->native_observed = true;
            record->scope_owner = scope_track(r, id, 0);
            native_pointer_publish(id);
        } catch (...) {
            invalidate(id);
            throw;
        }
    }
    return id;
}
static bool copy_cloned_native_dependencies(BqtRequest *r, uint32_t target, uint32_t source) {
    if (!target || target == source) return !r->error;
    // Clone constructors copy their native fields. Retain the same dependent
    // objects instead of retaining the original event/engine wrapper itself.
    std::vector<Retention> copied;
    for (const auto &edge : retentions)
        if (edge.owner == source && edge.target) copied.push_back(edge);
    RetentionBatch changes;
    for (const auto &edge : copied) {
        const bool already_present = std::any_of(retentions.begin(), retentions.end(), [&](const auto &existing) {
            return existing.owner == target && existing.slot == edge.slot && existing.key == edge.key && existing.target;
        });
        if (already_present) continue;
        if (!changes.add(r, target, edge.slot, edge.target, nullptr, false, false, edge.key)) return false;
    }
    return changes.finish(r);
}
template<class T> static uint32_t observe_cloned_event(BqtRequest *r, T *pointer, uint16_t type) {
    if (!pointer) return 0;
    for (uint32_t i = 1; i < capacity; ++i) {
        auto &record = entries[i];
        if (record.value && record.cast && record.cast(record.value, type) == pointer)
            return own(r, pointer, type);
    }
    std::unique_ptr<QEvent> original(pointer);
@OBSERVED_EVENT_CLONES@
    // A plugin can define a further native subclass absent from extraction.
    // Preserve it intact; ownership transfers still require an observed type.
    return own(r, static_cast<T *>(original.release()), type);
}
