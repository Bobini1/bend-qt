struct RhiBufferAllocation { uint32_t id = 0, size = 0; int type = 0; uint32_t usage = 0; int mode = 0; };
static bool rhi_record_borrowed(uint32_t id) {
    for (const auto &edge : retentions) if (edge.target == id && edge.slot == 0xb1000004u && entry(edge.owner)) return true;
    return false;
}
static SlotTable<RhiBufferAllocation> rhi_buffer_allocations;
static void rhi_buffer_clear(uint32_t id) { rhi_buffer_allocations[id & 65535u] = {}; }
static void rhi_buffer_allocation(uint32_t id, QRhiBuffer *buffer, bool created) {
    rhi_buffer_allocations[id & 65535u] = created ? RhiBufferAllocation{id, buffer->size(), int(buffer->type()), uint32_t(buffer->usage()), 0} : RhiBufferAllocation{};
}
static bool rhi_buffer_batch_access(BqtRequest *r, uint32_t id) {
    auto &allocation = rhi_buffer_allocations[id & 65535u];
    if (allocation.id == id) {
        if (allocation.mode == 1) { fail(r, EPERM, "Direct dynamic updates cannot mix with batch updates/readbacks before buffer recreation"); return false; }
        allocation.mode = 2;
    }
    return true;
}
static bool rhi_full_buffer_update(BqtRequest *r, QRhiBuffer *buffer, const QByteArray &bytes, quint32 requested) {
    if (buffer->type() != QRhiBuffer::Dynamic) return fail(r, EINVAL, "Direct update requires a Dynamic RHI buffer");
    if (!rhi_command_ready(r, r->self) || !rhi_pass_required(r, r->self, 0)) return true;
    const auto count = requested ? requested : buffer->size();
    if (count > buffer->size() || quint64(bytes.size()) < count) return fail(r, ERANGE, "Direct RHI update exceeds source or destination extent");
    auto &allocation = rhi_buffer_allocations[r->self & 65535u];
    if (allocation.id != r->self || allocation.size != buffer->size() || allocation.type != int(buffer->type()) || allocation.usage != uint32_t(buffer->usage()))
        return fail(r, ENODATA, "Buffer must be created through the binding after its latest allocation settings");
    if (allocation.mode == 2) return fail(r, EPERM, "Direct dynamic updates cannot mix with batch updates/readbacks before buffer recreation");
    buffer->fullDynamicBufferUpdateForCurrentFrame(bytes.constData(), requested);
    allocation.mode = 1;
    return true;
}
struct RhiRecordOrigin { uint32_t id = 0, owner = 0; uint64_t epoch = 0; bool frame = false; bool (*previous)(BqtRequest *, uint32_t) = nullptr; };
static SlotTable<RhiRecordOrigin> rhi_record_origins;
static bool rhi_record_valid(BqtRequest *r, uint32_t id) {
    const auto &origin = rhi_record_origins[id & 65535u];
    auto *parent = origin.id == id && entry(origin.owner) ? rhi_identity(origin.owner) : nullptr;
    if (!parent || !parent->domain->alive || (origin.frame &&
            (parent->domain->frame_epoch != origin.epoch || !parent->domain->rhi->isRecordingFrame()))) {
        fail(r, ESTALE, "Native RHI record expired with its owner or native recording state"); return false;
    }
    if (!rhi_validate(r, origin.owner)) return false;
    if (native_call_scope) native_call_scope->pin(r, origin.owner);
    return !origin.previous || origin.previous(r, id);
}
static void rhi_record_origin(BqtRequest *r, uint32_t id, uint32_t owner, bool frame) {
    auto *value = entry(id); auto *parent = rhi_identity(owner);
    if (!value || !parent) { fail(r, ESTALE, "Native RHI record has no live owner"); return; }
    rhi_record_origins[id & 65535u] = {id, owner, parent->domain->frame_epoch, frame, value->validate};
    value->validate = rhi_record_valid;
}
