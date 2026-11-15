// Only the main thread reads Entry records. Emitters on other threads capture
// an immutable identity through this small synchronized index, without touching
// or dereferencing the native pointer. Work is proportional to public bases.
struct NativePointerObservation {
    uint32_t token;
    const void *original;
    std::shared_ptr<std::atomic<bool>> alive;
    std::vector<std::pair<const void *, uint16_t>> aliases;
    std::vector<const void *> originals;
    std::atomic<bool> in_destructor{false};
    NativePointerObservation(uint32_t id, const void *pointer, std::shared_ptr<std::atomic<bool>> live)
        : token(id), original(pointer), alive(std::move(live)) {}
};
struct NativePointerCapture {
    std::shared_ptr<NativePointerObservation> observation;
    const void *pointer = nullptr;
    uint16_t type = 0;
    bool native_frame = false;
};
struct NativePointerKeyLess {
    bool operator()(const std::pair<const void *, uint16_t> &left,
                    const std::pair<const void *, uint16_t> &right) const {
        if (left.first != right.first) return std::less<const void *>{}(left.first, right.first);
        return left.second < right.second;
    }
};
struct NativePointerIndex {
    QMutex mutex;
    std::map<std::pair<const void *, uint16_t>, std::shared_ptr<NativePointerObservation>, NativePointerKeyLess> values;
    std::map<const void *, std::vector<std::shared_ptr<NativePointerObservation>>, std::less<const void *>> originals;
};
static NativePointerIndex &native_pointer_index() {
    static auto *state = new NativePointerIndex;
    return *state;
}
static SlotTable<std::shared_ptr<NativePointerObservation>> native_pointer_observations;
static std::vector<std::pair<const void *, uint16_t>> native_pointer_aliases(const Entry &);
static void native_metadata_forget(uint32_t);

static std::shared_ptr<NativePointerObservation> native_pointer_observe(uint32_t id) {
    auto *value = entry(id);
    if (!value) return {};
    auto &owner = native_pointer_observations[id & 65535u];
    if (!owner) {
        std::shared_ptr<std::atomic<bool>> alive;
        if (value->alive) alive = *value->alive;
        else {
            alive = std::make_shared<std::atomic<bool>>(true);
            value->alive = new std::shared_ptr<std::atomic<bool>>(alive);
        }
        owner = std::make_shared<NativePointerObservation>(id, value->value, std::move(alive));
    }
    return owner;
}
static void native_pointer_publish(uint32_t id) {
    auto *value = entry(id);
    if (!value) return;
    const auto aliases = native_pointer_aliases(*value);
    if (aliases.empty() && !value->object) return;
    auto owner = native_pointer_observe(id);
    auto &state = native_pointer_index();
    QMutexLocker lock(&state.mutex);
    owner->original = value->value;
    for (const void *original : {value->value, static_cast<void *>(value->object)}) {
        if (!original) continue;
        if (std::find(owner->originals.cbegin(), owner->originals.cend(), original) == owner->originals.cend())
            owner->originals.push_back(original);
        auto &identities = state.originals[original];
        if (std::find(identities.cbegin(), identities.cend(), owner) == identities.cend()) identities.push_back(owner);
    }
    for (const auto &alias : aliases) {
        if (std::find(owner->aliases.cbegin(), owner->aliases.cend(), alias) == owner->aliases.cend())
            owner->aliases.push_back(alias);
        state.values[alias] = owner;
    }
}
static void native_pointer_forget(uint32_t id) {
    auto &owner = native_pointer_observations[id & 65535u];
    if (!owner || owner->token != id) return;
    owner->alive->store(false, std::memory_order_release);
    native_metadata_forget(id);
    auto &state = native_pointer_index();
    QMutexLocker lock(&state.mutex);
    for (const auto &alias : owner->aliases) {
        auto found = state.values.find(alias);
        if (found != state.values.end() && found->second == owner) state.values.erase(found);
    }
    for (const auto *original : owner->originals) {
        auto found = state.originals.find(original);
        if (found == state.originals.end()) continue;
        auto &identities = found->second;
        identities.erase(std::remove(identities.begin(), identities.end(), owner), identities.end());
        if (identities.empty()) state.originals.erase(found);
    }
    owner.reset();
}
static NativePointerCapture native_pointer_capture(const void *pointer, uint16_t type, bool native_frame = false) {
    if (!pointer) return {};
    auto &state = native_pointer_index();
    QMutexLocker lock(&state.mutex);
    auto found = state.values.find({pointer, type});
    if (found == state.values.end()) {
        if (native_frame) return {{}, pointer, type, true};
        throw std::system_error(ESTALE, std::generic_category(), "Native pointer has no live observed identity");
    }
    if (!found->second->alive->load(std::memory_order_acquire))
        throw std::system_error(ESTALE, std::generic_category(), "Native pointer has no live observed identity");
    return {found->second, pointer, type};
}
static bool native_pointer_live(const NativePointerCapture &capture) {
    if (!capture.pointer) return true;
    const auto &owner = capture.observation;
    if (!owner) return capture.native_frame;
    if (!owner->alive->load(std::memory_order_acquire)) return false;
    const auto *value = entry(owner->token);
    if (!value || (value->alive && !(*value->alive)->load(std::memory_order_acquire))) return false;
    BqtRequest request{}; request.self = owner->token;
    NativeCallScope validation;
    validation.pin(&request, owner->token);
    if (request.error || !rhi_validate_dependencies(&request, owner->token) ||
        !value_provenance_validate(&request, owner->token) || !aggregate_validate(&request, owner->token)) return false;
    value = entry(owner->token);
    if (value && value->validate && !value->validate(&request, owner->token)) return false;
    value = entry(owner->token);
    if (!value || (value->alive && !(*value->alive)->load(std::memory_order_acquire))) return false;
    return value->cast && value->cast(value->value, capture.type) == capture.pointer;
}
static std::vector<uint32_t> native_pointer_died(const void *pointer) {
    std::vector<uint32_t> identities;
    auto &state = native_pointer_index();
    QMutexLocker lock(&state.mutex);
    auto found = state.originals.find(pointer);
    if (found == state.originals.end()) return identities;
    for (const auto &owner : found->second) {
        owner->alive->store(false, std::memory_order_release);
        owner->in_destructor.store(false, std::memory_order_release);
        if (std::find(identities.begin(), identities.end(), owner->token) == identities.end())
            identities.push_back(owner->token);
    }
    return identities;
}
static void native_pointer_destroying(const void *pointer) {
    auto &state = native_pointer_index();
    QMutexLocker lock(&state.mutex);
    auto found = state.originals.find(pointer);
    if (found == state.originals.end()) return;
    for (const auto &owner : found->second) {
        owner->in_destructor.store(true, std::memory_order_release);
        owner->alive->store(false, std::memory_order_release);
    }
}
static bool native_pointer_destructing(uint32_t id) {
    const auto &owner = native_pointer_observations[id & 65535u];
    return owner && owner->token == id && owner->in_destructor.load(std::memory_order_acquire);
}
