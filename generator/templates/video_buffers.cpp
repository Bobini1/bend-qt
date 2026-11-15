struct VideoMappingState {
    uint32_t owner = 0, record = 0; int mode = 0; bool active = true;
    std::shared_ptr<std::atomic<uint64_t>> epoch;
    uint64_t generation = 0;
};
struct VideoPlaneStorage {
    std::shared_ptr<std::vector<uint64_t>> bytes;
    size_t size = 0, offset = 0;
};
struct VideoRecordStorage {
    uint32_t token = 0;
    VideoPlaneStorage planes[4];
    std::shared_ptr<VideoMappingState> mapping;
};
struct VideoBufferStorage {
    uint32_t token = 0;
    std::shared_ptr<VideoMappingState> mapping;
    std::optional<QVideoFrameFormat> format;
    bool format_frozen = false;
    bool mapping_inflight = false;
};
static SlotTable<VideoRecordStorage *> video_records;
static SlotTable<VideoBufferStorage *> video_buffers;
static constexpr uint32_t video_map_slot = 0x5649444du;
static bool video_mapping_in_progress(uint32_t);
static VideoRecordStorage *video_record(uint32_t id) {
    auto *p=video_records[id & 65535u]; return p && p->token==id ? p : nullptr;
}
static VideoBufferStorage *video_buffer(uint32_t id, bool create=false) {
    auto *p=video_buffers[id & 65535u];
    if (p && p->token==id) return p;
    if (!create) return nullptr;
    auto next=std::make_unique<VideoBufferStorage>(); next->token=id;
    video_buffers[id & 65535u]=next.release(); return video_buffers[id & 65535u];
}
static bool video_mapping_in_progress(uint32_t id) {
    auto *buffer=video_buffer(id); return buffer && buffer->mapping_inflight;
}
static void retire_video_mapping(uint32_t id) {
    if (auto *p=video_buffer(id)) {
        if (p->mapping) p->mapping->active=false;
        p->mapping.reset();
    }
    for (auto &edge:retentions) if (edge.owner==id && edge.slot==video_map_slot) edge={};
    schedule_collection();
}
// Qt may unmap a buffer on another thread. Even an unmap that runs only the
// native base implementation revokes the views at once; the registry itself
// changes on the main thread.
static void video_unmap_from_thread(uint32_t id,const std::shared_ptr<std::atomic<uint64_t>> &epoch) try {
    const uint64_t generation=epoch->fetch_add(1,std::memory_order_acq_rel)+1;
    if (auto *context=main_context.load(std::memory_order_acquire))
        QMetaObject::invokeMethod(context,[id,epoch,generation] {
            auto *buffer=video_buffer(id);
            if (buffer && buffer->mapping && buffer->mapping->epoch==epoch && buffer->mapping->generation<generation)
                retire_video_mapping(id);
        },Qt::QueuedConnection);
} catch (...) {
    // The atomic revocation already happened. A later map or destruction
    // retires the lease if allocating its queued cleanup event failed.
}
static void video_buffers_forget(uint32_t id) {
    if (video_buffer(id)) {
        retire_video_mapping(id); delete video_buffers[id & 65535u]; video_buffers[id & 65535u]=nullptr;
    }
    if (video_record(id)) { delete video_records[id & 65535u]; video_records[id & 65535u]=nullptr; }
}
static bool validate_video_record(BqtRequest *r,uint32_t id) {
    auto *e=entry(id); auto *storage=video_record(id);
    if (!e || !storage) { fail(r,ESTALE,"Video plane record expired"); return false; }
    auto *owner=storage->mapping ? entry(storage->mapping->owner) : nullptr;
    bool active=storage->mapping && storage->mapping->active && storage->mapping->epoch &&
                storage->mapping->generation==storage->mapping->epoch->load(std::memory_order_acquire);
    bool alive=owner && (!owner->alive || (*owner->alive)->load(std::memory_order_acquire));
    auto decision=lifetime_video_epoch[unsigned(bool(storage->mapping))*4+unsigned(active)*2+unsigned(alive)];
    if (decision) { fail(r,decision,"Video mapping expired or its buffer was destroyed"); return false; }
    auto &data=*static_cast<QAbstractVideoBuffer::MapData *>(e->value);
    if (data.planeCount<0 || data.planeCount>4) { fail(r,ERANGE,"Video plane count exceeds fixed storage"); return false; }
    for (int i=0;i<4;++i) {
        auto &plane=storage->planes[i]; auto *pointer=plane.bytes ? reinterpret_cast<uchar *>(plane.bytes->data()) + plane.offset : nullptr;
        if (data.data[i]!=pointer || data.dataSize[i]<0 || data.bytesPerLine[i]<0 || plane.offset>plane.size || size_t(data.dataSize[i])>plane.size-plane.offset) {
            fail(r,ESTALE,"Video plane pointers or extents changed outside the binding"); return false;
        }
    }
    return true;
}
static bool video_record_mutable(BqtRequest *r,uint32_t id) {
    if (!validate_video_record(r,id)) return false;
    auto *e=entry(id); auto *storage=video_record(id);
    unsigned policy=unsigned(e->owned)*8+unsigned(retained(id))*4+unsigned(e->active_calls>1)*2+unsigned(e->read_only);
    if (!lifetime_move[policy] || storage->mapping) { fail(r,EBUSY,"Published video plane records are immutable"); return false; }
    return true;
}
static uint32_t finish_video_ownership(BqtRequest *r,uint32_t id) try {
    auto *e=entry(id); if (!e || e->type!=@MAP@) return id;
    auto next=std::make_unique<VideoRecordStorage>(); next->token=id;
    uint32_t origin=native_call_scope ? native_call_scope->value_origin : 0;
    auto *source=video_record(origin);
    if (!source) if (auto *buffer=video_buffer(origin); buffer && buffer->mapping) source=video_record(buffer->mapping->record);
    if (source) { *next=*source; next->token=id; }
    else if (auto *previous=video_record(id)) { *next=*previous; next->token=id; }
    auto *data=static_cast<QAbstractVideoBuffer::MapData *>(e->value);
    for (int i=0;i<4;++i) {
        auto &plane=next->planes[i]; auto *pointer=plane.bytes ? reinterpret_cast<uchar *>(plane.bytes->data()) + plane.offset : nullptr;
        if (data->data[i]!=pointer) {
            fail(r,ENOTSUP,"Native video plane pointers require a checked mapping origin");
            auto *value=e->value; auto destroy=e->destroy; invalidate(id); if (destroy) destroy(value); return 0;
        }
    }
    delete video_records[id & 65535u]; video_records[id & 65535u]=next.release();
    e->validate=validate_video_record;
    if (!validate_video_record(r,id)) {
        auto *value=e->value; auto destroy=e->destroy; invalidate(id); if (destroy) destroy(value); return 0;
    }
    return id;
} catch (...) {
    if (auto *e=entry(id)) { auto *value=e->value; auto destroy=e->destroy; invalidate(id); if (destroy) destroy(value); }
    throw;
}
static bool set_video_planes(BqtRequest *r,uint32_t id,const QList<std::optional<ImageBuffer>> &planes) {
    if (!video_record_mutable(r,id)) return false;
    if (planes.size()!=4) { fail(r,EINVAL,"Video plane array must contain exactly four optional buffers"); return false; }
    auto next=*video_record(id); auto *data=static_cast<QAbstractVideoBuffer::MapData *>(entry(id)->value);
    for (int i=0;i<4;++i) {
        next.planes[i]=planes[i] ? VideoPlaneStorage{planes[i]->storage,planes[i]->size} : VideoPlaneStorage{};
        if (size_t(data->dataSize[i])>next.planes[i].size) { fail(r,ERANGE,"Video plane size exceeds replacement storage"); return false; }
    }
    *video_record(id)=std::move(next);
    for (int i=0;i<4;++i) data->data[i]=video_record(id)->planes[i].bytes ? reinterpret_cast<uchar *>(video_record(id)->planes[i].bytes->data()) : nullptr;
    return true;
}
static bool set_video_plane_count(BqtRequest *r,uint32_t id,int count) {
    if (!video_record_mutable(r,id)) return false;
    if (count<0 || count>4) { fail(r,ERANGE,"Video plane count must be between zero and four"); return false; }
    static_cast<QAbstractVideoBuffer::MapData *>(entry(id)->value)->planeCount=count; return true;
}
static bool set_video_plane_sizes(BqtRequest *r,uint32_t id,const QList<int> &sizes,bool stride) {
    if (!video_record_mutable(r,id)) return false;
    if (sizes.size()!=4) { fail(r,EINVAL,"Video plane extent array must contain exactly four elements"); return false; }
    auto *data=static_cast<QAbstractVideoBuffer::MapData *>(entry(id)->value); auto *storage=video_record(id);
    for (int i=0;i<4;++i) if (sizes[i]<0 || (!stride && size_t(sizes[i])>storage->planes[i].size)) {
        fail(r,ERANGE,"Video plane extent exceeds its owned backing storage"); return false;
    }
    for (int i=0;i<4;++i) (stride ? data->bytesPerLine : data->dataSize)[i]=sizes[i];
    return true;
}
static BqtValue video_planes(BqtRequest *r,uint32_t id) {
    if (!validate_video_record(r,id)) return {};
    auto *data=static_cast<QAbstractVideoBuffer::MapData *>(entry(id)->value); auto *storage=video_record(id);
    ConversionValueGuard result(sequence_value(4));
    for (int i=0;i<4;++i) {
        auto &wire=result.value.items[i]; wire=sequence_value(data->data[i] ? 1 : 0);
        if (!data->data[i]) continue;
        int mode=storage->mapping ? storage->mapping->mode : QVideoFrame::ReadWrite;
        MemoryView view{id,data->data[i],size_t(data->dataSize[i]),i,!(mode & QVideoFrame::WriteOnly),nullptr};
        view.readable=bool(mode & QVideoFrame::ReadOnly);
        view.observe=[](BqtRequest *check,const MemoryView &view,bool) {
            if (!validate_video_record(check,view.owner)) return false;
            auto &data=*static_cast<QAbstractVideoBuffer::MapData *>(entry(view.owner)->value);
            return view.auxiliary<4 && view.address==data.data[view.auxiliary] && view.size==size_t(data.dataSize[view.auxiliary]);
        };
        wire.items[0].word=register_memory_view(r,view,@VIEW@); wire.items[0].owned_handle=wire.items[0].word;
        if (r->error) return {};
    }
    return result.release();
}
static bool video_buffer_observed(BqtRequest *r,uint32_t id) {
    auto *e=entry(id);
    if (!e || !e->native_observed || (e->alive && !(*e->alive)->load(std::memory_order_acquire))) {
        fail(r,ENOTSUP,"Direct buffer mapping requires an observed custom video buffer"); return false;
    }
    return true;
}
struct VideoMapInvocation;
static VideoMapInvocation *video_map_invocation;
struct VideoMapInvocation {
    VideoMapInvocation *previous=video_map_invocation;
    uint32_t owner; int mode; bool published=false;
    std::shared_ptr<std::atomic<uint64_t>> epoch;
    uint64_t generation;
    VideoMapInvocation(BqtRequest *r,uint32_t owner,int mode,std::shared_ptr<std::atomic<uint64_t>> epoch)
        :owner(owner),mode(mode),epoch(std::move(epoch)),generation(this->epoch->load(std::memory_order_acquire)) {
        if (!video_buffer_observed(r,owner)) return;
        auto *buffer=video_buffer(owner,true);
        if (buffer->mapping && buffer->mapping->epoch && buffer->mapping->generation!=buffer->mapping->epoch->load(std::memory_order_acquire)) retire_video_mapping(owner);
        if (mode<1 || mode>3) { fail(r,EINVAL,"Invalid video mapping mode"); return; }
        if (buffer->mapping_inflight || (buffer->mapping && buffer->mapping->active)) { fail(r,EBUSY,"Custom video buffer is already mapping or mapped"); return; }
        buffer->mapping_inflight=true;
        video_map_invocation=this;
    }
    ~VideoMapInvocation() {
        if (video_map_invocation==this) {
            if (auto *buffer=video_buffer(owner)) buffer->mapping_inflight=false;
            video_map_invocation=previous;
        }
    }
};
static bool remember_video_format(BqtRequest *r,const QVideoFrameFormat &format) {
    if (format.pixelFormat()<QVideoFrameFormat::Format_Invalid || format.pixelFormat()>=QVideoFrameFormat::NPixelFormats) { fail(r,EINVAL,"Custom video format has an unknown native pixel enum"); return false; }
    auto *frame=callback_frame(r->self);
    if (!frame || !entry(frame->receiver)) { fail(r,ESTALE,"Video format callback receiver expired"); return false; }
    auto *buffer=video_buffer(frame->receiver,true); if (!buffer->format_frozen) buffer->format=format; return true;
}
// Public pixel formats define the plane sampling. This also performs Qt 6.12's
// documented single-buffer plane derivation with checked 64-bit arithmetic
// before Qt's qvideoframe.cpp map() can perform its unchecked int arithmetic.
static bool normalize_video_layout(BqtRequest *r,uint32_t owner,QAbstractVideoBuffer::MapData &data,VideoRecordStorage &storage) {
    auto *buffer=video_buffer(owner);
    if (!buffer || !buffer->format) return true; // A direct map exposes only bounded plane views.
    const auto &format=*buffer->format;
    using F=QVideoFrameFormat;
    const auto pixel=format.pixelFormat();
    if (pixel==F::Format_Jpeg) return data.planeCount==1 || (fail(r,EINVAL,"JPEG video needs one compressed plane"),false);
    if (!format.isValid() || pixel<=F::Format_Invalid || pixel>=F::NPixelFormats) {
        fail(r,EINVAL,"Video buffer returned an invalid pixel format"); return false;
    }
    uint64_t width=unsigned(format.frameWidth()),height=unsigned(format.frameHeight());
    if (!width || !height || width>INT_MAX || height>INT_MAX) { fail(r,ERANGE,"Invalid video dimensions"); return false; }
    uint64_t row[4]{},rows[4]{height,height,height,height};
    unsigned planes=1, component=1; bool subsampled_three=false, imc_three=false;
    switch (pixel) {
    case F::Format_YUV420P10: component=2; [[fallthrough]];
    case F::Format_YUV420P: case F::Format_YV12:
        planes=3; subsampled_three=true; row[0]=width*component;
        row[1]=row[2]=((width+1)/2)*component; rows[1]=rows[2]=(height+1)/2; break;
    case F::Format_YUV422P:
        planes=3; subsampled_three=true; row[0]=width; row[1]=row[2]=(width+1)/2; break;
    case F::Format_P010: case F::Format_P016: component=2; [[fallthrough]];
    case F::Format_NV12: case F::Format_NV21:
        planes=2; row[0]=width*component; row[1]=((width+1)/2)*2*component; rows[1]=(height+1)/2; break;
    case F::Format_IMC1: case F::Format_IMC3:
        planes=3; imc_three=true; row[0]=width; row[1]=row[2]=(width+1)/2; rows[1]=rows[2]=(height+1)/2; break;
    case F::Format_IMC2: case F::Format_IMC4:
        planes=2; row[0]=width; row[1]=((width+1)/2)*2; rows[1]=(height+1)/2; break;
    case F::Format_UYVY: case F::Format_YUYV: row[0]=((width+1)/2)*4; break;
    case F::Format_Y8: row[0]=width; break;
    case F::Format_Y16: row[0]=width*2; break;
    case F::Format_AYUV: case F::Format_AYUV_Premultiplied: row[0]=width*4; break;
    case F::Format_SamplerExternalOES: case F::Format_SamplerRect:
        fail(r,ENOTSUP,"A CPU plane buffer cannot provide an opaque GPU sampler"); return false;
    default: {
        auto image=F::imageFormatFromPixelFormat(pixel);
        if (image==QImage::Format_Invalid) { fail(r,ENOTSUP,"Unknown video pixel packing"); return false; }
        row[0]=(width*QImage::toPixelFormat(image).bitsPerPixel()+7)/8;
    }}
    if (data.planeCount==1 && planes>1) {
        uint64_t stride=unsigned(data.bytesPerLine[0]),total=unsigned(data.dataSize[0]);
        uint64_t first=stride*height;
        if (first>total || first>INT_MAX) { fail(r,ERANGE,"Single-buffer video luma plane exceeds its extent"); return false; }
        uint64_t sizes[3]{first,0,0},strides[3]{stride,stride,stride};
        if (subsampled_three) {
            uint64_t chroma_height=pixel==F::Format_YUV422P ? height : height/2;
            if (!chroma_height) { fail(r,ERANGE,"Single-buffer planar video needs at least two rows"); return false; }
            strides[1]=strides[2]=(total-first)/2/chroma_height;
            sizes[1]=sizes[2]=strides[1]*chroma_height;
        } else if (imc_three) sizes[1]=sizes[2]=stride*height/2;
        else sizes[1]=total-first;
        uint64_t offset=0;
        for (unsigned i=0;i<planes;++i) {
            if (sizes[i]>INT_MAX || strides[i]>INT_MAX || offset>total || sizes[i]>total-offset) {
                fail(r,ERANGE,"Derived video plane exceeds its owned backing"); return false;
            }
            storage.planes[i]=storage.planes[0]; storage.planes[i].offset=storage.planes[0].offset+size_t(offset);
            data.data[i]=reinterpret_cast<uchar *>(storage.planes[i].bytes->data())+storage.planes[i].offset;
            data.dataSize[i]=int(sizes[i]); data.bytesPerLine[i]=int(strides[i]); offset+=sizes[i];
        }
        data.planeCount=int(planes);
    }
    if (data.planeCount!=int(planes)) { fail(r,EINVAL,"Video plane count does not match its pixel format"); return false; }
    for (unsigned i=0;i<planes;++i) {
        if (row[i]>unsigned(data.bytesPerLine[i]) || uint64_t(unsigned(data.bytesPerLine[i]))*rows[i]>unsigned(data.dataSize[i])) {
            fail(r,ERANGE,"Video pixel rows exceed their bounded plane storage"); return false;
        }
    }
    return true;
}
static bool publish_video_mapping(BqtRequest *r,uint32_t source,QAbstractVideoBuffer::MapData &result) {
    auto *call=video_map_invocation;
    auto *frame=callback_frame(r->self);
    if (frame) while (call && call->owner!=frame->receiver) call=call->previous;
    if (!call || !frame) { fail(r,EINVAL,"Video mapping reply has no active native invocation"); return false; }
    if (!validate_video_record(r,source)) return false;
    if (!result.planeCount) return true;
    for (int i=0;i<result.planeCount;++i) if (!result.data[i] || result.dataSize[i]<=0) {
        fail(r,EINVAL,"Mapped video planes require nonempty bounded storage"); return false;
    }
    NativeCallScope scope; scope.value_origin=source;
    ConversionValueGuard copy({}); copy.value.word=own(r,new QAbstractVideoBuffer::MapData(result),@MAP@); copy.value.owned_handle=copy.value.word;
    if (r->error) return false;
    auto *copy_data=static_cast<QAbstractVideoBuffer::MapData *>(entry(copy.value.word)->value);
    if (!normalize_video_layout(r,call->owner,*copy_data,*video_record(copy.value.word))) return false;
    result=*copy_data;
    auto mapping=std::make_shared<VideoMappingState>(); mapping->owner=call->owner; mapping->record=copy.value.word; mapping->mode=call->mode;
    mapping->epoch=call->epoch; mapping->generation=call->generation;
    if (mapping->generation!=mapping->epoch->load(std::memory_order_acquire)) {
        fail(r,ESTALE,"Native buffer was unmapped before its map callback completed"); return false;
    }
    RetentionBatch retention;
    if (!retention.add(r,call->owner,video_map_slot,copy.value.word,nullptr,false,false,0) || !retention.finish(r)) return false;
    video_record(copy.value.word)->mapping=mapping;
    auto *e=entry(copy.value.word); e->read_only=true; e->pending_release=true;
    video_buffer(call->owner,true)->mapping=std::move(mapping);
    copy.value.owned_handle=0; call->published=true; return true;
}
static BqtValue consume_video_buffer(BqtRequest *r,uint32_t id,QAbstractVideoBuffer *source) {
    auto *e=entry(id);
    if (!e || !video_buffer_observed(r,id) || !can_transfer_handle(r,id)) return {};
    unsigned policy=unsigned(e->owned)*8+unsigned(retained(id))*4+unsigned(e->active_calls>1)*2+unsigned(e->read_only);
    if (!lifetime_move[policy]) { fail(r,EBUSY,"Video frame requires an exclusively owned, inactive custom buffer"); return {}; }
    if (auto *buffer=video_buffer(id); buffer && buffer->mapping && buffer->mapping->active) {
        fail(r,EBUSY,"Unmap the custom video buffer before transferring ownership"); return {};
    }
    // Allocate the wrapper before crossing the consuming native boundary.
    auto frame=std::make_unique<QVideoFrame>();
    e->owned=false;
    *frame=QVideoFrame(std::unique_ptr<QAbstractVideoBuffer>(source));
    if (r->error) return {};
    if (auto *buffer=video_buffer(id)) buffer->format_frozen=true;
    BqtValue result{}; result.word=own(r,frame.release(),@FRAME@); result.owned_handle=result.word; return result;
}
