// Qt calls Bend: a connected signal, an overridden virtual method or a stored
// function runs a Bend handler. The handler runs on the main thread, on Qt's
// own stack, and Qt has its answer before the native call returns.

// One handler invocation in progress. Invocations nest: a handler may call Qt,
// which may call another handler.
static bool render_factory_consumable(uint32_t);
static bool render_factory_handoff(BqtRequest *, uint32_t, uint32_t, bool);
static uint32_t render_factory_restore(BqtRequest *, const void *, uint16_t, uint32_t);
struct PendingFactoryResult { uint32_t id; bool render_node; };
struct CallbackFrame {
    BqtValue arguments;
    bool (*decode)(BqtRequest *, const BqtValue &, void *);
    void *destination;
    uint32_t receiver;
    // Objects named by the handler's answer stay checked until Qt has it.
    NativeCallScope *answer = nullptr;
    bool answered = false;
    int error = 0;
    std::vector<PendingFactoryResult> pending_factory_results;
};
// Calls use the same 16-bit slot/generation format as object handles. Grow
// stable slots for nested calls, and retire exhausted generations rather than
// allowing an expired answer token to identify a later call.
struct CallbackSlot {
    CallbackFrame *frame;
    uint32_t generation;
};
static std::deque<CallbackSlot> callback_slots(256);
static uint32_t callback_token(uint32_t index, uint32_t generation) { return generation << 16 | index; }

// The failure belongs to the Bend-started Qt operation that is running now.
static void callback_report_error(int error, const char *text = nullptr)
{
    if (!error) return;
    if (!text) text = "A Qt call into Bend failed";
    if (CallFrame::current) CallFrame::current->handler_failed(error, text);
    else std::fprintf(stderr, "bend-qt: %s (error %d) outside a Qt operation\n", text, error);
}

// Snapshot signal inputs on the emitting thread, but convert and invoke only
// on main. Reply signals keep their caller waiting for the native outputs.
static bool callback_connection_type(BqtRequest *r, uint32_t type, bool functor = true) {
    if (type & ~uint32_t(3 | Qt::UniqueConnection | Qt::SingleShotConnection)) {
        fail(r, EINVAL, "Invalid Qt connection type"); return false;
    }
    if (functor && (type & Qt::UniqueConnection)) {
        fail(r, EINVAL, "Qt UniqueConnection requires a QObject method or signal receiver"); return false;
    }
    return true;
}
template<class Function> static bool callback_signal_call_with_type(uint32_t id, Function &&call, uint32_t type, bool reply)
{
    const uint32_t mode = type & 3u;
    const bool on_main = QThread::currentThread() == main_thread;
    if (mode == Qt::BlockingQueuedConnection && on_main) {
        callback_report_error(EDEADLK, "A blocking queued signal cannot wait for its own Bend thread");
        return false;
    }
    if (reply && mode == Qt::QueuedConnection) {
        callback_report_error(ENOTSUP, "A mutable signal reply cannot be delivered asynchronously");
        return false;
    }
    auto deliver = [id, type, call = std::forward<Function>(call)]() mutable {
        // A queued emission may outlive disconnect and reuse of its slot.
        if (!connection(id)) return;
        struct Finish {
            uint32_t id, type;
            ~Finish() { if (type & Qt::SingleShotConnection) if (auto *value = connection(id)) close_connection(*value); }
        } finish{id, type};
        call();
    };
    if (on_main && mode != Qt::QueuedConnection) {
        deliver();
        return true;
    }
    auto *context = main_context.load(std::memory_order_acquire);
    return context && QMetaObject::invokeMethod(context, std::move(deliver),
        reply || (!on_main && (mode == Qt::DirectConnection || mode == Qt::BlockingQueuedConnection))
            ? Qt::BlockingQueuedConnection : Qt::QueuedConnection);
}
template<class Function> static bool callback_signal_call(uint32_t id, Function &&call, bool reply)
{
    return callback_signal_call_with_type(id, std::forward<Function>(call), Qt::AutoConnection, reply);
}

