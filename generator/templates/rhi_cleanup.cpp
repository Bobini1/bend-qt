struct RhiCleanupKey {};
// One Bend cleanup handler. Replacing or removing it gives the handler back.
struct RhiCleanupRegistration {
    std::weak_ptr<RhiDomain> domain;
    std::shared_ptr<RhiCleanupKey> native_key;
    uint32_t owner, key, handler;
    bool keyed, invoked = false;
    ~RhiCleanupRegistration() { callback_release_handler(handler); }
};
// The domain whose cleanup handler is running: its resources stay usable
// for exactly that long.
static RhiDomain *rhi_cleanup_running;
static auto &rhi_cleanup_registrations() {
    static auto *records = new std::vector<std::shared_ptr<RhiCleanupRegistration>>;
    return *records;
}
static void rhi_cleanup_forget(uint32_t id) {
    auto &records = rhi_cleanup_registrations();
    records.erase(std::remove_if(records.begin(), records.end(), [id](const auto &record) { return record->owner == id; }), records.end());
}
static bool rhi_cleanup_access(BqtRequest *r, const std::shared_ptr<RhiDomain> &domain) {
    bool causal = rhi_cleanup_running == domain.get();
    auto error = lifetime_cleanup_access[unsigned(domain->alive) * 4 + unsigned(domain->cleaning) * 2 + unsigned(causal)];
    if (error) { fail(r, error, "RHI resources are available only to their active cleanup callback"); return false; }
    return true;
}
static void rhi_cleanup_begin(const std::shared_ptr<RhiDomain> &domain) {
    domain->cleaning = true;
    if (auto *e = entry(domain->id)) e->destroying = true;
    domain->cleanup_remaining = 0;
    for (const auto &record : rhi_cleanup_registrations())
        if (record->owner == domain->id && !record->invoked) ++domain->cleanup_remaining;
    if (!domain->cleanup_remaining) rhi_native_cleanup(domain);
}
static void rhi_cleanup_invoke(const std::shared_ptr<RhiCleanupRegistration> &record) noexcept {
    auto domain = record->domain.lock();
    if (!domain || !domain->alive || record->invoked) return;
    record->invoked = true;
    auto *outer = rhi_cleanup_running;
    rhi_cleanup_running = domain.get();
    try {
        auto arguments = sequence_value(1);
        arguments.items[0].word = record->key;
        callback_invoke(record->handler, domain->id, arguments, callback_decode_unit, nullptr);
    } catch (const std::bad_alloc &) { callback_report_error(ENOMEM); }
      catch (...) { callback_report_error(EFAULT); }
    rhi_cleanup_running = outer;
    if (domain->cleanup_remaining) --domain->cleanup_remaining;
    if (!domain->cleanup_remaining) {
        try { rhi_native_cleanup(domain); }
        catch (...) { callback_report_error(EFAULT); }
    }
}
// Takes the handler once registered; Bend keeps it when this fails.
static bool rhi_add_cleanup(BqtRequest *r, uint32_t key, uint32_t handler, bool keyed) {
    NativeCallScope scope;
    auto *root = get<QRhi>(r, r->self, @QRHI@);
    auto *identity = rhi_identity(r->self);
    if (r->error || !identity) return true;
    auto domain = identity->domain;
    if (domain->cleaning) return fail(r, EBUSY, "Cannot register handlers during native RHI cleanup");
    auto &records = rhi_cleanup_registrations();
    size_t position = records.size();
    if (keyed) for (size_t i = 0; i < records.size(); ++i)
        if (records[i]->owner == r->self && records[i]->keyed && records[i]->key == key) { position = i; break; }
    auto record = std::make_shared<RhiCleanupRegistration>();
    record->domain = domain; record->owner = r->self; record->key = key; record->handler = 0; record->keyed = keyed;
    record->native_key = position < records.size() ? records[position]->native_key : std::make_shared<RhiCleanupKey>();
    if (position == records.size()) records.reserve(records.size() + 1);
    try {
        QRhi::CleanupCallback invoke = [record](QRhi *) { rhi_cleanup_invoke(record); };
        if (keyed) root->addCleanupCallback(record->native_key.get(), invoke);
        else root->addCleanupCallback(invoke);
    } catch (...) {
        // A Qt allocation failure may have inserted an empty std::function.
        // Remove the key rather than leave a destructor-time exception behind.
        if (keyed) {
            root->removeCleanupCallback(record->native_key.get());
            if (position < records.size()) records.erase(records.begin() + position);
        }
        throw;
    }
    record->handler = handler;
    if (position < records.size()) records[position] = record;
    else records.push_back(record);
    return true;
}
static bool rhi_remove_cleanup(BqtRequest *r, uint32_t key) {
    NativeCallScope scope;
    auto *root = get<QRhi>(r, r->self, @QRHI@);
    auto *identity = rhi_identity(r->self);
    if (r->error || !identity) return true;
    if (identity->domain->cleaning) return fail(r, EBUSY, "Cannot remove handlers during native RHI cleanup");
    auto &records = rhi_cleanup_registrations();
    for (auto it = records.begin(); it != records.end(); ++it)
        if ((*it)->owner == r->self && (*it)->keyed && (*it)->key == key) {
            root->removeCleanupCallback((*it)->native_key.get());
            records.erase(it);
            break;
        }
    return true;
}
