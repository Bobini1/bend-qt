namespace GenericVariants {
static constexpr uint32_t origin_slot = 0xffffffa2u;
static bool metadata_value(uint16_t type) {
    switch (type) { @METADATA_CASES@ return true; default: return false; }
}
struct WeakOwner {
    uint32_t id = 0, owner = 0;
    bool (*previous)(BqtRequest *, uint32_t) = nullptr;
};
static SlotTable<WeakOwner> weak_owners;
static bool validate_weak_owner(BqtRequest *r, uint32_t id) {
    const auto origin = weak_owners[id & 65535u];
    auto *owner = origin.id == id ? entry(origin.owner) : nullptr;
    if (!owner || (owner->alive && !(*owner->alive)->load(std::memory_order_acquire))) {
        fail(r, ESTALE, "A stored value's QObject owner was destroyed"); return false;
    }
    if (native_call_scope) native_call_scope->pin(r, origin.owner);
    return !r->error && (!origin.previous || origin.previous(r, id));
}
static uint32_t private_variant(BqtRequest *r, const QVariant &value) {
    // Provenance is attached explicitly below. Allocating the private carrier
    // must not accidentally retain the property host through r->self.
    BqtRequest allocation{}; allocation.scope = r->scope;
    NativeCallScope scope;
    ValueProvenanceScope origins(&scope, std::vector<uint32_t>{});
    const uint32_t id = own(&allocation, new QVariant(value), @VARIANT_ID@);
    if (allocation.error) fail(r, allocation.error, allocation.message);
    return id;
}

// Only this private immutable anchor owns the aggregate graph. Public QVariant
// copies use VariantOrigin, so ordinary copy/assign/swap/clear keep their policy.
static bool collect_sources(BqtRequest *r, uint32_t id, uint32_t excluded,
                            std::vector<uint32_t> &seen, std::vector<uint32_t> &sources,
                            bool retain_objects) {
    if (!id || id == excluded || std::find(seen.begin(), seen.end(), id) != seen.end()) return true;
    seen.push_back(id);
    auto *value = entry(id);
    if (!value) { fail(r, ESTALE, "QVariant input origin expired"); return false; }
    if (auto *record = aggregate_record(id)) {
        bool anchor = false;
        for (const auto &field : record->fields) if (field.slot == origin_slot) {
            anchor = true;
            for (uint32_t source : field.values)
                if (!collect_sources(r, source, excluded, seen, sources, retain_objects)) return false;
        }
        if (anchor) return true;
    }
    const auto origin = variant_origins[id & 65535u];
    if (origin.token == id && origin.source)
        return collect_sources(r, origin.source, excluded, seen, sources, retain_objects);
    if (value->object) { if (retain_objects) sources.push_back(id); }
    else if (aggregate_dependent(id)) {
        const bool self = excluded && reaches_token(id, excluded);
        const uint32_t snapshot = variant_snapshots[id & 65535u] == id && !self ? id : make_variant_snapshot(r, id);
        if (!snapshot) return false;
        if (native_call_scope) native_call_scope->pin(r, snapshot);
        if (r->error) return false;
        if (self) {
            // A property already lives inside this owner. A private copy may
            // observe it weakly instead of forming owner -> field -> owner.
            // Returned metadata copies acquire their ordinary strong root in
            // finish_output; external-data copies keep this stale check.
            bool weakened = false;
            for (auto &edge : retentions) if (edge.owner == snapshot && edge.target == excluded) {
                edge = {}; weakened = true;
            }
            if (weakened) {
                auto *copy = entry(snapshot);
                weak_owners[snapshot & 65535u] = {snapshot, excluded, copy->validate};
                copy->validate = validate_weak_owner;
                schedule_collection();
            }
        }
        sources.push_back(snapshot);
    }
    return true;
}
static bool attach_origins(BqtRequest *r, uint32_t result, const QVariant &value,
                           const std::vector<uint32_t> &inputs,
                           uint32_t excluded = 0, bool retain_objects = true) {
    BendSignalApi::Snapshot guards;
    try { guards.guard(value); }
    catch (const std::system_error &error) { fail(r, error.code().value(), error.what()); return false; }
    catch (const std::length_error &error) { fail(r, E2BIG, error.what()); return false; }
    if (!guards.live()) { fail(r, ESTALE, "A QVariant QObject was destroyed"); return false; }
    if (!guards.pin_metadata(r)) return false;
    std::vector<uint32_t> seen{result}, sources;
    auto checked_inputs = inputs;
    if (native_call_scope) for (auto id : native_call_scope->pins)
        if (std::find(checked_inputs.begin(), checked_inputs.end(), id) == checked_inputs.end()) checked_inputs.push_back(id);
    for (uint32_t source : checked_inputs)
        if (!collect_sources(r, source, excluded, seen, sources, retain_objects)) return false;
    // A pointer is a dependency even when it came from an existing QVariant.
    if (retain_objects) for (const auto &guard : guards.objects) {
        uint32_t id = borrow(r, guard.identity, @QOBJECT_ID@);
        if (r->error) return false;
        if (id == excluded) continue;
        if (std::find(sources.begin(), sources.end(), id) == sources.end()) sources.push_back(id);
    }
    if (retain_objects) for (const auto &guard : guards.native_objects) {
        if (!guard.pointer) continue;
        if (!native_pointer_live(guard) || !guard.observation) {
            fail(r, ESTALE, "A QVariant native pointer origin expired"); return false;
        }
        const uint32_t id = guard.observation->token;
        if (id == excluded) continue;
        if (std::find(sources.begin(), sources.end(), id) == sources.end()) sources.push_back(id);
    }
    for (const auto &guard : guards.qml_lists) {
        const uint32_t id = BendQmlLists::owner(r, guard);
        if (r->error) return false;
        if (id && id != excluded && std::find(sources.begin(), sources.end(), id) == sources.end()) sources.push_back(id);
    }
    if (sources.empty()) return true;
    BqtValue anchor_value{};
    anchor_value.word = private_variant(r, value);
    anchor_value.owned_handle = anchor_value.word;
    ConversionValueGuard anchor(anchor_value);
    if (r->error) return false;
    AggregateFieldUpdate update(r, anchor_value.word);
    for (uint32_t source : sources) if (!update.pin(source)) return false;
    update.next->fields.push_back({origin_slot, std::move(sources)});
    if (!update.prepare() || !update.commit()) return false;
    auto *record = entry(anchor_value.word);
    record->read_only = true;
    record->pending_release = true;
    variant_snapshots[anchor_value.word & 65535u] = anchor_value.word;
    return preserve_variant_origin(r, result, anchor_value.word);
}
static uint32_t snapshot(BqtRequest *r, const QVariant &value, uint32_t excluded, bool retain_objects) {
    const auto inputs = native_call_scope ? native_call_scope->pins : std::vector<uint32_t>{};
    BqtValue result{};
    result.word = private_variant(r, value);
    result.owned_handle = result.word;
    ConversionValueGuard guard(result);
    if (r->error || !attach_origins(r, result.word, value, inputs, excluded, retain_objects)) return 0;
    const auto origin = variant_origins[result.word & 65535u];
    if (origin.token != result.word || !origin.source) return 0;
    entry(result.word)->read_only = true;
    variant_snapshots[result.word & 65535u] = result.word;
    return guard.release().word;
}
static uint32_t metadata_owner(uint32_t source, const QMetaObject *expected, std::vector<uint32_t> &seen) {
    if (!source || std::find(seen.begin(), seen.end(), source) != seen.end()) return 0;
    seen.push_back(source);
    if (!entry(source)) return 0;
    const auto origin = metadata_source(source);
    if (origin.root)
        for (const QMetaObject *current = origin.expected; current; current = current->superClass())
            if (current == expected) return source;
    for (const auto &edge : retentions) if (edge.owner == source && edge.target)
        if (uint32_t found = metadata_owner(edge.target, expected, seen)) return found;
    return 0;
}
static bool finish_output(BqtRequest *r, BqtValue &value, uint32_t source) {
    for (size_t i = 0; i < value.count; ++i)
        if (!finish_output(r, value.items[i], source)) return false;
    const uint32_t result = value.owned_handle;
    if (!result) return true;
    auto *record = entry(result);
    if (!record) { fail(r, ESTALE, "Unboxed QVariant value expired"); return false; }
    if (const QMetaObject *expected = metadata_value(record->type) ? metadata_root_pointer(record) : nullptr) {
        std::vector<uint32_t> seen;
        uint32_t owner = metadata_owner(source, expected, seen);
        ConversionValueGuard fallback(BqtValue{});
        if (!owner && immutable_metaobject(expected)) {
            fallback.value = observe_metadata_field(r, expected);
            owner = fallback.value.word;
        }
        if (!owner) { if (!r->error) fail(r, ENOTSUP, "QVariant metadata needs an observed QObject or type origin"); return false; }
        NativeCallScope scope;
        scope.value_origin = owner;
        if (!finish_metadata_ownership(r, result)) return false;
    }
    return preserve_variant_origin(r, result, source);
}
static bool box(BqtRequest *r) {
    NativeCallScope scope;
    const int type = BendSignalApi::argument_type(r, r->arguments[0]);
    if (r->error) return true;
    if (type == -1) return fail(r, EINVAL, "QVariant cannot contain void");
    if (!BendSignalApi::meta_type(type).isValid()) return fail(r, ENOTSUP, "This argument metatype is unavailable in the native payload");
    QVariant value = BendSignalApi::read_value(r, type, r->arguments[1]);
    if (r->error) return true;
    value = native_owned_snapshot(value);
    const auto sources = scope.pins;
    ValueProvenanceScope origins(&scope, sources);
    BqtValue result{};
    result.word = own(r, new QVariant(value), @VARIANT_ID@);
    result.owned_handle = result.word;
    ConversionValueGuard guard(result);
    if (r->error || !attach_origins(r, result.word, value, sources)) return true;
    r->result = guard.release();
    return true;
}
static bool unbox(BqtRequest *r) {
    NativeCallScope scope;
    auto *value = get<QVariant>(r, r->self, @VARIANT_ID@, false, false);
    if (r->error) return true;
    const int type = BendSignalApi::argument_type(r, r->arguments[0]);
    if (r->error) return true;
    const auto requested = BendSignalApi::meta_type(type);
    if (type != -1 && !requested.isValid()) return fail(r, ENOTSUP, "This argument metatype is unavailable in the native payload");
    if (type == -1 || (requested.id() != QMetaType::QVariant && !BendQualifiedTypes::compatible(value->metaType(), requested)))
        return fail(r, EINVAL, "QVariant has a different native metatype; convert it explicitly first");
    scope.value_origin = variant_source_origin(r->self);
    ConversionValueGuard result(BendSignalApi::write_value(r, type,
        requested.id() == QMetaType::QVariant ? value : value->constData()));
    if (r->error || !finish_output(r, result.value, r->self)) return true;
    r->result = result.release();
    return true;
}
static bool independent(QMetaType type) {
    if (type.flags().testFlag(QMetaType::IsEnumeration)) return true;
    switch (type.id()) {
    case QMetaType::Bool: case QMetaType::Int: case QMetaType::UInt:
    case QMetaType::LongLong: case QMetaType::ULongLong: case QMetaType::Long: case QMetaType::ULong:
    case QMetaType::Short: case QMetaType::UShort: case QMetaType::Char: case QMetaType::SChar:
    case QMetaType::UChar: case QMetaType::Char16: case QMetaType::Char32: case QMetaType::QChar:
    case QMetaType::Float: case QMetaType::Double: case QMetaType::QString: case QMetaType::QByteArray:
        return true;
    default: return false;
    }
}
struct MutationGuard {
    uint32_t id;
    QVariant *value;
    bool committed = false;
    ~MutationGuard() {
        if (committed) return;
        value->clear();
        clear_variant_origin(id);
        BqtRequest cleanup{};
        finish_model_index_ownership(&cleanup, id);
    }
};
static bool conversion(BqtRequest *r) {
    NativeCallScope scope;
    const uint32_t mode = r->arguments[1].word;
    if (mode > 1) return fail(r, EINVAL, "Invalid QVariant conversion mode");
    auto *value = get<QVariant>(r, r->self, @VARIANT_ID@, false, mode != 0);
    if (r->error) return true;
    const int type = BendSignalApi::argument_type(r, r->arguments[0]);
    if (r->error) return true;
    if (type == -1) return fail(r, EINVAL, "QVariant cannot convert to void");
    const auto target = BendSignalApi::meta_type(type);
    if (!target.isValid()) return fail(r, ENOTSUP, "This argument metatype is unavailable in the native payload");
    if (!mode) { r->result.word = value->canConvert(target); return true; }
    if (entry(r->self)->active_calls > 1) return fail(r, EBUSY, "QVariant is in another active native call");
    MutationGuard rollback{r->self, value};
    const auto previous = value->metaType();
    r->result.word = value->convert(target);
    if (value->metaType() != previous) {
        clear_variant_origin(r->self);
        if (value->isValid() && !independent(value->metaType())) {
            const auto inputs = scope.pins;
            if (!attach_origins(r, r->self, *value, inputs)) return true;
        }
    }
    finish_model_index_ownership(r, r->self);
    if (!r->error) rollback.committed = true;
    return true;
}
static bool create(BqtRequest *r) {
    r->result.word = own(r, new QVariant, @VARIANT_ID@);
    r->result.owned_handle = r->result.word;
    return true;
}
static bool is_valid(BqtRequest *r) {
    NativeCallScope scope;
    auto *value = get<QVariant>(r, r->self, @VARIANT_ID@, false, false);
    if (!r->error) r->result.word = value->isValid();
    return true;
}
static bool is_null(BqtRequest *r) {
    NativeCallScope scope;
    auto *value = get<QVariant>(r, r->self, @VARIANT_ID@, false, false);
    if (!r->error) r->result.word = value->isNull();
    return true;
}
static bool clear(BqtRequest *r) {
    NativeCallScope scope;
    auto *value = get<QVariant>(r, r->self, @VARIANT_ID@);
    if (r->error) return true;
    if (entry(r->self)->active_calls > 1) return fail(r, EBUSY, "QVariant is in another active native call");
    value->clear();
    clear_variant_origin(r->self);
    finish_model_index_ownership(r, r->self);
    return true;
}
static bool meta_type(BqtRequest *r) {
    NativeCallScope scope;
    auto *value = get<QVariant>(r, r->self, @VARIANT_ID@, false, false);
    if (r->error) return true;
    r->result.word = own(r, new QMetaType(value->metaType()), @METATYPE_ID@);
    r->result.owned_handle = r->result.word;
    return true;
}
} // namespace GenericVariants
static bool generic_variant_finish(BqtRequest *r, BqtValue &value, uint32_t source) {
    return GenericVariants::finish_output(r, value, source);
}
static uint32_t generic_variant_snapshot(BqtRequest *r, const QVariant &value, uint32_t excluded, bool retain_objects) {
    return GenericVariants::snapshot(r, value, excluded, retain_objects);
}
static bool generic_variant_validate(BqtRequest *r, uint32_t source) {
    if (source) get<QVariant>(r, source, @VARIANT_ID@, false, false);
    return !r->error;
}
static bool generic_variant_refresh(BqtRequest *r, uint32_t id) {
    auto *record = entry(id);
    if (!record) { fail(r, ESTALE, "Converted QVariant was destroyed"); return false; }
    const auto &value = *static_cast<QVariant *>(record->value);
    if (!value.isValid() || GenericVariants::independent(value.metaType())) return true;
    const auto inputs = native_call_scope ? native_call_scope->pins : std::vector<uint32_t>{};
    GenericVariants::MutationGuard rollback{id, static_cast<QVariant *>(record->value)};
    bool attached = GenericVariants::attach_origins(r, id, value, inputs);
    if (attached) rollback.committed = true;
    return attached;
}
