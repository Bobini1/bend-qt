// Observable collection relationships supplement QObject's native parent tree.
// Reserve every slot before mutation: addActions must never partly succeed and
// then discover that its remaining lifetime edges cannot be represented.
static uint32_t retention_token(BqtRequest *r, const QObject *object, bool required = true)
{
    if (!object) return 0;
    for (uint32_t i = 1; i < capacity; ++i)
        if (entries[i].value && entries[i].object == object)
            return token(i, entries[i].generation);
    if (required) fail(r, ESTALE, "Collection member has no live handle");
    return 0;
}

struct RetainedInternalDevice { uint32_t owner; QObject *device; };
static SlotTable<RetainedInternalDevice> retained_internal_devices;

static void retention_set_internal_device(uint32_t owner, QObject *device)
{
    if (owner && entry(owner)) retained_internal_devices[owner & 65535u] = {owner, device};
}

static QObject *retention_internal_device(uint32_t owner)
{
    if (!entry(owner)) return nullptr;
    const auto &record = retained_internal_devices[owner & 65535u];
    return record.owner == owner ? record.device : nullptr;
}

static QObject *retained_explicit_style(QObject *object, uint32_t)
{
    // QWidget::style() may return a private stylesheet proxy. An explicit style
    // is conservatively pinned until another binding setStyle call or owner
    // destruction, rather than confusing that proxy with the original style.
    for (const auto &edge : retentions) {
        if (!edge.owner || edge.current != retained_explicit_style) continue;
        auto *owner = entry(edge.owner), *target = entry(edge.target);
        if (owner && owner->object == object && target) return target->object;
    }
    return nullptr;
}

struct RetentionBatch {
    struct Change {
        int index;
        uint32_t owner, slot, key, target;
        QObject *(*current)(QObject *, uint32_t);
        bool remove;
    };
    std::vector<Change> changes;
    ~RetentionBatch() { for (const auto &change : changes) if (change.index >= 0) unreserve_retention(change.index); }

    bool add(BqtRequest *r, uint32_t owner, uint32_t slot, uint32_t target,
             QObject *(*current)(QObject *, uint32_t), bool remove = false,
             bool constructor = false, uint32_t key = UINT32_MAX)
    {
        owner = render_factory_retention_owner(owner);
        if (!owner && !constructor) return true; // Clearing a reverse relationship.
        bool collection = key == UINT32_MAX;
        if (collection) key = target;
        if (!target && collection) {
            if (constructor) return true;
            fail(r, EINVAL, "Collection member must not be null"); return false;
        }
        for (const auto &change : changes)
            if (change.owner == owner && change.slot == slot && change.key == key) return true;
        int index = -1;
        if (constructor) {
            if (target && !entry(target)) { fail(r, ESTALE, "Invalid constructor dependency"); return false; }
            if (!target) return true;
            for (uint32_t i = 0; i < capacity; ++i)
                if (!retentions[i].owner && !retention_reserved[i]) { index = int(i); break; }
            if (index < 0) { fail(r, ENOSPC, "Qt retention registry is full"); return false; }
        } else {
            BqtRequest checked = *r;
            checked.self = owner;
            index = prepare_retention(&checked, slot, key, remove ? 0 : target);
            if (checked.error) { fail(r, checked.error, checked.message); return false; }
        }
        changes.push_back(Change{index, owner, slot, key, target, current, remove});
        if (index >= 0) reserve_retention(index, owner, slot, key);
        return true;
    }

    bool finish(BqtRequest *r, uint32_t constructed = 0, bool unconditional = false)
    {
        bool accepted = true;
        for (const auto &change : changes) {
            uint32_t owner_id = render_factory_retention_owner(change.owner ? change.owner : constructed);
            auto *owner = entry(owner_id), *target = entry(change.target);
            if (!owner || (change.target && !target)) {
                accepted = false;
                fail(r, ESTALE, "A retained object was destroyed during the native call");
                continue;
            }
            // QObject constructors commonly receive their parent. Native parent
            // ownership already keeps the child alive; a reverse dependency
            // would create a permanent parent/child retention cycle.
            if (constructed && target && entry_inside(owner_id, change.target)) continue;
            if (constructed && target && reaches_token(change.target, owner_id)) {
                accepted = false;
                fail(r, ELOOP, "Constructed Qt dependency would create a retention cycle");
                continue;
            }
            QObject *actual = (unconditional || !change.current) ? (target ? target->object : nullptr)
                                            : change.current(owner->object, change.key);
            bool matches = change.remove ? actual == nullptr : actual == (target ? target->object : nullptr);
            if (!matches) { accepted = false; continue; }
            commit_retention(change.index, owner_id, change.slot, change.key,
                             change.remove ? 0 : change.target, change.current);
        }
        if (!accepted) {
            if (!r->error) fail(r, EINVAL, "Qt rejected a retained collection member");
            // A failed constructor cannot return an inaccessible live object.
            if (constructed) if (auto *e = entry(constructed)) {
                auto *value = e->value;
                auto destroy = e->destroy;
                invalidate(constructed);
                destroy(value);
            }
        }
        return accepted;
    }
};
