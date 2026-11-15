namespace RuntimeValueTypes {
static constexpr int code_base = 0x10000000;
static constexpr uint32_t schema_marker = 1447119957;
struct Definition {
    BendValueTypes::Type *type;
    std::vector<int> fields;
    int code;
};
static auto &definitions() {
    static auto *state = new std::vector<std::unique_ptr<Definition>>;
    return *state;
}
static bool is_code(int code) { return code >= code_base && code < code_base + int(definitions().size() * 2); }
static Definition *definition(int code) { return is_code(code) ? definitions()[size_t(code - code_base) / 2].get() : nullptr; }
static bool sequence_code(int code) { return (code - code_base) & 1; }
static bool is_schema(const BqtValue *value) {
    return value && value->tag == 2 && value->count == 3 && !value->items[0].tag
        && value->items[0].word == schema_marker && !value->items[0].high;
}
static RuntimeValueTypes::Definition *ensure(BqtRequest *r, const BqtValue &schema) {
    static thread_local unsigned depth;
    if (depth >= 128) { fail(r, E2BIG, "Qt value schemas are nested more than 128 levels"); return nullptr; }
    struct Depth { unsigned &value; Depth(unsigned &n) : value(n) { ++value; } ~Depth() { --value; } } guard(depth);
    if (!is_schema(&schema) || schema.items[1].tag != 1 || schema.items[2].tag != 2) {
        fail(r, EINVAL, "Invalid Qt value type schema"); return nullptr;
    }
    const QByteArray name(schema.items[1].text, qsizetype(schema.items[1].size));
    if (!RuntimeQtObjects::class_identifier(name)) { fail(r, EINVAL, "Invalid Qt value type name"); return nullptr; }
    if (RuntimeQtObjects::classes->count(name)) { fail(r, EEXIST, "A QObject class already has this value type name"); return nullptr; }
    if ((!BendValueTypes::registry().count(name) && RuntimeQtObjects::bound_native_name(name))
        || RuntimeQtObjects::pointer_names->count(name + '*')) {
        fail(r, EEXIST, "A native or declared QObject class already has this value type name"); return nullptr;
    }
    std::vector<BendValueTypes::Field> fields; std::vector<int> codecs;
    const auto &properties = schema.items[2];
    for (size_t i = 0; i < properties.count; ++i) {
        const auto &property = properties.items[i];
        if (property.tag != 2 || property.count != 5 || property.items[0].tag != 1
            || property.items[2].tag || property.items[2].high || property.items[4].tag != 2) {
            fail(r, EINVAL, "Invalid value field declaration"); return nullptr;
        }
        const uint32_t flags = property.items[2].word;
        if ((flags & ~127u) || property.items[4].count) {
            fail(r, ENOTSUP, "This property attribute needs an object or a value member implementation"); return nullptr;
        }
        const QByteArray field(property.items[0].text, qsizetype(property.items[0].size));
        if (!BendSignalApi::identifier(field)) { fail(r, EINVAL, "Invalid value field name"); return nullptr; }
        int code = BendSignalApi::argument_type(r, property.items[1]);
        if (r->error) return nullptr;
        fields.push_back({field, BendSignalApi::meta_type(code), !(flags & 1), bool(flags & 2), bool(flags & 4),
                          !(flags & 8), !(flags & 16), !(flags & 32), bool(flags & 64)});
        codecs.push_back(code);
    }
    BendValueTypes::Type *type;
    try { type = BendValueTypes::define(name, fields); }
    catch (const std::invalid_argument &error) {
        fail(r, BendValueTypes::registry().count(name) || QMetaType::fromName(name).isValid() ? EEXIST : EINVAL, error.what());
        return nullptr;
    }
    for (const auto &existing : definitions()) if (existing->type == type) {
        if (existing->fields != codecs) { fail(r, EEXIST, "This value name has a different field codec"); return nullptr; }
        return existing.get();
    }
    if (definitions().size() >= 0x08000000u) { fail(r, EOVERFLOW, "Too many Qt value schemas"); return nullptr; }
    auto value = std::make_unique<Definition>(); value->type = type; value->fields = std::move(codecs);
    value->code = code_base + int(definitions().size() * 2);
    auto *result = value.get(); definitions().push_back(std::move(value)); return result;
}
static int argument_type(BqtRequest *r, const QByteArray &name, const BqtValue *dependency) {
    if (is_schema(dependency)) {
        auto *value = ensure(r, *dependency); if (!value) return INT_MIN;
        if (name != value->type->name) { fail(r, EINVAL, "Value descriptor has a different native name"); return INT_MIN; }
        return value->code;
    }
    if (name.startsWith("QList<") && dependency && dependency->tag == 2 && dependency->count == 2
        && dependency->items[0].tag == 1
        && QByteArray(dependency->items[0].text, qsizetype(dependency->items[0].size)) == "Bend.Sequence") {
        const auto &argument = dependency->items[1];
        if (argument.tag != 2 || argument.count != 2 || !is_schema(&argument.items[1])) return INT_MIN;
        const int element = BendSignalApi::argument_type(r, argument);
        if (r->error) return INT_MIN;
        auto *value = definition(element);
        if (value && !sequence_code(element) && name == value->type->list_name) return element + 1;
    }
    return INT_MIN;
}
static QMetaType meta_type(int code) {
    auto *value = definition(code);
    return value ? (sequence_code(code) ? value->type->list_type() : value->type->type()) : QMetaType{};
}
static BqtValue store(BqtRequest *r, const QVariant &value) {
    NativeCallScope scope;
    const auto inputs = scope.previous ? scope.previous->pins : std::vector<uint32_t>{};
    // QObject inputs include the property/signal host. An owning value copy
    // retains the objects actually present in its fields, found by Snapshot,
    // rather than retaining that host. Value/view origins still need leases.
    for (auto id : inputs) if (auto *source = entry(id); source && !source->object) scope.pin(r, id);
    BqtValue result{}; result.word = GenericVariants::private_variant(r, value); result.owned_handle = result.word;
    ConversionValueGuard guard(result);
    if (r->error || !GenericVariants::attach_origins(r, result.word, value, scope.pins)) return {};
    return guard.release();
}
static QVariant read_value(BqtRequest *r, int code, const BqtValue &wire) {
    auto *value = definition(code);
    if (!value) { fail(r, EINVAL, "Unknown Qt value argument"); return {}; }
    if (sequence_code(code)) {
        if (wire.tag != 2) { fail(r, EINVAL, "Expected a Qt value sequence"); return {}; }
        QVariant result(value->type->list_type());
        auto *sequence = static_cast<BendValueTypes::Sequence *>(result.data());
        for (size_t i = 0; i < wire.count; ++i) {
            auto element = read_value(r, code - 1, wire.items[i]); if (r->error) return {};
            sequence->values.append(std::move(element));
        }
        return result;
    }
    if (wire.tag || wire.high) { fail(r, EINVAL, "Expected an owning Qt value handle"); return {}; }
    auto *carrier = ::bendqt::get<QVariant>(r, wire.word, @VARIANT_ID@, false, false);
    if (r->error) return {};
    if (carrier->metaType() != value->type->type()) { fail(r, EINVAL, "Qt value has another schema"); return {}; }
    return *carrier;
}
static BqtValue write_value(BqtRequest *r, int code, const void *source) {
    auto *value = definition(code);
    if (!value) { fail(r, EINVAL, "Unknown Qt value result"); return {}; }
    if (!sequence_code(code)) return store(r, QVariant(value->type->type(), source));
    const auto &sequence = *static_cast<const BendValueTypes::Sequence *>(source);
    BqtValue result{}; result.tag = 2; result.count = size_t(sequence.values.size());
    result.items = static_cast<BqtValue *>(std::calloc(result.count, sizeof(BqtValue)));
    if (result.count && !result.items) throw std::bad_alloc();
    ConversionValueGuard guard(result);
    for (size_t i = 0; i < result.count; ++i) {
        result.items[i] = store(r, sequence.values.at(qsizetype(i))); if (r->error) return {};
    }
    return guard.release();
}
static bool assign_value(BqtRequest *r, int code, void *target, const void *source) {
    const auto type = meta_type(code);
    if (!type.isValid()) { fail(r, EINVAL, "Unknown Qt value result type"); return false; }
    if (target) { type.destruct(target); type.construct(target, source); } return true;
}
static bool create(BqtRequest *r) {
    NativeCallScope scope; auto *value = ensure(r, r->arguments[0]); if (!value) return true;
    const auto &wire = r->arguments[1]; const auto mode = r->arguments[2].word;
    if (wire.tag != 2 || mode > 1 || (mode && wire.count != value->fields.size()))
        return fail(r, EINVAL, "The value constructor needs exactly its declared fields");
    auto candidate = value->type->create();
    if (mode) for (size_t i = 0; i < wire.count; ++i) {
        QVariant field = BendSignalApi::read_value(r, value->fields[i], wire.items[i]); if (r->error) return true;
        static_cast<BendValueTypes::Value *>(candidate.data())->fields[qsizetype(i)] = native_owned_snapshot(field);
    }
    r->result = store(r, candidate); return true;
}
static int field_index(BqtRequest *r, const Definition *value, const BqtValue &field) {
    if (field.tag != 2 || field.count != 5 || field.items[0].tag != 1) { fail(r, EINVAL, "Invalid value field descriptor"); return -1; }
    const QByteArray name(field.items[0].text, qsizetype(field.items[0].size));
    int index = value->type->meta->indexOfProperty(name.constData());
    if (index < 0) { fail(r, ENOENT, "This value type has no such field"); return -1; }
    const int code = BendSignalApi::argument_type(r, field.items[1]);
    if (r->error) return -1;
    if (code != value->fields[size_t(index)]) { fail(r, EINVAL, "Value field descriptor has a different type"); return -1; }
    return index;
}
static bool get(BqtRequest *r) {
    NativeCallScope scope; auto *value = ensure(r, r->arguments[0]); if (!value) return true;
    auto *carrier = ::bendqt::get<QVariant>(r, r->arguments[1].word, @VARIANT_ID@, false, false); if (r->error) return true;
    if (carrier->metaType() != value->type->type()) return fail(r, EINVAL, "Qt value has another schema");
    const int index = field_index(r, value, r->arguments[2]); if (index < 0) return true;
    const auto &field = static_cast<const BendValueTypes::Value *>(carrier->constData())->fields.at(index);
    r->result = BendSignalApi::write_value(r, value->fields[size_t(index)],
        BendValueTypes::field_data(value->type->fields[size_t(index)], field));
    if (!r->error) GenericVariants::finish_output(r, r->result, r->arguments[1].word);
    return true;
}
static bool updated(BqtRequest *r) {
    NativeCallScope scope; auto *value = ensure(r, r->arguments[0]); if (!value) return true;
    auto *carrier = ::bendqt::get<QVariant>(r, r->arguments[1].word, @VARIANT_ID@, false, false); if (r->error) return true;
    if (carrier->metaType() != value->type->type()) return fail(r, EINVAL, "Qt value has another schema");
    const int index = field_index(r, value, r->arguments[2]); if (index < 0) return true;
    auto data = BendSignalApi::read_value(r, value->fields[size_t(index)], r->arguments[3]); if (r->error) return true;
    auto candidate = *carrier;
    if (!BendValueTypes::write(candidate, value->type->fields[size_t(index)].name, native_owned_snapshot(data)))
        return fail(r, EPERM, "This Qt value field is not writable");
    r->result = store(r, candidate); return true;
}
static bool register_qml(BqtRequest *r) {
#if @HAS_QML@
    auto *value = ensure(r, r->arguments[0]); if (!value) return true;
    const QByteArray uri(r->arguments[1].text, qsizetype(r->arguments[1].size));
    const QByteArray name(r->arguments[4].text, qsizetype(r->arguments[4].size));
    if (!BendSignalApi::identifier(name) || !QChar::isLower(QString::fromUtf8(name).toUcs4().front())
        || uri.isEmpty() || uri.contains('\0') || r->arguments[2].word > 254 || r->arguments[3].word > 254)
        return fail(r, EINVAL, "A QML value registration needs a URI, lowercase type name and valid version");
    QQmlPrivate::RegisterType registration{};
    registration.structVersion = QQmlPrivate::RegisterType::CurrentVersion;
    registration.typeId = value->type->type(); registration.listId = value->type->list_type();
    registration.uri = intern_native_name(uri.constData(), size_t(uri.size()));
    registration.version = QTypeRevision::fromVersion(r->arguments[2].word, r->arguments[3].word);
    registration.elementName = intern_native_name(name.constData(), size_t(name.size())); registration.metaObject = value->type->meta;
    registration.parserStatusCast = registration.valueSourceCast = registration.valueInterceptorCast = registration.finalizerCast = -1;
    registration.creationMethod = QQmlPrivate::ValueTypeCreationMethod::Structured;
    const int id = QQmlPrivate::qmlregister(QQmlPrivate::TypeRegistration, &registration);
    if (id < 0) return fail(r, EINVAL, "Qt rejected the value registration");
    QQmlPrivate::RegisterSequentialContainer sequence{};
    sequence.uri = registration.uri; sequence.version = registration.version;
    sequence.typeId = value->type->list_type(); sequence.metaSequence = QMetaSequence(&value->type->sequence);
    QQmlPrivate::qmlregister(QQmlPrivate::SequentialContainerRegistration, &sequence);
    r->result.word = uint32_t(id); return true;
#else
    return fail(r, ENOTSUP, "This package has no QtQml module");
#endif
}
} // namespace RuntimeValueTypes
