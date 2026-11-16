namespace RuntimeQtObjects {
// Native operation handlers return whether an operation was recognized. Member
// helpers instead return success; do not use fail()'s handled=true as success.
static bool reject(BqtRequest *r, int code, const char *message) {
    fail(r, code, message); return false;
}
enum PropertyFlags : uint32_t {
    PropertyReadOnly = 1, PropertyConstant = 2, PropertyResettable = 4, PropertyNotStored = 8,
    PropertyNotDesignable = 16, PropertyNotScriptable = 32, PropertyUser = 64,
    PropertyFinal = 128, PropertyRequired = 256, PropertyVirtual = 512, PropertyOverride = 1024,
    PropertyBindable = 2048, PropertyNoNotify = 4096, PropertyRevision = 8192, PropertyExplicitNotify = 16384,
    PropertyAccessMask = PropertyReadOnly | PropertyConstant,
    PropertyKnownFlags = PropertyAccessMask | PropertyResettable | PropertyNotStored | PropertyNotDesignable |
        PropertyNotScriptable | PropertyUser | PropertyFinal | PropertyRequired | PropertyVirtual | PropertyOverride |
        PropertyBindable | PropertyNoNotify | PropertyRevision | PropertyExplicitNotify | 0x3f0000u
};
struct BaseInfo {
    uint16_t id;
    const QMetaObject *meta;
    bool (*constructor)(BqtRequest *);
    int size;
    QObject *(*place)(void *);
    QObject *(*make)();
    int parser, source, interceptor, finalizer;
    bool static_metadata = true;
    bool extension_metadata = true;
};
template<class Proxy, bool Default> static BaseInfo base_info_for(uint16_t id, const QMetaObject *meta, bool (*constructor)(BqtRequest *), bool static_metadata, bool extension_metadata) {
    BaseInfo value{id, meta, constructor, int(sizeof(Proxy)), nullptr, nullptr, -1, -1, -1, -1};
    value.static_metadata = static_metadata;
    value.extension_metadata = extension_metadata;
    if constexpr (Default && !std::is_abstract_v<Proxy>) {
        value.place = [](void *memory) -> QObject * { return new(memory) Proxy; };
        value.make = []() -> QObject * { return new Proxy; };
    }
#if @HAS_QML@
    value.parser = QQmlPrivate::StaticCastSelector<Proxy, QQmlParserStatus>::cast();
    value.source = QQmlPrivate::StaticCastSelector<Proxy, QQmlPropertyValueSource>::cast();
    value.interceptor = QQmlPrivate::StaticCastSelector<Proxy, QQmlPropertyValueInterceptor>::cast();
    value.finalizer = QQmlPrivate::StaticCastSelector<Proxy, QQmlFinalizerHook>::cast();
#endif
    return value;
}
@BASE_DECLARATIONS@
#if defined(BQT_NATIVE_PARTITIONS)
static std::map<uint16_t, BaseInfo (*)()> partition_bases;
using BindingFactory = std::shared_ptr<BendPropertyBindings::Storage> (*)(QMetaType, BendPropertyBindings::Read, BendPropertyBindings::Write);
static std::map<int, BindingFactory> partition_bindings;
#endif
static BaseInfo base_info(uint16_t id) {
    switch (id) {
@BASE_CASES@
    }
#if defined(BQT_NATIVE_PARTITIONS)
    auto found = partition_bases.find(id);
    if (found != partition_bases.end()) return found->second();
#endif
    return {};
}
// BQT_RUNTIME_BODY_BEGIN binding_storage
static std::shared_ptr<BendPropertyBindings::Storage> binding_storage(int code, QMetaType type,
        BendPropertyBindings::Read read, BendPropertyBindings::Write write) {
#if @HAS_QML@
    if (auto *list = BendQmlLists::type_from_code(code)) return list->binding(type, std::move(read), std::move(write));
#endif
    if (code == INT_MAX) return BendPropertyBindings::make<OpaqueData::Value>(type, std::move(read), std::move(write));
    switch (code) {
@BINDING_CASES@
    }
#if defined(BQT_NATIVE_PARTITIONS)
    auto found = partition_bindings.find(code);
    if (found != partition_bindings.end()) return found->second(type, std::move(read), std::move(write));
#endif
    if (RuntimeEnums::is_code(code)) return RuntimeEnums::binding_storage(code, type, std::move(read), std::move(write));
    if (type.flags().testFlag(QMetaType::PointerToQObject))
        return BendPropertyBindings::make<QObject *>(type, std::move(read), std::move(write));
    return {};
}
// BQT_RUNTIME_BODY_END binding_storage
struct PointerType {
    QtPrivate::QMetaTypeInterface interface{};
    std::atomic<const QMetaObject *> meta{nullptr};
    QByteArray name;
    int index;
    PointerType(QByteArray value, int number,
                const QtPrivate::QMetaTypeInterface *source = QMetaType::fromType<QObject *>().iface(),
                bool pointer = true) : name(std::move(value)), index(number) {
        interface.revision = QtPrivate::QMetaTypeInterface::CurrentRevision;
        interface.alignment = source->alignment;
        interface.size = source->size;
        interface.flags = source->flags;
        interface.typeId.storeRelaxed(0);
        if (pointer) interface.metaObjectFn = [](const QtPrivate::QMetaTypeInterface *self) {
            return reinterpret_cast<const PointerType *>(self)->meta.load(std::memory_order_acquire);
        };
        interface.name = name.constData();
        interface.defaultCtr = source->defaultCtr;
        interface.copyCtr = source->copyCtr;
        interface.moveCtr = source->moveCtr;
        interface.dtor = source->dtor;
        interface.equals = source->equals;
        interface.lessThan = source->lessThan;
        interface.debugStream = source->debugStream;
        interface.dataStreamOut = source->dataStreamOut;
        interface.dataStreamIn = source->dataStreamIn;
        interface.legacyRegisterOp = nullptr;
    }
    QMetaType type() const { return QMetaType(&interface); }
};
struct PropertyInfo { QByteArray name; int type; uint32_t flags; int meta_index; uint revision = 0; };
struct MethodInfo { QByteArray signature; std::vector<int> arguments; int result; int meta_index; };
struct ClassInfo {
    QByteArray name, fingerprint;
    BaseInfo base;
    std::shared_ptr<ClassInfo> parent;
    PointerType *pointer = nullptr;
    QMetaObject *meta = nullptr;
    std::vector<PropertyInfo> properties;
    std::map<int, MethodInfo> methods;
    std::vector<RuntimeEnums::Type *> enums;
};
// Qt's global metatype registry and QML caches can retain these interfaces.
// Keep immutable definitions for the process lifetime.
static auto *classes = new std::map<QByteArray, std::shared_ptr<ClassInfo>>;
static auto *pointers = new std::vector<PointerType *>;
static auto *pointer_names = new std::map<QByteArray, PointerType *>;

static std::shared_ptr<ClassInfo> ensure_class(BqtRequest *, const BqtValue &, unsigned = 0);
static bool is_absent(const BqtValue &wire) { return wire.tag == 0 && !wire.word && !wire.high; }
static QByteArray text(const BqtValue &wire) { return QByteArray(wire.text, qsizetype(wire.size)); }
static bool class_identifier(const QByteArray &name) {
    qsizetype begin = 0;
    while (true) {
        auto end = name.indexOf("::", begin);
        if (end < 0) return BendSignalApi::identifier(name.mid(begin));
        if (!BendSignalApi::identifier(name.mid(begin, end - begin))) return false;
        begin = end + 2;
    }
}
// BQT_RUNTIME_BODY_BEGIN bound_native_name
static bool bound_native_name(const QByteArray &name) {
    static const char *const names[] = { @NATIVE_CLASS_NAMES@ };
    const auto end = names + sizeof(names) / sizeof(*names);
    const auto match = std::lower_bound(names, end, name.constData(),
        [](const char *a, const char *b) { return std::strcmp(a, b) < 0; });
    return (match != end && name == *match) || QMetaType::fromName(name).isValid();
}
// BQT_RUNTIME_BODY_END bound_native_name
static std::optional<QTypeRevision> parse_revision(BqtRequest *r, const BqtValue &wire) {
    if (wire.tag || (wire.word != 65535 && wire.word > 254) || wire.high > 254) {
        fail(r, ERANGE, "Revision segments must be between 0 and 254"); return {};
    }
    return wire.word == 65535 ? QTypeRevision::fromMinorVersion(int(wire.high))
        : QTypeRevision::fromVersion(int(wire.word), int(wire.high));
}
static bool fingerprint(BqtRequest *r, const BqtValue &wire, QByteArray &out, unsigned depth = 0) {
    if (depth > 128 || out.size() > 4 * 1024 * 1024) return reject(r, E2BIG, "Qt object schema exceeds its size bound");
    out += char(wire.tag);
    if (wire.tag == 0) { out += QByteArray::number(wire.word) + ',' + QByteArray::number(wire.high) + ';'; }
    else if (wire.tag == 1) { out += QByteArray::number(wire.size) + ':'; out.append(wire.text, qsizetype(wire.size)); }
    else if (wire.tag == 2) {
        out += '[';
        for (size_t i = 0; i < wire.count; ++i) if (!fingerprint(r, wire.items[i], out, depth + 1)) return false;
        out += ']';
    } else return reject(r, EINVAL, "Malformed Qt object schema");
    return true;
}
static PointerType *pointer_type(const QByteArray &name) {
    auto previous = pointer_names->find(name);
    if (previous != pointer_names->end()) return previous->second;
    if (pointers->size() >= size_t(INT_MAX - 1)) throw std::length_error("Qt metatype index range exhausted");
    auto value = std::make_unique<PointerType>(name, int(pointers->size()));
    pointers->push_back(value.get());
    try { pointer_names->emplace(name, value.get()); }
    catch (...) { pointers->pop_back(); throw; }
    return value.release();
}
static PointerType *pointer_from_code(int code) {
    int64_t index = -2 - int64_t(code);
    return index >= 0 && size_t(index) < pointers->size() ? (*pointers)[size_t(index)] : nullptr;
}
static std::optional<BendSignalApi::Declaration> method_declaration(BqtRequest *r, const BqtValue &wire) {
    return BendSignalApi::declaration(r, wire);
}
struct MethodAttributes {
    QList<QByteArray> names;
    QByteArray tag;
    uint32_t flags = 0, access = 2, revision = 0;
};
static std::optional<MethodAttributes> method_attributes(BqtRequest *r, const BqtValue &wire, size_t count) {
    if (!wire_shape(r, wire, 2, 4) || wire.items[0].tag != 2 || wire.items[1].tag != 1 ||
        wire.items[2].tag || wire.items[3].tag) {
        if (!r->error) fail(r, EINVAL, "Invalid QObject method attributes");
        return {};
    }
    MethodAttributes result;
    result.flags = wire.items[2].word; result.access = wire.items[2].high;
    if ((result.flags & ~3u) || result.access > uint32_t(QMetaMethod::Public)) {
        fail(r, EINVAL, "Invalid QObject method flags or access"); return {};
    }
    if (wire.items[0].count && wire.items[0].count != count) {
        fail(r, EINVAL, "Method argument names must match its argument count"); return {};
    }
    for (size_t i = 0; i < wire.items[0].count; ++i) {
        const auto &name = wire.items[0].items[i];
        if (name.tag != 1 || (name.size && !BendSignalApi::identifier(text(name)))) {
            fail(r, EINVAL, "Invalid QObject method argument name"); return {};
        }
        result.names.append(text(name));
    }
    if (wire.items[1].size && std::memchr(wire.items[1].text, 0, wire.items[1].size)) {
        fail(r, EINVAL, "A QObject method tag cannot contain NUL"); return {};
    }
    result.tag = text(wire.items[1]);
    const uint32_t major = wire.items[3].word, minor = wire.items[3].high;
    if (result.flags & 1u) {
        auto revision = parse_revision(r, wire.items[3]);
        if (!revision) return {};
        result.revision = revision->toEncodedVersion<quint16>();
    } else if (major || minor) { fail(r, EINVAL, "A method revision needs the REVISION attribute"); return {}; }
    return result;
}
static std::shared_ptr<ClassInfo> ensure_class(BqtRequest *r, const BqtValue &wire, unsigned depth) {
    if (depth > 64 || !wire_shape(r, wire, 2, 8) || wire.items[0].tag != 1 ||
        wire.items[1].tag || wire.items[1].high || wire.items[3].tag != 2 ||
        wire.items[4].tag != 2 || wire.items[5].tag != 2 || wire.items[6].tag != 2 || wire.items[7].tag != 2) {
        if (!r->error) fail(r, EINVAL, "A Qt object schema needs a name, base and member declarations");
        return {};
    }
    const auto name = text(wire.items[0]);
    if (!class_identifier(name)) { fail(r, EINVAL, "Invalid QObject class name"); return {}; }
    if (BendValueTypes::registry().count(name)) { fail(r, EEXIST, "A value type already has this QObject class name"); return {}; }
    // Pointer metatypes can be registered lazily, so fromName(name + '*')
    // alone cannot reserve native QObject names against dynamic definitions.
    if (bound_native_name(name)) {
        fail(r, EEXIST, "QObject class name conflicts with a native Qt class"); return {};
    }
    QByteArray key;
    if (!fingerprint(r, wire, key)) return {};
    auto previous = classes->find(name);
    if (previous != classes->end()) {
        if (previous->second->fingerprint != key) { fail(r, EEXIST, "QObject class name already has a different schema"); return {}; }
        return previous->second;
    }
    auto value = std::make_shared<ClassInfo>();
    value->name = name;
    value->fingerprint = key;
    if (wire.items[1].word > UINT16_MAX) { fail(r, EINVAL, "Invalid QObject native base"); return {}; }
    value->base = base_info(uint16_t(wire.items[1].word));
    if (!value->base.meta) { fail(r, ENOTSUP, "This native base has no supported subclass wrapper"); return {}; }
    if (!is_absent(wire.items[2])) {
        value->parent = ensure_class(r, wire.items[2], depth + 1);
        if (!value->parent) return {};
        if (value->parent->base.id != value->base.id) { fail(r, EINVAL, "QObject schema inheritance changes its native base"); return {}; }
        value->properties = value->parent->properties;
        value->methods = value->parent->methods;
    }
    const QByteArray pointer_name = name + '*';
    if (pointer_names->find(pointer_name) == pointer_names->end() && QMetaType::fromName(pointer_name).isValid()) {
        fail(r, EEXIST, "QObject class name conflicts with an existing Qt metatype"); return {};
    }
    value->pointer = pointer_type(pointer_name);
    if (!classes->emplace(name, value).second) {
        fail(r, EEXIST, "QObject class name already has a different schema"); return {};
    }
    struct Rollback {
        QByteArray name; bool committed = false;
        ~Rollback() { if (!committed) classes->erase(name); }
    } rollback{name};
    BendMetaObjectBuilder builder;
    builder.setClassName(name);
    const QMetaObject *super = value->parent ? value->parent->meta : value->base.meta;
    if (wire.items[3].count + uint64_t(super->propertyCount()) > INT_MAX ||
        wire.items[3].count + uint64_t(wire.items[4].count) + wire.items[5].count + super->methodCount() > INT_MAX) {
        fail(r, E2BIG, "QObject schema exceeds Qt's native index range"); return {};
    }
    builder.setSuperClass(super);
    std::set<QByteArray> enum_names;
    if (wire.items[7].count + uint64_t(super->enumeratorCount()) > INT_MAX) { fail(r, E2BIG, "Too many QObject enumerations"); return {}; }
    for (size_t i = 0; i < wire.items[7].count; ++i) {
        auto *enumeration = RuntimeEnums::ensure(r, wire.items[7].items[i]);
        if (!enumeration) return {};
        if (enumeration->scope != name) { fail(r, EINVAL, "Enumeration scope differs from its QObject class"); return {}; }
        if (!enum_names.insert(enumeration->local_name).second) { fail(r, EEXIST, "Duplicate QObject enumeration"); return {}; }
        if (enumeration->bound_class) { fail(r, EEXIST, "Enumeration already belongs to a different QObject schema"); return {}; }
        uint flags = ((enumeration->flags & 1u) ? QtMocConstants::EnumIsFlag : 0u) |
                     ((enumeration->flags & 2u) ? QtMocConstants::EnumIsScoped : 0u) |
                     ((enumeration->flags & 4u) ? QtMocConstants::EnumIs64Bit : 0u);
        builder.addEnumerator(enumeration->local_name, enumeration->alias, enumeration->type(), flags, enumeration->entries);
        value->enums.push_back(enumeration);
    }
    std::set<QByteArray> info_keys;
    for (size_t i = 0; i < wire.items[6].count; ++i) {
        const auto &info = wire.items[6].items[i];
        if (!wire_shape(r, info, 2, 2) || info.items[0].tag != 1 || info.items[1].tag != 1) return {};
        auto key = text(info.items[0]), content = text(info.items[1]);
        if (key.contains('\0') || content.contains('\0')) { fail(r, EINVAL, "QObject class info cannot contain NUL"); return {}; }
        if (!info_keys.insert(key).second) { fail(r, EEXIST, "Duplicate QObject class info"); return {}; }
        builder.addClassInfo(key, content);
    }
    struct PropertySignal { int index = -1; QByteArray inherited; };
    std::vector<PropertySignal> property_signals;
    std::set<QByteArray> property_signal_signatures;
    const size_t first_property = value->properties.size();
    for (size_t i = 0; i < wire.items[3].count; ++i) {
        const auto &property = wire.items[3].items[i];
        if (!wire_shape(r, property, 2, 5) || property.items[0].tag != 1 || property.items[2].tag || property.items[2].high ||
            property.items[3].tag || property.items[4].tag != 2) return {};
        const uint32_t flags = property.items[2].word;
        if ((flags & ~PropertyKnownFlags) || (flags & PropertyAccessMask) == PropertyAccessMask ||
            ((flags & PropertyConstant) && (flags & PropertyExplicitNotify)) ||
            ((flags & PropertyExplicitNotify) && (flags & PropertyNoNotify))) {
            fail(r, EINVAL, "Invalid QObject property attributes"); return {};
        }
        auto property_name = text(property.items[0]);
        if (!BendSignalApi::identifier(property_name)) { fail(r, EINVAL, "Invalid QObject property name"); return {}; }
        int inherited = super->indexOfProperty(property_name);
        if (inherited >= 0 && super->property(inherited).isFinal()) {
            fail(r, EPERM, "A final QObject property cannot be overridden"); return {};
        }
#if QT_VERSION >= QT_VERSION_CHECK(6, 11, 0)
        if ((flags & PropertyOverride) && (inherited < 0 || !(super->property(inherited).isVirtual() || super->property(inherited).isOverride()))) {
            fail(r, EINVAL, "An overriding QObject property needs an inherited virtual property"); return {};
        }
#else
        if (flags & (PropertyVirtual | PropertyOverride)) {
            fail(r, ENOTSUP, "Virtual and overriding property metadata requires Qt 6.11"); return {};
        }
#endif
        for (size_t j = first_property; j < value->properties.size(); ++j)
            if (value->properties[j].name == property_name) { fail(r, EEXIST, "Duplicate QObject property"); return {}; }
        uint revision = 0;
        if (flags & PropertyRevision) {
            if ((property.items[3].word != 65535 && property.items[3].word > 254) || property.items[3].high > 254) {
                fail(r, ERANGE, "Property revision segments must be between 0 and 254"); return {};
            }
            revision = ((property.items[3].word == 65535 ? 255 : property.items[3].word) << 8) | property.items[3].high;
        } else if (property.items[3].word || property.items[3].high) {
            fail(r, EINVAL, "A property revision needs the REVISION attribute"); return {};
        }
        int type = BendSignalApi::argument_type(r, property.items[1]);
        if (r->error || type == -1) { if (!r->error) fail(r, EINVAL, "A QObject property cannot have type void"); return {}; }
        if ((flags & 0x3f0000u) && !BendQmlLists::is_code(type)) {
            fail(r, EINVAL, "QML list callback capabilities require a QML list property"); return {};
        }
        if (!BendSignalApi::meta_type(type).isCopyConstructible()) {
            fail(r, ENOTSUP, "A QObject property type must support an owning copy"); return {};
        }
        PropertySignal notify;
        std::optional<BendSignalApi::Declaration> notification_declaration;
        if (!(flags & (PropertyConstant | PropertyNoNotify))) {
            QByteArray signature = property_name + "Changed()";
            if (flags & PropertyExplicitNotify) {
                if (property.items[4].count != 1) { fail(r, EINVAL, "A property needs exactly one NOTIFY declaration"); return {}; }
                auto declaration = method_declaration(r, property.items[4].items[0]);
                if (!declaration) return {};
                if (declaration->types.size() > 1 || (!declaration->types.empty() &&
                    BendSignalApi::meta_type(declaration->types[0]) != BendSignalApi::meta_type(type))) {
                    fail(r, EINVAL, "A NOTIFY signal must take zero arguments or one argument of the property type"); return {};
                }
                signature = declaration->signature;
                notification_declaration = std::move(*declaration);
            } else if (property.items[4].count) { fail(r, EINVAL, "Unexpected property NOTIFY declaration"); return {}; }
            int inherited_signal = super->indexOfMethod(signature);
            if (inherited_signal >= 0) {
                auto method = super->method(inherited_signal);
                if (method.methodType() != QMetaMethod::Signal) { fail(r, EEXIST, "Property notification conflicts with an inherited method"); return {}; }
                notify.inherited = method.name();
            } else {
                notify.index = builder.indexOfMethod(signature);
                if (notify.index < 0) {
                    auto method = builder.addSignal(signature);
                    if (notification_declaration) BendSignalApi::configure_signal(method, *notification_declaration);
                    if (!notification_declaration || !notification_declaration->revision) method.setRevision(revision);
                    notify.index = method.index();
                    property_signal_signatures.insert(signature);
                }
            }
        } else if (property.items[4].count) { fail(r, EINVAL, "A property without notifications cannot declare NOTIFY"); return {}; }
        property_signals.push_back(std::move(notify));
        value->properties.push_back({property_name, type, flags, -1, revision});
    }
    for (size_t i = 0; i < wire.items[4].count; ++i) {
        auto signal = method_declaration(r, wire.items[4].items[i]);
        if (!signal) return {};
        int previous_signal = builder.indexOfMethod(signal->signature);
        if (previous_signal >= 0 && property_signal_signatures.erase(signal->signature)) {
            auto existing = builder.method(previous_signal);
            existing.setParameterNames(signal->parameter_names);
            if (signal->revision) existing.setRevision(signal->revision);
            continue;
        }
        if (super->indexOfMethod(signal->signature) >= 0 || builder.indexOfMethod(signal->signature) >= 0) {
            fail(r, EEXIST, "QObject signal conflicts with another member"); return {};
        }
        auto added = builder.addSignal(signal->signature);
        added.setAccess(QMetaMethod::Public);
        BendSignalApi::configure_signal(added, *signal);
    }
    for (size_t i = first_property; i < value->properties.size(); ++i) {
        auto &property = value->properties[i];
        auto type = BendSignalApi::meta_type(property.type);
        const auto &notification = property_signals[i - first_property];
        auto added = builder.addProperty(property.name, type.name(), type, notification.index);
        if (!notification.inherited.isEmpty()) added.setInheritedNotify(notification.inherited);
        added.setReadable(true); added.setWritable(!(property.flags & PropertyAccessMask));
        added.setConstant(property.flags & PropertyConstant);
        added.setScriptable(!(property.flags & PropertyNotScriptable));
        added.setDesignable(!(property.flags & PropertyNotDesignable));
        added.setUser(property.flags & PropertyUser);
        added.setFinal(property.flags & PropertyFinal);
        added.setVirtual(property.flags & PropertyVirtual);
        added.setOverride(property.flags & PropertyOverride);
        added.setRequired(property.flags & PropertyRequired);
        added.setBindable(property.flags & PropertyBindable);
        added.setRevision(property.revision);
        added.setResettable(property.flags & PropertyResettable);
        added.setStored(!(property.flags & PropertyNotStored));
        property.meta_index = super->propertyCount() + added.index();
    }
    std::vector<MethodInfo> declared_methods;
    for (size_t i = 0; i < wire.items[5].count; ++i) {
        const auto &method = wire.items[5].items[i];
        if (!wire_shape(r, method, 2, 4)) return {};
        BqtValue declaration = sequence_value(2);
        // Borrow the two declaration fields; the request retains ownership.
        declaration.items[0] = method.items[0]; declaration.items[1] = method.items[1];
        auto parsed = method_declaration(r, declaration);
        std::free(declaration.items);
        if (!parsed) return {};
        auto attributes = method_attributes(r, method.items[3], parsed->types.size());
        if (!attributes) return {};
        int result = BendSignalApi::argument_type(r, method.items[2]);
        if (r->error) return {};
        if (result != -1 && !BendSignalApi::meta_type(result).isCopyConstructible()) {
            fail(r, ENOTSUP, "A QObject method return type must support an owning copy"); return {};
        }
        const int inherited_method = super->indexOfMethod(parsed->signature);
        if (inherited_method >= 0) {
            const auto inherited = super->method(inherited_method);
            if (inherited.methodType() == QMetaMethod::Signal) { fail(r, EEXIST, "QObject method conflicts with an inherited signal"); return {}; }
            if (!BendQualifiedTypes::compatible(inherited.returnMetaType(), BendSignalApi::meta_type(result))) {
                fail(r, EINVAL, "An overriding QObject method must keep its return type"); return {};
            }
        }
        if (builder.indexOfMethod(parsed->signature) >= 0) {
            fail(r, EEXIST, "QObject method conflicts with another member"); return {};
        }
        auto added = builder.addSlot(parsed->signature);
        added.setAccess(QMetaMethod::Access(attributes->access));
        added.setMethodType((attributes->flags & 2u) ? QMetaMethod::Method : QMetaMethod::Slot);
        added.setParameterNames(attributes->names);
        added.setTag(attributes->tag);
        added.setRevision(attributes->revision);
        added.setReturnType(BendSignalApi::meta_type(result).name());
        declared_methods.push_back(MethodInfo{parsed->signature, parsed->types, result, -1});
    }
    value->meta = builder.toMetaObject();
    if (!value->meta) throw std::bad_alloc();
    for (auto &method : declared_methods) {
        // Builder slot indices are relative to slots, not to all methods.
        method.meta_index = value->meta->indexOfMethod(method.signature);
        value->methods.emplace(method.meta_index, std::move(method));
    }
    value->pointer->type().registerType();
    RuntimeEnums::prepare_class(value->enums, value->meta);
    native_metadata_mark_immutable(value->meta);
    RuntimeEnums::bind_class(value->enums, value->meta);
    value->pointer->meta.store(value->meta, std::memory_order_release);
    rollback.committed = true;
#if @HAS_QML@
    BendQmlLists::metadata_published(-2 - value->pointer->index);
#endif
    return value;
}
} // namespace RuntimeQtObjects

