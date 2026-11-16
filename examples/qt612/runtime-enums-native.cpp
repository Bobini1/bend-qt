// Qt control for the enum constant lookup used by runtime-enums.bend.
#include <QtCore/QCoreApplication>
#include <QtCore/QMetaEnum>
#include <QtQml/QQmlComponent>
#include <QtQml/QQmlEngine>
#include <iostream>
#include <memory>

class EnumSubject : public QObject {
    Q_OBJECT
    Q_PROPERTY(Wide wide MEMBER wide)
public:
    enum class Wide : qint64 { Huge = 4294967297LL };
    Q_ENUM(Wide)
    Wide wide = Wide::Huge;
};

int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    qmlRegisterType<EnumSubject>("Example.EnumControl", 1, 0, "EnumSubject");
    QQmlEngine engine;
    QQmlComponent component(&engine);
    component.setData(R"(import Example.EnumControl 1.0
EnumSubject { wide: EnumSubject.Wide.Huge; property string result: String(wide) }
)", QUrl());
    std::unique_ptr<QObject> object(component.create());
    if (!object) { qWarning() << component.errors(); return 1; }
    const auto meta = QMetaEnum::fromType<EnumSubject::Wide>();
    const auto native = meta.keyToValue64("Huge");
    if (!native || *native != 4294967297ULL || !meta.is64Bit()) return 2;
    // Qt 6.12's QML constant lookup truncates this value to 32 bits, while
    // its native enum metadata preserves all 64 bits.
    const auto qml = object->property("result").toString();
    std::cout << "native=" << *native << " qml=" << qml.toStdString() << '\n';
    return qml == QStringLiteral("1") ? 0 : 3;
}
#include "runtime-enums-native.moc"
