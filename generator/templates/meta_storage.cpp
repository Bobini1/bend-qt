constexpr uint32_t meta_storage_slot = 0xffffffddu;

static void meta_storage_clear_source(uint32_t id) {
    for (auto &edge : retentions) if (edge.owner == id && edge.slot == meta_storage_slot) edge = {};
    schedule_collection();
}

static bool meta_storage_type(BqtRequest *r, QMetaType type) {
    if (!type.isValid() || type.sizeOf() <= 0 || type.alignOf() <= 0 ||
            (type.alignOf() & (type.alignOf() - 1)) || !type.isDestructible())
        return !fail(r, EINVAL, "Metatype has no valid destructible native storage");
    if (type.flags().testFlag(QMetaType::IsPointer))
        return !fail(r, ENOTSUP, "Raw pointer metatypes need a tracked pointee lifetime");
    return true;
}

static bool meta_storage_ready(BqtRequest *r, MetaStorage *storage, QMetaType expected,
                               bool initialized, bool writing, uint32_t id) {
    if (!storage || !meta_storage_type(r, expected)) return false;
    if (storage->type != expected) { fail(r, EINVAL, "Storage metatype does not match the operation"); return false; }
    if (storage->initialized != initialized) {
        fail(r, initialized ? ENODATA : EALREADY, initialized ? "Storage has no constructed value" : "Storage already has a constructed value");
        return false;
    }
    auto *e = entry(id);
    if (writing && e && e->read_only) {
        fail(r, EPERM, "Metatype storage is read-only"); return false;
    }
    if (writing && (retained(id) || (e && e->active_calls > 1))) {
        fail(r, EBUSY, "Metatype storage is retained or active elsewhere"); return false;
    }
    return true;
}

static uint32_t allocate_meta_storage(BqtRequest *r, QMetaType type) {
    if (!meta_storage_type(r, type)) return 0;
    return own(r, new MetaStorage(type), @TYPE@);
}

static uint32_t create_meta_storage(BqtRequest *r, QMetaType type, const void *copy) {
    if (!meta_storage_type(r, type)) return 0;
    auto value = std::make_unique<MetaStorage>(type);
    if (!type.construct(value->data, copy)) return 0;
    value->initialized = true;
    return own(r, value.release(), @TYPE@);
}

static bool replace_meta_storage_origin(BqtRequest *r, uint32_t id, uint32_t source) {
    if (id == source) return true;
    clear_variant_origin(id);
    if (preserve_variant_origin(r, id, source)) return true;
    // The converter has already written a value. If recording its dependencies
    // fails, destroy it while the source is still pinned by this native call.
    auto *value = entry(id);
    auto *storage = value ? static_cast<MetaStorage *>(value->value) : nullptr;
    if (storage && storage->owns_storage && storage->initialized) {
        storage->type.destruct(storage->data);
        storage->initialized = false;
        meta_storage_clear_source(id);
        storage->source = 0;
    }
    return false;
}
