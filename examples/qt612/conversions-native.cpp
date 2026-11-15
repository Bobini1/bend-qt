// Maintainer fixture. The harness supplies the generated source and codec names.
#include <new>
#include <cstdlib>
#include <cassert>
#include <thread>
#include BQT_GENERATED_WRAPPERS
#include "test-host-native.h"

static int fail_after_allocations = -1;

void *operator new(std::size_t size)
{
    if (fail_after_allocations == 0) {
        fail_after_allocations = -1; // Destruction during unwinding may allocate.
        throw std::bad_alloc();
    }
    if (fail_after_allocations > 0)
        --fail_after_allocations;
    if (void *memory = std::malloc(size))
        return memory;
    throw std::bad_alloc();
}

void operator delete(void *memory) noexcept { std::free(memory); }
void operator delete(void *memory, std::size_t) noexcept { std::free(memory); }

#ifdef BQT_FUTURE_NEW
static void future_checks()
{
    using namespace bendqt;
    BqtRequest request{};
    BQT_FUTURE_NEW(&request);
    assert(!request.error);
    const auto original = request.result.word;
    request = {};
    BQT_WATCHER_NEW(&request);
    assert(!request.error);
    const auto watcher = request.result.word;
    request = {};
    request.self = watcher;
    request.arguments[0].word = original;
    BQT_WATCHER_SET(&request);
    assert(request.error == ENODATA); // An invalid future must not hang await.
    request = {};
    request.arguments[0].word = original;
    BQT_FUTURE_AWAIT(&request);
    assert(request.error == ENODATA);

    QPromise<QString> promise;
    promise.start();
    *static_cast<Future_QString *>(entry(original)->value) = promise.future();
    request = {};
    request.arguments[0].word = original;
    BQT_FUTURE_CLONE(&request);
    assert(!request.error);
    const auto survivor = request.result.word;
    request = {};
    request.arguments[0].word = survivor;
    BQT_FUTURE_RESULT(&request);
    assert(request.error == EAGAIN); // Return promptly before any result exists.

    request = {};
    request.self = watcher;
    request.arguments[0].word = original;
    BQT_WATCHER_SET(&request);
    assert(!request.error);
    request = {};
    request.self = original;
    destroy_object(&request);
    assert(!request.error); // The watcher and clone keep the shared state alive.

    // The generated await operation processes Qt events on the main thread
    // until the shared future finishes. Destroying this context cancels timers.
    QObject timer_scope;
    bool completed = false;
    bool heartbeat = false;
    QTimer::singleShot(0, &timer_scope, [&] { heartbeat = true; });
    QTimer::singleShot(10, &timer_scope, [&] {
        assert(QThread::currentThread() == main_thread);
        promise.addResult(QStringLiteral("asynchronous result"));
        promise.finish();
        completed = true;
    });
    QTimer::singleShot(3000, &timer_scope, [] { std::abort(); });
    request = {};
    request.arguments[0].word = survivor;
    BQT_FUTURE_AWAIT(&request);
    assert(!request.error && heartbeat && completed);
    request = {};
    request.arguments[0].word = survivor;
    BQT_FUTURE_RESULT(&request);
    assert(!request.error);
    assert(QString::fromUtf8(request.result.text, qsizetype(request.result.size)) == QStringLiteral("asynchronous result"));
    discard_value(request.result);
    for (auto id : {watcher, survivor}) {
        request = {};
        request.self = id;
        destroy_object(&request);
        assert(!request.error);
    }
    std::puts("QT612_NATIVE_FUTURES_OK pending_result=1 asynchronous_completion=1 gui_heartbeat=1 invalid_wait=1 shared_state=1 await_loop=1");
}
#endif

