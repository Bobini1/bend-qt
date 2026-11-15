#!/usr/bin/env python3
"""Check outlined signal codecs through bounded units and packaged native ELF."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
import custom_signals
import native_shards
import native_workspace
from backend import compile_backend


def load_shard_control():
    spec = importlib.util.spec_from_file_location('native_shard_control', ROOT / 'scripts/check-qt-native-shards.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture():
    rows = [
        ('int', dict(kind='i32')),
        ('QString', dict(kind='string')),
        ('QVariant', dict(kind='value', name='QVariant')),
        ('QCommandLineOption', dict(kind='value', name='QCommandLineOption')),
        ('QWebSocketCorsAuthenticator', dict(kind='value', name='QWebSocketCorsAuthenticator')),
        ('QMetaProperty', dict(kind='value', name='QMetaProperty')),
        ('QList<QString>', dict(kind='list', children=[dict(kind='string')])) ,
        ('QList<QObject*>', dict(kind='list', children=[dict(kind='object', name='QObject')])) ,
        ('QMap<QString,QMetaProperty>', dict(kind='map', children=[dict(kind='string'), dict(kind='value', name='QMetaProperty')])) ,
        ('QEvent*', dict(kind='object', name='QEvent')),
        ('UnassignableValue', dict(kind='value', name='UnassignableValue')),
    ]
    while len(rows) < 128:
        rows.append(('int', dict(kind='i32')))
    rows.append(('RhiOnlyValue', dict(kind='value', name='RhiOnlyValue')))
    arguments = [(None, native, dict(value, native_codec=f'shard_{i}')) for i, (native, value) in enumerate(rows)]
    generator = SimpleNamespace(custom_signal_arguments=arguments,
        ids={'QObject': 1, 'QEvent': 2}, callback_qml=False,
        classes={'QObject': dict(qobject=True), 'QEvent': dict(qobject=False)})
    generator.abi_cohort = dict(names={'RhiOnlyValue'}, headers=[], pattern=re.compile(r'\bRhiOnlyValue\b'),
        proxies=set(), operations=set(), exact_helpers={})
    generated = custom_signals.cpp(generator)
    stripped, auxiliary = native_shards.split_auxiliary(generated)
    typed = [row for row in auxiliary if row[0] == 'native_signal_arguments']
    dispatchers = [row for row in auxiliary if row[0] == 'signal_dispatch']
    assert len(typed) == len(arguments) == 129
    assert [identifier for family, identifier, body in typed] == list(range(129))
    assert [identifier for family, identifier, body in dispatchers] == list(range(7))
    # Argument descriptors need the full request wire shape; the runtime-hub
    # control tests that seventh dispatcher separately.
    auxiliary = [row for row in auxiliary if row[:2] != ('signal_dispatch', 6)]
    declaration_start = stripped.index('namespace BendSignalApi {\nstruct Snapshot;')
    owned_start = stripped.index('extern __attribute__((visibility("hidden"))) QVariant native_owned_variant_snapshot', declaration_start)
    argument_start = stripped.index('extern __attribute__((visibility("hidden"))) int argument_type', owned_start)
    snapshot_start = stripped.index('struct Snapshot {', argument_start)
    live_start = stripped.index('    bool live() const', snapshot_start)
    declarations = stripped[declaration_start:owned_start]
    dispatch = stripped[owned_start:argument_start] + '} // namespace BendSignalApi\n'
    snapshot = 'namespace BendSignalApi {\nstruct SnapshotOrigin;\n' + stripped[snapshot_start:live_start] + '};\n}\n'
    for forbidden in ('qRegisterMetaType<', 'QMetaType::fromType<', 'QVariant::fromValue(native_owned_snapshot'):
        assert forbidden not in declarations + dispatch + snapshot, forbidden
    prototypes = '\n'.join(line for line in declarations.splitlines() if line.startswith('extern '))
    assert prototypes and 'visibility("hidden")' in prototypes
    codecs = []
    for i, (native, value) in enumerate(rows):
        body = f'''static std::optional<{native}> read_shard_{i}(BqtRequest *, const BqtValue &value) {{
    if (value.tag == 9) {{ signal_codec_error = EILSEQ; return {{}}; }}
    return std::optional<{native}>(std::in_place, *static_cast<{native} const *>(value.pointer));
}}
static BqtValue write_shard_{i}(BqtRequest *, {native} const &value) {{
    auto copy = std::shared_ptr<{native}>(new {native}(value));
    signal_codec_copies.push_back(copy);
    return BqtValue{{0, copy.get()}};
}}
'''
        if native == 'RhiOnlyValue': body = '#if BQT_HAS_RHI\n' + body + '#endif\n'
        codecs.append(body)
    preamble = r'''
#include <QtCore/QtCore>
#include <QtCore/qtmocconstants.h>
#include <QtWebSockets/QWebSocketCorsAuthenticator>
#include <array>
#include <optional>
#include <vector>
#include <memory>
#include <cassert>
#include <cerrno>
#include <climits>
#include <map>
#include <set>
#include <cstring>
#include <stdexcept>
#ifndef BQT_HAS_RHI
#define BQT_HAS_RHI 1
#endif
struct BqtValue { uint32_t tag = 0; const void *pointer = nullptr; };
struct UnassignableValue {
    int value;
    explicit UnassignableValue(int v) : value(v) {}
    UnassignableValue(const UnassignableValue &) = default;
    UnassignableValue &operator=(const UnassignableValue &) = delete;
};
Q_DECLARE_METATYPE(UnassignableValue)
#if BQT_HAS_RHI
struct RhiOnlyValue { int value; };
Q_DECLARE_METATYPE(RhiOnlyValue)
#endif
'''
    setup = r'''
static int signal_codec_error = 0;
static QThread *main_thread = QThread::currentThread();
static std::vector<std::shared_ptr<void>> signal_codec_copies;
static bool fail(BqtRequest *, int code, const char *) { signal_codec_error = code; return true; }
struct NativePointerCapture { const void *pointer; uint16_t type; bool native_frame; };
struct NativeMetadataCapture { const QMetaObject *pointer; };
static NativePointerCapture native_pointer_capture(const void *pointer, uint16_t type, bool native_frame) { return {pointer,type,native_frame}; }
static std::optional<NativeMetadataCapture> native_metadata_capture(const QMetaObject *meta) { return NativeMetadataCapture{meta}; }
namespace BendQmlLists {
struct Capture {};
static std::optional<Capture> capture(const QVariant &) { return {}; }
}
namespace OpaqueData {
using Value = int;
static QMetaType meta_type() { return QMetaType(QMetaType::Int); }
static std::optional<int> read(BqtRequest *, const BqtValue &wire) { return *static_cast<const int *>(wire.pointer); }
static BqtValue write(BqtRequest *, const int &value) { return {0,&value}; }
}
static QMetaType runtime_argument_meta(int) { return {}; }
static QVariant runtime_argument_read(BqtRequest *r, int, const BqtValue &) { fail(r,ENOTSUP,"unavailable"); return {}; }
static BqtValue runtime_argument_write(BqtRequest *r, int, const void *) { fail(r,ENOTSUP,"unavailable"); return {}; }
static bool runtime_argument_assign(BqtRequest *r, int, void *, const void *) { fail(r,ENOTSUP,"unavailable"); return false; }
'''
    native_snapshots = (ROOT / 'generator/templates/native_snapshots.cpp').read_text()
    values = ((ROOT / 'generator/templates/dynamic_metadata.cpp').read_text()
              + (ROOT / 'generator/templates/value_types.cpp').read_text())
    shared = setup + values + ''.join(codecs) + native_snapshots + declarations + dispatch + snapshot
    shared += ''.join('// BQT_AUXILIARY_BEGIN ' + family + ' ' + str(identifier) + '\n' + body +
                      '// BQT_AUXILIARY_END ' + family + ' ' + str(identifier) + '\n'
                      for family, identifier, body in auxiliary)
    shared += r'''
static QMetaType (*signal_codec_identity)() = nullptr;
static const QMetaObject *signal_codec_metadata = nullptr;
static QVariant signal_codec_snapshot;
static std::unique_ptr<BendSignalApi::Snapshot> signal_codec_guards;
'''
    create = r'''
    signal_codec_identity = &BendSignalApi::bqt_native_signal_argument_0_meta;
    const int input = 42;
    BqtValue wire{0,&input};
    auto native = BendSignalApi::read_value(r,0,wire);
    if (native.toInt()!=42 || native.metaType()!=BendSignalApi::meta_type(0)) { r->value=0; return true; }
    auto written=BendSignalApi::write_value(r,0,native.constData());
    if (*static_cast<const int *>(written.pointer)!=42) { r->value=0; return true; }
    int output=0;
    if (!BendSignalApi::assign_value(r,0,&output,native) || output!=42) { r->value=0; return true; }
    QCommandLineOption option(QStringLiteral("native-option"));
    auto nondefault=BendSignalApi::read_value(r,3,BqtValue{0,&option});
    if (static_cast<const QCommandLineOption *>(nondefault.constData())->names()!=option.names()) { r->value=0; return true; }
    QWebSocketCorsAuthenticator explicit_copy(QStringLiteral("https://bend.example"));
    auto copied=BendSignalApi::read_value(r,4,BqtValue{0,&explicit_copy});
    if (static_cast<const QWebSocketCorsAuthenticator *>(copied.constData())->origin()!=explicit_copy.origin()) { r->value=0; return true; }
    const auto property=QObject::staticMetaObject.property(QObject::staticMetaObject.indexOfProperty("objectName"));
    signal_codec_metadata=property.enclosingMetaObject();
    QMap<QString,QMetaProperty> metadata{{QStringLiteral("item"),property}};
    BendSignalApi::Snapshot reflection;
    reflection.guard(QVariant::fromValue(metadata));
    if (reflection.metadata.size()!=1 || reflection.metadata.front().pointer!=signal_codec_metadata) { r->value=0; return true; }
    QChar external[3]={QChar('o'),QChar('l'),QChar('d')};
    QList<QString> strings{QString::fromRawData(external,3)};
    signal_codec_snapshot=native_owned_snapshot(QVariant::fromValue(strings));
    external[0]=QChar('x');
    if (signal_codec_snapshot.value<QList<QString>>().front()!=QStringLiteral("old")) { r->value=0; return true; }
    QObject *guarded_object=new QObject;
    auto *gadget_type=BendValueTypes::define("CodecGuardRecord", {{"object",QMetaType::fromType<QObject *>()}});
    auto gadget=gadget_type->create();
    if (!BendValueTypes::write(gadget,"object",QVariant::fromValue(guarded_object))) { r->value=0; return true; }
    BendSignalApi::Snapshot gadget_guard; gadget_guard.guard(gadget);
    if (gadget_guard.objects.size()!=1 || gadget_guard.objects.front().identity!=guarded_object) { r->value=0; return true; }
    signal_codec_guards=std::make_unique<BendSignalApi::Snapshot>();
    signal_codec_guards->guard(QVariant::fromValue(QList<QObject*>{guarded_object}));
    if(signal_codec_guards->objects.size()!=1 || signal_codec_guards->objects.front().object.data()!=guarded_object) { r->value=0; return true; }
    delete guarded_object;
    QEvent event(QEvent::User); QEvent *event_pointer=&event;
    BendSignalApi::Snapshot native_pointer;
    native_pointer.guard(QVariant::fromValue(event_pointer),0,true);
    if (native_pointer.native_objects.size()!=1 || native_pointer.native_objects[0].pointer!=&event || !native_pointer.native_objects[0].native_frame) { r->value=0; return true; }
    UnassignableValue unassignable(71);
    auto unassigned=BendSignalApi::read_value(r,10,BqtValue{0,&unassignable});
    if (BendSignalApi::can_assign(10) || BendSignalApi::assign_value(r,10,&unassignable,unassigned) || signal_codec_error!=ENOTSUP || unassignable.value!=71) { r->value=0; return true; }
    signal_codec_error=0;
    if (BendSignalApi::read_value(r,0,BqtValue{9,&input}).isValid() || signal_codec_error!=EILSEQ) { r->value=0; return true; }
    signal_codec_error=0;
    QVariant opaque(QStringLiteral("already-a-variant"));
    auto variant=BendSignalApi::read_value(r,2,BqtValue{0,&opaque});
    if (variant.metaType()!=QMetaType(QMetaType::QString) || variant.toString()!=opaque.toString()) { r->value=0; return true; }
#if BQT_HAS_RHI
    if (!BendSignalApi::meta_type(128).isValid()) { r->value=0; return true; }
#else
    if (BendSignalApi::meta_type(128).isValid()) { r->value=0; return true; }
    BendSignalApi::read_value(r,128,wire);
    if (signal_codec_error!=ENOTSUP) { r->value=0; return true; }
#endif
    signal_codec_error=0;
'''
    verify = r'''
    r->value=r->value && signal_codec_identity==&BendSignalApi::bqt_native_signal_argument_0_meta
        && signal_codec_identity()==BendSignalApi::meta_type(0)
        && BendSignalApi::bqt_native_signal_argument_127_meta()==BendSignalApi::meta_type(0)
        && QMetaType::fromName("int")==BendSignalApi::meta_type(0)
        && signal_codec_metadata==&QObject::staticMetaObject
        && signal_codec_snapshot.value<QList<QString>>().front()==QStringLiteral("old")
        && signal_codec_guards->objects.front().object.isNull();
    signal_codec_snapshot.clear(); signal_codec_guards.reset(); signal_codec_copies.clear();
'''
    control = load_shard_control()
    source = preamble + control.NATIVE
    source = source.replace('static int initializations = 0;', shared + '\nstatic int initializations = 0;')
    source = source.replace('r->pointer = registry_pointer; r->value = 1; return true;',
        'r->pointer = registry_pointer; r->value = 1;\n' + create + '\nreturn true;')
    source = source.replace('catch (const Marker &value) { r->value = r->value && value.value == 77; }',
        'catch (const Marker &value) { r->value = r->value && value.value == 77; }\n' + verify)
    return source, control.CONSUMER


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=ROOT / 'build/native-signal-shards')
    parser.add_argument('--qt-root', type=Path, default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    source, consumer = fixture()
    receipts = {}
    os.environ['BQT_SHARD_OPERATIONS'] = '1'
    os.environ['BQT_AUXILIARY_FUNCTIONS'] = '128'
    os.environ['BQT_SHARD_JOBS'] = '1'
    os.environ['BQT_COMPILER_AS_MIB'] = '4096'
    for public in (False, True):
        folder = args.work / ('public' if public else 'full'); folder.mkdir(exist_ok=True)
        path = folder / 'wrappers.cpp'
        path.write_text(('#define BQT_HAS_RHI 0\n' if public else '#define BQT_HAS_RHI 1\n') + source)
        native_shards.write_changed(folder / 'shared-input.h', '#define INPUT_VALUE 47\n')
        payload, imports, native = compile_backend(path, args.qt_root, folder, 'clang++-19', ['QtCore','QtWebSockets'])
        assert native['shards']['auxiliary_functions'] == 135
        assert native['shards']['auxiliary_shards'] == 3
        assert native['shards']['operation_shards'] == 4
        shared = (native_workspace.actual_work(folder) / 'shards/shared.hpp').read_text()
        assert 'qRegisterMetaType<' not in shared
        assert 'return assign_native<' not in shared
        code = consumer.replace('@PAYLOAD@', payload).replace('exceptions=1', 'exceptions=1 native_signal_codecs=1')
        consumer_path = folder / 'consumer.c'; consumer_path.write_text(code)
        binary = folder / 'consumer'
        subprocess.run(['clang', str(consumer_path), '-ldl', '-pthread', '-o', str(binary)], check=True)
        environment = dict(os.environ, LD_LIBRARY_PATH=str(args.qt_root / 'lib'))
        tested = subprocess.run([str(binary)], env=environment, text=True, capture_output=True)
        (folder / 'native.log').write_text(tested.stdout + tested.stderr)
        if tested.returncode: raise RuntimeError(f'Native signal codec consumer failed ({tested.returncode}); see {folder / "native.log"}')
        receipts['public' if public else 'full'] = dict(passed=True, shards=native['shards'],
            output=tested.stdout, relocations=native['payload']['relocations'])
    receipt = dict(passed=True, cases=129, bounded_auxiliary_groups=True,
        exact_native_metatypes=True, nondefault_and_explicit_copy=True,
        metadata_and_pointer_guards=True, owned_container_snapshots=True,
        native_assignment_and_errors=True, cross_translation_unit_identity=True,
        public_abi_cohort_guard=True, payloads=receipts,
        generator_sha256=hashlib.sha256((ROOT / 'generator/custom_signals.py').read_bytes()).hexdigest(),
        template_sha256=hashlib.sha256((ROOT / 'generator/templates/custom_signals.cpp').read_bytes()).hexdigest(),
        dispatch_sha256=hashlib.sha256((ROOT / 'generator/runtime_dispatch.py').read_bytes()).hexdigest(),
        boundary='Real Qt codec adapters and packaged native payload with small codec shims; full generated Bend wire codecs and package consumers remain integration gates')
    (args.work / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('QT612_NATIVE_SIGNAL_SHARDS_OK full=1 public_abi=1 codecs=129 batches=3 dispatchers=6 nondefault=1 metadata=1 containers=1 guards=1 identity=1', flush=True)


if __name__ == '__main__':
    main()
