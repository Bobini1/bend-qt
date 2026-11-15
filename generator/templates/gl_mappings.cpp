// GL 3 exposes non-mutating map liveness and pointer queries. The buffer and
// context remain held by the MemoryView; no numeric address reaches Bend.
static bool check_gl_mapping_context(BqtRequest *r) {
    if (!check_graphics_context(r)) return false;
    auto version = QOpenGLContext::currentContext()->format().version();
    if (version.first < 3) {
        fail(r, ENOTSUP, "Checked OpenGL mappings require OpenGL or OpenGL ES 3"); return false;
    }
    return true;
}
struct GLBufferBinding {
    QOpenGLExtraFunctions *functions;
    GLenum target;
    GLint previous = 0;
    GLBufferBinding(QOpenGLBuffer::Type type, GLuint buffer)
        : functions(QOpenGLContext::currentContext()->extraFunctions()), target(GLenum(type)) {
        GLenum selector = type == QOpenGLBuffer::VertexBuffer ? GL_ARRAY_BUFFER_BINDING :
            type == QOpenGLBuffer::IndexBuffer ? GL_ELEMENT_ARRAY_BUFFER_BINDING :
            type == QOpenGLBuffer::PixelPackBuffer ? GL_PIXEL_PACK_BUFFER_BINDING : GL_PIXEL_UNPACK_BUFFER_BINDING;
        functions->glGetIntegerv(selector, &previous);
        functions->glBindBuffer(target, buffer);
    }
    ~GLBufferBinding() { functions->glBindBuffer(target, GLuint(previous)); }
};
struct NativeGLMapping {
    QOpenGLBuffer buffer;
    QPointer<QOpenGLContext> context;
    void *address = nullptr;
    bool active = false, explicit_flush = false;
    explicit NativeGLMapping(const QOpenGLBuffer &source)
        : buffer(source), context(QOpenGLContext::currentContext()) {}
    bool compatible() const {
        auto *current = QOpenGLContext::currentContext();
        return context && current && (context == current || QOpenGLContext::areSharing(context, current));
    }
    bool live() {
        if (!active || !compatible() || !buffer.isCreated()) return false;
        auto *functions = QOpenGLContext::currentContext()->extraFunctions();
        if (!functions->glIsBuffer(buffer.bufferId())) { active = false; return false; }
        GLBufferBinding binding(buffer.type(), buffer.bufferId());
        GLint mapped = 0;
        void *pointer = nullptr;
        functions->glGetBufferParameteriv(binding.target, GL_BUFFER_MAPPED, &mapped);
        if (mapped) functions->glGetBufferPointerv(binding.target, GL_BUFFER_MAP_POINTER, &pointer);
        if (!mapped || pointer != address) active = false;
        return active;
    }
    void flush(size_t offset, size_t count) {
        if (explicit_flush && count && live()) {
            GLBufferBinding binding(buffer.type(), buffer.bufferId());
            binding.functions->glFlushMappedBufferRange(binding.target, GLintptr(offset), GLsizeiptr(count));
        }
    }
    ~NativeGLMapping() {
        if (live()) {
            GLBufferBinding binding(buffer.type(), buffer.bufferId());
            buffer.unmap();
        }
    }
};
static void flush_memory_mapping(const MemoryView &view, size_t offset, size_t count) {
    if (view.gl_mapping) view.gl_mapping->flush(offset, count);
    flush_raw_gl_mapping(view, offset, count);
}
static bool observe_gl_mapping(BqtRequest *r, const MemoryView &view, bool) {
    if (!entry(view.owner)) { fail(r, ESTALE, "OpenGL mapping owner was destroyed"); return false; }
    if (!view.gl_mapping || !view.gl_mapping->compatible()) {
        fail(r, EXDEV, "OpenGL mapping requires its current or sharing context"); return false;
    }
    if (!view.gl_mapping->live()) { fail(r, ESTALE, "OpenGL mapping has been unmapped or replaced"); return false; }
    return true;
}
static void retire_gl_mappings(GLuint buffer) {
    retire_raw_gl_mappings(buffer);
    for (const auto &e : entries) if (e.value && e.type == @MEMORY_VIEW@) {
        const auto &state = static_cast<const MemoryView *>(e.value)->gl_mapping;
        if (state && state->compatible() && state->buffer.bufferId() == buffer) state->active = false;
    }
}
static bool guard_gl_mapping_mutation(BqtRequest *r, QOpenGLBuffer *buffer) {
    if (!guard_raw_gl_mapping_mutation(r, buffer->bufferId())) return false;
    for (const auto &e : entries) if (e.value && e.type == @MEMORY_VIEW@) {
        const auto &state = static_cast<const MemoryView *>(e.value)->gl_mapping;
        if (state && state->compatible() && state->buffer.bufferId() == buffer->bufferId() && state->live()) {
            fail(r, EBUSY, "Unmap the OpenGL buffer before changing its storage"); return false;
        }
    }
    return true;
}
