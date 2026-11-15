"""Keep resource-associated dependencies attached to native swapped resources."""


def handles(g, m):
    f = m['function']
    return (f['name'] == 'swap' and not f['static'] and len(m['args']) == 1
            and not g.classes[f['declaring_class']].get('qobject')
            and m['args'][0].get('name') == f['declaring_class']
            and m['args'][0]['kind'] in ('object', 'value'))


def before_call(g, m):
    return ['if (!prepare_resource_swap(r, r->arguments[0].word)) return true;'] if handles(g, m) else []


def after_native(g, m):
    return ['finish_resource_swap(r->self, r->arguments[0].word);'] if handles(g, m) else []


def cpp(g):
    return '''
static void swap_retention_owners(uint32_t first, uint32_t second) {
    for (auto &edge : retentions) {
        if (edge.owner == first) edge.owner = second;
        else if (edge.owner == second) edge.owner = first;
    }
}
static bool prepare_resource_swap(BqtRequest *r, uint32_t other) {
    auto *first = entry(r->self), *second = entry(other);
    if (!first || !second) { fail(r, ESTALE, "Swapped object was destroyed"); return false; }
    if (r->self == other) return true;
    if (first->active_calls > 1 || second->active_calls > 1) {
        fail(r, EBUSY, "Cannot swap a resource during another active native call"); return false;
    }
    if (is_value_view_handle(r->self) || is_value_view_handle(other) || first->native_owner || second->native_owner) {
        fail(r, EPERM, "Resource swap requires independent native values"); return false;
    }
    if (!graphics_context_ready(r->self) || !graphics_context_ready(other)) {
        fail(r, EXDEV, "Both swapped graphics resources require their current context"); return false;
    }
    for (uint32_t i = 0; i < capacity; ++i)
        if (retention_reserved[i] && (retention_reservation_keys[i].owner == r->self ||
                retention_reservation_keys[i].owner == other)) {
            fail(r, EBUSY, "Resource dependency is being changed by a native call"); return false;
        }
    // Simulate the complete post-swap graph. No Qt call, allocation or callback
    // occurs while this transient graph is installed.
    swap_retention_owners(r->self, other);
    bool cycle = false;
    for (const auto &edge : retentions)
        if ((edge.owner == r->self || edge.owner == other) && edge.target &&
                reaches_token(edge.target, edge.owner)) { cycle = true; break; }
    swap_retention_owners(r->self, other);
    if (cycle) { fail(r, ELOOP, "Resource swap would create a retention cycle"); return false; }
    return true;
}
static void finish_resource_swap(uint32_t first, uint32_t second) {
    if (first == second) return;
    swap_retention_owners(first, second);
    auto *left = entry(first), *right = entry(second);
    if (left && right) std::swap(left->graphics_context, right->graphics_context);
}
'''
