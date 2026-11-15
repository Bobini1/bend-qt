// Included by the native conversion harness when the additive extractor exposes GLsync.
#ifdef BQT_GL_SYNC_FENCE
static void gl_sync_checks()
{
    using namespace bendqt;
    QOpenGLContext first, shared, separate;
    assert(first.create());
    shared.setShareContext(&first);
    assert(shared.create() && separate.create());
    QOffscreenSurface surface;
    surface.setFormat(first.format());
    surface.create();
    assert(first.makeCurrent(&surface));
    BqtRequest request{};
    auto *functions = new QOpenGLExtraFunctions(&first);
    const auto functions_id = own(&request, functions, BQT_GL_EXTRA_FUNCTIONS_TYPE);
    assert(functions_id && !request.error);
    request = {};
    request.self = functions_id;
    request.arguments[0].word = GL_SYNC_GPU_COMMANDS_COMPLETE;
    BQT_GL_SYNC_FENCE(&request);
    assert(!request.error);
    const auto sync = request.result.word;
    assert(sync && request.result.owned_handle == sync);
    request = {};
    request.self = functions_id;
    request.arguments[0].word = sync;
    BQT_GL_SYNC_IS(&request);
    assert(!request.error && request.result.word == GL_TRUE);

    assert(separate.makeCurrent(&surface));
    request = {};
    assert(!checked_gl_sync(&request, sync) && request.error == EXDEV);
    assert(shared.makeCurrent(&surface));
    request = {};
    assert(checked_gl_sync(&request, sync) && !request.error);
    assert(first.makeCurrent(&surface));
    request = {};
    request.self = functions_id;
    request.arguments[0].word = sync;
    request.arguments[1].word = GL_SYNC_FLUSH_COMMANDS_BIT;
    request.arguments[2] = wide_value(UINT64_C(1000000000));
    // The operation runs its Qt wait loop before returning to the caller.
    assert(BQT_GL_SYNC_WAIT(&request));
    assert(!request.error && (request.result.word == GL_ALREADY_SIGNALED || request.result.word == GL_CONDITION_SATISFIED));
    discard_value(request.arguments[2]);

    // A timer poll restores its original context without changing another call's context.
    {
        auto state = std::make_shared<GlSyncWait>();
        state->context = &first;
        state->surface = &surface;
        state->surface_guard = &surface;
        request = {};
        assert(callback_pin(&request, sync));
        state->sync_id = sync;
        state->timeout = UINT64_MAX;
        state->elapsed.start();
        assert(separate.makeCurrent(&surface));
        assert(state->poll(&request));
        assert(!request.error && QOpenGLContext::currentContext() == &separate);
        assert(first.makeCurrent(&surface));
        request = {};
        request.self = functions_id;
        request.arguments[0].word = sync;
        BQT_GL_SYNC_DELETE(&request);
        assert(request.error == EBUSY && entry(sync));
    }
    request = {};
    request.self = functions_id;
    request.arguments[0].word = sync;
    BQT_GL_SYNC_DELETE(&request);
    assert(!request.error && !entry(sync));
    request = {};
    request.self = functions_id;
    request.arguments[0].word = sync;
    BQT_GL_SYNC_DELETE(&request);
    assert(request.error == ESTALE);

    request = {};
    request.self = functions_id;
    request.arguments[0].word = GL_SYNC_GPU_COMMANDS_COMPLETE;
    BQT_GL_SYNC_FENCE(&request);
    assert(!request.error);
    const auto deferred = request.result.word;
    first.doneCurrent();
    request = {};
    request.self = deferred;
    release_object(&request);
    assert(!request.error && entry(deferred)->pending_release);
    assert(shared.makeCurrent(&surface));
    collect_pending();
    assert(!entry(deferred));
    assert(first.makeCurrent(&surface));
    request = {};
    request.self = functions_id;
    destroy_object(&request);
    assert(!request.error);
    std::puts("QT612_NATIVE_GL_SYNC_OK owned_fence=1 shared_context=1 foreign_rejected=1 wait=1 restore_context=1 pinned_delete=1 stale=1 deferred_cleanup=1");
}
#endif
