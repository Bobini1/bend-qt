// Namespace aliases preserve C++ identity, so they cannot isolate conflicting
// Qt metatypes. Give qualified module types their own complete interface and
// forward lifetime operations to the exact originating interface instead.
#include <QtCore/QMetaContainer>
#include <QtCore/QIterable>
#include <mutex>
#include <dlfcn.h>
namespace BendQualifiedTypes {
struct Interface : QtPrivate::QMetaTypeInterface {
    const QtPrivate::QMetaTypeInterface *original = nullptr;
    QByteArray qualified_name;
    QByteArray module;
    std::unique_ptr<QtMetaContainerPrivate::QMetaSequenceInterface> sequence;
    std::unique_ptr<QtMetaContainerPrivate::QMetaAssociationInterface> association;
};
static std::recursive_mutex mutex;
static std::map<QByteArray, std::shared_ptr<Interface>> &interfaces() {
    static auto *values = new std::map<QByteArray, std::shared_ptr<Interface>>;
    return *values;
}
static const QtPrivate::QMetaTypeInterface *source(const QtPrivate::QMetaTypeInterface *value) {
    return static_cast<const Interface *>(value)->original;
}
static QMetaType existing(const char *name) {
    std::lock_guard<std::recursive_mutex> guard(mutex);
    auto found = interfaces().find(name);
    return found == interfaces().end() ? QMetaType{} : QMetaType(found->second.get());
}
static QMetaType plain(QMetaType native, const char *name, const char *module = "") {
    std::lock_guard<std::recursive_mutex> guard(mutex);
    auto &values = interfaces();
    if (auto found = values.find(name); found != values.end()) {
        if (found->second->original != native.iface() || found->second->module != module)
            throw std::invalid_argument("A qualified native metatype has conflicting module origins");
        return QMetaType(found->second.get());
    }
    for (const auto &row : values) if (row.second->original == native.iface() && row.second->module == module) {
        auto value = row.second; values.emplace(name, value);
        QMetaType result(value.get());
        QMetaType::registerNormalizedTypedef(QMetaObject::normalizedType(name), result);
        return result;
    }
    const auto *original = native.iface();
    if (!original || original->revision != QtPrivate::QMetaTypeInterface::CurrentRevision)
        throw std::invalid_argument("Unsupported native metatype interface revision");
    auto value = std::make_shared<Interface>();
    auto *type = value.get(); type->original = original; type->qualified_name = name; type->module = module;
    type->revision = original->revision; type->size = original->size;
    type->alignment = original->alignment; type->flags = original->flags;
    type->name = type->qualified_name.constData();
    if (original->metaObjectFn) type->metaObjectFn = [](auto *i) { auto *s = source(i); return s->metaObjectFn(s); };
    if (original->defaultCtr) type->defaultCtr = [](auto *i, void *p) { auto *s = source(i); s->defaultCtr(s, p); };
    if (original->copyCtr) type->copyCtr = [](auto *i, void *p, const void *v) { auto *s = source(i); s->copyCtr(s, p, v); };
    if (original->moveCtr) type->moveCtr = [](auto *i, void *p, void *v) { auto *s = source(i); s->moveCtr(s, p, v); };
    if (original->dtor) type->dtor = [](auto *i, void *p) { auto *s = source(i); s->dtor(s, p); };
    if (original->equals) type->equals = [](auto *i, const void *a, const void *b) { auto *s = source(i); return s->equals(s, a, b); };
    if (original->lessThan) type->lessThan = [](auto *i, const void *a, const void *b) { auto *s = source(i); return s->lessThan(s, a, b); };
    if (original->debugStream) type->debugStream = [](auto *i, QDebug &d, const void *v) { auto *s = source(i); s->debugStream(s, d, v); };
    if (original->dataStreamOut) type->dataStreamOut = [](auto *i, QDataStream &d, const void *v) { auto *s = source(i); s->dataStreamOut(s, d, v); };
    if (original->dataStreamIn) type->dataStreamIn = [](auto *i, QDataStream &d, void *v) { auto *s = source(i); s->dataStreamIn(s, d, v); };
    // The new name owns a fresh typeId; the native alias registration hook
    // would collapse it back into Qt's process-wide unqualified name.
    type->legacyRegisterOp = nullptr;
    values.emplace(type->qualified_name, std::move(value));
    QMetaType result(type); result.registerType(); return result;
}
template<class Container> static QMetaType sequence(const char *name, QMetaType element, const char *module = "") {
    std::lock_guard<std::recursive_mutex> guard(mutex);
    auto meta = plain(QMetaType::fromType<Container>(), name, module);
    auto *type = interfaces().at(name).get();
    if (!type->sequence) {
        type->sequence = std::make_unique<QtMetaContainerPrivate::QMetaSequenceInterface>(
            *QMetaSequence::fromContainer<Container>().iface());
        type->sequence->valueMetaType = element.iface();
        const auto sequence = QMetaSequence(type->sequence.get());
        const auto iterable = QMetaType::fromType<QIterable<QMetaSequence>>();
        if (!QMetaType::registerConverterFunction([sequence](const void *p, void *r) {
                *static_cast<QIterable<QMetaSequence> *>(r) = QIterable<QMetaSequence>(sequence, static_cast<const Container *>(p)); return true;
            }, meta, iterable)
            || !QMetaType::registerMutableViewFunction([sequence](void *p, void *r) {
                *static_cast<QIterable<QMetaSequence> *>(r) = QIterable<QMetaSequence>(sequence, static_cast<Container *>(p)); return true;
            }, meta, iterable)) throw std::invalid_argument("Cannot register a qualified native sequence");
    }
    return meta;
}
template<class Container> static QMetaType association(const char *name, QMetaType key, QMetaType mapped, const char *module = "") {
    std::lock_guard<std::recursive_mutex> guard(mutex);
    auto meta = plain(QMetaType::fromType<Container>(), name, module);
    auto *type = interfaces().at(name).get();
    if (!type->association) {
        type->association = std::make_unique<QtMetaContainerPrivate::QMetaAssociationInterface>(
            *QMetaAssociation::fromContainer<Container>().iface());
        type->association->keyMetaType = key.iface(); type->association->mappedMetaType = mapped.iface();
        const auto association = QMetaAssociation(type->association.get());
        const auto iterable = QMetaType::fromType<QIterable<QMetaAssociation>>();
        if (!QMetaType::registerConverterFunction([association](const void *p, void *r) {
                *static_cast<QIterable<QMetaAssociation> *>(r) = QIterable<QMetaAssociation>(association, static_cast<const Container *>(p)); return true;
            }, meta, iterable)
            || !QMetaType::registerMutableViewFunction([association](void *p, void *r) {
                *static_cast<QIterable<QMetaAssociation> *>(r) = QIterable<QMetaAssociation>(association, static_cast<Container *>(p)); return true;
            }, meta, iterable)) throw std::invalid_argument("Cannot register a qualified native association");
    }
    return meta;
}
template<class Container> static QMetaType native_sequence(const char *name, QMetaType element, const char * = "") {
    static const auto meta = QMetaType::fromType<Container>();
    static const bool registered = [&] {
        auto *view = new QtMetaContainerPrivate::QMetaSequenceInterface(*QMetaSequence::fromContainer<Container>().iface());
        view->valueMetaType = element.iface();
        const auto sequence = QMetaSequence(view);
        const auto iterable = QMetaType::fromType<QIterable<QMetaSequence>>();
        if (!QMetaType::hasRegisteredConverterFunction(meta, iterable))
            QMetaType::registerConverterFunction([sequence](const void *p, void *r) {
                *static_cast<QIterable<QMetaSequence> *>(r) = QIterable<QMetaSequence>(sequence, static_cast<const Container *>(p)); return true;
            }, meta, iterable);
        if (!QMetaType::hasRegisteredMutableViewFunction(meta, iterable))
            QMetaType::registerMutableViewFunction([sequence](void *p, void *r) {
                *static_cast<QIterable<QMetaSequence> *>(r) = QIterable<QMetaSequence>(sequence, static_cast<Container *>(p)); return true;
            }, meta, iterable);
        return true;
    }();
    (void)registered; QMetaType::registerNormalizedTypedef(QMetaObject::normalizedType(name), meta); return meta;
}
template<class Container> static QMetaType native_association(const char *name, QMetaType key, QMetaType mapped, const char * = "") {
    static const auto meta = QMetaType::fromType<Container>();
    static const bool registered = [&] {
        auto *view = new QtMetaContainerPrivate::QMetaAssociationInterface(*QMetaAssociation::fromContainer<Container>().iface());
        view->keyMetaType = key.iface(); view->mappedMetaType = mapped.iface();
        const auto association = QMetaAssociation(view);
        const auto iterable = QMetaType::fromType<QIterable<QMetaAssociation>>();
        if (!QMetaType::hasRegisteredConverterFunction(meta, iterable))
            QMetaType::registerConverterFunction([association](const void *p, void *r) {
                *static_cast<QIterable<QMetaAssociation> *>(r) = QIterable<QMetaAssociation>(association, static_cast<const Container *>(p)); return true;
            }, meta, iterable);
        if (!QMetaType::hasRegisteredMutableViewFunction(meta, iterable))
            QMetaType::registerMutableViewFunction([association](void *p, void *r) {
                *static_cast<QIterable<QMetaAssociation> *>(r) = QIterable<QMetaAssociation>(association, static_cast<Container *>(p)); return true;
            }, meta, iterable);
        return true;
    }();
    (void)registered; QMetaType::registerNormalizedTypedef(QMetaObject::normalizedType(name), meta); return meta;
}
static const Interface *isolated(QMetaType type) {
    for (const auto &row : interfaces()) if (row.second.get() == type.iface()) return row.second.get();
    return nullptr;
}
static bool compatible(QMetaType actual, QMetaType expected) {
    if (actual.iface() == expected.iface()) return true;
    std::lock_guard<std::recursive_mutex> guard(mutex);
    const auto *target = isolated(expected), *received = isolated(actual);
    if (!target && received) return compatible(expected, actual);
    if (!target) return actual == expected;
    if (received && received->module != target->module) return false;
    const QMetaType native(target->original);
    const QMetaType origin = received ? QMetaType(received->original) : actual;
    if (!origin.isValid() || origin.sizeOf() != native.sizeOf() || origin.alignOf() != native.alignOf()
            || origin.flags() != native.flags() || !origin.name() || !native.name()
            || QMetaObject::normalizedType(origin.name()) != QMetaObject::normalizedType(native.name())) return false;
    if (origin.iface() == native.iface()) return true;
    if (origin.metaObject() || native.metaObject()) return origin.metaObject() == native.metaObject();
    Dl_info provided{}, required{};
    if (dladdr(origin.iface(), &provided) && dladdr(native.iface(), &required)
            && provided.dli_fbase == required.dli_fbase) return true;
    if (target->module.isEmpty() || !provided.dli_fname) return false;
    const char *file = std::strrchr(provided.dli_fname, '/'); file = file ? file + 1 : provided.dli_fname;
    const QByteArray prefix = "lib" + QByteArray(target->module).replace(0, 2, "Qt6");
    return QByteArray(file).startsWith(prefix);
}
}
