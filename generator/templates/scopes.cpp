struct ScopeResource { uint32_t id; uint8_t kind; };
struct ResourceScope {
    uint32_t parent;
    bool closing = false;
    std::vector<ScopeResource> resources;
    size_t compact_at = 4096;
};
static std::map<uint32_t, ResourceScope> resource_scopes;
static std::map<std::pair<uint8_t, uint32_t>, uint32_t> auxiliary_scope_owners;
static uint32_t next_resource_scope;

static bool scope_resource_live(uint32_t owner, const ScopeResource &resource) {
    if (resource.kind == 0) { auto *e = entry(resource.id); return e && e->scope_owner == owner; }
    if (resource.kind == 1) { auto *c = connection(resource.id); return c && c->scope_owner == owner; }
    auto it = auxiliary_scope_owners.find({resource.kind, resource.id});
    return it != auxiliary_scope_owners.end() && it->second == owner;
}
static void scope_append(uint32_t owner, ResourceScope &scope, ScopeResource resource) {
    if (scope.resources.size() >= scope.compact_at) {
        auto &values = scope.resources;
        values.erase(std::remove_if(values.begin(), values.end(), [owner](const ScopeResource &value) {
            return !scope_resource_live(owner, value);
        }), values.end());
        scope.compact_at = std::max(size_t(4096), values.size() * 2);
    }
    scope.resources.push_back(resource);
}