static void callback_signal_error(uint32_t id, int error) noexcept
{
    try {
        if (callback_signal_call(id, [error] {
            try { callback_report_error(error); }
            catch (...) { std::fprintf(stderr, "bend-qt: signal handler failed (error %d)\n", error); }
        }, false)) return;
    } catch (...) {}
    std::fprintf(stderr, "bend-qt: cannot deliver signal error %d\n", error);
}

static CallbackFrame *callback_frame(uint32_t id)
{
    const uint32_t i = id & 65535u;
    if (!i || i >= callback_slots.size()) return nullptr;
    auto &s = callback_slots[i];
    return s.frame && s.generation == id >> 16 ? s.frame : nullptr;
}

// The stack frame owns native copies until the native call returns. The wire
// copy delivered to Bend never duplicates that ownership claim. A handler may
// copy a value explicitly to keep it beyond this invocation.
static BqtValue callback_wire_copy(const BqtValue &source)
{
    BqtValue result = source;
    result.owned_handle = 0;
    result.owned_data = 0;
    result.items = nullptr;
    result.text = nullptr;
    if (source.text) {
        result.text = static_cast<char *>(std::malloc(source.size + 1));
        if (!result.text) std::abort();
        std::memcpy(result.text, source.text, source.size);
        result.text[source.size] = 0;
    }
    if (source.count) {
        result.items = static_cast<BqtValue *>(std::calloc(source.count, sizeof(BqtValue)));
        if (!result.items) std::abort();
        for (size_t i = 0; i < source.count; ++i) result.items[i] = callback_wire_copy(source.items[i]);
    }
    return result;
}

static void callback_wire_free(BqtValue &value)
{
    for (size_t i = 0; i < value.count; ++i) callback_wire_free(value.items[i]);
    std::free(value.items);
    std::free(value.text);
    value = {};
}

// The handler answers from inside the scope that owns its result, so the
// native value is copied or adopted before that scope ends.
static bool callback_resolve(BqtRequest *r)
{
    auto *frame = callback_frame(r->self);
    if (!frame) return fail(r, ESTALE, "Qt is no longer waiting for this answer");
    if (frame->answered) return fail(r, EALREADY, "This Qt call already has its answer");
    // Transfer checks during decoding must not see the answer's own pins.
    std::vector<uint32_t> named;
    {
        NativeCallScope decoding;
        decoding.noting = true;
        if (!frame->decode(r, r->arguments[0], frame->destination)) {
            if (!r->error) fail(r, EINVAL, "Malformed answer to a Qt call");
            frame->error = r->error;
            return true;
        }
        named.swap(decoding.pins);
    }
    for (auto id : named) frame->answer->pin(r, id);
    if (r->error) { frame->error = r->error; return true; }
    frame->answered = true;
    return true;
}

struct CallbackArgumentPins {
    std::vector<uint32_t> ids;
    void collect(BqtRequest *r, const BqtValue &value) {
        for (uint32_t id : {value.owned_handle, value.borrowed_handle}) {
            if (!id) continue;
            bool exists = false;
            for (auto prior : ids) if (prior == id) { exists = true; break; }
            if (!exists) {
                ids.push_back(id);
                if (!callback_pin(r, id)) ids.pop_back();
            }
        }
        for (size_t i = 0; i < value.count; ++i) collect(r, value.items[i]);
    }
    void release() { for (auto id : ids) callback_unpin(id); ids.clear(); }
    ~CallbackArgumentPins() { release(); }
};

struct CallbackOwnedArguments {
    BqtValue value;
    static void mark(const BqtValue &item) {
        if (item.owned_handle) mark_callback_ephemeral_value(item.owned_handle);
        for (size_t i = 0; i < item.count; ++i) mark(item.items[i]);
    }
    static void finish(const BqtValue &item) {
        if (item.owned_handle) finish_callback_ephemeral_value(item.owned_handle);
        for (size_t i = 0; i < item.count; ++i) finish(item.items[i]);
    }
    ~CallbackOwnedArguments() { finish(value); discard_value(value); }
    BqtValue take() { auto result = value; value = {}; return result; }
};

struct CallbackReceiverPin {
    uint32_t receiver;
    ~CallbackReceiverPin() { if (receiver) callback_unpin(receiver); }
};

