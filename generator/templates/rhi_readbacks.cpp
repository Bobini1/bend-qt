// A pending readback and the Bend handler Qt runs with its result. A batch
// released before submission cancels the readback: the handler never runs.
struct RhiReadbackPending {
    QRhiReadbackResult result{};
    std::shared_ptr<RhiDomain> domain;
    uint32_t batch = 0, handler = 0;
    bool finished = false, submitted = false, pinned = false;
    ~RhiReadbackPending() {
        if (pinned) callback_unpin(domain->id);
        callback_release_handler(handler);
    }
};
static auto &rhi_readbacks() { static auto *items = new std::vector<std::shared_ptr<RhiReadbackPending>>; return *items; }
static void rhi_sweep_readbacks() {
    auto &items = rhi_readbacks();
    items.erase(std::remove_if(items.begin(), items.end(), [](const auto &item) { return item->finished; }), items.end());
}
static void rhi_readback_finished(const std::shared_ptr<RhiReadbackPending> &state) {
    state->finished = true;
    if (state->pinned) { callback_unpin(state->domain->id); state->pinned = false; }
    // The backend's completed() call must finish before its result storage can
    // be reclaimed. The value given to the handler is independently owned.
    try {
        if (application) QTimer::singleShot(0, application, [] { rhi_sweep_readbacks(); });
    } catch (...) {
        // Posting is optional maintenance, and must not escape Qt's native
        // completion callback. Keep the finished storage until a later sweep
        // or rhi_finish_readbacks at owner destruction or teardown.
    }
}
static void rhi_cancel_readback(const std::shared_ptr<RhiReadbackPending> &state) {
    if (state->finished) return;
    rhi_readback_finished(state);
}
// Takes the handler: the pending readback owns it from here on.
static std::shared_ptr<RhiReadbackPending> rhi_new_readback(BqtRequest *r, uint32_t batch, uint32_t handler) {
    auto *identity = rhi_identity(batch);
    if (!identity || !identity->batch) { fail(r, ESTALE, "RHI readback batch expired"); return {}; }
    auto state = std::make_shared<RhiReadbackPending>();
    state->domain = identity->domain;
    state->batch = batch;
    if (!callback_pin(r, state->domain->id)) return {};
    state->pinned = true;
    std::weak_ptr<RhiReadbackPending> weak = state;
    state->result.completed = [weak] {
        auto state = weak.lock();
        if (!state || state->finished) return;
        try {
            auto copy = std::make_unique<QRhiReadbackResult>();
            copy->format = state->result.format;
            copy->pixelSize = state->result.pixelSize;
            copy->data = state->result.data;
            BqtRequest converted{};
            // Ready.invoke decodes one value rather than a signal tuple.
            CallbackOwnedArguments arguments{BqtValue{}};
            arguments.value.word = own(&converted, copy.release(), @QRHIREADBACKRESULT_ID@);
            arguments.value.owned_handle = arguments.value.word;
            if (converted.error) callback_report_error(converted.error, converted.message);
            else {
                int error = callback_invoke(state->handler, state->domain->id, arguments.take(), callback_decode_unit, nullptr);
                if (error) callback_report_error(error);
            }
        } catch (const std::bad_alloc &) { callback_report_error(ENOMEM, "RHI readback copy allocation failed"); }
          catch (...) { callback_report_error(EFAULT, "RHI readback copy failed"); }
        rhi_readback_finished(state);
    };
    rhi_readbacks().push_back(state);
    // Qt owns the handler only once the readback is registered.
    state->handler = handler;
    return state;
}
static void rhi_readback_forget(uint32_t id) {
    // Submission disarms this cancellation before the pooled batch identity is
    // revoked. A released or abandoned batch never owns a pending native read.
    for (const auto &state : rhi_readbacks()) if (!state->finished && !state->submitted && state->batch == id)
        rhi_cancel_readback(state);
}
static void rhi_batch_submitted(uint32_t id) {
    for (const auto &state : rhi_readbacks()) if (state->batch == id && !state->finished) state->submitted = true;
}
static void rhi_readbacks_merged(uint32_t target, uint32_t source) {
    for (const auto &state : rhi_readbacks()) if (state->batch == source && !state->finished) state->batch = target;
}
static void rhi_finish_readbacks(const std::shared_ptr<RhiDomain> &domain) {
    bool pending = false;
    for (const auto &state : rhi_readbacks()) if (state->domain == domain && state->submitted && !state->finished) pending = true;
    if (pending && domain->alive) domain->rhi->finish();
    rhi_sweep_readbacks();
}
