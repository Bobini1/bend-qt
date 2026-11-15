namespace ConvenienceScriptSingletons {
static constexpr uint32_t owner_slot = 0xffffff9bu;
struct State {
    QByteArray uri, name;
    uint32_t owner = 0, handler = 0;
    int type_id = -1;
    bool active = true;
};
class Registration final : public QObject {
    std::shared_ptr<State> state;
public:
    explicit Registration(std::shared_ptr<State> value) : state(std::move(value)) {}
    ~Registration() override {
        state->active = false;
        if (state->type_id >= 0)
            QQmlPrivate::qmlunregister(QQmlPrivate::SingletonRegistration, quintptr(state->type_id));
        if (state->handler) callback_release_handler(std::exchange(state->handler, 0));
    }
};
struct Answer {
    QQmlEngine *engine;
    QJSValue value;
};
static bool decode(BqtRequest *r, const BqtValue &wire, void *destination) {
    if (!wire_shape(r, wire, 0)) return false;
    auto *value = get<QJSValue>(r, wire.word, @QJSVALUE_ID@, false, false);
    if (r->error) return false;
    auto *answer = static_cast<Answer *>(destination);
    // Primitive values have independent copies. Heap values must belong to
    // this engine; Qt does not permit sharing a JavaScript heap across engines.
    if (value->isString()) answer->value = QJSValue(value->toString());
    else if (value->isNumber()) answer->value = QJSValue(value->toNumber());
    else if (value->isBool()) answer->value = QJSValue(value->toBool());
    else if (value->isNull() || value->isUndefined()) answer->value = *value;
    else {
        std::vector<uint32_t> owners, visited;
        collect_value_provenance(r, wire.word, owners, visited);
        if (r->error) return false;
        bool matched = false;
        for (auto owner : owners) {
            auto *record = entry(owner);
            auto *engine = record && record->object ? qobject_cast<QJSEngine *>(record->object) : nullptr;
            if (!engine) continue;
            if (engine != answer->engine) {
                fail(r, EXDEV, "A script singleton value belongs to another JavaScript engine");
                return false;
            }
            matched = true;
        }
        if (!matched) {
            fail(r, ENOTSUP, "A script singleton value needs its engine origin");
            return false;
        }
        answer->value = *value;
    }
    return true;
}
static QJSValue create(const std::shared_ptr<State> &state, QQmlEngine *engine) {
    if (!state->active || QThread::currentThread() != main_thread) return {};
    NativeCallScope scope;
    BqtRequest request{};
    try {
        const uint32_t engine_id = borrow(&request, engine, @QML_ENGINE_ID@);
        scope.pin(&request, engine_id);
        if (request.error) { callback_report_error(request.error, request.message); return {}; }
        request.self = engine_id;
        const int edge = prepare_retention(&request, owner_slot, state->owner, state->owner);
        if (request.error) { callback_report_error(request.error, request.message); return {}; }
        commit_retention(edge, engine_id, owner_slot, state->owner, state->owner, nullptr);
        CallbackOwnedArguments arguments{sequence_value(1)};
        arguments.value.items[0].word = engine_id;
        arguments.value.items[0].borrowed_handle = engine_id;
        Answer answer{engine, {}};
        if (callback_invoke(state->handler, state->owner, arguments.take(), decode, &answer)) return {};
        return answer.value;
    } catch (const std::bad_alloc &) { callback_report_error(ENOMEM); }
      catch (...) { callback_report_error(EFAULT); }
    return {};
}
static bool register_type(BqtRequest *r) {
    NativeCallScope scope;
    for (size_t i : {0u, 3u})
        if (!r->arguments[i].size || std::memchr(r->arguments[i].text, 0, r->arguments[i].size))
            return fail(r, EINVAL, "QML singleton URI and name must be nonempty and contain no NUL");
    if (r->arguments[1].word > 254 || r->arguments[2].word > 254)
        return fail(r, ERANGE, "Invalid QML singleton version");
    auto state = std::make_shared<State>();
    state->uri = QByteArray(r->arguments[0].text, qsizetype(r->arguments[0].size));
    state->name = QByteArray(r->arguments[3].text, qsizetype(r->arguments[3].size));
    if (!BendSignalApi::qml_name(state->name))
        return fail(r, EINVAL, "A QML singleton name must begin with an uppercase letter");
    auto registration = std::make_unique<Registration>(state);
    const uint32_t owner = own(r, static_cast<QObject *>(registration.release()), @QOBJECT_ID@);
    if (r->error) return true;
    state->owner = owner;
    CallbackOwnedRegistration rollback{owner};
    QQmlPrivate::RegisterSingletonType api{};
    api.structVersion = 0;
    api.uri = state->uri.constData();
    api.version = QTypeRevision::fromVersion(int(r->arguments[1].word), int(r->arguments[2].word));
    api.typeName = state->name.constData();
    api.scriptApi = [state](QQmlEngine *engine, QJSEngine *) { return create(state, engine); };
    state->type_id = QQmlPrivate::qmlregister(QQmlPrivate::SingletonRegistration, &api);
    if (state->type_id < 0) return fail(r, EINVAL, "Qt rejected the script singleton registration");
    state->handler = r->arguments[4].word;
    r->result.word = owner;
    r->result.owned_handle = owner;
    rollback.release();
    return true;
}
}