struct CallbackSlotRegistration {
    CallbackSlot &slot;
    ~CallbackSlotRegistration() { slot.frame = nullptr; }
};

static bool callback_decode_unit(BqtRequest *r, const BqtValue &wire, void *)
{ return wire_shape(r, wire, 0); }

// Runs `handler` for `receiver` (0 when there is no live receiver). Answers
// 0, or an errno value: ENOSYS asks for the C++ base implementation. Unless
// `report` is false, any other failure also fails the Qt operation Bend
// started, since Qt itself cannot carry a handler's failure.
static int callback_invoke(uint32_t handler, uint32_t receiver, BqtValue arguments,
                           bool (*decode)(BqtRequest *, const BqtValue &, void *), void *destination,
                           bool report = true)
{
    CallbackOwnedArguments owned_arguments{arguments};
    CallbackOwnedArguments::mark(arguments);
    // Callers bring calls from other threads to the main thread first.
    if (!bend || QThread::currentThread() != main_thread) return EXDEV;
    BqtRequest pin{};
    if (receiver && !callback_pin(&pin, receiver)) return pin.error;
    CallbackReceiverPin receiver_pin{receiver};
    CallbackArgumentPins argument_pins;
    argument_pins.collect(&pin, arguments);
    if (pin.error) return pin.error;
    uint32_t slot_index = 0;
    for (uint32_t i = 1; i < callback_slots.size(); ++i) {
        auto &slot = callback_slots[i];
        if (slot.frame || slot.generation == UINT16_MAX) continue;
        slot_index = i;
        ++slot.generation;
        break;
    }
    if (!slot_index && callback_slots.size() < slot_limit) {
        slot_index = uint32_t(callback_slots.size());
        callback_slots.resize(std::min(slot_index * 2, slot_limit));
        callback_slots[slot_index].generation = 1;
    }
    if (!slot_index) {
        if (report) callback_report_error(ENOSPC, "Qt callback token space is exhausted");
        return ENOSPC;
    }
    NativeCallScope answer_scope;
    CallbackFrame frame{arguments, decode, destination, receiver, &answer_scope};
    auto &slot = callback_slots[slot_index];
    slot.frame = &frame;
    CallbackSlotRegistration registration{slot};
    BqtValue request = sequence_value(2);
    request.items[0].word = callback_token(slot_index, slot.generation);
    request.items[1] = callback_wire_copy(arguments);
    const char *text = nullptr;
    int status = bend->invoke(handler, &request, &text);
    callback_wire_free(request);
    int error = 0;
    const bool needs_answer = decode != callback_decode_unit;
    if (status == BQT_HANDLER_WAITS) {
        // The handler continues as an ordinary Bend computation. A signal
        // needs nothing more; a method that must return a value cannot wait.
        if (needs_answer && !frame.answered) {
            error = EWOULDBLOCK;
            text = "A Bend handler waited before answering Qt";
        }
    } else if (status != BQT_HANDLER_DONE) {
        error = status;
    } else if (frame.error) {
        error = frame.error;
    } else if (needs_answer && !frame.answered) {
        error = ENODATA;
        text = "A Bend handler finished without answering Qt";
    }
    // A raw native factory allocation has no destructor observer. Its answer
    // pins keep it owned while the handler's cleanup runs. Commit its domain
    // transfer only after a successful answer, before those pins unwind.
    if (!error) {
        for (const auto &result : frame.pending_factory_results) {
            BqtRequest transfer{};
            if (!render_factory_handoff(&transfer, result.id, receiver, result.render_node)) {
                error = transfer.error ? transfer.error : EINVAL;
                text = transfer.message ? transfer.message : "The native factory result could not be handed to Qt";
                break;
            }
        }
    }
    if (report && error && error != ENOSYS) callback_report_error(error, text);
    return error;
}

