#!/usr/bin/env python3
"""Check nine explicit outlined runtime dispatch hubs and public ABI guards."""
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
import native_shards
import native_workspace
import qt_objects
import runtime_dispatch
from backend import compile_backend


def fixture():
    spec = importlib.util.spec_from_file_location('runtime_signal_control', ROOT / 'scripts/check-qt-native-signal-shards.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    source, consumer = module.fixture()
    qml_forward = (ROOT / 'generator/templates/qml_list_properties.cpp').read_text().split('namespace BendQmlLists {', 1)[0]
    assert 'static ' not in qml_forward and qml_forward.count('visibility("hidden")') == 4
    source = source.replace('static int signal_codec_error = 0;', qml_forward + '\nstatic int signal_codec_error = 0;', 1)
    source = source.replace('struct BqtValue { uint32_t tag = 0; const void *pointer = nullptr; };',
        'struct BqtValue { uint32_t tag=0; const void *pointer=nullptr; uint32_t count=0; const BqtValue *items=nullptr; const char *text=nullptr; uint64_t size=0; uint32_t word=0, high=0; };')
    source = source.replace('uint32_t operation; intptr_t value; void *pointer; }',
                            'uint32_t operation; intptr_t value; void *pointer; int error; }')
    consumer = consumer.replace('uint32_t operation; intptr_t value; void *pointer; }',
                                 'uint32_t operation; intptr_t value; void *pointer; int error; }')
    source = source.replace('static bool fail(BqtRequest *, int code, const char *) { signal_codec_error = code; return true; }',
        'static bool fail(BqtRequest *r, int code, const char *) { r->error=code; signal_codec_error=code; return true; }')
    generator = SimpleNamespace(custom_signal_arguments=[(None, 'int', {}), (None, 'RhiOnlyValue', {})])
    generator.abi_cohort = dict(names={'RhiOnlyValue'}, headers=[], pattern=re.compile(r'\bRhiOnlyValue\b'),
        proxies=set(), operations=set(), exact_helpers={})
    cases, declarations, factories = qt_objects._binding_factory_parts(generator)
    assert cases[1].startswith('#if BQT_HAS_RHI\n') and cases[1].endswith('\n#endif')
    def body(template, name):
        begin = template.index('// BQT_RUNTIME_BODY_BEGIN ' + name + '\n')
        end = template.index('// BQT_RUNTIME_BODY_END ' + name + '\n', begin)
        return template[begin:end] + '// BQT_RUNTIME_BODY_END ' + name + '\n'
    template = (ROOT / 'generator/templates/qt_objects.cpp').read_text()
    hubs = 'namespace RuntimeQtObjects {\n' + body(template, 'binding_storage') + body(template, 'bound_native_name') + '}\n'
    hubs = hubs.replace('@HAS_QML@', '0').replace('@BINDING_CASES@', '\n'.join(cases)).replace('@NATIVE_CLASS_NAMES@', '"ReservedNative", "int"')
    signal_template = (ROOT / 'generator/templates/custom_signals.cpp').read_text()
    hubs += 'namespace BendSignalApi {\n' + body(signal_template, 'argument_type').replace('@TYPE_NAMES@', '{"int", 0}, {"RhiOnlyValue", 128}') + '}\n'
    hubs = runtime_dispatch.cpp(hubs)
    prefix = (ROOT / 'generator/templates/property_bindings.cpp').read_text() + r'''
namespace RuntimeEnums {
static bool is_code(int) { return false; }
static std::shared_ptr<BendPropertyBindings::Storage> binding_storage(int, QMetaType, BendPropertyBindings::Read, BendPropertyBindings::Write) { return {}; }
}
namespace BendQmlLists {
static int argument_type(BqtRequest *, const QByteArray &, const BqtValue *) { return INT_MIN; }
}
namespace RuntimeValueTypes {
static int argument_type(BqtRequest *, const QByteArray &, const BqtValue *) { return INT_MIN; }
static int sequence_type(BqtRequest *, const QByteArray &, const BqtValue *) { return INT_MIN; }
}
static int runtime_argument_index(BqtRequest *, const QByteArray &, const BqtValue *) { return 91; }
'''
    source = source.replace('static int initializations = 0;',
                            prefix + '\n'.join(declarations) + '\n' + ''.join(factories) + hubs + '\nstatic int initializations = 0;')
    verify = r'''
    r->error=0; signal_codec_error=0;
    BqtValue name{}; name.tag=1; name.text="int"; name.size=3;
    r->value = r->value && BendSignalApi::argument_type(r,name)==0 && !r->error;
    name.text="RhiOnlyValue"; name.size=12;
    r->value = r->value && BendSignalApi::argument_type(r,name)==128 && !r->error;
    name.text="AuthoredQObject*"; name.size=16;
    r->value = r->value && BendSignalApi::argument_type(r,name)==91 && !r->error;
    name.text="QList<Unknown>"; name.size=14;
    r->value = r->value && BendSignalApi::argument_type(r,name)==INT_MIN && r->error==ENOTSUP;
    r->error=0; signal_codec_error=0; name.tag=0;
    r->value = r->value && BendSignalApi::argument_type(r,name)==INT_MIN && r->error==EINVAL;
    r->error=0; signal_codec_error=0;
    auto read=[](bool)->std::optional<QVariant>{ return QVariant(37); };
    auto write=[](QVariant,bool){ return true; };
    auto storage=RuntimeQtObjects::binding_storage(0,QMetaType::fromType<int>(),read,write);
    r->value = r->value && storage && storage->metaType()==QMetaType::fromType<int>()
        && QBindable<int>(storage->bindable(false)).value()==37;
#if BQT_HAS_RHI
    auto rhi=RuntimeQtObjects::binding_storage(1,QMetaType::fromType<RhiOnlyValue>(),
        [](bool)->std::optional<QVariant>{return QVariant::fromValue(RhiOnlyValue{73});},write);
    r->value = r->value && rhi && rhi->metaType()==QMetaType::fromType<RhiOnlyValue>()
        && QBindable<RhiOnlyValue>(rhi->bindable(false)).value().value==73;
#else
    r->value = r->value && !RuntimeQtObjects::binding_storage(1,QMetaType{},read,write);
#endif
    r->value = r->value && RuntimeQtObjects::bound_native_name("ReservedNative")
        && RuntimeQtObjects::bound_native_name("int")
        && !RuntimeQtObjects::bound_native_name("UnregisteredAuthoredClass");
'''
    source = source.replace('r->value = task_context == 7 && initializations == 1; return true;',
                            'r->value = task_context == 7 && initializations == 1;\n' + verify + '\nreturn true;')
    _, blocks = native_shards.split_auxiliary(source)
    assert len([row for row in blocks if row[0] in ('signal_dispatch', 'qt_object_dispatch')]) == 9
    return source, consumer, cases[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=ROOT / 'build/qt612/runtime-dispatch-check')
    parser.add_argument('--qt-root', type=Path, default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    args = parser.parse_args(); work=args.work.resolve(); work.mkdir(parents=True,exist_ok=True)
    receipt=dict(passed=False); receipt_path=work/'receipt.json';receipt_path.write_text(json.dumps(receipt)+'\n')
    source, consumer, guarded_case=fixture()
    for invalid in ('static auto meta_type(int type) {\nreturn 1;\n}\n',
                    'static int meta_type(int type = 0) {\nreturn 1;\n}\n'):
        try: runtime_dispatch.cpp('// BQT_RUNTIME_BODY_BEGIN meta_type\n'+invalid+'// BQT_RUNTIME_BODY_END meta_type\n')
        except ValueError: pass
        else: raise RuntimeError('Deduced-return/default-argument dispatch expansion was accepted')
    previous={key:os.environ.get(key) for key in ('BQT_SHARD_OPERATIONS','BQT_AUXILIARY_FUNCTIONS','BQT_SHARD_JOBS','BQT_COMPILER_AS_MIB')}
    os.environ.update(BQT_SHARD_OPERATIONS='1',BQT_AUXILIARY_FUNCTIONS='128',BQT_SHARD_JOBS='1',BQT_COMPILER_AS_MIB='4096')
    try:
        payloads={}
        for public in (False,True):
            folder=work/('public' if public else 'full');folder.mkdir(exist_ok=True)
            path=folder/'wrappers.cpp';path.write_text(('#define BQT_HAS_RHI 0\n' if public else '#define BQT_HAS_RHI 1\n')+source)
            native_shards.write_changed(folder/'shared-input.h','#define INPUT_VALUE 47\n')
            payload,_,native=compile_backend(path,args.qt_root,folder,'clang++-19',['QtCore','QtWebSockets'])
            symbols=subprocess.check_output(['nm','--defined-only','--demangle',str(native_workspace.actual_work(folder)/'wrappers.o')],text=True)
            for name,(_,_,scope) in runtime_dispatch.HUBS.items():
                qualified='bendqt::'+(scope+'::' if scope else '')+name
                assert re.search(r'(?m)^[0-9a-fA-F]+ T '+re.escape(qualified)+r'\(',symbols),qualified+' is not a strong definition'
            shared=(native_workspace.actual_work(folder)/'shards/shared.hpp').read_text()
            assert 'case 128: return bqt_native_signal_argument_' not in shared
            assert 'case 0: return bqt_property_binding_factory_' not in shared
            code=consumer.replace('@PAYLOAD@',payload); consumer_path=folder/'consumer.c';consumer_path.write_text(code)
            subprocess.run(['clang',str(consumer_path),'-ldl','-pthread','-o',str(folder/'consumer')],check=True)
            tested=subprocess.run([str(folder/'consumer')],text=True,capture_output=True,env=dict(os.environ,LD_LIBRARY_PATH=str(args.qt_root/'lib')))
            (folder/'native.log').write_text(tested.stdout+tested.stderr)
            if tested.returncode:raise RuntimeError('Runtime dispatch consumer failed '+str(tested.returncode)+tested.stdout+tested.stderr)
            payloads['public' if public else 'full']=dict(passed=True,shards=native['shards'])
        negative=work/'negative';negative.mkdir(exist_ok=True)
        assert source.count(guarded_case)==1
        bare=guarded_case.removeprefix('#if BQT_HAS_RHI\n').removesuffix('\n#endif')
        path=negative/'wrappers.cpp';path.write_text('#define BQT_HAS_RHI 0\n'+source.replace(guarded_case,bare,1))
        native_shards.write_changed(negative/'shared-input.h','#define INPUT_VALUE 47\n')
        try: compile_backend(path,args.qt_root,negative,'clang++-19',['QtCore','QtWebSockets'])
        except RuntimeError as error:
            if 'bqt_property_binding_factory_1' not in str(error):raise
        else:raise RuntimeError('Missing public RHI dispatch guard linked successfully')
        receipt.update(passed=True,hubs=9,full_and_public=True,typed_adapters_preserved=True,
                       binding_and_native_name=True,argument_descriptors=True,public_rhi_guard_negative=True,
                       deduced_return_and_default_arguments_rejected=True,strong_hub_definitions=True,payloads=payloads,
                       source_sha256={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in
                           [ROOT/'generator/runtime_dispatch.py',ROOT/'generator/custom_signals.py',ROOT/'generator/qt_objects.py',
                            ROOT/'generator/templates/custom_signals.cpp',ROOT/'generator/templates/qt_objects.cpp',ROOT/'generator/templates/native_snapshots.cpp',
                            ROOT/'generator/templates/qml_list_properties.cpp']})
        receipt_path.write_text(json.dumps(receipt,indent=2)+'\n');print('QT612_RUNTIME_DISPATCH_SHARDS_OK')
    finally:
        for key,value in previous.items():
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value


if __name__=='__main__':main()
