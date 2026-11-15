#if @HAS_QML@
namespace RuntimeQtObjects {
static constexpr uint32_t singleton_owner_slot = 0xffffffa0u;
static constexpr uint32_t singleton_instance_slot = 0xffffffa1u;
struct TypeState;
using RelatedFactory = QObject *(*)(QObject *);
struct SingletonState {
    std::shared_ptr<ClassInfo> schema;
    std::shared_ptr<TypeState> related;
    QByteArray uri, name;
    QPointer<QObject> instance;
    QPointer<QQmlEngine> instance_engine;
    uint32_t owner = 0, instance_id = 0, handler = 0;
    int type_id = -1;
    bool active = true, instance_used = false;
};
static bool setup_singleton_related(BqtRequest *, const std::shared_ptr<SingletonState> &, const BqtValue &);
static RelatedFactory singleton_extension_factory(const SingletonState &);
static const QMetaObject *singleton_extension_meta(const SingletonState &);
static bool initialize_singleton(BqtRequest *, SingletonState &, uint32_t);
class SingletonRegistration final : public QObject {
    std::shared_ptr<SingletonState> state;
public:
    explicit SingletonRegistration(std::shared_ptr<SingletonState> value) : state(std::move(value)) {}
    std::shared_ptr<TypeState> related() const { return state->related; }
    ~SingletonRegistration() override;
};
static bool singleton_decode(BqtRequest *r, const BqtValue &wire, void *context) {
    auto *pair = static_cast<std::pair<SingletonState *, QQmlEngine *> *>(context);
    auto value = runtime_argument_read(r, -2 - pair->first->schema->pointer->index, wire);
    if (r->error) return false;
    auto *object = *static_cast<QObject *const *>(value.constData());
    if (!object || (object->parent() && object->parent() != pair->second))
        return reject(r, EINVAL, "A singleton factory must return an unparented object or an engine child");
    object->setParent(pair->second);
    QJSEngine::setObjectOwnership(object, QJSEngine::CppOwnership);
    set_owned(wire.word, false);
    if (auto *e = entry(wire.word)) e->scope_owner = 0;
    pair->first->instance = object;
    return initialize_singleton(r, *pair->first, wire.word);
}
static QObject *singleton_get(const std::shared_ptr<SingletonState> &state, QQmlEngine *engine) {
    if (!state->active || QThread::currentThread() != main_thread) return nullptr;
    // A singleton requested from a root constructor is a separate allocation,
    // including when its typed factory uses the same Bend class schema.
    RuntimePlacementScope placement(nullptr);
    NativeCallScope scope;
    BqtRequest request{};
    try {
        uint32_t engine_id = borrow(&request, engine, @QML_ENGINE_ID@);
        if (request.error) return nullptr;
        request.self = engine_id;
        int edge = prepare_retention(&request, singleton_owner_slot, state->owner, state->owner);
        if (request.error) { callback_report_error(request.error, request.message); return nullptr; }
        commit_retention(edge, engine_id, singleton_owner_slot, state->owner, state->owner, nullptr);
        if (state->instance_id) {
            if (!state->instance || (state->instance_used && state->instance_engine != engine)) {
                engine->throwError(QStringLiteral("A registered singleton instance may be used by only one QML engine"));
                return nullptr;
            }
            if (!state->instance_used) {
                // Before first use the registration keeps the supplied object
                // alive. Once QML uses it, the engine holds that object directly.
                // Otherwise an extension retaining its registration would form
                // registration -> instance -> extension -> registration.
                int instance_edge = prepare_retention(&request, singleton_instance_slot, 0, state->instance_id);
                if (request.error) { callback_report_error(request.error, request.message); return nullptr; }
                commit_retention(instance_edge, engine_id, singleton_instance_slot, 0, state->instance_id, nullptr);
                BqtRequest release{}; release.self = state->owner;
                int previous_edge = prepare_retention(&release, singleton_instance_slot, 0, 0);
                if (release.error) { callback_report_error(release.error, release.message); return nullptr; }
                commit_retention(previous_edge, state->owner, singleton_instance_slot, 0, 0, nullptr);
            }
            if (!state->instance_used && !initialize_singleton(&request, *state, state->instance_id)) {
                callback_report_error(request.error, request.message);
                return nullptr;
            }
            state->instance_used = true; state->instance_engine = engine;
            QJSEngine::setObjectOwnership(state->instance, QJSEngine::CppOwnership);
            return state->instance;
        }
        // The engine owns factory-created instances. Transfer ownership while
        // decoding the answer, before the Bend callback scope is closed.
        std::pair<SingletonState *, QQmlEngine *> context{state.get(), engine};
        if (state->handler) {
            CallbackOwnedArguments arguments{sequence_value(1)};
            arguments.value.items[0].word = engine_id;
            arguments.value.items[0].borrowed_handle = engine_id;
            int error = callback_invoke(state->handler, state->owner, arguments.take(), singleton_decode, &context);
            if (error) return nullptr;
        } else {
            BqtRequest construction{};
            if (!state->schema->base.constructor) { engine->throwError(QStringLiteral("Singleton native base needs a Bend factory")); return nullptr; }
            RuntimeConstructionMeta metadata(state->schema->meta);
            state->schema->base.constructor(&construction);
            if (!construction.error) attach_definition(&construction, construction.result.word, state->schema);
            if (!construction.error) singleton_decode(&construction, construction.result, &context);
            if (construction.error) { discard_value(construction.result); callback_report_error(construction.error, construction.message); return nullptr; }
        }
        return state->instance;
    } catch (const std::bad_alloc &) { callback_report_error(ENOMEM); }
      catch (...) { callback_report_error(EFAULT); }
    return nullptr;
}
static bool register_singleton_common(BqtRequest *r, bool factory) {
    NativeCallScope scope;
    const auto &wire = r->arguments[0];
    if (!wire_shape(r, wire, 2, 3)) return true;
    auto schema = ensure_class(r, wire.items[0]); if (!schema) return true;
    auto revision = parse_revision(r, r->arguments[factory ? 5 : 7]); if (!revision) return true;
    for (size_t i : {1u, 4u}) if (!r->arguments[i].size || std::memchr(r->arguments[i].text, 0, r->arguments[i].size))
        return fail(r, EINVAL, "QML singleton URI and name must be nonempty and contain no NUL");
    if (r->arguments[2].word > 254 || r->arguments[3].word > 254) return fail(r, ERANGE, "Invalid QML singleton version");
    auto state = std::make_shared<SingletonState>();
    state->schema = schema; state->uri = text(r->arguments[1]); state->name = text(r->arguments[4]);
    if (!setup_singleton_related(r, state, wire)) return true;
    if (!BendSignalApi::qml_name(state->name))
        return fail(r, EINVAL, "A QML singleton name must begin with an uppercase letter");
    if (!factory) {
        uint32_t mode = r->arguments[6].word;
        if (mode > 1) return fail(r, EINVAL, "Invalid singleton mode");
        if (mode) {
            state->instance_id = r->arguments[5].word;
            auto *object = get<QObject>(r, state->instance_id, @QOBJECT_ID@);
            if (r->error) return true;
            if (!object->metaObject()->inherits(schema->meta)) return fail(r, EINVAL, "Singleton instance has the wrong Bend class");
            state->instance = object;
        } else if (!schema->base.constructor) return fail(r, ENOTSUP, "This singleton requires a Bend factory");
    }
    auto registration = std::make_unique<SingletonRegistration>(state);
    uint32_t owner = own(r, static_cast<QObject *>(registration.release()), @QOBJECT_ID@);
    if (r->error) return true;
    state->owner = owner;
    if (state->instance_id) {
        BqtRequest retention{}; retention.self = owner;
        int edge = prepare_retention(&retention, singleton_instance_slot, 0, state->instance_id);
        if (retention.error) { BqtRequest release{}; release.self = owner; release_object(&release); return fail(r, retention.error, retention.message); }
        commit_retention(edge, owner, singleton_instance_slot, 0, state->instance_id, nullptr);
    }
    QQmlPrivate::RegisterSingletonType api{};
    api.structVersion = 0; api.uri = state->uri.constData();
    api.version = QTypeRevision::fromVersion(int(r->arguments[2].word), int(r->arguments[3].word));
    api.typeName = state->name.constData();
    api.qObjectApi = [state](QQmlEngine *engine, QJSEngine *) { return singleton_get(state, engine); };
    api.instanceMetaObject = schema->meta; api.typeId = schema->pointer->type();
    api.extensionObjectCreate = singleton_extension_factory(*state);
    api.extensionMetaObject = singleton_extension_meta(*state);
    api.revision = *revision;
    state->type_id = QQmlPrivate::qmlregister(QQmlPrivate::SingletonRegistration, &api);
    if (state->type_id < 0) { BqtRequest release{}; release.self = owner; release_object(&release); return fail(r, EINVAL, "Qt rejected the singleton registration"); }
    if (factory) state->handler = r->arguments[6].word;
    r->result.word = owner; r->result.owned_handle = owner;
    return true;
}
static bool register_singleton(BqtRequest *r) { return register_singleton_common(r, false); }
static bool register_factory(BqtRequest *r) { return register_singleton_common(r, true); }

struct TypeAnchor {
    std::shared_ptr<ClassInfo> schema, attached, extension;
    std::weak_ptr<TypeState> state;
};
struct FactorySlot { TypeAnchor *anchor = nullptr; bool extension = false; };
struct TypeState {
    std::shared_ptr<ClassInfo> schema, attached, extension;
    QByteArray uri, name;
    uint32_t owner = 0, handlers[4]{};
    int type_id = -1;
    bool active = true;
    bool placement_constructor = true;
    RelatedFactory attached_factory = nullptr, extension_factory = nullptr;
    std::map<QObject *, std::pair<uint32_t, QPointer<QObject>>> extensions;
};
SingletonRegistration::~SingletonRegistration() {
    state->active = false;
    if (state->related) {
        state->related->active = false;
        for (auto &handler : state->related->handlers)
            if (handler) callback_release_handler(std::exchange(handler, 0));
    }
    if (state->type_id >= 0) QQmlPrivate::qmlunregister(QQmlPrivate::SingletonRegistration, quintptr(state->type_id));
    if (state->handler) callback_release_handler(std::exchange(state->handler, 0));
}
static RelatedFactory singleton_extension_factory(const SingletonState &state) {
    state.related->owner = state.owner;
    return state.related->extension_factory;
}
static const QMetaObject *singleton_extension_meta(const SingletonState &state) {
    return state.related->extension ? state.related->extension->meta : nullptr;
}
static QObject *related_create(FactorySlot *, QObject *);

// Qt's attached/extension callbacks have no userdata. Allocate a distinct
// callback identity with its context, as a closure. Code is written once, then
// made executable and read-only; contexts remain separate writable data.
// Qt caches these function addresses, so pages live until process exit.
static RelatedFactory factory_closure(BqtRequest *r, TypeAnchor *anchor, bool extension) {
    struct Page { FactorySlot *contexts; unsigned char *code; size_t used, count; };
    static auto *pages = new std::vector<Page>;
    if (pages->empty() || pages->back().used == pages->back().count) {
        long page_size = sysconf(_SC_PAGESIZE);
        if (page_size < 32) { fail(r, ENOSYS, "Cannot determine executable page size"); return nullptr; }
        size_t count = size_t(page_size) / 32;
        auto contexts = std::make_unique<FactorySlot[]>(count);
        void *memory = mmap(nullptr, size_t(page_size), PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        if (memory == MAP_FAILED) { fail(r, errno, "Cannot allocate QML factory closures"); return nullptr; }
        auto *code = static_cast<unsigned char *>(memory);
        for (size_t i = 0; i < count; ++i) {
            // SysV x86-64: factory(QObject*) -> related_create(context, QObject*).
            const unsigned char prefix[] = {0xf3,0x0f,0x1e,0xfa, 0x48,0x89,0xfe, 0x48,0xbf};
            auto *at = code + i * 32;
            std::memcpy(at, prefix, sizeof(prefix));
            uintptr_t context = reinterpret_cast<uintptr_t>(&contexts[i]);
            std::memcpy(at + 9, &context, 8);
            at[17] = 0x48; at[18] = 0xb8;
            uintptr_t function = reinterpret_cast<uintptr_t>(&related_create);
            std::memcpy(at + 19, &function, 8);
            at[27] = 0xff; at[28] = 0xe0;
            at[29] = at[30] = at[31] = 0x90;
        }
        if (mprotect(memory, size_t(page_size), PROT_READ | PROT_EXEC)) {
            int error = errno; munmap(memory, size_t(page_size));
            fail(r, error, "Cannot finalize QML factory closures"); return nullptr;
        }
        try { pages->push_back(Page{contexts.get(), code, 0, count}); }
        catch (...) { munmap(memory, size_t(page_size)); throw; }
        contexts.release();
    }
    auto &page = pages->back(); size_t index = page.used++;
    page.contexts[index] = FactorySlot{anchor, extension};
    return reinterpret_cast<RelatedFactory>(page.code + index * 32);
}
class TypeRegistration final : public QObject {
public:
    std::shared_ptr<TypeState> state;
    explicit TypeRegistration(std::shared_ptr<TypeState> value) : state(std::move(value)) {}
    ~TypeRegistration() override {
        state->active = false;
        if (state->type_id >= 0) QQmlPrivate::qmlunregister(QQmlPrivate::TypeRegistration, quintptr(state->type_id));
        for (auto &handler : state->handlers) if (handler) callback_release_handler(std::exchange(handler, 0));
    }
};
static std::shared_ptr<TypeState> type_state(BqtRequest *r) {
    auto *object = get<QObject>(r, r->self, @QOBJECT_ID@);
    if (r->error) return {};
    auto *registration = dynamic_cast<TypeRegistration *>(object);
    if (registration && registration->state->active) return registration->state;
    auto *singleton = dynamic_cast<SingletonRegistration *>(object);
    if (singleton && singleton->related() && singleton->related()->active) return singleton->related();
    fail(r, EINVAL, "Expected an active QML type or singleton registration"); return {};
}
static bool retain_registration(BqtRequest *r, uint32_t id, uint32_t owner) {
    BqtRequest retention{}; retention.self = id;
    int edge = prepare_retention(&retention, singleton_owner_slot, owner, owner);
    if (retention.error) return reject(r, retention.error, retention.message);
    commit_retention(edge, id, singleton_owner_slot, owner, owner, nullptr);
    return true;
}
static bool decode_unit(BqtRequest *r, const BqtValue &wire, void *) {
    return (!wire.tag && !wire.word && !wire.high) || reject(r, EINVAL, "A QML initializer must return Unit");
}
static bool initialize_singleton(BqtRequest *r, SingletonState &state, uint32_t instance) {
    if (!state.related || !state.related->handlers[0]) return true;
    CallbackOwnedArguments arguments{sequence_value(1)};
    arguments.value.items[0].word = instance;
    arguments.value.items[0].borrowed_handle = instance;
    int error = callback_invoke(state.related->handlers[0], state.owner, arguments.take(), decode_unit, nullptr);
    if (!error) return true;
    auto *frame = CallFrame::current;
    return reject(r, error, frame && frame->handler_error == error && !frame->handler_message.empty()
        ? frame->handler_message.c_str() : "Bend singleton initializer failed");
}
static bool decode_placement(BqtRequest *r, const BqtValue &wire, void *context) {
    auto &pending = *static_cast<RuntimePendingPlacement *>(context);
    auto *object = get<QObject>(r, wire.word, @QOBJECT_ID@);
    if (r->error) return false;
    if (!pending.object || object != pending.object || wire.word != pending.handle)
        return reject(r, EINVAL, "A QML constructor must return the instance built by newAs or QtObject.new for its pending schema");
    return true;
}
static void create_into(void *memory, void *userdata) {
    auto *anchor = static_cast<TypeAnchor *>(userdata);
    auto state = anchor->state.lock();
    RuntimePendingPlacement pending{anchor->schema->meta, anchor->schema->base.id, memory};
    RuntimePlacementScope placement(&pending);
    NativeCallScope scope;
    BqtRequest request{};
    try {
        bool active = state && state->active;
        if (active && state->handlers[3]) {
            CallbackOwnedArguments arguments{sequence_value(0)};
            int error = callback_invoke(state->handlers[3], state->owner, arguments.take(), decode_placement, &pending);
            if (error) {
                auto *frame = CallFrame::current;
                fail(&request, error, frame && frame->handler_error == error && !frame->handler_message.empty()
                    ? frame->handler_message.c_str() : "Bend QML constructor failed");
            }
        }
        if (!pending.object && anchor->schema->base.place) {
            RuntimeConstructionMeta metadata(anchor->schema->meta);
            pending.claimed = true;
            pending.object = anchor->schema->base.place(memory);
        }
        if (!pending.object) {
            if (!request.error) fail(&request, active ? ENOSYS : ESTALE,
                active ? "This QML native base needs Qml.handleConstructor and a schema-aware constructor" : "The QML type registration has expired");
            callback_report_error(request.error, request.message);
            throw std::runtime_error(request.message ? request.message : "QML construction failed before placement");
        }
        auto *object = pending.object;
        uint32_t id = pending.handle ? pending.handle : borrow(&request, object, anchor->schema->base.id);
        if (!request.error) dynamic_cast<RuntimeObjectHost *>(object)->runtime_observe(id);
        auto *host = dynamic_cast<RuntimeObjectHost *>(object);
        if (!request.error && !host->bqt_object) attach_definition(&request, id, anchor->schema);
        if (!request.error && (!state || !state->active)) fail(&request, ESTALE, "The QML type registration has expired");
        if (!request.error) retain_registration(&request, id, state->owner);
        if (!request.error && state->handlers[0]) {
            CallbackOwnedArguments arguments{sequence_value(1)};
            arguments.value.items[0].word = id; arguments.value.items[0].borrowed_handle = id;
            callback_invoke(state->handlers[0], state->owner, arguments.take(), decode_unit, nullptr);
        }
    } catch (const std::bad_alloc &) {
        if (!request.error) fail(&request, ENOMEM, "QML constructor allocation failed");
        if (!pending.object) { callback_report_error(request.error, request.message); throw; }
    } catch (...) {
        if (!request.error) fail(&request, EFAULT, "QML constructor raised an exception");
        if (!pending.object) { callback_report_error(request.error, request.message); throw; }
    }
    if (request.error) callback_report_error(request.error, request.message);
}
struct RelatedResult {
    std::shared_ptr<ClassInfo> schema;
    QObject *parent, *value = nullptr;
    uint32_t owner;
    bool extension;
};
static bool decode_related(BqtRequest *r, const BqtValue &wire, void *context) {
    auto &result = *static_cast<RelatedResult *>(context);
    auto value = runtime_argument_read(r, -2 - result.schema->pointer->index, wire);
    if (r->error) return false;
    auto *object = *static_cast<QObject *const *>(value.constData());
    if (result.extension && object && object->metaObject() != result.schema->meta)
        return reject(r, ENOTSUP, "Qt requires an extension factory to return the exact registered static metaobject");
    if (!object || object == result.parent || (object->parent() && object->parent() != result.parent))
        return reject(r, EINVAL, "An attached or extension factory must return a new object or a child of its target");
    if (result.owner && !retain_registration(r, wire.word, result.owner)) return false;
    object->setParent(result.parent);
    QJSEngine::setObjectOwnership(object, QJSEngine::CppOwnership);
    set_owned(wire.word, false);
    if (auto *e = entry(wire.word)) e->scope_owner = 0;
    result.value = object;
    return true;
}
static QObject *related_create(FactorySlot *slot, QObject *parent) {
    auto state = slot->anchor->state.lock();
    if (QThread::currentThread() != main_thread) return nullptr;
    RuntimePlacementScope placement(nullptr);
    NativeCallScope scope;
    BqtRequest request{};
    auto schema = slot->extension ? slot->anchor->extension : slot->anchor->attached;
    bool active = state && state->active;
    RelatedResult context{schema, parent, nullptr, active ? state->owner : 0, slot->extension};
    uint32_t target = borrow(&request, parent, @QOBJECT_ID@);
    uint32_t handler = active ? state->handlers[slot->extension ? 2 : 1] : 0;
    int handler_error = 0;
    if (!request.error && handler) {
        CallbackOwnedArguments arguments{sequence_value(1)};
        arguments.value.items[0].word = target; arguments.value.items[0].borrowed_handle = target;
        // A failed handler has already reported its original error. Qt's
        // extension machinery dereferences the returned object unconditionally,
        // so leave a correctly typed default instance for Qt to finish/clean up.
        handler_error = callback_invoke(handler, state->owner, arguments.take(), decode_related, &context);
    }
    if (!request.error && !context.value) {
        if (!schema->base.make) {
            auto *frame = CallFrame::current;
            int error = handler_error ? handler_error : active ? ENOSYS : ESTALE;
            const char *message = frame && frame->handler_error == error && !frame->handler_message.empty()
                ? frame->handler_message.c_str() : "A nondefault QML related type needs an installed Bend factory";
            callback_report_error(error, message);
            if (slot->extension) throw std::runtime_error(message);
            return nullptr;
        }
        RuntimeConstructionMeta metadata(schema->meta);
        uint32_t id = own(&request, schema->base.make(), schema->base.id);
        BqtValue wire{}; wire.word = id; wire.owned_handle = id;
        if (!request.error) {
            auto *host = dynamic_cast<RuntimeObjectHost *>(entry(id)->object);
            host->runtime_observe(id);
            attach_definition(&request, id, schema);
        }
        if (!request.error) decode_related(&request, wire, &context);
        if (request.error) discard_value(wire);
    }
    if (request.error) {
        callback_report_error(request.error, request.message);
        if (!slot->extension) return nullptr;
        // Native allocation/construction errors unwind like Qt constructors;
        // never hand Qt an invalid/null extension and continue dereferencing it.
        throw std::runtime_error(request.message ? request.message : "QML related-object construction failed");
    }
    if (!active) callback_report_error(ESTALE, "The QML type registration has expired");
    if (active && slot->extension) {
        state->extensions[parent] = {target, context.value};
        std::weak_ptr<TypeState> weak = state;
        QObject::connect(parent, &QObject::destroyed, application, [weak, parent, target] {
            if (auto state = weak.lock()) {
                auto found = state->extensions.find(parent);
                if (found != state->extensions.end() && found->second.first == target) state->extensions.erase(found);
            }
        });
    }
    return context.value;
}
static bool setup_singleton_related(BqtRequest *r, const std::shared_ptr<SingletonState> &state, const BqtValue &wire) {
    // Qt's singleton registration ABI exposes extension objects but no attached
    // factory. Do not silently discard an attached declaration on this path.
    if (!is_absent(wire.items[1])) return reject(r, ENOTSUP, "Qt singleton registration does not support attached types");
    auto related = std::make_shared<TypeState>();
    related->schema = state->schema;
    related->placement_constructor = false;
    if (!is_absent(wire.items[2])) {
        related->extension = ensure_class(r, wire.items[2]);
        if (!related->extension) return false;
        if (!related->extension->base.static_metadata)
            return reject(r, ENOTSUP, "A singleton extension needs a native base with static metadata");
        if (!related->extension->base.extension_metadata)
            return reject(r, ENOTSUP, "Qt's extension proxy does not support a native dynamic metaobject such as QQmlPropertyMap");
        auto anchor = std::make_unique<TypeAnchor>(TypeAnchor{related->schema, {}, related->extension, related});
        related->extension_factory = factory_closure(r, anchor.get(), true);
        if (r->error) { anchor.release(); return false; }
        anchor.release(); // Qt caches the closure context for process lifetime.
    }
    state->related = std::move(related);
    return true;
}
static bool register_type_common(BqtRequest *r, uint32_t mode, const QString &reason,
        QTypeRevision revision = QTypeRevision::fromMinorVersion(0)) {
    NativeCallScope scope;
    if (mode > 2) return fail(r, EINVAL, "Invalid QML type registration mode");
    const auto &wire = r->arguments[0];
    if (!wire_shape(r, wire, 2, 3)) return true;
    auto state = std::make_shared<TypeState>();
    state->schema = ensure_class(r, wire.items[0]); if (!state->schema) return true;
    if (!is_absent(wire.items[1])) { state->attached = ensure_class(r, wire.items[1]); if (!state->attached) return true; }
    if (!is_absent(wire.items[2])) { state->extension = ensure_class(r, wire.items[2]); if (!state->extension) return true; }
    if (state->extension && !state->extension->base.extension_metadata)
        return fail(r, ENOTSUP, "Qt's extension proxy does not support a native dynamic metaobject such as QQmlPropertyMap");
    if (!state->schema->base.static_metadata)
        return fail(r, ENOTSUP, "A QML class needs a native base with schema-aware metadata");
    for (const auto &schema : {state->attached, state->extension})
        if (schema && !schema->base.static_metadata)
            return fail(r, ENOTSUP, "A QML related type needs a native base with static metadata");
    if (!r->arguments[1].size || std::memchr(r->arguments[1].text, 0, r->arguments[1].size))
        return fail(r, EINVAL, "QML type URI must be nonempty and contain no NUL");
    if (r->arguments[2].word > 254 || r->arguments[3].word > 254) return fail(r, ERANGE, "Invalid QML type version");
    state->uri = text(r->arguments[1]); state->name = text(r->arguments[4]);
    if (mode != 2 && !BendSignalApi::qml_name(state->name))
        return fail(r, EINVAL, "A QML type name must begin with an uppercase letter");
    auto anchor = std::make_unique<TypeAnchor>(TypeAnchor{state->schema, state->attached, state->extension, state});
    if (state->attached) state->attached_factory = factory_closure(r, anchor.get(), false);
    if (!r->error && state->extension) state->extension_factory = factory_closure(r, anchor.get(), true);
    if (r->error) { anchor.release(); return true; } // An allocated callback keeps its context address.
    auto registration = std::make_unique<TypeRegistration>(state);
    state->owner = own(r, static_cast<QObject *>(registration.release()), @QOBJECT_ID@);
    if (r->error) { anchor.release(); return true; }
    auto *list = BendQmlLists::ensure_type(r, -2 - state->schema->pointer->index);
    if (!list) return true;
    QQmlPrivate::RegisterType api{};
    api.structVersion = QQmlPrivate::RegisterType::CurrentVersion;
    api.typeId = state->schema->pointer->type(); api.listId = list->native;
    const auto &base = state->schema->base;
    api.objectSize = mode ? 0 : base.size; api.create = mode ? nullptr : create_into;
    api.userdata = anchor.release(); api.noCreationReason = reason;
    api.uri = state->uri.constData(); api.elementName = mode == 2 ? nullptr : state->name.constData();
    api.version = QTypeRevision::fromVersion(int(r->arguments[2].word), int(r->arguments[3].word));
    api.metaObject = state->schema->meta;
    api.revision = revision;
    api.parserStatusCast = base.parser; api.valueSourceCast = base.source;
    api.valueInterceptorCast = base.interceptor; api.finalizerCast = base.finalizer;
    api.attachedPropertiesFunction = state->attached_factory;
    api.attachedPropertiesMetaObject = state->attached ? state->attached->meta : nullptr;
    api.extensionObjectCreate = state->extension_factory;
    api.extensionMetaObject = state->extension ? state->extension->meta : nullptr;
    state->type_id = QQmlPrivate::qmlregister(QQmlPrivate::TypeRegistration, &api);
    if (state->type_id < 0) { BqtRequest release{}; release.self = state->owner; release_object(&release); return fail(r, EINVAL, "Qt rejected the type registration"); }
    r->result.word = state->owner; r->result.owned_handle = state->owner;
    return true;
}
static bool register_type(BqtRequest *r) { return register_type_common(r, 0, QString()); }
static bool register_type_revision(BqtRequest *r) {
    auto revision = parse_revision(r, r->arguments[5]);
    return revision ? register_type_common(r, 0, QString(), *revision) : true;
}
static bool register_type_mode(BqtRequest *r) {
    return register_type_common(r, r->arguments[5].word,
        QString::fromUtf8(r->arguments[6].text, qsizetype(r->arguments[6].size)));
}
class UnavailableRegistration final : public QObject {
    int type_id = -1;
public:
    void registered(int value) { type_id = value; }
    ~UnavailableRegistration() override {
        if (type_id >= 0) QQmlPrivate::qmlunregister(QQmlPrivate::TypeRegistration, quintptr(type_id));
    }
};
static bool register_unavailable(BqtRequest *r) {
    NativeCallScope scope;
    for (size_t index : {0u, 3u})
        if (!r->arguments[index].size || std::memchr(r->arguments[index].text, 0, r->arguments[index].size))
            return fail(r, EINVAL, "QML type URI and name must be nonempty and contain no NUL");
    if (r->arguments[1].word > 254 || r->arguments[2].word > 254)
        return fail(r, ERANGE, "Invalid QML type version");
    const QByteArray uri = text(r->arguments[0]), name = text(r->arguments[3]);
    if (!BendSignalApi::qml_name(name))
        return fail(r, EINVAL, "A QML type name must begin with an uppercase letter");
    auto registration = std::make_unique<UnavailableRegistration>();
    int type = qmlRegisterTypeNotAvailable(uri.constData(), int(r->arguments[1].word),
        int(r->arguments[2].word), name.constData(),
        QString::fromUtf8(r->arguments[4].text, qsizetype(r->arguments[4].size)));
    if (type < 0) return fail(r, EINVAL, "Qt rejected the unavailable type registration");
    registration->registered(type);
    r->result.word = own(r, static_cast<QObject *>(registration.release()), @QOBJECT_ID@);
    r->result.owned_handle = r->result.word;
    return true;
}
static bool install_qml(BqtRequest *r) {
    auto state = type_state(r); if (!state) return true;
    const auto &wire = r->arguments[0];
    if (!wire_shape(r, wire, 2, 3)) return true;
    std::shared_ptr<ClassInfo> declared[] = {state->schema, state->attached, state->extension};
    for (size_t i = 0; i < 3; ++i) {
        auto value = is_absent(wire.items[i]) ? std::shared_ptr<ClassInfo>{} : ensure_class(r, wire.items[i]);
        if (r->error) return true;
        if (value != declared[i]) return fail(r, EINVAL, "The QML registration has a different class schema");
    }
    uint32_t kind = r->arguments[1].word;
    if (kind > 3 || (kind == 1 && !state->attached) || (kind == 2 && !state->extension) || (kind == 3 && !state->placement_constructor))
        return fail(r, EINVAL, "The QML type does not declare this factory");
    uint32_t previous = std::exchange(state->handlers[kind], r->arguments[2].word);
    if (previous) callback_release_handler(previous);
    return true;
}
static bool related_object(BqtRequest *r) {
    NativeCallScope scope;
    auto state = type_state(r); if (!state) return true;
    auto *target = get<QObject>(r, r->arguments[0].word, @QOBJECT_ID@); if (r->error) return true;
    const auto &wire = r->arguments[1];
    if (!wire_shape(r, wire, 2, 3)) return true;
    std::shared_ptr<ClassInfo> declared[] = {state->schema, state->attached, state->extension};
    for (size_t i = 0; i < 3; ++i) {
        auto value = is_absent(wire.items[i]) ? std::shared_ptr<ClassInfo>{} : ensure_class(r, wire.items[i]);
        if (r->error) return true;
        if (value != declared[i]) return fail(r, EINVAL, "The QML registration has a different class schema");
    }
    uint32_t kind = r->arguments[2].word;
    QObject *value = nullptr;
    if (kind == 0 && state->attached) value = qmlAttachedPropertiesObject(target, state->attached_factory, true);
    else if (kind == 1 && state->extension && target->metaObject()->inherits(state->schema->meta)) {
        auto cached = state->extensions.find(target);
        if (cached != state->extensions.end() && cached->second.first == r->arguments[0].word)
            value = cached->second.second;
        if (!value) {
            // A derived QML type can have its own extension before this base's
            // extension. Select by the requested schema, not just index zero.
            for (int index = 0;; ++index) {
                auto *candidate = QQmlPrivate::qmlExtendedObject(target, index);
                if (!candidate) break;
                if (candidate->metaObject()->inherits(state->extension->meta)) { value = candidate; break; }
            }
        }
    }
    else return fail(r, ENOTSUP, "The QML registration has no requested attached or extension type");
    if (!value) return fail(r, ENOENT, "Qt did not create the attached or extension object");
    auto expected = kind ? state->extension : state->attached;
    if (!value->metaObject()->inherits(expected->meta)) return fail(r, EINVAL, "Qt returned an incompatible related object");
    r->result.word = borrow(r, value, @QOBJECT_ID@);
    r->result.borrowed_handle = r->result.word;
    return true;
}
}
#endif
