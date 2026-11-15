constexpr uint32_t generic_argument_slot = 0xffffffd9u;
struct GenericArgumentOrigin {
    std::shared_ptr<QByteArray> name;
    uint32_t storage = 0;
    bool writable = false;
};
static SlotTable<GenericArgumentOrigin *> generic_argument_origins;
static QMetaType generic_argument_type(QByteArray name) {
    auto type = QMetaType::fromName(name);
    if (type.isValid()) return type;
    name = name.trimmed();
    if (name.endsWith('&')) name.chop(1);
    if (name.startsWith("const ")) name.remove(0, 6);
    return QMetaType::fromName(name.trimmed());
}
static void generic_argument_forget(uint32_t id) {
    auto *value = generic_argument_origins[id & 65535u];
    generic_argument_origins[id & 65535u] = nullptr;
    delete value;
}
static QGenericArgument *generic_argument_value(Entry *e) {
    if (!e) return nullptr;
    if (e->type == @QGenericArgument@) return static_cast<QGenericArgument *>(e->value);
    if (e->type == @QGenericReturnArgument@) return static_cast<QGenericReturnArgument *>(e->value);
    return nullptr;
}
static bool validate_generic_argument(BqtRequest *r, uint32_t id) {
    auto *value = generic_argument_value(entry(id));
    auto *origin = value ? generic_argument_origins[id & 65535u] : nullptr;
    if (!value || !origin) { fail(r, ESTALE, "Generic argument origin expired"); return false; }
    const char *name = origin->name ? origin->name->constData() : nullptr;
    if (value->name() != name) { fail(r, ESTALE, "Generic argument type name changed"); return false; }
    if (!origin->storage) {
        if (value->data()) { fail(r, ESTALE, "Generic argument has untracked native data"); return false; }
        return true;
    }
    auto *storage = get<MetaStorage>(r, origin->storage, @MetaStorage@, false, false);
    if (!storage) return false;
    if (!storage->initialized || storage->data != value->data() || !name || generic_argument_type(*origin->name) != storage->type) {
        fail(r, ESTALE, "Generic argument storage was destroyed or changed type"); return false;
    }
    return true;
}
static bool install_generic_argument_origin(BqtRequest *r, uint32_t id, std::unique_ptr<GenericArgumentOrigin> origin) {
    BqtRequest claim{}; claim.self = id;
    int edge = prepare_retention(&claim, generic_argument_slot, 0, origin->storage);
    if (claim.error) { fail(r, claim.error, claim.message); return false; }
    commit_retention(edge, id, generic_argument_slot, 0, origin->storage, nullptr);
    generic_argument_forget(id);
    generic_argument_origins[id & 65535u] = origin.release();
    entry(id)->validate = validate_generic_argument;
    return true;
}
template <typename T> static uint32_t new_generic_argument(BqtRequest *r, uint16_t type,
        const QString &name, bool named, uint32_t storage_id) {
    auto *storage = get<MetaStorage>(r, storage_id, @MetaStorage@, true, false);
    if (r->error) return 0;
    auto origin = std::make_unique<GenericArgumentOrigin>();
    origin->writable = std::is_same_v<T, QGenericReturnArgument>;
    if (named) {
        origin->name = std::make_shared<QByteArray>(name.toUtf8());
        if (origin->name->contains('\0')) { fail(r, EINVAL, "Generic argument type name contains NUL"); return 0; }
    }
    if (storage) {
        if (!origin->name || generic_argument_type(*origin->name) != storage->type) {
            fail(r, EINVAL, "Generic argument name does not match its typed storage"); return 0;
        }
        if (!meta_storage_ready(r, storage, storage->type, true, false, storage_id)) return 0;
        if (origin->writable && entry(storage_id)->read_only) { fail(r, EPERM, "Return argument requires writable storage"); return 0; }
    }
    origin->storage = storage_id;
    auto *value = new T(origin->name ? origin->name->constData() : nullptr, storage ? storage->data : nullptr);
    auto id = insert(r, value, nullptr, type, native_deleter<T>(), true, NativeTraits<T>::cast);
    if (!id) return 0;
    try {
        if (install_generic_argument_origin(r, id, std::move(origin))) return id;
    } catch (...) { invalidate(id); delete value; throw; }
    invalidate(id); delete value; return 0;
}
static uint32_t finish_generic_argument_ownership(BqtRequest *r, uint32_t id) {
    auto *e = entry(id);
    auto *value = generic_argument_value(e);
    if (!value) return id;
    uint32_t source = native_call_scope && native_call_scope->value_origin ? native_call_scope->value_origin : r->self;
    auto *old = entry(source) ? generic_argument_origins[source & 65535u] : nullptr;
    try {
        std::unique_ptr<GenericArgumentOrigin> origin;
        if (old) origin = std::make_unique<GenericArgumentOrigin>(*old);
        else if (!value->name() && !value->data()) origin = std::make_unique<GenericArgumentOrigin>();
        else { fail(r, ENOTSUP, "Generic argument copy has no typed storage origin"); }
        if (origin && install_generic_argument_origin(r, id, std::move(origin))) return id;
    } catch (...) {
        auto *storage = e->value; auto destroy = e->destroy;
        invalidate(id); destroy(storage); throw;
    }
    auto *storage = e->value; auto destroy = e->destroy;
    invalidate(id); destroy(storage); return 0;
}
static bool validate_generic_storage_alias(BqtRequest *r, uint32_t id) {
    auto *e = entry(id);
    if (!e) { fail(r, ESTALE, "Generic argument storage alias expired"); return false; }
    auto *storage = static_cast<MetaStorage *>(e->value);
    if (!validate_generic_argument(r, storage->alias_owner)) return false;
    auto *argument = generic_argument_value(entry(storage->alias_owner));
    if (!argument || argument->data() != storage->data) { fail(r, ESTALE, "Generic argument was reassigned"); return false; }
    if (native_call_scope) native_call_scope->pin(r, storage->alias_owner);
    return !r->error;
}
static uint32_t generic_argument_storage(BqtRequest *r, uint32_t owner) {
    auto *origin = generic_argument_origins[owner & 65535u];
    if (!origin || !origin->storage) return 0;
    auto *source = get<MetaStorage>(r, origin->storage, @MetaStorage@, false, false);
    if (!source) return 0;
    auto id = own(r, new MetaStorage(source->type, source->data, owner), @MetaStorage@);
    if (!id) return 0;
    BqtRequest claim{}; claim.self = id;
    int edge = prepare_retention(&claim, generic_argument_slot, 0, owner);
    if (claim.error) {
        auto *storage = static_cast<MetaStorage *>(entry(id)->value);
        invalidate(id); delete storage; fail(r, claim.error, claim.message); return 0;
    }
    commit_retention(edge, id, generic_argument_slot, 0, owner, nullptr);
    entry(id)->validate = validate_generic_storage_alias;
    entry(id)->read_only = !origin->writable || entry(origin->storage)->read_only;
    return finish_model_index_ownership(r, id);
}

