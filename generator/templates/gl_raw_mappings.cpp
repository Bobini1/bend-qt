static GLuint raw_gl_buffer_id(BqtRequest *r, GLenum target_or_name, bool named)
{
    if (!check_graphics_context(r)) return 0;
    auto *functions = QOpenGLContext::currentContext()->extraFunctions();
    if (named) {
        if (!functions->glIsBuffer(target_or_name)) { fail(r, EINVAL, "OpenGL buffer name is not an allocated buffer"); return 0; }
        return target_or_name;
    }
    GLenum binding = 0;
    switch (target_or_name) {
    case GL_ARRAY_BUFFER: binding = GL_ARRAY_BUFFER_BINDING; break;
    case GL_ELEMENT_ARRAY_BUFFER: binding = GL_ELEMENT_ARRAY_BUFFER_BINDING; break;
    case GL_PIXEL_PACK_BUFFER: binding = GL_PIXEL_PACK_BUFFER_BINDING; break;
    case GL_PIXEL_UNPACK_BUFFER: binding = GL_PIXEL_UNPACK_BUFFER_BINDING; break;
    case GL_COPY_READ_BUFFER: binding = GL_COPY_READ_BUFFER_BINDING; break;
    case GL_COPY_WRITE_BUFFER: binding = GL_COPY_WRITE_BUFFER_BINDING; break;
    case GL_UNIFORM_BUFFER: binding = GL_UNIFORM_BUFFER_BINDING; break;
    case GL_TRANSFORM_FEEDBACK_BUFFER: binding = GL_TRANSFORM_FEEDBACK_BUFFER_BINDING; break;
    case GL_ATOMIC_COUNTER_BUFFER: binding = GL_ATOMIC_COUNTER_BUFFER_BINDING; break;
    case GL_DRAW_INDIRECT_BUFFER: binding = GL_DRAW_INDIRECT_BUFFER_BINDING; break;
    case GL_DISPATCH_INDIRECT_BUFFER: binding = GL_DISPATCH_INDIRECT_BUFFER_BINDING; break;
    case GL_SHADER_STORAGE_BUFFER: binding = GL_SHADER_STORAGE_BUFFER_BINDING; break;
    case GL_TEXTURE_BUFFER: binding = GL_TEXTURE_BUFFER_BINDING; break;
    case GL_QUERY_BUFFER: binding = GL_QUERY_BUFFER_BINDING; break;
    default: fail(r, EINVAL, "Unsupported OpenGL buffer binding target"); return 0;
    }
    GLint buffer = 0;
    functions->glGetIntegerv(binding, &buffer);
    if (!buffer) { fail(r, EINVAL, "OpenGL mapping requires a bound buffer"); return 0; }
    return GLuint(buffer);
}

struct RawGLBufferBinding {
    QOpenGLExtraFunctions *functions = QOpenGLContext::currentContext()->extraFunctions();
    GLint previous = 0;
    explicit RawGLBufferBinding(GLuint buffer) {
        functions->glGetIntegerv(GL_ARRAY_BUFFER_BINDING, &previous);
        functions->glBindBuffer(GL_ARRAY_BUFFER, buffer);
    }
    ~RawGLBufferBinding() { functions->glBindBuffer(GL_ARRAY_BUFFER, GLuint(previous)); }
    GLint64 value(GLenum parameter) {
        GLint64 result = 0;
        const auto *context = QOpenGLContext::currentContext();
        const auto version = context->format().version();
        if (context->isOpenGLES() || version.first > 3 || (version.first == 3 && version.second >= 2))
            functions->glGetBufferParameteri64v(GL_ARRAY_BUFFER, parameter, &result);
        else { GLint narrow = 0; functions->glGetBufferParameteriv(GL_ARRAY_BUFFER, parameter, &narrow); result = narrow; }
        return result;
    }
};

