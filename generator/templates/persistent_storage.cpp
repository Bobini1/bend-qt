// The category dies before the byte array that backs categoryName(). Its
// registry cast returns the real Qt object, while destruction owns the holder.
struct StableLoggingCategory {
    QByteArray name;
    QLoggingCategory category;
    StableLoggingCategory(QByteArray text, QtMsgType level) : name(std::move(text)), category(name.constData(), level) {}
};
static void destroy_logging_category(void *value) { delete static_cast<StableLoggingCategory *>(value); }
static void *cast_logging_category(void *value, uint16_t type) {
    return type == @LOGGING_TYPE@ ? &static_cast<StableLoggingCategory *>(value)->category : nullptr;
}

struct StableMessageLogContext {
    QByteArray file, function, category;
    QMessageLogContext value;
    StableMessageLogContext(QByteArray f = {}, int line = 0, QByteArray fn = {}, QByteArray cat = {})
        : file(std::move(f)), function(std::move(fn)), category(std::move(cat)),
          value(file.isNull() ? nullptr : file.constData(), line,
                function.isNull() ? nullptr : function.constData(), category.isNull() ? nullptr : category.constData()) {}
};
struct StableMessageLogger {
    QByteArray file, function, category;
    QMessageLogger value;
    StableMessageLogger(QByteArray f = {}, int line = 0, QByteArray fn = {}, QByteArray cat = {})
        : file(std::move(f)), function(std::move(fn)), category(std::move(cat)),
          value(file.isNull() ? nullptr : file.constData(), line,
                function.isNull() ? nullptr : function.constData(), category.isNull() ? nullptr : category.constData()) {}
};
template <typename Holder> static void destroy_message_context(void *value) { delete static_cast<Holder *>(value); }
template <typename Holder, uint16_t Type> static void *cast_message_context(void *value, uint16_t type) {
    return type == Type ? &static_cast<Holder *>(value)->value : nullptr;
}
static bool set_message_context_field(BqtRequest *r, const char *&field,
                                     QByteArray StableMessageLogContext::*member, const std::optional<QString> &text) {
    auto *e = entry(r->self);
    if (!e || e->destroy != destroy_message_context<StableMessageLogContext>) {
        fail(r, EPERM, "Logging context field needs independently owned string storage"); return false;
    }
    QByteArray bytes = text ? text->toUtf8() : QByteArray();
    if (text && bytes.contains('\0')) { fail(r, EINVAL, "Logging context contains an embedded NUL"); return false; }
    auto *holder = static_cast<StableMessageLogContext *>(e->value);
    holder->*member = std::move(bytes);
    field = text ? (holder->*member).constData() : nullptr;
    return true;
}

struct TranslationSnapshots { std::vector<QByteArray> values; };
struct TranslationStorageRecord { QPointer<QTranslator> translator; std::weak_ptr<TranslationSnapshots> storage; };
static std::shared_ptr<TranslationSnapshots> translation_storage(QTranslator *translator) {
    static std::vector<TranslationStorageRecord> records;
    for (auto it = records.begin(); it != records.end();) {
        auto storage = it->storage.lock();
        if (!storage) { it = records.erase(it); continue; }
        if (it->translator == translator) return storage;
        ++it;
    }
    auto storage = std::make_shared<TranslationSnapshots>();
    records.push_back({translator, storage});
    // QObject emits this after QTranslator's destructor has stopped reading its
    // data. A native deletion outside the binding follows the same lifetime.
    QObject::connect(translator, &QObject::destroyed, [storage] { storage->values.clear(); });
    return storage;
}
static bool load_translation_snapshot(BqtRequest *, QTranslator *translator, const QByteArray &source, int count, const QString &directory) {
    auto storage = translation_storage(translator);
    // Allocate before touching Qt. Keep all candidates if Qt unwinds midway;
    // the next completed load, or native destruction, reclaims old snapshots.
    storage->values.emplace_back(source.constData(), count);
    const auto &bytes = storage->values.back();
    bool result = translator->load(reinterpret_cast<const uchar *>(bytes.constData()), count, directory);
    QByteArray surviving = std::move(storage->values.back());
    storage->values.clear();
    storage->values.push_back(std::move(surviving));
    return result;
}