struct RuntimeObjectState {
    struct Field {
        QVariant value;
        // Reflection can return a pointer to an owning copy when Qt cannot
        // default-construct or assign the declared type in its result buffer.
        QVariant read_cache;
        BendSignalApi::Snapshot guard;
        std::vector<QMetaObject::Connection> watches;
        uint32_t origin = 0, read_cache_origin = 0;
        uint32_t getter = 0, setter = 0;
        bool observed = false;
        bool binding_write = false;
        std::shared_ptr<BendPropertyBindings::Storage> binding;
        std::shared_ptr<BendQmlLists::Context> qml_list;
    };
    QObject *object;
    uint32_t handle;
    std::shared_ptr<RuntimeQtObjects::ClassInfo> schema;
    std::vector<Field> fields;
    std::map<int, uint32_t> methods;
    RuntimeObjectState(QObject *value, uint32_t id, std::shared_ptr<RuntimeQtObjects::ClassInfo> definition)
        : object(value), handle(id), schema(std::move(definition)) {
        for (const auto &property : schema->properties) {
            Field field;
            auto type = BendSignalApi::meta_type(property.type);
            if (type.id() != QMetaType::QVariant && type.isDefaultConstructible()) field.value = QVariant(type);
            fields.push_back(std::move(field));
        }
    }
    ~RuntimeObjectState() {
        for (auto &field : fields) {
            for (auto &watch : field.watches) QObject::disconnect(watch);
            if (field.getter) callback_release_handler(field.getter);
            if (field.setter) callback_release_handler(field.setter);
        }
        for (const auto &method : methods) if (method.second) callback_release_handler(method.second);
    }
};

