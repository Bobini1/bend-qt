#!/usr/bin/env python3
"""Check owning dynamic gadgets and actual QML structured-value writeback."""
import argparse
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = r'''
#include <QtCore/QtCore>
#include <QtCore/qtmocconstants.h>
#include <QtQml/QtQml>
#include <QtQml/qqmlprivate.h>
#include <algorithm>
#include <map>
#include <set>
#include <memory>
#include <vector>
#include <stdexcept>
#include <cstring>
#include <cstdio>
#include "dynamic_metadata.cpp"
#include "value_types.cpp"
using namespace BendValueTypes;
static int expose(Type *type, const char *name) {
    QQmlPrivate::RegisterType registration{};
    registration.structVersion = QQmlPrivate::RegisterType::CurrentVersion;
    registration.typeId = type->type();
    registration.listId = type->list_type();
    registration.uri = "Bend.Values";
    registration.version = QTypeRevision::fromVersion(1, 0);
    registration.elementName = name;
    registration.metaObject = type->meta;
    registration.parserStatusCast = registration.valueSourceCast = registration.valueInterceptorCast = registration.finalizerCast = -1;
    registration.creationMethod = QQmlPrivate::ValueTypeCreationMethod::Structured;
    const int id = QQmlPrivate::qmlregister(QQmlPrivate::TypeRegistration, &registration);
    QQmlPrivate::RegisterSequentialContainer sequence{};
    sequence.uri = registration.uri; sequence.version = registration.version;
    sequence.typeId = type->list_type(); sequence.metaSequence = QMetaSequence(&type->sequence);
    QQmlPrivate::qmlregister(QQmlPrivate::SequentialContainerRegistration, &sequence);
    return id;
}
int main(int argc, char **argv) {
    QCoreApplication application(argc, argv);
    const auto integer = QMetaType::fromType<qint64>(), number = QMetaType::fromType<double>();
    std::vector<Field> fields{{"timestamp", integer}, {"position", number}};
    auto *time = define("BendTime", fields);
    Q_ASSERT(define("BendTime", fields) == time);
    try { define("BendTime", {{"different", integer}}); Q_UNREACHABLE(); }
    catch (const std::invalid_argument &) {}
    try { define("QString", fields); Q_UNREACHABLE(); }
    catch (const std::invalid_argument &) {}
    auto *change = define("BendBpmChange", {{"time", time->type()}, {"bpm", number}});
    auto value = time->create();
    Q_ASSERT(write(value, "timestamp", QVariant::fromValue(qint64(9007199254740997))));
    Q_ASSERT(write(value, "position", 0.25));
    auto copied = value;
    Q_ASSERT(write(copied, "position", 2.5));
    Q_ASSERT(read(value, "position").toDouble() == 0.25);
    Q_ASSERT(read(copied, "timestamp").toLongLong() == 9007199254740997LL);
    auto changed = change->create(); Q_ASSERT(write(changed, "time", copied));
    auto nested = read(changed, "time"); Q_ASSERT(write(nested, "position", 7.5));
    Q_ASSERT(read(read(changed, "time"), "position").toDouble() == 2.5);
    Q_ASSERT(write(changed, "time", nested));
    Q_ASSERT(read(read(changed, "time"), "position").toDouble() == 7.5);
    auto before = changed;
    QByteArray bytes; QDataStream output(&bytes, QIODevice::WriteOnly); output << changed << copied;
    QVariant restored, restoredTime; QDataStream input(bytes); input >> restored >> restoredTime;
    Q_ASSERT(input.status() == QDataStream::Ok && restored == before && restoredTime == copied);
    Field constant{"fixed", integer}; constant.constant = true;
    Field reset{"resettable", number}; reset.resettable = true; reset.stored = false;
    auto *attributes = define("BendValueAttributes", {constant, reset, {"payload", QMetaType::fromType<QVariant>()}});
    auto data = attributes->create();
    Q_ASSERT(!write(data, "fixed", 5)); Q_ASSERT(write(data, "resettable", 6.5));
    const auto property = attributes->meta->property(attributes->meta->indexOfProperty("resettable"));
    Q_ASSERT(!property.isStored() && property.resetOnGadget(data.data()));
    Q_ASSERT(read(data, "resettable").toDouble() == 0);
    const QVariantMap map{{"number", 42}, {"text", "hello"}};
    Q_ASSERT(write(data, "payload", map)); Q_ASSERT(read(data, "payload").toMap() == map);
    Q_ASSERT(expose(time, "time") >= 0 && expose(change, "bpmChange") >= 0);
    {
        QQmlEngine engine; QQmlComponent component(&engine);
        component.setData(R"QML(
import QtQml
import Bend.Values 1.0
QtObject {
    property time stamp: ({ timestamp: 1234, position: 0.5 })
    property bpmChange change: ({ time: ({ timestamp: 2000, position: 1.5 }), bpm: 120 })
    property double observed: stamp.position
    property list<time> entries: [({ timestamp: 10, position: 0.125 }), ({ timestamp: 20, position: 0.75 })]
    property list<bpmChange> changes: [({time: ({timestamp: 30, position: 3}), bpm: 180})]
    property double listPosition: entries[1].position
    function modify() { stamp.position = 2.25; change.time.position = 4.5; entries[1].position = 6.25; }
}
)QML", QUrl("file:///bend-value-types.qml"));
        if (component.isError()) qFatal("%s", qPrintable(component.errorString()));
        std::unique_ptr<QObject> object(component.create());
        if (!object) qFatal("%s", qPrintable(component.errorString()));
        Q_ASSERT(object->property("stamp").metaType() == time->type());
        Q_ASSERT(object->property("observed").toDouble() == 0.5);
        Q_ASSERT(object->property("entries").metaType() == time->list_type());
        Q_ASSERT(object->property("changes").metaType() == change->list_type());
        Q_ASSERT(time->list_type() != change->list_type());
        Q_ASSERT(object->property("listPosition").toDouble() == 0.75);
        Q_ASSERT(QMetaObject::invokeMethod(object.get(), "modify"));
        Q_ASSERT(object->property("observed").toDouble() == 2.25);
        Q_ASSERT(object->property("listPosition").toDouble() == 6.25);
        Q_ASSERT(read(read(object->property("change"), "time"), "position").toDouble() == 4.5);
        Q_ASSERT(read(value, "position").toDouble() == 0.25);
    }
    puts("QT_VALUE_TYPE_CORE_OK owning_copies=1 nested_values=1 stream=1 qml_structure=1 writeback=1");
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qt-root', type=Path, default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    parser.add_argument('--work', type=Path, default=ROOT / 'build/value-type-core-check')
    parser.add_argument('--cxx', default='clang++-19')
    args = parser.parse_args(); qt = args.qt_root.resolve(); work = args.work.resolve(); work.mkdir(parents=True, exist_ok=True)
    source = work / 'main.cpp'; source.write_text(SOURCE)
    executable = work / 'app'
    command = [args.cxx, '-std=c++17', '-O1', '-fPIC', '-DQT_NO_VERSION_TAGGING',
               '-I' + str(qt / 'include'), '-I' + str(qt / 'include/QtCore'), '-I' + str(qt / 'include/QtQml'),
               '-I' + str(ROOT / 'generator/templates'), str(source), '-o', str(executable),
               '-L' + str(qt / 'lib'), '-lQt6Qml', '-lQt6Network', '-lQt6Core']
    compiled = subprocess.run(command, text=True, capture_output=True)
    (work / 'compile.log').write_text(compiled.stdout + compiled.stderr)
    if compiled.returncode:
        raise RuntimeError('Value core compilation failed; see ' + str(work / 'compile.log'))
    env = dict(os.environ, LD_LIBRARY_PATH=str(qt / 'lib'), QML_IMPORT_PATH=str(qt / 'qml'))
    tested = subprocess.run([str(executable)], env=env, text=True, capture_output=True)
    (work / 'run.log').write_text(tested.stdout + tested.stderr)
    if tested.returncode or 'QT_VALUE_TYPE_CORE_OK' not in tested.stdout:
        raise RuntimeError('Native value/QML check failed; see ' + str(work / 'run.log'))
    (work / 'receipt.json').write_text(json.dumps(dict(passed=True, qt=str(qt), command=command,
        owning_copies=True, nested_values=True, qdatastream_roundtrip=True, qml_structured_values=True,
        qml_nested_writeback=True, property_attributes=True, distinct_typed_sequences=True,
        boundary='Native reflected gadget/sequence core; Bend adapters and full package integration remain required'), indent=2) + '\n')
    print(tested.stdout.strip())


if __name__ == '__main__':
    main()
