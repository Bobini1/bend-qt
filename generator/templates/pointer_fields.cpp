struct GeometryAttributeStorage {
    uint32_t token;
    std::vector<QSGGeometry::Attribute> values;
};
static SlotTable<GeometryAttributeStorage *> geometry_attribute_storage;
static GeometryAttributeStorage *geometry_attributes(uint32_t id) {
    auto *value = geometry_attribute_storage[id & 65535u];
    return value && value->token == id ? value : nullptr;
}
static void pointer_fields_forget(uint32_t id) {
    if (geometry_attributes(id)) {
        delete geometry_attribute_storage[id & 65535u];
        geometry_attribute_storage[id & 65535u] = nullptr;
    }
}
static void swap_geometry_attributes(uint32_t first, uint32_t second) {
    if (first == second) return;
    auto &a = geometry_attribute_storage[first & 65535u], &b = geometry_attribute_storage[second & 65535u];
    std::swap(a, b);
    if (a) a->token = first;
    if (b) b->token = second;
}
static bool validate_geometry_attributes(BqtRequest *r, uint32_t id) {
    auto *e = entry(id); auto *storage = geometry_attributes(id);
    if (!e || !storage) { fail(r, ESTALE, "Geometry attribute storage expired"); return false; }
    auto *value = static_cast<QSGGeometry::AttributeSet *>(e->value);
    if (value->count < 0 || size_t(value->count) > storage->values.size() || value->stride < 0 ||
            value->attributes != (storage->values.empty() ? nullptr : storage->values.data())) {
        fail(r, ESTALE, "Geometry attribute storage was replaced outside the binding"); return false;
    }
    return true;
}
static uint32_t fail_pointer_field_value(uint32_t id) {
    if (auto *e = entry(id)) {
        auto *value = e->value; auto destroy = e->destroy;
        invalidate(id); if (destroy) destroy(value);
    }
    return 0;
}
static uint32_t finish_pointer_field_ownership(BqtRequest *r, uint32_t id) try {
    auto *e = entry(id);
    if (e && e->type == @ATTRIBUTE@) { e->render_only = false; return id; }
    if (!e || e->type != @ATTRIBUTE_SET@) return id;
    // Both the descriptor and its array now have ordinary owned value storage.
    e->render_only = false;
    auto *value = static_cast<QSGGeometry::AttributeSet *>(e->value);
    if (value->count < 0 || value->stride < 0 || (value->count && !value->attributes)) {
        fail(r, EINVAL, "Geometry attribute record has no valid array extent"); return fail_pointer_field_value(id);
    }
    auto next = std::make_unique<GeometryAttributeStorage>(); next->token = id;
    if (value->count) next->values.assign(value->attributes, value->attributes + value->count);
    value->attributes = next->values.empty() ? nullptr : next->values.data();
    pointer_fields_forget(id);
    geometry_attribute_storage[id & 65535u] = next.release();
    e->validate = validate_geometry_attributes;
    return id;
} catch (...) {
    fail_pointer_field_value(id);
    throw;
}
static bool geometry_attribute_mutation_allowed(BqtRequest *r, uint32_t id) {
    auto *e = entry(id);
    if (!e || !validate_geometry_attributes(r, id)) return false;
    const unsigned permission = unsigned(e->owned) * 8 + unsigned(retained(id)) * 4 +
                                unsigned(e->active_calls > 1) * 2 + unsigned(e->read_only);
    if (!lifetime_move[permission]) {
        fail(r, EBUSY, "Geometry retains an immutable attribute layout"); return false;
    }
    return true;
}
static bool geometry_attribute_count_allowed(BqtRequest *r, uint32_t id, int count) {
    if (!geometry_attribute_mutation_allowed(r, id)) return false;
    if (count < 0 || size_t(count) > geometry_attributes(id)->values.size()) {
        fail(r, ERANGE, "Attribute count exceeds its owned array"); return false;
    }
    return true;
}
static bool geometry_attribute_stride_allowed(BqtRequest *r, uint32_t id, int stride) {
    if (!geometry_attribute_mutation_allowed(r, id)) return false;
    if (stride < 0) { fail(r, EINVAL, "Geometry stride cannot be negative"); return false; }
    return true;
}
static bool geometry_allocation_allowed(BqtRequest *r, const QSGGeometry::AttributeSet &attributes,
        int vertices, int indices, int index_type) {
    int index_size = index_type == QSGGeometry::UnsignedByteType ? 1 :
                     index_type == QSGGeometry::UnsignedShortType ? 2 :
                     index_type == QSGGeometry::UnsignedIntType ? 4 : 0;
    if (attributes.count <= 0 || attributes.stride <= 0 || !attributes.attributes || vertices < 0 || indices < 0 || !index_size) {
        fail(r, EINVAL, "Geometry needs a nonempty layout and valid allocation dimensions"); return false;
    }
    uint64_t layout_size = 0;
    for (int i=0; i<attributes.count; ++i) {
        const auto &attribute = attributes.attributes[i];
        unsigned scalar_size = 0;
        switch (attribute.type) {
        case QSGGeometry::ByteType: case QSGGeometry::UnsignedByteType: scalar_size=1; break;
        case QSGGeometry::ShortType: case QSGGeometry::UnsignedShortType: case QSGGeometry::Bytes2Type: scalar_size=2; break;
        case QSGGeometry::Bytes3Type: scalar_size=3; break;
        case QSGGeometry::IntType: case QSGGeometry::UnsignedIntType: case QSGGeometry::FloatType: case QSGGeometry::Bytes4Type: scalar_size=4; break;
        case QSGGeometry::DoubleType: scalar_size=8; break;
        }
        if (attribute.position < 0 || attribute.tupleSize < 1 || attribute.tupleSize > 4 || !scalar_size) {
            fail(r, EINVAL, "Geometry contains an invalid attribute descriptor"); return false;
        }
        layout_size += uint64_t(scalar_size) * unsigned(attribute.tupleSize);
    }
    if (layout_size > unsigned(attributes.stride)) {
        fail(r, EINVAL, "Geometry attributes exceed the vertex stride"); return false;
    }
    // Qt 6.12 computes these byte counts and their sum in int arithmetic.
    unsigned allocation_index_size = index_type == QSGGeometry::UnsignedShortType ? 2u : 4u;
    if (uint64_t(vertices) * unsigned(attributes.stride) + uint64_t(indices) * allocation_index_size > INT_MAX) {
        fail(r, EOVERFLOW, "Geometry allocation exceeds Qt's native byte-count range"); return false;
    }
    return true;
}
