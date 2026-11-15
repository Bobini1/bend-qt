#!/usr/bin/env python3
"""Check generated QObject-reference signal connectors against real Qt."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
import signals


def connector(owner, name, arguments, with_type=False):
    generator = SimpleNamespace(classes={name: {'qobject': True} for name in ('QObject', 'QSessionManager')})
    converted = [dict(kind='object', name=kind, pointer=pointer,
                      native_codec='object', cpp=cpp)
                 for kind, pointer, cpp in arguments]
    function = dict(declaring_class=owner, name=name, const=False,
                    arguments=[dict(type=dict(cpp=cpp)) for _, _, cpp in arguments])
    method = dict(function=function, signal_connection_type=with_type,
                  signal=dict(args=converted, outputs=[], terminal=False, private_marker=False))
    return '\n'.join(signals.connect_case(generator, method))


HEADER = r'''#include <QtCore/QObject>
class ReferenceSender : public QObject {
    Q_OBJECT
public:
    using QObject::QObject;
    void fire(QObject &mutableObject, const QObject &readOnlyObject, QObject *nullable) {
        emit ready(mutableObject, readOnlyObject, nullable);
    }
signals:
    void ready(QObject &, const QObject &, QObject *);
};
'''

NATIVE = r'''
#include <QtCore/QtCore>
#include <QtGui/QGuiApplication>
#include <QtGui/QSessionManager>
#include <cassert>
#include <cerrno>
#include <memory>
#include <map>
#include <system_error>
#include "reference-sender.h"
struct BqtValue { uint32_t word = 0; const void *pointer = nullptr; std::vector<BqtValue> items; };
struct BqtRequest { uint32_t self = 1; BqtValue arguments[2], result; int error = 0; const char *message = ""; };
struct NativeCallScope {};
struct CallbackNativeArguments {};
struct NativeAggregateInputScope { explicit NativeAggregateInputScope(BqtRequest *) {} };
static BqtValue sequence_value(size_t size) { BqtValue value; value.items.resize(size); return value; }
struct CallbackOwnedArguments { BqtValue value; BqtValue take() { return std::move(value); } };
static int last_error = 0, received = 0;
static std::vector<const QObject *> expected;
static bool fail(BqtRequest *r, int code, const char *message) { r->error=code; r->message=message; return true; }
static void callback_report_error(int code, const char * = "") { last_error=code; }
static void callback_signal_error(uint32_t, int code) { last_error=code; }
static bool callback_connection_type(BqtRequest *, uint32_t) { return true; }
struct Record { QObject *context = nullptr; QMetaObject::Connection *connection = nullptr; };
static std::map<uint32_t, Record> records;
static uint32_t next_connection = 0;
static Record *connection(uint32_t id) { return &records.at(id); }
static uint32_t new_connection(BqtRequest *, uint32_t) { records.emplace(++next_connection, Record{}); return next_connection; }
static void clear_connections() { for (auto &[id,r] : records) { delete r.connection; delete r.context; } records.clear(); }
struct CallbackConnectionGuard { uint32_t id=0; bool keep=false; ~CallbackConnectionGuard() { if(id && !keep) clear_connections(); } };
static bool callback_decode_unit(BqtRequest *, const BqtValue &, void *) { return true; }
static int callback_invoke(uint32_t, uint32_t, BqtValue values, decltype(&callback_decode_unit), void *) {
    assert(values.items.size()==expected.size());
    for(size_t i=0;i<expected.size();++i) assert(values.items[i].pointer==expected[i]);
    const_cast<QObject *>(expected[0])->setObjectName(QStringLiteral("changed"));
    ++received; return 0;
}
static BqtValue write_object(BqtRequest *, const QObject *object) { BqtValue value; value.pointer=object; return value; }
template<class F> static bool callback_signal_call_with_type(uint32_t, F function, uint32_t type, bool) {
    if ((type&3u)==Qt::QueuedConnection) return QMetaObject::invokeMethod(QCoreApplication::instance(), std::move(function), Qt::QueuedConnection);
    function(); return true;
}
namespace BendSignalApi {
static bool synchronous_native_arguments(uint32_t type) { return (type&3u)!=Qt::QueuedConnection; }
struct Snapshot {
    std::vector<QPointer<QObject>> objects;
    void guard(const QVariant &value, unsigned, bool) {
        auto *object=value.value<QObject *>();
        if(!object) object=const_cast<QObject *>(value.value<const QObject *>());
        if(object) objects.push_back(object);
    }
    bool live() const { for(const auto &object:objects) if(!object) return false; return true; }
    bool capture_origins(BqtRequest *, uint32_t) { return true; }
    bool stage_native_arguments(BqtRequest *, CallbackNativeArguments &, uint32_t) { return true; }
    bool finish_output(BqtRequest *, BqtValue &) const { return true; }
};
}
@SNAPSHOTS@
QVariant native_owned_variant_snapshot(const QVariant &value, unsigned) { return value; }
@CONNECTORS@
int main(int argc, char **argv) {
    QCoreApplication application(argc,argv);
    ReferenceSender sender;
    QObject mutableObject, readOnlyObject;
    readOnlyObject.setObjectName(QStringLiteral("constant"));
    expected={&mutableObject,&readOnlyObject,nullptr};
    BqtRequest direct;
    connect_direct(&direct,&sender);
    assert(!direct.error);
    sender.fire(mutableObject,readOnlyObject,nullptr);
    assert(received==1 && !last_error && mutableObject.objectName()==QStringLiteral("changed"));
    assert(readOnlyObject.objectName()==QStringLiteral("constant"));
    clear_connections();
    received=0; mutableObject.setObjectName(QStringLiteral("before"));
    BqtRequest queued; queued.arguments[0].word=Qt::QueuedConnection;
    connect_with(&queued,&sender);
    sender.fire(mutableObject,readOnlyObject,nullptr);
    assert(!queued.error && !received && mutableObject.objectName()==QStringLiteral("before"));
    QCoreApplication::processEvents();
    assert(received==1 && !last_error && mutableObject.objectName()==QStringLiteral("changed"));
    received=0;
    auto *doomed=new QObject;
    sender.fire(*doomed,*doomed,nullptr);
    delete doomed;
    QCoreApplication::processEvents();
    assert(!received && last_error==ESTALE);
    clear_connections();
    puts("QT612_QOBJECT_REFERENCE_SIGNALS_OK identity=1 const=1 null=1 queued=1 stale=1 session_manager_compiles=1");
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qt-root', type=Path, default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    parser.add_argument('--work', type=Path, default=ROOT / 'build/qobject-reference-signals')
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    references = [('QObject', False, 'QObject &'), ('QObject', False, 'const QObject &'), ('QObject', True, 'QObject *')]
    parts = []
    for name, owner, signal, arguments, with_type in [
            ('connect_direct','ReferenceSender','ready',references,False),
            ('connect_with','ReferenceSender','ready',references,True),
            ('connect_commit','QGuiApplication','commitDataRequest',[('QSessionManager',False,'QSessionManager &')],False),
            ('connect_save','QGuiApplication','saveStateRequest',[('QSessionManager',False,'QSessionManager &')],True)]:
        parts.append(f'bool {name}(BqtRequest *r, {owner} *self) {{\n' + connector(owner,signal,arguments,with_type) + '\nreturn true;\n}\n')
    source = NATIVE.replace('@SNAPSHOTS@', (ROOT / 'generator/templates/native_snapshots.cpp').read_text()).replace('@CONNECTORS@', ''.join(parts))
    header = args.work / 'reference-sender.h'; header.write_text(HEADER)
    path = args.work / 'main.cpp'; path.write_text(source)
    moc = args.work / 'moc-reference-sender.cpp'
    includes = ['-I'+str(args.qt_root/'include'), '-I'+str(args.qt_root/'include/QtCore'), '-I'+str(args.qt_root/'include/QtGui')]
    subprocess.run([str(args.qt_root/'libexec/moc'), *includes, str(header), '-o', str(moc)], check=True)
    flags = ['clang++-19','-std=c++17','-O1','-fPIC',*includes]
    binary = args.work/'check'
    compiled = subprocess.run([*flags,str(path),str(moc),'-L'+str(args.qt_root/'lib'),'-lQt6Gui','-lQt6Core','-o',str(binary)],text=True,capture_output=True)
    (args.work/'compile.log').write_text(compiled.stdout+compiled.stderr)
    if compiled.returncode: raise RuntimeError('QObject reference connector compilation failed; see compile.log')
    tested = subprocess.run([str(binary)],env=dict(os.environ,LD_LIBRARY_PATH=str(args.qt_root/'lib')),text=True,capture_output=True)
    (args.work/'native.log').write_text(tested.stdout+tested.stderr)
    if tested.returncode: raise RuntimeError('QObject reference signal runtime check failed; see native.log')
    broken = source.replace('native_owned_snapshot(&a0)', 'native_owned_snapshot(a0)')
    assert broken != source
    negative = args.work/'copy-negative.cpp'; negative.write_text(broken)
    rejected = subprocess.run([*flags,'-fsyntax-only',str(negative)],text=True,capture_output=True)
    (args.work/'copy-negative.log').write_text(rejected.stdout+rejected.stderr)
    assert rejected.returncode and ('deleted' in rejected.stderr or 'private destructor' in rejected.stderr), 'QObject copy regression was not detected'
    (args.work/'receipt.json').write_text(json.dumps(dict(passed=True,mutable_and_const_identity=True,
        nullable_pointer=True,queued_identity=True,deleted_argument_guard=True,session_manager_compiles=True,
        copy_negative_control=True,generator_sha256=hashlib.sha256((ROOT/'generator/signals.py').read_bytes()).hexdigest(),
        boundary='Generated connectors and native snapshots with real Qt signals; small wire, scope and scheduler shims. Full Bend package remains an integration gate.'),indent=2)+'\n')
    print(tested.stdout.strip())


if __name__ == '__main__':
    main()
