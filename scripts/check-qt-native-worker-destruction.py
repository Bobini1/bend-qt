#!/usr/bin/env python3
"""Check exact native observer/index code across worker QObject teardown."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = r'''
#include <QtCore/QtCore>
#include <QtGui/QTextObjectInterface>
#include <QtWidgets/QApplication>
#include <algorithm>
#include <array>
#include <atomic>
#include <map>
#include <memory>
#include <optional>
#include <system_error>
#include <vector>
#include <cstdio>
#include <cstddef>
struct BqtRequest { uint32_t self=0; int error=0; };
struct RuntimeObjectState; struct CallbackHandlers; struct NativeDestructionScope;
@ENTRY@
static constexpr uint32_t capacity=32;
template<class T> using SlotTable=std::array<T,capacity>;
static SlotTable<Entry> entries;
@RETENTION@
static SlotTable<Retention> retentions;
static constexpr uint32_t shared_holder_slot=0xfffffff0u;
struct Connection { bool active=false,terminal=false; uint32_t sender=0; uint16_t generation=1; };
static SlotTable<Connection> connections;
static void connection_terminal(Connection&,uint32_t) {}
static void close_connection(Connection&c) { c.active=false; ++c.generation; }
static uint32_t token(uint32_t i,uint16_t g) { return i|(uint32_t(g)<<16); }
static Entry *entry(uint32_t id) { auto&e=entries[id&65535]; return id&&e.value&&e.generation==(id>>16)?&e:nullptr; }
static bool fail(BqtRequest*r,int code,const char*) {r->error=code;return true;}
static QThread *main_thread;
static QApplication *application;
static std::atomic<QObject*> main_context;
static std::vector<uint32_t> native_pointer_died(const void*);
static void native_pointer_destroying(const void*);
static bool native_pointer_destructing(uint32_t);
static void take_row_native_deleted(uint32_t) {}
static void invalidate(uint32_t);
static void collect();
static void schedule_collection() {collect();}
static void dynamic_properties_event(QObject*,QEvent*) {}
@FORGETS@
@SCOPE@
@OBSERVER@
static bool callback_pin(BqtRequest*,uint32_t id) {if(auto*e=entry(id))++e->active_calls;return true;}
static void callback_unpin(uint32_t id) {if(auto*e=entry(id))if(e->active_calls)--e->active_calls;}
@CALL_SCOPE@
static bool rhi_validate_dependencies(BqtRequest*,uint32_t) {return true;}
static bool value_provenance_validate(BqtRequest*,uint32_t) {return true;}
static bool aggregate_validate(BqtRequest*,uint32_t) {return true;}
static void native_metadata_forget(uint32_t) {}
@INDEX@
static std::vector<std::pair<const void*,uint16_t>> native_pointer_aliases(const Entry&e) {
    return e.type==2?std::vector<std::pair<const void*,uint16_t>>{{e.value,2}}:std::vector<std::pair<const void*,uint16_t>>{};
}
@INVALIDATION@
@TRACKED@
static bool can_transfer_handle(BqtRequest*,uint32_t) {return true;}
static bool attach_graphics_context(BqtRequest*,uint32_t) {return true;}
static bool attach_rhi_identity(BqtRequest*,uint32_t) {return true;}
static bool render_type(uint16_t) {return false;}
static uint32_t gui_render_window=0;
static uint32_t scope_track(BqtRequest*,uint32_t,unsigned) {return 1;}
static bool grow_registry() {return false;}
@INSERT@
static bool rhi_cleanup_operation(BqtRequest*,uint32_t) {return true;}
static bool cursor_guard_defer_release(BqtRequest*,uint32_t) {return false;}
static void release_static_native_view(void*) {}
static bool retained(uint32_t) {return false;}
static bool active_in_subtree(uint32_t) {return false;}
static bool graphics_context_ready(uint32_t) {return true;}
static bool rhi_release_ready(uint32_t) {return true;}
static void schedule_render_collection(uint32_t) {}
static unsigned gui_render_depth=0;
static constexpr int lifetime_scoped[4]={0,0,0,0};
static bool destroy_object(BqtRequest*) {return false;}
@RELEASE@
static uint32_t add(void*value,QObject*object,uint16_t type=1) {
    for(uint32_t i=1;i<capacity;++i)if(!entries[i].value) {
        auto&e=entries[i];auto generation=e.generation;e={};e.generation=generation?generation:1;
        e.value=value;e.object=object;e.type=type;
        const auto id=token(i,e.generation);
        if(object) {
            auto alive=std::make_shared<std::atomic<bool>>(true);
            e.alive=new std::shared_ptr<std::atomic<bool>>(alive);
@QOBJECT_OBSERVATION@
        }
        native_pointer_publish(id);return id;
    }
    std::abort();
}
static void collect() {
    static bool collecting=false;if(collecting)return;collecting=true;
    for(uint32_t i=1;i<capacity;++i) {
        auto&e=entries[i];if(!e.value||!e.owned||!e.pending_release||e.destroying)continue;
        const auto id=token(i,e.generation);bool held=false;
        for(const auto&edge:retentions)if(entry(edge.owner)&&edge.target==id)held=true;
        if(!held) {auto*value=static_cast<QObject*>(e.value);e.destroying=true;delete value;invalidate(id);}
    }
    collecting=false;
}
struct InterfaceObject : QObject, QTextObjectInterface {
    QSizeF intrinsicSize(QTextDocument*,int,const QTextFormat&) override {return {};}
    void drawObject(QPainter*,const QRectF&,QTextDocument*,int,const QTextFormat&) override {}
};
struct PausedChild final : QObject {
    QSemaphore &started,&resume; QPointer<QObject> dependency; bool &survived;
    PausedChild(QObject*parent,QSemaphore&a,QSemaphore&b,QObject*d,bool&ok)
        :QObject(parent),started(a),resume(b),dependency(d),survived(ok) {}
    ~PausedChild() override {started.release();resume.acquire();survived=bool(dependency);}
};
static void drain() {QCoreApplication::sendPostedEvents();QCoreApplication::processEvents();}
static bool moved(bool adjusted) {
    QThread worker; QObject*object=nullptr;void*pointer=nullptr;
    if(adjusted) {
        auto*value=new NativeTracked<InterfaceObject>;object=value;
        pointer=static_cast<QTextObjectInterface*>(value);
        if(pointer==static_cast<void*>(object))return false;
    } else {object=new NativeTracked<QObject>;pointer=object;}
    const auto id=add(pointer,object,adjusted?2:1);
    const auto duplicate=adjusted?add(object,object):0;
    object->moveToThread(&worker);worker.start();
    QMetaObject::invokeMethod(object,[object,&worker]{delete object;worker.quit();},Qt::QueuedConnection);
    if(!worker.wait(5000))return false;drain();
    return !entry(id)&&(!duplicate||!entry(duplicate));
}
static bool paused() {
    QThread worker;QSemaphore started,resume;bool survived=false;
    auto*dependency=new QObject;QPointer<QObject> alive=dependency;
    const auto dependency_id=add(dependency,dependency);entry(dependency_id)->owned=true;entry(dependency_id)->pending_release=true;
    auto*object=new NativeTracked<QObject>;const auto id=add(object,object);
    new PausedChild(object,started,resume,dependency,survived);
    retentions[0].owner=id;retentions[0].target=dependency_id;
    object->moveToThread(&worker);worker.start();
    QMetaObject::invokeMethod(object,[object,&worker]{delete object;worker.quit();},Qt::QueuedConnection);
    if(!started.tryAcquire(1,5000))return false;
    const bool phase=native_pointer_destructing(id);
    BqtRequest cleanup_request;cleanup_request.self=id;
    {NativeCallScope cleanup;release_object(&cleanup_request);collect();}
    // The just-ended main scope must not leave a dangling scope pointer or
    // release a graph whose native child destructor is still on the worker.
    const bool held=entry(id)&&entry(id)->deferred_invalidation&&!entry(id)->deferred_scope&&alive;
    {NativeCallScope other;collect();}
    resume.release();const bool finished=worker.wait(5000);drain();
    return phase&&cleanup_request.error==ESTALE&&held&&finished&&survived&&!entry(id)&&!entry(dependency_id)&&!alive;
}
alignas(64) static std::array<std::byte,4096> reuse_storage;
static bool reuse_occupied=false;
struct ReusedQObject : QObject {
    static void *operator new(std::size_t size) {
        if(reuse_occupied||size>reuse_storage.size())std::abort();reuse_occupied=true;return reuse_storage.data();
    }
    static void operator delete(void*) noexcept {reuse_occupied=false;}
};
static bool reused() {
    QThread worker;BqtRequest request;
    auto*old=new NativeTracked<ReusedQObject>;uint32_t old_id;
    {NativeCallScope creation;old_id=insert(&request,old,old,1,[](void*p){delete static_cast<NativeTracked<ReusedQObject>*>(p);},true);}
    old->moveToThread(&worker);worker.start();
    QMetaObject::invokeMethod(old,[old,&worker]{delete old;worker.quit();},Qt::QueuedConnection);
    if(!worker.wait(5000))return false;
    // Do not process the queued completion before allocating at exactly the
    // freed address: insert must distinguish the replacement's live identity.
    auto*replacement=new NativeTracked<ReusedQObject>;replacement->setObjectName("replacement");uint32_t id;
    {NativeCallScope creation;id=insert(&request,replacement,replacement,1,[](void*p){delete static_cast<NativeTracked<ReusedQObject>*>(p);},true);}
    bool good=static_cast<void*>(replacement)==static_cast<void*>(old)&&id!=old_id&&entry(id)&&entry(id)->alive&&(*entry(id)->alive)->load();
    drain();good=good&&entry(id)&&(*entry(id)->alive)->load()&&replacement->objectName()=="replacement";
    delete replacement;drain();return good&&!entry(id)&&!reuse_occupied;
}
struct DuringDestruction final : QObject {
    std::function<void()> check;
    DuringDestruction(QObject*parent,std::function<void()> value):QObject(parent),check(std::move(value)) {}
    ~DuringDestruction() override {check();}
};
static bool dying_borrow() {
    BqtRequest request;auto*object=new NativeTracked<QObject>;uint32_t id;
    {NativeCallScope creation;id=insert(&request,object,object,1,[](void*p){delete static_cast<NativeTracked<QObject>*>(p);},true);}
    bool blocked=false;
    new DuringDestruction(object,[&]{BqtRequest borrowed;const auto result=insert(&borrowed,object,object,1,nullptr,false);blocked=!result&&borrowed.error==ESTALE;});
    delete object;return blocked&&!entry(id);
}
int main(int argc,char**argv) {
    BendApplication app(argc,argv);application=&app;main_thread=QThread::currentThread();main_context.store(&app);
    const QByteArray mode=argc>1?argv[1]:"all";
    if((mode=="all"||mode=="plain")&&!moved(false)){std::puts("WORKER_QOBJECT_FINALIZATION_MISSING");return 70;}
    if((mode=="all"||mode=="interface")&&!moved(true)){std::puts("WORKER_INTERFACE_FINALIZATION_MISSING");return 71;}
    if((mode=="all"||mode=="paused")&&!paused()){std::puts("WORKER_DESTRUCTOR_GRAPH_RELEASED_EARLY");return 72;}
    if((mode=="all"||mode=="reuse")&&!reused()){std::puts("WORKER_REPLACEMENT_REUSED_DEAD_IDENTITY");return 73;}
    if((mode=="all"||mode=="dying")&&!dying_borrow()){std::puts("NATIVE_DESTRUCTOR_REBORROWED_DYING_IDENTITY");return 74;}
    std::printf("QT_NATIVE_WORKER_DESTRUCTION Qt=%s mode=%s passed=1\n",qVersion(),mode.constData());
}
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qt-root',type=Path,default=Path.home()/'.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    parser.add_argument('--work',type=Path,default=ROOT/'build/native-worker-destruction')
    parser.add_argument('--cxx',default='clang++-19')
    parser.add_argument('--sanitize',action='store_true')
    args=parser.parse_args();args.work.mkdir(parents=True,exist_ok=True)
    runtime=(ROOT/'generator/templates/runtime.cpp').read_text()
    def between(start,end):return runtime.split(start,1)[1].split(end,1)[0]
    def whole(start,end):return start+between(start,end)
    snippets=dict(ENTRY=whole('struct Entry {','\nstruct Retention {'),
        RETENTION=whole('struct Retention {','\nstatic uint32_t render_factory_retention_owner'),
        SCOPE=whole('static thread_local unsigned native_destructor_depth','\nstatic std::atomic<QObject *> main_context'),
        OBSERVER=whole('class NativeDeletionObserver {','\nstatic void discard_value'),
        CALL_SCOPE=whole('struct NativeCallScope;','\nstruct NativeDispatchIsolation'),
        INVALIDATION=whole('static void dispatch_terminal_connections','\nstatic void invalidate_native_children'),
        TRACKED=whole('static void native_deleted(void *value)','// @NATIVE_OBJECTS@'),
        INSERT=whole('static uint32_t __attribute__((noinline)) insert(','\ntemplate<class T> struct NativeTraits'),
        RELEASE=whole('static bool release_object(BqtRequest *r)','\nstatic void collect_pending'),
        QOBJECT_OBSERVATION=whole('auto *registry_thread = main_thread;','                if (auto *thread ='),
        INDEX=(ROOT/'generator/templates/pointer_observations.cpp').read_text())
    forgets=('static_native_view_forget','value_provenance_before_invalidate','aggregate_forget','video_buffers_forget',
        'lazy_value_forget','pointer_fields_forget','rhi_forget','dismiss_native_guards','native_model_forget','value_guard_forget',
        'model_index_forget','generic_argument_forget','boundary_finder_forget','dynamic_properties_forget')
    snippets['FORGETS']='\n'.join('static void '+name+'(uint32_t) {}'for name in forgets)
    def render(parts):
        source=SOURCE
        for key,value in parts.items():source=source.replace('@'+key+'@',value)
        return source
    flags=[args.cxx,'-std=c++17','-O1','-fPIC',*['-I'+str(args.qt_root/'include'/module)for module in ('','QtCore','QtGui','QtWidgets')],
        '-L'+str(args.qt_root/'lib'),'-Wl,-rpath,'+str(args.qt_root/'lib'),'-lQt6Widgets','-lQt6Gui','-lQt6Core']
    if args.sanitize:flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    env=dict(os.environ,LD_LIBRARY_PATH=str(args.qt_root/'lib'),QT_QPA_PLATFORM='offscreen',ASAN_OPTIONS='detect_leaks=0')
    receipts={}
    controls=[('normal',snippets,'all',0,'QT_NATIVE_WORKER_DESTRUCTION')]
    for name,before,after,mode,code,marker in [
        ('missing_qobject_index','if (aliases.empty() && !value->object) return;','if (aliases.empty()) return;','plain',70,'WORKER_QOBJECT_FINALIZATION_MISSING'),
        ('missing_qobject_original','static_cast<void *>(value->object)','value->value','interface',71,'WORKER_INTERFACE_FINALIZATION_MISSING'),
        ('missing_worker_phase','owner->in_destructor.load(std::memory_order_acquire)','false','paused',72,'WORKER_DESTRUCTOR_GRAPH_RELEASED_EARLY')]:
        changed=dict(snippets);assert changed['INDEX'].count(before)==1;changed['INDEX']=changed['INDEX'].replace(before,after)
        controls.append((name,changed,mode,code,marker))
    changed=dict(snippets)
    old_condition='if (entries[i].destroying || (entries[i].alive && !(*entries[i].alive)->load(std::memory_order_acquire)))'
    assert changed['INSERT'].count(old_condition)==1
    changed['INSERT']=changed['INSERT'].replace(old_condition,'if (false)')
    controls.append(('reuse_dead_identity',changed,'reuse',73,'WORKER_REPLACEMENT_REUSED_DEAD_IDENTITY'))
    changed=dict(snippets)
    assert changed['INSERT'].count('if (native_pointer_destructing(previous_id))')==1
    changed['INSERT']=changed['INSERT'].replace('if (native_pointer_destructing(previous_id))','if (false)')
    controls.append(('reborrow_dying_identity',changed,'dying',74,'NATIVE_DESTRUCTOR_REBORROWED_DYING_IDENTITY'))
    for name,parts,mode,code,marker in controls:
        source=args.work/(name+'.cpp');source.write_text(render(parts));target=args.work/name
        built=subprocess.run([*flags,str(source),'-o',str(target)],capture_output=True,text=True)
        (args.work/(name+'-compile.log')).write_text(built.stdout+built.stderr)
        if built.returncode:raise RuntimeError('Worker destruction control did not compile: '+str(args.work/(name+'-compile.log')))
        run=subprocess.run([str(target),mode],env=env,capture_output=True,text=True,timeout=30)
        (args.work/(name+'-runtime.log')).write_text(run.stdout+run.stderr)
        passed=run.returncode==code and marker in run.stdout
        receipts[name]=dict(passed=passed,exit_code=run.returncode,output=run.stdout.strip(),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
        if not passed:raise RuntimeError('Worker destruction control failed: '+name+' '+run.stdout+run.stderr)
    receipt=dict(passed=True,sanitized=args.sanitize,controls=receipts,
        exact_snippet_sha256={key:hashlib.sha256(value.encode()).hexdigest()for key,value in snippets.items()},
        source_identity='Production Entry, scope, observer, index, invalidation, NativeCallScope and tracked wrappers; registry collection/retention host is a test fixture')
    (args.work/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print('QT_NATIVE_WORKER_DESTRUCTION_CONTROLS_OK normal=1 negatives=5 sanitized='+str(int(args.sanitize)))


if __name__=='__main__':main()
