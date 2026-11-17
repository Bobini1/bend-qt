namespace NativeFunctionCallbacks {
// Raw function pointers have no userdata. Each immutable executable stub
// supplies a distinct stable context. Code pages and tiny inactive contexts
// remain valid for native copies; their Bend handlers have separate lifetimes.
template<class Function> static Function closure(BqtRequest *r, void *context, void *target, bool two_pointer_arguments) {
    struct Slot { void *context = nullptr, *target = nullptr; };
    static_assert(sizeof(void *) == 8 && sizeof(Slot) == 16, "Native callback stubs require the Linux x86-64 ABI");
    struct Page { Slot *contexts; unsigned char *code; size_t used, count; };
    static auto *pages = new std::vector<Page>;
    if (pages->empty() || pages->back().used == pages->back().count) {
        long size = sysconf(_SC_PAGESIZE);
        if (size < 32) { fail(r, ENOSYS, "Cannot determine native callback page size"); return nullptr; }
        const size_t count = size_t(size) / 32;
        auto contexts = std::make_unique<Slot[]>(count);
        void *memory = mmap(nullptr, size_t(size), PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        if (memory == MAP_FAILED) { fail(r, errno, "Cannot allocate native callback closures"); return nullptr; }
        auto *code = static_cast<unsigned char *>(memory);
        // Stub addresses are fixed before publication. Their separate context
        // slots stay writable, so an executable page is never rewritten.
        std::memset(code, 0x90, size_t(size));
        for (size_t i = 0; i < count; ++i) {
            auto *stub = code + i * 32;
            size_t at = 0;
            const unsigned char entry[] = {0xf3, 0x0f, 0x1e, 0xfa};
            std::memcpy(stub + at, entry, sizeof(entry)); at += sizeof(entry);
            if (two_pointer_arguments) {
                const unsigned char shift[] = {0x48,0x89,0xf2, 0x48,0x89,0xfe};
                std::memcpy(stub + at, shift, sizeof(shift)); at += sizeof(shift);
            }
            stub[at++] = 0x49; stub[at++] = 0xbb; // movabs r11, slot
            auto pointer = reinterpret_cast<uintptr_t>(&contexts[i]);
            std::memcpy(stub + at, &pointer, sizeof(pointer)); at += sizeof(pointer);
            const unsigned char call[] = {0x49,0x8b,0x3b, 0x49,0x8b,0x43,0x08, 0xff,0xe0};
            std::memcpy(stub + at, call, sizeof(call));
        }
        if (mprotect(memory, size_t(size), PROT_READ | PROT_EXEC)) {
            int error = errno; munmap(memory, size_t(size));
            fail(r, error, "Cannot publish native callback code"); return nullptr;
        }
        try { pages->push_back(Page{contexts.get(), code, 0, count}); }
        catch (...) { munmap(memory, size_t(size)); throw; }
        contexts.release();
    }
    auto &page = pages->back(); const size_t index = page.used++;
    page.contexts[index] = Slot{context, target};
    return reinterpret_cast<Function>(page.code + index * 32);
}

#if @HAS_EASING@
struct EasingState {
    uint32_t handler = 0;
    std::shared_ptr<std::atomic<bool>> alive = std::make_shared<std::atomic<bool>>(true);
    QEasingCurve::EasingFunction function = nullptr;
};
static auto &easing_states() { static auto *values = new std::vector<std::unique_ptr<EasingState>>; return *values; }
struct EasingView { QEasingCurve::EasingFunction function; };
static void delete_easing_view(void *p) { delete static_cast<EasingView *>(p); }
static EasingView *easing_view(BqtRequest *r, uint32_t id) {
    auto *value = entry(id);
    if (!value || value->destroy != delete_easing_view) { fail(r, ESTALE, "The easing function view has expired"); return nullptr; }
    return static_cast<EasingView *>(value->value);
}
static uint32_t make_easing_view(BqtRequest *r, QEasingCurve::EasingFunction function) {
    if (!function) return 0;
    auto value = std::make_unique<EasingView>(EasingView{function});
    return insert(r, value.release(), nullptr, 0, delete_easing_view, true);
}
static bool decode_real(BqtRequest *r, const BqtValue &wire, void *destination) {
    if (!wire_shape(r, wire, 0)) return false;
    *static_cast<qreal *>(destination) = qreal(real_value(wire));
    return true;
}
static qreal easing_invoke(EasingState *state, qreal progress) noexcept {
    auto invoke = [&]() -> qreal {
        if (!state->alive->load(std::memory_order_acquire) || !state->handler || !bend) return 0;
        try {
            CallbackOwnedArguments arguments{sequence_value(1)};
            arguments.value.items[0] = real_bits(progress);
            qreal result = 0;
            int error = callback_invoke(state->handler, 0, arguments.take(), decode_real, &result);
            return error ? qreal(0) : result;
        } catch (const std::bad_alloc &) { callback_report_error(ENOMEM); }
          catch (...) { callback_report_error(EFAULT); }
        return 0;
    };
    try {
        if (QThread::currentThread() == main_thread) return invoke();
        return callback_from_thread<qreal>(state->alive, invoke, [] { return qreal(0); });
    } catch (...) { return 0; }
}
static bool easing_new(BqtRequest *r) {
    auto state = std::make_unique<EasingState>();
    state->function = closure<QEasingCurve::EasingFunction>(r, state.get(), reinterpret_cast<void *>(&easing_invoke), false);
    if (r->error) return true;
    auto *pointer = state.get();
    easing_states().push_back(std::move(state));
    uint32_t id = make_easing_view(r, pointer->function);
    if (r->error) return true;
    pointer->handler = r->arguments[0].word;
    r->result.word = id; r->result.owned_handle = id;
    return true;
}
static bool easing_release(BqtRequest *r) {
    if (!easing_view(r, r->self)) return true;
    return release_object(r);
}
static bool easing_call(BqtRequest *r) {
    NativeCallScope scope;
    auto *value = easing_view(r, r->self);
    if (!value) return true;
    scope.pin(r, r->self);
    r->result = real_bits(value->function(qreal(real_value(r->arguments[0]))));
    return true;
}
static bool easing_set(BqtRequest *r) {
    NativeCallScope scope;
    auto *curve = get<QEasingCurve>(r, r->self, @EASING_ID@);
    auto *function = easing_view(r, r->arguments[0].word);
    if (r->error) return true;
    curve->setCustomType(function->function);
    return true;
}
static bool easing_same(BqtRequest *r) {
    auto *left = easing_view(r, r->self);
    auto *right = easing_view(r, r->arguments[0].word);
    if (r->error) return true;
    r->result.word = left->function == right->function;
    return true;
}
static bool easing_get(BqtRequest *r) {
    NativeCallScope scope;
    auto *curve = get<QEasingCurve>(r, r->self, @EASING_ID@, false, false);
    if (r->error) return true;
    r->result.word = make_easing_view(r, curve->customType());
    r->result.owned_handle = r->result.word;
    return true;
}
#endif

#if @HAS_ACCESSIBLE@
struct AccessibleState {
    uint32_t handler = 0;
    std::shared_ptr<std::atomic<bool>> alive = std::make_shared<std::atomic<bool>>(true);
    QAccessible::InterfaceFactory function = nullptr;
};
struct CachedAccessible {
    uint32_t token = 0;
    QAccessible::Id cache = 0;
    bool (*previous)(BqtRequest *, uint32_t) = nullptr;
};
static auto &accessible_views() { static auto *values = new SlotTable<CachedAccessible>; return *values; }
static bool accessible_validate(BqtRequest *r, uint32_t id) {
    auto *record = entry(id);
    if (!record) {
        fail(r, ESTALE, "The accessible interface has expired"); return false;
    }
    auto &source = accessible_views()[id & 65535u];
    if (source.token != id) { fail(r, ESTALE, "The accessible interface has expired"); return false; }
    if (source.previous && !source.previous(r, id)) return false;
    record = entry(id);
    auto *pointer = record && record->cast ? static_cast<QAccessibleInterface *>(record->cast(record->value, @ACCESSIBLE_ID@)) : nullptr;
    if (!pointer || QAccessible::accessibleInterface(source.cache) != pointer) {
        source = {};
        if (record) invalidate(id);
        fail(r, ESTALE, "Qt removed the accessible interface from its cache"); return false;
    }
    return true;
}
static uint32_t accessible_borrow_impl(BqtRequest *r, QAccessibleInterface *value, bool writable) {
    if (!value) return 0;
    for (uint32_t i = 1; i < capacity; ++i) {
        auto &record = entries[i];
        if (record.value && record.cast && record.cast(record.value, @ACCESSIBLE_ID@) == value) {
            const uint32_t id = token(i, record.generation);
            if (record.validate == accessible_validate) {
                auto &source = accessible_views()[i];
                if (source.token != id || QAccessible::accessibleInterface(source.cache) != value) {
                    source = {};
                    invalidate(id);
                    continue;
                }
            }
            if (writable) record.read_only = false;
            return id;
        }
    }
    const auto cache = QAccessible::uniqueId(value);
    QObject *object = value->object();
    uint32_t owner = borrow(r, object ? object : application, @QOBJECT_ID@);
    if (r->error) return 0;
    uint32_t id = register_native_borrow(r, value, @ACCESSIBLE_ID@, owner);
    if (auto *record = entry(id); record && !writable) record->read_only = true;
    if (auto *record = entry(id); record && !record->native_observed) {
        if (record->validate != accessible_validate) {
            accessible_views()[id & 65535u] = CachedAccessible{id, cache, record->validate};
            record->validate = accessible_validate;
        }
    }
    return id;
}
static uint32_t accessible_borrow(BqtRequest *r, QAccessibleInterface *value) {
    return accessible_borrow_impl(r, value, true);
}
static uint32_t accessible_borrow(BqtRequest *r, const QAccessibleInterface *value) {
    // Qt's cache indexes interface identities through a mutable pointer. Its
    // registration does not establish mutable access to a const native view.
    return accessible_borrow_impl(r, const_cast<QAccessibleInterface *>(value), false);
}
static bool accessible_delete(BqtRequest *r) {
    const auto cache = QAccessible::Id(r->arguments[0].word);
    auto *pointer = QAccessible::accessibleInterface(cache);
    std::vector<uint32_t> aliases;
    if (pointer) {
        for (uint32_t i = 1; i < capacity; ++i) {
            auto &record = entries[i];
            if (!record.value || !record.cast || record.cast(record.value, @ACCESSIBLE_ID@) != pointer) continue;
            uint32_t id = token(i, record.generation);
            if (retained(id) || active_in_subtree(id)) return fail(r, EBUSY, "The accessible interface is retained by a native call or value");
            aliases.push_back(id);
        }
    }
    QAccessible::deleteAccessibleInterface(cache);
    for (auto id : aliases) {
        auto &source = accessible_views()[id & 65535u];
        if (source.token == id) source = {};
        if (entry(id)) invalidate(id);
    }
    return true;
}
static auto &accessible_states() { static auto *values = new std::vector<std::unique_ptr<AccessibleState>>; return *values; }
static void deactivate_accessible(AccessibleState *state) {
    if (!state->alive->exchange(false, std::memory_order_acq_rel)) return;
    QAccessible::removeFactory(state->function);
    callback_release_handler(std::exchange(state->handler, 0));
}
static void delete_accessible_registration(void *p) { deactivate_accessible(static_cast<AccessibleState *>(p)); }
static bool adopt_accessible(BqtRequest *r, uint32_t id, QAccessibleInterface *value, bool factory = true) {
    if (!id) return true;
    auto *record = entry(id);
    struct Rollback {
        uint32_t id, owner;
        bool owned, committed = false;
        std::vector<std::pair<uint32_t, Retention>> removed;
        ~Rollback() {
            if (committed) return;
            for (const auto &edge : removed) retentions[edge.first] = edge.second;
            if (auto *record = entry(id)) { record->native_owner = owner; record->owned = owned; }
        }
    } rollback{id, record->native_owner, record->owned};
    QObject *object = value->object();
    uint32_t owner = object ? borrow(r, object, @QOBJECT_ID@) : 0;
    if (r->error) return false;
    if (factory) {
        if (!callback_transfer_result(r, id)) return false;
    } else {
        if (!can_transfer_handle(r, id)) return false;
        if (record->read_only || !record->native_observed) {
            fail(r, ENOTSUP, "An accessible registration needs observable mutable ownership"); return false;
        }
        set_owned(id, false);
    }
    if (owner) {
        // Before transfer a wrapper keeps its referenced widget alive. Qt's
        // accessibility cache instead owns the interface until that QObject
        // dies. The old inverse dependency would prevent either from dying.
        // Retention slots start at 0, unlike entry tokens.
        for (uint32_t i = 0; i < capacity; ++i) {
            auto &edge = retentions[i];
            if (edge.owner == id && edge.target && entry_inside(owner, edge.target)) {
                rollback.removed.emplace_back(i, edge);
                edge = {};
            }
        }
        if (!set_native_owner(r, id, owner)) return false;
    }
    entry(id)->scope_owner = 0;
    rollback.committed = true;
    return true;
}
static bool accessible_register(BqtRequest *r) {
    NativeCallScope scope;
    const uint32_t id = r->arguments[0].word;
    auto *value = get<QAccessibleInterface>(r, id, @ACCESSIBLE_ID@, false, false);
    if (r->error) return true;
    if (entry(id)->owned && !adopt_accessible(r, id, value, false)) return true;
    r->result.word = QAccessible::uniqueId(value);
    return true;
}
static bool accessible_decode(BqtRequest *r, const BqtValue &wire, void *destination) {
    if (!wire_shape(r, wire, 0)) return false;
    auto *value = get<QAccessibleInterface>(r, wire.word, @ACCESSIBLE_ID@, true, false);
    if (r->error || !adopt_accessible(r, wire.word, value)) return false;
    *static_cast<QAccessibleInterface **>(destination) = value;
    return true;
}
static QAccessibleInterface *accessible_invoke(AccessibleState *state, const QString &key, QObject *object) noexcept {
    auto invoke = [&]() -> QAccessibleInterface * {
        if (!state->alive->load(std::memory_order_acquire) || !state->handler || !bend) return nullptr;
        try {
            NativeCallScope scope;
            BqtRequest conversion{};
            uint32_t id = borrow(&conversion, object, @QOBJECT_ID@);
            if (conversion.error) { callback_report_error(conversion.error, conversion.message); return nullptr; }
            CallbackOwnedArguments arguments{sequence_value(2)};
            arguments.value.items[0] = string_value(key);
            arguments.value.items[1].word = id;
            arguments.value.items[1].borrowed_handle = id;
            QAccessibleInterface *result = nullptr;
            int error = callback_invoke(state->handler, 0, arguments.take(), accessible_decode, &result);
            return error ? nullptr : result;
        } catch (const std::bad_alloc &) { callback_report_error(ENOMEM); }
          catch (...) { callback_report_error(EFAULT); }
        return nullptr;
    };
    try {
        if (QThread::currentThread() == main_thread) return invoke();
        return callback_from_thread<QAccessibleInterface *>(state->alive, invoke, [] { return static_cast<QAccessibleInterface *>(nullptr); });
    } catch (...) { return nullptr; }
}
static bool accessible_install(BqtRequest *r) {
    auto state = std::make_unique<AccessibleState>();
    state->function = closure<QAccessible::InterfaceFactory>(r, state.get(), reinterpret_cast<void *>(&accessible_invoke), true);
    if (r->error) return true;
    auto *pointer = state.get();
    accessible_states().push_back(std::move(state));
    uint32_t id = insert(r, pointer, nullptr, 0, delete_accessible_registration, true);
    if (r->error) return true;
    r->result.word = id; r->result.owned_handle = id;
    QAccessible::installFactory(pointer->function);
    pointer->handler = r->arguments[0].word;
    return true;
}
static bool accessible_remove(BqtRequest *r) {
    auto *value = entry(r->self);
    if (!value || value->destroy != delete_accessible_registration) return fail(r, ESTALE, "The accessibility factory registration has expired");
    return release_object(r);
}
#endif
static void shutdown() {
    uint32_t easing = 0, released = 0;
#if @HAS_EASING@
    for (const auto &state : easing_states()) {
        state->alive->store(false, std::memory_order_release);
        if (state->handler) { ++easing; callback_release_handler(std::exchange(state->handler, 0)); ++released; }
    }
#endif
#if @HAS_ACCESSIBLE@
    for (const auto &state : accessible_states()) deactivate_accessible(state.get());
#endif
    if (easing && std::getenv("BEND_QT_CHECK_SHUTDOWN"))
        std::fprintf(stdout, "QT612_EASING_CALLBACKS_SHUTDOWN retained=%u released=%u\n", easing, released);
}
} // namespace NativeFunctionCallbacks
static void native_function_callbacks_shutdown() { NativeFunctionCallbacks::shutdown(); }
