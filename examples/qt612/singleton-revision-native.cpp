// Maintainer differential probe for the pinned Qt 6.12.0 registration policy.
// Run moc on this file to produce singleton-revision-native.moc, then compile
// with the QtCore, QtGui and QtQml include paths and libraries. The moc output
// belongs in the build directory, which must also be on the include path.
#include <QtCore/QMetaProperty>
#include <QtCore/QObject>
#include <QtCore/QString>
#include <QtGui/QGuiApplication>
#include <QtQml/QQmlComponent>
#include <QtQml/QQmlEngine>
#include <QtQml/qqmlprivate.h>
#include <cassert>
#include <iostream>
#include <memory>

class RevisedSingletonProbe final : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString revised READ revised NOTIFY revisedChanged REVISION(2))
public:
    explicit RevisedSingletonProbe(QObject *parent = nullptr) : QObject(parent) {}
    QString revised() const { return QStringLiteral("native"); }
signals:
    Q_REVISION(2) void revisedChanged();
};

int main(int argc, char **argv) {
    QGuiApplication application(argc, argv);
    QQmlPrivate::RegisterSingletonType type{};
    type.uri = "Probe.SingletonRevision";
    type.version = QTypeRevision::fromVersion(1, 0);
    type.typeName = "Settings";
    type.qObjectApi = [](QQmlEngine *engine, QJSEngine *) {
        return new RevisedSingletonProbe(engine);
    };
    type.instanceMetaObject = &RevisedSingletonProbe::staticMetaObject;
    type.typeId = QMetaType::fromType<RevisedSingletonProbe *>();
    type.revision = QTypeRevision::fromMinorVersion(0);
    const int registration = QQmlPrivate::qmlregister(QQmlPrivate::SingletonRegistration, &type);
    assert(registration >= 0);
    const auto property = type.instanceMetaObject->property(
        type.instanceMetaObject->indexOfProperty("revised"));
    assert(property.revision() == 0xff02);
    QQmlEngine engine;
    QQmlComponent component(&engine);
    component.setData("import QtQml\nimport Probe.SingletonRevision 1.0\n"
        "QtObject { property string result: typeof Settings.revised }", QUrl());
    assert(component.isReady());
    std::unique_ptr<QObject> object(component.create());
    assert(object);
    const auto result = object->property("result").toString();
    // Qt's JavaScript singleton lookup does not check the property's revision.
    assert(result == QStringLiteral("string"));
    std::cout << "NATIVE_SINGLETON_REVISION_JS=" << result.toStdString() << '\n';
}

#include "singleton-revision-native.moc"
