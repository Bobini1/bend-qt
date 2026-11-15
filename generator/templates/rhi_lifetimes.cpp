struct RhiDomain { uint32_t id; QRhi *rhi; bool alive = true, frame_owned = false; QRhiSwapChain *swapchain = nullptr; int pass = 0; QRhiCommandBuffer *commands = nullptr; uint64_t frame_epoch = 0; bool cleaning = false; uint32_t cleanup_remaining = 0; };
static void rhi_cleanup_begin(const std::shared_ptr<RhiDomain> &);
static void rhi_cleanup_forget(uint32_t);
static bool rhi_cleanup_access(BqtRequest *, const std::shared_ptr<RhiDomain> &);
static void rhi_close_buffer_mappings(const std::shared_ptr<RhiDomain> &);
static bool rhi_mappings_closed(BqtRequest *, uint32_t);
static void rhi_readback_forget(uint32_t);
static void rhi_finish_readbacks(const std::shared_ptr<RhiDomain> &);
static void rhi_batch_submitted(uint32_t);
static void rhi_readbacks_merged(uint32_t, uint32_t);
struct RhiIdentity {
    uint32_t id;
    std::shared_ptr<RhiDomain> domain;
    bool batch = false, merged = false;
};
static auto &rhi_identities() { static auto *items = new std::vector<RhiIdentity>; return *items; }
static SlotTable<uint32_t> rhi_expired_dependencies;
static RhiIdentity *rhi_identity(uint32_t id) {
    for (auto &item : rhi_identities()) if (item.id == id) return &item;
    return nullptr;
}
static void rhi_native_records_changed(uint32_t id) {
    auto *owner = rhi_identity(id);
    if (!owner) return;
    const auto domain = owner->domain;
    ++domain->frame_epoch;
    // Copied native records carry the same slot as their source. Expire those
    // copies without revoking the command wrapper, which Qt still permits using
    // after finish() or a pass/external-recording transition.
    for (const auto &edge : retentions) if (edge.slot == 0xb1000004u && edge.target && edge.owner) {
        auto *value = entry(edge.target);
        auto *origin = value && value->type == @QRHICOMMANDBUFFER_ID@ ? rhi_identity(edge.target) : nullptr;
        if (origin && origin->domain == domain)
            rhi_expired_dependencies[edge.owner & 65535u] = edge.owner;
    }
}
static void rhi_forget(uint32_t id) {
    rhi_cleanup_forget(id);
    // Preserve expiry even after the general retention collector removes its
    // dead edge. These trivial slots never allocate during a native destructor.
    for (const auto &edge : retentions) if (edge.target == id && edge.owner &&
            ((edge.slot & 0xff000000u) == 0xb2000000u || edge.slot == 0xb1000003u || edge.slot == 0xb1000002u || edge.slot == 0xb1000004u))
        rhi_expired_dependencies[edge.owner & 65535u] = edge.owner;
    if (rhi_expired_dependencies[id & 65535u] == id) rhi_expired_dependencies[id & 65535u] = 0;
    rhi_readback_forget(id);
    auto &items = rhi_identities();
    items.erase(std::remove_if(items.begin(), items.end(), [id](const auto &item) { return item.id == id; }), items.end());
}
static bool rhi_validate(BqtRequest *r, uint32_t id) {
    auto *item = rhi_identity(id);
    if (!item || !item->domain->alive) { fail(r, ESTALE, "RHI native owner has expired"); return false; }
    if (!rhi_cleanup_access(r, item->domain)) return false;
    if (item->domain->rhi->thread() != QThread::currentThread()) {
        fail(r, EXDEV, "RHI resources require their creation thread"); return false;
    }
    return true;
}
static bool rhi_retain_root(BqtRequest *r, uint32_t id, const std::shared_ptr<RhiDomain> &domain) {
    if (id == domain->id) return true;
    auto saved = r->self; r->self = id;
    auto index = prepare_retention(r, 0xb1000001u, 0, domain->id);
    r->self = saved;
    if (r->error) return false;
    commit_retention(index, id, 0xb1000001u, 0, domain->id, nullptr);
    return true;
}
static void rhi_native_cleanup(const std::shared_ptr<RhiDomain> &domain) {
    // Registered RHI instances are confined to the GUI thread. Cleanup runs
    // before the backend is torn down, so owned wrappers can still release it.
    rhi_close_buffer_mappings(domain);
    rhi_finish_readbacks(domain);
    domain->alive = false;
    for (;;) {
        uint32_t id = 0;
        for (const auto &item : rhi_identities())
            if (item.domain == domain && item.id != domain->id) { id = item.id; break; }
        if (!id) break;
        if (auto *e = entry(id)) {
            auto value = e->value; auto destroy = e->owned ? e->destroy : nullptr;
            invalidate(id);
            if (destroy) destroy(value);
        } else rhi_forget(id);
    }
    invalidate(domain->id);
}
static bool attach_rhi_identity(BqtRequest *r, uint32_t id) {
    auto *e = entry(id);
    if (!e || rhi_identity(id)) return true;
    QRhi *root = nullptr;
    if (e->type == @QRHI_ID@) root = static_cast<QRhi *>(e->value);
    else if (e->cast) if (auto *value = static_cast<QRhiResource *>(e->cast(e->value, @QRHIRESOURCE_ID@))) root = value->rhi();
    if (!root) return true;
    if (root->thread() != QThread::currentThread()) { fail(r, EXDEV, "RHI belongs to a different native thread"); return false; }
    std::shared_ptr<RhiDomain> domain;
    if (e->type == @QRHI_ID@) {
        domain = std::make_shared<RhiDomain>(RhiDomain{id, root});
        root->addCleanupCallback([domain](QRhi *) { rhi_cleanup_begin(domain); });
        e->native_observed = true;
    } else {
        uint32_t root_id = borrow(r, root, @QRHI_ID@);
        auto *parent = rhi_identity(root_id);
        if (r->error || !parent) return false;
        domain = parent->domain;
    }
    rhi_identities().push_back({id, domain});
    if (e->type == @QRHICOMMANDBUFFER_ID@) domain->commands = static_cast<QRhiCommandBuffer *>(e->value);
    e->validate = rhi_validate;
    if (e->owned) return rhi_retain_root(r, id, domain);
    if (id != domain->id) e->native_owner = domain->id;
    return true;
}
static bool rhi_destroy_root(BqtRequest *r) {
    auto *identity = rhi_identity(r->self);
    if (!identity || identity->id != identity->domain->id) return false;
    auto *e = entry(r->self);
    e->destroying = true;
    e->destroy(e->value); // The actual native cleanup phase revokes the registry.
    return true;
}
static bool rhi_cleanup_operation(BqtRequest *r, uint32_t id) {
    auto *identity = rhi_identity(id);
    return !identity || rhi_cleanup_access(r, identity->domain);
}
static void rhi_register_batch(BqtRequest *r, uint32_t id, uint32_t owner) {
    if (rhi_identity(id)) return;
    auto *root = rhi_identity(owner);
    auto *e = entry(id);
    if (!root || !e) { fail(r, ESTALE, "RHI batch owner has expired"); return; }
    auto domain = root->domain;
    e->destroy = +[](void *p) { static_cast<QRhiResourceUpdateBatch *>(p)->release(); };
    e->owned = true;
    e->native_owner = 0;
    e->validate = rhi_validate;
    r->result.owned_handle = id;
    rhi_identities().push_back({id, domain, true, false});
    rhi_retain_root(r, id, domain);
}
static bool borrow_rhi_identity(BqtRequest *r, void *value, uint16_t type,
                               void *(*cast)(void *, uint16_t), void (*destroy)(void *), uint32_t *result) {
    if (type == @QRHIRESOURCEUPDATEBATCH_ID@) {
        auto *owner = rhi_identity(r->self);
        if (!owner || owner->id != owner->domain->id) {
            fail(r, ENOTSUP, "A pooled RHI batch requires its creating QRhi owner"); return true;
        }
        *result = insert(r, value, nullptr, type, +[](void *p) { static_cast<QRhiResourceUpdateBatch *>(p)->release(); }, false, cast);
        if (*result) rhi_register_batch(r, *result, r->self);
        return true;
    }
    if (type != @QRHI_ID@ && (!cast || !cast(value, @QRHIRESOURCE_ID@))) return false;
    *result = insert(r, value, nullptr, type, destroy, false, cast);
    return true;
}
static bool rhi_release_ready(uint32_t id) {
    auto *item = rhi_identity(id);
    return !item || !item->domain->alive || item->batch || !item->domain->rhi->isRecordingFrame();
}
static bool rhi_mutation_ready(BqtRequest *r, uint32_t id) {
    if (!rhi_release_ready(id)) { fail(r, EBUSY, "RHI resource mutation requires the frame to be submitted first"); return false; }
    return true;
}
static bool rhi_command_ready(BqtRequest *r, uint32_t id) {
    auto *item = rhi_identity(id);
    if (!item || !item->domain->alive || !item->domain->rhi->isRecordingFrame()) {
        fail(r, EPERM, "RHI command recording requires an active frame"); return false;
    }
    return true;
}
static bool rhi_pass_required(BqtRequest *r, uint32_t id, int phase) {
    auto *item = rhi_identity(id);
    if (!item || (phase == -1 ? item->domain->pass == 0 : item->domain->pass != phase)) { fail(r, EPERM, "RHI operation is not valid in the current pass"); return false; }
    return true;
}
static bool rhi_begin_frame_ready(BqtRequest *r, uint32_t id) {
    auto *item = rhi_identity(id);
    if (!item || !item->domain->alive) { fail(r, ESTALE, "RHI native owner has expired"); return false; }
    if (item->domain->frame_owned || item->domain->rhi->isRecordingFrame()) {
        fail(r, EBUSY, "An RHI frame is already active"); return false;
    }
    return true;
}
static bool rhi_end_frame_ready(BqtRequest *r, uint32_t id, bool offscreen, QRhiSwapChain *swapchain = nullptr) {
    auto *item = rhi_identity(id);
    if (!item || !item->domain->alive || !item->domain->frame_owned || !item->domain->rhi->isRecordingFrame()) {
        fail(r, EPERM, "No binding-owned RHI frame is active"); return false;
    }
    if (offscreen ? item->domain->swapchain != nullptr : !swapchain || item->domain->swapchain != swapchain) {
        fail(r, EINVAL, "RHI frame kind or swapchain differs from the active frame"); return false;
    }
    return rhi_mappings_closed(r, id);
}
static bool rhi_finish_frame_ready(BqtRequest *r, uint32_t id) {
    auto *item = rhi_identity(id);
    if (!item || !item->domain->alive) { fail(r, ESTALE, "RHI native owner has expired"); return false; }
    if (item->domain->rhi->isRecordingFrame() != item->domain->frame_owned) {
        fail(r, EPERM, "Cannot finish an RHI frame outside the binding's frame scope"); return false;
    }
    return true;
}
static void rhi_pass_changed(uint32_t id, int phase) { if (auto *item = rhi_identity(id)) item->domain->pass = phase; }
static void rhi_end_active_pass(const std::shared_ptr<RhiDomain> &domain) {
    if (domain->commands && domain->pass == 1) domain->commands->endPass();
    if (domain->commands && domain->pass == 2) domain->commands->endComputePass();
    domain->pass = 0;
}
static bool rhi_same_domain(BqtRequest *r, uint32_t first, uint32_t second) {
    if (!second) return true;
    auto *a = rhi_identity(first); auto *b = rhi_identity(second);
    if (!a || !b || a->domain != b->domain) { fail(r, EXDEV, "RHI operands belong to different native instances"); return false; }
    return true;
}
static bool rhi_dependency_domain(BqtRequest *r, uint32_t owner, uint32_t target) {
    auto *a = rhi_identity(owner); auto *b = rhi_identity(target);
    if (a && b && a->domain != b->domain) { fail(r, EXDEV, "RHI value refers to a resource from another native instance"); return false; }
    for (const auto &edge : retentions) if (edge.owner == target && edge.target && edge.target != owner)
        if (!rhi_dependency_domain(r, owner, edge.target)) return false;
    return true;
}
static bool rhi_validate_dependencies(BqtRequest *r, uint32_t id) {
    auto *e = entry(id);
    if (!e) return false;
    switch (e->type) { @RHI_VALUE_TYPES@ break; default: return true; }
    if (rhi_expired_dependencies[id & 65535u] == id) {
        fail(r, ESTALE, "An RHI descriptor or backend dependency was destroyed natively"); return false;
    }
    for (const auto &edge : retentions) if (edge.owner == id && edge.target)
        if (auto *origin = rhi_identity(edge.target))
            if (!rhi_cleanup_access(r, origin->domain)) return false;
    for (const auto &edge : retentions) if (edge.owner == id && !edge.target &&
            ((edge.slot & 0xff000000u) == 0xb2000000u || edge.slot == 0xb1000003u || edge.slot == 0xb1000002u || edge.slot == 0xb1000004u)) {
        fail(r, ESTALE, "An RHI descriptor or backend dependency was destroyed natively"); return false;
    }
    return true;
}
static bool rhi_batch_ready(BqtRequest *r, uint32_t id, bool nullable = false) {
    if (!id && nullable) return true;
    auto *item = rhi_identity(id);
    if (!item || !item->batch || !entry(id)) { fail(r, ESTALE, "RHI update batch has been released or consumed"); return false; }
    if (item->merged) { fail(r, EPERM, "Merged RHI update batches must only be released"); return false; }
    return rhi_validate(r, id);
}
static void rhi_batch_merged(uint32_t id) { if (auto *item = rhi_identity(id)) item->merged = true; }
static bool rhi_retain_argument(BqtRequest *r, uint32_t owner, uint32_t target) {
    if (!target) return true;
    if (!rhi_dependency_domain(r, owner, target)) return false;
    auto saved = r->self; r->self = owner;
    auto index = prepare_retention(r, 0xb1000002u, target, target);
    r->self = saved;
    if (r->error) return false;
    commit_retention(index, owner, 0xb1000002u, target, target, nullptr);
    return true;
}
static bool rhi_merge_dependencies(BqtRequest *r, uint32_t target, uint32_t source) {
    if (target == source) { fail(r, EINVAL, "An RHI update batch cannot merge itself"); return false; }
    if (!rhi_batch_ready(r, source) || !rhi_same_domain(r, target, source)) return false;
    std::vector<uint32_t> values;
    for (const auto &edge : retentions) if (edge.owner == source && edge.slot == 0xb1000002u) values.push_back(edge.target);
    for (auto value : values) if (!rhi_retain_argument(r, target, value)) return false;
    return true;
}
static bool rhi_release_batch(BqtRequest *r) {
    auto *item = rhi_identity(r->self);
    if (!item || !item->batch) return fail(r, ESTALE, "RHI update batch has already been released or consumed");
    return destroy_object(r);
}
static bool rhi_delete_later(BqtRequest *r) {
    auto *e = entry(r->self);
    if (!e) return fail(r, ESTALE, "RHI resource has expired");
    if (!rhi_validate(r, r->self)) return true;
    if (!e->owned) return fail(r, EPERM, "Borrowed RHI resources cannot be scheduled for deletion");
    e->pending_release = true;
    schedule_collection();
    return true;
}
static void rhi_frame_started(uint32_t root, QRhiSwapChain *swapchain) {
    if (auto *item = rhi_identity(root)) { ++item->domain->frame_epoch; item->domain->frame_owned = true; item->domain->swapchain = swapchain; }
}
static void rhi_frame_finished(uint32_t root) {
    auto *item = rhi_identity(root);
    if (!item) return;
    auto domain = item->domain;
    domain->frame_owned = false;
    domain->swapchain = nullptr;
    ++domain->frame_epoch;
    domain->pass = 0;
    domain->commands = nullptr;
    for (;;) {
        uint32_t id = 0;
        for (const auto &value : rhi_identities()) if (value.domain == domain)
            if (auto *e = entry(value.id); e && e->type == @QRHICOMMANDBUFFER_ID@) { id = value.id; break; }
        if (!id) break;
        invalidate(id);
    }
}
struct RhiFrameStartGuard {
    BqtRequest *request;
    QRhi *rhi;
    QRhiSwapChain *swapchain;
    bool committed = false;
    RhiFrameStartGuard(BqtRequest *r, QRhi *value, QRhiSwapChain *window)
        : request(r), rhi(value), swapchain(window) {}
    ~RhiFrameStartGuard() {
        if (committed || !rhi->isRecordingFrame()) return;
        // Conversion can fail after Qt has begun a frame, before Bend receives
        // its command buffer. Keep shutdown ownership if native cleanup throws.
        rhi_frame_started(request->self, swapchain);
        try {
            const auto result = swapchain ? rhi->endFrame(swapchain) : rhi->endOffscreenFrame();
            rhi_frame_finished(request->self);
            schedule_collection();
        } catch (...) {
            if (!request->error) fail(request, EFAULT, "RHI frame rollback failed");
        }
    }
};
static void rhi_shutdown() {
    for (;;) {
        std::shared_ptr<RhiDomain> domain;
        for (const auto &item : rhi_identities()) if (item.domain->frame_owned) { domain = item.domain; break; }
        if (!domain) break;
        if (domain->alive && domain->rhi->isRecordingFrame()) {
            rhi_close_buffer_mappings(domain);
            rhi_end_active_pass(domain);
            if (domain->swapchain) domain->rhi->endFrame(domain->swapchain);
            else domain->rhi->endOffscreenFrame();
        }
        rhi_frame_finished(domain->id);
    }
    std::vector<std::shared_ptr<RhiDomain>> roots;
    for (const auto &item : rhi_identities()) if (item.id == item.domain->id) roots.push_back(item.domain);
    for (const auto &root : roots) rhi_finish_readbacks(root);
}
