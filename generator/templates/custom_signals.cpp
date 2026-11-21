static bool runtime_signal_object_create(BqtRequest *);
static uint32_t generic_variant_snapshot(BqtRequest *, const QVariant &, uint32_t, bool);
static bool generic_variant_validate(BqtRequest *, uint32_t);
static bool generic_variant_finish(BqtRequest *, BqtValue &, uint32_t);
namespace BendSignalApi {
struct Snapshot;
@ARGUMENT_DECLARATIONS@
#if defined(BQT_NATIVE_PARTITIONS)
struct NativeCodec {
    int code;
    const char *name;
    QMetaType (*meta)();
    QVariant (*read)(BqtRequest *, const BqtValue &);
    BqtValue (*write)(BqtRequest *, const void *);
    bool (*assign)(BqtRequest *, void *, const void *);
    bool (*assignable)();
    bool (*matches)(QMetaType);
    QVariant (*snapshot)(const QVariant &, unsigned);
    void (*guard)(Snapshot &, const QVariant &, unsigned, bool);
};
static std::recursive_mutex partition_codec_mutex;
static std::map<int, NativeCodec> partition_codecs;
static std::map<QByteArray, int> partition_argument_names;
static const NativeCodec *partition_codec(int code) {
    std::lock_guard<std::recursive_mutex> lock(partition_codec_mutex);
    auto found = partition_codecs.find(code);
    return found == partition_codecs.end() ? nullptr : &found->second;
}
static std::vector<NativeCodec> partition_snapshot_codecs() {
    std::lock_guard<std::recursive_mutex> lock(partition_codec_mutex);
    std::vector<NativeCodec> result;
    for (const auto &row : partition_codecs)
        if (row.second.matches) result.push_back(row.second);
    return result;
}
#endif
}
// BQT_RUNTIME_BODY_BEGIN native_owned_variant_snapshot
static QVariant native_owned_variant_snapshot(const QVariant &value, unsigned depth) {
#if defined(BQT_NATIVE_PARTITIONS)
    for (const auto &codec : BendSignalApi::partition_snapshot_codecs())
        if (codec.snapshot && codec.matches(value.metaType())) return codec.snapshot(value, depth);
#else
    @OWNED_CONTAINER_VALUES@
#endif
    return value;
}
// BQT_RUNTIME_BODY_END native_owned_variant_snapshot
namespace BendSignalApi {
// BQT_RUNTIME_BODY_BEGIN meta_type
static QMetaType meta_type(int type) {
    if (type == INT_MAX) return OpaqueData::meta_type();
    if (type == (1 << 30) - 1) return QMetaType::fromType<QObject *>();  // object_identity_type
    switch (type) {
@META_TYPES@
    }
#if defined(BQT_NATIVE_PARTITIONS)
    if (auto *codec = partition_codec(type)) return codec->meta();
#endif
    return type == -1 ? QMetaType(QMetaType::Void) : runtime_argument_meta(type);
}
// BQT_RUNTIME_BODY_END meta_type
// BQT_RUNTIME_BODY_BEGIN read_value
static QVariant read_value(BqtRequest *r, int type, const BqtValue &wire) {
    if (type == INT_MAX) {
        auto value = OpaqueData::read(r, wire);
        return value ? QVariant::fromValue(std::move(*value)) : QVariant{};
    }
    switch (type) {
@READ_VALUES@
    }
#if defined(BQT_NATIVE_PARTITIONS)
    if (auto *codec = partition_codec(type)) return codec->read(r, wire);
#endif
    return runtime_argument_read(r, type, wire);
}
// BQT_RUNTIME_BODY_END read_value
// BQT_RUNTIME_BODY_BEGIN write_value
static BqtValue write_value(BqtRequest *r, int type, const void *value) {
    if (type == INT_MAX) return OpaqueData::write(r, *static_cast<const OpaqueData::Value *>(value));
    switch (type) {
@WRITE_VALUES@
    }
#if defined(BQT_NATIVE_PARTITIONS)
    if (auto *codec = partition_codec(type)) return codec->write(r, value);
#endif
    return runtime_argument_write(r, type, value);
}
// BQT_RUNTIME_BODY_END write_value
template<class T> static bool assign_native(BqtRequest *r, void *target, const void *source) {
    if constexpr (std::is_copy_assignable_v<T>) {
        if (target) *static_cast<T *>(target) = *static_cast<const T *>(source);
        return true;
    }
    fail(r, ENOTSUP, "The Qt return type is not copy assignable");
    return false;
}
// BQT_RUNTIME_BODY_BEGIN can_assign
static bool can_assign(int type) {
    if (type == INT_MAX) return true;
    switch (type) {
@ASSIGNABLE_VALUES@
    }
#if defined(BQT_NATIVE_PARTITIONS)
    if (auto *codec = partition_codec(type)) return codec->assignable();
#endif
    return type == -1 || runtime_argument_meta(type).isValid();
}
// BQT_RUNTIME_BODY_END can_assign
// BQT_RUNTIME_BODY_BEGIN assign_value
static bool assign_value(BqtRequest *r, int type, void *target, const QVariant &value) {
    if (!target || type == -1) return true;
    if (type == INT_MAX) { *static_cast<OpaqueData::Value *>(target) = *static_cast<const OpaqueData::Value *>(value.constData()); return true; }
    const void *source = meta_type(type).id() == QMetaType::QVariant ? &value : value.constData();
    switch (type) {
@ASSIGN_VALUES@
    }
#if defined(BQT_NATIVE_PARTITIONS)
    if (auto *codec = partition_codec(type)) return codec->assign(r, target, source);
#endif
    return runtime_argument_assign(r, type, target, source);
}
// BQT_RUNTIME_BODY_END assign_value
// BQT_RUNTIME_BODY_BEGIN argument_type
static int argument_type(BqtRequest *r, const BqtValue &argument) {
    const BqtValue *name = &argument, *dependency = nullptr;
    if (argument.tag == 2 && argument.count == 2) { name = &argument.items[0]; dependency = &argument.items[1]; }
    if (name->tag != 1) { fail(r, EINVAL, "An argument descriptor needs a native type name"); return INT_MIN; }
    QByteArray type(name->text, qsizetype(name->size));
    const int qml_list = BendQmlLists::argument_type(r, type, dependency);
    if (r->error || qml_list != INT_MIN) return qml_list;
    const int record = RuntimeValueTypes::argument_type(r, type, dependency);
    if (r->error || record != INT_MIN) return record;
    if (type == "BendData") return INT_MAX;
    if (type == "void") return -1;
    static const struct { const char *name; int code; } names[] = {@TYPE_NAMES@};
    for (const auto &entry : names) if (type == entry.name) return entry.code;
    const auto normalized = QMetaObject::normalizedType(type.constData());
    for (size_t i = 0; i < sizeof(names) / sizeof(*names); ++i)
        if (normalized == QMetaObject::normalizedType(names[i].name)) return names[i].code;
#if defined(BQT_NATIVE_PARTITIONS)
    {
        std::lock_guard<std::recursive_mutex> lock(partition_codec_mutex);
        auto external = partition_argument_names.find(normalized);
        if (external != partition_argument_names.end()) return external->second;
    }
#endif
    const auto registered = QMetaType::fromName(type);
    if (registered.isValid())
        for (size_t i = 0; i < sizeof(names) / sizeof(*names); ++i)
            if (registered == meta_type(names[i].code)) return names[i].code;
    const int list = RuntimeValueTypes::sequence_type(r, type, dependency);
    if (r->error || list != INT_MIN) return list;
    if (type.contains('<')) {
        fail(r, ENOTSUP, "Native container argument instantiation is absent from the selected binding inventory");
        return INT_MIN;
    }
    return runtime_argument_index(r, type, dependency);
}
// BQT_RUNTIME_BODY_END argument_type
static bool identifier(const QByteArray &value) {
    if (value.isEmpty()) return false;
    const auto text = QString::fromUtf8(value);
    if (text.toUtf8() != value) return false;
    const auto characters = text.toUcs4();
    auto first = [](char32_t c) { return c == '_' || c == '$' || QChar::isLetter(c) || QChar::category(c) == QChar::Number_Letter; };
    if (!first(characters.front())) return false;
    for (auto c : characters) {
        const auto category = QChar::category(c);
        if (!first(c) && category != QChar::Number_DecimalDigit && category != QChar::Mark_NonSpacing &&
            category != QChar::Mark_SpacingCombining && category != QChar::Mark_Enclosing && c != 0x200c && c != 0x200d)
            return false;
    }
    return true;
}
static bool qml_name(const QByteArray &value) {
    if (!identifier(value)) return false;
    return QChar::isUpper(QString::fromUtf8(value).toUcs4().front());
}
struct Declaration {
    QByteArray name, signature;
    std::vector<int> types;
    // A native signal's `X&` parameter: the value is Qt's own object, passed
    // as the X* descriptor's value. `spellings` holds the declared names.
    std::vector<bool> references;
    QList<QByteArray> spellings;
    QList<QByteArray> parameter_names;
    uint32_t revision = 0;
    bool identity = false;  // QObject.destroyed() with its ObjectIdentity argument
    // Qt lends an argument for the call (Internal.Signal.native flag 2): the
    // handler runs synchronously, and another emitting thread waits for it.
    bool blocking = false;
};
// The runtime's code for the identity QObject.destroyed passes (signals.py).
// Static descriptors count up from 0 and value types from 0x10000000; runtime
// enums count down from INT_MAX - 1 to 1 << 30. This code is below them all.
constexpr int object_identity_type = (1 << 30) - 1;
static int declared_type(BqtRequest *r, const BqtValue &argument, Declaration &result) {
    const BqtValue *name = argument.tag == 2 && argument.count == 2 ? &argument.items[0] : &argument;
    QByteArray text = name->tag == 1 ? QByteArray(name->text, qsizetype(name->size)) : QByteArray();
    result.spellings.append(QMetaObject::normalizedType(text.constData()));
    result.references.push_back(false);
    if (text == "BendObjectIdentity") { result.identity = true; return object_identity_type; }
    if (!text.endsWith('&') || text.endsWith("&&")) return argument_type(r, argument);
    result.references.back() = true;
    QByteArray pointer = text.chopped(1).trimmed() + '*';
    BqtValue renamed = *name;
    renamed.text = pointer.data();
    renamed.size = size_t(pointer.size());
    if (name == &argument) return argument_type(r, renamed);
    BqtValue items[2] = {renamed, argument.items[1]};
    BqtValue described = argument;
    described.items = items;
    return argument_type(r, described);
}
static std::optional<Declaration> declaration(BqtRequest *r, const BqtValue &wire) {
    // Two fields are used internally to resolve a named Method signature.
    if (wire.tag != 2 || (wire.count != 2 && wire.count != 3) || wire.items[0].tag != 1 || wire.items[1].tag != 2) {
        fail(r, EINVAL, "A signal declaration needs a name and argument types"); return {};
    }
    const auto &name = wire.items[0];
    Declaration result;
    result.name = QByteArray(name.text, qsizetype(name.size));
    if (!identifier(result.name)) { fail(r, EINVAL, "Invalid Qt signal name"); return {}; }
    const auto &arguments = wire.items[1];
    if (arguments.count >= size_t(INT_MAX)) { fail(r, E2BIG, "Signal arguments exceed Qt's native index range"); return {}; }
    result.signature = result.name + '(';
    for (size_t i = 0; i < arguments.count; ++i) {
        const auto &argument = arguments.items[i];
        int found = declared_type(r, argument, result);
        if (r->error || found == -1) { if (!r->error) fail(r, EINVAL, "A signal argument cannot be void"); return {}; }
        QByteArray type = meta_type(found).name();
        if (!meta_type(found).isCopyConstructible()) { fail(r, ENOTSUP, "Signal argument metatype is not copyable"); return {}; }
        result.types.push_back(found);
        if (i) result.signature += ',';
        result.signature += type;
    }
    result.signature += ')';
    if (wire.count == 3) {
        const auto &attributes = wire.items[2];
        if (!wire_shape(r, attributes, 2, 3) || attributes.items[0].tag != 2 ||
            attributes.items[1].tag || attributes.items[1].high || (attributes.items[1].word & ~3u) || attributes.items[2].tag) {
            if (!r->error) fail(r, EINVAL, "Invalid Qt signal attributes");
            return {};
        }
        const auto &names = attributes.items[0];
        if (names.count && names.count != result.types.size()) {
            fail(r, EINVAL, "Signal argument names must match its argument count"); return {};
        }
        for (size_t i = 0; i < names.count; ++i) {
            const auto &name = names.items[i];
            if (name.tag != 1) { fail(r, EINVAL, "Invalid Qt signal argument name"); return {}; }
            const QByteArray text(name.text, qsizetype(name.size));
            if (!text.isEmpty() && !identifier(text)) { fail(r, EINVAL, "Invalid Qt signal argument name"); return {}; }
            result.parameter_names.append(text);
        }
        result.blocking = attributes.items[1].word & 2u;
        if (attributes.items[1].word & 1u) {
            const auto major = attributes.items[2].word, minor = attributes.items[2].high;
            if ((major != 65535 && major > 254) || minor > 254) { fail(r, ERANGE, "Invalid Qt signal revision"); return {}; }
            result.revision = (major == 65535 ? 0xff00u : major << 8) | minor;
        } else if (attributes.items[2].word || attributes.items[2].high) {
            fail(r, EINVAL, "Signal revision requires a revision attribute"); return {};
        }
    }
    return result;
}
static void configure_signal(BendMetaObjectBuilder::MethodRef method, const Declaration &signal) {
    method.setAccess(QMetaMethod::Public);
    method.setParameterNames(signal.parameter_names);
    method.setRevision(signal.revision);
}
static bool synchronous_native_arguments(uint32_t type) {
    const auto mode = type & 3u;
    return mode == Qt::DirectConnection || mode == Qt::BlockingQueuedConnection ||
        (mode == Qt::AutoConnection && QThread::currentThread() == main_thread);
}
struct SnapshotOrigin {
    uint32_t id = 0;
    ~SnapshotOrigin() {
        if (!id) return;
        if (QThread::currentThread() == main_thread) callback_unpin(id);
        else if (auto *context = main_context.load(std::memory_order_acquire)) {
            const auto token = id;
            QMetaObject::invokeMethod(context, [token] { callback_unpin(token); }, Qt::QueuedConnection);
        }
    }
};
// Capture on the emitting thread, before raw QObject pointers can expire. Qt
// owns a reference-counted slot object, so disconnect during emission cannot
// destroy the capture function while it is running on another thread.
struct Snapshot {
    struct Guard { QObject *identity; QPointer<QObject> object; };
    std::vector<QVariant> values;
    std::vector<QVariant> roots;
    std::vector<Guard> objects;
    std::vector<NativePointerCapture> native_objects;
    std::vector<NativeMetadataCapture> metadata;
    std::vector<BendQmlLists::Capture> qml_lists;
    std::shared_ptr<SnapshotOrigin> origin;
    void guard_metadata(const QMetaObject *meta) {
        if (auto captured = native_metadata_capture(meta)) metadata.push_back(std::move(*captured));
    }
    void guard(const QVariant &value, unsigned depth = 0, bool native_frame = false) {
        if (depth > 128) throw std::length_error("Signal variant nesting exceeds 128");
        if (!depth) roots.push_back(value);
        if (auto captured = BendQmlLists::capture(value)) qml_lists.push_back(std::move(*captured));
        if (value.metaType().flags().testFlag(QMetaType::PointerToQObject)) {
            auto *object = value.value<QObject *>();
            if (!object) object = const_cast<QObject *>(value.value<const QObject *>());
            if (object) {
                if (object->thread() != main_thread) throw std::system_error(EXDEV, std::generic_category(), "Signal QObject belongs to another thread");
                objects.push_back({object, object});
            }
        } else if (value.metaType().id() == QMetaType::QVariantMap) {
            const auto map = value.toMap();
            for (auto it = map.cbegin(); it != map.cend(); ++it) guard(it.value(), depth + 1, native_frame);
        } else if (value.metaType().id() == QMetaType::QVariantHash) {
            const auto map = value.toHash();
            for (auto it = map.cbegin(); it != map.cend(); ++it) guard(it.value(), depth + 1, native_frame);
        } else if (value.metaType().id() == QMetaType::QVariantList) {
            const auto list = value.toList();
            for (const auto &item : list) guard(item, depth + 1, native_frame);
        } else if (BendValueTypes::list_of(value.metaType())) {
            const auto &list = *static_cast<const BendValueTypes::Sequence *>(value.constData());
            for (const auto &item : list.values) guard(item, depth + 1, native_frame);
        } else if (auto shape = BendValueTypes::classify(value.metaType()); shape.first && !shape.second) {
            const auto &record = *static_cast<const BendValueTypes::Value *>(value.constData());
            for (const auto &item : record.fields) guard(item, depth + 1, native_frame);
        }
#if defined(BQT_NATIVE_PARTITIONS)
        else for (const auto &codec : partition_snapshot_codecs()) {
            if (codec.guard && codec.matches(value.metaType())) {
                codec.guard(*this, value, depth, native_frame); break;
            }
        }
#else
@GUARD_CONTAINERS@
#endif
    }
    bool live() const {
        for (const auto &item : qml_lists) if (!BendQmlLists::live(item)) return false;
        for (const auto &item : objects) if (!item.object || item.object.data() != item.identity) return false;
        for (const auto &item : native_objects) if (!native_pointer_live(item)) return false;
        BqtRequest request{};
        for (const auto &item : metadata) if (!native_metadata_live(&request, item)) return false;
        if (origin && !generic_variant_validate(&request, origin->id)) return false;
        return true;
    }
    bool pin_metadata(BqtRequest *r) const {
        for (const auto &item : qml_lists) if (!BendQmlLists::pin(r, item)) return false;
        for (const auto &item : metadata) if (!native_metadata_pin(r, item)) return false;
        return true;
    }
    bool capture_origins(BqtRequest *r, uint32_t excluded) {
        if (origin || QThread::currentThread() != main_thread) return true;
        for (const auto &capture : native_objects)
            if (capture.pointer && !capture.observation) return true;
        NativeCallScope scope;
        for (auto *previous = scope.previous; previous; previous = previous->previous)
            for (uint32_t id : previous->pins) scope.pin(r, id);
        if (r->error || !pin_metadata(r)) return false;
        QVariantList contents;
        contents.reserve(qsizetype(roots.size()));
        for (const auto &value : roots) contents.append(value);
        auto held = std::make_shared<SnapshotOrigin>();
        const auto id = generic_variant_snapshot(r, contents, excluded, false);
        if (r->error) return false;
        if (!id) return true;
        if (!callback_pin(r, id)) {
            BqtRequest release{}; release.self = id; release_object(&release);
            return false;
        }
        held->id = id;
        if (auto *record = entry(id)) record->scope_owner = 0;
        BqtRequest release{}; release.self = id;
        release_object(&release);
        if (release.error) { fail(r, release.error, release.message); return false; }
        origin = std::move(held);
        return true;
    }
    bool finish_output(BqtRequest *r, BqtValue &value) const {
        return generic_variant_finish(r, value, origin ? origin->id : 0);
    }
    bool stage_native_arguments(BqtRequest *r, CallbackNativeArguments &arguments, uint32_t receiver) {
        for (auto &capture : native_objects) {
            if (capture.observation || !capture.pointer) continue;
            switch (capture.type) {
@TEMPORARY_POINTERS@
            default:
                fail(r, ENOTSUP, "Native pointer argument has no temporary borrowing policy");
                return false;
            }
            if (r->error) return false;
            // Still inside the emitting call: a value Qt lends (no observed
            // identity) keeps its call-scoped capture.
            const bool read_only = capture.read_only;
            capture = native_pointer_capture(capture.pointer, capture.type, true);
            capture.read_only = read_only;
        }
        return true;
    }
};
class Receiver final {
    Declaration declaration;
    std::vector<QMetaType> metatypes;
    uint32_t id, handler, sender;
    uint32_t mode;
public:
    void invoke(void **arguments) const noexcept {
        // Copy immutable state before a synchronous Bend handler disconnects.
        const uint32_t connection_id = id, function = handler, object = sender;
        try {
            const auto types = declaration.types;
            Snapshot snapshot;
            snapshot.values.reserve(types.size());
            for (size_t i = 0; i < types.size(); ++i) {
                const auto type = metatypes[i];
                // A reference parameter's slot holds the object itself; its
                // descriptor's value is the pointer to it.
                const void *source = arguments[i + 1];
                const void *pointer = source;
                if (declaration.references[i]) source = &pointer;
                snapshot.values.push_back(native_owned_snapshot(type.id() == QMetaType::QVariant
                    ? *static_cast<const QVariant *>(source) : QVariant(type, source)));
                snapshot.guard(snapshot.values.back(), 0, declaration.blocking || synchronous_native_arguments(mode));
            }
            BqtRequest capture{};
            if (!snapshot.capture_origins(&capture, object)) {
                callback_report_error(capture.error, capture.message); return;
            }
            auto deliver = [types, function, object, snapshot = std::move(snapshot)]() mutable {
                try {
                    if (!snapshot.live()) { callback_report_error(ESTALE, "A signal argument QObject was destroyed before delivery"); return; }
                    BqtRequest conversion{};
                    NativeCallScope scope;
                    CallbackNativeArguments native_arguments;
                    if (!snapshot.stage_native_arguments(&conversion, native_arguments, object)) {
                        callback_report_error(conversion.error, conversion.message); return;
                    }
                    if (!snapshot.capture_origins(&conversion, object)) {
                        callback_report_error(conversion.error, conversion.message); return;
                    }
                    CallbackOwnedArguments values{sequence_value(types.size())};
                    for (size_t i = 0; i < types.size(); ++i) {
                        const auto &value = snapshot.values[i];
                        const void *data = meta_type(types[i]).id() == QMetaType::QVariant ? &value : value.constData();
                        values.value.items[i] = write_value(&conversion, types[i], data);
                        if (conversion.error) break;
                    }
                    if (!conversion.error && !snapshot.finish_output(&conversion, values.value) && !conversion.error)
                        fail(&conversion, EPROTO, "Signal argument origin repair failed");
                    if (conversion.error) callback_report_error(conversion.error, conversion.message);
                    else {
                        int error = callback_invoke(function, object, values.take(), callback_decode_unit, nullptr);
                        if (error) callback_report_error(error);
                    }
                } catch (const std::bad_alloc &) { callback_report_error(ENOMEM); }
                  catch (const std::length_error &) { callback_report_error(E2BIG); }
                  catch (const std::system_error &error) { callback_report_error(error.code().value(), error.what()); }
                  catch (...) { callback_report_error(EFAULT); }
            };
            if (!callback_signal_call_with_type(connection_id, std::move(deliver), mode, declaration.blocking)) callback_signal_error(connection_id, EPIPE);
        } catch (const std::bad_alloc &) { callback_signal_error(connection_id, ENOMEM); }
          catch (const std::length_error &) { callback_signal_error(connection_id, E2BIG); }
          catch (const std::system_error &error) { callback_signal_error(connection_id, error.code().value()); }
          catch (...) { callback_signal_error(connection_id, EFAULT); }
    }
    Receiver(Declaration value, uint32_t connection, uint32_t function, uint32_t object, uint32_t type)
        : declaration(std::move(value)), id(connection), handler(function), sender(object), mode(type) {
        metatypes.reserve(declaration.types.size());
        for (int argument : declaration.types) metatypes.push_back(meta_type(argument));
    }
};
} // namespace BendSignalApi
@ARGUMENT_DEFINITIONS@
} // namespace bendqt

