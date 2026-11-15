
static bool validate_primitive_storage(BqtRequest *r, uint32_t id) {
    auto *record = entry(id);
    if (!record) { fail(r, ESTALE, "JavaScript primitive storage was released"); return false; }
    auto *storage = static_cast<MetaStorage *>(record->value);
    auto *owner = entry(storage->alias_owner);
    if (!owner || owner->type != @PRIMITIVE@) {
        fail(r, ESTALE, "JavaScript primitive storage owner was destroyed"); return false;
    }
    auto *value = static_cast<QJSPrimitiveValue *>(owner->value);
    if (value->metaType() != storage->type || value->constData() != storage->data) {
        fail(r, ESTALE, "JavaScript primitive storage type changed"); return false;
    }
    if (native_call_scope) native_call_scope->pin(r, storage->alias_owner);
    return !r->error;
}

static uint32_t primitive_storage(BqtRequest *r, QJSPrimitiveValue *value, uint32_t owner, bool readonly) {
    if (!value->constData()) return 0;
    auto id = own(r, new MetaStorage(value->metaType(), value->data(), owner), @TYPE@);
    if (!id) return 0;
    BqtRequest claim{}; claim.self = id;
    constexpr uint32_t slot = 0xffffffdbu;
    int edge = prepare_retention(&claim, slot, 0, owner);
    if (claim.error) {
        auto *storage = static_cast<MetaStorage *>(entry(id)->value);
        invalidate(id); delete storage;
        fail(r, claim.error, claim.message); return 0;
    }
    commit_retention(edge, id, slot, 0, owner, nullptr);
    entry(id)->read_only = readonly;
    entry(id)->validate = validate_primitive_storage;
    return id;
}
