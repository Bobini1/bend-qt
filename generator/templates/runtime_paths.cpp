// Register a process-lifetime :/qt/etc/qt.conf before QApplication starts.
// The uncompressed version-1 resource layout is also checked against rcc in
// the deployment integration check. No resource compiler runs on consumers.
#include <QtCore/QByteArray>
#include <QtCore/QFile>
#include <QtCore/QResource>
#include <cstring>
namespace RuntimePaths {
static void word(QByteArray &out, quint32 value, unsigned width = 4) {
    for (unsigned i = width; i; --i) out.append(char(value >> ((i - 1) * 8)));
}
static quint32 name(QByteArray &out, const char *text) {
    const auto offset = quint32(out.size());
    const auto length = unsigned(std::strlen(text));
    quint32 hash = 0;
    for (const unsigned char *p = reinterpret_cast<const unsigned char *>(text); *p; ++p) {
        hash = (hash << 4) + *p;
        hash ^= (hash & 0xf0000000U) >> 23;
        hash &= 0x0fffffffU;
    }
    word(out, length, 2); word(out, hash);
    for (unsigned i = 0; i < length; ++i) word(out, quint8(text[i]), 2);
    return offset;
}
static void directory(QByteArray &out, quint32 name, quint32 child) {
    word(out, name); word(out, 2, 2); word(out, 1); word(out, child);
}
static const char *configure(const char *prefix) {
    if (!prefix) return nullptr;
    // Repeated native partitions share the same process resource.
    if (QFile::exists(QStringLiteral(":/qt/etc/qt.conf")))
        return "A Qt path configuration was registered before the bundled runtime";
    auto escaped = QByteArray(prefix);
    escaped.replace("\\", "\\\\"); escaped.replace("\"", "\\\"");
    escaped.replace("\n", "\\n"); escaped.replace("\r", "\\r");
    const auto ini = QByteArray("[Paths]\nPrefix=\"") + escaped + "\"\n";
    QByteArray names, tree;
    const auto qt = name(names, "qt"), etc = name(names, "etc"), conf = name(names, "qt.conf");
    directory(tree, 0, 1); directory(tree, qt, 2); directory(tree, etc, 3);
    word(tree, conf); word(tree, 0, 2); word(tree, 0, 2); word(tree, 1, 2); word(tree, 0);
    auto *resource = new QByteArray("qres", 4);
    word(*resource, 1); word(*resource, 20);
    word(*resource, 20 + tree.size()); word(*resource, 20 + tree.size() + 4 + ini.size());
    resource->append(tree); word(*resource, ini.size()); resource->append(ini); resource->append(names);
    if (!QResource::registerResource(reinterpret_cast<const uchar *>(resource->constData()))) {
        delete resource; return "Cannot register the bundled Qt path configuration";
    }
    // QResource retains these bytes; keep them through late Qt/plugin teardown.
    return nullptr;
}
}