struct NativeRawGLMapping {
    GLuint buffer = 0;
    QPointer<QOpenGLContext> context = QOpenGLContext::currentContext();
    void *address = nullptr;
    bool active = false, owned = true, explicit_flush = false;
    bool compatible() const {
        auto *current = QOpenGLContext::currentContext();
        return context && current && (context == current || QOpenGLContext::areSharing(context, current));
    }
    bool live() {
        if (!active || !compatible()) return false;
        auto *functions = QOpenGLContext::currentContext()->extraFunctions();
        if (!functions->glIsBuffer(buffer)) { active = false; return false; }
        RawGLBufferBinding binding(buffer);
        GLint mapped = 0;
        void *pointer = nullptr;
        functions->glGetBufferParameteriv(GL_ARRAY_BUFFER, GL_BUFFER_MAPPED, &mapped);
        if (mapped) functions->glGetBufferPointerv(GL_ARRAY_BUFFER, GL_BUFFER_MAP_POINTER, &pointer);
        if (!mapped || pointer != address) active = false;
        return active;
    }
    void flush(size_t offset, size_t count) {
        if (explicit_flush && count && live()) {
            RawGLBufferBinding binding(buffer);
            binding.functions->glFlushMappedBufferRange(GL_ARRAY_BUFFER, GLintptr(offset), GLsizeiptr(count));
        }
    }
    ~NativeRawGLMapping() {
        if (owned && live()) {
            RawGLBufferBinding binding(buffer);
            binding.functions->glUnmapBuffer(GL_ARRAY_BUFFER);
        }
    }
};

static void flush_raw_gl_mapping(const MemoryView &view, size_t offset, size_t count)
{
    if (view.raw_gl_mapping) view.raw_gl_mapping->flush(offset, count);
}

static void retire_raw_gl_mappings(GLuint buffer)
{
    for (const auto &e : entries) if (e.value && e.type == @MEMORY_VIEW@) {
        const auto &state = static_cast<const MemoryView *>(e.value)->raw_gl_mapping;
        if (state && state->compatible() && state->buffer == buffer) state->active = false;
    }
}

static bool guard_raw_gl_mapping_mutation(BqtRequest *r, GLuint buffer)
{
    for (const auto &e : entries) if (e.value && e.type == @MEMORY_VIEW@) {
        const auto &view = *static_cast<const MemoryView *>(e.value);
        if (view.raw_gl_mapping && view.raw_gl_mapping->buffer == buffer && view.raw_gl_mapping->compatible() && view.raw_gl_mapping->live())
            return fail(r, EBUSY, "Release or unmap raw OpenGL mappings before replacing buffer storage"), false;
@QT_BUFFER_MUTATION_GUARD@
    }
    return true;
}

static bool observe_raw_gl_mapping(BqtRequest *r, const MemoryView &view, bool)
{
    if (!entry(view.owner)) return fail(r, ESTALE, "Raw OpenGL mapping owner was destroyed"), false;
    if (!view.raw_gl_mapping || !view.raw_gl_mapping->compatible())
        return fail(r, EXDEV, "Raw OpenGL mapping requires its current or sharing context"), false;
    if (!view.raw_gl_mapping->live()) return fail(r, ESTALE, "Raw OpenGL mapping has been unmapped or replaced"), false;
    return true;
}

