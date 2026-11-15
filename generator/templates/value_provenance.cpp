// A copy retains the QObject origins themselves. Retaining a mutable source
// wrapper would make later source assignment change the copy's lifetime.
// Every edge in this slot is validated as a QObject origin, so no other
// module may reuse its value for an unrelated retention edge.
constexpr uint32_t value_provenance_slot = 0xffffffd8u;
constexpr uint32_t js_exposure_slot = 0xffffffd7u;
#if @HAS_QJSEngine@
static bool prepare_js_exposure(BqtRequest *r, uint32_t engine, uint32_t object, RetentionBatch &lease) {
    if (!object) return true;
    auto *target = entry(object);
    if (!target || !target->object) { fail(r, ESTALE, "JavaScript exposure requires a live QObject handle"); return false; }
    if (target->alive && !(*target->alive)->load(std::memory_order_acquire)) {
        fail(r, ESTALE, "JavaScript exposure target was destroyed"); return false;
    }
    if (target->object->thread() != main_thread) {
        fail(r, EXDEV, "JavaScript exposure target belongs to another thread"); return false;
    }
    // Reserve and commit before the native operation. Even a throwing call may
    // have installed an engine-heap reference. These conservative leases last
    // until engine destruction, including after a context/property is cleared.
    // Ancestors and self are explicitly rejected by the ordinary cycle check;
    // skipping that edge would become unsafe after a later reparenting.
    if (!lease.add(r, engine, js_exposure_slot, object, nullptr)) return false;
    if (auto *host = dynamic_cast<RuntimeObjectHost *>(target->object)) host->bqt_exposed = true;
    if (native_call_scope) { native_call_scope->pin(r, engine); native_call_scope->pin(r, object); }
    return !r->error;
}
static bool retain_js_exposure(BqtRequest *r, uint32_t engine, uint32_t object) {
    RetentionBatch lease;
    return prepare_js_exposure(r, engine, object, lease) && lease.finish(r);
}
static bool prepare_js_variant_exposures(BqtRequest *r, uint32_t engine, const QVariant &value, RetentionBatch &lease, unsigned depth = 0) {
    if (depth > 128) { fail(r, EOVERFLOW, "QML context value nesting is too deep"); return false; }
    if (value.metaType().flags().testFlag(QMetaType::PointerToQObject)) {
        auto *object = value.value<QObject *>();
        if (!object) return true;
        auto id = retention_token(r, object, false);
        if (!id) { fail(r, ENOTSUP, "QML context QObject pointer requires an observed native handle"); return false; }
        return prepare_js_exposure(r, engine, id, lease);
    }
    if (value.metaType() == QMetaType::fromType<QVariantList>()) {
        for (const auto &child : value.toList())
            if (!prepare_js_variant_exposures(r, engine, child, lease, depth + 1)) return false;
    } else if (value.metaType() == QMetaType::fromType<QVariantMap>()) {
        for (const auto &child : value.toMap())
            if (!prepare_js_variant_exposures(r, engine, child, lease, depth + 1)) return false;
    } else if (value.metaType() == QMetaType::fromType<QVariantHash>()) {
        for (const auto &child : value.toHash())
            if (!prepare_js_variant_exposures(r, engine, child, lease, depth + 1)) return false;
    }
    return true;
}
static bool retain_js_variant_exposures(BqtRequest *r, uint32_t engine, const QVariant &value) {
    RetentionBatch lease;
    return prepare_js_variant_exposures(r, engine, value, lease) && lease.finish(r);
}
template<class Properties> static bool retain_js_context_properties(BqtRequest *r, uint32_t engine, const Properties &properties) {
    RetentionBatch lease;
    for (const auto &property : properties)
        if (!prepare_js_variant_exposures(r, engine, property.value, lease)) return false;
    return lease.finish(r);
}
#endif
static SlotTable<uint32_t> value_provenance_expired;
static void value_provenance_before_invalidate(uint32_t id) {
    for (const auto &edge : retentions)
        if (edge.slot == value_provenance_slot && edge.target == id && entry(edge.owner))
            value_provenance_expired[edge.owner & 65535u] = edge.owner;
}
struct ValueProvenanceScope {
    NativeCallScope *call;
    std::vector<uint32_t> sources;
    ValueProvenanceScope *previous;
    static inline ValueProvenanceScope *current = nullptr;
    ValueProvenanceScope(NativeCallScope *scope, std::initializer_list<uint32_t> ids)
        : call(scope), sources(ids), previous(current) { current = this; }
    ValueProvenanceScope(NativeCallScope *scope, std::vector<uint32_t> ids)
        : call(scope), sources(std::move(ids)), previous(current) { current = this; }
    ~ValueProvenanceScope() { current = previous; }
};
static bool value_provenance_validate(BqtRequest *r, uint32_t id) {
    if (value_provenance_expired[id & 65535u] == id) {
        fail(r, ESTALE, "Qt value's QObject origin was destroyed"); return false;
    }
    for (const auto &edge : retentions) if (edge.owner == id && edge.slot == value_provenance_slot) {
        auto *owner = entry(edge.target);
        if (!owner || !owner->object || (owner->alive &&
                !(*owner->alive)->load(std::memory_order_acquire))) {
            fail(r, ESTALE, "Qt value's QObject origin was destroyed"); return false;
        }
        if (owner->object->thread() != main_thread) {
            fail(r, EXDEV, "Qt value's origin belongs to another thread"); return false;
        }
        if (native_call_scope) native_call_scope->pin(r, edge.target);
        if (r->error) return false;
    }
    return !r->error;
}
static void collect_value_provenance(BqtRequest *r, uint32_t id,
        std::vector<uint32_t> &owners, std::vector<uint32_t> &visited, bool all_objects = false) {
    if (!id || std::find(visited.begin(), visited.end(), id) != visited.end()) return;
    visited.push_back(id);
    auto *e = entry(id);
    if (!e) { fail(r, ESTALE, "Copied Qt value origin expired"); return; }
    if (!value_provenance_validate(r, id)) return;
    if (e->object) {
        if (e->object->thread() != main_thread) { fail(r, EXDEV, "Cannot copy a QObject value origin owned by another thread"); return; }
        if (e->alive && !(*e->alive)->load(std::memory_order_acquire)) {
            fail(r, ESTALE, "Copied QObject origin was destroyed"); return;
        }
        QObject *object = e->object;
        // Audited foreign interfaces (such as DBus) can return independent
        // QVariant values. Do not probe their QML data from the GUI thread.
        if (object->thread() != main_thread) return;
        bool intrinsic = all_objects;
#if @HAS_QJSEngine@
        intrinsic |= qobject_cast<QJSEngine *>(object) != nullptr;
#endif
#if @HAS_QTextDocument@
        intrinsic |= qobject_cast<QTextDocument *>(object) != nullptr;
#endif
        if (intrinsic) owners.push_back(id);
#if @HAS_QQmlContext@
        if (auto *context = qobject_cast<QQmlContext *>(object)) {
            if (auto *engine = context->engine()) owners.push_back(borrow(r, engine, @QQmlEngine@));
        } else if (auto *engine = qmlEngine(object)) owners.push_back(borrow(r, engine, @QQmlEngine@));
#endif
        return;
    }
    // QVariant origin snapshots and known value copies can have several layers.
    // Traverse their immutable retention graph, never their opaque native data.
    for (const auto &edge : retentions) if (edge.owner == id && edge.target) {
        // These edges were just validated as concrete QObject origins above.
        // Preserve them even when their type is not an engine or document
        // (notably a SQL driver), independently of other traversal paths.
        if (edge.slot == value_provenance_slot) owners.push_back(edge.target);
        else collect_value_provenance(r, edge.target, owners, visited, all_objects);
    }
}
static uint32_t fail_value_provenance(BqtRequest *r, uint32_t id) {
    if (auto *e = entry(id)) {
        auto *value = e->value; auto destroy = e->destroy;
        invalidate(id); if (destroy) destroy(value);
    }
    return 0;
}
static uint32_t finish_value_provenance(BqtRequest *r, uint32_t id) try {
    auto *e = entry(id);
    if (!e) return id;
    const bool property = e->type == @QQmlProperty@;
    const bool script = e->type == @QJSValue@ || e->type == @QJSManagedValue@ || e->type == @QJSValueIterator@;
    if (!property && !script && e->type != @QTextCursor@ && e->type != @QVariant@ && e->type != @QSqlQuery@) return id;
    std::vector<uint32_t> owners, visited;
    if (native_call_scope && native_call_scope->value_origin)
        collect_value_provenance(r, native_call_scope->value_origin, owners, visited, property);
    else if (auto *scope = ValueProvenanceScope::current; scope && scope->call == native_call_scope) {
        for (auto source : scope->sources) collect_value_provenance(r, source, owners, visited, property);
    } else if (r->self && r->self != id) collect_value_provenance(r, r->self, owners, visited, property);
    if (r->error) return fail_value_provenance(r, id);
    if (e->type == @QTextCursor@) {
#if @HAS_QTextCursor@
        // Cursors survive edits; unlike block iterators they need no epoch guard.
        owners.clear();
        auto *cursor = static_cast<QTextCursor *>(e->value);
        if (!cursor->isNull())
            if (auto *document = cursor->document())
                owners.push_back(borrow(r, document, @QTextDocument@));
#endif
    } else if (e->type == @QJSManagedValue@) {
#if @HAS_QJSManagedValue@
        owners.clear();
        if (auto *engine = static_cast<QJSManagedValue *>(e->value)->engine())
            owners.push_back(borrow(r, engine, @QJSEngine@));
#endif
    } else if (e->type == @QSqlQuery@) {
#if @HAS_QSqlQuery@ && @HAS_QSqlDriver@
        // A copied query owns shared native result storage. Its driver edge
        // must belong to the query copy, independently of any result view.
        owners.clear();
        const auto *driver = static_cast<QSqlQuery *>(e->value)->driver();
        // Qt's null result has a process-global dummy driver. It requires no
        // registry handle or lifetime edge and must not leak a borrowed token.
        QSqlQuery empty(static_cast<QSqlResult *>(nullptr));
        if (driver && driver != empty.driver())
            owners.push_back(borrow_const(r, driver, @QSqlDriver@));
#endif
    } else if (property) {
#if @HAS_QQmlProperty@
        if (auto *object = static_cast<QQmlProperty *>(e->value)->object())
            owners.push_back(borrow(r, object, @QObject@));
#endif
    }
    if (r->error) return fail_value_provenance(r, id);
    if (e->type == @QJSValue@ && owners.empty()) {
#if @HAS_QJSValue@
        auto *value = static_cast<QJSValue *>(e->value);
        // Public primitive conversion gives standalone storage, including a
        // string which may otherwise occupy a particular engine's heap slot.
        if (value->isString()) *value = QJSValue(value->toString());
        else if (value->isNumber()) *value = QJSValue(value->toNumber());
        else if (value->isBool()) *value = QJSValue(value->toBool());
        else if (!value->isNull() && !value->isUndefined()) {
            fail(r, ENOTSUP, "Managed JavaScript value requires an observed engine origin");
            return fail_value_provenance(r, id);
        }
#endif
    }
    std::sort(owners.begin(), owners.end());
    owners.erase(std::unique(owners.begin(), owners.end()), owners.end());
    RetentionBatch changes;
    for (auto owner : owners)
        if (!changes.add(r, id, value_provenance_slot, owner, nullptr)) return fail_value_provenance(r, id);
    // Reserve replacements before removing old dependencies. Native assignment
    // has already happened, so failure invalidates and disposes the destination.
    for (const auto &edge : retentions) if (edge.owner == id && edge.slot == value_provenance_slot &&
            std::find(owners.begin(), owners.end(), edge.target) == owners.end())
        if (!changes.add(r, id, value_provenance_slot, 0, nullptr, false, false, edge.key))
            return fail_value_provenance(r, id);
    if (!changes.finish(r)) return fail_value_provenance(r, id);
    value_provenance_expired[id & 65535u] = 0;
    return id;
} catch (...) {
    fail_value_provenance(r, id);
    throw;
}
static void clear_value_provenance(uint32_t id) {
    value_provenance_expired[id & 65535u] = 0;
    for (auto &edge : retentions) if (edge.owner == id && edge.slot == value_provenance_slot) edge = {};
}
static bool copy_value_provenance(BqtRequest *r, uint32_t target, uint32_t source) {
    NativeCallScope scope; scope.value_origin = source;
    return finish_value_provenance(r, target) != 0;
}
