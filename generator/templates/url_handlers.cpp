struct UrlHandlerLease {
    QString scheme;
    QByteArray method;
    QPointer<QObject> receiver;
    QMetaObject::Connection destroyed;
    uint32_t token = 0;
};
static QMap<QString, uint32_t> url_handlers;

static void delete_url_handler(void *pointer) {
    auto *lease = static_cast<UrlHandlerLease *>(pointer);
    if (url_handlers.value(lease->scheme) == lease->token) {
        QDesktopServices::unsetUrlHandler(lease->scheme);
        url_handlers.remove(lease->scheme);
    }
    QObject::disconnect(lease->destroyed);
    delete lease;
}

static void release_url_handler(uint32_t token) {
    auto *record = entry(token);
    if (!record || record->destroy != delete_url_handler) return;
    auto *lease = record->value;
    invalidate(token);
    delete_url_handler(lease);
}

static void unset_url_handler(QString scheme) {
    scheme = scheme.toLower();
    auto id = url_handlers.value(scheme);
    if (id) release_url_handler(id);
    else QDesktopServices::unsetUrlHandler(scheme);
}

static bool set_url_handler(BqtRequest *r, QString scheme, QObject *receiver,
                            uint32_t target, const QByteArray &method) {
    scheme = scheme.toLower();
    if (!receiver) { unset_url_handler(scheme); return true; }
    if (receiver->thread() != main_thread) {
        fail(r, EXDEV, "URL handler receiver must belong to the GUI thread"); return false;
    }
    const int index = receiver->metaObject()->indexOfMethod((method + "(QUrl)").constData());
    if (index < 0 || receiver->metaObject()->method(index).access() != QMetaMethod::Public) {
        fail(r, EINVAL, "URL handler must name a public Qt slot or invokable accepting QUrl"); return false;
    }
    auto lease = std::make_unique<UrlHandlerLease>();
    lease->scheme = scheme; lease->method = method; lease->receiver = receiver;
    auto *pointer = lease.get();
    auto id = insert(r, lease.release(), nullptr, 0, delete_url_handler, true);
    if (!id) return false;
    pointer->token = id;
    const auto previous = url_handlers.value(scheme);
    try {
        BqtRequest claim{}; claim.self = id;
        constexpr uint32_t slot = 0xffffffdbu;
        int edge = prepare_retention(&claim, slot, 0, target);
        if (claim.error) { fail(r, claim.error, claim.message); release_url_handler(id); return false; }
        commit_retention(edge, id, slot, 0, target, nullptr);
        pointer->destroyed = QObject::connect(receiver, &QObject::destroyed,
            [id] { release_url_handler(id); });
        url_handlers.insert(scheme, id);
        QDesktopServices::setUrlHandler(scheme, receiver, method.constData());
    } catch (...) {
        // Restore the registry before destroying the prospective lease, whose
        // destructor must not unregister the previous successful handler.
        if (previous) url_handlers.insert(scheme, previous);
        else url_handlers.remove(scheme);
        release_url_handler(id);
        throw;
    }
    if (previous) release_url_handler(previous);
    return true;
}
