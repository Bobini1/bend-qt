// Emit the metadata format consumed by compiled Qt 6 moc objects. There are
// no private Qt symbols here: future Qt 6 runtimes must still read revision 13
// metadata emitted by Qt 6.12 moc. Keep this small subset aligned with the
// ordinary moc layout, not the in-memory layout of QMetaObjectBuilder.
class BendMetaObjectBuilder {
    struct Method {
        QByteArray signature, name, result = "void", tag;
        QList<QByteArray> arguments, parameter_names;
        uint flags;
        uint revision = 0;
    };
    struct Property {
        QByteArray name, type_name;
        QMetaType type;
        uint flags = QtMocConstants::Readable | QtMocConstants::Writable | QtMocConstants::Designable | QtMocConstants::Scriptable | QtMocConstants::Stored;
        int notify;
        uint revision = 0;
        QByteArray inherited_notify;
    };
    QByteArray class_name;
    struct Enumeration {
        QByteArray name, alias;
        QMetaType type;
        uint flags;
        std::vector<std::pair<QByteArray, uint64_t>> entries;
    };
    const QMetaObject *super = &QObject::staticMetaObject;
    const QtPrivate::QMetaTypeInterface *self_type = nullptr;
    uint meta_flags = 0;
    std::vector<Method> methods;
    std::vector<Property> properties;
    std::vector<Enumeration> enumerations;
    std::vector<std::pair<QByteArray, QByteArray>> class_info;
    uint signals_count = 0;
    static QList<QByteArray> parameters(const QByteArray &signature) {
        QList<QByteArray> values;
        auto begin = signature.indexOf('(') + 1;
        auto end = signature.lastIndexOf(')');
        int depth = 0;
        for (auto i = begin; i < end; ++i) {
            char c = signature[i];
            if (c == '<' || c == '(' || c == '[') ++depth;
            else if (c == '>' || c == ')' || c == ']') --depth;
            else if (c == ',' && !depth) { values.append(signature.mid(begin, i - begin)); begin = i + 1; }
        }
        if (begin < end) values.append(signature.mid(begin, end - begin));
        return values;
    }
public:
    class MethodRef {
        BendMetaObjectBuilder *owner;
        size_t number;
    public:
        MethodRef(BendMetaObjectBuilder *value, size_t index) : owner(value), number(index) {}
        int index() const { return int(number); }
        void setAccess(QMetaMethod::Access access) { auto &flags = owner->methods[number].flags; flags = (flags & ~3u) | uint(access); }
        void setReturnType(const QByteArray &type) { owner->methods[number].result = QMetaObject::normalizedType(type.constData()); }
        void setParameterNames(const QList<QByteArray> &names) { owner->methods[number].parameter_names = names; }
        void setTag(const QByteArray &tag) { owner->methods[number].tag = tag; }
        void setMethodType(QMetaMethod::MethodType type) { auto &flags = owner->methods[number].flags; flags = (flags & ~12u) | (uint(type) << 2); }
        void setRevision(uint revision) { auto &method = owner->methods[number]; method.revision = revision; method.flags = revision ? method.flags | QtMocConstants::MethodRevisioned : method.flags & ~QtMocConstants::MethodRevisioned; }
    };
    class PropertyRef {
        BendMetaObjectBuilder *owner;
        size_t number;
        void flag(uint mask, bool value) { auto &flags = owner->properties[number].flags; flags = value ? flags | mask : flags & ~mask; }
    public:
        PropertyRef(BendMetaObjectBuilder *value, size_t index) : owner(value), number(index) {}
        int index() const { return int(number); }
        void setReadable(bool value) { flag(QtMocConstants::Readable, value); }
        void setWritable(bool value) { flag(QtMocConstants::Writable, value); }
        void setConstant(bool value) { flag(QtMocConstants::Constant, value); }
        void setResettable(bool value) { flag(QtMocConstants::Resettable, value); }
        void setStored(bool value) { flag(QtMocConstants::Stored, value); }
        void setScriptable(bool value) { flag(QtMocConstants::Scriptable, value); }
        void setDesignable(bool value) { flag(QtMocConstants::Designable, value); }
        void setUser(bool value) { flag(QtMocConstants::User, value); }
        void setFinal(bool value) { flag(QtMocConstants::Final, value); }
        void setVirtual(bool value) {
#if QT_VERSION >= QT_VERSION_CHECK(6, 11, 0)
            flag(QtMocConstants::Virtual, value);
#else
            if (value) throw std::invalid_argument("Virtual property metadata requires Qt 6.11");
#endif
        }
        void setOverride(bool value) {
#if QT_VERSION >= QT_VERSION_CHECK(6, 11, 0)
            flag(QtMocConstants::Override, value);
#else
            if (value) throw std::invalid_argument("Override property metadata requires Qt 6.11");
#endif
        }
        void setRequired(bool value) { flag(QtMocConstants::Required, value); }
        void setBindable(bool value) { flag(QtMocConstants::Bindable, value); }
        void setRevision(uint revision) { owner->properties[number].revision = revision; }
        void setInheritedNotify(const QByteArray &name) { owner->properties[number].inherited_notify = name; }
    };
    void setClassName(const QByteArray &name) { class_name = name; }
    void setSuperClass(const QMetaObject *meta) { super = meta; }
    void setMetaType(QMetaType type) { self_type = type.iface(); }
    void setFlags(uint flags) { meta_flags = flags; }
    void addClassInfo(const QByteArray &key, const QByteArray &value) { class_info.emplace_back(key, value); }
    void addEnumerator(const QByteArray &name, const QByteArray &alias, QMetaType type, uint flags,
                       const std::vector<std::pair<QByteArray, uint64_t>> &entries) {
        enumerations.push_back(Enumeration{name, alias, type, flags, entries});
    }
    int indexOfMethod(const QByteArray &signature) const {
        auto normalized = QMetaObject::normalizedSignature(signature.constData());
        for (size_t i = 0; i < methods.size(); ++i) if (methods[i].signature == normalized) return int(i);
        return -1;
    }
    MethodRef add(const QByteArray &signature, bool signal) {
        auto normalized = QMetaObject::normalizedSignature(signature.constData());
        if (signal && signals_count != methods.size()) throw std::logic_error("Signals must precede slots in Qt metadata");
        Method method;
        method.signature = normalized; method.name = normalized.left(normalized.indexOf('('));
        method.arguments = parameters(normalized);
        method.flags = QtMocConstants::AccessPublic | (signal ? QtMocConstants::MethodSignal : QtMocConstants::MethodSlot);
        methods.push_back(std::move(method));
        if (signal) ++signals_count;
        return MethodRef(this, methods.size() - 1);
    }
    MethodRef addSignal(const QByteArray &signature) { return add(signature, true); }
    MethodRef method(int index) { return MethodRef(this, size_t(index)); }
    MethodRef addSlot(const QByteArray &signature) { return add(signature, false); }
    PropertyRef addProperty(const QByteArray &name, const QByteArray &type, QMetaType meta, int notify) {
        properties.push_back(Property{name, QMetaObject::normalizedType(type.constData()), meta,
            QtMocConstants::Readable | QtMocConstants::Writable | QtMocConstants::Designable | QtMocConstants::Scriptable | QtMocConstants::Stored |
                (meta.flags().testFlag(QMetaType::IsEnumeration) ? QtMocConstants::EnumOrFlag : 0u), notify});
        return PropertyRef(this, properties.size() - 1);
    }
    QMetaObject *toMetaObject() const {
        static_assert(QtMocConstants::OutputRevision == 13, "Review the metadata writer when upgrading the generator's Qt headers");
        std::vector<QByteArray> strings;
        std::map<QByteArray, uint> indices;
        auto intern = [&](const QByteArray &text) -> uint {
            auto found = indices.find(text);
            if (found != indices.end()) return found->second;
            if (strings.size() >= 0x7fffffffu) throw std::length_error("Qt metadata string index range exhausted");
            uint index = uint(strings.size());
            strings.push_back(text); indices.emplace(text, index);
            return index;
        };
        intern(class_name);
        uint empty = intern(QByteArray());
        auto type_id = [&](const QByteArray &name) -> uint {
            auto meta = QMetaType::fromName(name);
            if (meta.isValid() && meta.id() < QMetaType::User) return uint(meta.id());
            return QtMocConstants::IsUnresolvedType | intern(name);
        };
        std::vector<uint> data(14 + methods.size() * 6);
        std::vector<const QtPrivate::QMetaTypeInterface *> types;
        for (const auto &property : properties) types.push_back(property.type.iface());
        for (const auto &enumeration : enumerations) types.push_back(enumeration.type.iface());
        types.push_back(self_type); // The optional metatype of the class itself.
        for (size_t i = 0; i < methods.size(); ++i) {
            const auto &method = methods[i];
            size_t at = 14 + i * 6;
            data[at] = intern(method.name); data[at + 1] = uint(method.arguments.size());
            data[at + 3] = intern(method.tag);
            data[at + 4] = method.flags; data[at + 5] = uint(types.size());
            if (method.flags & QtMocConstants::MethodRevisioned) data.push_back(method.revision);
            data[at + 2] = uint(data.size());
            data.push_back(type_id(method.result));
            types.push_back(QMetaType::fromName(method.result).iface());
            for (const auto &argument : method.arguments) {
                data.push_back(type_id(argument)); types.push_back(QMetaType::fromName(argument).iface());
            }
            for (qsizetype argument = 0; argument < method.arguments.size(); ++argument)
                data.push_back(argument < method.parameter_names.size() ? intern(method.parameter_names[argument]) : empty);
        }
        uint property_offset = uint(data.size());
        for (const auto &property : properties) {
            data.push_back(intern(property.name)); data.push_back(type_id(property.type_name));
            data.push_back(property.flags);
            data.push_back(property.inherited_notify.isEmpty() ? uint(property.notify) : QtMocConstants::IsUnresolvedSignal | intern(property.inherited_notify));
            data.push_back(property.revision);
        }
        uint class_info_offset = uint(data.size());
        for (const auto &[key, value] : class_info) { data.push_back(intern(key)); data.push_back(intern(value)); }
        uint enum_offset = uint(data.size());
        data.resize(data.size() + enumerations.size() * 5);
        for (size_t i = 0; i < enumerations.size(); ++i) {
            const auto &enumeration = enumerations[i];
            const size_t at = enum_offset + i * 5;
            data[at] = intern(enumeration.name); data[at + 1] = intern(enumeration.alias);
            data[at + 2] = enumeration.flags; data[at + 3] = uint(enumeration.entries.size());
            data[at + 4] = uint(data.size());
            for (const auto &[key, bits] : enumeration.entries) { data.push_back(intern(key)); data.push_back(uint(bits)); }
            if (enumeration.flags & QtMocConstants::EnumIs64Bit)
                for (const auto &[key, bits] : enumeration.entries) data.push_back(uint(bits >> 32));
        }
        uint end = uint(data.size());
        data[0] = 13; data[1] = 0; data[2] = uint(class_info.size()); data[3] = class_info_offset;
        data[4] = uint(methods.size()); data[5] = 14;
        data[6] = uint(properties.size()); data[7] = property_offset;
        data[8] = uint(enumerations.size()); data[9] = enum_offset; data[10] = 0; data[11] = end;
        data[12] = QtMocConstants::AllocatedMetaObject | meta_flags; data[13] = signals_count;
        data.push_back(0);
        auto aligned = [](size_t value, size_t alignment) { return (value + alignment - 1) & ~(alignment - 1); };
        size_t data_at = sizeof(QMetaObject);
        size_t string_at = data_at + data.size() * sizeof(uint);
        size_t string_size = strings.size() * 2 * sizeof(uint);
        for (const auto &text : strings) string_size += size_t(text.size()) + 1;
        if (string_size > UINT_MAX) throw std::length_error("Qt metadata strings exceed the native offset range");
        size_t type_at = aligned(string_at + string_size, alignof(const QtPrivate::QMetaTypeInterface *));
        auto *allocation = static_cast<unsigned char *>(std::calloc(1, type_at + types.size() * sizeof(types[0])));
        if (!allocation) throw std::bad_alloc();
        auto *meta = new(allocation) QMetaObject{};
        auto *words = reinterpret_cast<uint *>(allocation + data_at);
        auto *table = reinterpret_cast<uint *>(allocation + string_at);
        auto *interfaces = reinterpret_cast<const QtPrivate::QMetaTypeInterface **>(allocation + type_at);
        std::memcpy(words, data.data(), data.size() * sizeof(uint));
        std::memcpy(interfaces, types.data(), types.size() * sizeof(types[0]));
        size_t offset = strings.size() * 2 * sizeof(uint);
        for (size_t i = 0; i < strings.size(); ++i) {
            table[2 * i] = uint(offset); table[2 * i + 1] = uint(strings[i].size());
            std::memcpy(allocation + string_at + offset, strings[i].constData(), size_t(strings[i].size()));
            offset += size_t(strings[i].size()) + 1;
        }
        meta->d.superdata = super; meta->d.data = words;
        meta->d.stringdata = table; meta->d.metaTypes = interfaces;
        return meta;
    }
};
