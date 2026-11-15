#!/usr/bin/env python3
"""Check outlined virtual bodies, Qt worker delivery and cross-unit vtables."""
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

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'generator'))
import abi_cohorts
import callbacks
import native_shards
import native_workspace
from backend import compile_backend,compiler_flags


def fixture():
    spec=importlib.util.spec_from_file_location('virtual_shard_control',ROOT/'scripts/check-qt-native-shards.py')
    control=importlib.util.module_from_spec(spec);spec.loader.exec_module(control)
    transport=(ROOT/'generator/templates/callbacks.cpp').read_text()
    bridge=transport[transport.index('template<class Function> static bool callback_on_main('):transport.index('static void connection_terminal(')]
    rows=[('compute','int','int a0','','a0','return NativeBridge::compute(a0);','return a0 + 100;'),
          ('token','Result','int a0',' const noexcept','a0','return NativeBridge::token(a0);','return Result{a0 + 200};'),
          ('reference','const Result &','',' const noexcept','','return NativeBridge::reference();','return stored;'),
          ('mutable_ref','int &','',' noexcept','','return NativeBridge::mutable_ref();','return number;'),
          ('text','QString','const QString &a0',' const','a0','return NativeBridge::text(a0);','return a0 + QStringLiteral(":handled");'),
          ('compute','int','const QString &a0',' const','a0','return NativeBridge::compute(a0);','return int(a0.size()) + 300;'),
          ('touch','void','int a0','','a0','NativeBridge::touch(a0); return;','number += a0; return;')]
    while len(rows)<129:
        i=len(rows);rows.append(('extra'+str(i),'int','',' const','','return '+str(i)+';','return '+str(i)+';'))
    declarations=[];definitions=[]
    for identifier,(name,result,parameters,qualifier,values,fallback,answer) in enumerate(rows):
        body=['        if (!bqt_receiver) { '+fallback+' }']
        body+=callbacks.thread_branch(dict(function=dict(name=name)),result,values,fallback,fallback)
        body+=['        try {','            HandlerLease lease;','            if (QThread::currentThread() != main_thread) wrong_thread = true;']
        if name=='compute' and parameters=='int a0':body+=['            if (a0 < 0) throw std::runtime_error("handler failure");']
        body+=['            '+answer,'        } catch (...) { ++handler_errors; '+fallback+' }']
        declaration,definition=callbacks._virtual_body_parts('VirtualProxy',identifier,name,result,parameters,qualifier,body)
        assert '\n'.join(body) in definition
        declarations.append(declaration);definitions.append(definition)
    private_declaration,private_definition=callbacks._virtual_body_parts('GuardedProxy',129,'special','int','','',['        RhiOnlyMarker marker; return marker.value;'])
    generator=SimpleNamespace(abi_cohort=dict(names={'RhiOnlyMarker'},headers=[],pattern=re.compile(r'\bRhiOnlyMarker\b'),proxies=set(),operations=set(),exact_helpers={}))
    guarded=abi_cohorts.proxy(generator,'GuardedProxy',['class GuardedProxy : public GuardedBase { public:',private_declaration,'};',private_definition])
    assert 'GuardedProxy' in generator.abi_cohort['proxies']
    guarded=[callbacks._guard_proxy_definition(line) if line==private_definition else line for line in guarded]
    padding='\n'.join('    virtual int extra'+str(i)+'() const { return '+str(i)+'; }' for i in range(7,129))
    setup=r'''
static QThread *main_thread = QThread::currentThread();
static std::atomic<QObject *> main_context{nullptr};
static int handler_leases=0,handler_errors=0,destroyed_proxies=0;
static bool wrong_thread=false;
struct HandlerLease { HandlerLease(){++handler_leases;} ~HandlerLease(){--handler_leases;} };
class NativeBridge {
protected:
    struct Result { int value; };
    Result stored{7}; int number=11;
    virtual ~NativeBridge() { if(handler_leases) std::abort(); ++destroyed_proxies; }
public:
    virtual int compute(int value) { return value-10; }
    virtual Result token(int value) const noexcept { return Result{value}; }
    virtual const Result &reference() const noexcept { return stored; }
    virtual int &mutable_ref() noexcept { return number; }
    virtual QString text(const QString &value) const { return value; }
    virtual int compute(const QString &value) const { return int(value.size())-10; }
    virtual void touch(int value) { number+=value; }
    int *number_address(){return &number;}
@PADDING@
};
class GuardedBase { public: virtual ~GuardedBase()=default; virtual int special(){return 0;} };
#if BQT_HAS_RHI
struct RhiOnlyMarker { int value=71; };
#endif
'''.replace('@PADDING@',padding)
    shared=setup+bridge+'\nclass VirtualProxy final : public NativeBridge {\npublic:\n'
    shared+='    uint32_t bqt_receiver=1;\n    std::shared_ptr<std::atomic<bool>> bqt_alive=std::make_shared<std::atomic<bool>>(true);\n'
    shared+='    ~VirtualProxy() override { bqt_alive->store(false); }\n'+'\n'.join(declarations)+'\n};\n'
    shared+='\n'.join(guarded)+'\n'+''.join(definitions)+r'''
static VirtualProxy *virtual_proxy=nullptr;
static NativeBridge *virtual_base=nullptr;
static const std::type_info *virtual_rtti=nullptr;
static void *virtual_vtable=nullptr;
static std::unique_ptr<QCoreApplication> virtual_application;
static void *vtable_of(const void *object){void *result;std::memcpy(&result,object,sizeof(result));return result;}
'''
    create=r'''
    virtual_proxy=new VirtualProxy;virtual_base=virtual_proxy;
    virtual_rtti=&typeid(*virtual_base);virtual_vtable=vtable_of(virtual_base);
    r->value=r->value && virtual_base->compute(4)==104 && virtual_base->token(2).value==202
        && virtual_base->text(QStringLiteral("m"))==QStringLiteral("m:handled") && !handler_leases;
'''
    verify=r'''
    r->value=r->value && dynamic_cast<VirtualProxy *>(virtual_base)==virtual_proxy
        && virtual_rtti==&typeid(VirtualProxy) && virtual_vtable==vtable_of(virtual_proxy)
        && &virtual_base->mutable_ref()==virtual_base->number_address()
        && noexcept(virtual_base->token(1)) && noexcept(virtual_base->reference());
#if BQT_HAS_RHI
    GuardedProxy guarded;r->value=r->value && guarded.special()==71;
#else
    r->value=r->value && std::is_abstract_v<GuardedProxy>;
#endif
'''
    worker=r'''
    r->value=r->value && virtual_base->compute(5)==105 && virtual_base->token(3).value==203
        && virtual_base->reference().value==7 && &virtual_base->mutable_ref()==virtual_base->number_address()
        && virtual_base->text(QStringLiteral("w"))==QStringLiteral("w:handled")
        && virtual_base->compute(QStringLiteral("abc"))==303;
    virtual_base->touch(3);
    r->value=r->value && *virtual_base->number_address()==14 && virtual_base->compute(-1)==-11;
    virtual_proxy->bqt_alive->store(false);
    r->value=r->value && virtual_base->compute(5)==-5;
    virtual_proxy->bqt_alive->store(true);
    auto *context=main_context.exchange(nullptr);
    r->value=r->value && virtual_base->compute(6)==-4;
    main_context.store(context);
'''
    source=control.NATIVE.replace('static int initializations = 0;',shared+'\nstatic int initializations = 0;')
    source=source.replace('r->pointer = registry_pointer; r->value = 1; return true;',
        'r->pointer = registry_pointer; r->value = 1;\n'+create+'\nreturn true;')
    source=source.replace('catch (const Marker &value) { r->value = r->value && value.value == 77; }',
        'catch (const Marker &value) { r->value = r->value && value.value == 77; }\n'+verify)
    source=source.replace('task_context = 99; return true;','task_context = 99;\n'+worker+'\nreturn true;')
    source=source.replace('r->value = task_context == 7 && initializations == 1; return true;',
        'QCoreApplication::processEvents(); r->value = task_context == 7 && initializations == 1; return true;')
    finish=r'''
static bool __attribute__((noinline)) bqt_op_14(BqtRequest *r) {
    delete virtual_proxy;virtual_proxy=nullptr;virtual_base=nullptr;
    r->value=destroyed_proxies==1 && !handler_leases && handler_errors==1 && !wrong_thread;
    main_context.store(nullptr);virtual_application.reset();return true;
}
'''
    source=source.replace('static bool dispatch(BqtRequest *r) {',finish+'\nstatic bool dispatch(BqtRequest *r) {')
    source=source.replace('default:return false;','case 14:return bqt_op_14(r);\n    default:return false;')
    source=source.replace('    return nullptr;\n}',r'''
    static int argc=1;static char name[]="virtual-control";static char *argv[]={name,nullptr};
    bendqt::virtual_application=std::make_unique<QCoreApplication>(argc,argv);
    bendqt::main_context.store(bendqt::virtual_application.get());return nullptr;
}''',1)
    preamble='#include <QtCore/QtCore>\n#include <atomic>\n#include <memory>\n#include <optional>\n#include <stdexcept>\n#include <cstring>\n#ifndef BQT_HAS_RHI\n#define BQT_HAS_RHI 1\n#endif\n'
    consumer=control.CONSUMER.replace('#include <pthread.h>','#include <pthread.h>\n#include <stdatomic.h>')
    consumer=consumer.replace('static void *other_thread(void *unused) {','static _Atomic int worker_done=0;\nstatic void *other_thread(void *unused) {')
    consumer=consumer.replace('return (void *)(intptr_t)(r.value != 0);','atomic_store(&worker_done,1); return (void *)(intptr_t)(r.value != 0);')
    consumer=consumer.replace('if(pthread_create(&thread,NULL,other_thread,NULL)||pthread_join(thread,&result)||(intptr_t)result!=1)return 4;',r'''
    if(pthread_create(&thread,NULL,other_thread,NULL))return 4;
    while(!atomic_load(&worker_done)){BqtRequest tick={13,0,NULL};bqt_abi_call(&tick);usleep(100);}
    if(pthread_join(thread,&result)||(intptr_t)result!=1)return 4;
''')
    consumer=consumer.replace('    puts("QT612_NATIVE_SHARDS_OK', '    r.operation=14;r.value=0;bqt_abi_call(&r);if(!r.value)return 6;\n    puts("QT612_NATIVE_SHARDS_OK')
    return preamble+source,consumer,hashlib.sha256(bridge.encode()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,default=ROOT/'build/qt612/proxy-virtual-shards-check')
    parser.add_argument('--qt-root',type=Path,default=Path.home()/'.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    args=parser.parse_args();work=args.work.resolve();work.mkdir(parents=True,exist_ok=True)
    receipt=dict(passed=False);destination=work/'receipt.json';destination.write_text(json.dumps(receipt)+'\n')
    source,consumer,bridge_sha=fixture();previous={k:os.environ.get(k) for k in ('BQT_SHARD_OPERATIONS','BQT_AUXILIARY_FUNCTIONS','BQT_SHARD_JOBS')}
    os.environ.update(BQT_SHARD_OPERATIONS='1',BQT_AUXILIARY_FUNCTIONS='128',BQT_SHARD_JOBS='1')
    try:
        results={}
        for public in (False,True):
            folder=work/('public' if public else 'full');folder.mkdir(exist_ok=True)
            path=folder/'wrappers.cpp';path.write_text(('#define BQT_HAS_RHI 0\n' if public else '')+source)
            native_shards.write_changed(folder/'shared-input.h','#define INPUT_VALUE 47\n')
            payload,_,native=compile_backend(path,args.qt_root,folder,'clang++-19',['QtCore'])
            assert native['shards']['auxiliary_functions']==130 and native['shards']['auxiliary_shards']==2
            assert native['shards']['operation_shards']==5
            header=(native_workspace.actual_work(folder)/'shards/shared.hpp').read_text()
            assert 'HandlerLease lease;' not in header
            code=folder/'consumer.c';code.write_text(consumer.replace('@PAYLOAD@',payload))
            subprocess.run(['clang',str(code),'-ldl','-pthread','-o',str(folder/'consumer')],check=True)
            result=subprocess.run([str(folder/'consumer')],capture_output=True,text=True,timeout=30,
                env=dict(os.environ,LD_LIBRARY_PATH=str(args.qt_root/'lib')))
            (folder/'native.log').write_text(result.stdout+result.stderr)
            if result.returncode:raise RuntimeError('Outlined virtual consumer failed '+str(result.returncode)+result.stdout+result.stderr)
            results['public' if public else 'full']=dict(passed=True,shards=native['shards'])
        negative=work/'negative';negative.mkdir(exist_ok=True)
        start=source.index('// BQT_AUXILIARY_BEGIN proxy_virtuals 129\n');end=source.index('// BQT_AUXILIARY_END proxy_virtuals 129\n',start)
        broken=source[start:end].replace('#if BQT_HAS_RHI\n','',1).replace('#endif\n','',1)
        path=negative/'wrappers.cpp';path.write_text('#define BQT_HAS_RHI 0\n'+source[:start]+broken+source[end:])
        native_shards.write_changed(negative/'shared-input.h','#define INPUT_VALUE 47\n')
        try:native_shards.check_syntax(path,negative/'syntax',compiler_flags(args.qt_root,'clang++-19',['QtCore']),maximum_operations=1)
        except RuntimeError as error:
            if 'auxiliary-proxy_virtuals-' not in str(error):raise
        else:raise RuntimeError('Extracted virtual cohort guard regression passed')
        receipt.update(passed=True,virtuals=130,full_and_public=True,real_worker_bridge=True,
            protected_return_types=True,reference_and_value_returns=True,const_noexcept_and_overloads=True,
            rtti_key_function_vtable_identity=True,failure_and_destruction_cleanup=True,
            private_guard_negative=True,bridge_sha256=bridge_sha,payloads=results,
            callbacks_sha256=hashlib.sha256((ROOT/'generator/callbacks.py').read_bytes()).hexdigest(),
            boundary='Production body renderer and actual worker bridge with small handler/ownership shims; full Bend consumers remain integration gates')
        destination.write_text(json.dumps(receipt,indent=2)+'\n');print('QT612_PROXY_VIRTUAL_SHARDS_OK')
    finally:
        for k,v in previous.items():
            if v is None:os.environ.pop(k,None)
            else:os.environ[k]=v


if __name__=='__main__':main()
