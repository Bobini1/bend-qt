template<class T> struct LazyValueTraits;
// @LAZY_TRAITS@
struct LazyValueOrigin {
    uint32_t id = 0, converter = 0;
    std::shared_ptr<void> backing;
};
static SlotTable<LazyValueOrigin *> lazy_value_origins;
static LazyValueOrigin *lazy_value_origin(uint32_t id) {
    auto *origin = lazy_value_origins[id & 65535u];
    return origin && origin->id == id ? origin : nullptr;
}
static void lazy_value_forget(uint32_t id) {
    if (lazy_value_origin(id)) { delete lazy_value_origins[id & 65535u]; lazy_value_origins[id & 65535u] = nullptr; }
}
template<class T> static typename LazyValueTraits<T>::Converter *lazy_converter(BqtRequest *r, uint32_t id, bool writable) {
    auto *origin = lazy_value_origin(id);
    if (!origin) { fail(r, ESTALE, "Deferred conversion has no owned input origin"); return nullptr; }
    if (!origin->converter) { fail(r, EINVAL, "Deferred conversion has no converter"); return nullptr; }
    using Traits = LazyValueTraits<T>;
    return get<typename Traits::Converter>(r, origin->converter, Traits::converter_type, false, writable);
}
template<class T> static bool validate_lazy_value(BqtRequest *r, uint32_t id) {
    auto *e = entry(id); auto *origin = lazy_value_origin(id);
    if (!e || !origin) { fail(r, ESTALE, "Deferred conversion origin expired"); return false; }
    using Traits = LazyValueTraits<T>;
    auto *value = static_cast<T *>(e->value);
    auto backing = std::static_pointer_cast<typename Traits::Backing>(origin->backing);
    typename Traits::View view(*backing);
    if (Traits::data(*value).data() != view.data() || Traits::data(*value).size() != view.size()) {
        fail(r, ESTALE, "Deferred conversion input storage changed outside the binding"); return false;
    }
    if (!origin->converter) {
        if (Traits::converter(*value)) { fail(r, ESTALE, "Deferred converter identity changed"); return false; }
        return true;
    }
    auto *converter = lazy_converter<T>(r, id, false);
    if (r->error) return false;
    if (converter != Traits::converter(*value)) { fail(r, ESTALE, "Deferred conversion converter changed outside the binding"); return false; }
    return true;
}
template<class T> static uint32_t capture_lazy_value(BqtRequest *r, uint32_t id) {
    using Traits = LazyValueTraits<T>;
    auto *e = entry(id); if (!e) return id;
    auto *value = static_cast<T *>(e->value);
    auto next = std::make_unique<LazyValueOrigin>(); next->id = id;
    auto source = native_call_scope && native_call_scope->value_origin ? native_call_scope->value_origin : r->self;
    auto *old = lazy_value_origin(source);
    if (old && entry(source) && entry(source)->type == e->type) {
        next->converter = old->converter; next->backing = old->backing;
    } else {
        auto *converter = Traits::converter(*value);
        if (converter) {
            auto *owner = entry(source);
            if (!owner || !owner->cast || owner->cast(owner->value, Traits::converter_type) != converter) {
                fail(r, ENOTSUP, "Native deferred conversion requires an observed converter call origin"); return 0;
            }
            next->converter = source;
        } else if (!Traits::data(*value).isEmpty()) {
            fail(r, ENOTSUP, "Deferred input view has no observed native origin"); return 0;
        }
        auto data = Traits::data(*value);
        next->backing = std::make_shared<typename Traits::Backing>(data.data(), data.size());
    }
    RetentionBatch batch;
    constexpr uint32_t slot = 0xffffffe1u;
    if (!batch.add(r, id, slot, next->converter, nullptr, false, false, 0) || !batch.finish(r)) return 0;
    Traits::data(*value) = typename Traits::View(*std::static_pointer_cast<typename Traits::Backing>(next->backing));
    lazy_value_forget(id); lazy_value_origins[id & 65535u] = next.release();
    e->validate = validate_lazy_value<T>;
    return id;
}
template<class T, class View> static bool set_lazy_data(BqtRequest *r, uint32_t id, View input) {
    using Traits = LazyValueTraits<T>;
    auto *e = entry(id); auto *origin = lazy_value_origin(id);
    if (!e || !origin) { fail(r, ESTALE, "Deferred conversion origin expired"); return false; }
    if (e->active_calls > 1) { fail(r, EBUSY, "Deferred conversion is active"); return false; }
    auto backing = std::make_shared<typename Traits::Backing>(input.data(), input.size());
    Traits::data(*static_cast<T *>(e->value)) = typename Traits::View(*backing);
    origin->backing = std::move(backing);
    return true;
}
template<class T> static bool set_lazy_converter(BqtRequest *r, uint32_t id, typename LazyValueTraits<T>::Converter *converter) {
    using Traits = LazyValueTraits<T>;
    auto *e = entry(id); auto *origin = lazy_value_origin(id);
    if (!e || !origin) { fail(r, ESTALE, "Deferred conversion origin expired"); return false; }
    if (e->active_calls > 1) { fail(r, EBUSY, "Deferred conversion is active"); return false; }
    uint32_t target = 0;
    if (converter) {
        for (uint32_t i=1; i<capacity; ++i)
            if (entries[i].value && entries[i].cast && entries[i].cast(entries[i].value, Traits::converter_type) == converter) {
                target = token(i, entries[i].generation); break;
            }
        if (!target) { fail(r, ENOTSUP, "Deferred converter must be a registered native handle"); return false; }
        if (!get<typename Traits::Converter>(r, target, Traits::converter_type, false, true)) return false;
    }
    RetentionBatch batch;
    if (!batch.add(r, id, 0xffffffe1u, target, nullptr, false, false, 0) || !batch.finish(r)) return false;
    Traits::converter(*static_cast<T *>(e->value)) = converter;
    origin->converter = target;
    return true;
}
static uint32_t finish_lazy_value_ownership(BqtRequest *r, uint32_t id) try {
    auto *e = entry(id); if (!e) return id;
    uint32_t result = id;
    switch (e->type) {
    // @LAZY_CASES@
    default: return id;
    }
    if (!result) {
        auto *value = e->value; auto destroy = e->destroy;
        invalidate(id); if (destroy) destroy(value);
    }
    return result;
} catch (...) {
    if (auto *e = entry(id)) { auto *value = e->value; auto destroy = e->destroy; invalidate(id); if (destroy) destroy(value); }
    throw;
}