#ifdef BQT_FILE_DIALOG_GET_OPEN
static void inout_pointer_checks()
{
    using namespace bendqt;
    QTemporaryFile file(QDir::tempPath() + QStringLiteral("/bend-output-XXXXXX.txt"));
    assert(file.open());
    bool selected = false;
    QTimer::singleShot(0, application, [&] {
        auto *dialog = qobject_cast<QFileDialog *>(QApplication::activeModalWidget());
        assert(dialog);
        assert(dialog->selectedNameFilter() == QStringLiteral("All (*)"));
        dialog->selectNameFilter(QStringLiteral("Text (*.txt)"));
        dialog->selectFile(file.fileName());
        selected = true;
        assert(QMetaObject::invokeMethod(dialog, "accept", Qt::DirectConnection));
    });
    QTimer timeout;
    timeout.setSingleShot(true);
    QObject::connect(&timeout, &QTimer::timeout, application, [] {
        if (auto *dialog = qobject_cast<QDialog *>(QApplication::activeModalWidget()))
            dialog->reject();
    });
    timeout.start(3000);
    BqtRequest request{};
    request.arguments[1] = string_value(QStringLiteral("Bend pointer conversion fixture"));
    request.arguments[2] = string_value(file.fileName());
    request.arguments[3] = string_value(QStringLiteral("Text (*.txt);;All (*)"));
    request.arguments[4] = string_value(QStringLiteral("All (*)"));
    request.arguments[5].word = QFileDialog::DontUseNativeDialog;
    BQT_FILE_DIALOG_GET_OPEN(&request);
    assert(!request.error && selected);
    assert(request.result.tag == 2 && request.result.count == 2);
    const auto &name = request.result.items[0];
    const auto &filter = request.result.items[1];
    assert(QString::fromUtf8(name.text, qsizetype(name.size)) == file.fileName());
    assert(QString::fromUtf8(filter.text, qsizetype(filter.size)) == QStringLiteral("Text (*.txt)"));
    for (int i = 1; i <= 4; ++i)
        discard_value(request.arguments[i]);
    discard_value(request.result);
    std::puts("QT612_NATIVE_INOUT_POINTERS_OK initial_filter=1 updated_filter=1 returned_file=1");
}
#endif

#ifdef BQT_SHADER_MATRIX_2
#ifdef BQT_GL_TEX_IMAGE_2D
static void pixel_buffer_checks(QOpenGLFunctions *functions, uint32_t functions_id)
{
    using namespace bendqt;
    QOpenGLFramebufferObject frame(QSize(2, 2));
    assert(frame.isValid() && frame.bind());
    functions->glClearColor(1, 0, 0, 1);
    functions->glClear(GL_COLOR_BUFFER_BIT);
    functions->glPixelStorei(GL_PACK_ALIGNMENT, 8);
    functions->glPixelStorei(GL_PACK_ROW_LENGTH, 4);
    functions->glPixelStorei(GL_PACK_SKIP_ROWS, 1);
    functions->glPixelStorei(GL_PACK_SKIP_PIXELS, 1);
    BqtRequest call{};
    auto *bytes = new QByteArray(43, '\0');
    const auto bytes_id = own(&call, bytes, BQT_GL_BYTE_ARRAY_TYPE);
    assert(bytes_id && !call.error);
    call.self = functions_id;
    call.arguments[2].word = 2;
    call.arguments[3].word = 2;
    call.arguments[4].word = GL_RGBA;
    call.arguments[5].word = GL_UNSIGNED_BYTE;
    call.arguments[6].word = bytes_id;
    BQT_GL_READ_PIXELS(&call);
    assert(call.error == ERANGE && bytes->size() == 43);
    bytes->resize(44);
    call.error = 0;
    call.message = nullptr;
    BQT_GL_READ_PIXELS(&call);
    assert(!call.error && functions->glGetError() == GL_NO_ERROR);
    assert(static_cast<unsigned char>(bytes->at(20)) == 255 && bytes->at(21) == 0);
    assert(static_cast<unsigned char>(bytes->at(36)) == 255 && bytes->at(37) == 0);
    for (int index = 0; index < 20; ++index) assert(bytes->at(index) == 0);
    functions->glPixelStorei(GL_PACK_ALIGNMENT, 4);
    functions->glPixelStorei(GL_PACK_ROW_LENGTH, 0);
    functions->glPixelStorei(GL_PACK_SKIP_ROWS, 0);
    functions->glPixelStorei(GL_PACK_SKIP_PIXELS, 0);

    GLuint texture = 0;
    functions->glGenTextures(1, &texture);
    functions->glBindTexture(GL_TEXTURE_2D, texture);
    functions->glPixelStorei(GL_UNPACK_ALIGNMENT, 4);
    functions->glPixelStorei(GL_UNPACK_ROW_LENGTH, 3);
    functions->glPixelStorei(GL_UNPACK_SKIP_ROWS, 1);
    functions->glPixelStorei(GL_UNPACK_SKIP_PIXELS, 1);
    call = {};
    call.self = functions_id;
    call.arguments[0].word = GL_TEXTURE_2D;
    call.arguments[2].word = GL_RGBA;
    call.arguments[3].word = 2;
    call.arguments[4].word = 1;
    call.arguments[6].word = GL_RGBA;
    call.arguments[7].word = GL_UNSIGNED_BYTE;
    BQT_GL_TEX_IMAGE_2D(&call); // Null handle explicitly allocates without reading pixels.
    assert(!call.error && functions->glGetError() == GL_NO_ERROR);
    *bytes = QByteArray(23, '\0');
    call.arguments[8].word = bytes_id;
    BQT_GL_TEX_IMAGE_2D(&call);
    assert(call.error == ERANGE);
    *bytes = QByteArray(24, '\0');
    (*bytes)[16] = char(255); (*bytes)[19] = char(255);
    (*bytes)[22] = char(255); (*bytes)[23] = char(255);
    call.error = 0;
    call.message = nullptr;
    BQT_GL_TEX_IMAGE_2D(&call);
    assert(!call.error && functions->glGetError() == GL_NO_ERROR);
    functions->glPixelStorei(GL_UNPACK_IMAGE_HEIGHT, 3);
    functions->glPixelStorei(GL_UNPACK_SKIP_IMAGES, 2);
    call = {};
    assert(gl_pixel_extent(&call, true, true, 2, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE) == 96);
    assert(!call.error); // A one-slice 3D transfer still applies skipped images.
    functions->glPixelStorei(GL_UNPACK_ROW_LENGTH, 0);
    functions->glPixelStorei(GL_UNPACK_SKIP_ROWS, 0);
    functions->glPixelStorei(GL_UNPACK_SKIP_PIXELS, 0);
    functions->glPixelStorei(GL_UNPACK_IMAGE_HEIGHT, 0);
    functions->glPixelStorei(GL_UNPACK_SKIP_IMAGES, 0);
    functions->glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, texture, 0);
    assert(functions->glCheckFramebufferStatus(GL_FRAMEBUFFER) == GL_FRAMEBUFFER_COMPLETE);
    *bytes = QByteArray(8, '\0');
    call = {};
    call.self = functions_id;
    call.arguments[2].word = 2;
    call.arguments[3].word = 1;
    call.arguments[4].word = GL_RGBA;
    call.arguments[5].word = GL_UNSIGNED_BYTE;
    call.arguments[6].word = bytes_id;
    BQT_GL_READ_PIXELS(&call);
    assert(!call.error && functions->glGetError() == GL_NO_ERROR);
    assert(static_cast<unsigned char>(bytes->at(0)) == 255 && bytes->at(2) == 0);
    assert(bytes->at(4) == 0 && static_cast<unsigned char>(bytes->at(6)) == 255);

