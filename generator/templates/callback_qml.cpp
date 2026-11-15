// Public Qt QML APIs provide dynamic typed properties, signals and methods
// through composite QML types. No private QMetaObjectBuilder ABI is used.
static bool callback_qml_installed;
static QTemporaryDir *callback_qml_directory;
static uint64_t callback_qml_source_number;

// Handler tokens QML code may name. QML holds no ownership: releasing the
// QmlHandler gives the handler back, and later invocations fail.
static std::vector<uint32_t> callback_qml_handlers;

QVariant CallbackQmlBridge::invoke(quint32 method, const QVariantList &arguments)
{
    auto *engine = qmlEngine(this);
    if (std::find(callback_qml_handlers.begin(), callback_qml_handlers.end(), handler_) == callback_qml_handlers.end()) {
        if (engine) engine->throwError(QStringLiteral("This BendBridge has no live Bend handler"));
        return {};
    }
    try {
        BqtRequest conversion{};
        uint32_t receiver = borrow(&conversion, this, @QOBJECT_ID@);
        if (conversion.error) return {};
        CallbackOwnedArguments wire{sequence_value(2)};
        wire.value.items[0].word = method;
        wire.value.items[1] = write_@VARIANT_LIST_CODEC@(&conversion, arguments);
        if (conversion.error) return {};
        std::optional<QVariant> result;
        auto decode = [](BqtRequest *r, const BqtValue &value, void *destination) {
            auto decoded = read_@VARIANT_CODEC@(r, value);
            if (!decoded) return false;
            *static_cast<std::optional<QVariant> *>(destination) = std::move(decoded);
            return true;
        };
        int error = callback_invoke(handler_, receiver, wire.take(), decode, &result);
        if (error || !result) {
            if (engine) engine->throwError(QStringLiteral("Bend QML handler failed (%1)").arg(error));
            return {};
        }
        return std::move(*result);
    } catch (const std::bad_alloc &) {
        callback_report_error(ENOMEM);
        if (engine) engine->throwError(QStringLiteral("Bend QML handler allocation failed"));
        return {};
    } catch (...) {
        callback_report_error(EFAULT);
        if (engine) engine->throwError(QStringLiteral("Bend QML handler native conversion failed"));
        return {};
    }
}

static bool callback_qml_handler(BqtRequest *r)
{
    callback_qml_handlers.push_back(r->arguments[0].word);
    try { scope_track(r, r->arguments[0].word, 2); }
    catch (...) { callback_qml_handlers.pop_back(); throw; }
    r->result.word = r->arguments[0].word;
    return true;
}

static bool callback_qml_release(BqtRequest *r)
{
    auto it = std::find(callback_qml_handlers.begin(), callback_qml_handlers.end(), r->self);
    if (it == callback_qml_handlers.end()) return fail(r, ESTALE, "This QML handler was already released");
    callback_qml_handlers.erase(it);
    scope_forget_aux(2, r->self);
    callback_release_handler(r->self);
    return true;
}

static bool callback_qml_install(BqtRequest *r)
{
    if (!callback_qml_installed) {
        if (qmlRegisterType<CallbackQmlBridge>("Bend.Qt", 1, 0, "BendBridge") < 0)
            return fail(r, EINVAL, "Cannot register the Bend QML bridge");
        callback_qml_installed = true;
    }
    return true;
}

static bool callback_qml_register_source(BqtRequest *r)
{
    if (!callback_qml_install(r) || r->error) return true;
    for (uint32_t i : {0u, 3u}) {
        const auto &value = r->arguments[i];
        if (!value.size || std::memchr(value.text, 0, value.size))
            return fail(r, EINVAL, "QML URI and type name must be nonempty and contain no NUL");
    }
    if (r->arguments[1].word > 254 || r->arguments[2].word > 254)
        return fail(r, ERANGE, "QML version components must be between 0 and 254");
    if (!callback_qml_directory) {
        callback_qml_directory = new QTemporaryDir;
        if (!callback_qml_directory->isValid()) {
            delete callback_qml_directory;
            callback_qml_directory = nullptr;
            return fail(r, EIO, "Cannot create storage for runtime QML type declarations");
        }
        QObject::connect(application, &QObject::destroyed, [] {
            delete callback_qml_directory;
            callback_qml_directory = nullptr;
        });
    }
    const QString path = callback_qml_directory->filePath(QStringLiteral("BendType%1.qml").arg(++callback_qml_source_number));
    QFile source(path);
    if (!source.open(QIODevice::WriteOnly)) return fail(r, EIO, "Cannot open the runtime QML type source");
    const auto &content = r->arguments[4];
    if (source.write(content.text, qint64(content.size)) != qint64(content.size)) {
        source.remove();
        return fail(r, EIO, "Cannot write the runtime QML type source");
    }
    source.close();
    const QByteArray uri(r->arguments[0].text, qsizetype(r->arguments[0].size));
    const QByteArray name(r->arguments[3].text, qsizetype(r->arguments[3].size));
    int result = qmlRegisterType(QUrl::fromLocalFile(path), uri.constData(),
                                 int(r->arguments[1].word), int(r->arguments[2].word), name.constData());
    if (result < 0) { source.remove(); return fail(r, EINVAL, "Qt rejected the QML composite type registration"); }
    r->result.word = uint32_t(result);
    return true;
}
