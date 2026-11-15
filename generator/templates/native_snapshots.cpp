// Qt's text/byte copies may alias fromRawData input. Signals own their input
// snapshots, including text and bytes nested inside supported containers.
static void native_snapshot_depth(unsigned depth) {
    if (depth > 128) throw std::length_error("Signal value nesting exceeds 128");
}
extern __attribute__((visibility("hidden"))) QVariant native_owned_variant_snapshot(const QVariant &, unsigned);
template<class T> static T native_owned_snapshot(const T &, unsigned = 0);
static QString native_owned_snapshot(const QString &, unsigned = 0);
static QByteArray native_owned_snapshot(const QByteArray &, unsigned = 0);
static QVariant native_owned_snapshot(const QVariant &, unsigned = 0);
template<class T> static QList<T> native_owned_snapshot(const QList<T> &, unsigned = 0);
template<class T> static QSet<T> native_owned_snapshot(const QSet<T> &, unsigned = 0);
template<class K, class V> static QMap<K,V> native_owned_snapshot(const QMap<K,V> &, unsigned = 0);
template<class K, class V> static QHash<K,V> native_owned_snapshot(const QHash<K,V> &, unsigned = 0);
template<class K, class V> static QMultiMap<K,V> native_owned_snapshot(const QMultiMap<K,V> &, unsigned = 0);
template<class K, class V> static QMultiHash<K,V> native_owned_snapshot(const QMultiHash<K,V> &, unsigned = 0);
template<class A, class B> static std::pair<A,B> native_owned_snapshot(const std::pair<A,B> &, unsigned = 0);
template<class T> static std::optional<T> native_owned_snapshot(const std::optional<T> &, unsigned = 0);
template<class T, size_t N> static std::array<T,N> native_owned_snapshot(const std::array<T,N> &, unsigned = 0);

template<class T> static T native_owned_snapshot(const T &value, unsigned depth) {
    native_snapshot_depth(depth);
    return T(value);
}
static QString native_owned_snapshot(const QString &value, unsigned depth) {
    native_snapshot_depth(depth);
    return value.isNull() ? QString() : QString(value.constData(), value.size());
}
static QByteArray native_owned_snapshot(const QByteArray &value, unsigned depth) {
    native_snapshot_depth(depth);
    return value.isNull() ? QByteArray() : QByteArray(value.constData(), value.size());
}
template<class T> static QList<T> native_owned_snapshot(const QList<T> &value, unsigned depth) {
    native_snapshot_depth(depth);
    QList<T> result;
    result.reserve(value.size());
    for (const auto &item : value) result.append(native_owned_snapshot(item, depth + 1));
    return result;
}
template<class T> static QSet<T> native_owned_snapshot(const QSet<T> &value, unsigned depth) {
    native_snapshot_depth(depth);
    QSet<T> result;
    result.reserve(value.size());
    for (const auto &item : value) result.insert(native_owned_snapshot(item, depth + 1));
    return result;
}
template<class K, class V> static QMap<K,V> native_owned_snapshot(const QMap<K,V> &value, unsigned depth) {
    native_snapshot_depth(depth);
    QMap<K,V> result;
    for (auto it = value.cbegin(); it != value.cend(); ++it)
        result.insert(native_owned_snapshot(it.key(), depth + 1), native_owned_snapshot(it.value(), depth + 1));
    return result;
}
template<class K, class V> static QHash<K,V> native_owned_snapshot(const QHash<K,V> &value, unsigned depth) {
    native_snapshot_depth(depth);
    QHash<K,V> result;
    result.reserve(value.size());
    for (auto it = value.cbegin(); it != value.cend(); ++it)
        result.insert(native_owned_snapshot(it.key(), depth + 1), native_owned_snapshot(it.value(), depth + 1));
    return result;
}
template<class K, class V> static QMultiMap<K,V> native_owned_snapshot(const QMultiMap<K,V> &value, unsigned depth) {
    native_snapshot_depth(depth);
    QMultiMap<K,V> result;
    auto it = value.cend();
    while (it != value.cbegin()) {
        --it;
        result.insert(native_owned_snapshot(it.key(), depth + 1), native_owned_snapshot(it.value(), depth + 1));
    }
    return result;
}
template<class K, class V> static QMultiHash<K,V> native_owned_snapshot(const QMultiHash<K,V> &value, unsigned depth) {
    native_snapshot_depth(depth);
    std::vector<std::pair<K,V>> values;
    values.reserve(size_t(value.size()));
    for (auto it = value.cbegin(); it != value.cend(); ++it)
        values.emplace_back(native_owned_snapshot(it.key(), depth + 1), native_owned_snapshot(it.value(), depth + 1));
    QMultiHash<K,V> result;
    result.reserve(value.size());
    for (auto it = values.crbegin(); it != values.crend(); ++it) result.insert(it->first, it->second);
    return result;
}
template<class A, class B> static std::pair<A,B> native_owned_snapshot(const std::pair<A,B> &value, unsigned depth) {
    native_snapshot_depth(depth);
    return std::pair<A,B>{native_owned_snapshot(value.first, depth + 1), native_owned_snapshot(value.second, depth + 1)};
}
template<class T> static std::optional<T> native_owned_snapshot(const std::optional<T> &value, unsigned depth) {
    native_snapshot_depth(depth);
    if (!value) return std::nullopt;
    return std::optional<T>(std::in_place, native_owned_snapshot(*value, depth + 1));
}
template<class T, size_t N, size_t... I> static std::array<T,N> native_array_snapshot(
    const std::array<T,N> &value, unsigned depth, std::index_sequence<I...>) {
    return {native_owned_snapshot(value[I], depth + 1)...};
}
template<class T, size_t N> static std::array<T,N> native_owned_snapshot(const std::array<T,N> &value, unsigned depth) {
    native_snapshot_depth(depth);
    return native_array_snapshot(value, depth, std::make_index_sequence<N>{});
}
static QVariant native_owned_snapshot(const QVariant &value, unsigned depth) {
    native_snapshot_depth(depth);
    switch (value.metaType().id()) {
    case QMetaType::QString: return native_owned_snapshot(value.toString(), depth + 1);
    case QMetaType::QByteArray: return native_owned_snapshot(value.toByteArray(), depth + 1);
    case QMetaType::QVariant: return native_owned_snapshot(*static_cast<const QVariant *>(value.constData()), depth + 1);
    case QMetaType::QVariantList: return native_owned_snapshot(value.toList(), depth + 1);
    case QMetaType::QVariantMap: return native_owned_snapshot(value.toMap(), depth + 1);
    case QMetaType::QVariantHash: return native_owned_snapshot(value.toHash(), depth + 1);
    default: return native_owned_variant_snapshot(value, depth);
    }
}
