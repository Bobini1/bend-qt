// Runnables Qt takes over: thread-pool jobs and Quick render jobs.
//
// Qt runs a job on another thread and, with autoDelete, deletes it there. The
// binding schedules a wrapper instead, so the handle the program holds stays
// registered and checked until the job has finished, and every ownership
// change happens on the main thread. Wrappers use autoDelete=false: Qt
// documents that such a runnable may be deleted after run(), which also
// removes tryTake's address-reuse race.
static SlotTable<uint32_t> scheduled_runnables;
static bool runnable_is_scheduled(uint32_t id) { return scheduled_runnables[id & 65535u] == id; }

struct PoolJob;
static SlotTable<PoolJob *> pool_jobs;
// Jobs that ran, with their failure, until the main thread completes them.
static auto &finished_pool_jobs() {
    static auto *state = new std::pair<QMutex, std::vector<std::pair<PoolJob *, int>>>;
    return *state;
}
static void complete_finished_pool_jobs();
struct PoolState { uint32_t token; int reservations; int failure; };
static SlotTable<PoolState> pool_states;

static PoolState &pool_state(uint32_t id) {
    auto &state = pool_states[id & 65535u];
    if (state.token != id) state = {id, 0, 0};
    return state;
}

struct PoolJob final : QRunnable {
    uint32_t pool_id, runnable_id;
    QThreadPool *pool;
    QRunnable *target;
    bool native_delete;
    size_t slot;
    PoolJob(uint32_t owner, uint32_t id, QThreadPool *p, QRunnable *r, size_t index)
        : pool_id(owner), runnable_id(id), pool(p), target(r),
          native_delete(r->autoDelete()), slot(index) { setAutoDelete(false); }
    // On the main thread, once the job has run or Qt gave it back.
    void finish(bool taken, int error = 0) {
        if (pool_jobs[slot] != this) return;
        pool_jobs[slot] = nullptr;
        scheduled_runnables[runnable_id & 65535u] = 0;
        if (error && !pool_state(pool_id).failure) pool_state(pool_id).failure = error;
        callback_unpin(runnable_id);
        if (auto *e = entry(runnable_id)) {
            if (taken && native_delete) e->owned = true;
            else if (native_delete) {
                auto *storage = e->value;
                auto destroy = e->destroy;
                invalidate(runnable_id);
                destroy(storage);
            }
        }
        callback_unpin(pool_id);
        delete this;
    }
    void run() override {
        int failure = 0;
        try { target->run(); }
        catch (const std::bad_alloc &) { failure = ENOMEM; }
        catch (...) { failure = EFAULT; }
        // No access to this wrapper after this: the main thread may delete it
        // before this thread returns. Qt read autoDelete before run().
        {
            auto &finished = finished_pool_jobs();
            QMutexLocker lock(&finished.first);
            finished.second.emplace_back(this, failure);
        }
        if (auto *context = main_context.load(std::memory_order_acquire))
            QMetaObject::invokeMethod(context, [] { complete_finished_pool_jobs(); }, Qt::QueuedConnection);
    }
};

static void complete_finished_pool_jobs() {
    std::vector<std::pair<PoolJob *, int>> jobs;
    {
        auto &finished = finished_pool_jobs();
        QMutexLocker lock(&finished.first);
        jobs.swap(finished.second);
    }
    for (auto [job, failure] : jobs) job->finish(false, failure);
}

static PoolJob *pool_job_for(uint32_t id) {
    for (auto *job : pool_jobs) if (job && job->runnable_id == id) return job;
    return nullptr;
}

static bool pool_has_jobs(QThreadPool *pool) {
    for (auto *job : pool_jobs) if (job && job->pool == pool) return true;
    return false;
}