namespace RuntimeQtObjects {
static constexpr uint32_t property_origin_slot = 0xffffff9fu;
static constexpr uint32_t property_cache_origin_slot = 0xffffff9eu;
static std::shared_ptr<RuntimeObjectState> state(BqtRequest *r) {
    auto *object = get<QObject>(r, r->self, @QOBJECT_ID@);
    if (r->error) return {};
    auto *host = dynamic_cast<RuntimeObjectHost *>(object);
    if (!host || !host->bqt_object) { fail(r, EINVAL, "QObject has no Bend class schema"); return {}; }
    return host->bqt_object;
}
static bool read_field(BqtRequest *, const std::shared_ptr<RuntimeObjectState> &, size_t, bool, QVariant &);
static bool notify(BqtRequest *r, const std::shared_ptr<RuntimeObjectState> &state, size_t index, const QVariant *value = nullptr) {
    const auto &property = state->schema->properties[index];
    auto signal = state->schema->meta->property(property.meta_index).notifySignal();
    if (!signal.isValid()) return true;
    QVariant current;
    void *arguments[] = {nullptr, nullptr};
    if (signal.parameterCount()) {
        if (!value) {
            if (!read_field(r, state, index, false, current)) return false;
            value = &current;
        }
        arguments[1] = BendSignalApi::meta_type(property.type).id() == QMetaType::QVariant
            ? const_cast<QVariant *>(value) : const_cast<void *>(value->constData());
    }
    QMetaObject::activate(state->object, signal.enclosingMetaObject(), signal.methodIndex() - signal.enclosingMetaObject()->methodOffset(), arguments);
    return true;
}
static bool store(BqtRequest *r, const std::shared_ptr<RuntimeObjectState> &state, size_t index, QVariant value, bool announce, bool from_binding = false) {
    auto &field = state->fields[index];
    const auto &property = state->schema->properties[index];
    if ((property.flags & PropertyConstant) && field.observed) return reject(r, EPERM, "A constant property cannot change after its first read");
    value = native_owned_snapshot(value);
    if (field.binding && !from_binding && !field.binding_write) field.binding->clear();
    BendSignalApi::Snapshot guards;
    guards.guard(value);
    BqtValue origin{};
    origin.word = generic_variant_snapshot(r, value, state->handle, false);
    origin.owned_handle = origin.word;
    ConversionValueGuard captured(origin);
    if (r->error) return false;
    BqtRequest previous{};
    const bool previous_live = generic_variant_validate(&previous, field.origin);
    const bool changed = !previous_live || field.value != value;
    std::vector<QMetaObject::Connection> watches;
    try {
        for (const auto &guard : guards.objects) {
            std::weak_ptr<RuntimeObjectState> weak = state;
            watches.push_back(QObject::connect(guard.identity, &QObject::destroyed, state->object, [weak, index] {
                if (auto self = weak.lock()) {
                    BqtRequest request{};
                    if (self->fields[index].binding) self->fields[index].binding->changed();
                    if (!notify(&request, self, index) && request.error) callback_report_error(request.error, request.message);
                }
            }));
        }
    } catch (...) { for (auto &watch : watches) QObject::disconnect(watch); throw; }
    BqtRequest claim{}; claim.self = state->handle;
    const int retained_origin = prepare_retention(&claim, property_origin_slot, uint32_t(index), origin.word);
    if (claim.error) {
        for (auto &watch : watches) QObject::disconnect(watch);
        return reject(r, claim.error, claim.message);
    }
    commit_retention(retained_origin, state->handle, property_origin_slot, uint32_t(index), origin.word, nullptr);
    if (auto *record = entry(origin.word)) {
        record->read_only = true;
        record->scope_owner = 0;
        record->pending_release = true;
    }
    for (auto &watch : field.watches) QObject::disconnect(watch);
    field.watches = std::move(watches);
    field.guard = std::move(guards);
    field.value = std::move(value);
    field.origin = captured.release().word;
    schedule_collection();
    if (changed && field.binding && !from_binding && !field.binding_write) field.binding->changed();
    if (changed && announce) return notify(r, state, index, &field.value);
    return true;
}
static bool decode_void(BqtRequest *r, const BqtValue &value, void *) {
    if (value.tag || value.word || value.high) return reject(r, EINVAL, "A void QObject method returned a value");
    return true;
}
struct Answer {
    int type;
    uint32_t scope;
    std::optional<QVariant> value;
    std::vector<uint32_t> adopted;
    bool committed = false;
    uint32_t origin = 0;
    ~Answer() {
        if (origin) callback_unpin(origin);
        if (committed) return;
        for (auto id : adopted) {
            auto *resource = entry(id);
            if (!resource || resource->scope_owner != scope) continue;
            resource->scope_owner = 0;
            BqtRequest release{}; release.self = id;
            try { release_object(&release); } catch (...) { /* The callback's failure takes precedence. */ }
        }
    }
};
static bool decode_answer(BqtRequest *r, const BqtValue &wire, void *destination) {
    auto *answer = static_cast<Answer *>(destination);
    auto value = BendSignalApi::read_value(r, answer->type, wire);
    if (r->error) return false;
    const uint32_t origin = generic_variant_snapshot(r, value, 0, false);
    if (r->error) return false;
    if (origin) {
        if (!callback_pin(r, origin)) {
            BqtRequest cleanup{}; cleanup.self = origin; release_object(&cleanup);
            return false;
        }
        auto *record = entry(origin);
        record->scope_owner = 0;
        record->pending_release = true;
        if (answer->origin) callback_unpin(answer->origin);
        answer->origin = origin;
    }
    BendSignalApi::Snapshot guard;
    guard.guard(value);
    for (const auto &object : guard.objects)
        if (!scope_adopt_result(r, object.identity, answer->scope, &answer->adopted)) return false;
    for (const auto &object : guard.native_objects)
        if (object.observation && !scope_adopt_native_result(r, object.observation->token, answer->scope, &answer->adopted)) return false;
    answer->value = std::move(value);
    return true;
}
static bool invoke(BqtRequest *r, RuntimeObjectState &state, uint32_t handler,
                   const std::vector<int> &types, const std::vector<QVariant> &values, int result, QVariant *output) {
    if (!handler) return reject(r, ENOSYS, "No Bend handler is installed for this named QObject member");
    BendSignalApi::Snapshot snapshots;
    for (const auto &value : values) snapshots.guard(value, 0, true);
    CallbackNativeArguments native_arguments;
    if (!snapshots.stage_native_arguments(r, native_arguments, state.handle)) return false;
    if (!snapshots.capture_origins(r, state.handle)) return false;
    if (!snapshots.live()) return reject(r, ESTALE, "A QObject method argument expired before its handler ran");
    CallbackOwnedArguments arguments{sequence_value(types.size())};
    for (size_t i = 0; i < types.size(); ++i) {
        const auto &value = values[i];
        arguments.value.items[i] = BendSignalApi::write_value(r, types[i],
            BendSignalApi::meta_type(types[i]).id() == QMetaType::QVariant ? &value : value.constData());
        if (r->error) return false;
    }
    if (!snapshots.finish_output(r, arguments.value)) return false;
    Answer answer{result, r->scope ? r->scope : native_request_scope, {}};
    int error = callback_invoke(handler, state.handle, arguments.take(), result == -1 ? decode_void : decode_answer,
                                result == -1 ? nullptr : &answer);
    if (error) {
        auto *frame = CallFrame::current;
        return reject(r, error, frame && frame->handler_error == error && !frame->handler_message.empty()
            ? frame->handler_message.c_str() : "Bend QObject member handler failed");
    }
    if (result != -1) {
        if (!answer.value) return reject(r, EPROTO, "The QObject handler returned no value");
        if (answer.origin && native_call_scope) {
            native_call_scope->pin(r, answer.origin);
            if (r->error) return false;
            native_call_scope->value_origin = answer.origin;
        }
        if (output) *output = std::move(*answer.value);
    }
    answer.committed = true;
    return true;
}
static bool read_field(BqtRequest *r, const std::shared_ptr<RuntimeObjectState> &state, size_t index, bool storage, QVariant &value) {
    auto &field = state->fields[index];
    const auto &property = state->schema->properties[index];
    if (!storage && field.binding) field.binding->track();
    if (!storage && field.getter) {
        if (!invoke(r, *state, field.getter, {}, {}, property.type, &value)) return false;
        BendSignalApi::Snapshot guard; guard.guard(value);
        if (!guard.live()) return reject(r, ESTALE, "A QObject getter returned a destroyed reference");
    } else {
        if (!generic_variant_validate(r, field.origin)) return false;
        if (!field.guard.live()) {
            auto type = BendSignalApi::meta_type(property.type);
            if (!type.flags().testFlag(QMetaType::PointerToQObject)) return reject(r, ESTALE, "A stored property contains a destroyed QObject reference");
            field.value = QVariant(type);
            field.guard = {};
        }
        value = field.value;
    }
    if (BendSignalApi::meta_type(property.type).id() != QMetaType::QVariant && !value.isValid())
        return reject(r, ENODATA, "The QObject property needs an initial value or a getter");
    if (!storage) field.observed = true;
    return true;
}
static bool reset_field(BqtRequest *r, const std::shared_ptr<RuntimeObjectState> &state, size_t index) {
    if (!(state->schema->properties[index].flags & PropertyResettable))
        return reject(r, ENOTSUP, "The QObject property has no reset method");
    auto found = state->methods.find(-1 - int(index));
    return invoke(r, *state, found == state->methods.end() ? 0 : found->second, {}, {}, -1, nullptr);
}
static bool cache_read(BqtRequest *r, const std::shared_ptr<RuntimeObjectState> &state, size_t index, QVariant value) {
    BqtValue origin{};
    origin.word = generic_variant_snapshot(r, value, state->handle, false);
    origin.owned_handle = origin.word;
    ConversionValueGuard captured(origin);
    if (r->error) return false;
    BqtRequest claim{}; claim.self = state->handle;
    const int retained_origin = prepare_retention(&claim, property_cache_origin_slot, uint32_t(index), origin.word);
    if (claim.error) return reject(r, claim.error, claim.message);
    commit_retention(retained_origin, state->handle, property_cache_origin_slot, uint32_t(index), origin.word, nullptr);
    if (auto *record = entry(origin.word)) {
        record->read_only = true;
        record->scope_owner = 0;
        record->pending_release = true;
    }
    auto &field = state->fields[index];
    field.read_cache = std::move(value);
    field.read_cache_origin = captured.release().word;
    schedule_collection();
    return true;
}
static int property_index(BqtRequest *r, const RuntimeObjectState &state, const BqtValue &wire) {
    if (!wire_shape(r, wire, 2, 5) || wire.items[0].tag != 1) return -1;
    auto name = text(wire.items[0]);
    int type = BendSignalApi::argument_type(r, wire.items[1]);
    if (r->error) return -1;
    for (size_t remaining = state.schema->properties.size(); remaining; --remaining) {
        size_t i = remaining - 1;
        const auto &property = state.schema->properties[i];
        if (property.name == name) {
            if (BendSignalApi::meta_type(property.type) != BendSignalApi::meta_type(type)) {
                fail(r, EINVAL, "QObject property descriptor has the wrong native type"); return -1;
            }
            return int(i);
        }
    }
    fail(r, ENOENT, "QObject class does not declare this property"); return -1;
}
static bool attach_definition(BqtRequest *r, uint32_t id, const std::shared_ptr<ClassInfo> &schema) {
    auto *e = entry(id);
    if (!e || !e->object) return reject(r, ESTALE, "The native QObject constructor returned no live object");
    auto *host = dynamic_cast<RuntimeObjectHost *>(e->object);
    if (!host || host->runtime_base_id() != schema->base.id || !e->proxy)
        return reject(r, EINVAL, "Use the selected native base's newAs constructor for this schema");
    if (host->bqt_object || host->bqt_exposed) return reject(r, EBUSY, "Attach a QObject schema before exposing its native base");
    if (e->object->metaObject() != schema->base.meta && !e->object->metaObject()->inherits(schema->meta))
        return reject(r, ENOTSUP, "This native base needs schema-aware construction with ObjectType.new or its newAs constructor");
    auto value = std::make_shared<RuntimeObjectState>(e->object, id, schema);
    for (size_t index = 0; index < schema->properties.size(); ++index) {
        const auto &property = schema->properties[index];
#if @HAS_QML@
        if (BendQmlLists::is_code(property.type) && !BendQmlLists::attach(r, value, index)) return false;
#endif
        if (!(property.flags & PropertyBindable)) continue;
        std::weak_ptr<RuntimeObjectState> weak = value;
        auto read = [weak, index](bool storage) -> std::optional<QVariant> {
            auto self = weak.lock();
            if (!self) return {};
            BqtRequest request{}; request.self = self->handle;
            QVariant result;
            if (read_field(&request, self, index, storage, result)) return result;
            auto binding = self->fields[index].binding;
            if (binding) binding->readFailed(request.error);
            if (storage && request.error == ENODATA && binding && binding->allowsInitialization()) return {};
            callback_report_error(request.error, request.message);
            return {};
        };
        auto write = [weak, index](QVariant next, bool from_binding) -> bool {
            auto self = weak.lock();
            if (!self) return false;
            BqtRequest request{}; request.self = self->handle;
            auto &field = self->fields[index];
            if (!from_binding && field.binding) field.binding->clear();
            struct Restore { bool &value; bool previous; ~Restore() { value = previous; } } restore{field.binding_write, field.binding_write};
            field.binding_write = from_binding;
            bool ok = field.setter ? invoke(&request, *self, field.setter, {self->schema->properties[index].type}, {next}, -1, nullptr)
                : store(&request, self, index, std::move(next), true, from_binding);
            if (!ok && request.error) callback_report_error(request.error, request.message);
            return ok;
        };
        value->fields[index].binding = binding_storage(property.type, BendSignalApi::meta_type(property.type), std::move(read), std::move(write));
        if (!value->fields[index].binding) return reject(r, ENOTSUP, "The QObject property type has no bindable storage");
        value->fields[index].binding->evaluationScope = [weak]() -> std::shared_ptr<void> {
            auto scope = std::make_shared<NativeCallScope>();
            auto self = weak.lock();
            if (!self) { callback_report_error(ESTALE, "The QObject binding target was destroyed"); return scope; }
            BqtRequest request{};
            scope->pin(&request, self->handle);
            if (request.error) callback_report_error(request.error, request.message);
            return scope;
        };
    }
    host->bqt_object = value;
    e->dynamic_state = value.get();
    return true;
}
static bool create(BqtRequest *r) {
    auto schema = ensure_class(r, r->arguments[0]);
    if (!schema) return true;
    if (!schema->base.constructor) return fail(r, ENOTSUP, "This native base needs one of its schema-aware newAs constructors");
    BqtRequest construction{};
    construction.scope = r->scope;
    RuntimeConstructionMeta metadata(schema->meta, true);
    schema->base.constructor(&construction);
    if (construction.error) { discard_value(construction.result); return fail(r, construction.error, construction.message); }
    if (!attach_definition(r, construction.result.word, schema)) { discard_value(construction.result); return true; }
    r->result = construction.result;
    return true;
}
static bool create_with(BqtRequest *r, uint32_t operation, uint16_t base, bool (*constructor)(BqtRequest *)) {
    auto schema = ensure_class(r, r->arguments[0]);
    if (!schema) return true;
    if (schema->base.id != base) return fail(r, EINVAL, "The schema uses a different native constructor base");
    BqtRequest construction{};
    construction.scope = r->scope;
    construction.operation = operation;
    for (size_t i = 1; i < BQT_ARGUMENT_CAPACITY; ++i) construction.arguments[i - 1] = r->arguments[i];
    RuntimeConstructionMeta metadata(schema->meta, true);
    constructor(&construction);
    if (construction.error) { discard_value(construction.result); return fail(r, construction.error, construction.message); }
    if (!attach_definition(r, construction.result.word, schema)) { discard_value(construction.result); return true; }
    r->result = construction.result;
    return true;
}
static bool attach(BqtRequest *r) {
    NativeCallScope scope;
    get<QObject>(r, r->self, @QOBJECT_ID@);
    if (r->error) return true;
    auto schema = ensure_class(r, r->arguments[0]);
    if (!schema) return true;
    if (attach_definition(r, r->self, schema)) r->result.word = r->self;
    return true;
}
static bool cast(BqtRequest *r) {
    NativeCallScope scope;
    auto *object = get<QObject>(r, r->self, @QOBJECT_ID@);
    if (r->error) return true;
    auto schema = ensure_class(r, r->arguments[0]);
    if (!schema) return true;
    if (!object->metaObject()->inherits(schema->meta)) return fail(r, EINVAL, "QObject does not have the declared Bend class");
    r->result.word = r->self; return true;
}
static bool get_property(BqtRequest *r) {
    NativeCallScope scope;
    auto self = state(r); if (!self) return true;
    int index = property_index(r, *self, r->arguments[0]); if (index < 0) return true;
    if (r->arguments[1].word > 1) return fail(r, EINVAL, "Invalid property storage mode");
    QVariant value;
    if (read_field(r, self, size_t(index), r->arguments[1].word, value)) {
        int type = self->schema->properties[size_t(index)].type;
        r->result = BendSignalApi::write_value(r, type, BendSignalApi::meta_type(type).id() == QMetaType::QVariant ? &value : value.constData());
        if (!r->error) {
            const auto &field = self->fields[size_t(index)];
            const uint32_t origin = r->arguments[1].word || !field.getter ? field.origin : scope.value_origin;
            generic_variant_finish(r, r->result, origin);
        }
    }
    return true;
}
static bool set_property(BqtRequest *r) {
    NativeCallScope scope;
    auto self = state(r); if (!self) return true;
    int index = property_index(r, *self, r->arguments[0]); if (index < 0) return true;
    if (r->arguments[2].word > 1) return fail(r, EINVAL, "Invalid property storage mode");
    auto &field = self->fields[size_t(index)];
    const auto &property = self->schema->properties[size_t(index)];
    bool storage = r->arguments[2].word;
    if (!storage && (property.flags & PropertyAccessMask)) return fail(r, EPERM, "The QML property is read-only");
    auto value = BendSignalApi::read_value(r, property.type, r->arguments[1]);
    if (r->error) return true;
    if (field.binding && !field.binding_write) field.binding->clear();
    if (!storage && field.setter) invoke(r, *self, field.setter, {property.type}, {value}, -1, nullptr);
    else store(r, self, size_t(index), std::move(value), true);
    return true;
}
static bool notify_property(BqtRequest *r) {
    NativeCallScope scope;
    auto self = state(r); if (!self) return true;
    int index = property_index(r, *self, r->arguments[0]); if (index < 0) return true;
    if (self->schema->properties[size_t(index)].flags & PropertyConstant) return fail(r, EPERM, "A constant property has no notify signal");
    if (self->schema->properties[size_t(index)].flags & PropertyNoNotify) return fail(r, ENOTSUP, "The QObject property has no notify signal");
    if (self->fields[size_t(index)].binding && !self->fields[size_t(index)].binding_write) self->fields[size_t(index)].binding->changed();
    notify(r, self, size_t(index)); return true;
}
static bool reset_property(BqtRequest *r) {
    NativeCallScope scope;
    auto self = state(r); if (!self) return true;
    int index = property_index(r, *self, r->arguments[0]); if (index < 0) return true;
    reset_field(r, self, size_t(index));
    return true;
}
static bool bind_property(BqtRequest *r) {
    NativeCallScope scope;
    auto self = state(r); if (!self) return true;
    int target = property_index(r, *self, r->arguments[0]); if (target < 0) return true;
    BqtRequest request{}; request.self = r->arguments[1].word;
    auto source = state(&request);
    if (!source) return fail(r, request.error, request.message);
    int origin = property_index(r, *source, r->arguments[2]); if (origin < 0) return true;
    const auto &destination = self->schema->properties[size_t(target)];
    if (destination.flags & PropertyConstant) return fail(r, EPERM, "A constant property cannot receive a binding");
    auto target_binding = self->fields[size_t(target)].binding;
    auto source_binding = source->fields[size_t(origin)].binding;
    if (!target_binding || !source_binding) return fail(r, ENOTSUP, "Both QObject properties must declare BINDABLE");
    if (BendSignalApi::meta_type(destination.type) != BendSignalApi::meta_type(source->schema->properties[size_t(origin)].type))
        return fail(r, EINVAL, "Bound QObject properties must have the same native type");
    std::weak_ptr<RuntimeObjectState> weak_source = source;
    if (!target_binding->setEvaluator([weak_source, origin](bool) -> std::optional<QVariant> {
        auto source = weak_source.lock();
        if (!source) return {};
        BqtRequest request{}; request.self = source->handle;
        if (native_call_scope) native_call_scope->pin(&request, source->handle);
        QVariant value;
        if (!request.error && read_field(&request, source, size_t(origin), false, value)) return value;
        if (request.error) callback_report_error(request.error, request.message);
        return {};
    })) {
        auto *frame = CallFrame::current;
        if (frame && frame->handler_error) return fail(r, frame->handler_error, frame->handler_message.c_str());
        return fail(r, EINVAL, "Qt rejected the property binding");
    }
    return true;
}
static bool unbind_property(BqtRequest *r) {
    NativeCallScope scope;
    auto self = state(r); if (!self) return true;
    int index = property_index(r, *self, r->arguments[0]); if (index < 0) return true;
    auto binding = self->fields[size_t(index)].binding;
    if (!binding) return fail(r, ENOTSUP, "The QObject property does not declare BINDABLE");
    binding->clear(); return true;
}
static bool has_binding(BqtRequest *r) {
    NativeCallScope scope;
    auto self = state(r); if (!self) return true;
    int index = property_index(r, *self, r->arguments[0]); if (index < 0) return true;
    auto binding = self->fields[size_t(index)].binding;
    r->result.word = binding && binding->bindable(false).hasBinding();
    return true;
}
static bool call_method(BqtRequest *r) {
    NativeCallScope scope;
    auto self = state(r); if (!self) return true;
    const auto &wire = r->arguments[0];
    if (!wire_shape(r, wire, 2, 4)) return true;
    BqtValue fields[] = {wire.items[0], wire.items[1]};
    BqtValue declaration{}; declaration.tag = 2; declaration.count = 2; declaration.items = fields;
    auto method = method_declaration(r, declaration); if (!method) return true;
    if (!method_attributes(r, wire.items[3], method->types.size())) return true;
    int result = BendSignalApi::argument_type(r, wire.items[2]); if (r->error) return true;
    int index = self->schema->meta->indexOfMethod(method->signature);
    auto found = self->schema->methods.find(index);
    if (found == self->schema->methods.end() || found->second.result != result)
        return fail(r, EINVAL, "QObject does not declare this method signature");
    const auto &values = r->arguments[1];
    if (!wire_shape(r, values, 2, method->types.size())) return true;
    std::vector<QVariant> arguments;
    for (size_t i = 0; i < method->types.size(); ++i) {
        arguments.push_back(BendSignalApi::read_value(r, method->types[i], values.items[i]));
        if (r->error) return true;
    }
    QVariant answer;
    if (invoke(r, *self, self->methods[index], method->types, arguments, result, &answer) && result != -1) {
        r->result = BendSignalApi::write_value(r, result, BendSignalApi::meta_type(result).id() == QMetaType::QVariant ? &answer : answer.constData());
        if (!r->error) generic_variant_finish(r, r->result, scope.value_origin);
    }
    return true;
}
static bool install(BqtRequest *r) {
    NativeCallScope scope;
    auto self = state(r); if (!self) return true;
    uint32_t kind = r->arguments[1].word, handler = r->arguments[2].word;
    uint32_t *destination = nullptr;
    if (kind == 0) {
        const auto &wire = r->arguments[0];
        if (!wire_shape(r, wire, 2, 4)) return true;
        BqtValue declaration = sequence_value(2);
        declaration.items[0] = wire.items[0]; declaration.items[1] = wire.items[1];
        auto method = method_declaration(r, declaration);
        std::free(declaration.items);
        if (!method) return true;
        if (!method_attributes(r, wire.items[3], method->types.size())) return true;
        int result = BendSignalApi::argument_type(r, wire.items[2]); if (r->error) return true;
        int index = self->schema->meta->indexOfMethod(method->signature);
        auto found = self->schema->methods.find(index);
        if (found == self->schema->methods.end() || found->second.result != result) return fail(r, EINVAL, "QObject does not declare this method signature");
        destination = &self->methods[index];
    } else if (kind == 4) {
        int index = property_index(r, *self, r->arguments[0]); if (index < 0) return true;
        auto &field = self->fields[size_t(index)];
        if (self->schema->properties[size_t(index)].flags & PropertyConstant)
            return fail(r, EPERM, "A constant property cannot receive a binding");
        if (!field.binding) return fail(r, ENOTSUP, "The QObject property does not declare BINDABLE");
        // The binding owns its handler. Clearing/replacing it releases the
        // captured Bend state immediately, including native/QML binding edits.
        // Arm ownership only on success: a failed install is released by the
        // effect transport that supplied the new handler.
        auto lease = std::make_shared<CallbackFunctionHandler>(0);
        std::weak_ptr<RuntimeObjectState> weak = self;
        bool installed;
        try {
            installed = field.binding->setEvaluator([weak, index, handler, lease](bool) -> std::optional<QVariant> {
                auto self = weak.lock(); if (!self) return {};
                BqtRequest request{}; request.self = self->handle;
                QVariant value;
                if (invoke(&request, *self, handler, {}, {}, self->schema->properties[size_t(index)].type, &value)) return value;
                callback_report_error(request.error, request.message);
                return {};
            });
        } catch (...) {
            field.binding->clear();
            throw;
        }
        if (!installed) {
            field.binding->clear();
            auto *frame = CallFrame::current;
            if (frame && frame->handler_error)
                return fail(r, frame->handler_error, frame->handler_message.c_str());
            return fail(r, EINVAL, "The Bend property binding could not be installed");
        }
        lease->handler = handler;
        return true;
    } else if (kind == 1 || kind == 2 || kind == 3) {
        int index = property_index(r, *self, r->arguments[0]); if (index < 0) return true;
        auto &field = self->fields[size_t(index)];
        const auto flags = self->schema->properties[size_t(index)].flags;
        if (kind != 3 && (flags & PropertyConstant) && field.observed) return fail(r, EBUSY, "A constant property's getter is already observed");
        if (kind == 2 && (flags & PropertyAccessMask)) return fail(r, EPERM, "A read-only property cannot have a QML setter");
        if (kind == 3) {
            if (!(flags & PropertyResettable)) return fail(r, ENOTSUP, "The QObject property has no reset method");
            destination = &self->methods[-1 - index];
        } else destination = kind == 1 ? &field.getter : &field.setter;
    } else return fail(r, EINVAL, "Unknown QObject member handler kind");
    uint32_t previous = *destination;
    *destination = handler;
    if (previous) callback_release_handler(previous);
    return true;
}
} // namespace RuntimeQtObjects

