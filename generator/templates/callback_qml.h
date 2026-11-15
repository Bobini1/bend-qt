#pragma once
#include <QtCore/QObject>
#include <QtCore/QVariant>

namespace bendqt {
// Generated moc data for this fixed bridge is embedded in the package. User
// QML declarations are compiled by the installed Qt engine at runtime.
class CallbackQmlBridge : public QObject {
    Q_OBJECT
    Q_PROPERTY(quint32 handler READ handler WRITE setHandler)
public:
    explicit CallbackQmlBridge(QObject *parent = nullptr) : QObject(parent) {}
    quint32 handler() const { return handler_; }
    void setHandler(quint32 value) { handler_ = value; }
    Q_INVOKABLE QVariant invoke(quint32 method, const QVariantList &arguments);
private:
    quint32 handler_ = 0;
};
}
