namespace PostRoutines {
struct State {
    uint32_t handler = 0;
    uint32_t view = 0;
    QtCleanUpFunction function = nullptr;
    bool registered = false;
};
struct View { State *state; };
static auto &states() { static auto *values = new std::vector<std::unique_ptr<State>>; return *values; }
static const BqtHost *shutdown_host;
static int shutdown_error;

static void cancel(State &state) {
    if (state.registered) qRemovePostRoutine(state.function);
    state.registered = false;
    auto handler = std::exchange(state.handler, 0);
    callback_release_handler(handler);
}
static void delete_view(void *pointer) {
    std::unique_ptr<View> view(static_cast<View *>(pointer));
    view->state->view = 0;
    cancel(*view->state);
}
// A distinct decoder requires the handler to finish and acknowledge its call.
// A cleanup callback cannot wait for a running Qt application during its dtor.
static bool decode_done(BqtRequest *r, const BqtValue &wire, void *) {
    return wire_shape(r, wire, 0);
}
static void invoke(State *state) noexcept {
    if (!state->registered) return;
    state->registered = false;
    const uint32_t handler = std::exchange(state->handler, 0);
    if (state->view) {
        auto *record = entry(state->view);
        if (record && record->destroy == delete_view) {
            auto *view = static_cast<View *>(record->value);
            // Qt runs post routines from the application destructor, inside a
            // native destruction scope where invalidate() defers. The view is
            // a registration record, not a native object, and is deleted
            // here, so its handle ends now rather than at the scope's flush.
            invalidate_now(state->view);
            delete view;
        }
        state->view = 0;
    }
    const BqtHost *previous = bend;
    if (!bend) bend = shutdown_host;
    try {
        int error = callback_invoke(handler, 0, sequence_value(0), decode_done, nullptr);
        if (error && !shutdown_error) shutdown_error = error;
    } catch (const std::bad_alloc &) { if (!shutdown_error) shutdown_error = ENOMEM; }
      catch (...) { if (!shutdown_error) shutdown_error = EFAULT; }
    callback_release_handler(handler);
    bend = previous;
}
static bool add(BqtRequest *r) {
    if (!application && !shutdown_host)
        return fail(r, ESHUTDOWN, "The Qt application has ended");
    auto state = std::make_unique<State>();
    state->function = NativeFunctionCallbacks::closure<QtCleanUpFunction>(r, state.get(), reinterpret_cast<void *>(&invoke), false);
    if (r->error) return true;
    auto view = std::make_unique<View>(View{state.get()});
    // Stable tombstones keep every published native function pointer valid.
    auto *value = state.get();
    states().push_back(std::move(state));
    auto *published = view.release();
    try { value->view = insert(r, published, nullptr, 0, delete_view, true); }
    catch (...) { delete_view(published); throw; }
    if (r->error) return true;
    try { qAddPostRoutine(value->function); }
    catch (...) {
        invalidate(value->view);
        delete_view(published);
        throw;
    }
    value->handler = r->arguments[0].word;
    value->registered = true;
    // qAddPostRoutine registers application-wide cleanup. Ending the Action
    // that registered it must not silently cancel it; .with/remove opt into
    // earlier cancellation. Its original scope's resource record is now inert.
    if (auto *record = entry(value->view)) record->scope_owner = 0;
    r->result.word = value->view;
    r->result.owned_handle = value->view;
    return true;
}
static bool remove(BqtRequest *r) {
    auto *value = entry(r->self);
    if (!value || value->destroy != delete_view)
        return fail(r, ESTALE, "The Qt cleanup registration has ended");
    return release_object(r);
}
}

static bool post_routines_entry(const Entry &entry) {
    return entry.destroy == PostRoutines::delete_view;
}
static void post_routines_prepare() {
    PostRoutines::shutdown_host = bend;
    PostRoutines::shutdown_error = 0;
}
static int post_routines_shutdown() {
    const BqtHost *previous = bend;
    bend = PostRoutines::shutdown_host;
    for (auto &state : PostRoutines::states()) {
        PostRoutines::cancel(*state);
        if (state->view) {
            auto *record = entry(state->view);
            if (record && record->destroy == PostRoutines::delete_view) {
                auto *value = record->value;
                invalidate(state->view);
                PostRoutines::delete_view(value);
            }
            state->view = 0;
        }
    }
    callback_drain_released();
    bend = previous;
    PostRoutines::shutdown_host = nullptr;
    return PostRoutines::shutdown_error;
}
