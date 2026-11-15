struct NativeRhiMapping {
    uint32_t owner;
    QRhiBuffer *buffer;
    std::shared_ptr<RhiDomain> domain;
    void *address = nullptr;
    size_t size;
    bool active = false;
    NativeRhiMapping(uint32_t id, QRhiBuffer *value, const std::shared_ptr<RhiDomain> &source)
        : owner(id), buffer(value), domain(source), size(value->size()) {}
    void close() {
        if (!active) return;
        active = false;
        // Every live mapping is closed before frame submission or root teardown.
        if (domain->alive && entry(owner)) buffer->endFullDynamicBufferUpdateForCurrentFrame();
    }
    ~NativeRhiMapping() { close(); }
};
static auto &rhi_buffer_mappings() { static auto *items = new std::vector<std::weak_ptr<NativeRhiMapping>>; return *items; }
static void rhi_close_buffer_mappings(const std::shared_ptr<RhiDomain> &domain) {
    for (const auto &weak : rhi_buffer_mappings()) if (auto item = weak.lock(); item && item->domain == domain) item->close();
}
static bool rhi_mappings_closed(BqtRequest *r, uint32_t id) {
    auto *identity = rhi_identity(id);
    if (!identity) { fail(r, ESTALE, "RHI owner has expired"); return false; }
    for (const auto &weak : rhi_buffer_mappings()) if (auto item = weak.lock(); item && item->active && item->domain == identity->domain) {
        fail(r, EBUSY, "End dynamic buffer mappings before recording a pass or submitting the frame"); return false;
    }
    return true;
}
static std::shared_ptr<NativeRhiMapping> rhi_begin_buffer_mapping(BqtRequest *r, uint32_t id, QRhiBuffer *buffer) {
    auto *identity = rhi_identity(id);
    if (!identity || !identity->domain->alive || !identity->domain->frame_owned || !identity->domain->rhi->isRecordingFrame()) {
        fail(r, EPERM, "Dynamic buffer mapping requires a binding-owned active frame"); return {};
    }
    if (identity->domain->pass || buffer->type() != QRhiBuffer::Dynamic) {
        fail(r, EPERM, "Dynamic buffer mapping requires a Dynamic buffer outside a render or compute pass"); return {};
    }
    auto &items = rhi_buffer_mappings();
    items.erase(std::remove_if(items.begin(), items.end(), [](const auto &weak) { return weak.expired(); }), items.end());
    for (const auto &weak : items) if (auto item = weak.lock(); item && item->owner == id && item->active) {
        fail(r, EBUSY, "Dynamic buffer already has an active mapping"); return {};
    }
    // Allocate every binding-owned record before the native mapping starts.
    auto result = std::make_shared<NativeRhiMapping>(id, buffer, identity->domain);
    items.push_back(result);
    result->address = buffer->beginFullDynamicBufferUpdateForCurrentFrame();
    result->active = result->address != nullptr;
    if (!result->active) { fail(r, ENOTSUP, "The RHI backend did not provide a dynamic buffer mapping"); return {}; }
    return result;
}
static bool rhi_end_buffer_mapping(BqtRequest *r, uint32_t id) {
    for (const auto &weak : rhi_buffer_mappings()) if (auto item = weak.lock(); item && item->owner == id && item->active) {
        item->close(); return true;
    }
    return fail(r, ESTALE, "This buffer has no active dynamic mapping");
}
static bool observe_rhi_mapping(BqtRequest *r, const MemoryView &view, bool) {
    auto state = view.rhi_mapping;
    if (!state || !state->active || !state->domain->alive || !state->domain->frame_owned || !state->domain->rhi->isRecordingFrame()) {
        fail(r, ESTALE, "Dynamic buffer mapping has ended"); return false;
    }
    auto *buffer = get<QRhiBuffer>(r, view.owner, @QRHIBUFFER_ID@, false, true);
    if (r->error) return false;
    if (buffer != state->buffer || buffer->size() != view.size) { fail(r, ESTALE, "Dynamic buffer storage has changed"); return false; }
    return true;
}
