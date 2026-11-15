namespace BendSignalApi {
extern __attribute__((visibility("hidden"))) QMetaType meta_type(int);
extern __attribute__((visibility("hidden"))) int argument_type(BqtRequest *, const BqtValue &);
extern __attribute__((visibility("hidden"))) QVariant read_value(BqtRequest *, int, const BqtValue &);
extern __attribute__((visibility("hidden"))) BqtValue write_value(BqtRequest *, int, const void *);
}
namespace BendQmlLists {
struct Type;
struct Context;
static constexpr uintptr_t context_magic = uintptr_t(0x4251) << 48;
static constexpr uintptr_t context_mask = uintptr_t(0xffff) << 48;
static constexpr uint32_t disabled_mask = 0x3f0000u;
static constexpr uint32_t owner_slot = 0xffffff91u, member_slot = 0xffffff90u;
struct Observation {
    uintptr_t token;
    uint32_t owner;
    QObject *identity;
    QPointer<QObject> object;
    Type *type;
    std::shared_ptr<std::atomic<bool>> alive = std::make_shared<std::atomic<bool>>(true);
};
struct ContextSlot { uint32_t generation = 1; std::weak_ptr<Observation> observation; };
static auto *context_slots = new std::vector<ContextSlot>(1);
static auto *free_contexts = new std::vector<uint32_t>;
static auto *context_mutex = new std::mutex;
static std::shared_ptr<Observation> observe_context(uint32_t owner, QObject *object, Type *type) {
    std::lock_guard<std::mutex> lock(*context_mutex);
    uint32_t index;
    if (free_contexts->empty()) {
        if (context_slots->size() >= (1u << 24)) throw std::length_error("QML list context identity range exhausted");
        index = uint32_t(context_slots->size()); context_slots->emplace_back();
    } else { index = free_contexts->back(); free_contexts->pop_back(); }
    auto &slot = (*context_slots)[index];
    auto result = std::make_shared<Observation>();
    result->token = context_magic | uintptr_t(slot.generation) << 24 | index;
    result->owner = owner; result->identity = object; result->object = object; result->type = type;
    slot.observation = result;
    return result;
}
static std::shared_ptr<Observation> observation(uintptr_t token) {
    if ((token & context_mask) != context_magic) return {};
    std::lock_guard<std::mutex> lock(*context_mutex);
    const uint32_t index = uint32_t(token & 0xffffffu), generation = uint32_t((token >> 24) & 0xffffffu);
    if (index >= context_slots->size()) return {};
    auto &slot = (*context_slots)[index];
    return slot.generation == generation ? slot.observation.lock() : std::shared_ptr<Observation>{};
}
static void forget_context(const std::shared_ptr<Observation> &value) {
    value->alive->store(false, std::memory_order_release);
    std::lock_guard<std::mutex> lock(*context_mutex);
    const auto index = uint32_t(value->token & 0xffffffu);
    auto &slot = (*context_slots)[index];
    slot.observation.reset();
    if (slot.generation != 0xffffffu) { ++slot.generation; free_contexts->push_back(index); }
}
struct Capture {
    std::shared_ptr<Observation> observed;
    QPointer<QObject> object;
    QObject *identity = nullptr;
};
struct Header { QObject *object; void *data; };
static Header header(const void *data) { Header value{}; if (data) std::memcpy(&value, data, sizeof(value)); return value; }
static std::optional<Capture> capture(const QVariant &value) {
    if (!value.metaType().flags().testFlag(QMetaType::IsQmlList)) return {};
    const auto view = header(value.constData());
    Capture result; result.identity = view.object;
    const auto token = reinterpret_cast<uintptr_t>(view.data);
    if ((token & context_mask) == context_magic) {
        result.observed = observation(token);
        if (!result.observed || !result.observed->alive->load(std::memory_order_acquire)
                || result.observed->identity != view.object)
            throw std::system_error(ESTALE, std::generic_category(), "A QML list view context expired");
    }
    // Native foreign list values retain Qt's normal owner-lifetime contract at
    // the native call boundary. Authored views are checked before this access.
    result.object = result.observed ? result.observed->object : QPointer<QObject>(view.object);
    if (!result.observed && view.object && view.object->thread() != main_thread)
        throw std::system_error(EXDEV, std::generic_category(), "A QML list owner belongs to another thread");
    return result;
}
static bool live(const Capture &value) {
    return (!value.identity || (value.object && value.object.data() == value.identity))
        && (!value.observed || value.observed->alive->load(std::memory_order_acquire));
}
static bool pin(BqtRequest *r, const Capture &value) {
    if (!live(value)) { fail(r, ESTALE, "A QML list owner expired"); return false; }
    const uint32_t id = value.observed ? value.observed->owner
        : value.identity ? borrow(r, value.identity, @QOBJECT_ID@) : 0;
    if (!r->error && id) get<QObject>(r, id, @QOBJECT_ID@, false, false);
    return !r->error;
}
static uint32_t owner(BqtRequest *r, const Capture &value) {
    if (!pin(r, value)) return 0;
    return value.observed ? value.observed->owner : value.identity ? borrow(r, value.identity, @QOBJECT_ID@) : 0;
}
static QVariant dispatch(uintptr_t, unsigned, qsizetype, QObject *, bool = false);
struct Type {
    int code = 0, element = 0;
    QMetaType native, element_meta;
    bool registered = false;
    QVariant (*view)(Type *, QObject *, uintptr_t, uint32_t) = nullptr;
    QObject *(*object)(const QVariant &) = nullptr;
    QVariant (*value)(Type *, QObject *) = nullptr;
    bool (*assign)(void *, const void *) = nullptr;
    std::shared_ptr<BendPropertyBindings::Storage> (*binding)(QMetaType, BendPropertyBindings::Read, BendPropertyBindings::Write) = nullptr;
};
static auto *types = new std::vector<Type *>;
static auto *types_by_element = new std::map<int, Type *>;
static bool is_code(int code) { return code > INT_MIN && code < INT_MIN / 2; }
static Type *type_from_code(int code) {
    const int64_t index = int64_t(code) - INT_MIN - 1;
    return index >= 0 && uint64_t(index) < types->size() ? (*types)[size_t(index)] : nullptr;
}
static bool register_list(Type *type) {
    if (type->registered) return true;
    const auto *meta = type->element_meta.metaObject();
    if (!meta) return false; // Forward class metadata can be published later.
    QQmlPrivate::RegisterType api{};
    api.structVersion = QQmlPrivate::RegisterType::CurrentVersion;
    api.typeId = type->element_meta; api.listId = type->native;
    api.uri = "BendQt.InternalLists"; api.elementName = nullptr;
    api.version = QTypeRevision::fromMajorVersion(1);
    api.metaObject = meta;
    if (QQmlPrivate::qmlregister(QQmlPrivate::TypeRegistration, &api) < 0) return false;
    type->registered = true;
    return true;
}
static void registrations_cleared() { for (auto *type : *types) type->registered = false; }
static void metadata_published(int element) {
    auto found = types_by_element->find(element);
    if (found != types_by_element->end()) register_list(found->second);
}
template<class T> struct Factory {
    using List = QQmlListProperty<T>;
    static QObject *object(const QVariant &value) { return *static_cast<T *const *>(value.constData()); }
    static QVariant value(Type *type, QObject *object) {
        T *pointer = object ? dynamic_cast<T *>(object) : nullptr;
        return QVariant(type->element_meta, &pointer);
    }
    static QVariant view(Type *type, QObject *owner, uintptr_t token, uint32_t disabled) {
        static_assert(std::is_standard_layout_v<List>);
        static_assert(offsetof(List, object) == 0 && offsetof(List, data) == sizeof(QObject *));
        auto append = +[](List *list, T *value) { dispatch(reinterpret_cast<uintptr_t>(list->data), 0, 0, value); };
        auto count = +[](List *list) -> qsizetype { return dispatch(reinterpret_cast<uintptr_t>(list->data), 1, 0, nullptr).toLongLong(); };
        auto at = +[](List *list, qsizetype index) -> T * {
            auto value = dispatch(reinterpret_cast<uintptr_t>(list->data), 2, index, nullptr);
            return value.isValid() ? *static_cast<T *const *>(value.constData()) : nullptr;
        };
        auto clear = +[](List *list) { dispatch(reinterpret_cast<uintptr_t>(list->data), 3, 0, nullptr); };
        auto replace = +[](List *list, qsizetype index, T *value) { dispatch(reinterpret_cast<uintptr_t>(list->data), 4, index, value); };
        auto remove = +[](List *list) { dispatch(reinterpret_cast<uintptr_t>(list->data), 5, 0, nullptr); };
        List list(owner, reinterpret_cast<void *>(token), disabled & 65536u ? nullptr : append,
            disabled & 131072u ? nullptr : count, disabled & 262144u ? nullptr : at,
            disabled & 524288u ? nullptr : clear, disabled & 1048576u ? nullptr : replace,
            disabled & 2097152u ? nullptr : remove);
        return QVariant(type->native, &list);
    }
    static bool assign(void *target, const void *source) {
        if (target) *static_cast<List *>(target) = *static_cast<const List *>(source);
        return true;
    }
    static Type *create(int element, QMetaType native) {
        auto value = std::make_unique<Type>();
        value->element = element; value->element_meta = BendSignalApi::meta_type(element); value->native = native;
        value->view = view; value->object = object; value->value = Factory::value; value->assign = assign;
        value->binding = BendPropertyBindings::make<List>;
        return value.release();
    }
};
template<class T> static Type *native_type(int element) {
    return Factory<T>::create(element, QMetaType::fromType<QQmlListProperty<T>>());
}
static Type *native_type_for(int);
static QMetaType dynamic_type(QMetaType element) {
    struct Interface {
        QtPrivate::QMetaTypeInterface interface{};
        QMetaType element;
        QByteArray name;
        explicit Interface(QMetaType value) : element(value) {
            name = "QQmlListProperty<" + QByteArray(element.name()).chopped(1) + '>';
            const auto *source = QMetaType::fromType<QQmlListProperty<QObject>>().iface();
            interface.revision = source->revision; interface.alignment = source->alignment; interface.size = source->size;
            interface.flags = source->flags | QMetaType::IsQmlList; interface.typeId.storeRelaxed(0);
            interface.name = name.constData();
            interface.metaObjectFn = [](const QtPrivate::QMetaTypeInterface *self) {
                return reinterpret_cast<const Interface *>(self)->element.metaObject();
            };
            interface.defaultCtr = source->defaultCtr; interface.copyCtr = source->copyCtr; interface.moveCtr = source->moveCtr;
            interface.dtor = source->dtor; interface.equals = source->equals; interface.lessThan = source->lessThan;
            interface.debugStream = source->debugStream; interface.dataStreamOut = source->dataStreamOut;
            interface.dataStreamIn = source->dataStreamIn; interface.legacyRegisterOp = nullptr;
        }
    };
    auto *value = new Interface(element);
    return QMetaType(&value->interface);
}
static Type *ensure_type(BqtRequest *r, int element) {
    auto found = types_by_element->find(element);
    if (found != types_by_element->end()) { register_list(found->second); return found->second; }
    auto meta = BendSignalApi::meta_type(element);
    if (!meta.isValid()) {
        fail(r, ENOTSUP, "The QML list element type is unavailable in this native payload"); return nullptr;
    }
    if (!meta.flags().testFlag(QMetaType::PointerToQObject)) {
        fail(r, EINVAL, "A QML list element descriptor must be a QObject type"); return nullptr;
    }
    std::unique_ptr<Type> value(native_type_for(element));
    if (!value) value.reset(Factory<QObject>::create(element, dynamic_type(meta)));
    if (types->size() >= size_t(INT_MAX / 2 - 1)) { fail(r, E2BIG, "QML list type index range exhausted"); return nullptr; }
    value->code = INT_MIN + 1 + int(types->size());
    value->native.registerType();
    auto *result = value.get();
    types_by_element->emplace(element, result);
    try { types->push_back(result); } catch (...) { types_by_element->erase(element); throw; }
    value.release(); register_list(result);
    return result;
}
static int argument_type(BqtRequest *r, const QByteArray &name, const BqtValue *dependency) {
    if (!dependency || dependency->tag != 2 || dependency->count != 2
            || dependency->items[0].tag != 1
            || QByteArray(dependency->items[0].text, qsizetype(dependency->items[0].size)) != "qml_list") return INT_MIN;
    const int element = BendSignalApi::argument_type(r, dependency->items[1]);
    auto *type = r->error ? nullptr : ensure_type(r, element);
    if (!type) return INT_MIN;
    if (name != type->native.name()) { fail(r, EINVAL, "A QML list descriptor has an incompatible native name"); return INT_MIN; }
    return type->code;
}
static QVariant read_value(BqtRequest *r, int code, const BqtValue &wire) {
    auto *type = type_from_code(code);
    if (!type || wire.tag || wire.high) { fail(r, EINVAL, "Invalid QML list view payload"); return {}; }
    auto *value = get<QVariant>(r, wire.word, @VARIANT_ID@, false, false);
    if (r->error) return {};
    if (value->metaType() != type->native) { fail(r, EINVAL, "QML list view has a different element type"); return {}; }
    if (auto held = capture(*value); held && !pin(r, *held)) return {};
    return *value;
}
static BqtValue write_value(BqtRequest *r, int code, const void *data) {
    auto *type = type_from_code(code);
    if (!type) { fail(r, EINVAL, "Unknown QML list argument type"); return {}; }
    QVariant value(type->native, data);
    auto held = capture(value);
    if (held && !pin(r, *held)) return {};
    BqtValue result{};
    result.word = own(r, new QVariant(value), @VARIANT_ID@); result.owned_handle = result.word;
    if (!r->error && !generic_variant_finish(r, result, native_call_scope ? native_call_scope->value_origin : 0)) return result;
    if (!r->error) generic_variant_refresh(r, result.word);
    return result;
}
static bool attach(BqtRequest *, const std::shared_ptr<RuntimeObjectState> &, size_t);
static bool operation(BqtRequest *);
static bool install(BqtRequest *);
static bool reference(BqtRequest *r) {
    NativeCallScope scope;
    auto *value = get<QVariant>(r, r->arguments[0].word, @VARIANT_ID@, false, false);
    if (r->error) return true;
    auto held = capture(*value);
    if (!held) return fail(r, EINVAL, "QmlListView does not contain a native QML list");
    if (!pin(r, *held)) return true;
    r->result.word = own(r, new QQmlListReference(*value), @LIST_REFERENCE_ID@);
    r->result.owned_handle = r->result.word;
    return true;
}
} // namespace BendQmlLists
@NATIVE_FACTORY_DECLARATIONS@
namespace BendQmlLists {
static Type *native_type_for(int element) { switch (element) { @NATIVE_FACTORY_CASES@ } return nullptr; }
}