static uint32_t rcc_u32(const uchar *p) {
    return uint32_t(p[0]) << 24 | uint32_t(p[1]) << 16 | uint32_t(p[2]) << 8 | uint32_t(p[3]);
}
static uint16_t rcc_u16(const uchar *p) { return uint16_t(p[0]) << 8 | uint16_t(p[1]); }
static bool valid_rcc_snapshot(const QByteArray &bytes) {
    const auto size = size_t(bytes.size());
    const auto *data = reinterpret_cast<const uchar *>(bytes.constData());
    if (size < 20 || std::memcmp(data, "qres", 4)) return false;
    const auto version = rcc_u32(data + 4);
    if (version < 1 || version > 3) return false;
    const size_t header = version >= 3 ? 24 : 20;
    if (size < header || (version >= 3 && (rcc_u32(data + 20) & ~5u))) return false;
    const size_t tree = rcc_u32(data + 8), payload = rcc_u32(data + 12), names = rcc_u32(data + 16);
    if (tree < header || tree >= size || payload < header || payload >= size || names < header || names >= size) return false;
    auto extent = [&](size_t base) {
        size_t end = size;
        for (auto offset : {tree, payload, names}) if (offset > base) end = std::min(end, offset);
        return end - base;
    };
    const size_t width = version >= 2 ? 22 : 14;
    const size_t tree_size = extent(tree), payload_size = extent(payload), names_size = extent(names);
    // Qt uses signed 32-bit offsets (and int node*width) internally.
    if (size > INT32_MAX || tree_size % width || tree_size / width > size_t(INT32_MAX) / width) return false;
    const size_t count = tree_size / width;
    if (!count || !(rcc_u16(data + tree + 4) & 2)) return false;
    std::vector<unsigned char> reached(count, 0);
    std::vector<size_t> pending{0}; reached[0] = 1;
    while (!pending.empty()) {
        size_t index = pending.back(); pending.pop_back();
        const uchar *node = data + tree + width * index;
        size_t name = rcc_u32(node);
        // The root has no name and rcc is allowed to leave its offset zero.
        if (index) {
            if (name > names_size || names_size - name < 6) return false;
            size_t length = rcc_u16(data + names + name);
            if (length > (names_size - name - 6) / 2) return false;
        }
        uint16_t flags = rcc_u16(node + 4);
        if (flags & ~7u || ((flags & 1) && (flags & 4))) return false;
        if (((flags & 4) && version < 3) || (version >= 3 && ((flags & 5u) & ~rcc_u32(data + 20)))) return false;
        if (flags & 2) {
            if (flags != 2) return false;
            size_t children = rcc_u32(node + 6), first = rcc_u32(node + 10);
            if (first > count || children > count - first) return false;
            for (size_t child = first; child < first + children; ++child) {
                if (reached[child]) return false;
                reached[child] = 1; pending.push_back(child);
            }
        } else {
            size_t offset = rcc_u32(node + 10);
            if (offset > payload_size || payload_size - offset < 4) return false;
            size_t length = rcc_u32(data + payload + offset);
            if (length > payload_size - offset - 4 || ((flags & 1) && length < 4)) return false;
        }
    }
    return std::all_of(reached.begin(), reached.end(), [](unsigned char value) { return value != 0; });
}

// File-backed roots own their mmap/copy in Qt. Removing a registration or its
// temporary pathname never frees bytes still referenced by QResource/QFile.
struct ResourceSnapshot {
    uint32_t source;
    QString file, root;
    bool registered = false;
    ~ResourceSnapshot() { if (registered) QResource::unregisterResource(file, root); }
};
static void destroy_resource_snapshot(void *value) { delete static_cast<ResourceSnapshot *>(value); }
static QString normalized_resource_root(QString root) {
    if (root.startsWith(u':')) root.remove(0, 1);
    return root.isEmpty() ? root : QDir::cleanPath(root);
}
static bool register_resource_snapshot(BqtRequest *r, uint32_t source, const QByteArray &bytes, QString root) {
    root = normalized_resource_root(root);
    if ((!root.isEmpty() && !root.startsWith(u'/')) || !valid_rcc_snapshot(bytes)) return false;
    QTemporaryFile file(QDir::tempPath() + QStringLiteral("/bend-qt-resource-XXXXXX.rcc"));
    if (!file.open()) { fail(r, EIO, "Cannot create the resource snapshot"); return false; }
    if (file.write(bytes) != bytes.size() || !file.flush()) { fail(r, EIO, "Cannot write the resource snapshot"); return false; }
    auto value = std::make_unique<ResourceSnapshot>(ResourceSnapshot{source, file.fileName(), root, false});
    auto *record = value.release();
    uint32_t id = insert(r, record, nullptr, 65534, destroy_resource_snapshot, true);
    if (!id) return false;
    BqtRequest check{}; check.self = id;
    constexpr uint32_t slot = 0xffffffe8u;
    int index = prepare_retention(&check, slot, 0, source);
    if (check.error) {
        invalidate(id); delete record; fail(r, check.error, check.message); return false;
    }
    RetentionReservation reservation(index, id, slot, 0);
    try {
        record->registered = QResource::registerResource(record->file, record->root);
    } catch (...) { invalidate(id); delete record; throw; }
    if (!record->registered) { invalidate(id); delete record; return false; }
    commit_retention(index, id, slot, 0, source, nullptr);
    return true;
}
static bool unregister_resource_snapshot(BqtRequest *, uint32_t source, const QByteArray &, QString root) {
    root = normalized_resource_root(root);
    for (uint32_t i = 1; i < capacity; ++i) {
        auto &e = entries[i];
        if (!e.value || e.destroy != destroy_resource_snapshot) continue;
        auto *record = static_cast<ResourceSnapshot *>(e.value);
        if (record->source != source || record->root != root) continue;
        bool result = QResource::unregisterResource(record->file, record->root);
        record->registered = false;
        invalidate(token(i, e.generation)); delete record;
        return result;
    }
    return false;
}
