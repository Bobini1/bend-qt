static constexpr uint32_t convenience_script_slot = 0xffffff9cu;

static bool convenience_collect_inputs(BqtRequest *r, const BqtValue &wire, unsigned shape,
                                       QVariantList &values, std::vector<uint32_t> &sources) {
    if (!shape) {
        auto *value = get<QVariant>(r, wire.word, @VARIANT_ID@, false, false);
        if (r->error) return false;
        sources.push_back(wire.word);
        values.append(native_owned_snapshot(*value));
        return true;
    }
    if (!wire_shape(r, wire, 2)) return false;
    for (size_t i = 0; i < wire.count; ++i) {
        const auto &item = wire.items[i];
        if (shape == 3) {
            if (!wire_shape(r, item, 2, 2) || !convenience_collect_inputs(r, item.items[1], 0, values, sources)) return false;
        } else if (!convenience_collect_inputs(r, item, shape - 1, values, sources)) return false;
    }
    return true;
}
static uint32_t convenience_capture_inputs(BqtRequest *r, const BqtValue &wire, unsigned shape, uint32_t excluded) {
    NativeCallScope scope;
    QVariantList values;
    std::vector<uint32_t> sources;
    if (!convenience_collect_inputs(r, wire, shape, values, sources)) return 0;
    for (auto source : sources) scope.pin(r, source);
    if (r->error) return 0;
    return generic_variant_snapshot(r, values, excluded, true);
}
static bool convenience_retain_origin(BqtRequest *r, uint32_t owner, uint32_t origin, uint32_t slot, uint32_t key) {
    if (!origin) return true;
    BqtRequest claim{}; claim.self = owner;
    const int relation = prepare_retention(&claim, slot, key, origin);
    if (claim.error) { fail(r, claim.error, claim.message); return false; }
    commit_retention(relation, owner, slot, key, origin, nullptr);
    auto *value = entry(origin);
    value->read_only = true;
    value->scope_owner = 0;
    value->pending_release = true;
    schedule_collection();
    return true;
}
static bool convenience_keep_script_origin(BqtRequest *r, uint32_t owner, uint32_t origin) {
    // JavaScript may keep a QVariant wrapper anywhere in its heap. Its origin
    // lease lasts until engine destruction, like QObject exposure leases.
    return convenience_retain_origin(r, owner, origin, convenience_script_slot, origin);
}
