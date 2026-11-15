namespace BendQmlLists {
static auto *contexts = new std::map<uintptr_t, std::weak_ptr<Context>>;
struct Context {
    std::weak_ptr<RuntimeObjectState> state;
    std::shared_ptr<Observation> observed;
    size_t index;
    uint32_t anchor = 0;
    std::unique_ptr<QVariant> anchor_storage;
    std::vector<QPointer<QObject>> values;
    std::vector<uint32_t> ancestors;
    std::array<uint32_t, 6> handlers{};
    uint32_t active = 0;
    ~Context() {
        if (observed) { contexts->erase(observed->token); forget_context(observed); }
        if (entry(anchor)) invalidate(anchor);
        for (auto handler : handlers) if (handler) callback_release_handler(handler);
    }
};
static bool report(BqtRequest *r, int code, const char *message) { fail(r, code, message); return false; }
static bool retain_values(BqtRequest *r, Context &context, const std::vector<QPointer<QObject>> &values) {
    AggregateFieldUpdate update(r, context.anchor);
    std::vector<uint32_t> members, ancestors;
    for (const auto &object : values) if (object) {
        const uint32_t id = borrow(r, object.data(), @QOBJECT_ID@);
        if (r->error) return false;
        // An internal ancestor edge does not pin its own native subtree. Keep
        // the edge so detaching the owner turns it into an ordinary lease.
        if (id == context.observed->owner || entry_inside(context.observed->owner, id)) {
            if (!update.pin(id)) return false;
            if (std::find(ancestors.begin(), ancestors.end(), id) == ancestors.end()) ancestors.push_back(id);
            continue;
        }
        if (std::find(members.begin(), members.end(), id) == members.end()) {
            if (!update.pin(id)) return false;
            members.push_back(id);
        }
    }
    update.next->fields.clear();
    update.next->fields.push_back({member_slot, std::move(members)});
    if (!update.prepare()) return false;
    RetentionBatch internal;
    for (auto previous : context.ancestors)
        if (std::find(ancestors.begin(), ancestors.end(), previous) == ancestors.end()
                && !internal.add(r, context.anchor, member_slot - 1, 0, nullptr, false, false, previous)) return false;
    for (auto current : ancestors)
        if (std::find(context.ancestors.begin(), context.ancestors.end(), current) == context.ancestors.end()
                && !internal.add(r, context.anchor, member_slot - 1, current, nullptr, false, true)) return false;
    if (!update.commit() || !internal.finish(r)) return false;
    context.ancestors = std::move(ancestors);
    return true;
}
static bool changed(BqtRequest *r, const std::shared_ptr<RuntimeObjectState> &state, size_t index) {
    auto &field = state->fields[index];
    if (field.binding) field.binding->changed();
    return RuntimeQtObjects::notify(r, state, index);
}
static bool call(BqtRequest *r, const std::shared_ptr<Context> &context, unsigned kind,
                 qsizetype index, QObject *object, bool storage, QVariant &result) {
    auto state = context->state.lock();
    if (!state || !context->observed->alive->load(std::memory_order_acquire))
        return report(r, ESTALE, "The QML list owner expired");
    auto *type = context->observed->type;
    const auto &property = state->schema->properties[context->index];
    if (kind > 5) return report(r, EINVAL, "Unknown QML list operation");
    if (property.flags & (65536u << kind)) return report(r, ENOTSUP, "The QML list callback is disabled");
    if ((kind == 0 || kind == 4) && object) {
        if (object->thread() != main_thread) return report(r, EXDEV, "QML list element belongs to another thread");
        auto *meta = type->element_meta.metaObject();
        if (!meta || !object->metaObject()->inherits(meta)) return report(r, EINVAL, "QML list element has the wrong declared type");
    }
    if (!storage && context->handlers[kind]) {
        const uint32_t bit = 1u << kind;
        if (context->active & bit) return report(r, ELOOP, "Recursive QML list callback; use the Storage operation to access native backing");
        struct Guard { uint32_t &value, bit; ~Guard() { value &= ~bit; } } guard{context->active, bit};
        context->active |= bit;
        std::vector<int> arguments;
        std::vector<QVariant> values;
        if (kind == 2 || kind == 4) { arguments.push_back(@INT64_CODE@); values.push_back(QVariant::fromValue(qint64(index))); }
        if (kind == 0 || kind == 4) { arguments.push_back(type->element); values.push_back(type->value(type, object)); }
        const int output = kind == 1 ? @INT64_CODE@ : kind == 2 ? type->element : -1;
        if (!RuntimeQtObjects::invoke(r, *state, context->handlers[kind], arguments, values, output, &result)) return false;
        if (!context->observed->alive->load(std::memory_order_acquire)) return report(r, ESTALE, "The QML list owner was destroyed in its callback");
        if (kind == 1 && result.toLongLong() < 0) return report(r, ERANGE, "A QML list count cannot be negative");
        return true;
    }
    const auto size = qsizetype(context->values.size());
    if ((kind == 2 || kind == 4) && (index < 0 || index >= size))
        return report(r, ERANGE, "QML list index is outside its native extent");
    if (kind == 5 && !size) return report(r, ERANGE, "The QML list is empty");
    if (kind == 1) { result = QVariant::fromValue(qint64(size)); return true; }
    if (kind == 2) { result = type->value(type, context->values[size_t(index)].data()); return true; }
    auto values = context->values;
    if (kind == 0) values.push_back(object);
    else if (kind == 3) values.clear();
    else if (kind == 4) values[size_t(index)] = object;
    else if (kind == 5) values.pop_back();
    if (!retain_values(r, *context, values)) return false;
    context->values = std::move(values);
    return changed(r, state, context->index);
}
static QVariant dispatch(uintptr_t token, unsigned kind, qsizetype index, QObject *object, bool storage) {
    auto observed = observation(token);
    if (!observed || !observed->alive->load(std::memory_order_acquire)) { callback_report_error(ESTALE, "A QML list callback context expired"); return {}; }
    if (QThread::currentThread() != main_thread) {
        return callback_from_thread<QVariant>(observed->alive,
            [=] { return dispatch(token, kind, index, object, storage); }, [] { return QVariant{}; });
    }
    NativeCallScope scope;
    BqtRequest request{}; request.self = observed->owner;
    QVariant result;
    try {
        scope.pin(&request, observed->owner);
        auto found = contexts->find(token);
        auto context = found == contexts->end() ? std::shared_ptr<Context>{} : found->second.lock();
        if (!request.error && !context) fail(&request, ESTALE, "The QML list callback context expired");
        if (!request.error) call(&request, context, kind, index, object, storage, result);
    } catch (const std::bad_alloc &) { fail(&request, ENOMEM, "QML list callback allocation failed"); }
      catch (const std::system_error &error) { fail(&request, error.code().value(), error.what()); }
      catch (...) { fail(&request, EFAULT, "QML list callback raised an exception"); }
    if (request.error) {
        callback_report_error(request.error, request.message);
        if (observed->alive->load(std::memory_order_acquire))
            if (auto *engine = qmlEngine(observed->identity)) engine->throwError(QString::fromUtf8(request.message));
        return {};
    }
    return result;
}
static bool attach(BqtRequest *r, const std::shared_ptr<RuntimeObjectState> &state, size_t index) {
    auto *type = type_from_code(state->schema->properties[index].type);
    if (!type) return report(r, EINVAL, "Unknown QML list element type");
    register_list(type);
    auto context = std::make_shared<Context>();
    context->state = state; context->index = index;
    context->observed = observe_context(state->handle, state->object, type);
    QObject::connect(state->object, &QObject::destroyed, [alive = context->observed->alive] {
        alive->store(false, std::memory_order_release);
    });
    BqtRequest allocation{};
    {
        NativeCallScope allocation_scope;
        ValueProvenanceScope no_inputs(&allocation_scope, std::vector<uint32_t>{});
        context->anchor_storage = std::make_unique<QVariant>();
        context->anchor = insert(&allocation, context->anchor_storage.get(), nullptr, @VARIANT_ID@, nullptr, false);
    }
    if (allocation.error) return report(r, allocation.error, allocation.message);
    if (!set_native_owner(r, context->anchor, state->handle)) return false;
    contexts->emplace(context->observed->token, context);
    state->fields[index].value = type->view(type, state->object, context->observed->token, state->schema->properties[index].flags);
    state->fields[index].qml_list = std::move(context);
    return true;
}
static bool operation(BqtRequest *r) {
    NativeCallScope scope;
    auto self = RuntimeQtObjects::state(r); if (!self) return true;
    const int index = RuntimeQtObjects::property_index(r, *self, r->arguments[0]); if (index < 0) return true;
    auto context = self->fields[size_t(index)].qml_list;
    if (!context || r->arguments[1].word > 5 || r->arguments[2].word > 1)
        return fail(r, EINVAL, "This descriptor does not name a QML list operation");
    const unsigned kind = r->arguments[1].word;
    const bool storage = r->arguments[2].word;
    const qint64 at = qint64(wide_bits(r->arguments[3]));
    auto *type = context->observed->type;
    register_list(type);
    QObject *object = nullptr;
    if (kind == 0 || kind == 4) {
        auto value = BendSignalApi::read_value(r, type->element, r->arguments[4]);
        if (r->error) return true;
        object = type->object(value);
    }
    QVariant answer;
    if (!storage) {
        QVariant value;
        if (!RuntimeQtObjects::read_field(r, self, size_t(index), false, value)) return true;
        if (!context->observed->alive->load(std::memory_order_acquire)) return fail(r, ESTALE, "The QML list owner was destroyed in its getter");
        auto held = capture(value);
        if (!held || !pin(r, *held)) return true;
        QQmlListReference reference(value);
        if (!reference.isValid()) return fail(r, ESTALE, "The QML list view owner expired");
        if (kind == 0) { if (!reference.canAppend()) return fail(r, ENOTSUP, "The QML list has no append callback"); if (!reference.append(object)) return fail(r, EINVAL, "QML list element has the wrong type"); }
        else if (kind == 1) { if (!reference.canCount()) return fail(r, ENOTSUP, "The QML list has no count callback"); answer = QVariant::fromValue(qint64(reference.count())); }
        else if (kind == 2 || kind == 4) {
            if (!reference.canCount() || (kind == 2 ? !reference.canAt() : !reference.canReplace())) return fail(r, ENOTSUP, "The QML list has no indexed callback");
            if (at < 0 || at >= reference.count()) return fail(r, ERANGE, "QML list index is outside its native extent");
            if (kind == 2) answer = type->value(type, reference.at(at));
            else if (!reference.replace(at, object)) return fail(r, EINVAL, "QML list element has the wrong type");
        } else if (kind == 3) { if (!reference.canClear()) return fail(r, ENOTSUP, "The QML list has no clear callback"); reference.clear(); }
        else { if (!reference.canRemoveLast() || !reference.canCount()) return fail(r, ENOTSUP, "The QML list has no removable tail"); if (!reference.count()) return fail(r, ERANGE, "The QML list is empty"); reference.removeLast(); }
        auto *frame = CallFrame::current;
        if (frame && frame->handler_error) return fail(r, frame->handler_error, frame->handler_message.c_str());
    } else if (!call(r, context, kind, qsizetype(at), object, true, answer)) return true;
    if (kind == 1) r->result = wide_value(uint64_t(answer.toLongLong()));
    else if (kind == 2) r->result = BendSignalApi::write_value(r, type->element, answer.constData());
    return true;
}
static bool install(BqtRequest *r) {
    NativeCallScope scope;
    auto self = RuntimeQtObjects::state(r); if (!self) return true;
    const int index = RuntimeQtObjects::property_index(r, *self, r->arguments[0]); if (index < 0) return true;
    auto context = self->fields[size_t(index)].qml_list;
    const auto kind = r->arguments[1].word, handler = r->arguments[2].word;
    if (!context || kind > 5 || !handler) return fail(r, EINVAL, "Invalid QML list handler declaration");
    if (self->schema->properties[size_t(index)].flags & (65536u << kind)) return fail(r, ENOTSUP, "The QML list callback is disabled");
    const auto previous = std::exchange(context->handlers[kind], handler);
    if (previous) callback_release_handler(previous);
    return true;
}
} // namespace BendQmlLists
