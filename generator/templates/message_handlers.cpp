// qInstallMessageHandler is process-global and Qt may log on any thread. A
// Bend handler receives the messages logged on the main thread; the others,
// and any message logged while the handler runs, go to the previous handler.
struct MessageHandlerState {
    QMutex mutex;
    bool installed = false;
    uint32_t handler = 0;
    QtMessageHandler previous = nullptr;
    std::atomic<int> last_error{0};
};
static auto &message_handler_state()
{ static auto *state = new MessageHandlerState; return *state; }

static void message_handler_fallback(QtMessageHandler previous, QtMsgType type,
                                    const QMessageLogContext &context, const QString &message) noexcept
{
    try {
        if (previous) { previous(type, context, message); return; }
        auto bytes = qFormatLogMessage(type, context, message).toUtf8();
        std::fwrite(bytes.constData(), 1, size_t(bytes.size()), stderr);
        std::fputc('\n', stderr);
        std::fflush(stderr);
    } catch (...) {
        std::fputs("Qt message handler failed while formatting native fallback\n", stderr);
    }
}

static BqtValue message_context_text(const char *value)
{
    BqtValue result = sequence_value(value ? 1 : 0);
    if (value) result.items[0] = string_value(QString::fromUtf8(value));
    return result;
}

static void message_handler_native(QtMsgType type, const QMessageLogContext &context,
                                   const QString &message) noexcept
{
    auto &state = message_handler_state();
    uint32_t handler;
    QtMessageHandler previous;
    { QMutexLocker lock(&state.mutex); handler = state.installed ? state.handler : 0; previous = state.previous; }
    static thread_local bool active;
    if (!handler || active || !bend || QThread::currentThread() != main_thread) {
        message_handler_fallback(previous, type, context, message);
        return;
    }
    active = true;
    struct Guard { bool &active; ~Guard() { active = false; } } guard{active};
    try {
        // The message is copied: a handler never borrows Qt's context strings.
        CallbackOwnedArguments arguments{sequence_value(7)};
        arguments.value.items[0].word = uint32_t(type);
        arguments.value.items[1] = string_value(message);
        arguments.value.items[2] = message_context_text(context.category);
        arguments.value.items[3] = message_context_text(context.file);
        arguments.value.items[4].word = uint32_t(context.line);
        arguments.value.items[5] = message_context_text(context.function);
        arguments.value.items[6].word = uint32_t(context.version);
        // Logging is diagnostic, not a result of the Qt operation in progress:
        // a failed handler is recorded here and never fails that operation.
        int error = callback_invoke(handler, 0, arguments.take(), callback_decode_unit, nullptr, false);
        if (!error) return;
        state.last_error.store(error, std::memory_order_release);
    } catch (const std::bad_alloc &) { state.last_error.store(ENOMEM, std::memory_order_release); }
      catch (...) { state.last_error.store(EFAULT, std::memory_order_release); }
    message_handler_fallback(previous, type, context, message);
}

static bool message_handler_install(BqtRequest *r)
{
    auto &state = message_handler_state();
    QMutexLocker lock(&state.mutex);
    if (state.installed) return fail(r, EBUSY, "A Bend Qt message handler is already installed");
    state.handler = r->arguments[0].word;
    state.last_error.store(0, std::memory_order_release);
    state.previous = qInstallMessageHandler(message_handler_native);
    state.installed = true;
    return true;
}

// Gives Qt its previous handler back. Answers the Bend handler to release.
static uint32_t message_handler_remove()
{
    auto &state = message_handler_state();
    QMutexLocker lock(&state.mutex);
    if (!state.installed) return 0;
    qInstallMessageHandler(state.previous);
    state.installed = false;
    return std::exchange(state.handler, 0);
}

static bool message_handler_restore(BqtRequest *r)
{
    auto handler = message_handler_remove();
    if (!handler) return fail(r, ESTALE, "No Bend Qt message handler is installed");
    callback_release_handler(handler);
    return true;
}

static void message_handler_shutdown()
{
    message_handler_remove();
}

static bool message_handler_status(BqtRequest *r)
{
    r->result.word = uint32_t(message_handler_state().last_error.load(std::memory_order_acquire));
    return true;
}

static bool message_read_context(BqtRequest *r, const BqtValue &wire, std::optional<QByteArray> &value)
{
    if (!wire_shape(r, wire, 2)) return false;
    if (wire.count > 1) { fail(r, EINVAL, "Invalid optional log context string"); return false; }
    if (!wire.count) return true;
    if (!wire_shape(r, wire.items[0], 1)) return false;
    value.emplace(wire.items[0].text, qsizetype(wire.items[0].size));
    if (value->contains('\0')) { fail(r, EINVAL, "Qt log context strings cannot contain NUL"); return false; }
    return true;
}

static bool message_handler_format(BqtRequest *r)
{
    const auto &wire = r->arguments[0];
    if (!wire_shape(r, wire, 2, 7) || !wire_shape(r, wire.items[0], 0) ||
        !wire_shape(r, wire.items[1], 1) || !wire_shape(r, wire.items[4], 0) || !wire_shape(r, wire.items[6], 0)) return true;
    if (wire.items[0].word > uint32_t(QtInfoMsg)) return fail(r, EINVAL, "Unknown Qt message type");
    std::optional<QByteArray> category, file, function;
    if (!message_read_context(r, wire.items[2], category) || !message_read_context(r, wire.items[3], file) ||
        !message_read_context(r, wire.items[5], function)) return true;
    QMessageLogContext context(file ? file->constData() : nullptr, int32_t(wire.items[4].word),
                               function ? function->constData() : nullptr, category ? category->constData() : nullptr);
    context.version = int32_t(wire.items[6].word);
    auto text = QString::fromUtf8(wire.items[1].text, qsizetype(wire.items[1].size));
    r->result = string_value(qFormatLogMessage(QtMsgType(wire.items[0].word), context, text));
    return true;
}
