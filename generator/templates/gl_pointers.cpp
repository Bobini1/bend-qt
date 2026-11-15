static bool validate_gl_client_pointer_query(BqtRequest *r, GLenum selector, GLuint index, bool attributes)
{
    if (!attributes) return true;
    if (selector != GL_VERTEX_ATTRIB_ARRAY_POINTER)
        return fail(r, EINVAL, "Vertex attribute pointer query requires GL_VERTEX_ATTRIB_ARRAY_POINTER"), false;
    GLint limit = 0;
    QOpenGLContext::currentContext()->functions()->glGetIntegerv(GL_MAX_VERTEX_ATTRIBS, &limit);
    if (limit < 0 || index >= GLuint(limit))
        return fail(r, ERANGE, "Vertex attribute index exceeds the context limit"), false;
    return true;
}
static bool gl_client_pointer_result(BqtRequest *r, GLenum selector, GLuint index, bool attributes, void *pointer)
{
    // kind: 0 = buffer offset, 1 = feedback, 2 = selection, 3 = null.
    // Feedback/selection storage is bounded and owned by the context adapter.
    GLuint buffer = 0;
    auto *context = QOpenGLContext::currentContext();
    if (attributes) {
        GLint value = 0;
        context->functions()->glGetVertexAttribiv(index, GL_VERTEX_ATTRIB_ARRAY_BUFFER_BINDING, &value);
        buffer = GLuint(value);
    } else {
        GLenum binding = 0;
        switch (selector) {
        case GL_VERTEX_ARRAY_POINTER: binding = GL_VERTEX_ARRAY_BUFFER_BINDING; break;
        case GL_NORMAL_ARRAY_POINTER: binding = GL_NORMAL_ARRAY_BUFFER_BINDING; break;
        case GL_COLOR_ARRAY_POINTER: binding = GL_COLOR_ARRAY_BUFFER_BINDING; break;
        case GL_INDEX_ARRAY_POINTER: binding = GL_INDEX_ARRAY_BUFFER_BINDING; break;
        case GL_TEXTURE_COORD_ARRAY_POINTER: binding = GL_TEXTURE_COORD_ARRAY_BUFFER_BINDING; break;
        case GL_EDGE_FLAG_ARRAY_POINTER: binding = GL_EDGE_FLAG_ARRAY_BUFFER_BINDING; break;
        case GL_FOG_COORD_ARRAY_POINTER: binding = GL_FOG_COORD_ARRAY_BUFFER_BINDING; break;
        case GL_SECONDARY_COLOR_ARRAY_POINTER: binding = GL_SECONDARY_COLOR_ARRAY_BUFFER_BINDING; break;
        case GL_FEEDBACK_BUFFER_POINTER: case GL_SELECTION_BUFFER_POINTER: break;
        case GL_DEBUG_CALLBACK_FUNCTION: case GL_DEBUG_CALLBACK_USER_PARAM:
            if (pointer) return fail(r, ENOTSUP, "Foreign GL debug callbacks have no binding-owned signature or data extent");
            break;
        default: return fail(r, EINVAL, "Unknown OpenGL client pointer selector");
        }
        if (binding) { GLint value = 0; context->functions()->glGetIntegerv(binding, &value); buffer = GLuint(value); }
    }
    r->result = sequence_value(5);
    r->result.items[0].word = 3;
    r->result.items[2] = wide_value(0);
    r->result.items[3] = sequence_value(0);
    r->result.items[4] = sequence_value(0);
    if (buffer) {
        RawGLBufferBinding bound(buffer);
        const auto offset = uint64_t(reinterpret_cast<uintptr_t>(pointer));
        const auto extent = bound.value(GL_BUFFER_SIZE);
        if (extent < 0 || offset > uint64_t(extent)) return fail(r, ERANGE, "OpenGL client offset exceeds its buffer");
        r->result.items[0].word = 0;
        r->result.items[1].word = buffer;
        discard_value(r->result.items[2]);
        r->result.items[2] = wide_value(offset);
        return true;
    }
    if (!pointer) return true;
    for (const auto &slot : retained_gl_outputs()) if (slot.context == context) {
        if (selector == GL_FEEDBACK_BUFFER_POINTER && slot.feedback && slot.feedback->values.data() == pointer) {
            r->result.items[3] = sequence_value(1);
            const auto id = own(r, new GLFeedbackBuffer{slot.feedback}, @GLFeedbackBuffer@);
            if (r->error) return true;
            r->result.items[0].word = 1;
            r->result.items[3].items[0].word = id;
            r->result.items[3].items[0].owned_handle = id;
            return true;
        }
        if (selector == GL_SELECTION_BUFFER_POINTER && slot.selection && slot.selection->values.data() == pointer) {
            r->result.items[4] = sequence_value(1);
            const auto id = own(r, new GLSelectionBuffer{slot.selection}, @GLSelectionBuffer@);
            if (r->error) return true;
            r->result.items[0].word = 2;
            r->result.items[4].items[0].word = id;
            r->result.items[4].items[0].owned_handle = id;
            return true;
        }
    }
    return fail(r, ENOTSUP, "Foreign OpenGL client storage has no binding-owned extent");
}
