namespace DynamicProperties {
static constexpr uint32_t origin_slot = 0xffffff98u;
struct Field {
    uint32_t key = 0, origin = 0;
    int error = 0;
    std::string message;
    BendSignalApi::Snapshot guards;
    QVariant value;
};
struct Pending {
    QByteArray name;
    bool awaiting_event = true;
};
struct State {
    uint32_t owner = 0, next_key = 0;
    QPointer<QObject> object;
    std::map<QByteArray, std::shared_ptr<Field>> fields;
    std::vector<Pending *> pending;
};
static std::map<QObject *, std::shared_ptr<State>> states;

static std::shared_ptr<State> state(QObject *object, uint32_t owner) {
    auto found = states.find(object);
    if (found != states.end() && found->second->owner == owner) return found->second;
    auto value = std::make_shared<State>();
    value->owner = owner;
    value->object = object;
    states[object] = value;
    return value;
}
static bool usable(BqtRequest *r, const std::shared_ptr<Field> &field) {
    if (field->error) { fail(r, field->error, field->message.c_str()); return false; }
    if (!generic_variant_validate(r, field->origin)) return false;
    if (!field->guards.live()) { fail(r, ESTALE, "A dynamic property value origin expired"); return false; }
    return field->guards.pin_metadata(r);
}
// The old payload and its origin stay pinned until both Qt's assignment and
// every reentrant event handler have finished. Retention changes precede the
// event, so a handler can read or replace the new value immediately.
static std::shared_ptr<Field> capture(BqtRequest *r, const std::shared_ptr<State> &host,
                                    const QByteArray &name, const QVariant &value) {
    auto found = host->fields.find(name);
    std::shared_ptr<Field> previous = found == host->fields.end() ? nullptr : found->second;
    auto next = std::make_shared<Field>();
    if (previous) next->key = previous->key;
    else {
        if (host->next_key == UINT32_MAX) { fail(r, EOVERFLOW, "Dynamic property keys exhausted"); return {}; }
        next->key = ++host->next_key;
    }
    next->value = native_owned_snapshot(value);
    next->guards.guard(next->value);
    BqtValue origin{};
    origin.word = generic_variant_snapshot(r, next->value, host->owner, false);
    origin.owned_handle = origin.word;
    ConversionValueGuard captured(origin);
    if (r->error) return {};
    // Allocate the map node before committing the lease. Replacing its shared
    // pointer is then noexcept, even if the native call recursively writes it.
    if (!previous) host->fields.emplace(name, std::shared_ptr<Field>{});
    BqtRequest claim{}; claim.self = host->owner;
    const int edge = prepare_retention(&claim, origin_slot, next->key, origin.word);
    if (claim.error) {
        if (!previous) host->fields.erase(name);
        fail(r, claim.error, claim.message); return {};
    }
    if (origin.word && native_call_scope) native_call_scope->pin(r, origin.word);
    if (r->error) { if (!previous) host->fields.erase(name); return {}; }
    commit_retention(edge, host->owner, origin_slot, next->key, origin.word, nullptr);
    if (auto *record = entry(origin.word)) {
        record->read_only = true;
        record->scope_owner = 0;
        record->pending_release = true;
    }
    next->origin = captured.release().word;
    host->fields.find(name)->second = next;
    schedule_collection();
    return next;
}
static void erase_if_current(const std::shared_ptr<State> &host, const QByteArray &name,
                             const std::shared_ptr<Field> &field) {
    auto found = host->fields.find(name);
    if (found != host->fields.end() && found->second == field) {
        host->fields.erase(found);
        for (auto &edge : retentions)
            if (edge.owner == host->owner && edge.slot == origin_slot && edge.key == field->key) edge = {};
        schedule_collection();
    }
}
struct PendingWrite {
    std::shared_ptr<State> host;
    Pending value;
    PendingWrite(std::shared_ptr<State> object, const QByteArray &name) : host(std::move(object)), value{name, true} {
        host->pending.push_back(&value);
    }
    ~PendingWrite() {
        auto found = std::find(host->pending.begin(), host->pending.end(), &value);
        if (found != host->pending.end()) host->pending.erase(found);
    }
};
static bool write(BqtRequest *r, QObject *object, const char *name, const QVariant &value) {
    if (!name) return fail(r, EINVAL, "A property name cannot be null");
    // Declared properties keep their own native setters and NOTIFY semantics.
    if (object->metaObject()->indexOfProperty(name) >= 0) {
        r->result.word = object->setProperty(name, value); return true;
    }
    auto host = state(object, r->self);
    const QByteArray key(name);
    NativeCallScope old_payload;
    auto found = host->fields.find(key);
    auto previous = found == host->fields.end() ? nullptr : found->second;
    // Do not validate the old value: replacing/removing a stale value is valid.
    if (previous && previous->origin) old_payload.pin(r, previous->origin);
    if (r->error) return true;
    // Capture only this call's inputs, not the origin of the previous payload.
    NativeCallScope capture_scope;
    if (old_payload.previous) for (auto id : old_payload.previous->pins) capture_scope.pin(r, id);
    if (r->error) return true;
    PendingWrite pending(host, key);
    auto next = capture(r, host, key, value);
    if (!next) return true;
    r->result.word = object->setProperty(name, next->value);
    if (!next->value.isValid()) erase_if_current(host, key, next);
    return true;
}
static bool read(BqtRequest *r, QObject *object, const char *name) {
    if (!name) return fail(r, EINVAL, "A property name cannot be null");
    const QByteArray key(name);
    std::shared_ptr<Field> field;
    auto found = states.find(object);
    if (found != states.end() && found->second->owner == r->self) {
        auto item = found->second->fields.find(key);
        if (item != found->second->fields.end()) field = item->second;
    }
    if (field && !usable(r, field)) return true;
    const QVariant value = field ? field->value : object->property(name);
    if (!field && object->metaObject()->indexOfProperty(name) < 0 && value.isValid()) {
        auto host = state(object, r->self);
        field = capture(r, host, key, value);
        if (!field) return true;
    }
    // An outgoing QVariant is an ordinary independent value handle. Give it
    // its own snapshot; later replacement of this property cannot change it.
    NativeCallScope output;
    if (field) {
        if (field->origin) output.pin(r, field->origin);
    } else if (output.previous) for (auto id : output.previous->pins) output.pin(r, id);
    if (r->error) return true;
    BqtValue result{};
    result.word = own(r, new QVariant(value), @QVARIANT_ID@);
    result.owned_handle = result.word;
    ConversionValueGuard converted(result);
    if (r->error || !GenericVariants::attach_origins(r, result.word, value, output.pins)) return true;
    if (field && !generic_variant_finish(r, converted.value, field->origin)) return true;
    r->result = converted.release();
    return true;
}
static void changed(QObject *object, const QByteArray &name) {
    auto found = states.find(object);
    if (found == states.end()) return;
    auto host = found->second;
    for (auto pending = host->pending.rbegin(); pending != host->pending.rend(); ++pending)
        if ((*pending)->name == name && (*pending)->awaiting_event) {
            (*pending)->awaiting_event = false; return;
        }
    auto item = host->fields.find(name);
    if (item == host->fields.end()) return;
    NativeCallScope old_payload;
    auto previous = item->second;
    BqtRequest request{};
    if (previous && previous->origin) old_payload.pin(&request, previous->origin);
    auto inputs = old_payload.previous ? old_payload.previous->pins : std::vector<uint32_t>{};
    // Event observation must run before any user event filter or virtual
    // QObject::event handler, including raw native calls to setProperty.
    NativeCallScope capture_scope;
    for (auto id : inputs) capture_scope.pin(&request, id);
    try {
        std::shared_ptr<Field> next;
        if (!request.error) next = capture(&request, host, name, object->property(name.constData()));
        if (next && !next->value.isValid()) erase_if_current(host, name, next);
    } catch (const std::system_error &error) { fail(&request, error.code().value(), error.what()); }
      catch (const std::bad_alloc &) { fail(&request, ENOMEM, "Cannot retain a dynamic property value"); }
      catch (const std::exception &error) { fail(&request, EINVAL, error.what()); }
    if (request.error) {
        auto current = host->fields.find(name);
        if (current != host->fields.end() && current->second) {
            current->second->error = request.error;
            current->second->message = request.message ? request.message : "Dynamic property observation failed";
        }
        callback_report_error(request.error, request.message);
    }
}
} // namespace DynamicProperties
static void dynamic_properties_event(QObject *object, QEvent *event) {
    if (QThread::currentThread() != main_thread || !event || event->type() != QEvent::DynamicPropertyChange) return;
    try { DynamicProperties::changed(object, static_cast<QDynamicPropertyChangeEvent *>(event)->propertyName()); }
    catch (const std::bad_alloc &) { callback_report_error(ENOMEM, "Cannot observe a dynamic property change"); }
    catch (const std::exception &error) { callback_report_error(EINVAL, error.what()); }
}
static void dynamic_properties_forget(uint32_t id) {
    for (auto item = DynamicProperties::states.begin(); item != DynamicProperties::states.end(); ) {
        if (item->second->owner == id) item = DynamicProperties::states.erase(item);
        else ++item;
    }
}
