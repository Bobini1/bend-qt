// Maintainer-only check: the production typed facade preserves a runtime list
// metatype through Qt's tagged QUntypedBindable metadata query and binding.
#include <QtCore/QCoreApplication>
#include <QtCore/QProperty>
#include <QtQml/QQmlListProperty>
#include <atomic>
#include <cassert>
#include <iostream>
#include "../../generator/templates/property_bindings.cpp"

struct RuntimeListMeta {
    QtPrivate::QMetaTypeInterface interface{};
    std::atomic<const QMetaObject *> element{&QObject::staticMetaObject};
    RuntimeListMeta() {
        const auto *source = QMetaType::fromType<QQmlListProperty<QObject>>().iface();
        interface.revision = source->revision;
        interface.alignment = source->alignment; interface.size = source->size;
        interface.flags = source->flags; interface.typeId.storeRelaxed(0);
        interface.name = "QQmlListProperty<BendNativeListElement>";
        interface.metaObjectFn = [](const QtPrivate::QMetaTypeInterface *self) {
            return reinterpret_cast<const RuntimeListMeta *>(self)->element.load();
        };
        interface.defaultCtr = source->defaultCtr; interface.copyCtr = source->copyCtr;
        interface.moveCtr = source->moveCtr; interface.dtor = source->dtor;
        interface.equals = source->equals; interface.lessThan = source->lessThan;
    }
};

int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    static RuntimeListMeta runtime;
    const QMetaType type(&runtime.interface);
    type.registerType();
    assert(type.flags().testFlag(QMetaType::IsQmlList));
    assert(type.metaObject() == &QObject::staticMetaObject);
    QObject first, second;
    QList<QObject *> one{&first}, two{&second};
    QQmlListProperty<QObject> firstView(&first, &one), secondView(&second, &two);
    QVariant source(type, &firstView), target(type, &secondView);
    auto from = BendPropertyBindings::make<QQmlListProperty<QObject>>(type,
        [&](bool) -> std::optional<QVariant> { return source; },
        [&](QVariant value, bool) { source = std::move(value); return true; });
    auto to = BendPropertyBindings::make<QQmlListProperty<QObject>>(type,
        [&](bool) -> std::optional<QVariant> { return target; },
        [&](QVariant value, bool) { target = std::move(value); return true; });
    assert(from && to);
    auto fromBindable = from->bindable(false), toBindable = to->bindable(true);
    assert(fromBindable.metaType() == type && toBindable.metaType() == type);
    assert(toBindable.setBinding(fromBindable.makeBinding()));
    assert(target.metaType() == type);
    assert(static_cast<const QQmlListProperty<QObject> *>(target.constData())->object == &first);
    source = QVariant(type, &secondView);
    from->changed();
    assert(static_cast<const QQmlListProperty<QObject> *>(target.constData())->object == &second);
    assert(!to->bindingError().hasError());
    std::cout << "QT612_QML_LIST_BINDING_NATIVE_OK typed=1 dynamic_meta=1 propagation=1\n";
}
