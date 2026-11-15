// Maintainer-only checks of the typed Qt binding facade. The Bend fixture
// property-bindings.bend separately verifies the generated consumer API.
#include <QtCore/QCoreApplication>
#include <QtCore/QMetaType>
#include <QtCore/QObject>
#include <QtCore/QProperty>
#include <QtCore/QCommandLineOption>
#include <cassert>
#include <iostream>
#include "../../generator/templates/property_bindings.cpp"

struct ExplicitCopyOnly {
    int value;
    explicit ExplicitCopyOnly(int initial) : value(initial) {}
    explicit ExplicitCopyOnly(const ExplicitCopyOnly &other) : value(other.value) {}
    ExplicitCopyOnly(ExplicitCopyOnly &&) = delete;
    ExplicitCopyOnly &operator=(const ExplicitCopyOnly &) = default;
    ExplicitCopyOnly &operator=(ExplicitCopyOnly &&) = delete;
    friend bool operator==(const ExplicitCopyOnly &left, const ExplicitCopyOnly &right) { return left.value == right.value; }
};
Q_DECLARE_METATYPE(ExplicitCopyOnly)

struct TestField {
    QVariant value;
    int writes = 0;
    std::shared_ptr<BendPropertyBindings::Storage> storage;
    template<class T> explicit TestField(T initial) : value(QVariant::fromValue(initial)) {
        storage = BendPropertyBindings::make<T>(QMetaType::fromType<T>(),
            [this](bool) -> std::optional<QVariant> { return value; },
            [this](QVariant next, bool from_binding) {
                if (!from_binding) storage->clear();
                bool changed = next != value;
                value = std::move(next);
                ++writes;
                if (changed && !from_binding) storage->changed();
                return true;
            });
    }
    template<class T> void set(T next) {
        storage->clear();
        bool changed = value != QVariant::fromValue(next);
        value = QVariant::fromValue(next);
        if (changed) storage->changed();
    }
};

struct RuntimeMeta {
    QtPrivate::QMetaTypeInterface interface{};
    QByteArray name;
    explicit RuntimeMeta(QByteArray typeName, QMetaType sourceType = QMetaType::fromType<QObject *>(), uint extraFlags = 0)
        : name(std::move(typeName)) {
        auto *source = sourceType.iface();
        interface.revision = QtPrivate::QMetaTypeInterface::CurrentRevision;
        interface.alignment = source->alignment;
        interface.size = source->size;
        interface.flags = source->flags | extraFlags;
        interface.typeId.storeRelaxed(0);
        interface.metaObjectFn = source->metaObjectFn;
        interface.name = name.constData();
        interface.defaultCtr = source->defaultCtr;
        interface.copyCtr = source->copyCtr;
        interface.moveCtr = source->moveCtr;
        interface.dtor = source->dtor;
        interface.equals = source->equals;
        interface.lessThan = source->lessThan;
    }
};