#ifdef BQT_TEXTURE_UPLOAD
    auto *managed_texture = new QOpenGLTexture(QOpenGLTexture::Target2D);
    assert(managed_texture->create());
    managed_texture->setSize(2, 1);
    managed_texture->setFormat(QOpenGLTexture::RGBA8_UNorm);
    managed_texture->setMipLevels(1);
    managed_texture->allocateStorage(QOpenGLTexture::RGBA, QOpenGLTexture::UInt8);
    auto *options = new QOpenGLPixelTransferOptions;
    options->setAlignment(1);
    options->setRowLength(3);
    options->setSkipRows(1);
    options->setSkipPixels(1);
    call = {};
    const auto texture_id = own(&call, managed_texture, BQT_TEXTURE_TYPE);
    const auto options_id = own(&call, options, BQT_PIXEL_OPTIONS_TYPE);
    assert(texture_id && options_id && !call.error);
    call.self = texture_id;
    call.arguments[0].word = QOpenGLTexture::RGBA;
    call.arguments[1].word = QOpenGLTexture::UInt8;
    call.arguments[2].word = bytes_id;
    call.arguments[3].word = options_id;
    *bytes = QByteArray(23, '\0');
    BQT_TEXTURE_UPLOAD(&call);
    assert(call.error == ERANGE);
    *bytes = QByteArray(24, '\0');
    (*bytes)[17] = char(255); (*bytes)[19] = char(255);
    (*bytes)[20] = char(255); (*bytes)[23] = char(255);
    call.error = 0;
    call.message = nullptr;
    BQT_TEXTURE_UPLOAD(&call);
    assert(!call.error && functions->glGetError() == GL_NO_ERROR);
    GLint restored = -1;
    functions->glGetIntegerv(GL_UNPACK_ROW_LENGTH, &restored);
    assert(restored == 0);
    functions->glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, managed_texture->textureId(), 0);
    *bytes = QByteArray(8, '\0');
    call = {};
    call.self = functions_id;
    call.arguments[2].word = 2;
    call.arguments[3].word = 1;
    call.arguments[4].word = GL_RGBA;
    call.arguments[5].word = GL_UNSIGNED_BYTE;
    call.arguments[6].word = bytes_id;
    BQT_GL_READ_PIXELS(&call);
    assert(!call.error && functions->glGetError() == GL_NO_ERROR);
    assert(bytes->at(0) == 0 && static_cast<unsigned char>(bytes->at(1)) == 255);
    assert(static_cast<unsigned char>(bytes->at(4)) == 255 && bytes->at(5) == 0);
    functions->glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, texture, 0);
    for (auto id : {options_id, texture_id}) {
        call = {};
        call.self = id;
        destroy_object(&call);
        assert(!call.error);
    }
    std::puts("QT612_NATIVE_TEXTURE_OPTIONS_OK explicit_layout=1 exact_extent=1 native_pixels=1 restored_state=1");
