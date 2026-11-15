static bool prepare_consuming_move(BqtRequest *r, uint32_t id)
{
    auto *value = entry(id);
    if (!value) { fail(r, ESTALE, "Move source was destroyed"); return false; }
    bool owned = value->owned && !value->native_owner && !value->shared_managed && !is_value_view_handle(id);
    bool held = retained(id);
    bool active = value->active_calls > 1;
    if (!lifetime_move[unsigned(owned) * 8 + unsigned(held) * 4 + unsigned(active) * 2 + unsigned(value->read_only)]) {
        fail(r, owned && !value->read_only ? EBUSY : EPERM,
             "A consuming move requires an owned, writable, unretained and idle source");
        return false;
    }
    return true;
}

static bool prepare_move_assignment(BqtRequest *r, uint32_t source)
{
    if (source == r->self) { fail(r, EINVAL, "Self move assignment is not supported"); return false; }
    for (const auto &edge : retentions)
        if (edge.owner == source && reaches_token(edge.target, r->self)) {
            fail(r, ELOOP, "Moving this value would create a retention cycle");
            return false;
        }
    return true;
}

struct MoveInput {
    uint32_t source;
    uint32_t exception_destination = 0;
    bool armed = false;
    bool committed = false;
    explicit MoveInput(uint32_t id) : source(id) {}
    MoveInput(const MoveInput &) = delete;
    // Once the native call starts, failure consumes the source too. This avoids
    // exposing a native moved-from value whose useful operations are unspecified.
    ~MoveInput() {
        if (!armed) return;
        // A throwing assignment may already have changed its destination.
        // Dispose it while both its old and source dependencies remain pinned.
        // This branch is permitted only for an exclusive, owned destination.
        if (!committed && exception_destination)
            if (auto *value = entry(exception_destination)) {
                auto *storage = value->value;
                auto destroy = value->destroy;
                invalidate(exception_destination);
                destroy(storage);
            }
        if (auto *value = entry(source)) {
            auto *storage = value->value;
            auto destroy = value->destroy;
            invalidate(source);
            destroy(storage);
        }
    }
    void complete(uint32_t destination, bool replace) {
        if (!entry(destination)) return;
        committed = true;
        if (replace)
            for (auto &edge : retentions) if (edge.owner == destination) edge = {};
        for (auto &edge : retentions)
            if (edge.owner == source) edge.owner = destination;
    }
};