int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    TestField source(3), target(0), third(0);
    auto sb = source.storage->bindable(true);
    auto tb = target.storage->bindable(true);
    assert(sb.metaType() == QMetaType::fromType<int>());
    assert(tb.setBinding(sb.makeBinding()));
    assert(target.value.toInt() == 3);
    assert(third.storage->bindable(true).setBinding(tb.makeBinding()));
    source.set(9);
    assert(target.value.toInt() == 9 && third.value.toInt() == 9);
    assert(!target.storage->bindingError().hasError());
    assert(target.writes == 2 && third.writes == 2);
    QBindable<int> typed(tb);
    typed.setValue(12);
    source.set(17);
    assert(target.value.toInt() == 12 && third.value.toInt() == 12);
    assert(!tb.hasBinding());
    assert(target.storage->bindable(false).isReadOnly());
    TestField text(QStringLiteral("hello")), textTarget(QStringLiteral(""));
    assert(textTarget.storage->bindable(true).setBinding(text.storage->bindable(true).makeBinding()));
    text.set(QStringLiteral("world"));
    assert(textTarget.value.toString() == "world");
    TestField vector(QVariantList{1, 2}), vectorTarget(QVariantList{});
    assert(vectorTarget.storage->bindable(true).setBinding(vector.storage->bindable(true).makeBinding()));
    vector.set(QVariantList{3, 4, 5});
    assert(vectorTarget.value.toList().size() == 3);
    // QCommandLineOption has no default constructor, but initialized native
    // properties and the binding engine can still hold and update it.
    TestField option(QCommandLineOption(QStringLiteral("first")));
    TestField optionTarget(QCommandLineOption(QStringLiteral("before")));
    assert(!QMetaType::fromType<QCommandLineOption>().isDefaultConstructible());
    assert(option.storage && optionTarget.storage);
    assert(optionTarget.storage->bindable(true).setBinding(option.storage->bindable(false).makeBinding()));
    assert(static_cast<const QCommandLineOption *>(optionTarget.value.constData())->names() == QStringList{QStringLiteral("first")});
    QProperty<QCommandLineOption> nativeOption(QCommandLineOption(QStringLiteral("before")));
    assert(nativeOption.setBinding(option.storage->bindable(false).makeBinding()));
    option.set(QCommandLineOption(QStringLiteral("second")));
    assert(nativeOption.value().names() == QStringList{QStringLiteral("second")});
    assert(static_cast<const QCommandLineOption *>(optionTarget.value.constData())->names() == QStringList{QStringLiteral("second")});
    QVariant initiallyEmpty;
    int emptyWrites = 0, computed = 0, evaluationDepth = 0;
    struct EvaluationScope {
        int &depth;
        explicit EvaluationScope(int &value) : depth(value) { ++depth; }
        ~EvaluationScope() { --depth; }
    };
    auto bootstrap = BendPropertyBindings::make<QCommandLineOption>(QMetaType::fromType<QCommandLineOption>(),
        [&](bool) -> std::optional<QVariant> {
            assert(evaluationDepth > 0);
            return initiallyEmpty.isValid() ? std::optional<QVariant>{initiallyEmpty} : std::nullopt;
        },
        [&](QVariant value, bool fromBinding) {
            assert(evaluationDepth > 0 && fromBinding);
            initiallyEmpty = std::move(value); ++emptyWrites;
            return true;
        });
    bootstrap->evaluationScope = [&]() -> std::shared_ptr<void> {
        return std::make_shared<EvaluationScope>(evaluationDepth);
    };
    int nativeEvaluations = 0;
    auto external = Qt::makePropertyBinding([&] {
        ++nativeEvaluations;
        return QCommandLineOption(QStringLiteral("external"));
    });
    auto emptyBindable = bootstrap->bindable(true);
    assert(emptyBindable.isReadOnly() && !emptyBindable.setBinding(external));
    assert(nativeEvaluations == 0 && !emptyBindable.hasBinding());
    QProperty<int> bootstrapDependency(7);
    assert(bootstrap->setEvaluator([&](bool) -> std::optional<QVariant> {
        assert(evaluationDepth > 0);
        ++computed;
        return QVariant::fromValue(QCommandLineOption(QString::number(bootstrapDependency.value())));
    }));
    assert(evaluationDepth == 0 && computed == 1 && emptyWrites == 1);
    assert(static_cast<const QCommandLineOption *>(initiallyEmpty.constData())->names() == QStringList{QStringLiteral("7")});
    bootstrapDependency = 9;
    assert(evaluationDepth == 0 && computed == 2 && emptyWrites == 2);
    assert(static_cast<const QCommandLineOption *>(initiallyEmpty.constData())->names() == QStringList{QStringLiteral("9")});
    std::shared_ptr<BendPropertyBindings::Storage> unavailable;
    unavailable = BendPropertyBindings::make<QCommandLineOption>(QMetaType::fromType<QCommandLineOption>(),
        [&](bool) -> std::optional<QVariant> { unavailable->readFailed(EIO); return {}; },
        [](QVariant, bool) { assert(false); return false; });
    int unexpectedEvaluations = 0;
    assert(!unavailable->setEvaluator([&](bool) -> std::optional<QVariant> {
        ++unexpectedEvaluations;
        return QVariant::fromValue(QCommandLineOption(QStringLiteral("unexpected")));
    }));
    assert(unexpectedEvaluations == 0 && unavailable->bindingError().hasError());
    unavailable->clear();
    // Native copyability includes explicit copy constructors and types with
    // deleted moves. Neither property reads nor bindings need implicit copies.
    const auto explicitType = QMetaType::fromType<ExplicitCopyOnly>();
    ExplicitCopyOnly initialExplicit(3), initialTarget(0);
    QVariant explicitSource(explicitType, &initialExplicit), explicitTarget(explicitType, &initialTarget);
    auto explicitStorage = BendPropertyBindings::make<ExplicitCopyOnly>(explicitType,
        [&](bool) -> std::optional<QVariant> { return explicitSource; },
        [&](QVariant value, bool) { explicitSource = std::move(value); return true; });
    auto explicitDestination = BendPropertyBindings::make<ExplicitCopyOnly>(explicitType,
        [&](bool) -> std::optional<QVariant> { return explicitTarget; },
        [&](QVariant value, bool) { explicitTarget = std::move(value); return true; });
    assert(explicitStorage && explicitDestination);
    assert(explicitDestination->bindable(true).setBinding(explicitStorage->bindable(false).makeBinding()));
    assert(static_cast<const ExplicitCopyOnly *>(explicitTarget.constData())->value == 3);
    ExplicitCopyOnly updatedExplicit(8);
    explicitSource = QVariant(explicitType, &updatedExplicit);
    explicitStorage->changed();
    assert(static_cast<const ExplicitCopyOnly *>(explicitTarget.constData())->value == 8);
    QProperty<int> native(0);
    assert(native.setBinding(source.storage->bindable(true).makeBinding()));
    source.set(28);
    assert(native.value() == 28);
    assert(tb.setBinding(Qt::makePropertyBinding([&native] { return native.value() * 2; })));
    source.set(32);
    assert(target.value.toInt() == 64 && third.value.toInt() == 64);
    {
        QScopedPropertyUpdateGroup group;
        source.set(40);
        source.set(41);
    }
    assert(target.value.toInt() == 82);
    assert(target.storage->setEvaluator([&](bool) -> std::optional<QVariant> {
        QBindable<int> sourceValue(source.storage->bindable(false));
        return QVariant::fromValue(sourceValue.value() * 3 + 1);
    }));
    assert(target.value.toInt() == 124 && third.value.toInt() == 124);
    source.set(5);
    assert(target.value.toInt() == 16 && third.value.toInt() == 16);
    assert(!target.storage->setEvaluator([](bool) -> std::optional<QVariant> { return {}; }));
    assert(target.value.toInt() == 16);
    auto temporary = std::make_unique<TestField>(7);
    assert(tb.setBinding(temporary->storage->bindable(true).makeBinding()));
    temporary.reset();
    target.storage->clear();
    // This is a genuinely distinct QObject pointer metatype, not an alias.
    // Qt retains registered interfaces; keep its storage for process lifetime.
    auto *pointerMeta = new RuntimeMeta("BendRuntimePointerProbe*");
    QMetaType pointerType(&pointerMeta->interface);
    pointerType.registerType();
    QObject firstObject, secondObject;
    QObject *pointer = &firstObject;
    QVariant pointerSource(pointerType, &pointer), pointerTarget(pointerType);
    std::shared_ptr<BendPropertyBindings::Storage> ps, pt;
    ps = BendPropertyBindings::make<QObject *>(pointerType,
        [&](bool) -> std::optional<QVariant> { return pointerSource; },
        [&](QVariant next, bool fromBinding) {
            if (!fromBinding) ps->clear();
            bool changed = next != pointerSource;
            pointerSource = next;
            if (changed && !fromBinding) ps->changed();
            return true;
        });
    pt = BendPropertyBindings::make<QObject *>(pointerType,
        [&](bool) -> std::optional<QVariant> { return pointerTarget; },
        [&](QVariant next, bool fromBinding) {
            if (!fromBinding) pt->clear();
            bool changed = next != pointerTarget;
            pointerTarget = next;
            if (changed && !fromBinding) pt->changed();
            return true;
        });
    assert(ps->bindable(true).metaType() == pointerType);
    assert(ps->bindable(true).metaType() != QMetaType::fromType<QObject *>());
    assert(pt->bindable(true).setBinding(ps->bindable(false).makeBinding()));
    assert(*static_cast<QObject *const *>(pointerTarget.constData()) == &firstObject);
    pointer = &secondObject;
    pointerSource = QVariant(pointerType, &pointer);
    ps->changed();
    assert(*static_cast<QObject *const *>(pointerTarget.constData()) == &secondObject);
    auto *enumMeta = new RuntimeMeta("BendRuntimeEnumProbe", QMetaType::fromType<qint32>(), QMetaType::IsEnumeration);
    QMetaType enumType(&enumMeta->interface);
    enumType.registerType();
    qint32 enumWord = 3;
    QVariant enumSource(enumType, &enumWord), enumTarget(enumType);
    std::shared_ptr<BendPropertyBindings::Storage> es, et;
    es = BendPropertyBindings::make<qint32>(enumType,
        [&](bool) -> std::optional<QVariant> { return enumSource; },
        [&](QVariant next, bool fromBinding) {
            if (!fromBinding) es->clear();
            enumSource = next;
            if (!fromBinding) es->changed();
            return true;
        });
    et = BendPropertyBindings::make<qint32>(enumType,
        [&](bool) -> std::optional<QVariant> { return enumTarget; },
        [&](QVariant next, bool fromBinding) {
            if (!fromBinding) et->clear();
            enumTarget = next;
            if (!fromBinding) et->changed();
            return true;
        });
    assert(es->bindable(false).metaType() == enumType);
    assert(es->bindable(false).metaType() != QMetaType::fromType<qint32>());
    assert(et->bindable(true).setBinding(es->bindable(false).makeBinding()));
    assert(*static_cast<const qint32 *>(enumTarget.constData()) == 3);
    enumWord = 7;
    enumSource = QVariant(enumType, &enumWord);
    es->changed();
    assert(*static_cast<const qint32 *>(enumTarget.constData()) == 7);
    std::cout << "PROPERTY_BINDINGS_NATIVE_OK" << std::endl;
}
