#include <cassert>
#include <cstdio>
#include BQT_GENERATED_WRAPPERS
#include "test-host-native.h"
using namespace bendqt;
using Operation=bool (*)(BqtRequest *);
static void checked(const BqtRequest &r) { if(r.error)std::fprintf(stderr,"%d %s\n",r.error,r.message);assert(!r.error); }
static BqtValue word(uint32_t n){BqtValue v{};v.word=n;return v;}
static BqtValue list(std::initializer_list<BqtValue> values){auto v=sequence_value(values.size());size_t i=0;for(auto x:values)v.items[i++]=x;return v;}
static BqtRequest call(Operation fn,uint32_t self,std::initializer_list<BqtValue> args={}){
 BqtRequest r{};r.self=self;size_t n=0;for(auto x:args)r.arguments[n++]=x;fn(&r);for(size_t i=0;i<n;++i)discard_value(r.arguments[i]);return r;
}
template<class T> static uint32_t put(T *p,uint16_t t){BqtRequest r{};auto id=own(&r,p,t);checked(r);return id;}
template<class T> static T *value(uint32_t id){assert(entry(id));return static_cast<T *>(entry(id)->value);}
static void release(uint32_t id){BqtRequest r{};r.self=id;release_object(&r);checked(r);collect_pending();}
static QRhiCommandBuffer *begin(uint32_t root){auto *rhi=value<QRhi>(root);QRhiCommandBuffer *cb=nullptr;assert(rhi->beginOffscreenFrame(&cb)==QRhi::FrameOpSuccess);rhi_frame_started(root,nullptr);return cb;}
static uint32_t command(uint32_t root,QRhiCommandBuffer *cb){BqtRequest r{};r.self=root;auto id=borrow(&r,cb,TYPE_QRhiCommandBuffer);checked(r);return id;}
static void readback_cleanup(uint32_t root) {
 auto *rhi=value<QRhi>(root);
 auto buffer=put(rhi->newBuffer(QRhiBuffer::Static,QRhiBuffer::StorageBuffer,4),TYPE_QRhiBuffer);
 assert(value<QRhiBuffer>(buffer)->create());
 auto *native_batch=rhi->nextResourceUpdateBatch();auto batch=put(native_batch,TYPE_QRhiResourceUpdateBatch);
 BqtRequest request{};rhi_register_batch(&request,batch,root);checked(request);
 auto state=rhi_new_readback(&request,batch,93);checked(request);assert(state&&state->pinned);
 const auto original_pins=entry(root)->active_calls;
 // Qt's completion callback runs the handler with its own copy of the
 // result, even when posting the later storage sweep fails.
 unsigned delivered=0;
 test_handler=[&](uint32_t handler,const BqtValue *call){
  assert(handler==93&&QThread::currentThread()==main_thread);
  assert(call&&call->tag==2&&call->count==2&&call->items[1].tag==0);
  auto *e=entry(call->items[1].word);assert(e);
  assert(static_cast<QRhiReadbackResult *>(e->value)->data==QByteArray("read",4));
  ++delivered;return int(BQT_HANDLER_DONE);
 };
 native_batch->uploadStaticBuffer(value<QRhiBuffer>(buffer),0,4,"read");
 native_batch->readBackBuffer(value<QRhiBuffer>(buffer),0,4,&state->result);
 auto *cb=begin(root);rhi_batch_submitted(batch);
 readback_post_fail=true;
 cb->resourceUpdate(native_batch);invalidate(batch);
 // Leave the frame and pending readback to the ordinary host shutdown path.
 rhi_shutdown();
 test_handler=nullptr;
 assert(delivered==1&&!readback_post_fail&&readback_post_failures==1);
 assert(state->finished&&!state->pinned&&entry(root)->active_calls+1==original_pins);
 assert(state->result.data==QByteArray("read",4));
 assert(!rhi_identity(root)->domain->frame_owned);
 assert(std::none_of(rhi_readbacks().begin(),rhi_readbacks().end(),[&](const auto &item){return item==state;}));
 state.reset();release(buffer);
 std::puts("QT612_RHI_READBACK_POST_FAILURE_OK");
}
int main(int argc,char **argv){
 test_host_start(argc,argv);
 QRhiNullInitParams init;auto root=put(QRhi::create(QRhi::Null,&init),TYPE_QRhi);auto *rhi=value<QRhi>(root);
 readback_cleanup(root);
 auto buffer=put(rhi->newBuffer(QRhiBuffer::Dynamic,QRhiBuffer::UniformBuffer,64),TYPE_QRhiBuffer);assert(value<QRhiBuffer>(buffer)->create());
 auto r=call(OP_MAP,buffer);assert(r.error==EPERM);
 auto *cb=begin(root);auto commands=command(root,cb);
 r=call(OP_MAP,buffer);checked(r);auto viewid=r.result.word;auto *view=value<MemoryView>(viewid);assert(view->size==64&&!view->readonly&&!view->readable);
 assert(view->observe(&r,*view,true));std::memset(view->address,0x2a,64);
 r=call(OP_MAP,buffer);assert(r.error==EBUSY);
 r=call(OP_FINISH,root);assert(r.error==EBUSY);
 r=call(OP_END_FRAME,root,{word(0)});assert(r.error==EBUSY);
 BqtRequest guard{};assert(!rhi_mappings_closed(&guard,commands)&&guard.error==EBUSY);
 r=call(OP_UNMAP,buffer);checked(r);BqtRequest stale{};assert(!view->observe(&stale,*view,true)&&stale.error==ESTALE);
 r=call(OP_UNMAP,buffer);assert(r.error==ESTALE);release(viewid);
 r=call(OP_MAP,buffer);checked(r);viewid=r.result.word;view=value<MemoryView>(viewid);BqtRequest copied{};
 auto copyid=register_memory_view(&copied,*view,TYPE_MemoryView);checked(copied);release(viewid);
 assert(!rhi_mappings_closed(&(guard=BqtRequest{}),commands));release(copyid);
 assert(rhi_mappings_closed(&(guard=BqtRequest{}),commands));
 // A copied view's last release closes the mapping, so frame submission works.
 r=call(OP_END_FRAME,root,{word(0)});checked(r);assert(!entry(commands));
 auto immutable=put(rhi->newBuffer(QRhiBuffer::Immutable,QRhiBuffer::UniformBuffer,64),TYPE_QRhiBuffer);assert(value<QRhiBuffer>(immutable)->create());
 cb=begin(root);commands=command(root,cb);r=call(OP_MAP,immutable);assert(r.error==EPERM);
 r=call(OP_END_FRAME,root,{word(0)});checked(r);release(immutable);
 // Null backend runs the public command path without requiring shader binaries.
 auto vertex=put(rhi->newBuffer(QRhiBuffer::Immutable,QRhiBuffer::VertexBuffer,32),TYPE_QRhiBuffer);assert(value<QRhiBuffer>(vertex)->create());
 auto index=put(rhi->newBuffer(QRhiBuffer::Immutable,QRhiBuffer::IndexBuffer,16),TYPE_QRhiBuffer);assert(value<QRhiBuffer>(index)->create());
 auto other=put(QRhi::create(QRhi::Null,&init),TYPE_QRhi);auto foreign=put(value<QRhi>(other)->newBuffer(QRhiBuffer::Immutable,QRhiBuffer::VertexBuffer,16),TYPE_QRhiBuffer);assert(value<QRhiBuffer>(foreign)->create());
 auto texture=put(rhi->newTexture(QRhiTexture::RGBA8,QSize(8,8),1,QRhiTexture::RenderTarget),TYPE_QRhiTexture);assert(value<QRhiTexture>(texture)->create());
 auto target=put(rhi->newTextureRenderTarget(QRhiTextureRenderTargetDescription(value<QRhiTexture>(texture))),TYPE_QRhiTextureRenderTarget);
 auto pass=put(value<QRhiTextureRenderTarget>(target)->newCompatibleRenderPassDescriptor(),TYPE_QRhiRenderPassDescriptor);
 value<QRhiTextureRenderTarget>(target)->setRenderPassDescriptor(value<QRhiRenderPassDescriptor>(pass));assert(value<QRhiTextureRenderTarget>(target)->create());
 cb=begin(root);commands=command(root,cb);
 auto bindings=[&](uint32_t id,uint32_t offset){return list({list({word(id),word(offset)})});};
 r=call(OP_VERTEX,commands,{word(0),word(1),bindings(vertex,0),word(index),word(0),word(QRhiCommandBuffer::IndexUInt16)});assert(r.error==EPERM);
 cb->beginPass(value<QRhiTextureRenderTarget>(target),Qt::black,{1,0});rhi_pass_changed(commands,1);
 r=call(OP_VERTEX,commands,{word(0),word(2),bindings(vertex,0),word(index),word(0),word(QRhiCommandBuffer::IndexUInt16)});assert(r.error==ERANGE);
 r=call(OP_VERTEX,commands,{word(0),word(1),bindings(vertex,33),word(index),word(0),word(QRhiCommandBuffer::IndexUInt16)});assert(r.error==ERANGE);
 r=call(OP_VERTEX,commands,{word(0),word(1),bindings(foreign,0),word(index),word(0),word(QRhiCommandBuffer::IndexUInt16)});assert(r.error==EXDEV);
 r=call(OP_VERTEX,commands,{word(0),word(1),bindings(vertex,4),word(index),word(2),word(QRhiCommandBuffer::IndexUInt16)});checked(r);
 release(vertex);release(index);assert(entry(vertex)&&entry(index));
 cb->endPass();rhi_pass_changed(commands,0);r=call(OP_END_FRAME,root,{word(0)});checked(r);collect_pending();assert(!entry(vertex)&&!entry(index));
 // Shutdown closes unfinished mappings before the backend submits its frame.
 cb=begin(root);commands=command(root,cb);r=call(OP_MAP,buffer);checked(r);viewid=r.result.word;rhi_shutdown();
 stale={};assert(!value<MemoryView>(viewid)->observe(&stale,*value<MemoryView>(viewid),true)&&stale.error==ESTALE);release(viewid);
 for(auto id:{target,pass,texture,buffer,foreign,other,root})release(id);
 size_t live=0,edges=0;for(const auto &e:entries)live+=e.value!=nullptr;for(const auto &e:retentions)edges+=e.owner!=0;
 std::printf("REMAINING objects=%zu retentions=%zu\n",live,edges);assert(!live&&!edges);assert(bqt_abi_stop()==0);std::puts("QT612_NEXT_RHI_BUFFERS_OK");
}
