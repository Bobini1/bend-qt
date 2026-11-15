static GLsync checked_gl_sync(BqtRequest *r, uint32_t id)
{
    if (!check_graphics_context(r)) return nullptr;
    if (!id) return nullptr;
    auto *value = get<QOpenGLSync>(r, id, @SYNC_TYPE@, false, false);
    if (r->error) return nullptr;
    auto *context = QOpenGLContext::currentContext();
    if (!value->group || !value->value) { fail(r, ESTALE, "OpenGL synchronization object was destroyed"); return nullptr; }
    if (context->shareGroup() != value->group) { fail(r, EXDEV, "OpenGL synchronization object belongs to another share group"); return nullptr; }
    return value->value;
}

static uint32_t own_gl_sync(BqtRequest *r, GLsync native)
{
    if (!native) { fail(r, EIO, "OpenGL could not create a synchronization object"); return 0; }
    auto *context = QOpenGLContext::currentContext();
    QOpenGLSync *value = nullptr;
    try { value = new QOpenGLSync(native, context->shareGroup()); }
    catch (...) { context->extraFunctions()->glDeleteSync(native); throw; }
    const auto id = own(r, value, @SYNC_TYPE@);
    if (!id) return 0;
    try {
        QObject::connect(context->shareGroup(), &QObject::destroyed, application, [id] {
            auto *e = entry(id);
            if (!e) return;
            auto *storage = static_cast<QOpenGLSync *>(e->value);
            storage->value = nullptr; // The last native share-group context freed it.
            invalidate(id);
            delete storage;
        });
    } catch (...) {
        auto *e = entry(id);
        if (e) { invalidate(id); delete value; }
        throw;
    }
    return id;
}

static bool delete_gl_sync(BqtRequest *r, uint32_t id)
{
    NativeDispatchIsolation isolation; // The explicit destroy must see outstanding wait pins.
    checked_gl_sync(r, id);
    if (r->error) return true;
    if (!id) { QOpenGLContext::currentContext()->extraFunctions()->glDeleteSync(nullptr); return true; }
    BqtRequest cleanup{};
    cleanup.self = id;
    destroy_object(&cleanup);
    if (cleanup.error) fail(r, cleanup.error, cleanup.message);
    return true;
}

struct GlSyncWait {
    uint32_t sync_id = 0, context_id = 0, surface_id = 0;
    QPointer<QOpenGLContext> context;
    QPointer<QObject> surface_guard;
    QSurface *surface = nullptr;
    QElapsedTimer elapsed;
    uint64_t timeout = 0;
    GLbitfield flags = 0;
    GLenum status = GL_TIMEOUT_EXPIRED;
    bool waited = false;
    ~GlSyncWait() {
        if (sync_id) callback_unpin(sync_id);
        if (context_id) callback_unpin(context_id);
        if (surface_id) callback_unpin(surface_id);
    }
    bool poll(BqtRequest *r) {
        if (!context || !surface_guard || !entry(sync_id)) {
            fail(r, ESTALE, "OpenGL wait lost its synchronization object or context surface"); return true;
        }
        QPointer<QOpenGLContext> previous = QOpenGLContext::currentContext();
        QSurface *previous_surface = previous ? previous->surface() : nullptr;
        QPointer<QObject> previous_guard = previous_surface ? dynamic_cast<QObject *>(previous_surface) : nullptr;
        const bool switch_context = previous != context || previous_surface != surface;
        if (switch_context && !context->makeCurrent(surface)) {
            fail(r, EIO, "OpenGL wait could not restore its context"); return true;
        }
        auto *stored = static_cast<QOpenGLSync *>(entry(sync_id)->value);
        status = context->extraFunctions()->glClientWaitSync(stored->value, flags, 0);
        flags = 0;
        if (switch_context) {
            if (previous && previous_guard) {
                if (!previous->makeCurrent(previous_surface)) fail(r, EIO, "OpenGL wait could not restore the previous context");
            } else context->doneCurrent();
        }
        if (waited && status == GL_ALREADY_SIGNALED) status = GL_CONDITION_SATISFIED;
        if (r->error || status != GL_TIMEOUT_EXPIRED) return true;
        waited = true;
        return uint64_t(elapsed.nsecsElapsed()) >= timeout;
    }
};

static bool wait_gl_sync(BqtRequest *r, uint32_t id, GLbitfield flags, uint64_t timeout)
{
    const auto native = checked_gl_sync(r, id);
    if (r->error) return true;
    auto *context = QOpenGLContext::currentContext();
    if (!id || !timeout) {
        r->result.word = context->extraFunctions()->glClientWaitSync(native, flags, timeout);
        return true;
    }
    auto state = std::make_shared<GlSyncWait>();
    state->context = context;
    state->surface = context->surface();
    state->surface_guard = dynamic_cast<QObject *>(state->surface);
    if (!state->surface_guard) return fail(r, ENOTSUP, "OpenGL asynchronous wait requires an observable surface");
    if (!callback_pin(r, id)) return true;
    state->sync_id = id;
    const auto owner = borrow(r, context, @CONTEXT_TYPE@);
    if (!owner || !callback_pin(r, owner)) return true;
    state->context_id = owner;
    const auto surface_owner = borrow(r, state->surface_guard.data(), @OBJECT_TYPE@);
    if (!surface_owner || !callback_pin(r, surface_owner)) return true;
    state->surface_id = surface_owner;
    state->flags = flags;
    state->timeout = timeout;
    state->elapsed.start();
    return wait_until(r, [state, r] { return state->poll(r); }, QDeadlineTimer(QDeadlineTimer::Forever),
        [state](BqtRequest *result) { if (!result->error) result->result.word = state->status; });
}