// Handlers installed on one override object. Qt may call a virtual method on
// any thread, so lookups are guarded.
struct CallbackHandlers {
    mutable QMutex mutex;
    std::vector<std::pair<uint32_t, uint32_t>> rows;
    bool (*accepts)(uint32_t) = nullptr;
    uint32_t find(uint32_t method) const {
        QMutexLocker lock(&mutex);
        for (const auto &row : rows) if (row.first == method) return row.second;
        return 0;
    }
    // Answers the handler this one replaces.
    uint32_t set(uint32_t method, uint32_t handler) {
        QMutexLocker lock(&mutex);
        for (auto &row : rows)
            if (row.first == method) { auto previous = row.second; row.second = handler; return previous; }
        rows.emplace_back(method, handler);
        return 0;
    }
    std::vector<uint32_t> take() {
        QMutexLocker lock(&mutex);
        std::vector<uint32_t> result;
        for (const auto &row : rows) result.push_back(row.second);
        rows.clear();
        return result;
    }
};

// Bend's handler table changes only on the main thread. A handler dropped on
// another thread waits here for the next main-thread pass.
static auto &callback_released()
{
    // A trivial static pointer avoids static-destruction order hazards.
    static auto *state = new std::pair<QMutex, std::vector<uint32_t>>;
    return *state;
}

static void callback_drain_released()
{
    std::vector<uint32_t> handlers;
    {
        auto &state = callback_released();
        QMutexLocker lock(&state.first);
        handlers.swap(state.second);
    }
    if (bend) for (auto handler : handlers) bend->release(handler);
}

static void callback_release_handler(uint32_t handler)
{
    if (!handler) return;
    if (QThread::currentThread() == main_thread) {
        if (bend) bend->release(handler);
        return;
    }
    auto &state = callback_released();
    QMutexLocker lock(&state.first);
    state.second.push_back(handler);
}

// The handler Bend installs for one virtual method of an override object.
static bool callback_install(BqtRequest *r)
{
    auto *e = entry(r->self);
    if (!e) return fail(r, ESTALE, "Invalid or destroyed Qt object handle");
    if (!e->handlers) return fail(r, EINVAL, "Only an object made by newOverride runs Bend handlers");
    uint32_t method = r->arguments[0].word, handler = r->arguments[1].word;
    if (!e->handlers->accepts || !e->handlers->accepts(method))
        return fail(r, ENOTSUP, "This override class does not forward that virtual method");
    callback_release_handler(e->handlers->set(method, handler));
    return true;
}

// Registers what a new override object needs: its liveness flag, which its
// destructor clears on whatever thread Qt destroys it, and its handlers.
static void callback_observe(uint32_t id, const std::shared_ptr<std::atomic<bool>> &alive, CallbackHandlers *handlers)
{
    auto *e = entry(id);
    if (!e) return;
    auto slot = std::make_unique<std::shared_ptr<std::atomic<bool>>>(alive);
    // A QObject already has a flag for its destroyed signal; the proxy's own
    // destructor runs earlier and is the one that matters for its virtuals.
    delete e->alive;
    e->alive = slot.release();
    e->proxy = true;
    e->handlers = handlers;
}

static void callback_proxy_destroyed(uint32_t id, const std::shared_ptr<std::atomic<bool>> &alive, CallbackHandlers &handlers)
{
    alive->store(false, std::memory_order_release);
    for (auto handler : handlers.take()) callback_release_handler(handler);
    if (!id) return;
    if (QThread::currentThread() == main_thread) {
        if (auto *e = entry(id)) { e->handlers = nullptr; e->destroying = true; }
    }
    // NativeDeletionObserver invalidates only after the native base destructor.
}

// Bend runs on the main thread only. A virtual method Qt calls on another
// thread is run there instead, while the calling thread waits. The main
// thread must be inside a Qt event loop to take the call; a main thread that
// is itself waiting for the caller never does.
template<class Function> static bool callback_on_main(const std::shared_ptr<std::atomic<bool>> &alive, Function &&call)
{
    auto *context = main_context.load(std::memory_order_acquire);
    if (!context) return false;
    bool ran = false;
    const bool delivered = QMetaObject::invokeMethod(context, [&] {
        if (!alive->load(std::memory_order_acquire)) return;
        call();
        ran = true;
    }, Qt::BlockingQueuedConnection);
    return delivered && ran;
}

