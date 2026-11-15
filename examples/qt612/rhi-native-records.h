#pragma once
#ifdef BQT_RHI_FULL_UPDATE
static void rhi_native_record_checks() {
    using namespace bendqt;
    BqtRequest r{};
    QRhiNullInitParams parameters;
    auto *root = QRhi::create(QRhi::Null, &parameters);
    assert(root);
    uint32_t root_id = own(&r, root, BQT_RHI_ROOT_TYPE);
    auto *buffer = root->newBuffer(QRhiBuffer::Dynamic, QRhiBuffer::UniformBuffer, 4);
    uint32_t buffer_id = own(&r, buffer, BQT_RHI_BUFFER_TYPE);
    auto bytes_id = own(&r, new QByteArray("abcd", 4), BQT_RHI_BYTES_TYPE);
    assert(!r.error);
    r = {}; r.self = buffer_id; BQT_RHI_BUFFER_CREATE(&r); assert(!r.error && r.result.word);
    r = {}; r.self = buffer_id; r.arguments[0].word = bytes_id; BQT_RHI_FULL_UPDATE(&r);
    assert(r.error == EPERM);
    QRhiCommandBuffer *commands = nullptr;
    assert(root->beginOffscreenFrame(&commands) == QRhi::FrameOpSuccess);
    rhi_frame_started(root_id, nullptr);
    r = {}; r.self = buffer_id; r.arguments[0].word = bytes_id; BQT_RHI_FULL_UPDATE(&r);
    assert(!r.error);
    auto *native = buffer->beginFullDynamicBufferUpdateForCurrentFrame();
    assert(native && !std::memcmp(native, "abcd", 4));
    buffer->endFullDynamicBufferUpdateForCurrentFrame();
    r = {}; r.self = buffer_id; r.arguments[0].word = bytes_id; r.arguments[1].word = 5; BQT_RHI_FULL_UPDATE(&r);
    assert(r.error == ERANGE);
    auto *bytes = static_cast<QByteArray *>(entry(bytes_id)->value); bytes->truncate(3);
    r = {}; r.self = buffer_id; r.arguments[0].word = bytes_id; BQT_RHI_FULL_UPDATE(&r);
    assert(r.error == ERANGE); *bytes = QByteArray("abcd", 4);
    r = {}; assert(!rhi_buffer_batch_access(&r, buffer_id) && r.error == EPERM);
    // PySide does not register QRhiNullNativeHandles, so the Null backend has
    // no typed record. A backend-specific getter must reject the wrong backend.
    BqtValue record = {};
#ifdef BQT_RHI_NULL_HANDLES
    r = {}; r.self = root_id; BQT_RHI_NULL_HANDLES(&r); assert(!r.error && r.result.word);
    record = r.result;
#elif defined(BQT_RHI_GLES_HANDLES)
    r = {}; r.self = root_id; BQT_RHI_GLES_HANDLES(&r); assert(r.error == EINVAL && !r.result.word);
#endif
    r = {}; r.self = root_id; BQT_RHI_ENUM_NULL(&r); // self is ignored: static enumeration takes parameters.
    assert(r.error); // No typed parameter was supplied.
    r = {}; auto params_id = own(&r, new QRhiNullInitParams, BQT_RHI_NULL_PARAMS_TYPE);
    r = {}; r.arguments[0].word = params_id; BQT_RHI_ENUM_NULL(&r);
    assert(!r.error); discard_value(r.result);
    assert(root->endOffscreenFrame() == QRhi::FrameOpSuccess); rhi_frame_finished(root_id);
#ifdef BQT_RHI_BUFFER_NATIVE_DESTROY
    r = {}; r.self = buffer_id; BQT_RHI_BUFFER_NATIVE_DESTROY(&r); assert(!r.error);
    assert(root->beginOffscreenFrame(&commands) == QRhi::FrameOpSuccess); rhi_frame_started(root_id, nullptr);
    r = {}; r.self = buffer_id; r.arguments[0].word = bytes_id; BQT_RHI_FULL_UPDATE(&r);
    assert(r.error == ENODATA); // Destroyed native storage cannot reuse the old allocation extent.
    assert(root->endOffscreenFrame() == QRhi::FrameOpSuccess); rhi_frame_finished(root_id);
    std::puts("QT612_NATIVE_RHI_STORAGE_OK destroyed_allocation_rejected=1");
#endif
    for (auto id : {buffer_id, bytes_id, params_id}) { r = {}; r.self = id; destroy_object(&r); assert(!r.error); }
    if (record.word) {
        r = {}; r.self = root_id; destroy_object(&r); assert(r.error == EBUSY);
        discard_value(record);
    }
    r = {}; r.self = root_id; destroy_object(&r); assert(!r.error);
#ifdef BQT_RHI_GLES_HANDLES
    std::unique_ptr<QOffscreenSurface> surface(QRhiGles2InitParams::newFallbackSurface());
    QRhiGles2InitParams gl_params; gl_params.fallbackSurface = surface.get();
    auto *gl_root = QRhi::create(QRhi::OpenGLES2, &gl_params);
    assert(gl_root);
    r = {}; auto gl_id = own(&r, gl_root, BQT_RHI_ROOT_TYPE);
    r = {}; r.self = gl_id; BQT_RHI_GLES_HANDLES(&r);
    if (r.error) std::fprintf(stderr, "OpenGL RHI record: error %d: %s\n", r.error, r.message ? r.message : "");
    assert(!r.error && r.result.word);
    auto gl_record = r.result;
    assert(static_cast<QRhiGles2NativeHandles *>(entry(gl_record.word)->value)->context->isValid());
    r = {}; r.self = gl_id; destroy_object(&r); assert(r.error == EBUSY);
    discard_value(gl_record);
    r = {}; r.self = gl_id; destroy_object(&r); assert(!r.error);
    std::puts("QT612_NATIVE_RHI_GLES_RECORDS_OK actual_context=1 owner_retained=1");
#endif
    std::puts("QT612_NATIVE_RHI_RECORDS_OK zero_means_full=1 source_extent=1 destination_extent=1 active_frame=1 direct_batch_exclusion=1 wrong_backend_record=1 enumerate=1 record_owner=1 frame_expiry=1");
}
#endif