#endif

    GLuint vertex_buffer = 0;
    functions->glGenBuffers(1, &vertex_buffer);
    functions->glBindBuffer(GL_ARRAY_BUFFER, vertex_buffer);
    functions->glBufferData(GL_ARRAY_BUFFER, 24, nullptr, GL_STATIC_DRAW);
    call = {};
    call.self = functions_id;
    call.arguments[0].word = 1;
    call.arguments[1].word = 2;
    call.arguments[2].word = GL_FLOAT;
    call.arguments[5] = wide_value(25);
    BQT_GL_VERTEX_POINTER(&call);
    assert(call.error == ERANGE);
    call.arguments[5] = wide_value(0);
    call.error = 0;
    call.message = nullptr;
    BQT_GL_VERTEX_POINTER(&call);
    assert(!call.error && functions->glGetError() == GL_NO_ERROR);
    functions->glBindBuffer(GL_ARRAY_BUFFER, 0);
    BQT_GL_VERTEX_POINTER(&call);
    assert(call.error == EINVAL);
    functions->glDeleteBuffers(1, &vertex_buffer);
    functions->glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0);
    *bytes = QByteArray(3, '\0');
    call = {};
    call.self = functions_id;
    call.arguments[0].word = GL_TRIANGLES;
    call.arguments[1].word = 2;
    call.arguments[2].word = GL_UNSIGNED_SHORT;
    call.arguments[3].word = bytes_id;
    BQT_GL_DRAW_ELEMENTS(&call);
    assert(call.error == ERANGE);
    call.error = 0;
    call.message = nullptr;
    call.arguments[1].word = 0;
    BQT_GL_DRAW_ELEMENTS(&call);
    assert(!call.error && functions->glGetError() == GL_NO_ERROR);
    functions->glDeleteTextures(1, &texture);
    call = {};
    call.self = bytes_id;
    destroy_object(&call);
    assert(!call.error);
    std::puts("QT612_NATIVE_GL_PIXELS_OK row_alignment=1 row_skips=1 image_skips=1 exact_extent=1 null_allocation=1 native_pixels=1 client_indices=1 gpu_offsets=1");
}
#endif