static bool start_pool_job(BqtRequest *r, QThreadPool *pool, uint32_t id, QRunnable *target, int priority, int mode) {
    if (!target) { fail(r, EINVAL, "Thread-pool runnable is null"); return false; }
    if (runnable_is_scheduled(id)) { fail(r, EBUSY, "Runnable is already queued or running"); return false; }
    auto *e = entry(id);
    if (!e || !e->native_observed) { fail(r, EPERM, "A scheduled runnable requires observed destruction"); return false; }
    if (target->autoDelete() && (!e->owned || e->native_owner || e->read_only)) {
        fail(r, EPERM, "An auto-deleting runnable requires exclusive Bend ownership"); return false;
    }
    if (target->autoDelete() && (retained(id) || e->active_calls > 1)) {
        fail(r, EBUSY, "An auto-deleting runnable is retained or active elsewhere"); return false;
    }
    if (target->autoDelete() && !can_transfer_handle(r, id)) return false;
    if (mode == 2 && pool_state(r->self).reservations <= 0) {
        fail(r, EINVAL, "No binding-reserved thread is available"); return false;
    }
    size_t index = 0;
    while (index < capacity && pool_jobs[index]) ++index;
    if (index == capacity) { fail(r, ENOSPC, "Thread-pool job table is full"); return false; }
    auto job = std::make_unique<PoolJob>(r->self, id, pool, target, index);
    if (!callback_pin(r, id)) return false;
    if (!callback_pin(r, r->self)) { callback_unpin(id); return false; }
    pool_jobs[index] = job.get();
    scheduled_runnables[id & 65535u] = id;
    try {
        if (mode == 1 && !pool->tryStart(job.get())) {
            pool_jobs[index] = nullptr;
            scheduled_runnables[id & 65535u] = 0;
            callback_unpin(id); callback_unpin(r->self);
            return false;
        }
        if (mode == 0) pool->start(job.get(), priority);
        if (mode == 2) { pool->startOnReservedThread(job.get()); --pool_state(r->self).reservations; }
    } catch (...) {
        pool_jobs[index] = nullptr;
        scheduled_runnables[id & 65535u] = 0;
        callback_unpin(id); callback_unpin(r->self);
        throw;
    }
    if (job->native_delete) e->owned = false;
    job.release();
    return true;
}

static bool take_pool_job(BqtRequest *, QThreadPool *pool, uint32_t id) {
    auto *job = pool_job_for(id);
    if (!job || job->pool != pool || !pool->tryTake(job)) return false;
    job->finish(true);
    return true;
}

static void clear_pool_jobs(QThreadPool *pool) {
    for (auto *job : pool_jobs)
        if (job && job->pool == pool && pool->tryTake(job)) job->finish(false);
    pool->clear();
}

static void change_pool_reservation(BqtRequest *r, QThreadPool *pool, int change) {
    auto &state = pool_state(r->self);
    if ((change > 0 && state.reservations == INT_MAX) || (change < 0 && state.reservations == INT_MIN)) {
        fail(r, EOVERFLOW, "Thread-pool reservation count overflow"); return;
    }
    if (change > 0) pool->reserveThread(); else pool->releaseThread();
    state.reservations += change;
}

// Waits as Qt does: the main thread takes no other work meanwhile, so a job
// whose handler needs the main thread cannot finish during the wait. Jobs that
// did finish are completed before this returns.
static void wait_pool_jobs(BqtRequest *r, QThreadPool *pool, QDeadlineTimer deadline) {
    bool done = pool->waitForDone(deadline);
    complete_finished_pool_jobs();
    r->result.word = done && !pool_has_jobs(pool);
    auto &state = pool_state(r->self);
    if (state.failure) {
        int error = std::exchange(state.failure, 0);
        fail(r, error, "A native thread-pool runnable raised an exception");
    }
}

// Unlike Qt's blocking wait, this keeps the Qt/Bend event loop running so a
// pool thread can synchronously call its Bend handler and complete.
static void await_pool_jobs(BqtRequest *r, QThreadPool *pool, QDeadlineTimer deadline) {
    if (!deadline.hasExpired()) {
        for (const auto &slot : callback_slots) if (slot.frame) {
            auto *job = pool_job_for(slot.frame->receiver);
            if (job && job->pool == pool) {
                fail(r, EDEADLK, "A pool job cannot await completion of its own pool"); return;
            }
        }
    }
    wait_until(r, [pool] {
        bool done = pool->waitForDone(QDeadlineTimer(0));
        complete_finished_pool_jobs();
        return done && !pool_has_jobs(pool);
    }, deadline);
    auto &state = pool_state(r->self);
    if (!r->error && state.failure) {
        int error = std::exchange(state.failure, 0);
        fail(r, error, "A native thread-pool runnable raised an exception");
    }
}

