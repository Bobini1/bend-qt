#ifndef BEND_QT_QIO_PIPE_H
#define BEND_QT_QIO_PIPE_H
#include <QtCore/QObject>
#include <QtCore/QIODevice>
#include <QtCore/QPointer>
#include <memory>
#include <limits>
#include <cstring>
QT_BEGIN_NAMESPACE
namespace QtCoreHelper {
class QIOPipe : public QObject {
    Q_OBJECT
public:
    explicit QIOPipe(QObject *parent = nullptr);
    ~QIOPipe() override;
    bool open(QIODeviceBase::OpenMode mode);
    QIODevice *end1() const;
    QIODevice *end2() const;
private:
    QPointer<QIODevice> first;
    QPointer<QIODevice> second;
};
}
QT_END_NAMESPACE
#endif
