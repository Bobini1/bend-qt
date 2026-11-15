// Descriptor values can be copied on a worker, while registry and dynamic
// metadata validation stay on the main thread. Entries contain only immutable
// snapshots and a shared destruction observation; capture never dereferences
// the metaobject or visits registry records on the emitting thread.
struct NativeMetadataCapture {
    std::shared_ptr<NativePointerObservation> owner;
    MetadataOrigin origin;
};
struct NativeMetadataIndex {
    QMutex mutex;
    std::map<const QMetaObject *, std::vector<NativeMetadataCapture>, std::less<const QMetaObject *>> values;
    std::map<uint32_t, std::vector<const QMetaObject *>> roots;
    std::set<const QMetaObject *, std::less<const QMetaObject *>> immutable;
};
static NativeMetadataIndex &native_metadata_index() {
    static auto *value = new NativeMetadataIndex;
    return *value;
}
static void native_metadata_mark_immutable(const QMetaObject *meta) {
    if (!meta) return;
    auto &state = native_metadata_index();
    QMutexLocker lock(&state.mutex);
    state.immutable.insert(meta);
}
static bool native_metadata_is_immutable(const QMetaObject *meta) {
    auto &state = native_metadata_index();
    QMutexLocker lock(&state.mutex);
    return state.immutable.count(meta) != 0;
}
static void native_metadata_publish(uint32_t id) {
    if (QThread::currentThread() != main_thread) return;
    const auto origin = metadata_source(id);
    if (!origin.root || !origin.expected) return;
    auto owner = native_pointer_observe(origin.root);
    if (!owner) return;
    auto &state = native_metadata_index();
    QMutexLocker lock(&state.mutex);
    if (origin.immutable_root) state.immutable.insert(origin.expected);
    auto &records = state.values[origin.expected];
    records.erase(std::remove_if(records.begin(), records.end(), [&](const auto &old) {
        return old.origin.root == origin.root || !old.owner->alive->load(std::memory_order_acquire);
    }), records.end());
    records.push_back({std::move(owner), origin});
    auto &pointers = state.roots[origin.root];
    if (std::find(pointers.cbegin(), pointers.cend(), origin.expected) == pointers.cend())
        pointers.push_back(origin.expected);
}
static void native_metadata_forget(uint32_t id) {
    auto &state = native_metadata_index();
    QMutexLocker lock(&state.mutex);
    auto root = state.roots.find(id);
    if (root == state.roots.end()) return;
    for (const auto *pointer : root->second) {
        auto found = state.values.find(pointer);
        if (found == state.values.end()) continue;
        auto &records = found->second;
        records.erase(std::remove_if(records.begin(), records.end(), [id](const auto &record) {
            return record.origin.root == id;
        }), records.end());
        if (records.empty()) state.values.erase(found);
    }
    state.roots.erase(root);
}
template<class T, class = void> struct NativeMetadataStatic : std::false_type {};
template<class T> struct NativeMetadataStatic<T, std::void_t<decltype(&T::staticMetaObject)>> : std::true_type {};
template<class T> static bool native_metadata_static(const QMetaObject *meta) {
    if constexpr (NativeMetadataStatic<T>::value) return meta == &T::staticMetaObject;
    return false;
}
static bool native_metadata_compiled(const QMetaObject *meta) {
    if (meta == &Qt::staticMetaObject) return true;
@COMPILED_METADATA@
    return false;
}
static std::optional<NativeMetadataCapture> native_metadata_capture(const QMetaObject *meta) {
    if (!meta || native_metadata_compiled(meta)) return {};
    if (QThread::currentThread() == main_thread && immutable_metaobject(meta)) return {};
    auto &state = native_metadata_index();
    QMutexLocker lock(&state.mutex);
    if (state.immutable.count(meta)) return {};
    const auto found = state.values.find(meta);
    if (found != state.values.end())
        for (auto it = found->second.crbegin(); it != found->second.crend(); ++it)
            if (it->owner->alive->load(std::memory_order_acquire)) return *it;
    throw std::system_error(ESTALE, std::generic_category(), "Native metadata has no live observed origin");
}
static bool native_metadata_live(BqtRequest *r, const NativeMetadataCapture &capture) {
    if (!capture.owner || !capture.owner->alive->load(std::memory_order_acquire)) {
        fail(r, ESTALE, "Native metadata origin was destroyed"); return false;
    }
    const auto &origin = capture.origin;
    auto *root = entry(origin.root);
    if (!root || (root->alive && !(*root->alive)->load(std::memory_order_acquire))) {
        fail(r, ESTALE, "Native metadata origin was destroyed"); return false;
    }
    if (root->validate && !root->validate(r, origin.root)) return false;
    root = entry(origin.root);
    auto *current = metadata_root_pointer(root);
    if (!root || !current || current != origin.expected || current->propertyCount() != origin.properties ||
        current->methodCount() != origin.methods || current->enumeratorCount() != origin.enumerators ||
        current->classInfoCount() != origin.infos) {
        fail(r, ESTALE, "Native metadata origin changed before delivery"); return false;
    }
    if (native_call_scope) native_call_scope->pin(r, origin.root);
    return !r->error;
}
static bool native_metadata_pin(BqtRequest *r, const NativeMetadataCapture &capture) {
    if (!native_metadata_live(r, capture)) return false;
    auto *destination = native_call_scope;
    if (!destination) { fail(r, EINVAL, "Native metadata capture needs an active conversion scope"); return false; }
    // A private descriptor copy carries the normal metadata lease. Its public
    // payload is unused: the observed root and epoch live in metadata_origins.
    // Generic snapshots can copy it through their existing value-origin path.
    NativeCallScope staging;
    staging.value_origin = capture.origin.root;
    const auto id = own(r, new QMetaClassInfo, @METADATA_LEASE_ID@);
    if (r->error) return false;
    auto *record = entry(id);
    record->read_only = true;
    record->scope_owner = 0;
    destination->pin(r, id);
    BqtRequest release{}; release.self = id;
    release_object(&release);
    if (release.error && !r->error) fail(r, release.error, release.message);
    return !r->error;
}