static void finish_render_job(uint32_t id) {
    scheduled_runnables[id & 65535u] = 0;
    callback_unpin(id);
    if (auto *e = entry(id)) {
        auto *storage = e->value;
        auto destroy = e->destroy;
        invalidate(id);
        destroy(storage);
    }
}

// Qt owns a render job and deletes it after it runs, or with its window.
struct RenderJob final : QRunnable {
    uint32_t window_id, runnable_id;
    QRunnable *target;
    bool armed = false;
    RenderJob(uint32_t window, uint32_t id, QRunnable *value)
        : window_id(window), runnable_id(id), target(value) {}
    ~RenderJob() override {
        if (!armed) return;
        if (QThread::currentThread() != main_thread) {
            // Render jobs require the GUI render loop. Keep the registry on
            // the main thread even if native code changed the loop.
            if (auto *context = main_context.load(std::memory_order_acquire))
                QMetaObject::invokeMethod(context, [id = runnable_id] { finish_render_job(id); }, Qt::QueuedConnection);
        } else {
            finish_render_job(runnable_id);
        }
    }
    void run() override {
        BqtRequest observation{};
        GuiRenderScope scope(&observation, window_id);
        if (!scope.active) return;
        try { target->run(); }
        catch (...) { callback_report_error(EFAULT); }
    }
};

static bool schedule_render_job(BqtRequest *r, QQuickWindow *window, uint32_t id,
                                QRunnable *target, QQuickWindow::RenderStage stage) {
    if (!gui_render_enabled) return fail(r, EPERM, "Choose Render.useGuiThread before scheduling Bend render jobs");
    switch (stage) {
    case QQuickWindow::BeforeSynchronizingStage:
    case QQuickWindow::AfterSynchronizingStage:
    case QQuickWindow::BeforeRenderingStage:
    case QQuickWindow::AfterRenderingStage:
    case QQuickWindow::AfterSwapStage:
    case QQuickWindow::NoStage: break;
    default: return fail(r, EINVAL, "Unknown Qt render-job stage");
    }
    if (runnable_is_scheduled(id)) return fail(r, EBUSY, "Runnable is queued or running");
    auto *e = entry(id);
    if (!e || !e->owned || !e->destroy || !e->native_observed || e->native_owner || e->read_only)
        return fail(r, EPERM, "A render job requires an owned, observed runnable");
    if (retained(id) || e->active_calls > 1)
        return fail(r, EBUSY, "Runnable is retained, queued, or running");
    if (!can_transfer_handle(r, id)) return true;
    auto wrapper = std::make_unique<RenderJob>(r->self, id, target);
    if (!callback_pin(r, id)) return true;
    wrapper->armed = true;
    scheduled_runnables[id & 65535u] = id;
    // Qt owns every render job, whatever its autoDelete flag. The window is
    // not pinned while a job is queued: destroying a window that was never
    // shown discards its queued jobs.
    e->owned = false;
    window->scheduleRenderJob(wrapper.get(), stage);
    wrapper.release();
    return true;
}

// Before Qt is destroyed: queued jobs are given back and running ones are
// waited for. Handlers no longer run, so a job waiting for the main thread
// gets its refusal from the events processed here.
static void runnable_jobs_shutdown() {
    for (auto *job : pool_jobs)
        if (job && entry(job->pool_id) && job->pool->tryTake(job)) job->finish(false);
    for (;;) {
        bool running = false;
        for (auto *job : pool_jobs) if (job) running = true;
        if (!running) break;
        QCoreApplication::processEvents(QEventLoop::AllEvents);
        complete_finished_pool_jobs();
        QThread::msleep(1);
    }
}