static bool scope_valid(uint32_t id) {
    auto it = resource_scopes.find(id);
    return !id || (it != resource_scopes.end() && !it->second.closing);
}
static bool scope_adopt_result(BqtRequest *r, QObject *object, uint32_t target, std::vector<uint32_t> *adopted) {
    // Reply decoding runs before the handler scope closes. Move newly owned
    // results (and their owned QObject ancestors) to the calling operation.
    for (auto *value = object; value; value = value->parent()) {
        for (uint32_t i = 1; i < capacity; ++i) {
            auto &e = entries[i];
            if (!e.value || e.object != value || !e.owned || !r->scope || e.scope_owner != r->scope) continue;
            if (target == r->scope) continue;
            auto owner = resource_scopes.find(target);
            if (!target || owner == resource_scopes.end() || owner->second.closing) {
                fail(r, EBUSY, "A new QObject result needs a live calling scope or detachFromScope before returning"); return false;
            }
            if (adopted) adopted->push_back(token(i, e.generation));
            scope_append(target, owner->second, {token(i, e.generation), 0});
            e.scope_owner = target;
        }
    }
    return true;
}
static bool scope_adopt_native_result(BqtRequest *r, uint32_t id, uint32_t target, std::vector<uint32_t> *adopted) {
    // Native-object interface aliases can point into an owned value or child.
    // Promote the actual observed entry and any native owner, never the alias.
    for (uint32_t depth = 0; id && depth < capacity; ++depth) {
        auto *value = entry(id);
        if (!value) { fail(r, ESTALE, "A native pointer result expired"); return false; }
        if (value->object) return scope_adopt_result(r, value->object, target, adopted);
        uint32_t parent = value->native_owner;
        if (value->owned && r->scope && value->scope_owner == r->scope && target != r->scope) {
            auto owner = resource_scopes.find(target);
            if (!target || owner == resource_scopes.end() || owner->second.closing) {
                fail(r, EBUSY, "A new native object result needs a live calling scope or detachFromScope before returning"); return false;
            }
            if (adopted) adopted->push_back(id);
            scope_append(target, owner->second, {id, 0});
            value->scope_owner = target;
        }
        id = parent;
    }
    return true;
}
static uint32_t scope_track(BqtRequest *r, uint32_t id, uint8_t kind) {
    const uint32_t owner = r && r->scope ? r->scope : native_request_scope;
    if (!id || !owner) return 0;
    auto it = resource_scopes.find(owner);
    if (it == resource_scopes.end() || it->second.closing)
        throw std::domain_error("Qt resource scope has ended");
    scope_append(owner, it->second, {id, kind});
    if (kind >= 2) {
        try { auxiliary_scope_owners[{kind, id}] = owner; }
        catch (...) { it->second.resources.pop_back(); throw; }
    }
    return owner;
}
static void scope_forget_aux(uint8_t kind, uint32_t id) {
    auxiliary_scope_owners.erase({kind, id});
}
static bool scope_release_aux(BqtRequest *r, uint8_t kind, uint32_t id) {
    auto owner = auxiliary_scope_owners.find({kind, id});
    if (owner == auxiliary_scope_owners.end()) return fail(r, ESTALE, "The scoped Qt resource has ended");
    if (owner->second != r->scope) return fail(r, EPERM, "The Qt resource belongs to another scope");
    auxiliary_scope_owners.erase(owner);
    return true;
}
static bool scope_open(BqtRequest *r) {
    uint32_t parent = r->arguments[0].word;
    if (!scope_valid(parent)) return fail(r, ESTALE, "The parent Qt scope has ended");
    if (next_resource_scope == UINT32_MAX)
        return fail(r, ENOSPC, "Qt resource scope capacity exhausted");
    uint32_t id = ++next_resource_scope;
    resource_scopes.emplace(id, ResourceScope{parent, false, {}});
    r->result.word = id;
    return true;
}
static bool scope_close(BqtRequest *r) {
    uint32_t id = r->arguments[0].word;
    auto it = resource_scopes.find(id);
    if (!id || it == resource_scopes.end()) return fail(r, ESTALE, "Qt resource scope has ended");
    if (it->second.closing) return fail(r, EBUSY, "Qt resource scope is already closing");
    for (const auto &child : resource_scopes)
        if (child.second.parent == id) return fail(r, EBUSY, "Join nested Qt work before closing its scope");
    it->second.closing = true;
    int first_error = 0;
    const char *first_message = nullptr;
    while (!it->second.resources.empty()) {
        auto resource = it->second.resources.back();
        it->second.resources.pop_back();
        BqtRequest cleanup{};
        cleanup.self = resource.id;
        try {
            if (resource.kind == 0) {
                auto *e = entry(resource.id);
                if (!e || e->scope_owner != id) continue;
                e->scope_owner = 0;
                release_object(&cleanup);
            } else if (resource.kind == 1) {
                auto *c = connection(resource.id);
                if (!c || c->scope_owner != id) continue;
                c->scope_owner = 0;
                close_connection(*c);
            } else if (resource.kind == 3) {
                auto owner = auxiliary_scope_owners.find({resource.kind, resource.id});
                if (owner == auxiliary_scope_owners.end() || owner->second != id) continue;
                auxiliary_scope_owners.erase(owner);
                OpaqueData::release(resource.id);
            } else {
                auto owner = auxiliary_scope_owners.find({resource.kind, resource.id});
                if (owner == auxiliary_scope_owners.end() || owner->second != id) continue;
                auxiliary_scope_owners.erase(owner);
                @QML_HANDLER_RELEASE@
            }
        } catch (const std::bad_alloc &) { fail(&cleanup, ENOMEM, "Qt scoped cleanup allocation failed"); }
          catch (...) { fail(&cleanup, EFAULT, "Qt scoped cleanup raised an exception"); }
        if (cleanup.error && cleanup.error != ESTALE && !first_error) {
            first_error = cleanup.error;
            first_message = own_request_message(cleanup.message ? cleanup.message : "Qt scope cleanup failed");
        }
    }
    resource_scopes.erase(it);
    if (first_error) {
        return fail(r, first_error, first_message);
    }
    return true;
}
static bool scope_transfer(BqtRequest *r) {
    uint8_t kind = uint8_t(r->arguments[0].word);
    uint32_t id = r->arguments[1].word;
    if (r->arguments[2].word > 1) return fail(r, EINVAL, "Invalid Qt scope transfer mode");
    bool detach = r->arguments[2].word != 0;
    if (r->arguments[0].word > 2 || !r->scope) return fail(r, EINVAL, "Scope transfer requires a live typed Qt scope");
    auto current = resource_scopes.find(r->scope);
    if (current == resource_scopes.end() || current->second.closing) return fail(r, ESTALE, "Qt scope has ended");
    uint32_t parent = detach ? 0 : current->second.parent;
    if (!detach && !parent) return fail(r, EINVAL, "The root scope has no parent; use detachFromScope for explicit cleanup");
    uint32_t *owner = nullptr;
    if (kind == 0) { auto *e = entry(id); if (e) owner = &e->scope_owner; }
    else if (kind == 1) { auto *c = connection(id); if (c) owner = &c->scope_owner; }
    else { auto it = auxiliary_scope_owners.find({kind, id}); if (it != auxiliary_scope_owners.end()) owner = &it->second; }
    if (!owner) return fail(r, ESTALE, "The Qt resource has ended");
    if (*owner != r->scope) return fail(r, EPERM, "The current scope does not own this resource's cleanup");
    if (parent) {
        auto it = resource_scopes.find(parent);
        if (it == resource_scopes.end() || it->second.closing) return fail(r, ESTALE, "Parent Qt scope has ended");
        scope_append(parent, it->second, {id, kind});
    }
    *owner = parent;
    r->result.word = id;
    return true;
}
