#ifdef BQT_RETAINED_GL_FEEDBACK
static void gl_retained_checks()
{
    using namespace bendqt;
    QOpenGLContext context;
    assert(context.create());
    QOffscreenSurface surface;
    surface.setFormat(context.format()); surface.create();
    assert(context.makeCurrent(&surface));
    BqtRequest request{};
    const auto functions = own(&request, new QOpenGLFunctions_1_0, BQT_GL_LEGACY_FUNCTIONS_TYPE);
    const auto pointers = own(&request, new QOpenGLFunctions_1_1, BQT_GL_POINTER_FUNCTIONS_TYPE);
    const auto attributes = own(&request, new QOpenGLFunctions, BQT_GL_FUNCTIONS_TYPE);
    auto release = [&](uint32_t id) {
        request = {}; request.self = id;
        destroy_object(&request);
        assert(!request.error);
    };
    request = {}; request.self = functions;
    request.arguments[0].word = 16;
    request.arguments[1].word = GL_2D;
    BQT_RETAINED_GL_FEEDBACK(&request);
    assert(!request.error);
    const auto feedback = request.result.word;
    auto *gl = static_cast<QOpenGLFunctions_1_0 *>(entry(functions)->value);
    gl->glRenderMode(GL_FEEDBACK);
    gl->glPassThrough(42);
    request = {}; request.self = feedback; request.arguments[0].word = 2;
    BQT_RETAINED_GL_FEEDBACK_READ(&request);
    assert(request.error == EBUSY);
    request = {}; request.self = pointers; request.arguments[0].word = GL_FEEDBACK_BUFFER_POINTER;
    BQT_RETAINED_GL_POINTER(&request);
    assert(!request.error && request.result.items[0].word == 1);
    const auto alias = request.result.items[3].items[0].word;
    auto pointer_wire = request.result;
    release(feedback);
    assert(gl->glRenderMode(GL_RENDER) == 2);
    request = {}; request.self = alias; request.arguments[0].word = 2;
    BQT_RETAINED_GL_FEEDBACK_READ(&request);
    assert(!request.error && request.result.count == 2);
    assert(real_value(request.result.items[0]) == GL_PASS_THROUGH_TOKEN && real_value(request.result.items[1]) == 42);
    discard_value(request.result);
    discard_value(pointer_wire);
    // Context storage remains valid after the last Bend handle is released.
    gl->glRenderMode(GL_FEEDBACK); gl->glPassThrough(7);
    assert(gl->glRenderMode(GL_RENDER) == 2);

    request = {}; request.self = functions; request.arguments[0].word = 8;
    BQT_RETAINED_GL_SELECTION(&request);
    assert(!request.error);
    const auto selection = request.result.word;
    gl->glRenderMode(GL_SELECT); gl->glInitNames(); gl->glPushName(7);
    gl->glBegin(GL_POINTS); gl->glVertex2f(0, 0); gl->glEnd();
    assert(gl->glRenderMode(GL_RENDER) == 1);
    request = {}; request.self = selection; request.arguments[0].word = 4;
    BQT_RETAINED_GL_SELECTION_READ(&request);
    assert(!request.error && request.result.count == 4);
    assert(request.result.items[0].word == 1 && request.result.items[3].word == 7);
    discard_value(request.result);
    request = {}; request.self = selection; request.arguments[0].word = 9;
    BQT_RETAINED_GL_SELECTION_READ(&request);
    assert(request.error == ERANGE);
    release(selection);
    GLuint buffer = 0;
    auto *base = context.functions();
    base->glGenBuffers(1, &buffer); base->glBindBuffer(GL_ARRAY_BUFFER, buffer);
    base->glBufferData(GL_ARRAY_BUFFER, 16, nullptr, GL_STATIC_DRAW);
    base->glVertexAttribPointer(0, 2, GL_FLOAT, false, 0, reinterpret_cast<void *>(8));
    request = {}; request.self = attributes; request.arguments[0].word = 0;
    request.arguments[1].word = GL_VERTEX_ATTRIB_ARRAY_POINTER;
    BQT_RETAINED_GL_VERTEX_POINTER(&request);
    assert(!request.error && request.result.items[0].word == 0 && request.result.items[1].word == buffer);
    assert(wide_bits(request.result.items[2]) == 8);
    discard_value(request.result);
    base->glDeleteBuffers(1, &buffer);
    request = {};
    const auto bytes = own(&request, new QByteArray(2, char(0)), BQT_GL_BYTE_ARRAY_TYPE);
    request = {}; request.self = functions; request.arguments[0].word = 1;
    request.arguments[1].word = GL_3_BYTES; request.arguments[2].word = bytes;
    BQT_RETAINED_GL_CALL_LISTS(&request);
    assert(request.error == ERANGE);
    release(bytes); release(attributes); release(pointers); release(functions);
    std::puts("QT612_NATIVE_GL_RETAINED_OK feedback=1 selection=1 active_read_rejected=1 context_retention=1 pointer_alias=1 buffer_offset=1 bounded_lists=1");
}
#endif
