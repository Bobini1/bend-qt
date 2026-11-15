// QQmlListReference uses QPointer for its owner but does not own list members.
// The hidden lease survives temporary reference copies and ends with the native
// owner. It is not a QObject child, so QObject.children() remains unmodified.
constexpr uint16_t qml_list_lease_type = 65533u;
constexpr uint32_t qml_list_member_slot = 0xffffffdau;
struct QmlListLease : QObject {
    QQmlListReference reference;
    uint32_t id = 0, owner = 0;
    bool busy = false;
    explicit QmlListLease(const QQmlListReference &value) : reference(value) {}
};
static void destroy_qml_list_lease(void *value) { delete static_cast<QmlListLease *>(value); }

static uint32_t qml_list_owner(BqtRequest *r, const QQmlListReference &value) {
    auto *owner = value.object();
    if (!owner) return 0;
    auto id = borrow(r, owner, @QOBJECT_TYPE@);
    if (native_call_scope && id) native_call_scope->pin(r, id);
    return id;
}
static QmlListLease *qml_list_lease(BqtRequest *r, const QQmlListReference &value, bool create) {
    for (uint32_t i = 1; i < capacity; ++i)
        if (entries[i].value && entries[i].destroy == destroy_qml_list_lease) {
            auto *lease = static_cast<QmlListLease *>(entries[i].value);
            if (lease->reference == value) return lease;
        }
    if (!create || !value.isValid()) return nullptr;
    auto owner = qml_list_owner(r, value);
    if (!owner || r->error) return nullptr;
    auto lease = std::make_unique<QmlListLease>(value);
    auto *pointer = lease.release();
    auto id = insert(r, pointer, pointer, qml_list_lease_type, destroy_qml_list_lease, true);
    if (!id) return nullptr; // insert consumes a new owning allocation on failure.
    pointer->id = id;
    pointer->owner = owner;
    if (!set_native_owner(r, id, owner)) { invalidate(id); delete pointer; return nullptr; }
    try {
        QObject::connect(value.object(), &QObject::destroyed, pointer, [pointer] { delete pointer; });
    } catch (...) { invalidate(id); delete pointer; throw; }
    return pointer;
}
struct QmlListCall {
    QPointer<QmlListLease> lease;
    QmlListCall(BqtRequest *r, const QQmlListReference &value, QmlListLease *candidate) {
        qml_list_owner(r, value);
        if (!candidate || r->error) return;
        if (candidate->busy) { fail(r, EBUSY, "QML list is executing a native property callback"); return; }
        if (native_call_scope) native_call_scope->pin(r, candidate->id);
        if (r->error) return;
        lease = candidate;
        candidate->busy = true;
    }
    ~QmlListCall() { if (lease) lease->busy = false; }
};
static QObject *qml_list_current(QObject *object, uint32_t target_id) {
    auto *lease = static_cast<QmlListLease *>(object);
    auto *target_entry = entry(target_id);
    QPointer<QObject> target = target_entry ? target_entry->object : nullptr;
    if (!target || !lease->reference.isValid()) return nullptr;
    // Reentrant collection and write-only list properties retain conservatively.
    if (lease->busy || !lease->reference.canCount() || !lease->reference.canAt()) return target;
    NativeCallScope scope;
    BqtRequest check{};
    scope.pin(&check, target_id);
    QmlListCall call(&check, lease->reference, lease);
    if (check.error) return target;
    QPointer<QmlListLease> alive = lease;
    const auto count = lease->reference.count();
    for (qsizetype i = 0; alive && target && i < count; ++i) {
        if (!lease->reference.isValid()) return nullptr;
        // A callback can mutate a list while inspecting it. Recheck its extent.
        auto extent = lease->reference.count();
        if (!alive || !target || i >= extent) break;
        if (lease->reference.at(i) == target) return target;
    }
    return nullptr;
}
static bool retain_qml_list_member(BqtRequest *r, QmlListLease *lease, uint32_t target) {
    if (!lease || !target) return true;
    auto *member = entry(target);
    if (!member) { fail(r, ESTALE, "QML list member expired"); return false; }
    BqtRequest claim{}; claim.self = lease->id;
    // An owner/ancestor mention is internal to one native ownership subtree,
    // so it cannot keep that subtree alive by itself. Still record the edge:
    // detaching the list owner later turns it into a real cross-owner pin.
    bool ancestor = entry_inside(lease->owner, target);
    int index = prepare_retention(&claim, qml_list_member_slot, target, ancestor ? 0 : target);
    if (ancestor && index < 0 && !claim.error) {
        for (uint32_t i = 0; i < capacity; ++i)
            if (!retentions[i].owner && !retention_reserved[i]) { index = int(i); break; }
        if (index < 0) fail(&claim, ENOSPC, "Qt retention registry is full");
    }
    if (claim.error) { fail(r, claim.error, claim.message); return false; }
    // Publish before calling user-defined list callbacks: an exception after a
    // successful append must not leave an inserted member without its pin.
    commit_retention(index, lease->id, qml_list_member_slot, target, target, qml_list_current);
    return true;
}
static void clear_qml_list_members(uint32_t owner) {
    for (auto &edge : retentions) if (edge.owner == owner && edge.slot == qml_list_member_slot) edge = {};
    schedule_collection();
}
static void prune_qml_list_leases() {
    for (uint32_t i = 1; i < capacity; ++i) {
        auto &e = entries[i];
        if (!e.value || e.destroy != destroy_qml_list_lease || e.active_calls) continue;
        auto *lease = static_cast<QmlListLease *>(e.value);
        if (lease->busy) continue;
        bool retained_member = false;
        for (const auto &edge : retentions) if (edge.owner == lease->id) { retained_member = true; break; }
        if (!retained_member) { invalidate(lease->id); delete lease; }
    }
}
