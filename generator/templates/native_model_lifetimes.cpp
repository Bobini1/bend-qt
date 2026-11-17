// Native item models report removals before deleting their non-QObject items.
// Store persistent indexes rather than probing an item pointer after deletion.
struct NativeModelObservation {
    uint32_t item, model;
    QPersistentModelIndex *index;
};
static SlotTable<NativeModelObservation> native_model_observations;
static SlotTable<uint32_t> native_observed_models;
static SlotTable<uint32_t> native_take_tokens;
static SlotTable<uint32_t> native_take_depth;
#if defined(BQT_HAS_WIDGETS)
// Widget layouts own their QLayoutItems; groups without QtWidgets have none.
struct NativeLayoutObservation {
    uint32_t item, layout;
    QLayoutItem *pointer;
    QWidget *widget;
    bool checking;
};
static SlotTable<NativeLayoutObservation> native_layout_observations;
#endif

static void native_model_forget(uint32_t id)
{
#if defined(BQT_HAS_WIDGETS)
    auto &layout = native_layout_observations[id & 65535u];
    if (layout.item == id) {
        layout = {};
        if (auto *e = entry(id)) e->validate = nullptr;
    }
#endif
    auto &record = native_model_observations[id & 65535u];
    if (record.item != id) return;
    delete record.index;
    record = {};
}

static void native_model_detach(uint32_t id)
{
    for (const auto &record : native_model_observations)
        if (record.item && entry_inside(record.item, id)) native_model_forget(record.item);
#if defined(BQT_HAS_WIDGETS)
    for (const auto &record : native_layout_observations)
        if (record.item && entry_inside(record.item, id)) native_model_forget(record.item);
#endif
}

static bool native_model_taking(uint32_t id)
{
    for (uint32_t depth = 0; id && depth < capacity; ++depth) {
        auto slot = id & 65535u;
        if (native_take_tokens[slot] == id && native_take_depth[slot]) return true;
        auto *e = entry(id);
        id = e ? e->native_owner : 0;
    }
    return false;
}

struct NativeTakeScope {
    uint32_t id;
    explicit NativeTakeScope(uint32_t value) : id(value) {
        auto slot = id & 65535u;
        if (native_take_tokens[slot] != id) {
            native_take_tokens[slot] = id;
            native_take_depth[slot] = 0;
        }
        ++native_take_depth[slot];
    }
    NativeTakeScope(const NativeTakeScope &) = delete;
    ~NativeTakeScope() {
        auto slot = id & 65535u;
        if (native_take_tokens[slot] == id && native_take_depth[slot]) --native_take_depth[slot];
        auto &record = native_model_observations[slot];
        if (record.item == id && record.index && !record.index->isValid()) native_model_forget(id);
    }
};

struct NativeTakeBatch {
    std::vector<NativeTakeScope *> scopes;
    void add(uint32_t id) {
        if (!id) return;
        scopes.push_back(nullptr);
        scopes.back() = new NativeTakeScope(id);
    }
    ~NativeTakeBatch() { for (auto *scope : scopes) delete scope; }
};

#if defined(BQT_HAS_WIDGETS)
static bool validate_native_layout_item(BqtRequest *r, uint32_t id)
{
    if (native_model_taking(id)) return true;
    auto &record = native_layout_observations[id & 65535u];
    if (record.item != id) { fail(r, ESTALE, "Native layout item observation expired"); return false; }
    if (record.checking) { fail(r, EBUSY, "Native layout item validation is already active"); return false; }
    auto *owner = entry(record.layout);
    auto *layout = owner ? qobject_cast<QLayout *>(owner->object) : nullptr;
    if (!layout) { invalidate(id); fail(r, ESTALE, "Native layout item owner expired"); return false; }
    struct Checking {
        uint32_t id;
        ~Checking() { auto &r = native_layout_observations[id & 65535u]; if (r.item == id) r.checking = false; }
    } checking{id};
    record.checking = true;
    NativeCallScope scope;
    scope.pin(r, record.layout);
    if (r->error) return false;
    auto *pointer = record.pointer;
    bool found = false;
    for (int i = 0, count = layout->count(); i < count; ++i)
        if (layout->itemAt(i) == pointer) { found = true; break; }
    // The owner is pinned, but a callback may still remove this item. Reload
    // the generation after virtual layout calls before exposing its pointer.
    if (!entry(id) || !found) {
        invalidate(id);
        fail(r, ESTALE, "Native layout item was removed or replaced");
        return false;
    }
    return true;
}

