#ifdef BQT_GL_COMPRESSED_READ
static void gl_compressed_checks()
{
    using namespace bendqt;
    QOpenGLContext context;
    QSurfaceFormat format;
    format.setVersion(4, 3); format.setProfile(QSurfaceFormat::CoreProfile);
    context.setFormat(format);
    assert(context.create());
    QOffscreenSurface surface;
    surface.setFormat(context.format()); surface.create();
    assert(context.makeCurrent(&surface));
    assert(context.hasExtension("GL_EXT_texture_compression_s3tc") || context.hasExtension("GL_EXT_texture_compression_dxt1"));
    auto *gl = context.functions();
    GLuint texture = 0;
    gl->glGenTextures(1, &texture); gl->glBindTexture(GL_TEXTURE_2D, texture);
    BqtRequest request{};
    const auto functions = own(&request, new QOpenGLFunctions, BQT_GL_FUNCTIONS_TYPE);
    const auto desktop = own(&request, new QOpenGLFunctions_3_2_Core, BQT_RAW_MAPPING_FUNCTIONS_TYPE);
    auto *input = new QByteArray(31, char(0));
    const auto source = own(&request, input, BQT_GL_BYTE_ARRAY_TYPE);
    auto *output = new QByteArray(31, char(0));
    const auto target = own(&request, output, BQT_GL_BYTE_ARRAY_TYPE);
    auto layout = [&](bool unpack, int block_height) {
        const GLenum first = unpack ? 0x9127 : 0x912B;
        gl->glPixelStorei(first, 4); gl->glPixelStorei(first + 1, block_height);
        gl->glPixelStorei(first + 2, 1); gl->glPixelStorei(first + 3, 8);
        gl->glPixelStorei(unpack ? GL_UNPACK_ROW_LENGTH : GL_PACK_ROW_LENGTH, 8);
        gl->glPixelStorei(unpack ? GL_UNPACK_SKIP_PIXELS : GL_PACK_SKIP_PIXELS, 4);
        gl->glPixelStorei(unpack ? GL_UNPACK_SKIP_ROWS : GL_PACK_SKIP_ROWS, 4);
    };
    auto upload = [&](int width, int height, int count) {
        request = {}; request.self = functions;
        request.arguments[0].word = GL_TEXTURE_2D; request.arguments[1].word = 0;
        request.arguments[2].word = 0x83F0; // GL_COMPRESSED_RGB_S3TC_DXT1_EXT
        request.arguments[3].word = width; request.arguments[4].word = height;
        request.arguments[5].word = 0; request.arguments[6].word = count;
        request.arguments[7].word = source;
        BQT_GL_COMPRESSED_UPLOAD(&request);
    };
    layout(true, 4);
    upload(4, 4, 8);
    assert(request.error == ERANGE);
    input->resize(32);
    for (int i = 0; i < 8; ++i) (*input)[24 + i] = char(i + 1);
    upload(4, 4, 8);
    assert(!request.error && gl->glGetError() == GL_NO_ERROR);
    layout(false, 4);
    auto read = [&] {
        request = {}; request.self = desktop;
        request.arguments[0].word = GL_TEXTURE_2D; request.arguments[1].word = 0;
        request.arguments[2].word = target; BQT_GL_COMPRESSED_READ(&request);
    };
    read(); assert(request.error == ERANGE);
    output->resize(32); read();
    assert(!request.error && gl->glGetError() == GL_NO_ERROR);
    assert(output->mid(24, 8) == input->mid(24, 8));
    // Width/size alone enable row stride and skipped blocks. A zero block
    // height disables skipped rows; serialized byte count supplies row count.
    layout(true, 0);
    gl->glPixelStorei(GL_UNPACK_ROW_LENGTH, 12);
    input->resize(47);
    upload(8, 8, 32); assert(request.error == ERANGE);
    input->resize(48);
    for (int i = 0; i < 16; ++i) { (*input)[8 + i] = char(i); (*input)[32 + i] = char(i + 16); }
    upload(8, 8, 32);
    assert(!request.error && gl->glGetError() == GL_NO_ERROR);
    for (GLenum p = 0x912B; p < 0x912F; ++p) gl->glPixelStorei(p, 0);
    output->resize(32); read();
    assert(!request.error && *output == input->mid(8, 16) + input->mid(32, 16));
    gl->glPixelStorei(GL_UNPACK_SKIP_PIXELS, 1);
    upload(8, 8, 32); assert(request.error == EINVAL);
    gl->glDeleteTextures(1, &texture);
    for (auto id : {source, target, functions, desktop}) {
        request = {}; request.self = id; destroy_object(&request); assert(!request.error);
    }
    std::puts("QT612_NATIVE_GL_COMPRESSED_OK block_layout=1 unpack_extent=1 pack_extent=1 native_roundtrip=1 partial_block_state=1 skip_alignment=1");
}
#endif