static void matrix_array_checks()
{
    using namespace bendqt;
    QOpenGLContext context;
    assert(context.create());
    QOffscreenSurface surface;
    surface.setFormat(context.format());
    surface.create();
    assert(context.makeCurrent(&surface));
    {
        QOpenGLShaderProgram program;
        assert(program.addShaderFromSourceCode(QOpenGLShader::Vertex,
            "attribute vec4 position; uniform mat2 transform; void main() { gl_Position = vec4(transform * position.xy, position.zw); }"));
        assert(program.addShaderFromSourceCode(QOpenGLShader::Fragment,
            "void main() { gl_FragColor = vec4(1.0); }"));
        assert(program.link() && program.bind());
#ifdef BQT_GL_SHADER_QUERY
        QOpenGLFunctions *functions = new QOpenGLFunctions(&context);
        functions->initializeOpenGLFunctions();
        BqtRequest gl{};
        const auto functions_id = own(&gl, functions, BQT_GL_FUNCTIONS_TYPE);
        assert(functions_id && !gl.error);
#ifdef BQT_GL_SHADER_SOURCE
        {
            const auto shader = functions->glCreateShader(GL_VERTEX_SHADER);
            const QString text = QString::fromUtf8("// UTF-8: \xCE\xA9\nvoid main() { gl_Position = vec4(0.0); }");
            const auto expected = text.toUtf8();
            BqtRequest source{};
            source.self = functions_id;
            source.arguments[0].word = shader;
            source.arguments[1].word = 1;
            source.arguments[2] = sequence_value(1);
            source.arguments[2].items[0] = string_value(text + QStringLiteral("ignored trailing text"));
            source.arguments[3] = sequence_value(1);
            source.arguments[3].items[0].word = uint32_t(expected.size());
            BQT_GL_SHADER_SOURCE(&source);
            assert(!source.error);
            char stored[256]{};
            GLsizei length = 0;
            functions->glGetShaderSource(shader, sizeof(stored), &length, stored);
            assert(QByteArray(stored, length) == expected);
            functions->glCompileShader(shader);
            GLint compiled = 0;
            functions->glGetShaderiv(shader, GL_COMPILE_STATUS, &compiled);
            assert(compiled == GL_TRUE);
            source.arguments[1].word = 2;
            BQT_GL_SHADER_SOURCE(&source);
            assert(source.error == ERANGE);
            source.error = 0;
            source.arguments[1].word = 1;
            source.arguments[3].items[0].word = 1000;
            BQT_GL_SHADER_SOURCE(&source);
            assert(source.error == ERANGE);
            source.error = 0;
            discard_value(source.arguments[2].items[0]);
            source.arguments[2].items[0] = string_value(QString::fromUtf8("a\0b", 3));
            source.arguments[3].items[0].word = uint32_t(-1);
            BQT_GL_SHADER_SOURCE(&source);
            assert(source.error == EINVAL);
            discard_value(source.arguments[2]);
            discard_value(source.arguments[3]);
            functions->glDeleteShader(shader);
            std::puts("QT612_NATIVE_GL_STRINGS_OK utf8_extent=1 explicit_length=1 native_compile=1 count_rejected=1 length_rejected=1 nul_rejected=1");
        }
#endif
        gl.self = functions_id;
        gl.arguments[0].word = program.shaders().front()->shaderId();
        gl.arguments[1].word = GL_COMPILE_STATUS;
        BQT_GL_SHADER_QUERY(&gl);
        assert(!gl.error && gl.result.count == 1 && gl.result.items[0].word == GL_TRUE);
        discard_value(gl.result);
        gl = {};
        gl.self = functions_id;
        gl.arguments[0].word = program.programId();
        gl.arguments[1].word = 2;
        gl.arguments[2] = sequence_value(1);
        BQT_GL_ATTACHED_SHADERS(&gl);
        assert(gl.error == ERANGE);
        discard_value(gl.arguments[2]);
        gl.error = 0;
        gl.message = nullptr;
        gl.arguments[2] = sequence_value(2);
        BQT_GL_ATTACHED_SHADERS(&gl);
        assert(!gl.error && gl.result.count == 2 && gl.result.items[0].word == 2);
        auto &shader_names = gl.result.items[1];
        assert(shader_names.count == 2);
        for (const auto *shader : program.shaders())
            assert(shader_names.items[0].word == shader->shaderId() || shader_names.items[1].word == shader->shaderId());
        discard_value(gl.result);
        discard_value(gl.arguments[2]);
#ifdef BQT_GL_STATE_QUERY
        functions->glViewport(1, 2, 30, 40);
        gl = {};
        gl.self = functions_id;
        gl.arguments[0].word = GL_VIEWPORT;
        gl.arguments[1] = sequence_value(3);
        BQT_GL_STATE_QUERY(&gl);
        assert(gl.error == ERANGE);
        discard_value(gl.arguments[1]);
        gl.error = 0;
        gl.message = nullptr;
        gl.arguments[1] = sequence_value(4);
        BQT_GL_STATE_QUERY(&gl);
        assert(!gl.error && gl.result.count == 1 && gl.result.items[0].count == 4);
        const auto &viewport = gl.result.items[0];
        assert(viewport.items[0].word == 1 && viewport.items[1].word == 2
               && viewport.items[2].word == 30 && viewport.items[3].word == 40);
        discard_value(gl.result);
        discard_value(gl.arguments[1]);
        GLint formats = 0;
        functions->glGetIntegerv(GL_NUM_COMPRESSED_TEXTURE_FORMATS, &formats);
        assert(formats >= 0);
        gl = {};
        gl.self = functions_id;
        gl.arguments[0].word = GL_COMPRESSED_TEXTURE_FORMATS;
        gl.arguments[1] = sequence_value(size_t(formats));
        BQT_GL_STATE_QUERY(&gl);
        assert(!gl.error && gl.result.count == 1 && gl.result.items[0].count == size_t(formats));
        discard_value(gl.result);
        discard_value(gl.arguments[1]);
        gl = {};
        gl.self = functions_id;
        gl.arguments[0].word = UINT32_MAX;
        gl.arguments[1] = sequence_value(16);
        BQT_GL_STATE_QUERY(&gl);
        assert(gl.error == ENOTSUP);
        discard_value(gl.arguments[1]);
        std::puts("QT612_NATIVE_GL_STATE_OK viewport_extent=1 dynamic_count=1 unknown_selector_rejected=1");
#endif
#endif
        const auto location = program.uniformLocation("transform");
        assert(location >= 0);
        BqtRequest request{};
        const auto id = borrow(&request, &program, BQT_SHADER_PROGRAM_TYPE);
        assert(id && !request.error);
        request.self = id;
        request.arguments[0].word = uint32_t(location);
        request.arguments[1] = sequence_value(3);
        BQT_SHADER_MATRIX_2(&request);
        assert(request.error == EINVAL);
        discard_value(request.arguments[1]);
        request = {};
        request.self = id;
        request.arguments[0].word = uint32_t(location);
        request.arguments[1] = sequence_value(4);
        for (int i = 0; i < 4; ++i)
            request.arguments[1].items[i] = real_bits(double(i + 1));
        BQT_SHADER_MATRIX_2(&request);
        assert(!request.error);
        GLfloat actual[4]{};
        context.functions()->glGetUniformfv(program.programId(), location, actual);
        assert(context.functions()->glGetError() == GL_NO_ERROR);
        for (int i = 0; i < 4; ++i)
            assert(actual[i] == GLfloat(i + 1));
        discard_value(request.arguments[1]);
#ifdef BQT_SHADER_ATTRIBUTE_ARRAY
        request = {};
        request.self = id;
        request.arguments[0].word = 2; // GL forbids querying current attribute zero.
        request.arguments[1] = sequence_value(4);
        request.arguments[2].word = 3; // Three columns of two components need six values.
        request.arguments[3].word = 2;
        BQT_SHADER_ATTRIBUTE_ARRAY(&request);
        assert(request.error == ERANGE);
        request.error = 0;
        request.message = nullptr;
        request.arguments[2].word = 2;
        for (int i = 0; i < 4; ++i)
            request.arguments[1].items[i] = real_bits(double(i + 1));
        BQT_SHADER_ATTRIBUTE_ARRAY(&request);
        assert(!request.error);
        context.functions()->glGetVertexAttribfv(2, GL_CURRENT_VERTEX_ATTRIB, actual);
        assert(actual[0] == 1 && actual[1] == 2 && actual[2] == 0 && actual[3] == 1);
        context.functions()->glGetVertexAttribfv(3, GL_CURRENT_VERTEX_ATTRIB, actual);
        assert(actual[0] == 3 && actual[1] == 4 && actual[2] == 0 && actual[3] == 1);
        assert(context.functions()->glGetError() == GL_NO_ERROR);
        discard_value(request.arguments[1]);
#ifdef BQT_GL_SHADER_QUERY
        gl = {};
        gl.self = functions_id;
        gl.arguments[0].word = 3;
        gl.arguments[1].word = GL_CURRENT_VERTEX_ATTRIB;
        gl.arguments[2] = sequence_value(3);
        BQT_GL_ATTRIBUTE_QUERY(&gl);
        assert(gl.error == EINVAL);
        discard_value(gl.arguments[2]);
        gl.error = 0;
        gl.message = nullptr;
        gl.arguments[2] = sequence_value(4);
        for (auto index = 0; index < 4; ++index) gl.arguments[2].items[index] = real_bits(0.0);
        BQT_GL_ATTRIBUTE_QUERY(&gl);
        assert(!gl.error && gl.result.count == 1 && gl.result.items[0].count == 4);
        for (auto index = 0; index < 4; ++index) {
            const auto value = real_value(gl.result.items[0].items[index]);
            assert(value == double(actual[index]));
        }
        discard_value(gl.result);
        discard_value(gl.arguments[2]);
#endif
        std::puts("QT612_NATIVE_ATTRIBUTE_ARRAYS_OK extent_rejection=1 columns=1 rows=1 gl_readback=1");
#endif
#ifdef BQT_GL_SHADER_QUERY
        pixel_buffer_checks(functions, functions_id);
        const auto version = context.format().version();
        if (context.isOpenGLES() ? version.first >= 3 : (version.first > 2 || (version.first == 2 && version.second >= 1))) {
            GLuint pixel_buffer = 0;
            functions->glGenBuffers(1, &pixel_buffer);
            functions->glBindBuffer(GL_PIXEL_UNPACK_BUFFER, pixel_buffer);
            gl = {};
            const auto host_bytes = own(&gl, new QByteArray(16, '\0'), BQT_GL_BYTE_ARRAY_TYPE);
            assert(host_bytes && !gl.error);
            gl.self = functions_id;
            gl.arguments[6].word = 16;
            gl.arguments[7].word = host_bytes;
            BQT_GL_COMPRESSED_UPLOAD(&gl);
            assert(gl.error == EBUSY); // A bound PBO would reinterpret our host pointer as an offset.
            functions->glBindBuffer(GL_PIXEL_UNPACK_BUFFER, 0);
            functions->glDeleteBuffers(1, &pixel_buffer);
            gl = {};
            gl.self = host_bytes;
            destroy_object(&gl);
            assert(!gl.error);
        }
        gl = {};
        gl.self = functions_id;
        destroy_object(&gl);
        assert(!gl.error);
        std::puts("QT612_NATIVE_GL_ARRAYS_OK scalar_query=1 extent_rejection=1 fixed_output=1 counted_output=1 native_readback=1 pbo_rejection=1");
#endif
    }
    context.doneCurrent();
    std::puts("QT612_NATIVE_MATRIX_ARRAYS_OK extent_rejection=1 column_major_values=1 gl_readback=1");
}
#endif

