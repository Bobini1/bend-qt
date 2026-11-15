// Only peek at the source field here: its aggregate dependencies may contain
// this very child view. The ordinary get() of either object still validates
// those dependencies before an operation can dereference a pointee.
template<class T> static T *protected_fields_owner(BqtRequest *r, uint32_t id, uint16_t type, bool writable = false) {
    auto *record = entry(id);
    if (!record) { fail(r, ESTALE, "The native field owner has expired"); return nullptr; }
    // A child can have another checked alias as its physical owner. Validate
    // that chain before any current-provider dereferences the owner's pointer.
    // Aggregate dependency checks would recurse through the very child view.
    auto ancestor = record->native_owner;
    for (uint32_t depth = 0; ancestor; ++depth) {
        if (depth >= capacity || ancestor == id) {
            fail(r, ELOOP, "The native field owner chain is cyclic"); return nullptr;
        }
        auto *parent = entry(ancestor);
        if (!parent) { fail(r, ESTALE, "The native field ancestor has expired"); return nullptr; }
        if (parent->alive && !(*parent->alive)->load(std::memory_order_acquire)) {
            fail(r, ESTALE, "The native field ancestor was destroyed"); return nullptr;
        }
        if (parent->destroying) { fail(r, EBUSY, "Native field ancestor destruction is in progress"); return nullptr; }
        if (parent->object && parent->object->thread() != main_thread) {
            fail(r, EXDEV, "The native field ancestor belongs to another thread"); return nullptr;
        }
        if (native_call_scope) native_call_scope->pin(r, ancestor);
        if (r->error) return nullptr;
        if (parent->validate && !parent->validate(r, ancestor)) return nullptr;
        parent = entry(ancestor);
        if (!parent || r->error) return nullptr;
        if (!rhi_validate_dependencies(r, ancestor) || !value_provenance_validate(r, ancestor)) return nullptr;
        ancestor = parent->native_owner;
    }
    record = entry(id);
    if (!record) { fail(r, ESTALE, "The native field owner has expired"); return nullptr; }
    if (record->validate && !record->validate(r, id)) return nullptr;
    if (!rhi_validate_dependencies(r, id) || !value_provenance_validate(r, id)) return nullptr;
    return get<T>(r, id, type, false, writable, false);
}
struct ProtectedFieldAlias {
    uint32_t token = 0, owner = 0;
    const void *pointer = nullptr;
    std::function<const void *(BqtRequest *, uint32_t)> current;
    bool (*previous)(BqtRequest *, uint32_t) = nullptr;
    bool checking = false;
};
static SlotTable<ProtectedFieldAlias> protected_field_aliases;
static bool protected_fields_alias_validate(BqtRequest *r, uint32_t id) {
    auto source = protected_field_aliases[id & 65535u];
    if (!entry(id) || source.token != id) {
        if (source.token == id) protected_field_aliases[id & 65535u] = {};
        fail(r, ESTALE, "The native field view has expired"); return false;
    }
    if (source.checking) { fail(r, EBUSY, "The native alias is already being checked"); return false; }
    protected_field_aliases[id & 65535u].checking = true;
    struct Checking {
        uint32_t id;
        ~Checking() {
            auto &value = protected_field_aliases[id & 65535u];
            if (value.token == id) value.checking = false;
        }
    } checking{id};
    NativeCallScope scope;
    if (source.previous && !source.previous(r, id)) return false;
    const auto *pointer = source.current(r, source.owner);
    if (r->error || pointer != source.pointer) {
        if (!r->error) fail(r, ESTALE, "The native field has replaced its previous storage");
        if (r->error == ESTALE) {
            if (entry(id)) invalidate(id);
            if (protected_field_aliases[id & 65535u].token == id)
                protected_field_aliases[id & 65535u] = {};
        }
        return false;
    }
    return true;
}
static bool protected_fields_children_mutable(BqtRequest *r, uint32_t owner) {
    for (const auto &source : protected_field_aliases) {
        if (!source.token || !entry(source.token) || !entry_inside(source.token, owner)) continue;
        for (const auto &edge : retentions) {
            if (!edge.owner || !entry(edge.owner) || !edge.target || !entry(edge.target)) continue;
            if (entry_inside(edge.target, source.token) && !entry_inside(edge.owner, owner)) {
                fail(r, EBUSY, "A native consumer still retains this storage view");
                return false;
            }
        }
    }
    return true;
}
static void protected_fields_expire_children(uint32_t owner) {
    for (auto &source : protected_field_aliases)
        if (source.token && source.owner == owner) {
            const auto id = source.token;
            source = {};
            if (entry(id)) invalidate(id);
        }
}
static void protected_fields_watch(uint32_t id, const void *pointer, uint32_t owner,
        std::function<const void *(BqtRequest *, uint32_t)> current) {
    if (auto *record = entry(id)) {
        auto previous = record->validate;
        const auto &old = protected_field_aliases[id & 65535u];
        if (previous == protected_fields_alias_validate && old.token == id) previous = old.previous;
        protected_field_aliases[id & 65535u] = ProtectedFieldAlias{id, owner, pointer, std::move(current), previous};
        record->validate = protected_fields_alias_validate;
    }
}
template<class T> static uint32_t protected_fields_borrow(BqtRequest *r, T *pointer, uint16_t type,
        uint32_t owner, std::function<const void *(BqtRequest *, uint32_t)> current, bool readonly) {
    if (!pointer) return 0;
    for (uint32_t i = 1; i < capacity; ++i) {
        auto &record = entries[i];
        if (!record.value || !record.cast) continue;
        const auto id = token(i, record.generation);
        if (record.validate == protected_fields_alias_validate) {
            BqtRequest previous{};
            if (!protected_fields_alias_validate(&previous, id)) continue;
        }
        if (record.cast(record.value, type) == pointer) {
            if (!readonly && !std::is_const_v<T>) record.read_only = false;
            return id;
        }
    }
    const auto id = register_native_borrow(r, pointer, type, owner);
    if (auto *record = entry(id)) {
        record->read_only = readonly || std::is_const_v<T>;
        if (record->object) return id;
        protected_fields_watch(id, pointer, owner, std::move(current));
    }
    return id;
}
static void protected_fields_reconcile() {
    for (auto &source : protected_field_aliases) {
        if (!source.token) continue;
        if (!entry(source.token)) { source = {}; continue; }
        BqtRequest request{};
        protected_fields_alias_validate(&request, source.token);
    }
}
