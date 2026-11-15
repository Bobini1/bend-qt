#!/usr/bin/env python3
"""Check that native parent teardown keeps child dependencies alive."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
SOURCE=r'''
#include <QtCore/QtCore>
#include <QtQuick/QSGNode>
#include <QtWidgets/QApplication>
#include <QtWidgets/QMessageBox>
#include <array>
#include <atomic>
#include <memory>
#include <optional>
#include <vector>
#include <cassert>
struct BqtRequest { uint32_t self=0;int error=0; };
struct RuntimeObjectState;
struct CallbackHandlers;
struct NativeDestructionScope;
@ENTRY@
static constexpr uint32_t capacity=32;
static std::array<Entry,capacity> entries;
@RETENTION@
static std::array<Retention,capacity> retentions;
static constexpr uint32_t shared_holder_slot=0xfffffff0u;
struct Connection { bool active=false,terminal=false;uint32_t sender=0;uint16_t generation=1; };
static std::array<Connection,capacity> connections;
static unsigned terminal_calls=0;
static void connection_terminal(Connection&,uint32_t){++terminal_calls;}
static void close_connection(Connection&c){c.active=false;++c.generation;}
static uint32_t token(uint32_t i,uint16_t g){return i|(uint32_t(g)<<16);}
static Entry *entry(uint32_t id){auto &e=entries[id&65535];return id&&e.value&&e.generation==(id>>16)?&e:nullptr;}
static bool fail(BqtRequest*r,int code,const char*){r->error=code;return true;}
static QThread *main_thread;
static QObject *application;
static std::atomic<QObject*> main_context;
static std::array<bool,capacity> pointer_phase;
static std::vector<uint32_t> native_pointer_died(const void*value){
    std::vector<uint32_t> result;
    for(uint32_t i=1;i<capacity;++i)if(entries[i].value&&(entries[i].value==value||entries[i].object==value)){
        pointer_phase[i]=false;result.push_back(token(i,entries[i].generation));
    }
    return result;
}
static void native_pointer_destroying(const void*value){
    for(uint32_t i=1;i<capacity;++i)if(entries[i].value&&(entries[i].value==value||entries[i].object==value))pointer_phase[i]=true;
}
static bool native_pointer_destructing(uint32_t id){return entry(id)&&pointer_phase[id&65535];}
static void native_pointer_forget(uint32_t id){pointer_phase[id&65535]=false;}
static void take_row_native_deleted(uint32_t){}
static void invalidate(uint32_t);
static void collect();
static void schedule_collection(){collect();}
@FORGET_STUBS@
static void dynamic_properties_event(QObject*,QEvent*){}
@SCOPE@
@DELETION_OBSERVER@
static bool callback_pin(BqtRequest*,uint32_t){return true;}
static void callback_unpin(uint32_t){}
@CALL_SCOPE@
struct CallFrame {
    static inline CallFrame *current=nullptr;
    bool application_loop=false;QEventLoop *loop=nullptr;std::function<void()> stop;
};
@INVALIDATION@
@TRACKED@
static uint32_t add(void *p,uint32_t parent=0,QObject*object=nullptr){
    for(uint32_t i=1;i<capacity;++i)if(!entries[i].value){
        auto &e=entries[i];auto generation=e.generation;e={};e.generation=generation?generation:1;
        pointer_phase[i]=false;
        e.value=p;e.native_owner=parent;e.object=object;
        auto id=token(i,e.generation);
        if(object){
            auto alive=std::make_shared<std::atomic<bool>>(true);
            e.alive=new std::shared_ptr<std::atomic<bool>>(alive);
@QOBJECT_OBSERVATION@
        }
        return id;
    }
    std::abort();
}
static bool entry_inside(uint32_t id,uint32_t root){
    for(uint32_t n=0;id&&n<capacity;++n){if(id==root)return true;auto *e=entry(id);if(!e)return false;id=e->native_owner;}
    return false;
}
static bool retained(uint32_t id){
    for(auto &r:retentions)if(entry(r.owner)&&entry(r.target)&&entry_inside(r.target,id)&&!entry_inside(r.owner,id))return true;
    return false;
}
static void retain_dependency(uint32_t owner,uint32_t target){
    for(auto &edge:retentions)if(!edge.owner){edge={owner,1,0,target,nullptr};return;}
    std::abort();
}
static void collect(){
    for(uint32_t i=1;i<capacity;++i){auto &e=entries[i];auto id=token(i,e.generation);
        if(!e.value||!e.owned||!e.pending_release||e.destroying)continue;
        bool held=false;for(auto &r:retentions)if(entry(r.owner)&&r.target==id)held=true;
        if(!held){auto p=e.value;auto destroy=e.destroy;invalidate(id);destroy(p);}
    }
}
static bool rhi_cleanup_operation(BqtRequest*,uint32_t){return true;}
static bool graphics_context_ready(uint32_t){return true;}
static bool rhi_release_ready(uint32_t){return true;}
static bool active_in_subtree(uint32_t){return false;}
static bool cursor_guard_cleanup_ready(BqtRequest*,uint32_t){return true;}
static bool rhi_destroy_root(BqtRequest*){return false;}
static unsigned gui_render_depth=1;
@DESTROY@
static bool child_dependency_lived=false;
static bool terminal_synchronous=true;
static bool flush_callback_armed=false,flush_nested_clean=false;
static QObject *flush_survivor=nullptr;
static uint32_t flush_survivor_id=0;
static unsigned completed_cases=0;
static QPointer<QObject> last_dependency;
static uint32_t last_parent=0,last_middle=0;
struct CheckedChild:QSGNode {
    QPointer<QObject> dependency;
    explicit CheckedChild(QObject *value):dependency(value){}
    ~CheckedChild() override {
        QTimer::singleShot(0,[]{collect();});
        QCoreApplication::processEvents();
        child_dependency_lived=bool(dependency);
    }
};
struct CheckedQObjectChild:QObject {
    QPointer<QObject> dependency;
    uint32_t owner;
    CheckedQObjectChild(QObject *parent,QObject *value,uint32_t identity):QObject(parent),dependency(value),owner(identity){}
    ~CheckedQObjectChild() override {
        QTimer::singleShot(0,[id=owner]{invalidate(id);collect();});QCoreApplication::processEvents();
        child_dependency_lived=bool(dependency);
    }
};
struct FlushDependency:QObject {
    ~FlushDependency() override {
        if(!flush_callback_armed)return;
        assert(native_destruction_scope);
        flush_callback_armed=false;
        flush_survivor=new QObject;flush_survivor_id=add(flush_survivor,0,flush_survivor);
        uint32_t temporary_id=0;
        {
            NativeCallScope nested;
            auto *temporary=new QObject;temporary_id=add(temporary,0,temporary);delete temporary;
        }
        flush_nested_clean=!entry(temporary_id);
    }
};
static int flush_reentry(){
    {
        NativeCallScope effect;
        auto *parent=new QObject;auto parent_id=add(parent,0,parent);
        auto *dependency=new FlushDependency;auto dependency_id=add(dependency);
        entry(dependency_id)->owned=true;entry(dependency_id)->pending_release=true;
        entry(dependency_id)->destroy=[](void*p){delete static_cast<FlushDependency*>(p);};
        retain_dependency(parent_id,dependency_id);flush_callback_armed=true;delete parent;
    }
    const bool identity_survived=entry(flush_survivor_id)!=nullptr;
    delete flush_survivor;flush_survivor=nullptr;
    if(!identity_survived)return 48;
    if(!flush_nested_clean)return 49;
    return 0;
}
static uint32_t dependency_record(QPointer<QObject>&alive){
    auto *dependency=new QObject;alive=dependency;auto id=add(dependency);
    auto *record=entry(id);record->owned=true;record->pending_release=true;
    record->destroy=[](void*p){delete static_cast<QObject*>(p);};return id;
}
static bool native_parent(bool explicit_destroy){
    child_dependency_lived=false;
    auto *parent=new NativeTracked<QSGNode>;auto parent_id=add(static_cast<QSGNode*>(parent));
    entry(parent_id)->owned=true;entry(parent_id)->destroy=[](void*p){delete static_cast<QSGNode*>(p);};
    auto *middle=new QSGNode;auto middle_id=add(middle,parent_id);parent->appendChildNode(middle);
    QPointer<QObject> alive;auto dependency_id=dependency_record(alive);
    middle->appendChildNode(new CheckedChild(alive));retain_dependency(middle_id,dependency_id);
    if(explicit_destroy){BqtRequest r{parent_id};assert(destroy_object(&r)&&!r.error);}
    else delete static_cast<QSGNode*>(parent);
    collect();assert(!alive&&!entry(parent_id)&&!entry(middle_id));
    ++completed_cases;return child_dependency_lived;
}
static bool qobject_parent(int mode=0,bool verify_cleanup=true){
    child_dependency_lived=false;
    QObject *parent=mode==4?static_cast<QObject*>(new NativeTracked<QObject>):new QObject;
    auto parent_id=add(parent,0,parent);
    entry(parent_id)->owned=true;entry(parent_id)->destroy=[](void*p){delete static_cast<QObject*>(p);};
    auto *middle=new QObject(parent);auto middle_id=add(middle,parent_id,middle);
    QPointer<QObject> alive;auto dependency_id=dependency_record(alive);
    auto *child=new CheckedQObjectChild(middle,alive,parent_id);add(child,middle_id,child);
    retain_dependency(middle_id,dependency_id);
    auto terminal_before=terminal_calls;
    connections[0]={true,true,parent_id,connections[0].generation};
    if(mode==0){BqtRequest r{parent_id};assert(destroy_object(&r)&&!r.error);}
    else if(mode==1){QTimer::singleShot(0,[parent]{delete parent;});QCoreApplication::processEvents();}
    else if(mode==2){parent->deleteLater();QCoreApplication::sendPostedEvents(nullptr,QEvent::DeferredDelete);}
    else {NativeCallScope call_scope;delete parent;terminal_synchronous=terminal_synchronous&&terminal_calls==terminal_before+1;}
    collect();if(verify_cleanup)assert(!alive&&!entry(parent_id)&&!entry(middle_id));
    assert(terminal_calls==terminal_before+1);
    last_parent=parent_id;last_middle=middle_id;last_dependency=alive;
    ++completed_cases;return child_dependency_lived;
}
static bool static_modal_tail(){
    child_dependency_lived=false;
    uint32_t parent_id=0,middle_id=0;QPointer<QObject> alive;
    {
        NativeCallScope call_scope;
        @MODAL_BEFORE@
        QTimer::singleShot(0,[&]{
            auto *dialog=qobject_cast<QDialog*>(QApplication::activeModalWidget());assert(dialog);
            parent_id=add(dialog,0,dialog);
            auto *middle=new QObject(dialog);middle_id=add(middle,parent_id,middle);
            auto dependency_id=dependency_record(alive);
            auto *child=new CheckedQObjectChild(middle,alive,parent_id);add(child,middle_id,child);
            retain_dependency(middle_id,dependency_id);
            dialog->done(QMessageBox::Yes);
        });
        QMessageBox::question(nullptr,QStringLiteral("Teardown"),QStringLiteral("Native modal helper tail"),QMessageBox::Yes|QMessageBox::No);
    }
    collect();assert(parent_id&&middle_id&&!alive&&!entry(parent_id)&&!entry(middle_id));
    ++completed_cases;return child_dependency_lived;
}
int main(int argc,char **argv){
    BendApplication app(argc,argv);application=&app;main_thread=QThread::currentThread();
    if(!native_parent(false)||!native_parent(true)||!qobject_parent()){
        puts("NATIVE_PARENT_DEPENDENCY_RELEASED_BEFORE_CHILD_DESTRUCTION");return 42;
    }
    assert(completed_cases==3);
    if(!qobject_parent(1)||!qobject_parent(2)){
        puts("EXTERNAL_QOBJECT_CHILD_DEPENDENCY_RELEASED_DURING_NATIVE_EVENT");return 43;
    }
    if(!qobject_parent(3)){puts("DIRECT_NATIVE_CALL_RELEASED_CHILD_DEPENDENCY");return 44;}
    bool loop_released=false;
    {
        NativeCallScope call_scope;
        // Preparation before entering a blocking loop must release its own
        // completed deletions instead of carrying them through the loop.
        auto *prelude=new QObject;const auto prelude_id=add(prelude,0,prelude);delete prelude;
        @LOOP_BEFORE@
        QTimer::singleShot(0,[&]{
            assert(qobject_parent(1));
            QTimer::singleShot(0,[&]{
                loop_released=!entry(prelude_id)&&!last_dependency&&!entry(last_parent)&&!entry(last_middle);
                QCoreApplication::quit();
            });
        });
        QApplication::exec();
    }
    if(!loop_released){puts("EVENT_LOOP_RETAINED_DEAD_GRAPHS");return 45;}
    assert(completed_cases==7);
    if(!static_modal_tail()){puts("STATIC_MODAL_HELPER_RELEASED_CHILD_DEPENDENCY");return 46;}
    assert(completed_cases==8);
    {
        NativeDestructionScope outer_notification;
        assert(qobject_parent(3));
        assert(qobject_parent(4));
    }
    assert(completed_cases==10);
    if(!terminal_synchronous){puts("TERMINAL_CALLBACK_RETURNED_TOO_LATE");return 47;}
    const int reentry=flush_reentry();
    if(reentry==48){puts("REENTRANT_COLLECTION_REUSED_DEAD_TOKEN");return 48;}
    if(reentry==49){puts("NESTED_FLUSH_LEFT_COMPLETED_OBJECT");return 49;}
    puts("QT612_NATIVE_DESTRUCTION_OK native_parent=1 explicit_delete=1 qobject_children=1 native_event=1 deferred_delete=1 direct_call=1 loop_drain=1 modal_tail=1 nearest_scope=1 terminal_sync=1 tracked_qobject=1 reentrant_flush=1 generation_reuse=1 queued_gc=1 dependency_lifetime=1 cleanup=1");
}
'''


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work',type=Path,default=ROOT/'build/native-destruction')
    p.add_argument('--qt-root',type=Path,default=Path.home()/'.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    p.add_argument('--cxx',default='clang++-19')
    p.add_argument('--sanitize',action='store_true')
    p.add_argument('--external-qobject-delete',action='store_true',default=True,help='Audit native deletion during Qt event dispatch (enabled by default)')
    a=p.parse_args();a.work.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(ROOT/'generator'))
    import event_loops
    policy_bytes=(ROOT/'generator/event_loops.py').read_bytes()
    template=ROOT/'generator/templates/runtime.cpp';template_bytes=template.read_bytes()
    text=template_bytes.decode().replace('\r\n','\n')
    def between(start,end):
        begin=text.index(start);return text[begin:text.index(end,begin)]
    snippets=dict(ENTRY=between('struct Entry {','\nstruct Retention {'),
        RETENTION=between('struct Retention {','\nstatic uint32_t render_factory_retention_owner'),
        SCOPE=between('static thread_local unsigned native_destructor_depth','\nstatic std::atomic<QObject *> main_context'),
        DELETION_OBSERVER=between('class NativeDeletionObserver {','\nstatic void discard_value'),
        CALL_SCOPE='struct NativeCallScope;\nstatic NativeCallScope *native_call_scope;\n'+between('struct NativeCallScope {','\nstruct NativeDispatchIsolation'),
        INVALIDATION=between('static void dispatch_terminal_connections(uint32_t id)','\nstatic void invalidate_native_children'),
        TRACKED=between('static void native_deleted(void *value)','// @NATIVE_OBJECTS@'),
        DESTROY=between('static bool destroy_object(BqtRequest *r)','\nstatic bool release_object'),
        QOBJECT_OBSERVATION=between('auto *registry_thread = main_thread;','                if (auto *thread ='))
    fixture_generator=type('FixtureGenerator',(),{'classes':{}})()
    snippets['MODAL_BEFORE']='\n'.join(event_loops.before_call(fixture_generator,dict(
        function=dict(name='question',declaring_class='QMessageBox',static=True),**{'class':'QMessageBox'})))
    snippets['LOOP_BEFORE']='\n'.join(event_loops.before_call(fixture_generator,dict(
        function=dict(name='exec',declaring_class='QCoreApplication',static=True),**{'class':'QApplication'})))
    forgets=('static_native_view_forget','value_provenance_before_invalidate','aggregate_forget',
        'video_buffers_forget','lazy_value_forget','pointer_fields_forget','rhi_forget','dismiss_native_guards',
        'native_model_forget','value_guard_forget','model_index_forget','generic_argument_forget','boundary_finder_forget','dynamic_properties_forget')
    snippets['FORGET_STUBS']='\n'.join('static void '+name+'(uint32_t){}' for name in forgets)
    def render(parts):
        value=SOURCE
        for key,content in parts.items():value=value.replace('@'+key+'@',content)
        return value
    source=a.work/'main.cpp';source.write_text(render(snippets))
    qt=a.qt_root
    command=[a.cxx,'-std=c++17','-O1','-fPIC',str(source),'-I'+str(qt/'include'),'-I'+str(qt/'include/QtCore'),'-I'+str(qt/'include/QtGui'),'-I'+str(qt/'include/QtQuick'),'-I'+str(qt/'include/QtWidgets'),
        '-L'+str(qt/'lib'),'-Wl,-rpath,'+str(qt/'lib'),'-lQt6Widgets','-lQt6Quick','-lQt6Gui','-lQt6Core','-o',str(a.work/'control')]
    if a.sanitize:command+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    built=subprocess.run(command,capture_output=True,text=True);(a.work/'compile.log').write_text(built.stdout+built.stderr)
    if built.returncode:raise RuntimeError('Native destruction compile failed; see '+str(a.work/'compile.log'))
    env=dict(os.environ,LD_LIBRARY_PATH=str(qt/'lib'),QT_QPA_PLATFORM='offscreen')
    if a.sanitize:env['ASAN_OPTIONS']='detect_leaks=0'
    run=subprocess.run([str(a.work/'control')]+(['external'] if a.external_qobject_delete else []),capture_output=True,text=True,env=env)
    (a.work/'runtime.log').write_text(run.stdout+run.stderr)
    receipt=dict(passed=False,runtime_passed=run.returncode==0,sanitized=a.sanitize,external_qobject_delete=a.external_qobject_delete,exit_code=run.returncode,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        runtime_template_sha256=hashlib.sha256(template_bytes).hexdigest(),
        event_loop_policy_sha256=hashlib.sha256(policy_bytes).hexdigest(),output=run.stdout.strip(),
        exact_snippet_sha256={k:hashlib.sha256(v.encode()).hexdigest() for k,v in snippets.items() if k!='FORGET_STUBS'})
    (a.work/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(run.stdout,end='')
    if run.returncode:raise SystemExit(run.returncode)
    negatives={}
    lifetime_marker='NATIVE_PARENT_DEPENDENCY_RELEASED_BEFORE_CHILD_DESTRUCTION'
    retire_generation='if (++e->generation == 0)\n        e->retired = true;'
    local_flush='if (scope->flushing) return;\n    struct Guard { bool &value; ~Guard() { value = false; } } guard{scope->flushing};\n    scope->flushing = true;'
    global_flush='static bool flushing; if (flushing) return;\n    struct Guard { bool &value; ~Guard() { value = false; } } guard{flushing};\n    flushing = true;'
    mutations={
        'early_native_parent_invalidation':('TRACKED','~NativeTracked() override { NativeDeletionObserver::begin(); }',
            '~NativeTracked() override { native_deleted(static_cast<T *>(this)); }',42,lifetime_marker),
        'missing_explicit_destruction_scope':('DESTROY','NativeDestructionScope destruction;','/* negative control: no native destruction scope */',42,lifetime_marker),
        'missing_notify_scope':('SCOPE','NativeDestructionScope notification;','/* negative control: no notification scope */',43,'EXTERNAL_QOBJECT_CHILD_DEPENDENCY_RELEASED_DURING_NATIVE_EVENT'),
        'missing_direct_call_scope':('CALL_SCOPE','std::optional<NativeDestructionScope> destruction{std::in_place};','std::optional<NativeDestructionScope> destruction;',44,'DIRECT_NATIVE_CALL_RELEASED_CHILD_DEPENDENCY'),
        'event_loop_keeps_call_scope':('CALL_SCOPE','void allow_event_loop() { destruction.reset(); }','void allow_event_loop() {}',45,'EVENT_LOOP_RETAINED_DEAD_GRAPHS'),
        'modal_helper_drops_call_scope':('MODAL_BEFORE','if (CallFrame::current)','call_scope.allow_event_loop(); if (CallFrame::current)',46,'STATIC_MODAL_HELPER_RELEASED_CHILD_DEPENDENCY'),
        'nested_flush_takes_outer_records':('INVALIDATION','entries[i].deferred_scope == scope','true',42,lifetime_marker),
        'repeated_invalidation_changes_owner':('INVALIDATION','if (!e->deferred_invalidation || !e->deferred_scope) e->deferred_scope = native_destruction_scope;','e->deferred_scope = native_destruction_scope;',42,lifetime_marker),
        'terminal_callback_waits_for_flush':('INVALIDATION','if (!native_pointer_destructing(id)) dispatch_terminal_connections(id);','/* negative control: postpone terminal delivery */',47,'TERMINAL_CALLBACK_RETURNED_TOO_LATE'),
        'late_generation_retirement':('INVALIDATION',retire_generation,'/* negative control: generation retired after collection */',48,'REENTRANT_COLLECTION_REUSED_DEAD_TOKEN'),
        'global_flushing_guard':('INVALIDATION',local_flush,global_flush,49,'NESTED_FLUSH_LEFT_COMPLETED_OBJECT')}
    for name,(key,before,after,expected_code,expected_marker) in mutations.items():
        changed=dict(snippets);assert changed[key].count(before)==1;changed[key]=changed[key].replace(before,after)
        if name=='late_generation_retirement':
            assert changed[key].count('schedule_collection();')==1
            changed[key]=changed[key].replace('schedule_collection();','schedule_collection();\n    '+retire_generation)
        negative=a.work/(name+'.cpp');negative.write_text(render(changed));target=a.work/name
        argv=[str(negative) if item==str(source) else str(target) if item==str(a.work/'control') else item for item in command]
        built=subprocess.run(argv,capture_output=True,text=True);(a.work/(name+'-compile.log')).write_text(built.stdout+built.stderr)
        if built.returncode:raise RuntimeError('A negative control did not compile: '+name)
        rejected=subprocess.run([str(target)],capture_output=True,text=True,env=env)
        (a.work/(name+'-runtime.log')).write_text(rejected.stdout+rejected.stderr)
        ok=rejected.returncode==expected_code and rejected.stdout.strip()==expected_marker
        negatives[name]=dict(passed=ok,exit_code=rejected.returncode)
        if not ok:raise RuntimeError('A destruction negative control failed to detect the lifetime regression: '+name)
    receipt['negative_controls']=negatives
    receipt['passed']=True
    (a.work/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')


if __name__=='__main__':main()
