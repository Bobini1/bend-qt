namespace OpaqueData {
static std::atomic<const BqtHost *> host;

static void release(uint32_t token) noexcept {
    auto *owner = host.load(std::memory_order_acquire);
    if (token && owner && owner->data_release) owner->data_release(token);
}
static void drain() {
    if (auto *owner = host.load(std::memory_order_acquire); owner && owner->data_drain) owner->data_drain();
}
static void shutdown() { drain(); host.store(nullptr, std::memory_order_release); }

struct Control {
    uint32_t token;
    explicit Control(uint32_t value) : token(value) {}
    ~Control() { release(token); }
};
struct Value {
    std::shared_ptr<Control> data;
};
static QMetaType meta_type() {
    static const int id = qRegisterMetaType<Value>("BendData");
    return QMetaType(id);
}
static std::optional<Value> read(BqtRequest *r, const BqtValue &wire) {
    auto *owner = host.load(std::memory_order_acquire);
    if (wire.tag != 3 || !wire.word || wire.high || !owner || !owner->data_exists || !owner->data_retain || !owner->data_exists(wire.word)) {
        fail(r, EINVAL, "Expected a live opaque Bend value"); return {};
    }
    auto control = std::make_shared<Control>(0);
    int error = owner->data_retain(wire.word);
    if (error) { fail(r, error, "Cannot retain an opaque Bend value"); return {}; }
    control->token = wire.word;
    return Value{std::move(control)};
}
static BqtValue write(BqtRequest *r, const Value &value) {
    BqtValue result{};
    auto *owner = host.load(std::memory_order_acquire);
    if (!value.data || !owner || !owner->data_clone) { fail(r, EINVAL, "An opaque Bend value is uninitialized"); return result; }
    uint32_t token = owner->data_clone(value.data->token);
    if (!token) { fail(r, ENOSPC, "Cannot copy an opaque Bend value"); return result; }
    result.tag = 3; result.word = token; result.owned_data = token;
    return result;
}
static bool adopt(BqtRequest *r) {
    uint32_t token = r->arguments[0].word;
    auto *owner = host.load(std::memory_order_acquire);
    if (!r->scope || !owner || !owner->data_exists || !owner->data_exists(token)) return fail(r, ESTALE, "Opaque Bend value has expired");
    scope_track(r, token, 3);
    r->result.tag = 3; r->result.word = token;
    return true;
}
static bool release_lease(BqtRequest *r) {
    uint32_t token = r->arguments[0].word;
    if (!scope_release_aux(r, 3, token)) return false;
    release(token);
    return true;
}
#if @HAS_VARIANT@
static bool variant(BqtRequest *r) {
    auto value = read(r, r->arguments[0]);
    if (!value) return false;
    r->result.word = own(r, new QVariant(QVariant::fromValue(std::move(*value))), @VARIANT_ID@);
    return !r->error;
}
static bool from_variant(BqtRequest *r) {
    auto *value = get<QVariant>(r, r->self, @VARIANT_ID@);
    if (!value) return false;
    if (value->metaType() != meta_type()) return fail(r, EINVAL, "QVariant does not contain Bend data");
    r->result = write(r, *static_cast<const Value *>(value->constData()));
    return !r->error;
}
#endif
static bool count(BqtRequest *r) {
    drain();
    auto *owner = host.load(std::memory_order_acquire);
    r->result.word = owner && owner->data_count ? owner->data_count() : 0;
    return true;
}
} // namespace OpaqueData