static void observe_native_layout_item(uint32_t id, uint32_t owner, QLayoutItem *pointer)
{
    auto *e = entry(id), *layout = entry(owner);
    if (!e || e->object || !layout || !qobject_cast<QLayout *>(layout->object)) return;
    native_layout_observations[id & 65535u] = {id, owner, pointer, pointer->widget(), false};
    if (!e->native_observed) e->validate = validate_native_layout_item;
}

static bool native_layout_widget_idle(BqtRequest *r, QWidget *widget)
{
    for (const auto &record : native_layout_observations) {
        if (!record.item || record.widget != widget) continue;
        auto *e = entry(record.item);
        if (e && e->active_calls) {
            fail(r, EBUSY, "Widget's native layout item is active in a suspended callback");
            return false;
        }
    }
    return true;
}

static void reconcile_native_layouts()
{
    static bool reconciling;
    if (reconciling) return;
    struct Guard { ~Guard() { reconciling = false; } } guard;
    reconciling = true;
    for (const auto &record : native_layout_observations) {
        // A nested reconciliation cannot validate the same virtual call twice;
        // the active validator completes this observation before get returns.
        if (!record.item || record.checking || native_model_taking(record.item)) continue;
        auto *e = entry(record.item);
        if (!e || e->native_observed) continue;
        BqtRequest checked{};
        validate_native_layout_item(&checked, record.item);
    }
}
#else
static void reconcile_native_layouts() {}
#endif

static void native_model_removing(uint32_t model, const QModelIndex &parent,
                                  int first, int last, bool columns)
{
    for (const auto &record : native_model_observations) {
        if (record.model != model || !record.item || native_model_taking(record.item)) continue;
        QModelIndex index = *record.index;
        while (index.isValid()) {
            int position = columns ? index.column() : index.row();
            if (index.parent() == parent && position >= first && position <= last) {
                uint32_t id = record.item;
                native_model_forget(id);
                invalidate(id);
                break;
            }
            index = index.parent();
        }
    }
}

static void native_model_reset(uint32_t model)
{
    for (const auto &record : native_model_observations) {
        if (record.model != model || !record.item || native_model_taking(record.item)) continue;
        uint32_t id = record.item;
        native_model_forget(id);
        invalidate(id);
    }
}

static bool observe_native_model_item(BqtRequest *r, uint32_t item, uint32_t model_id,
                                      const QModelIndex &index)
{
    auto *value = entry(item), *owner = entry(model_id);
    auto *model = owner ? qobject_cast<QAbstractItemModel *>(owner->object) : nullptr;
    if (!value || !model || !index.isValid() || index.model() != model) {
        fail(r, EINVAL, "A native item observation requires its live model index");
        return false;
    }
    QPersistentModelIndex *next_index = nullptr;
    try { next_index = new QPersistentModelIndex(index); }
    catch (...) { invalidate(item); throw; }
    auto slot = model_id & 65535u;
    if (native_observed_models[slot] != model_id) {
        QMetaObject::Connection connections[4];
        try {
        connections[0] = QObject::connect(model, &QAbstractItemModel::rowsAboutToBeRemoved, model,
            [model_id](const QModelIndex &parent, int first, int last) {
                native_model_removing(model_id, parent, first, last, false);
            });
        connections[1] = QObject::connect(model, &QAbstractItemModel::columnsAboutToBeRemoved, model,
            [model_id](const QModelIndex &parent, int first, int last) {
                native_model_removing(model_id, parent, first, last, true);
            });
        connections[2] = QObject::connect(model, &QAbstractItemModel::modelAboutToBeReset, model,
            [model_id] { native_model_reset(model_id); });
        connections[3] = QObject::connect(model, &QObject::destroyed, [model_id] { native_model_reset(model_id); });
        native_observed_models[slot] = model_id;
        } catch (...) {
            for (auto connection : connections) QObject::disconnect(connection);
            delete next_index;
            invalidate(item);
            throw;
        }
    }
    auto &record = native_model_observations[item & 65535u];
    // This slot may have belonged to an earlier generation of the same handle.
    delete record.index;
    record = {item, model_id, next_index};
    return true;
}