static const QMetaObject *runtime_object_meta(const std::shared_ptr<RuntimeObjectState> &state, const QMetaObject *base) {
    // QML may install its own proxy/VME metaobject after construction, for
    // extensions or properties declared in QML. Preserve that outer layer.
    return state && base == state->schema->base.meta ? state->schema->meta : base;
}
static bool runtime_object_signal_declared(const std::shared_ptr<RuntimeObjectState> &state, const QMetaObject *meta) {
    if (!state) return false;
    for (auto schema = state->schema; schema; schema = schema->parent) if (schema->meta == meta) return true;
    return false;
}
static bool runtime_object_cast(const std::shared_ptr<RuntimeObjectState> &state, const char *name) {
    if (!state || !name) return false;
    for (auto schema = state->schema; schema; schema = schema->parent) if (schema->name == name) return true;
    return false;
}
static int runtime_object_metacall(QObject *object, const std::shared_ptr<RuntimeObjectState> &owner, QMetaObject::Call call, int index, void **arguments,
                                  const std::shared_ptr<std::atomic<bool>> &alive) {
    if (index < 0 || !owner) return index;
    auto state = owner;
    const auto &schema = state->schema;
    // Signal emission is permitted from another thread in Qt. Its immutable
    // declaration needs no registry access; receivers snapshot and queue the
    // values before the emitter can release them.
    if (call == QMetaObject::InvokeMetaMethod && QThread::currentThread() != main_thread) {
        int absolute = schema->base.meta->methodCount() + index;
        if (absolute < schema->meta->methodCount()) {
            auto method = schema->meta->method(absolute);
            if (method.methodType() == QMetaMethod::Signal) {
                QMetaObject::activate(object, method.enclosingMetaObject(),
                    method.methodIndex() - method.enclosingMetaObject()->methodOffset(), arguments);
                return index - (schema->meta->methodCount() - schema->base.meta->methodCount());
            }
        }
    }
    if (QThread::currentThread() != main_thread) {
        // The owning Qt thread keeps its native arguments alive while it waits.
        // Storage, codecs, pins and Bend handlers belong to main, just as for
        // generated virtual handlers. Do not touch that registry on the caller.
        auto keep_alive = alive;
        return callback_from_thread<int>(keep_alive, [&] {
            return runtime_object_metacall(object, state, call, index, arguments, keep_alive);
        }, [index] { return index; });
    }
    BqtRequest request{}; request.self = state->handle;
    NativeCallScope scope;
    try {
        scope.pin(&request, state->handle);
        if (!request.error && (call == QMetaObject::ReadProperty || call == QMetaObject::WriteProperty || call == QMetaObject::ResetProperty || call == QMetaObject::RegisterPropertyMetaType || call == QMetaObject::BindableProperty)) {
            if (size_t(index) < state->fields.size()) {
                auto &field = state->fields[size_t(index)];
                const auto &property = schema->properties[size_t(index)];
                auto type = BendSignalApi::meta_type(property.type);
                if (call == QMetaObject::ReadProperty) {
                    QVariant value;
                    if (RuntimeQtObjects::read_field(&request, state, size_t(index), false, value)) {
                        if (!type.isDefaultConstructible() || !BendSignalApi::can_assign(property.type)) {
                            if (RuntimeQtObjects::cache_read(&request, state, size_t(index), std::move(value)))
                                arguments[0] = const_cast<void *>(field.read_cache.constData());
                        } else BendSignalApi::assign_value(&request, property.type, arguments[0], value);
                    }
                } else if (call == QMetaObject::WriteProperty) {
                    if (property.flags & RuntimeQtObjects::PropertyAccessMask) fail(&request, EPERM, "The QObject property is read-only");
                    else {
                        if (field.binding && !field.binding_write) field.binding->clear();
                        QVariant value = type.id() == QMetaType::QVariant ? *static_cast<QVariant *>(arguments[0]) : QVariant(type, arguments[0]);
                        if (field.setter) RuntimeQtObjects::invoke(&request, *state, field.setter, {property.type}, {value}, -1, nullptr);
                        else RuntimeQtObjects::store(&request, state, size_t(index), std::move(value), true);
                    }
                } else if (call == QMetaObject::ResetProperty) {
                    RuntimeQtObjects::reset_field(&request, state, size_t(index));
                } else if (call == QMetaObject::BindableProperty) {
                    *static_cast<QUntypedBindable *>(arguments[0]) = field.binding
                        ? field.binding->bindable(!(property.flags & RuntimeQtObjects::PropertyAccessMask)) : QUntypedBindable{};
                } else *static_cast<QMetaType *>(arguments[0]) = type;
            }
            index -= int(state->fields.size());
        } else if (!request.error && call == QMetaObject::InvokeMetaMethod) {
            int absolute = schema->base.meta->methodCount() + index;
            if (absolute < schema->meta->methodCount()) {
                auto method = schema->meta->method(absolute);
                if (method.methodType() == QMetaMethod::Signal) QMetaObject::activate(object, method.enclosingMetaObject(), method.methodIndex() - method.enclosingMetaObject()->methodOffset(), arguments);
                else {
                    // An inherited QMetaMethod keeps its original index, but
                    // Bend member overrides dispatch by the child's signature.
                    // Native C++ base slots have already been handled by the
                    // generated proxy's call to its native qt_metacall.
                    const int target = schema->meta->indexOfMethod(method.methodSignature());
                    auto found = schema->methods.find(target);
                    if (found == schema->methods.end()) fail(&request, ENOENT, "Unknown QObject method");
                    else {
                        std::vector<QVariant> values;
                        for (size_t i = 0; i < found->second.arguments.size(); ++i) {
                            auto type = BendSignalApi::meta_type(found->second.arguments[i]);
                            values.push_back(type.id() == QMetaType::QVariant ? *static_cast<QVariant *>(arguments[i + 1]) : QVariant(type, arguments[i + 1]));
                        }
                        QVariant answer;
                        if (RuntimeQtObjects::invoke(&request, *state, state->methods[target], found->second.arguments, values, found->second.result, &answer))
                            BendSignalApi::assign_value(&request, found->second.result, arguments[0], answer);
                    }
                }
            }
            index -= schema->meta->methodCount() - schema->base.meta->methodCount();
        }
    } catch (const std::bad_alloc &) { fail(&request, ENOMEM, "Bend QObject member allocation failed"); }
      catch (...) { fail(&request, EFAULT, "Bend QObject member raised an exception"); }
    if (request.error) {
        callback_report_error(request.error, request.message);
#if @HAS_QML@
        if (object->thread() == main_thread)
            if (auto *engine = qmlEngine(object)) engine->throwError(QString::fromUtf8(request.message ? request.message : "Bend QObject member failed"));
#endif
    }
    return index;
}
static int runtime_argument_index(BqtRequest *r, const QByteArray &name, const BqtValue *dependency) {
    int enumeration = RuntimeEnums::argument_type(r, name, dependency);
    if (r->error || enumeration != INT_MIN) return enumeration;
    if (dependency && !RuntimeQtObjects::is_absent(*dependency) && !RuntimeQtObjects::ensure_class(r, *dependency)) return INT_MIN;
    auto found = RuntimeQtObjects::pointer_names->find(name);
    if (found == RuntimeQtObjects::pointer_names->end()) {
        if (!dependency || !RuntimeQtObjects::is_absent(*dependency) || !name.endsWith('*') ||
            !RuntimeQtObjects::class_identifier(name.chopped(1)) || RuntimeQtObjects::bound_native_name(name.chopped(1))) {
            fail(r, ENOTSUP, "Unknown native QObject argument type"); return INT_MIN;
        }
        // A named QObject reference is a forward declaration. Mutual schemas
        // can be defined before either class has an instance or QML cache.
        auto *pointer = RuntimeQtObjects::pointer_type(name);
        return -2 - pointer->index;
    }
    return -2 - found->second->index;
}
static QMetaType runtime_argument_meta(int code) {
    if (RuntimeValueTypes::is_code(code)) return RuntimeValueTypes::meta_type(code);
#if @HAS_QML@
    if (auto *type = BendQmlLists::type_from_code(code)) return type->native;
#endif
    if (RuntimeEnums::is_code(code)) return RuntimeEnums::meta_type(code);
    auto *pointer = RuntimeQtObjects::pointer_from_code(code);
    return pointer ? pointer->type() : QMetaType();
}
static QVariant runtime_argument_read(BqtRequest *r, int code, const BqtValue &wire) {
    if (RuntimeValueTypes::is_code(code)) return RuntimeValueTypes::read_value(r, code, wire);
#if @HAS_QML@
    if (BendQmlLists::is_code(code)) return BendQmlLists::read_value(r, code, wire);
#endif
    if (RuntimeEnums::is_code(code)) return RuntimeEnums::read_value(r, code, wire);
    auto *pointer = RuntimeQtObjects::pointer_from_code(code);
    if (!pointer || wire.tag || wire.high) { fail(r, EINVAL, "Invalid runtime QObject argument"); return {}; }
    const auto *meta = pointer->meta.load(std::memory_order_acquire);
    QObject *value = nullptr;
    if (wire.word) {
        if (!meta) { fail(r, ENOENT, "The referenced QObject class has not been defined"); return {}; }
        value = get<QObject>(r, wire.word, @QOBJECT_ID@);
        if (r->error) return {};
        if (!value->metaObject()->inherits(meta)) { fail(r, EINVAL, "QObject argument has the wrong Bend class"); return {}; }
    }
    return QVariant(pointer->type(), &value);
}
static BqtValue runtime_argument_write(BqtRequest *r, int code, const void *data) {
    if (RuntimeValueTypes::is_code(code)) return RuntimeValueTypes::write_value(r, code, data);
#if @HAS_QML@
    if (BendQmlLists::is_code(code)) return BendQmlLists::write_value(r, code, data);
#endif
    if (RuntimeEnums::is_code(code)) return RuntimeEnums::write_value(r, code, data);
    auto *pointer = RuntimeQtObjects::pointer_from_code(code);
    if (!pointer) { fail(r, EINVAL, "Unknown runtime QObject argument"); return {}; }
    const auto *meta = pointer->meta.load(std::memory_order_acquire);
    auto *value = *static_cast<QObject *const *>(data);
    if (value && !meta) { fail(r, ENOENT, "The referenced QObject class has not been defined"); return {}; }
    if (value && !value->metaObject()->inherits(meta)) { fail(r, EINVAL, "QObject result has the wrong Bend class"); return {}; }
    BqtValue result{};
    result.word = borrow(r, value, @QOBJECT_ID@);
    result.borrowed_handle = result.word;
    return result;
}
static bool runtime_argument_assign(BqtRequest *r, int code, void *target, const void *source) {
    if (RuntimeValueTypes::is_code(code)) return RuntimeValueTypes::assign_value(r, code, target, source);
#if @HAS_QML@
    if (auto *type = BendQmlLists::type_from_code(code)) return type->assign(target, source);
#endif
    if (RuntimeEnums::is_code(code)) return RuntimeEnums::assign_value(r, code, target, source);
    if (!RuntimeQtObjects::pointer_from_code(code)) return RuntimeQtObjects::reject(r, EINVAL, "Unknown runtime QObject result type");
    if (target) *static_cast<QObject **>(target) = *static_cast<QObject *const *>(source);
    return true;
}

// Signal-only construction shares the same names, immutable definitions and
// native-name reservations as the full QObject declaration API.
static bool runtime_signal_object_create(BqtRequest *r) {
    BqtValue empty{}; empty.tag = 2;
    BqtValue native{}; native.word = @QOBJECT_ID@;
    BqtValue fields[] = {r->arguments[0], native, {}, empty, r->arguments[1], empty, empty, empty};
    BqtValue schema{}; schema.tag = 2; schema.count = std::size(fields); schema.items = fields;
    BqtRequest request{}; request.scope = r->scope; request.arguments[0] = schema;
    RuntimeQtObjects::create(&request);
    if (request.error) return fail(r, request.error, request.message);
    r->result = request.result;
    return true;
}
