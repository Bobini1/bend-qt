// Ordinary value copies are independent. Values with an observed external
// origin carry that origin through QVariant without exposing a raw pointer.
constexpr uint32_t variant_origin_slot = 0xffffffdcu;
struct VariantOrigin {
    uint32_t token, source;
    bool (*previous)(BqtRequest *, uint32_t);
};
static SlotTable<VariantOrigin> variant_origins;
static SlotTable<uint32_t> variant_snapshots;
static uint32_t make_variant_snapshot(BqtRequest *, uint32_t);
static bool generic_variant_refresh(BqtRequest *, uint32_t);
static bool generic_variant_finish(BqtRequest *, BqtValue &, uint32_t);
static uint32_t generic_variant_snapshot(BqtRequest *, const QVariant &, uint32_t, bool);
static bool generic_variant_validate(BqtRequest *, uint32_t);

static uint32_t variant_source_origin(uint32_t id) {
    auto origin = variant_origins[id & 65535u];
    return origin.token == id && entry(id) ? origin.source : id;
}

static bool validate_variant_origin(BqtRequest *r, uint32_t id) {
    auto origin = variant_origins[id & 65535u];
    if (origin.token != id || !entry(origin.source)) {
        fail(r, ESTALE, "QVariant native value origin expired"); return false;
    }
    auto *source = entry(origin.source);
    if (!value_provenance_validate(r, origin.source) || !aggregate_validate(r, origin.source)) return false;
    if (source->validate && !source->validate(r, origin.source)) return false;
    if (origin.previous && !origin.previous(r, id)) return false;
    if (native_call_scope) native_call_scope->pin(r, origin.source);
    return !r->error;
}

static bool preserve_variant_origin(BqtRequest *r, uint32_t id, uint32_t source_id) {
    if (id == source_id) return true;
    source_id = variant_source_origin(source_id);
    auto *value = entry(id), *source = entry(source_id);
    if (!value || !source) return !r->error;
    bool dependent = source->validate || source->native_owner || has_boundary_backing(source_id);
    for (const auto &edge : retentions) if (edge.owner == source_id && edge.target) dependent = true;
    if (!dependent) return true;
    // A copied value must not follow later assignment of its source wrapper.
    // Keep a private read-only copy carrying the original native dependencies.
    if (variant_snapshots[source_id & 65535u] != source_id) {
        source_id = make_variant_snapshot(r, source_id);
        if (!source_id) return false;
        source = entry(source_id);
    }
    BqtRequest claim{}; claim.self = id;
    int index = prepare_retention(&claim, variant_origin_slot, 0, source_id);
    if (claim.error) { fail(r, claim.error, claim.message); return false; }
    commit_retention(index, id, variant_origin_slot, 0, source_id, nullptr);
    auto *model = model_index_origins[id & 65535u];
    const bool model_outer = value->validate == validate_model_index && model;
    auto previous = model_outer ? model->previous : value->validate;
    if (previous == validate_variant_origin && variant_origins[id & 65535u].token == id)
        previous = variant_origins[id & 65535u].previous;
    variant_origins[id & 65535u] = {id, source_id, previous};
    if (model_outer) model->previous = validate_variant_origin;
    else value->validate = validate_variant_origin;
    return true;
}

static void clear_variant_origin(uint32_t id) {
    clear_value_provenance(id);
    auto *value = entry(id);
    auto &origin = variant_origins[id & 65535u];
    if (value && origin.token == id && value->validate == validate_variant_origin)
        value->validate = origin.previous;
    else if (value && origin.token == id && value->validate == validate_model_index) {
        auto *model = model_index_origins[id & 65535u];
        if (model && model->previous == validate_variant_origin) model->previous = origin.previous;
    }
    origin = {};
    for (auto &edge : retentions) if (edge.owner == id && edge.slot == variant_origin_slot) edge = {};
    schedule_collection();
}

static void swap_variant_origins(uint32_t first, uint32_t second) {
    if (first == second) return;
    auto *left = entry(first), *right = entry(second);
    if (!left || !right) return;
    auto &a = variant_origins[first & 65535u], &b = variant_origins[second & 65535u];
    if (a.token != first) a = {};
    if (b.token != second) b = {};
    std::swap(a, b);
    if (a.source) a.token = first;
    if (b.source) b.token = second;
    std::swap(model_index_origins[first & 65535u], model_index_origins[second & 65535u]);
    std::swap(left->validate, right->validate);
}

static bool assign_variant_origin(BqtRequest *r, uint32_t target, uint32_t source) {
    if (target == source) return true;
    clear_variant_origin(target);
    if (preserve_variant_origin(r, target, source)) return copy_value_provenance(r, target, source);
    // Allocation/retention failure cannot leave a newly copied, unguarded value.
    if (auto *record = entry(target)) static_cast<QVariant *>(record->value)->clear();
    finish_model_index_ownership(r, target);
    return false;
}
