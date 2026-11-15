"""Checked QModelIndex copies; Qt already guards persistent indexes/ranges."""

TYPES = {'QModelIndex'}


def contains(t):
    return t.get('name') in TYPES or any(contains(child) for child in t.get('children', []))


def after_native(g, m):
    f = m['function']
    if f['declaring_class'] == 'QModelIndex' and f['name'] == 'operator=':
        return ['if (!finish_model_index_ownership(r, r->self)) return true;']
    if f['declaring_class'] == 'QVariant' and not f['const'] and not f['static']:
        lines = ['if (!finish_model_index_ownership(r, r->self)) return true;']
        if f['name'] == 'swap' and m['args']:
            lines += ['if (!finish_model_index_ownership(r, r->arguments[0].word)) return true;']
        return lines
    return []


def cpp(g):
    return f'''
struct ModelIndexOrigin {{
    QPointer<const QAbstractItemModel> model;
    QPersistentModelIndex anchor;
    bool had_model = false, was_valid = false;
    bool (*previous)(BqtRequest *, uint32_t) = nullptr;
}};
static SlotTable<ModelIndexOrigin *> model_index_origins;
static const QAbstractItemModel *live_index_model(BqtRequest *r, const QAbstractItemModel *address) {{
    if (!address) return nullptr;
    // Native QVariant payloads can contain indexes whose model died before the
    // payload entered the binding. Compare addresses before dereferencing them.
    const QObject *wanted = static_cast<const QObject *>(address);
    std::vector<QObject *> roots;
    for (uint32_t i = 1; i < capacity; ++i) {{
        const auto &record = entries[i];
        if (!record.value || !record.object) continue;
        const bool accessible = !record.destroying &&
            (!record.alive || (*record.alive)->load(std::memory_order_acquire));
        if (record.object == wanted) {{
            if (!accessible) {{ fail(r, ESTALE, "Index model is no longer accessible"); return nullptr; }}
            if (record.object->thread() != main_thread) {{ fail(r, EXDEV, "Index model belongs to another thread"); return nullptr; }}
            return qobject_cast<QAbstractItemModel *>(record.object);
        }}
        if (accessible && record.object->thread() == main_thread) roots.push_back(record.object);
    }}
    // Models created internally by a registered widget are observable through
    // its QObject child tree without inventing a class-specific ownership rule.
    std::vector<QObject *> visited;
    while (!roots.empty()) {{
        auto *object = roots.back(); roots.pop_back();
        if (std::find(visited.begin(), visited.end(), object) != visited.end()) continue;
        visited.push_back(object);
        for (auto *child : object->children()) {{
            if (child == wanted) return qobject_cast<QAbstractItemModel *>(child);
            roots.push_back(child);
        }}
    }}
    fail(r, ESTALE, "Index model has no live observable QObject origin");
    return nullptr;
}}
static const QModelIndex *model_index_value(const Entry *value) {{
    if (!value) return nullptr;
    if (value->type == {g.ids['QModelIndex']}) return static_cast<const QModelIndex *>(value->value);
    if (value->type == {g.ids['QVariant']}) {{
        const auto *variant = static_cast<const QVariant *>(value->value);
        return variant->metaType() == QMetaType::fromType<QModelIndex>() ? static_cast<const QModelIndex *>(variant->constData()) : nullptr;
    }}
    if (value->type == {g.ids['MetaStorage']}) {{
        const auto *storage = static_cast<const MetaStorage *>(value->value);
        return storage->initialized && storage->type == QMetaType::fromType<QModelIndex>() ? static_cast<const QModelIndex *>(storage->data) : nullptr;
    }}
    return nullptr;
}}
static void model_index_forget(uint32_t id) {{
    auto *origin = model_index_origins[id & 65535u];
    model_index_origins[id & 65535u] = nullptr;
    delete origin;
}}
static bool validate_model_index(BqtRequest *r, uint32_t id) {{
    auto *value = entry(id);
    auto *origin = value ? model_index_origins[id & 65535u] : nullptr;
    if (!value || !origin) {{ fail(r, ESTALE, "Model index has no native origin"); return false; }}
    if (origin->previous && !origin->previous(r, id)) return false;
    value = entry(id);
    origin = value ? model_index_origins[id & 65535u] : nullptr;
    if (!origin) {{ fail(r, ESTALE, "Model index origin expired during validation"); return false; }}
    auto *current = model_index_value(entry(id));
    if (!current) {{ fail(r, ESTALE, "Model index storage changed its native type"); return false; }}
    const auto &index = *current;
    // Native clients may move a model without using our migration adapter.
    // Do not inspect its persistent anchor before rejecting foreign affinity.
    if (origin->model && origin->model->thread() != main_thread) {{
        fail(r, EXDEV, "Index model belongs to another thread"); return false;
    }}
    if ((origin->had_model && !origin->model) || index.model() != origin->model.data() ||
            (origin->was_valid && (!origin->anchor.isValid() || QModelIndex(origin->anchor) != index))) {{
        fail(r, ESTALE, "Model index was invalidated by structural changes or model destruction"); return false;
    }}
    if (origin->model) {{
        // Pin the model only while calling it. Qt's persistent anchor observes
        // removal/reset/destruction; a stored index does not keep the model alive.
        uint32_t owner = 0;
        for (uint32_t i = 1; i < capacity; ++i)
            if (entries[i].value && entries[i].object == origin->model) {{ owner = token(i, entries[i].generation); break; }}
        if (!owner) {{
            auto *model = const_cast<QAbstractItemModel *>(origin->model.data());
            owner = insert(r, model, model, {g.ids['QAbstractItemModel']}, native_deleter<QAbstractItemModel>(), false);
        }}
        if (native_call_scope && owner) native_call_scope->pin(r, owner);
    }}
    return !r->error;
}}
static uint32_t finish_model_index_ownership(BqtRequest *r, uint32_t id) {{
    auto *value = entry(id);
    auto *current = model_index_value(value);
    if (!value) return id;
    auto *old = model_index_origins[id & 65535u];
    auto previous = value->validate == validate_model_index && old ? old->previous : value->validate;
    if (!current) {{
        if (value->validate == validate_model_index) value->validate = previous;
        model_index_forget(id); return id;
    }}
    try {{
        const auto &index = *current;
        auto origin = std::make_unique<ModelIndexOrigin>();
        origin->previous = previous;
        origin->had_model = index.model() != nullptr;
        origin->was_valid = index.isValid();
        const auto *model = live_index_model(r, index.model());
        if (!r->error) {{
            origin->model = model;
            origin->anchor = QPersistentModelIndex(index);
            model_index_forget(id);
            model_index_origins[id & 65535u] = origin.release();
            value->validate = validate_model_index;
            return id;
        }}
    }} catch (...) {{
        auto *storage = value->value; auto destroy = value->destroy;
        invalidate(id); destroy(storage); throw;
    }}
    auto *storage = value->value; auto destroy = value->destroy;
    invalidate(id); destroy(storage); return 0;
}}
'''
