// Owning, reflected Qt values for schemas declared by Bend. This core has no
// Bend handles or callbacks: copying a QVariant copies the complete value.
namespace BendValueTypes {
struct Type;
struct Value {
    const Type *type;
    QList<QVariant> fields;
};
struct Sequence {
    const Type *type;
    QList<QVariant> values;
};
struct Field {
    QByteArray name;
    QMetaType type;
    bool writable = true, constant = false, resettable = false;
    bool stored = true, designable = true, scriptable = true, user = false;
};
struct Interface : QtPrivate::QMetaTypeInterface { Type *owner; };
struct Type {
    QByteArray name, list_name;
    std::vector<Field> fields;
    Interface interface{};
    Interface list_interface{};
    QtMetaContainerPrivate::QMetaSequenceInterface sequence{};
    QMetaObject *meta = nullptr;
    QMetaType type() const { return QMetaType(&interface); }
    QMetaType list_type() const { return QMetaType(&list_interface); }
    QVariant create() const { return QVariant(type()); }
};
static void initialize_sequence(Type *);
static std::map<QByteArray, std::unique_ptr<Type>> &registry() {
    // Qt metatype registrations and queued QVariant values outlive applications.
    // Their interfaces and metaobjects therefore have process lifetime.
    static auto *types = new std::map<QByteArray, std::unique_ptr<Type>>;
    return *types;
}
static const Type *owner(const QtPrivate::QMetaTypeInterface *interface) {
    return static_cast<const Interface *>(interface)->owner;
}
static std::pair<const Type *, bool> classify(QMetaType meta) {
    if (!meta.isValid() || !meta.name()) return {};
    QByteArray name(meta.name());
    const bool sequence = name.startsWith("QList<") && name.endsWith('>');
    if (sequence) name = name.mid(6, name.size() - 7);
    auto found = registry().find(name);
    if (found == registry().end()) return {};
    const auto *type = found->second.get();
    if (meta.iface() != (sequence ? &type->list_interface : &type->interface)) return {};
    return {type, sequence};
}
static QVariant default_field(const Field &field) {
    return field.type.id() == QMetaType::QVariant ? QVariant{} : QVariant(field.type);
}
static Value defaults(const Type *type) {
    Value value{type, {}};
    for (const auto &field : type->fields) value.fields.append(default_field(field));
    return value;
}
static const void *field_data(const Field &field, const QVariant &value) {
    return field.type.id() == QMetaType::QVariant ? &value : value.constData();
}
static void assign_field(const Field &field, void *target, const QVariant &value) {
    // QMetaProperty read destinations already contain a default-constructed
    // object. Reconstruct it with the runtime type's actual copy constructor.
    field.type.destruct(target);
    field.type.construct(target, field_data(field, value));
}
static void metacall(QObject *object, QMetaObject::Call call, int index, void **arguments) {
    auto *value = reinterpret_cast<Value *>(object);
    if (index < 0 || size_t(index) >= value->type->fields.size()) return;
    const auto &field = value->type->fields[size_t(index)];
    if (call == QMetaObject::ReadProperty) {
        assign_field(field, arguments[0], value->fields.at(index));
    } else if (call == QMetaObject::WriteProperty) {
        if (!field.writable || field.constant) return;
        value->fields[index] = field.type.id() == QMetaType::QVariant
            ? *static_cast<const QVariant *>(arguments[0]) : QVariant(field.type, arguments[0]);
    } else if (call == QMetaObject::ResetProperty && field.resettable) {
        value->fields[index] = default_field(field);
    }
}
static bool same(const Field &left, const Field &right) {
    return left.name == right.name && left.type == right.type && left.writable == right.writable
        && left.constant == right.constant && left.resettable == right.resettable && left.stored == right.stored
        && left.designable == right.designable && left.scriptable == right.scriptable && left.user == right.user;
}
static Type *define(const QByteArray &name, const std::vector<Field> &fields) {
    if (name.isEmpty() || name.contains('\0')) throw std::invalid_argument("A value type needs a nonempty native name");
    auto &types = registry();
    if (auto found = types.find(name); found != types.end()) {
        if (fields.size() != found->second->fields.size()
            || !std::equal(fields.begin(), fields.end(), found->second->fields.begin(), same))
            throw std::invalid_argument("A different value type already has this name");
        return found->second.get();
    }
    if (QMetaType::fromName(name).isValid()) throw std::invalid_argument("A native metatype already has this name");
    if (QMetaType::fromName("QList<" + name + '>' ).isValid())
        throw std::invalid_argument("A native sequence metatype already has this name");
    std::set<QByteArray> names;
    for (const auto &field : fields) {
        if (field.name.isEmpty() || field.name.contains('\0') || !names.insert(field.name).second)
            throw std::invalid_argument("Value field names must be nonempty and unique");
        if (!field.type.isValid() || field.type.id() == QMetaType::Void
            || !field.type.isDefaultConstructible() || !field.type.isCopyConstructible())
            throw std::invalid_argument("A value field needs a default-constructible, copyable Qt type");
    }
    auto result = std::make_unique<Type>();
    auto *type = result.get(); type->name = name; type->fields = fields;
    auto &interface = type->interface;
    interface.owner = type;
    interface.revision = QtPrivate::QMetaTypeInterface::CurrentRevision;
    interface.alignment = alignof(Value); interface.size = sizeof(Value);
    interface.flags = QMetaType::IsGadget | QMetaType::NeedsConstruction | QMetaType::NeedsDestruction
        | QMetaType::NeedsCopyConstruction | QMetaType::NeedsMoveConstruction;
    interface.name = type->name.constData();
    interface.metaObjectFn = [](const auto *i) -> const QMetaObject * { return owner(i)->meta; };
    interface.defaultCtr = [](const auto *i, void *p) { new(p) Value(defaults(owner(i))); };
    interface.copyCtr = [](const auto *, void *p, const void *source) { new(p) Value(*static_cast<const Value *>(source)); };
    interface.moveCtr = [](const auto *, void *p, void *source) { new(p) Value(std::move(*static_cast<Value *>(source))); };
    interface.dtor = [](const auto *, void *p) { static_cast<Value *>(p)->~Value(); };
    interface.equals = [](const auto *, const void *a, const void *b) {
        const auto &left = *static_cast<const Value *>(a), &right = *static_cast<const Value *>(b);
        return left.type == right.type && left.fields == right.fields;
    };
    interface.debugStream = [](const auto *i, QDebug &debug, const void *p) {
        debug.nospace() << owner(i)->name << static_cast<const Value *>(p)->fields;
    };
    interface.dataStreamOut = [](const auto *, QDataStream &stream, const void *p) {
        const auto *value = static_cast<const Value *>(p);
        for (const auto &field : value->fields) stream << field;
    };
    interface.dataStreamIn = [](const auto *i, QDataStream &stream, void *p) {
        auto *type = owner(i); auto candidate = defaults(type);
        for (size_t index = 0; index < type->fields.size(); ++index) {
            QVariant value; stream >> value;
            const auto wanted = type->fields[index].type;
            if (stream.status() != QDataStream::Ok) return;
            if (wanted.id() != QMetaType::QVariant && value.metaType() != wanted) {
                stream.setStatus(QDataStream::ReadCorruptData); return;
            }
            candidate.fields[qsizetype(index)] = std::move(value);
        }
        *static_cast<Value *>(p) = std::move(candidate);
    };
    BendMetaObjectBuilder builder;
    builder.setClassName(name); builder.setSuperClass(nullptr); builder.setMetaType(type->type());
    builder.setFlags(QtMocConstants::PropertyAccessInStaticMetaCall);
    for (const auto &field : fields) {
        auto property = builder.addProperty(field.name, field.type.name(), field.type, -1);
        property.setWritable(field.writable && !field.constant); property.setConstant(field.constant);
        property.setResettable(field.resettable); property.setStored(field.stored);
        property.setDesignable(field.designable); property.setScriptable(field.scriptable); property.setUser(field.user);
    }
    type->meta = builder.toMetaObject(); type->meta->d.static_metacall = metacall;
    // Register only after the complete metadata and storage are stable. Qt may
    // immediately use the metatype's default constructor and metaObjectFn.
    initialize_sequence(type);
    types.emplace(name, std::move(result));
    type->type().registerType(); type->list_type().registerType();
    return type;
}
static QVariant read(const QVariant &value, const QByteArray &field) {
    if (!value.metaType().flags().testFlag(QMetaType::IsGadget))
        throw std::invalid_argument("Expected an owning Qt gadget value");
    const auto *meta = value.metaType().metaObject();
    int index = meta ? meta->indexOfProperty(field.constData()) : -1;
    if (index < 0) throw std::invalid_argument("Unknown value field");
    return meta->property(index).readOnGadget(value.constData());
}
static bool write(QVariant &value, const QByteArray &field, const QVariant &data) {
    if (!value.metaType().flags().testFlag(QMetaType::IsGadget))
        throw std::invalid_argument("Expected an owning Qt gadget value");
    const auto *meta = value.metaType().metaObject();
    int index = meta ? meta->indexOfProperty(field.constData()) : -1;
    if (index < 0) throw std::invalid_argument("Unknown value field");
    return meta->property(index).writeOnGadget(value.data(), data);
}
struct SequenceIterator { const Sequence *container; qsizetype index; };
static void sequence_read(const Sequence *sequence, qsizetype index, void *target) {
    if (index < 0 || index >= sequence->values.size()) return;
    auto type = sequence->type->type();
    type.destruct(target); type.construct(target, sequence->values.at(index).constData());
}
static void sequence_write(Sequence *sequence, qsizetype index, const void *source) {
    if (index < 0 || index >= sequence->values.size()) return;
    sequence->values[index] = QVariant(sequence->type->type(), source);
}
static void initialize_sequence(Type *type) {
    type->list_name = "QList<" + type->name + '>';
    auto &interface = type->list_interface;
    interface.owner = type;
    interface.revision = QtPrivate::QMetaTypeInterface::CurrentRevision;
    interface.alignment = alignof(Sequence); interface.size = sizeof(Sequence);
    interface.flags = QMetaType::NeedsConstruction | QMetaType::NeedsDestruction
        | QMetaType::NeedsCopyConstruction | QMetaType::NeedsMoveConstruction;
    interface.name = type->list_name.constData();
    interface.defaultCtr = [](const auto *i, void *p) { new(p) Sequence{owner(i), {}}; };
    interface.copyCtr = [](const auto *, void *p, const void *source) { new(p) Sequence(*static_cast<const Sequence *>(source)); };
    interface.moveCtr = [](const auto *, void *p, void *source) { new(p) Sequence(std::move(*static_cast<Sequence *>(source))); };
    interface.dtor = [](const auto *, void *p) { static_cast<Sequence *>(p)->~Sequence(); };
    interface.equals = [](const auto *, const void *a, const void *b) {
        const auto &left = *static_cast<const Sequence *>(a), &right = *static_cast<const Sequence *>(b);
        return left.type == right.type && left.values == right.values;
    };
    interface.dataStreamOut = [](const auto *, QDataStream &stream, const void *p) {
        stream << static_cast<const Sequence *>(p)->values;
    };
    interface.dataStreamIn = [](const auto *i, QDataStream &stream, void *p) {
        QList<QVariant> values; stream >> values;
        if (stream.status() != QDataStream::Ok) return;
        for (const auto &value : values) if (value.metaType() != owner(i)->type()) {
            stream.setStatus(QDataStream::ReadCorruptData); return;
        }
        static_cast<Sequence *>(p)->values = std::move(values);
    };
    using Container = QtMetaContainerPrivate::QMetaContainerInterface;
    auto &sequence = type->sequence;
    sequence.iteratorCapabilities = QtMetaContainerPrivate::InputCapability | QtMetaContainerPrivate::ForwardCapability
        | QtMetaContainerPrivate::BiDirectionalCapability | QtMetaContainerPrivate::RandomAccessCapability;
    sequence.sizeFn = [](const void *p) { return static_cast<const Sequence *>(p)->values.size(); };
    sequence.clearFn = [](void *p) { static_cast<Sequence *>(p)->values.clear(); };
    sequence.createIteratorFn = [](void *p, Container::Position position) -> void * {
        auto *container = static_cast<Sequence *>(p);
        return new SequenceIterator{container, position == Container::AtEnd ? container->values.size() : 0};
    };
    sequence.createConstIteratorFn = [](const void *p, Container::Position position) -> void * {
        auto *container = static_cast<const Sequence *>(p);
        return new SequenceIterator{container, position == Container::AtEnd ? container->values.size() : 0};
    };
    sequence.destroyIteratorFn = sequence.destroyConstIteratorFn = [](const void *p) { delete static_cast<const SequenceIterator *>(p); };
    sequence.compareIteratorFn = sequence.compareConstIteratorFn = [](const void *a, const void *b) {
        const auto &left = *static_cast<const SequenceIterator *>(a), &right = *static_cast<const SequenceIterator *>(b);
        return left.container == right.container && left.index == right.index;
    };
    sequence.copyIteratorFn = sequence.copyConstIteratorFn = [](void *a, const void *b) {
        *static_cast<SequenceIterator *>(a) = *static_cast<const SequenceIterator *>(b);
    };
    sequence.advanceIteratorFn = sequence.advanceConstIteratorFn = [](void *p, qsizetype amount) { static_cast<SequenceIterator *>(p)->index += amount; };
    sequence.diffIteratorFn = sequence.diffConstIteratorFn = [](const void *a, const void *b) {
        return static_cast<const SequenceIterator *>(a)->index - static_cast<const SequenceIterator *>(b)->index;
    };
    sequence.valueMetaType = &type->interface;
    sequence.addRemoveCapabilities = QtMetaContainerPrivate::CanAddAtBegin | QtMetaContainerPrivate::CanAddAtEnd
        | QtMetaContainerPrivate::CanRemoveAtBegin | QtMetaContainerPrivate::CanRemoveAtEnd;
    sequence.valueAtIndexFn = [](const void *p, qsizetype index, void *target) { sequence_read(static_cast<const Sequence *>(p), index, target); };
    sequence.setValueAtIndexFn = [](void *p, qsizetype index, const void *source) { sequence_write(static_cast<Sequence *>(p), index, source); };
    sequence.addValueFn = [](void *p, const void *source, Container::Position position) {
        auto *container = static_cast<Sequence *>(p); QVariant value(container->type->type(), source);
        if (position == Container::AtBegin) container->values.prepend(value); else container->values.append(value);
    };
    sequence.removeValueFn = [](void *p, Container::Position position) {
        auto &values = static_cast<Sequence *>(p)->values;
        if (!values.isEmpty()) { if (position == Container::AtBegin) values.removeFirst(); else values.removeLast(); }
    };
    sequence.valueAtIteratorFn = sequence.valueAtConstIteratorFn = [](const void *p, void *target) {
        const auto *iterator = static_cast<const SequenceIterator *>(p); sequence_read(iterator->container, iterator->index, target);
    };
    sequence.setValueAtIteratorFn = [](const void *p, const void *source) {
        const auto *iterator = static_cast<const SequenceIterator *>(p);
        sequence_write(const_cast<Sequence *>(iterator->container), iterator->index, source);
    };
    sequence.insertValueAtIteratorFn = [](void *p, const void *at, const void *source) {
        auto *container = static_cast<Sequence *>(p);
        container->values.insert(static_cast<const SequenceIterator *>(at)->index, QVariant(container->type->type(), source));
    };
    sequence.eraseValueAtIteratorFn = [](void *p, const void *at) {
        static_cast<Sequence *>(p)->values.removeAt(static_cast<const SequenceIterator *>(at)->index);
    };
    sequence.eraseRangeAtIteratorFn = [](void *p, const void *begin, const void *end) {
        const auto first = static_cast<const SequenceIterator *>(begin)->index;
        static_cast<Sequence *>(p)->values.remove(first, static_cast<const SequenceIterator *>(end)->index - first);
    };
}
} // namespace BendValueTypes