#ifdef BQT_GRAPHICS_FILTER_EQUAL
static void graphics_filter_checks()
{
    using namespace bendqt;
    using Filter = Qt3DRender::QGraphicsApiFilter;
    Filter available, required;
    BqtRequest request{};
    const auto left = borrow(&request, &available, BQT_GRAPHICS_FILTER_TYPE);
    const auto right = borrow(&request, &required, BQT_GRAPHICS_FILTER_TYPE);
    assert(left && right && !request.error);
    auto matches = [&](uint32_t first, uint32_t second) {
        BqtRequest call{};
        call.self = first;
        call.arguments[0].word = second;
        BQT_GRAPHICS_FILTER_EQUAL(&call);
        assert(!call.error);
        const auto equal = bool(call.result.word);
        call.result = {};
        BQT_GRAPHICS_FILTER_NOT_EQUAL(&call);
        assert(!call.error && bool(call.result.word) != equal);
        return equal;
    };
    available.setApi(Filter::OpenGL);
    required.setApi(Filter::OpenGL);
    available.setMajorVersion(4);
    available.setMinorVersion(6);
    required.setMajorVersion(3);
    required.setMinorVersion(3);
    available.setProfile(Filter::CompatibilityProfile);
    required.setProfile(Filter::CoreProfile);
    assert(matches(left, right) && !matches(right, left));
    available.setProfile(Filter::CoreProfile);
    required.setProfile(Filter::CompatibilityProfile);
    assert(!matches(left, right));
    required.setProfile(Filter::CoreProfile);
    available.setExtensions({QStringLiteral("A"), QStringLiteral("B")});
    required.setExtensions({QStringLiteral("B")});
    assert(matches(left, right));
    required.setExtensions({QStringLiteral("C")});
    assert(!matches(left, right));
    required.setExtensions({});
    available.setVendor(QStringLiteral("vendor"));
    required.setVendor(QStringLiteral("other"));
    assert(!matches(left, right));
    required.setVendor(QStringLiteral("vendor"));
    assert(matches(left, right));
    required.setApi(Filter::Vulkan);
    assert(!matches(left, right));
    std::puts("QT612_NATIVE_GRAPHICS_FILTER_OK directional_version=1 profile=1 extensions=1 vendor=1 api=1 complement=1");
}
#endif

