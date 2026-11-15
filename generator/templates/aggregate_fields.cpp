struct AggregateFieldCopies { uint32_t slot; std::vector<uint32_t> values; };
struct AggregateRecord { uint32_t token; std::vector<AggregateFieldCopies> fields; };
// Native callback inputs, and records Qt returns from its own objects (RHI
// native handles), establish the validity of their QObject fields while
// they are copied. The exact request prevents reentrant Bend calls from using
// this permission, and the scope ends before invoking the callback handler.
struct NativeAggregateInputScope {
    static inline NativeAggregateInputScope *current = nullptr;
    BqtRequest *request;
    NativeAggregateInputScope *previous = current;
    explicit NativeAggregateInputScope(BqtRequest *r) : request(r) { current = this; }
    ~NativeAggregateInputScope() { current = previous; }
};
static SlotTable<AggregateRecord *> aggregate_records;
static AggregateRecord *aggregate_record(uint32_t id) {
    auto *record = aggregate_records[id & 65535u];
    return record && record->token == id ? record : nullptr;
}
static void aggregate_forget(uint32_t id) {
    if (aggregate_record(id)) { delete aggregate_records[id & 65535u]; aggregate_records[id & 65535u] = nullptr; }
}
static void aggregate_swap(uint32_t first, uint32_t second) {
    if (first == second) return;
    auto &left = aggregate_records[first & 65535u], &right = aggregate_records[second & 65535u];
    std::swap(left, right);
    if (left) left->token = first;
    if (right) right->token = second;
}
static bool aggregate_validate(BqtRequest *r, uint32_t id) {
    auto *record = aggregate_record(id);
    if (!record) return true;
    NativeCallScope guard; guard.pin(r, id);
    std::vector<uint32_t> dependencies;
    for (const auto &field : record->fields)
        dependencies.insert(dependencies.end(), field.values.begin(), field.values.end());
    for (auto value : dependencies) {
        auto *copy = entry(value);
        if (!copy) { fail(r, ESTALE, "Aggregate field dependency expired"); return false; }
        if (copy->object) get<QObject>(r, value, copy->type, false, false);
        else get<void>(r, value, copy->type, false, false);
        if (r->error) return false;
    }
    return true;
}
static std::vector<uint32_t> aggregate_source_field(BqtRequest *r, uint32_t slot) {
    auto source = native_call_scope && native_call_scope->value_origin ? native_call_scope->value_origin : r->self;
    if (auto *record = aggregate_record(source))
        for (const auto &field : record->fields) if (field.slot == slot) return field.values;
    if (auto *scope = ValueProvenanceScope::current; scope && scope->call == native_call_scope) return scope->sources;
    return source ? std::vector<uint32_t>{source} : std::vector<uint32_t>{};
}
static bool aggregate_dependent(uint32_t id) {
    auto *e = entry(id);
    if (!e) return false;
    if (e->validate || e->native_owner || has_boundary_backing(id)) return true;
    for (const auto &edge : retentions) if (edge.owner == id && edge.target) return true;
    return false;
}
struct AggregateFieldUpdate {
    BqtRequest *request;
    uint32_t destination;
    std::vector<uint32_t> pins;
    std::unique_ptr<AggregateRecord> next;
    RetentionBatch changes;
    bool prepared = false;
    explicit AggregateFieldUpdate(BqtRequest *r, uint32_t id) : request(r), destination(id) {
        auto *old = aggregate_record(id);
        next = old ? std::make_unique<AggregateRecord>(*old) : std::make_unique<AggregateRecord>(AggregateRecord{id, {}});
    }
    ~AggregateFieldUpdate() { for (auto id : pins) callback_unpin(id); }
    bool pin(uint32_t id) {
        if (std::find(pins.begin(), pins.end(), id) != pins.end()) return true;
        pins.push_back(id);
        if (callback_pin(request, id)) return true;
        pins.pop_back();
        return false;
    }
    bool capture_object(uint32_t slot, const QObject *pointer) {
        std::vector<uint32_t> values;
        if (pointer) {
            uint32_t id = 0;
            for (uint32_t i = 1; i < capacity; ++i)
                if (entries[i].value && entries[i].object == pointer) { id = token(i, entries[i].generation); break; }
            if (!id) { fail(request, ENOTSUP, "QObject field requires an already observed native identity"); return false; }
            get<QObject>(request, id, entry(id)->type, false, false);
            if (request->error) return false;
            if (!pin(id)) return false;
            values.push_back(id);
        }
        for (auto &field : next->fields) if (field.slot == slot) { field.values = std::move(values); return true; }
        next->fields.push_back({slot, std::move(values)});
        return true;
    }
    template<class T> bool capture_pointer(uint32_t slot, T *pointer, uint16_t type, bool callback_pointer = false) {
        using Value = std::remove_cv_t<T>;
        if constexpr (std::is_base_of_v<QObject, Value>) {
            auto *input = NativeAggregateInputScope::current;
            if (pointer && input && input->request == request) {
                uint32_t observed = 0;
                if constexpr (std::is_const_v<T>) observed = borrow_const(request, pointer, type);
                else observed = borrow(request, pointer, type);
                if (!observed) return false;
            }
            return capture_object(slot, pointer);
        }
        else if constexpr (std::is_same_v<Value, QMetaObject>) {
            std::vector<uint32_t> values;
            if (pointer) {
                ConversionValueGuard lease(observe_metadata_field(request, pointer));
                if (request->error) return false;
                auto id = lease.value.word;
                if (!pin(id)) return false;
                if (lease.value.owned_handle) {
                    entry(id)->pending_release = true;
                    lease.value.owned_handle = 0;
                    schedule_collection();
                }
                values.push_back(id);
            }
            for (auto &field : next->fields) if (field.slot == slot) { field.values = std::move(values); return true; }
            next->fields.push_back({slot, std::move(values)});
            return true;
        }
        else {
            std::vector<uint32_t> values;
            if (pointer) {
                uint32_t id = 0;
                for (uint32_t i = 1; i < capacity; ++i)
                    if (entries[i].value == pointer) { id = token(i, entries[i].generation); break; }
                auto *input = NativeAggregateInputScope::current;
                if (!id && callback_pointer && input && input->request == request) {
                    if (!gui_render_depth) { fail(request, EPERM, "Scene graph input requires an active GUI render callback"); return false; }
                    id = register_native_borrow(request, pointer, type, destination);
                    if (request->error) return false;
                }
                if (!id) { fail(request, ENOTSUP, "Native pointer field requires an already observed identity"); return false; }
                auto *checked = get<Value>(request, id, type, false, false);
                if (request->error) return false;
                if (checked != pointer) { fail(request, EINVAL, "Native field identity has a different base address"); return false; }
                if (!pin(id)) return false;
                values.push_back(id);
            }
            for (auto &field : next->fields) if (field.slot == slot) { field.values = std::move(values); return true; }
            next->fields.push_back({slot, std::move(values)});
            return true;
        }
    }
    void keep(BqtValue &wire, std::vector<uint32_t> &copies) {
        for (size_t i=0; i<wire.count; ++i) keep(wire.items[i], copies);
        if (!wire.owned_handle || !aggregate_dependent(wire.owned_handle)) return;
        auto id = wire.owned_handle;
        copies.push_back(id);
        if (!pin(id)) return;
        auto *e = entry(id); e->read_only = true; e->pending_release = true;
        wire.owned_handle = 0;
        schedule_collection();
    }
    template<class Writer> bool capture(uint32_t slot, std::vector<uint32_t> sources, Writer write) {
        std::vector<uint32_t> copies;
        NativeCallScope scope;
        ValueProvenanceScope origins(&scope, std::move(sources));
        ConversionValueGuard wire(write());
        if (request->error) return false;
        keep(wire.value, copies);
        if (request->error) return false;
        for (auto &field : next->fields) if (field.slot == slot) { field.values = std::move(copies); return true; }
        next->fields.push_back({slot, std::move(copies)});
        return true;
    }
    bool prepare() {
        if (auto *old = aggregate_record(destination)) for (const auto &field : old->fields)
            for (auto value : field.values) {
                bool kept = false;
                for (const auto &current : next->fields) if (current.slot == field.slot &&
                        std::find(current.values.begin(), current.values.end(), value) != current.values.end()) kept = true;
                if (!kept && !changes.add(request, destination, field.slot, 0, nullptr, false, false, value)) return false;
            }
        for (const auto &field : next->fields) for (auto value : field.values) {
            // Callback aliases are already children of the copied native
            // argument and are invalidated with it at callback completion.
            if (entry_inside(value, destination)) continue;
            if (!changes.add(request, destination, field.slot, value, nullptr)) return false;
        }
        prepared = true;
        return true;
    }
    void native_failed() {
        if (lifetime_aggregate_commit[unsigned(prepared) * 2] == 1) invalidate_destination();
    }
    bool commit() {
        if (lifetime_aggregate_commit[unsigned(prepared) * 2 + 1] != 2) { fail(request, EINVAL, "Aggregate update was not prepared"); return false; }
        if (!changes.finish(request)) { invalidate_destination(); return false; }
        aggregate_forget(destination);
        aggregate_records[destination & 65535u] = next.release();
        return true;
    }
    void invalidate_destination() {
        if (auto *e = entry(destination)) {
            auto *value = e->value; auto destroy = e->destroy;
            invalidate(destination); if (destroy) destroy(value);
        }
    }
};
static uint32_t finish_aggregate_ownership(BqtRequest *r, uint32_t id) try {
    auto *e = entry(id);
    if (!e) return id;
    // Avoid allocations for classes without dependent aggregate fields.
    bool supported = false;
    switch (e->type) {
    // @AGGREGATE_SUPPORTED@
    default: break;
    }
    if (!supported) return id;
    AggregateFieldUpdate update(r, id);
    switch (e->type) {
    // @AGGREGATE_CASES@
    default: break;
    }
    if (r->error || !update.prepare() || !update.commit()) { update.invalidate_destination(); return 0; }
    return id;
} catch (...) {
    if (auto *e = entry(id)) {
        auto *value = e->value; auto destroy = e->destroy;
        invalidate(id); if (destroy) destroy(value);
    }
    throw;
}