struct GenericCallInput { uint32_t id; bool output; };
static QMetaMethod find_generic_method(const QMetaObject *meta, const QByteArray &name,
        std::initializer_list<GenericCallInput> inputs, bool constructor) {
    const int count = constructor ? meta->constructorCount() : meta->methodCount();
    for (int i = 0; i < count; ++i) {
        auto method = constructor ? meta->constructor(i) : meta->method(i);
        if (!constructor && method.name() != name) continue;
        int parameter = 0;
        bool matches = true;
        for (auto input : inputs) {
            if (input.output) continue;
            auto *argument = generic_argument_value(entry(input.id));
            if (!argument || !argument->name()) break;
            if (parameter >= method.parameterCount() || generic_argument_type(argument->name()) != method.parameterMetaType(parameter++)) { matches = false; break; }
        }
        if (matches && parameter == method.parameterCount()) return method;
    }
    return {};
}
struct GenericMetaCall {
    BqtRequest *request;
    std::vector<uint32_t> written;
    int exception_depth = std::uncaught_exceptions();
    bool handled = false;
    GenericMetaCall(BqtRequest *r, const QMetaMethod &method, uint32_t receiver,
                   Qt::ConnectionType connection, std::initializer_list<GenericCallInput> inputs) : request(r) {
        if (connection == Qt::BlockingQueuedConnection) { fail(r, EDEADLK, "A blocking queued invocation from the main thread would wait for itself"); return; }
        if (connection != Qt::AutoConnection && connection != Qt::DirectConnection && connection != Qt::QueuedConnection) {
            fail(r, EINVAL, "Unsupported generic invocation connection flags"); return;
        }
        if (receiver && method.isValid()) {
            auto *e = entry(receiver);
            if (!e || !e->object || e->object->thread() != main_thread) { fail(r, EXDEV, "Generic invocation receiver belongs to another thread"); return; }
            if (!e->object->metaObject()->inherits(method.enclosingMetaObject())) { fail(r, EINVAL, "Method does not belong to the receiver's Qt class"); return; }
        }
        int parameter = 0;
        const auto parameter_names = method.parameterTypes();
        bool empty = false;
        for (auto input : inputs) {
            if (!validate_generic_argument(r, input.id)) return;
            auto *argument = generic_argument_value(entry(input.id));
            auto *origin = generic_argument_origins[input.id & 65535u];
            if (!argument->name()) { if (!input.output) empty = true; continue; }
            if (empty && !input.output) { fail(r, EINVAL, "Generic arguments must be contiguous"); return; }
            if (!origin->storage) { fail(r, ENODATA, "Named generic argument has no native storage"); return; }
            auto *e = entry(origin->storage);
            bool mutable_reference = !input.output && parameter < parameter_names.size() &&
                parameter_names[parameter].endsWith('&') && !parameter_names[parameter].startsWith("const ");
            if (!input.output) ++parameter;
            if (e->active_calls > 1) { fail(r, EBUSY, "Generic argument storage is active in another native call"); return; }
            if ((input.output || mutable_reference) && e->read_only) { fail(r, EPERM, "Meta-call needs writable argument storage"); return; }
            if (connection == Qt::QueuedConnection) {
                if (input.output || mutable_reference) { fail(r, EINVAL, "Queued invocation cannot synchronously write arguments"); return; }
                bool dependent = e->validate || e->native_owner;
                for (const auto &edge : retentions) if (edge.owner == origin->storage && edge.target) dependent = true;
                if (dependent) { fail(r, ENOTSUP, "Queued invocation requires independently owned metatype values"); return; }
            }
            if (input.output || mutable_reference) written.push_back(origin->storage);
        }
    }
    ~GenericMetaCall() {
        if (std::uncaught_exceptions() <= exception_depth) return;
        // An exception can follow a partial native write. An owning storage
        // token must not continue advertising its old origin after that write.
        for (auto id : written) {
            for (uint32_t depth = 0; depth < capacity; ++depth) {
                auto *e = entry(id);
                if (!e || e->type != @MetaStorage@) break;
                auto *storage = static_cast<MetaStorage *>(e->value);
                if (storage->owns_storage) { invalidate(id); delete storage; break; }
                auto *argument = generic_argument_value(entry(storage->alias_owner));
                if (!argument) break; // Native scalar view (for example QJSPrimitiveValue).
                auto *origin = generic_argument_origins[storage->alias_owner & 65535u];
                if (!origin || origin->storage == id) break;
                id = origin->storage;
            }
        }
    }
    bool finish(bool called) {
        if (!called) return true;
        for (auto id : written) {
            clear_variant_origin(id);
            if (!finish_model_index_ownership(request, id)) return false;
        }
        return true;
    }
};
