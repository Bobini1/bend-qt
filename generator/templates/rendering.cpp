// Opt in before Qt creates any Quick window. The basic loop still uses Qt's
// selected graphics API; it changes the rendering thread, not the renderer.
static SlotTable<uint32_t> render_collection_windows;
static void watch_render_collection(uint32_t id, QQuickWindow *window);
static void render_factory_end_scope(uint64_t);

static bool use_gui_render_loop(BqtRequest *r)
{
    for (auto *window : QGuiApplication::allWindows())
        if (qobject_cast<QQuickWindow *>(window))
            return fail(r, EBUSY, "Choose the GUI render loop before creating Quick windows");
    if (!qputenv("QSG_RENDER_LOOP", QByteArrayLiteral("basic")))
        return fail(r, EIO, "Cannot configure the Qt render loop");
    gui_render_enabled = true;
    return true;
}

struct GuiRenderScope;
static GuiRenderScope *active_gui_render_scope = nullptr;
static uint64_t next_gui_render_scope = 0;
struct GuiRenderScope {
    GuiRenderScope *previous = active_gui_render_scope;
    uint64_t identity = 0;
    uint32_t window = 0;
    bool active = false;
    uint32_t previous_window = gui_render_window;
    explicit GuiRenderScope(BqtRequest *r, uint32_t receiver) {
        if (!application || QThread::currentThread() != main_thread) {
            fail(r, EXDEV, "Bend scene graph callbacks require rendering on the Qt GUI thread");
            return;
        }
        for (uint32_t depth = 0, id = receiver; id && depth < capacity; ++depth) {
            auto *e = entry(id);
            if (!e) break;
            QQuickWindow *native_window = nullptr;
            if (e->object) {
                native_window = qobject_cast<QQuickWindow *>(e->object);
                if (auto *item = qobject_cast<QQuickItem *>(e->object)) native_window = item->window();
            }
            if (!native_window && e->render_window) {
                auto *owner = entry(e->render_window);
                if (owner && owner->object && !owner->destroying
                        && (!owner->alive || (*owner->alive)->load(std::memory_order_acquire)))
                    native_window = qobject_cast<QQuickWindow *>(owner->object);
            }
            if (native_window) {
                window = borrow(r, native_window, @QQUICK_WINDOW_TYPE@);
                if (r->error || !callback_pin(r, window)) { window = 0; return; }
                try { watch_render_collection(window, native_window); }
                catch (...) { callback_unpin(window); window = 0; throw; }
                break;
            }
            id = e->native_owner;
        }
        if (next_gui_render_scope == UINT64_MAX) {
            fail(r, EOVERFLOW, "GUI render callback identity space is exhausted");
            return;
        }
        identity = ++next_gui_render_scope;
        active_gui_render_scope = this;
        ++gui_render_depth;
        if (window) gui_render_window = window;
        active = true;
    }
    GuiRenderScope(const GuiRenderScope &) = delete;
    ~GuiRenderScope() {
        if (active) {
            render_factory_end_scope(identity);
            active_gui_render_scope = previous; --gui_render_depth; gui_render_window = previous_window;
        }
        if (window) callback_unpin(window);
    }
};

static void watch_render_collection(uint32_t id, QQuickWindow *window)
{
    auto slot = id & 65535u;
    if (render_collection_windows[slot] == id) return;
    auto collect = [id] {
        if (!application || QThread::currentThread() != main_thread) return;
        BqtRequest observation{};
        GuiRenderScope scope(&observation, id);
        if (scope.active) collect_pending();
    };
    QObject::connect(window, &QQuickWindow::beforeSynchronizing, window, collect, Qt::DirectConnection);
    QObject::connect(window, &QQuickWindow::sceneGraphInvalidated, window, collect, Qt::DirectConnection);
    render_collection_windows[slot] = id;
}

static void schedule_render_collection(uint32_t id)
{
    auto *e = entry(id);
    auto *owner = e ? entry(e->render_window) : nullptr;
    auto *window = owner && owner->object ? qobject_cast<QQuickWindow *>(owner->object) : nullptr;
    if (window) window->update();
}

static void prepare_render_shutdown()
{
    // Registered scene-graph resources were created in a GUI render callback.
    // Let Qt make that renderer's context current and invalidate its graph;
    // the direct invalidation hook then collects pending external resources.
    for (uint32_t id : render_collection_windows) {
        auto *e = entry(id);
        auto *window = e && e->object ? qobject_cast<QQuickWindow *>(e->object) : nullptr;
        if (!window) continue;
        window->setPersistentSceneGraph(false);
        window->setPersistentGraphics(false);
        window->hide();
        window->releaseResources();
    }
}
