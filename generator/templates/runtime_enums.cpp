namespace RuntimeQtObjects { static bool class_identifier(const QByteArray &); }
namespace RuntimeEnums {
struct Type {
    QtPrivate::QMetaTypeInterface interface{};
    QByteArray name, scope, local_name, alias, fingerprint;
    uint32_t flags = 0;
    std::atomic<const QMetaObject *> meta{nullptr};
    bool bound_class = false;
    std::vector<std::pair<QByteArray, uint64_t>> entries;
    QMetaType type() const { return QMetaType(&interface); }
};
static auto *types = new std::vector<Type *>;
static auto *names = new std::map<QByteArray, Type *>;
// Qt can cache both an old namespace view and a later QObject owner view.
// Every emitted table is immutable and remains valid for the process lifetime.
static auto *metadata_arena = new std::set<const QMetaObject *>;
static void build_scope_metadata(const QByteArray &scope) {
    BendMetaObjectBuilder builder;
    builder.setClassName(scope);
    builder.setSuperClass(nullptr);
    for (const auto *type : *types) if (type->scope == scope) {
        const uint flags = ((type->flags & 1u) ? QtMocConstants::EnumIsFlag : 0u) |
                           ((type->flags & 2u) ? QtMocConstants::EnumIsScoped : 0u) |
                           ((type->flags & 4u) ? QtMocConstants::EnumIs64Bit : 0u);
        builder.addEnumerator(type->local_name, type->alias, type->type(), flags, type->entries);
    }
    auto *meta = builder.toMetaObject();
    if (!meta) throw std::bad_alloc();
    try {
        metadata_arena->insert(meta);
        native_metadata_mark_immutable(meta);
    } catch (...) { metadata_arena->erase(meta); std::free(meta); throw; }
    for (auto *type : *types) if (type->scope == scope && !type->bound_class)
        type->meta.store(meta, std::memory_order_release);
}
static void prepare_class(const std::vector<Type *> &enums, const QMetaObject *meta) {
    if (enums.empty()) return;
    metadata_arena->insert(meta);
}
static void bind_class(const std::vector<Type *> &enums, const QMetaObject *meta) noexcept {
    for (auto *type : enums) { type->meta.store(meta, std::memory_order_release); type->bound_class = true; }
}
static bool is_code(int code) { return code >= (1 << 30) && code < INT_MAX; }
static Type *from_code(int code) {
    if (!is_code(code)) return nullptr;
    size_t index = size_t(INT_MAX - 1 - code);
    return index < types->size() ? (*types)[index] : nullptr;
}
static bool identifier(const QByteArray &value) {
    return BendSignalApi::identifier(value);
}
static bool accepts(const BqtValue *wire) {
    return wire && wire->tag == 2 && wire->count && wire->items[0].tag == 1 &&
        QByteArray(wire->items[0].text, qsizetype(wire->items[0].size)) == "enum";
}
static bool in_range(uint32_t flags, uint64_t bits) {
    if (flags & 4u) return true;
    if (flags & 8u) return bits <= UINT32_MAX;
    return bits <= INT32_MAX || bits >= uint64_t(int64_t(INT32_MIN));
}
static Type *ensure(BqtRequest *r, const BqtValue &wire) {
    if (!wire_shape(r, wire, 2, 5) || !accepts(&wire) || wire.items[1].tag != 1 ||
        wire.items[2].tag || wire.items[2].high || (wire.items[2].word & ~15u) ||
        wire.items[3].tag != 1 || wire.items[4].tag != 2) {
        if (!r->error) fail(r, EINVAL, "Invalid Qt enumeration declaration");
        return nullptr;
    }
    auto value = std::make_unique<Type>();
    value->name = QByteArray(wire.items[1].text, qsizetype(wire.items[1].size));
    auto split = value->name.lastIndexOf("::");
    if (split <= 0 || !RuntimeQtObjects::class_identifier(value->name.left(split)) || !identifier(value->name.mid(split + 2))) {
        fail(r, EINVAL, "An enum type needs its QObject scope and name, such as Card::Status"); return nullptr;
    }
    value->scope = value->name.left(split); value->local_name = value->name.mid(split + 2);
    value->flags = wire.items[2].word;
    value->alias = QByteArray(wire.items[3].text, qsizetype(wire.items[3].size));
    if (value->alias.isEmpty()) value->alias = value->local_name;
    if (!identifier(value->alias) || (!(value->flags & 1u) && value->alias != value->local_name)) {
        fail(r, EINVAL, "An enum alias needs a valid flag enumeration name"); return nullptr;
    }
    QByteArray fingerprint = QByteArray::number(value->flags) + ':' + value->alias + ';';
    if (wire.items[4].count > size_t(INT_MAX)) { fail(r, E2BIG, "Too many enumeration keys"); return nullptr; }
    std::set<QByteArray> keys;
    for (size_t i = 0; i < wire.items[4].count; ++i) {
        const auto &entry = wire.items[4].items[i];
        if (!wire_shape(r, entry, 2, 2) || entry.items[0].tag != 1 || entry.items[1].tag) return nullptr;
        QByteArray name(entry.items[0].text, qsizetype(entry.items[0].size));
        if (!identifier(name)) { fail(r, EINVAL, "Invalid enumeration key"); return nullptr; }
        if (!keys.insert(name).second) { fail(r, EEXIST, "Duplicate enumeration key"); return nullptr; }
        uint64_t bits = uint64_t(entry.items[1].word) | (uint64_t(entry.items[1].high) << 32);
        if (!in_range(value->flags, bits)) { fail(r, ERANGE, "Enumeration value is outside its underlying type"); return nullptr; }
        fingerprint += name + '=' + QByteArray::number(bits) + ';';
        if (fingerprint.size() > 4 * 1024 * 1024) { fail(r, E2BIG, "Enumeration schema exceeds its size bound"); return nullptr; }
        value->entries.emplace_back(std::move(name), bits);
    }
    auto previous = names->find(value->name);
    if (previous != names->end()) {
        if (previous->second->fingerprint != fingerprint) { fail(r, EEXIST, "Enumeration name already has a different declaration"); return nullptr; }
        return previous->second;
    }
    if (QMetaType::fromName(value->name).isValid()) { fail(r, EEXIST, "Enumeration conflicts with an existing Qt type"); return nullptr; }
    if (types->size() >= (size_t(1) << 30) - 1) { fail(r, ENOSPC, "Qt enumeration type range exhausted"); return nullptr; }
    value->fingerprint = std::move(fingerprint);
    const auto *source = (value->flags & 4u)
        ? ((value->flags & 8u) ? QMetaType::fromType<quint64>().iface() : QMetaType::fromType<qint64>().iface())
        : ((value->flags & 8u) ? QMetaType::fromType<quint32>().iface() : QMetaType::fromType<qint32>().iface());
    auto &api = value->interface;
    api.revision = QtPrivate::QMetaTypeInterface::CurrentRevision;
    api.alignment = source->alignment; api.size = source->size;
    api.flags = source->flags | QMetaType::IsEnumeration;
    if (value->flags & 8u) api.flags |= QMetaType::IsUnsignedEnumeration;
    api.typeId.storeRelaxed(0); api.name = value->name.constData();
    api.metaObjectFn = [](const QtPrivate::QMetaTypeInterface *self) {
        return reinterpret_cast<const Type *>(self)->meta.load(std::memory_order_acquire);
    };
    api.defaultCtr = source->defaultCtr; api.copyCtr = source->copyCtr;
    api.moveCtr = source->moveCtr; api.dtor = source->dtor;
    api.equals = source->equals; api.lessThan = source->lessThan;
    api.debugStream = source->debugStream;
    api.dataStreamOut = source->dataStreamOut; api.dataStreamIn = source->dataStreamIn;
    api.legacyRegisterOp = nullptr;
    Type *result = value.get();
    types->push_back(result);
    try { names->emplace(value->name, result); }
    catch (...) { types->pop_back(); throw; }
    try { build_scope_metadata(value->scope); }
    catch (...) { names->erase(value->name); types->pop_back(); throw; }
    value.release();
    result->type().registerType();
    return result;
}
static int argument_type(BqtRequest *r, const QByteArray &name, const BqtValue *dependency) {
    if (accepts(dependency)) {
        auto *value = ensure(r, *dependency);
        if (!value) return INT_MIN;
        if (value->name != name) { fail(r, EINVAL, "Enumeration argument has a different native type name"); return INT_MIN; }
    }
    auto found = names->find(name);
    if (found == names->end()) return INT_MIN;
    const auto index = std::find(types->begin(), types->end(), found->second) - types->begin();
    return INT_MAX - 1 - int(index);
}
static QMetaType meta_type(int code) {
    auto *value = from_code(code);
    return value ? value->type() : QMetaType();
}
static std::shared_ptr<BendPropertyBindings::Storage> binding_storage(int code, QMetaType exact,
        BendPropertyBindings::Read read, BendPropertyBindings::Write write) {
    auto *type = from_code(code);
    if (!type) return {};
    if (type->flags & 4u) {
        if (type->flags & 8u) return BendPropertyBindings::make<quint64>(exact, std::move(read), std::move(write));
        return BendPropertyBindings::make<qint64>(exact, std::move(read), std::move(write));
    }
    if (type->flags & 8u) return BendPropertyBindings::make<quint32>(exact, std::move(read), std::move(write));
    return BendPropertyBindings::make<qint32>(exact, std::move(read), std::move(write));
}
static QVariant read_value(BqtRequest *r, int code, const BqtValue &wire) {
    auto *type = from_code(code);
    uint64_t bits = uint64_t(wire.word) | (uint64_t(wire.high) << 32);
    if (!type || wire.tag) { fail(r, EINVAL, "Invalid enumeration value"); return {}; }
    if (!in_range(type->flags, bits)) { fail(r, ERANGE, "Enumeration value is outside its underlying type"); return {}; }
    if (type->flags & 4u) return QVariant(type->type(), &bits);
    uint32_t narrow = uint32_t(bits);
    return QVariant(type->type(), &narrow);
}
static BqtValue write_value(BqtRequest *r, int code, const void *data) {
    auto *type = from_code(code);
    if (!type || !data) { fail(r, EINVAL, "Invalid native enumeration result"); return {}; }
    uint64_t bits = 0;
    if (type->flags & 4u) std::memcpy(&bits, data, sizeof(bits));
    else {
        uint32_t narrow; std::memcpy(&narrow, data, sizeof(narrow));
        bits = !(type->flags & 8u) && (narrow & 0x80000000u) ? uint64_t(int64_t(int32_t(narrow))) : uint64_t(narrow);
    }
    return wide_value(bits);
}
static bool assign_value(BqtRequest *r, int code, void *target, const void *source) {
    auto *type = from_code(code);
    if (!type) { fail(r, EINVAL, "Unknown enumeration type"); return false; }
    if (target && source) std::memcpy(target, source, type->interface.size);
    return true;
}
} // namespace RuntimeEnums
static bool runtime_enum_metadata(const QMetaObject *meta) {
    return RuntimeEnums::metadata_arena->find(meta) != RuntimeEnums::metadata_arena->end();
}
