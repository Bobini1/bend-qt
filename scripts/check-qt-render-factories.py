#!/usr/bin/env python3
"""Exercise the production factory domain against real Qt node allocations.

The small registry supplies the runtime primitives; the ownership-domain and
retention-batch implementations are the exact generator templates. The normal
Bend consumer gate separately checks the complete effect transport.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]

REGISTRY = r'''
#include <QtQuick/QtQuick>
#include <QtCore/QtCore>
#include <array>
#include <map>
#include <set>
#include <memory>
#include <vector>
#include <functional>
#include <cerrno>
#include <cassert>
struct BqtRequest { uint32_t self=0; int error=0; const char *message=nullptr; };
static bool fail(BqtRequest *r,int code,const char *text) { r->error=code;r->message=text;return true; }
template<class T> using SlotTable = std::array<T,1024>;
struct Entry {
    void *value=nullptr; QObject *object=nullptr; uint16_t type=0,generation=1;
    void(*destroy)(void*)=nullptr; bool owned=false,native_observed=false,pending=false;
    uint32_t native_owner=0,render_window=0;
    void *(*cast)(void*,uint16_t)=nullptr;
    bool(*validate)(BqtRequest*,uint32_t)=nullptr;
};
static constexpr uint32_t capacity=1024;
static SlotTable<Entry> entries;
static uint32_t token(uint32_t i,uint16_t g) { return i | uint32_t(g)<<16; }
static Entry *entry(uint32_t id) {
    auto &e=entries[id&65535u];return id && e.value && e.generation==(id>>16) ? &e:nullptr;
}
struct Retention {
    uint32_t owner=0,slot=0,key=0,target=0;
    QObject *(*current)(QObject*,uint32_t)=nullptr;
    uint32_t (*native_current)(uint32_t,uint32_t)=nullptr;
};
static SlotTable<Retention> retentions;
static SlotTable<bool> retention_reserved;
static bool fail_reservation=false,in_gc=false;
static uint32_t render_factory_retention_owner(uint32_t);
static void schedule_collection();
static void invalidate(uint32_t id) {
    auto *e=entry(id);if(!e)return;
    e->value=nullptr;e->owned=false;++e->generation;
    for(uint32_t i=1;i<capacity;++i)if(entries[i].value&&entries[i].native_owner==id)invalidate(token(i,entries[i].generation));
    for(auto &edge:retentions) { if(edge.owner==id)edge={};else if(edge.target==id)edge.target=0; }
}
static bool entry_inside(uint32_t id,uint32_t owner) {
    for(uint32_t n=0;id&&n<capacity;++n) { if(id==owner)return true;auto *e=entry(id);if(!e)return false;id=e->native_owner; }
    return false;
}
static bool reaches_token(uint32_t from,uint32_t to) { return entry_inside(to,from); }
static bool retained(uint32_t id) { for(auto &edge:retentions)if(edge.owner&&edge.target==id)return true;return false; }
static void schedule_collection() {
    if(in_gc)return;in_gc=true;
    for(uint32_t i=1;i<capacity;++i) {
        auto &e=entries[i];auto id=token(i,e.generation);
        if(e.value&&e.owned&&e.pending&&!retained(id)) { auto *p=e.value;auto destroy=e.destroy;invalidate(id);if(destroy)destroy(p); }
    }
    in_gc=false;
}
static void set_owned(uint32_t id,bool value) { if(auto *e=entry(id))e->owned=value; }
static bool set_native_owner(BqtRequest *r,uint32_t id,uint32_t owner) {
    auto *e=entry(id);if(!e||(owner&&!entry(owner))){fail(r,ESTALE,"owner");return false;}
    e->native_owner=owner;e->owned=!owner&&e->destroy;return true;
}
static uint32_t insert(BqtRequest*,void *value,QObject *object,uint16_t type,void(*destroy)(void*),bool owned,void*(*cast)(void*,uint16_t)=nullptr) {
    for(uint32_t i=1;i<capacity;++i)if(!entries[i].value) {
        auto g=entries[i].generation;entries[i]={};auto &e=entries[i];e.generation=g;
        e.value=value;e.object=object;e.type=type;e.destroy=destroy;e.owned=owned;e.cast=cast;
        auto id=token(i,g);if(object)QObject::connect(object,&QObject::destroyed,[id]{invalidate(id);});return id;
    }
    std::abort();
}
static uint32_t borrow(BqtRequest *r,QQuickWindow *window,uint16_t type) {
    for(uint32_t i=1;i<capacity;++i)if(entries[i].object==window)return token(i,entries[i].generation);
    return insert(r,window,window,type,nullptr,false);
}
static int prepare_retention(BqtRequest *r,uint32_t slot,uint32_t key,uint32_t target) {
    if(fail_reservation){fail_reservation=false;fail(r,ENOSPC,"negative reservation");return -1;}
    auto owner=render_factory_retention_owner(r->self);
    if(!entry(owner)||(target&&!entry(target))){fail(r,ESTALE,"retention");return -1;}
    for(uint32_t i=0;i<capacity;++i)
        if(!retention_reserved[i]&&((retentions[i].owner==owner&&retentions[i].slot==slot&&retentions[i].key==key)||!retentions[i].owner))return int(i);
    fail(r,ENOSPC,"retention full");return -1;
}
static void reserve_retention(int i,uint32_t,uint32_t,uint32_t) { if(i>=0)retention_reserved[i]=true; }
static void unreserve_retention(int i) { if(i>=0)retention_reserved[i]=false; }
static void commit_retention(int i,uint32_t owner,uint32_t slot,uint32_t key,uint32_t target,QObject*(*current)(QObject*,uint32_t)) {
    if(i>=0)retentions[i]=target?Retention{render_factory_retention_owner(owner),slot,key,target,current}:Retention{};
}
static QThread *main_thread;
struct TestRenderScope { uint64_t identity;uint32_t window; };
static TestRenderScope *active_gui_render_scope;
@RETENTION_BATCH@
@DOMAINS@
static void *node_cast(void *p,uint16_t type) { return type==1?p:nullptr; }
static void *rectangle_cast(void *p,uint16_t type) {
    auto *v=static_cast<QSGRectangleNode*>(p);return type==4?v:type==1?static_cast<QSGNode*>(v):nullptr;
}
static uint32_t add_node(BqtRequest *r,QSGNode *node,uint16_t type=1) {
    if(type==4)return insert(r,static_cast<QSGRectangleNode*>(node),nullptr,4,[](void*p){delete static_cast<QSGRectangleNode*>(p);},true,rectangle_cast);
    return insert(r,node,nullptr,1,[](void*p){delete static_cast<QSGNode*>(p);},true,node_cast);
}
struct ObservedNode final:QSGNode {
    uint32_t id=0;QPointer<QObject> dependency;
    ~ObservedNode() override { schedule_collection();assert(dependency);invalidate(id); }
};
int main(int argc,char **argv) {
    qputenv("QSG_RENDER_LOOP","basic");qputenv("QT_QUICK_BACKEND","software");
    QGuiApplication app(argc,argv);main_thread=QThread::currentThread();
    QQuickWindow window;window.resize(32,32);window.show();QCoreApplication::processEvents();window.grabWindow();
    assert(window.isSceneGraphInitialized());
    BqtRequest r;auto window_id=borrow(&r,&window,2);
    QQuickItem item(window.contentItem());item.setFlag(QQuickItem::ItemHasContents);
    auto item_id=insert(&r,&item,&item,5,nullptr,false);
    TestRenderScope scope{1,window_id};active_gui_render_scope=&scope;
    auto *root=window.createRectangleNode();assert(root);
    auto root_id=add_node(&r,root,4);entry(root_id)->render_window=window_id;render_factory_mark(root_id);
    auto *nested=new QSGNode;auto nested_id=add_node(&r,nested);root->appendChildNode(nested);entry(nested_id)->native_owner=root_id;entry(nested_id)->owned=false;
    auto *dependency=new QObject;QPointer<QObject> alive(dependency);
    auto dependency_id=insert(&r,dependency,dependency,6,[](void*p){delete static_cast<QObject*>(p);},true);
    auto *observed=new ObservedNode;observed->dependency=dependency;observed->id=add_node(&r,observed);
    entry(observed->id)->native_observed=true;entry(observed->id)->owned=false;entry(observed->id)->native_owner=nested_id;nested->appendChildNode(observed);
    auto observed_id=observed->id;
    retentions[0]={nested_id,0x123,0,dependency_id,nullptr};entry(dependency_id)->pending=true;
    fail_reservation=true;
    assert(!render_factory_handoff(&r,root_id,item_id,true)&&r.error==ENOSPC);
    assert(entry(root_id)&&entry(root_id)->owned&&entry(observed_id)->native_owner==nested_id&&retained(dependency_id));
    r.error=0;assert(render_factory_handoff(&r,root_id,item_id,true));
    assert(!entry(root_id)&&!entry(nested_id)&&entry(observed_id)&&alive);
    auto root_view=render_factory_restore(&r,static_cast<QSGNode*>(root),1,item_id);
    auto child_view=render_factory_restore(&r,nested,1,item_id);assert(root_view&&child_view);
    auto root_anchor=render_factory_retention_owner(root_view),child_anchor=render_factory_retention_owner(child_view);
    assert(root_anchor!=child_anchor&&entry(child_anchor)->native_owner==root_anchor);
    assert(entry(observed_id)->native_owner==child_anchor);
    assert(entry(root_view)->cast(entry(root_view)->value,4)==root);
    bool exact_slot=false;for(const auto &edge:retentions)if(edge.owner==child_anchor&&edge.slot==0x123&&edge.target==dependency_id)exact_slot=true;
    assert(exact_slot);
    root->removeChildNode(nested);assert(render_factory_sync_owner(&r,child_view,0));
    assert(entry(child_view)->owned&&entry(child_anchor)->native_owner==child_view);
    render_factory_replacing(item_id,root,nullptr);delete root;render_factory_replaced(item_id,root,nullptr);
    assert(entry(observed_id)&&entry(child_anchor)&&alive);
    render_factory_end_scope(1);assert(!entry(root_view)&&entry(child_view));
    scope.identity=2;
    assert(render_factory_consumable(child_view)&&render_factory_handoff(&r,child_view,item_id,true));
    assert(!entry(child_view)&&entry(child_anchor)&&entry(observed_id));
    auto closing_view=render_factory_restore(&r,nested,1,item_id);assert(closing_view);
    render_factory_replacing_allocation(child_anchor);
    BqtRequest stale;assert(!entry(closing_view)->validate(&stale,closing_view)&&stale.error==ESTALE);
    assert(alive);delete nested;render_factory_replaced_allocation(child_anchor);
    assert(!entry(observed_id)&&!entry(child_anchor)&&!alive);
    render_factory_end_scope(2);active_gui_render_scope=nullptr;
    assert(render_factory_domains->empty());
    window.hide();window.releaseResources();QCoreApplication::processEvents();
    puts("QT612_RENDER_FACTORY_DOMAINS_OK real_factory=1 atomic_failure=1 native_delete=1 nested_proxy=1 slots=1 subtree_move=1 reuse=1 allocation_replace=1 cleanup=1");
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=ROOT / 'build/render-factory-domains')
    parser.add_argument('--qt-root', type=Path, default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    parser.add_argument('--cxx', default='clang++-19')
    parser.add_argument('--sanitize', action='store_true')
    args = parser.parse_args(); args.work.mkdir(parents=True, exist_ok=True)
    template = ROOT / 'generator/templates/render_factory_domains.cpp'
    batch_path = ROOT / 'generator/templates/retention_extra.cpp'
    batch = batch_path.read_text(); start = batch.index('struct RetentionBatch {'); end = batch.index('\n};', start) + 3
    domains = template.read_text().replace('@QSG_NODE_ID@', '1').replace('@QQUICK_WINDOW_ID@', '2').replace('@VARIANT_ID@', '3')
    source = args.work / 'main.cpp'; source.write_text(REGISTRY.replace('@RETENTION_BATCH@', batch[start:end]).replace('@DOMAINS@', domains))
    kit = args.qt_root; target = args.work / 'control'
    command = [args.cxx, '-std=c++17', '-O1', '-g', '-fPIC', str(source), '-I' + str(kit / 'include')]
    if args.sanitize: command += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    command += ['-I' + str(kit / 'include' / module) for module in ('QtCore', 'QtGui', 'QtQml', 'QtQuick')]
    command += ['-L' + str(kit / 'lib'), '-Wl,-rpath,' + str(kit / 'lib'), '-lQt6Quick', '-lQt6Qml', '-lQt6Gui', '-lQt6Core', '-o', str(target)]
    built = subprocess.run(command, capture_output=True, text=True)
    (args.work / 'compile.log').write_text(built.stdout + built.stderr)
    if built.returncode: raise RuntimeError('Factory domain control failed to compile; see ' + str(args.work / 'compile.log'))
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software', QSG_RENDER_LOOP='basic', LD_LIBRARY_PATH=str(kit / 'lib'))
    if args.sanitize: env['ASAN_OPTIONS'] = 'detect_leaks=0'
    result = subprocess.run([str(target)], capture_output=True, text=True, env=env)
    (args.work / 'runtime.log').write_text(result.stdout + result.stderr)
    if result.returncode: raise RuntimeError('Factory domain control failed; see ' + str(args.work / 'runtime.log'))
    receipt = dict(passed=True, sanitized=args.sanitize, source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        domain_template_sha256=hashlib.sha256(template.read_bytes()).hexdigest(),
        retention_template_sha256=hashlib.sha256(batch_path.read_bytes()).hexdigest(), native_output=result.stdout.strip())
    (args.work / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(result.stdout, end='')


if __name__ == '__main__': main()