// The same, for any result type: `fallback` supplies the result when the main
// thread cannot take the call or the object is already gone.
template<class R, class Call, class Fallback>
static R callback_from_thread(const std::shared_ptr<std::atomic<bool>> &alive, Call &&call, Fallback &&fallback)
{
    if constexpr (std::is_void_v<R>) {
        if (!callback_on_main(alive, call)) fallback();
    } else if constexpr (std::is_reference_v<R>) {
        std::remove_reference_t<R> *result = nullptr;
        if (!callback_on_main(alive, [&] { result = &call(); }) || !result) return fallback();
        return static_cast<R>(*result);
    } else {
        std::optional<R> result;
        if (!callback_on_main(alive, [&] { result.emplace(call()); }) || !result) return fallback();
        return std::move(*result);
    }
}

static void connection_terminal(Connection &c, uint32_t identity)
{
    auto handler = c.handler;
    if (!handler) return;
    try {
        CallbackOwnedArguments arguments{sequence_value(1)};
        arguments.value.items[0].word = identity;
        int error = callback_invoke(handler, 0, arguments.take(), callback_decode_unit, nullptr);
        if (error) callback_report_error(error);
    } catch (const std::bad_alloc &) { callback_report_error(ENOMEM); }
      catch (...) { callback_report_error(EFAULT); }
}

// A Bend handler held by a function object Qt owns.
struct CallbackFunctionHandler {
    uint32_t handler;
    explicit CallbackFunctionHandler(uint32_t value) : handler(value) {}
    CallbackFunctionHandler(const CallbackFunctionHandler &) = delete;
    ~CallbackFunctionHandler() { callback_release_handler(handler); }
};

// The liveness flag of the object a stored function belongs to.
static std::shared_ptr<std::atomic<bool>> callback_source_alive(uint32_t id)
{
    auto *e = entry(id);
    return e && e->alive ? *e->alive : std::make_shared<std::atomic<bool>>(true);
}

// Undoes a signal connection that failed half way. Bend still owns the
// handler of a call that fails.
struct CallbackConnectionGuard {
    uint32_t id = 0;
    bool keep = false;
    ~CallbackConnectionGuard() {
        if (keep) return;
        if (auto *c = connection(id)) { c->handler = 0; close_connection(*c); }
    }
};

template<class T> struct CallbackConstruction {
    T *value;
    uint32_t handle = 0;
    ~CallbackConstruction() {
        // Retention rollback may already have destroyed the new instance.
        if (value && (!handle || entry(handle))) {
            if constexpr (std::is_base_of_v<RuntimeObjectHost, T>)
                if (runtime_pending_placement && runtime_pending_placement->object == value) return;
            delete value;
        }
    }
    void release() { value = nullptr; }
};

// A typesystem may remove an internal pure virtual entirely from extraction.
// Keep such a class compilable and reject construction explicitly; never try
// to instantiate an abstract proxy based only on the extracted method list.
template<class T, class... Args> static T *callback_construct(BqtRequest *r, Args&&... args)
{
    if constexpr (std::is_abstract_v<T>) {
        fail(r, ENOTSUP, "Qt has an unextracted pure virtual in this override base");
        return nullptr;
    } else {
        if constexpr (std::is_base_of_v<RuntimeObjectHost, T>) {
            auto *pending = runtime_pending_placement;
            if (pending && !pending->claimed && runtime_construction_placement && pending->schema == runtime_construction_meta && pending->base == T::bqt_native_base) {
                pending->claimed = true;
                auto *value = new(pending->memory) T(std::forward<Args>(args)...);
                pending->object = value;
                return value;
            }
        }
        return new T(std::forward<Args>(args)...);
    }
}

template<class T, class... Args> static QSharedPointer<T> callback_construct_shared(BqtRequest *r, Args&&... args)
{
    if constexpr (std::is_abstract_v<T>) {
        fail(r, ENOTSUP, "Qt has an unextracted pure virtual in this shared override base");
        return {};
    } else {
        return QSharedPointer<T>::create(std::forward<Args>(args)...);
    }
}

struct CallbackOwnedRegistration {
    uint32_t handle;
    ~CallbackOwnedRegistration() {
        if (handle) { BqtValue wire{}; wire.owned_handle = handle; discard_value(wire); }
    }
    void release() { handle = 0; }
};
