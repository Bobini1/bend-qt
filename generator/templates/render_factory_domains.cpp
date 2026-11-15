// A private anchor follows each native allocation after Qt consumes its token.
// Anchors preserve the original dependency slots and native ownership tree.
struct RenderFactoryView { uint32_t id = 0, anchor = 0; uint64_t scope = 0; };
static SlotTable<RenderFactoryView> render_factory_views;
static auto *render_factory_scope_views = new std::map<uint64_t, std::vector<uint32_t>>;
struct RenderFactoryMark { uint32_t id = 0; };
static SlotTable<RenderFactoryMark> render_factory_marks;
struct RenderFactoryDomain {
    uint64_t serial = 0;
    uint32_t anchor = 0, receiver = 0, window_id = 0;
    QPointer<QQuickWindow> window;
    QPointer<QQuickItem> item;
    const void *root = nullptr;
    void *value = nullptr;
    uint16_t type = 0;
    bool closing = false;
    void *(*cast)(void *, uint16_t) = nullptr;
    void (*destroy)(void *) = nullptr;
    std::unique_ptr<QVariant> storage;
    ~RenderFactoryDomain() { if (entry(anchor)) invalidate(anchor); }
};
static auto *render_factory_domains = new std::vector<std::unique_ptr<RenderFactoryDomain>>;
static auto *render_factory_windows = new std::map<QQuickWindow *, uint32_t>;
static uint64_t render_factory_serial = 0;
static RenderFactoryDomain *render_factory_domain(uint32_t anchor) {
    for (const auto &domain : *render_factory_domains)
        if (domain->anchor == anchor && entry(anchor)) return domain.get();
    return nullptr;
}
static uint32_t render_factory_retention_owner(uint32_t id) {
    const auto view = render_factory_views[id & 65535u];
    return entry(id) && view.id == id && entry(view.anchor) ? view.anchor : id;
}
static void render_factory_mark(uint32_t id) {
    auto *value = entry(id);
    if (value && value->owned && !value->object && !value->native_observed)
        render_factory_marks[id & 65535u] = {id};
}
static bool render_factory_consumable(uint32_t id) {
    auto *value = entry(id);
    return value && value->owned && !value->object && !value->native_observed
        && (render_factory_marks[id & 65535u].id == id || render_factory_retention_owner(id) != id);
}
static bool render_factory_detached(const RenderFactoryDomain &domain) {
    for (uint32_t id = domain.anchor, depth = 0; id && depth < capacity; ++depth) {
        auto *record = entry(id);
        if (!record) return false;
        if (record->owned) return true;
        id = record->native_owner;
    }
    return false;
}
template<class Predicate> static void render_factory_erase_if(Predicate erase) {
    for (size_t i = 0; i < render_factory_domains->size();) {
        auto &domain = (*render_factory_domains)[i];
        if (!entry(domain->anchor) || erase(*domain)) {
            // Remove the public ledger entry before invalidation can run a
            // callback that mutates this vector. Descendant anchors become
            // stale through native_owner, while detached subtrees stay live.
            auto removed = std::move(domain);
            render_factory_domains->erase(render_factory_domains->begin() + i);
            removed.reset();
            i = 0;
        } else ++i;
    }
}
static void render_factory_prune(QQuickWindow *window, uint64_t cutoff, bool all) {
    if (QThread::currentThread() != main_thread) return;
    render_factory_erase_if([&](const RenderFactoryDomain &domain) {
        return domain.window.data() == window && domain.serial <= cutoff && !render_factory_detached(domain)
            && (all || (domain.root && (!domain.item || domain.item->window() != window
                || !domain.item->flags().testFlag(QQuickItem::ItemHasContents))));
    });
    schedule_collection();
}
struct RenderFactoryCleanupJob final : QRunnable {
    QPointer<QQuickWindow> window;
    uint64_t cutoff;
    RenderFactoryCleanupJob(QQuickWindow *value, uint64_t serial) : window(value), cutoff(serial) {}
    void run() override { if (window) render_factory_prune(window, cutoff, true); }
};
static void render_factory_watch(QQuickWindow *window, uint32_t id) {
    auto found = render_factory_windows->find(window);
    if (found != render_factory_windows->end() && found->second == id) return;
    // Publish only after all observers are installed. A partial exception can
    // cause redundant safe observers on retry, never an unobserved domain.
    QObject::connect(window, &QQuickWindow::afterSynchronizing, window, [window] {
        render_factory_prune(window, render_factory_serial, false);
    }, Qt::DirectConnection);
    QObject::connect(window, &QQuickWindow::sceneGraphInvalidated, window, [window] {
        for (auto &domain : *render_factory_domains)
            if (domain->window == window && !render_factory_detached(*domain)) domain->closing = true;
        window->scheduleRenderJob(new RenderFactoryCleanupJob(window, render_factory_serial),
                                  QQuickWindow::AfterSynchronizingStage);
    }, Qt::DirectConnection);
    QObject::connect(window, &QObject::destroyed, [window, id] {
        if (QThread::currentThread() != main_thread) return;
        render_factory_erase_if([&](const RenderFactoryDomain &domain) {
            return domain.window_id == id && !render_factory_detached(domain);
        });
        auto found = render_factory_windows->find(window);
        if (found != render_factory_windows->end() && found->second == id) render_factory_windows->erase(found);
        schedule_collection();
    });
    render_factory_windows->insert_or_assign(window, id);
}
static bool render_factory_view_valid(BqtRequest *r, uint32_t id) {
    const auto view = render_factory_views[id & 65535u];
    auto *domain = render_factory_domain(view.anchor);
    if (view.id != id || !entry(id) || !domain || domain->closing
            || (!view.scope ? false : (!domain->window || !active_gui_render_scope
                || active_gui_render_scope->identity != view.scope))) {
        fail(r, ESTALE, "The factory view no longer has its native lifetime"); return false;
    }
    return true;
}
struct RenderFactoryAdoption {
    std::vector<uint32_t> retired;
    std::vector<std::pair<uint32_t, uint32_t>> preserved;
    std::vector<std::unique_ptr<RenderFactoryDomain>> allocations;
    RetentionBatch leases;
    uint32_t anchor = 0;
    bool committed = false;
    bool commit(BqtRequest *r) {
        if (committed) return true;
        for (auto id : retired) if (!entry(id)) { fail(r, ESTALE, "The adopted factory subtree expired"); return false; }
        for (auto link : preserved) if (!entry(link.first) || !entry(link.second)) {
            fail(r, ESTALE, "An observed factory child expired"); return false;
        }
        if (!leases.finish(r)) return false;
        // All allocations and vector capacity were reserved before Qt mutated.
        for (auto link : preserved) entry(link.first)->native_owner = link.second;
        for (auto &allocation : allocations) {
            render_factory_serial = std::max(render_factory_serial, allocation->serial);
            render_factory_domains->push_back(std::move(allocation));
        }
        allocations.clear();
        for (auto id : retired) { set_owned(id, false); invalidate(id); }
        committed = true;
        return true;
    }
};
static std::unique_ptr<RenderFactoryAdoption> render_factory_prepare_tree(BqtRequest *r, uint32_t id,
        uint32_t parent, QQuickWindow *window, uint32_t window_id, uint32_t receiver, bool render_node) {
    auto result = std::make_unique<RenderFactoryAdoption>();
    std::map<uint32_t, std::vector<uint32_t>> children;
    for (uint32_t i = 1; i < capacity; ++i)
        if (entries[i].value && entries[i].native_owner)
            children[entries[i].native_owner].push_back(token(i, entries[i].generation));
    std::vector<uint32_t> pending{id};
    std::set<uint32_t> seen, retiring;
    for (size_t i = 0; i < pending.size(); ++i) {
        const auto current = pending[i];
        if (!seen.insert(current).second) continue;
        auto *record = entry(current);
        if (!record) { fail(r, ESTALE, "A native factory subtree expired"); return {}; }
        if (current == id || (!(record->object || record->native_observed) && retiring.count(record->native_owner))) {
            result->retired.push_back(current); retiring.insert(current);
        }
        auto found = children.find(current);
        if (found != children.end()) pending.insert(pending.end(), found->second.begin(), found->second.end());
    }
    if (uint64_t(result->retired.size()) > UINT64_MAX - render_factory_serial) {
        fail(r, EOVERFLOW, "Render factory domain identity is exhausted"); return {};
    }
    std::map<uint32_t, uint32_t> anchors;
    for (auto old : result->retired) {
        auto *record = entry(old);
        auto allocation = std::make_unique<RenderFactoryDomain>();
        allocation->serial = render_factory_serial + result->allocations.size() + 1;
        allocation->window = window; allocation->window_id = window_id;
        allocation->value = record->value; allocation->type = record->type;
        allocation->cast = record->cast; allocation->destroy = record->destroy;
        if (old == id && render_node) {
            allocation->receiver = receiver;
            if (auto *owner = entry(receiver)) allocation->item = owner->object ? qobject_cast<QQuickItem *>(owner->object) : nullptr;
            allocation->root = record->cast ? record->cast(record->value, @QSG_NODE_ID@) : nullptr;
        }
        allocation->storage = std::make_unique<QVariant>();
        BqtRequest inserted{};
        allocation->anchor = insert(&inserted, allocation->storage.get(), nullptr, @VARIANT_ID@, nullptr, false);
        if (inserted.error || !allocation->anchor) {
            fail(r, inserted.error ? inserted.error : ENOMEM, inserted.message ? inserted.message : "Cannot allocate a factory lifetime"); return {};
        }
        anchors.emplace(old, allocation->anchor);
        result->allocations.push_back(std::move(allocation));
    }
    result->anchor = anchors.at(id);
    for (size_t i = 0; i < result->retired.size(); ++i) {
        const auto old = result->retired[i];
        auto *record = entry(old);
        auto found = anchors.find(record->native_owner);
        entry(result->allocations[i]->anchor)->native_owner = old == id ? parent
            : found != anchors.end() ? found->second : record->native_owner;
    }
    for (auto current : pending) {
        auto *record = entry(current);
        if (!record || retiring.count(current)) continue;
        auto found = anchors.find(record->native_owner);
        if (found != anchors.end()) result->preserved.emplace_back(current, found->second);
    }
    // Snapshot the original slots rather than coalescing unrelated property
    // references into one bag. Internal references use the corresponding anchor.
    std::vector<Retention> original;
    for (const auto &edge : retentions) if (retiring.count(edge.owner) && edge.target) original.push_back(edge);
    for (const auto &edge : original) {
        if (edge.current || edge.native_current) {
            fail(r, ENOTSUP, "A factory dependency requires its original typed observer"); return {};
        }
        const auto target = anchors.find(edge.target);
        if (!result->leases.add(r, anchors.at(edge.owner), edge.slot,
                target == anchors.end() ? edge.target : target->second,
                nullptr, false, false, edge.key)) return {};
    }
    render_factory_domains->reserve(render_factory_domains->size() + result->allocations.size());
    return result;
}
static std::unique_ptr<RenderFactoryAdoption> render_factory_prepare_adoption(BqtRequest *r, uint32_t id, uint32_t owner) {
    const auto parent = render_factory_retention_owner(owner);
    auto *record = entry(id);
    if (parent == owner || !record || record->object || record->native_observed || !record->owned
            || render_factory_retention_owner(id) != id) return {};
    auto *domain = render_factory_domain(parent);
    if (!domain || !domain->window || domain->closing) { fail(r, ESTALE, "The factory parent expired"); return {}; }
    return render_factory_prepare_tree(r, id, parent, domain->window.data(), domain->window_id, 0, false);
}
static bool render_factory_sync_owner(BqtRequest *r, uint32_t id, uint32_t owner) {
    const auto view = render_factory_views[id & 65535u];
    if (view.id != id || !entry(view.anchor)) return set_native_owner(r, id, render_factory_retention_owner(owner));
    auto *record = entry(id);
    auto *anchor = entry(view.anchor);
    if (!record || !anchor) { fail(r, ESTALE, "The factory allocation expired"); return false; }
    auto *domain = render_factory_domain(view.anchor);
    if (!domain || domain->closing) { fail(r, ESTALE, "The factory ownership domain expired"); return false; }
    if (!owner) {
        // The public token now owns the allocation and its anchor owns only
        // registry descendants. Do not leave the old parent in that graph.
        record->native_owner = 0;
        set_owned(id, true);
        anchor->native_owner = id;
        render_factory_views[id & 65535u].scope = 0;
        domain->root = nullptr; domain->receiver = 0; domain->item.clear();
    } else {
        const auto parent = render_factory_retention_owner(owner);
        if (!entry(parent) || parent == view.anchor || reaches_token(view.anchor, parent)) {
            fail(r, ELOOP, "Factory reparenting would create an ownership cycle"); return false;
        }
        anchor->native_owner = parent;
        record->native_owner = view.anchor;
        set_owned(id, false);
        domain->root = nullptr; domain->receiver = 0; domain->item.clear();
    }
    return true;
}
static bool render_factory_handoff(BqtRequest *r, uint32_t id, uint32_t receiver, bool render_node) {
    if (!render_factory_consumable(id)) { fail(r, EPERM, "This allocation has no factory consumption contract"); return false; }
    auto *record = entry(id);
    QQuickItem *item = nullptr;
    if (auto *caller = entry(receiver)) item = caller->object ? qobject_cast<QQuickItem *>(caller->object) : nullptr;
    uint32_t window_id = active_gui_render_scope ? active_gui_render_scope->window : 0;
    if (!window_id) window_id = record->render_window;
    if (!window_id) if (auto *caller = entry(receiver)) window_id = caller->render_window;
    QQuickWindow *window = nullptr;
    if (auto *candidate = entry(window_id)) window = candidate->object ? qobject_cast<QQuickWindow *>(candidate->object) : nullptr;
    if (!window && item && item->window()) {
        window = item->window(); window_id = borrow(r, window, @QQUICK_WINDOW_ID@);
        if (r->error) return false;
    }
    if (!window) { fail(r, ENODEV, "A factory transfer needs its render window"); return false; }
    render_factory_watch(window, window_id);
    if (!render_factory_consumable(id)) { fail(r, ESTALE, "The factory changed during observer installation"); return false; }
    const auto anchor = render_factory_retention_owner(id);
    if (anchor != id) {
        auto *domain = render_factory_domain(anchor);
        auto *root = entry(id);
        if (!domain || domain->closing || render_factory_serial == UINT64_MAX) {
            fail(r, ESTALE, "The detached factory lifetime expired"); return false;
        }
        domain->serial = ++render_factory_serial; domain->window = window; domain->window_id = window_id;
        domain->receiver = receiver; domain->item = render_node ? item : nullptr;
        domain->root = render_node && root->cast ? root->cast(root->value, @QSG_NODE_ID@) : nullptr;
        entry(anchor)->native_owner = 0;
        set_owned(id, false); invalidate(id);
        return true;
    }
    auto plan = render_factory_prepare_tree(r, id, 0, window, window_id, receiver, render_node);
    if (!plan) return false;
    if (!plan->commit(r)) return false;
    return true;
}
static void render_factory_replacing(uint32_t receiver, const void *previous, const void *next) {
    if (!previous || previous == next) return;
    for (const auto &root : *render_factory_domains)
        if (root->receiver == receiver && root->root == previous)
            for (auto &domain : *render_factory_domains)
                if (entry_inside(domain->anchor, root->anchor)) domain->closing = true;
}
static void render_factory_replaced(uint32_t receiver, const void *previous, const void *next) {
    if (!previous || previous == next) return;
    render_factory_erase_if([&](const RenderFactoryDomain &domain) {
        return domain.receiver == receiver && domain.root == previous;
    });
    schedule_collection();
}
static void render_factory_replacing_allocation(uint32_t id) {
    const auto anchor = render_factory_retention_owner(id);
    if (!render_factory_domain(anchor)) return;
    for (auto &domain : *render_factory_domains)
        if (entry_inside(domain->anchor, anchor)) domain->closing = true;
}
static void render_factory_replaced_allocation(uint32_t id) {
    const auto anchor = render_factory_retention_owner(id);
    render_factory_erase_if([&](const RenderFactoryDomain &domain) { return domain.anchor == anchor; });
    schedule_collection();
}
static uint32_t render_factory_restore(BqtRequest *r, const void *pointer, uint16_t type, uint32_t) {
    if (!pointer || !active_gui_render_scope) return 0;
    for (const auto &domain : *render_factory_domains) {
        if (!entry(domain->anchor) || !domain->window || domain->closing
                || !domain->cast || domain->cast(domain->value, type) != pointer) continue;
        for (uint32_t i = 1; i < capacity; ++i) {
            const auto id = token(i, entries[i].generation);
            const auto view = render_factory_views[i];
            if (entries[i].value && view.id == id && view.anchor == domain->anchor
                    && (!view.scope || view.scope == active_gui_render_scope->identity)) return id;
        }
        auto &views = (*render_factory_scope_views)[active_gui_render_scope->identity];
        views.reserve(views.size() + 1);
        const auto id = insert(r, domain->value, nullptr, domain->type, domain->destroy, false, domain->cast);
        if (!id) return 0;
        auto *record = entry(id);
        record->native_owner = domain->anchor; record->render_window = domain->window_id;
        record->validate = render_factory_view_valid;
        render_factory_views[id & 65535u] = {id, domain->anchor, active_gui_render_scope->identity};
        views.push_back(id);
        return id;
    }
    return 0;
}
static void render_factory_end_scope(uint64_t scope) {
    auto found = render_factory_scope_views->find(scope);
    if (found == render_factory_scope_views->end()) return;
    for (auto id : found->second) {
        const auto view = render_factory_views[id & 65535u];
        if (entry(id) && view.id == id && view.scope == scope) invalidate(id);
    }
    render_factory_scope_views->erase(found);
}
