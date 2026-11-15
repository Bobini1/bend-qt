// Exercises the QtGui GL functions without the optional QtOpenGL module.
#include <cassert>
#include BQT_GENERATED_WRAPPERS

int main(int argc, char **argv) {
    using namespace bendqt;
    QApplication app(argc, argv); application = &app; main_thread = app.thread();
    QOpenGLContext context;
    QSurfaceFormat format; format.setVersion(3, 2); format.setProfile(QSurfaceFormat::CoreProfile);
    context.setFormat(format); assert(context.create());
    QOffscreenSurface surface; surface.setFormat(context.format()); surface.create();
    assert(context.makeCurrent(&surface));
    BqtRequest r{};
    const auto functions = own(&r, new QOpenGLExtraFunctions, BQT_GL_GUI_FUNCTIONS_TYPE);
    assert(functions && !r.error);
    auto *gl = context.extraFunctions();
    GLuint buffer = 0; gl->glGenBuffers(1, &buffer); gl->glBindBuffer(GL_ARRAY_BUFFER, buffer);
    gl->glBufferData(GL_ARRAY_BUFFER, 8, "abcdefgh", GL_DYNAMIC_DRAW);
    auto release = [&](uint32_t id) { r = {}; r.self = id; destroy_object(&r); assert(!r.error); };
    auto map = [&](GLenum access, uint64_t offset, uint64_t length) {
        r = {}; r.self = functions; r.arguments[0].word = GL_ARRAY_BUFFER;
        r.arguments[1] = wide_value(offset); r.arguments[2] = wide_value(length); r.arguments[3].word = access;
        BQT_GL_GUI_RANGE(&r); assert(!r.error && r.result.word); return r.result.word;
    };
    const auto writable = map(GL_MAP_WRITE_BIT | GL_MAP_FLUSH_EXPLICIT_BIT, 2, 4);
    r = {}; const auto bytes = own(&r, new QByteArray("XY"), BQT_GL_GUI_BYTES_TYPE);
    r = {}; r.self = writable; r.arguments[0] = wide_value(0); r.arguments[1].word = bytes;
    BQT_GL_GUI_WRITE(&r); assert(!r.error);
    r = {}; r.self = functions; r.arguments[0].word = GL_ARRAY_BUFFER; r.arguments[1].word = GL_BUFFER_MAP_POINTER;
    BQT_GL_GUI_GET(&r); assert(!r.error && r.result.word); const auto alias = r.result.word;
    assert(static_cast<MemoryView *>(entry(alias)->value)->raw_gl_mapping ==
           static_cast<MemoryView *>(entry(writable)->value)->raw_gl_mapping);
    r = {}; r.self = functions; r.arguments[0].word = 1; r.arguments[1] = sequence_value(1); r.arguments[1].items[0].word = buffer;
    BQT_GL_GUI_DELETE(&r); assert(r.error == EBUSY); discard_value(r.arguments[1]);
    release(writable);
    GLint mapped = 0; gl->glGetBufferParameteriv(GL_ARRAY_BUFFER, GL_BUFFER_MAPPED, &mapped); assert(mapped);
    release(alias); gl->glGetBufferParameteriv(GL_ARRAY_BUFFER, GL_BUFFER_MAPPED, &mapped); assert(!mapped);
    const auto readable = map(GL_MAP_READ_BIT, 0, 8);
    r = {}; r.self = readable; r.arguments[0] = wide_value(0); r.arguments[1] = wide_value(8);
    BQT_GL_GUI_READ(&r); assert(!r.error);
    assert(*static_cast<QByteArray *>(entry(r.result.word)->value) == "abXYefgh");
    release(r.result.word);
    r = {}; r.self = functions; r.arguments[0].word = GL_ARRAY_BUFFER; BQT_GL_GUI_UNMAP(&r);
    assert(!r.error && r.result.word);
    r = {}; r.self = readable; BQT_GL_GUI_SIZE(&r); assert(r.error == ESTALE);
    release(readable); release(bytes); release(functions);
    gl->glDeleteBuffers(1, &buffer);
    std::puts("QT612_GUI_ONLY_RAW_GL_OK map=1 explicit_flush=1 getter_alias=1 delete_guard=1 scoped_unmap=1 explicit_unmap_stale=1 no_qt_opengl=1");
}