#include "gl-sync-native.h"
#include "allocated-bytes-native.h"
#include "native-interop-native.h"
#include "gl-legacy-native.h"
#include "gl-raw-mappings-native.h"
#include "gl-retained-native.h"
#include "byte-iterators-native.h"
#include "volume-data-native.h"
#include "gl-compressed-native.h"
#include "gl-pixel-offsets-native.h"
#include "text-outputs-native.h"
#include "native-platform-native.h"
#include "fixed-arrays-native.h"
#include "qtest-values-native.h"
#include "descriptor-snapshots-native.h"
#include "rhi-native-records.h"
#include "fixed-integer-aliases-native.h"

int main(int argc, char **argv)
{
    test_host_start(argc, argv);
    BqtRequest request{};
    fixed_integer_alias_checks();
#ifdef BQT_GL_SYNC_FENCE
    gl_sync_checks();
#endif
#ifdef BQT_STREAM_ALLOCATED_BYTES
    allocated_byte_checks();
#endif
#ifdef BQT_INTEROP_LIBRARY_RESOLVE
    native_interop_checks();
#endif
#ifdef BQT_LEGACY_MATERIAL_SET
    gl_legacy_checks();
#endif
#ifdef BQT_RAW_MAPPING_MAP
    gl_raw_mapping_checks();
#endif
#ifdef BQT_RETAINED_GL_FEEDBACK
    gl_retained_checks();
#endif
#ifdef BQT_BYTE_ITERATOR_BEGIN
    byte_iterator_checks();
#endif
#ifdef BQT_VOLUME_SET
    volume_data_checks();
#endif
#ifdef BQT_GL_COMPRESSED_READ
    gl_compressed_checks();
#endif
#ifdef BQT_PIXEL_OFFSET_UPLOAD
    gl_pixel_offset_checks();
#endif
#ifdef BQT_TEXT_DECODER_APPEND
    text_output_checks();
#endif
#ifdef BQT_PLATFORM_SURFACE
    native_platform_checks();
#endif
#ifdef BQT_READ_INT_ARRAY4
    fixed_array_checks();
#endif
#ifdef BQT_QTEST_FORMAT
    qtest_value_checks();
#endif
#ifdef BQT_RHI_ATTRIBUTE_AT
    rhi_snapshot_checks();
#endif
#ifdef BQT_SCXML_DATA_NAMES
    scxml_name_checks();
#endif
#ifdef BQT_RHI_FULL_UPDATE
    rhi_native_record_checks();
#endif
#ifdef BQT_FUTURE_NEW
    future_checks();
#endif
#ifdef BQT_FILE_DIALOG_GET_OPEN
    inout_pointer_checks();
#endif
#ifdef BQT_SHADER_MATRIX_2
    matrix_array_checks();
#endif
#ifdef BQT_GRAPHICS_FILTER_EQUAL
    graphics_filter_checks();
#endif

    auto empty = bendqt::sequence_value(0);
    auto absent = bendqt::BQT_READ_OPTIONAL_U64(&request, empty);
    assert(absent && !absent->has_value() && !request.error);
    bendqt::discard_value(empty);

    auto scalar = bendqt::sequence_value(1);
    scalar.items[0] = bendqt::wide_value(UINT64_MAX);
    auto present = bendqt::BQT_READ_OPTIONAL_U64(&request, scalar);
    assert(present && present->has_value() && **present == UINT64_MAX);
    bendqt::discard_value(scalar);

    auto excessive = bendqt::sequence_value(2);
    auto rejected = bendqt::BQT_READ_OPTIONAL_U64(&request, excessive);
    assert(!rejected && request.error == EINVAL);
    bendqt::discard_value(excessive);
    request = {};

    auto malformed = bendqt::sequence_value(1);
    malformed.items[0] = bendqt::string_value(QStringLiteral("wrong element"));
    assert(!bendqt::BQT_READ_OPTIONAL_U64(&request, malformed));
    assert(request.error == EINVAL);
    bendqt::discard_value(malformed);
    request = {};

    QList<QByteArray> values{QByteArray("first"), QByteArray("second")};
    bool threw = false;
    fail_after_allocations = 1;
    try {
        auto unexpected = bendqt::BQT_WRITE_BYTE_ARRAY_LIST(&request, values);
        bendqt::discard_value(unexpected);
    } catch (const std::bad_alloc &) {
        threw = true;
    }
    fail_after_allocations = -1;
    assert(threw);
    for (const auto &entry : bendqt::entries)
        assert(!entry.value); // The first copied handle was rolled back.
    assert(bqt_abi_stop() == 0);
    std::puts("QT612_NATIVE_CONVERSIONS_OK optional_absent=1 optional_present=1 cardinality=1 malformed_element=1 exception_rollback=1");
}