// QMetaObject::connect(QMetaMethod, functor) owns its functor through Qt's
// ordinary reference-counted callable wrapper. This header-only adapter feeds
// the already type-checked runtime signature to that wrapper. It imports no
// QObjectPrivate/QSlotObjectBase implementation symbols or private headers.
namespace QtPrivate {
template<> struct FunctionPointer<bendqt::BendSignalApi::Receiver> {
    enum { ArgumentCount = 0, IsPointerToMemberFunction = false };
    using Arguments = List<>;
    using ReturnType = void;
    template<class Args, class R> static void call(bendqt::BendSignalApi::Receiver &receiver, void *, void **arguments) {
        receiver.invoke(arguments);
    }
};
}
namespace bendqt {
namespace BendSignalApi {
static bool create(BqtRequest *r) {
    return runtime_signal_object_create(r);
}
static bool matches(const QMetaMethod &method, const Declaration &declaration) {
    if (method.parameterCount() != int(declaration.types.size())) return false;
    for (size_t i = 0; i < declaration.types.size(); ++i) {
        if (declaration.references[i]) {
            if (QMetaObject::normalizedType(method.parameterTypeName(int(i)).constData()) != declaration.spellings[qsizetype(i)]) return false;
        } else if (!BendQualifiedTypes::compatible(method.parameterMetaType(int(i)), meta_type(declaration.types[i]))) return false;
    }
    return true;
}
static bool destroyed_signal(const QMetaMethod &method) {
    return method.enclosingMetaObject() == &QObject::staticMetaObject && method.name() == "destroyed";
}
static std::optional<QMetaMethod> find_member(BqtRequest *r, const QMetaObject *meta, const Declaration &declaration, bool signal_only) {
    const int index = signal_only ? meta->indexOfSignal(declaration.signature) : meta->indexOfMethod(declaration.signature);
    if (index >= 0) {
        auto method = meta->method(index);
        if (matches(method, declaration)) return method;
    }
    // Internal module-qualified metatypes deliberately have different names
    // from Qt's original declarations. Resolve those aliases by their exact
    // originating interfaces, never by an unqualified name or numeric ID.
    std::optional<QMetaMethod> found;
    bool name_found = false;
    for (int i = meta->methodCount() - 1; i >= 0; --i) {
        auto method = meta->method(i);
        if ((signal_only && method.methodType() != QMetaMethod::Signal) || method.name() != declaration.name) continue;
        name_found = true;
        if (!matches(method, declaration)) continue;
        if (found && found->methodSignature() != method.methodSignature()) {
            fail(r, EINVAL, "Ambiguous QObject member argument types"); return {};
        }
        if (!found) found = method;
    }
    if (!found) fail(r, name_found ? EINVAL : ENOENT, name_found ? "Qt member argument type mismatch" : "QObject does not declare this member signature");
    return found;
}
static std::optional<QMetaMethod> find(BqtRequest *r, QObject *object, const Declaration &signal, bool native_destination = false) {
    auto method = find_member(r, object->metaObject(), signal, true);
    if (!method) return {};
    if (signal.identity != destroyed_signal(*method) && !(native_destination && !signal.identity)) {
        fail(r, signal.identity ? EINVAL : ENOTSUP, signal.identity ? "Only QObject.destroyed passes an ObjectIdentity"
             : "Connect QObject.destroyed() for the identity of a destroyed object"); return {};
    }
    return method;
}
// QObject.destroyed(): the registry forgets the sender, and closes its other
// connections, before Qt reaches this slot. This connection outlives that
// step, passes the sender's identity and closes after its single delivery.
static bool connect_destroyed(BqtRequest *r, QObject *object, uint32_t type, uint32_t handler) {
    CallbackConnectionGuard guard;
    guard.id = new_connection(r, handler);
    if (r->error) return true;
    const uint32_t id = guard.id, sender = r->self;
    connection(id)->sender = 0;
    connection(id)->context = new QObject;
    auto made = QObject::connect(object, &QObject::destroyed, connection(id)->context, [handler, id, sender, type] {
        auto deliver = [handler, id, sender] {
            try {
                CallbackOwnedArguments arguments{sequence_value(1)};
                arguments.value.items[0].word = sender;
                int error = callback_invoke(handler, 0, arguments.take(), callback_decode_unit, nullptr);
                if (error) callback_report_error(error);
            } catch (const std::bad_alloc &) { callback_report_error(ENOMEM); }
              catch (...) { callback_report_error(EFAULT); }
            if (auto *c = connection(id)) close_connection(*c);
        };
        if (!callback_signal_call_with_type(id, std::move(deliver), type, false)) callback_signal_error(id, EPIPE);
    }, Qt::DirectConnection);
    if (!made) return fail(r, EINVAL, "Qt signal connection failed");
    connection(id)->connection = new QMetaObject::Connection(made);
    r->result.word = id;
    guard.keep = true;
    return true;
}
// The runtime observes these signals (signals.RESERVED_EMISSIONS).
static bool reserved_emission(const QMetaMethod &method) {
    static const struct { const char *owner, *name; } reserved[] = {@RESERVED_EMISSIONS@};
    for (const auto &item : reserved)
        if (method.name() == item.name && qstrcmp(method.enclosingMetaObject()->className(), item.owner) == 0) return true;
    return false;
}
static bool connect_common(BqtRequest *r, bool typed) {
    NativeCallScope scope;
    auto *object = get<QObject>(r, r->self, @QOBJECT_ID@);
    if (r->error) return true;
    auto signal = declaration(r, r->arguments[0]);
    if (!signal) return true;
    auto method = find(r, object, *signal);
    if (!method) return true;
    const uint32_t type = typed ? r->arguments[1].word : uint32_t(Qt::AutoConnection);
    if (!callback_connection_type(r, type, true)) return true;
    const uint32_t handler = r->arguments[typed ? 2 : 1].word;
    if (signal->identity) return connect_destroyed(r, object, type, handler);
    if (signal->blocking && (type & 3u) == Qt::QueuedConnection)
        return fail(r, ENOTSUP, "Qt lends this signal's arguments for the call; it cannot be delivered asynchronously");
    CallbackConnectionGuard guard;
    guard.id = new_connection(r, handler);
    if (r->error) return true;
    auto *context = new QObject;
    connection(guard.id)->context = context;
    auto made = QMetaObject::connect(object, *method, context,
        Receiver(*signal, guard.id, handler, r->self, type),
        Qt::ConnectionType(uint32_t(Qt::DirectConnection) | (type & uint32_t(Qt::SingleShotConnection))));
    if (!made) return fail(r, EINVAL, "Cannot connect the Bend signal handler");
    connection(guard.id)->connection = new QMetaObject::Connection(made);
    r->result.word = guard.id;
    guard.keep = true;
    return true;
}
static bool connect(BqtRequest *r) { return connect_common(r, false); }
static bool connect_typed(BqtRequest *r) { return connect_common(r, true); }
static bool connect_member(BqtRequest *r) {
    NativeCallScope scope;
    auto *sender = get<QObject>(r, r->self, @QOBJECT_ID@);
    auto *receiver = get<QObject>(r, r->arguments[1].word, @QOBJECT_ID@);
    if (r->error) return true;
    const uint32_t kind = r->arguments[3].word, type = r->arguments[4].word;
    if (kind > 1 || !callback_connection_type(r, type, false)) {
        if (!r->error) fail(r, EINVAL, "Invalid signal destination kind");
        return true;
    }
    auto declaration_value = declaration(r, r->arguments[0]);
    if (!declaration_value) return true;
    auto signal = find(r, sender, *declaration_value, true);
    if (!signal) return true;
    const auto &member = r->arguments[2];
    if (member.tag != 2 || (kind == 0 && member.count != 4) || (kind == 1 && member.count != 3))
        return fail(r, EINVAL, "Invalid signal destination descriptor");
    BqtValue signature{}; signature.tag = 2; signature.count = 2; signature.items = member.items;
    auto destination = declaration(r, signature);
    if (!destination) return true;
    auto method = find_member(r, receiver->metaObject(), *destination, kind != 0);
    if (!method) return true;
    if (destination->types.size() > declaration_value->types.size())
        return fail(r, EINVAL, "Signal and destination argument counts are incompatible");
    for (size_t i = 0; i < destination->types.size(); ++i)
        if (!BendQualifiedTypes::compatible(meta_type(declaration_value->types[i]), meta_type(destination->types[i])))
            return fail(r, EINVAL, "Signal and destination arguments are incompatible");
    CallbackConnectionGuard guard;
    guard.id = new_connection(r, 0);
    if (r->error) return true;
    // The pinned Qt index-based connection accepts the already validated
    // native interfaces, including our internal qualified names. Supply the
    // exact source metatype IDs for queued copies rather than asking Qt to
    // resolve ambiguous unqualified names. Qt owns this array on success.
    auto argument_types = std::make_unique<int[]>(declaration_value->types.size() + 1);
    for (size_t i = 0; i < declaration_value->types.size(); ++i)
        argument_types[i] = meta_type(declaration_value->types[i]).id();
    const auto made = QMetaObject::connect(sender, signal->methodIndex(), receiver, method->methodIndex(), int(type), argument_types.get());
    if (!made) return fail(r, (type & uint32_t(Qt::UniqueConnection)) ? EEXIST : EINVAL, "Qt rejected the signal destination connection");
    argument_types.release();
    connection(guard.id)->connection = new QMetaObject::Connection(made);
    if (signal->enclosingMetaObject() == &QObject::staticMetaObject && signal->name() == "destroyed") {
        // Registry invalidation is an earlier destroyed observer. Keep this
        // native destination connected until Qt delivers it, then retire the
        // binding handle from a main-thread context registered afterwards.
        auto *record = connection(guard.id);
        record->sender = 0;
        record->context = new QObject;
        const auto id = guard.id;
        QObject::connect(sender, &QObject::destroyed, record->context, [id] {
            if (auto *record = connection(id)) close_connection(*record);
        });
    }
    r->result.word = guard.id;
    guard.keep = true;
    return true;
}
static bool emit_signal(BqtRequest *r) {
    NativeCallScope scope;
    auto *object = get<QObject>(r, r->self, @QOBJECT_ID@);
    if (r->error) return true;
    auto signal = declaration(r, r->arguments[0]);
    if (!signal) return true;
    if (signal->identity) return fail(r, EINVAL, "Only QObject.destroyed passes an ObjectIdentity");
    // As PySide does, emit through the meta-object, which also reaches
    // QPrivateSignal signals; only the runtime's own observers are refused.
    auto method = find_member(r, object->metaObject(), *signal, true);
    if (!method) return true;
    if (reserved_emission(*method)) return fail(r, EPERM, "The runtime observes this Qt signal, so Bend cannot emit it");
    const auto &wire = r->arguments[1];
    if (!wire_shape(r, wire, 2, signal->types.size())) return true;
    std::vector<QVariant> values;
    values.reserve(signal->types.size());
    for (size_t i = 0; i < signal->types.size(); ++i) {
        values.push_back(read_value(r, signal->types[i], wire.items[i]));
        if (r->error) return true;
    }
    std::vector<void *> arguments(values.size() + 1, nullptr);
    for (size_t i = 0; i < values.size(); ++i) {
        void *value = meta_type(signal->types[i]).id() == QMetaType::QVariant ? &values[i] : const_cast<void *>(values[i].constData());
        // A reference parameter's slot holds the object the pointer names.
        arguments[i + 1] = signal->references[i] ? *static_cast<void **>(value) : value;
        if (signal->references[i] && !arguments[i + 1]) return fail(r, EINVAL, "A reference signal argument cannot be null");
    }
    QMetaObject::activate(object, method->enclosingMetaObject(), method->methodIndex() - method->enclosingMetaObject()->methodOffset(), arguments.data());
    return true;
}
} // namespace BendSignalApi