static bool raw_gl_mapping_request(BqtRequest *r, GLuint target_or_name, bool named,
                                    int mode, int64_t offset, int64_t length, GLenum access)
{
    if (!check_gl_mapping_context(r)) return true;
    const auto buffer = raw_gl_buffer_id(r, target_or_name, named);
    if (r->error) return true;
    RawGLBufferBinding binding(buffer);
    GLint mapped = 0;
    binding.functions->glGetBufferParameteriv(GL_ARRAY_BUFFER, GL_BUFFER_MAPPED, &mapped);
    if (mode && mapped) return fail(r, EBUSY, "OpenGL buffer is already mapped");
    if (!mode && access != GL_BUFFER_MAP_POINTER) return fail(r, EINVAL, "OpenGL mapped-pointer query requires GL_BUFFER_MAP_POINTER");
    if (!mode && !mapped) return fail(r, ESTALE, "OpenGL buffer is not mapped");
    const auto extent = binding.value(GL_BUFFER_SIZE);
    bool readable = false, writable = false;
    if (mode == 1) {
        if (access != GL_READ_ONLY && access != GL_WRITE_ONLY && access != GL_READ_WRITE)
            return fail(r, EINVAL, "Invalid OpenGL mapping access");
        offset = 0; length = extent;
        readable = access != GL_WRITE_ONLY; writable = access != GL_READ_ONLY;
    } else if (mode == 2) {
        readable = access & GL_MAP_READ_BIT; writable = access & GL_MAP_WRITE_BIT;
        if ((access & ~255u) || !(readable || writable) || ((access & GL_MAP_FLUSH_EXPLICIT_BIT) && !writable) ||
            ((access & GL_MAP_COHERENT_BIT) && !(access & GL_MAP_PERSISTENT_BIT)) ||
            (readable && (access & (GL_MAP_INVALIDATE_RANGE_BIT | GL_MAP_INVALIDATE_BUFFER_BIT | GL_MAP_UNSYNCHRONIZED_BIT))))
            return fail(r, EINVAL, "Invalid OpenGL range mapping access");
    }
    if (mode && (extent < 0 || offset < 0 || length <= 0 || offset > extent || length > extent - offset))
        return fail(r, ERANGE, "Raw OpenGL mapping exceeds its buffer extent");
    if (!mode) {
        // Reuse an existing scope's control block, so a pointer getter neither
        // creates a second unmap owner nor outlives the original mapping scope.
        for (const auto &e : entries) if (e.value && e.type == @MEMORY_VIEW@) {
            const auto &view = *static_cast<const MemoryView *>(e.value);
            const bool same_raw = view.raw_gl_mapping && view.raw_gl_mapping->buffer == buffer && view.raw_gl_mapping->live();
            const bool same_qt = @QT_BUFFER_LIVE@;
            if (same_raw || same_qt) {
                r->result.word = register_memory_view(r, view, @MEMORY_VIEW@);
                if (auto *entry_value = entry(r->result.word)) entry_value->graphics_context = e.graphics_context;
                r->result.owned_handle = r->result.word;
                return true;
            }
        }
    }
    auto state = std::make_shared<NativeRawGLMapping>();
    state->buffer = buffer;
    state->owned = bool(mode);
    if (mode == 1) {
        const auto map = reinterpret_cast<void *(*)(GLenum, GLenum)>(QOpenGLContext::currentContext()->getProcAddress("glMapBuffer"));
        if (!map) return fail(r, ENOTSUP, "OpenGL context has no whole-buffer mapping entry point");
        state->address = map(GL_ARRAY_BUFFER, access);
    } else if (mode == 2) {
        state->address = binding.functions->glMapBufferRange(GL_ARRAY_BUFFER, GLintptr(offset), GLsizeiptr(length), access);
    } else {
        binding.functions->glGetBufferPointerv(GL_ARRAY_BUFFER, GL_BUFFER_MAP_POINTER, &state->address);
        offset = binding.value(GL_BUFFER_MAP_OFFSET); length = binding.value(GL_BUFFER_MAP_LENGTH);
        GLint flags = 0;
        binding.functions->glGetBufferParameteriv(GL_ARRAY_BUFFER, GL_BUFFER_ACCESS_FLAGS, &flags);
        access = GLenum(flags); readable = access & GL_MAP_READ_BIT; writable = access & GL_MAP_WRITE_BIT;
    }
    state->active = state->address != nullptr;
    state->explicit_flush = mode != 1 && (access & GL_MAP_FLUSH_EXPLICIT_BIT);
    if (!state->active) return fail(r, EIO, "OpenGL buffer mapping failed");
    if (length < 0 || uint64_t(length) > uint64_t(std::numeric_limits<qsizetype>::max()))
        return fail(r, ERANGE, "Raw OpenGL mapping extent is outside the native range");
    MemoryView view{r->self, state->address, size_t(length), 0, !writable, observe_raw_gl_mapping, {}, {}, readable, state};
    r->result.word = register_memory_view(r, view, @MEMORY_VIEW@);
    if (auto *registered = entry(r->result.word)) registered->graphics_context = entry(r->self)->graphics_context;
    r->result.owned_handle = r->result.word;
    return true;
}
