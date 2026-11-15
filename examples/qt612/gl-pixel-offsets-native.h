#ifdef BQT_PIXEL_OFFSET_UPLOAD
static void gl_pixel_offset_checks()
{
    using namespace bendqt;
    QOpenGLContext context;
    QSurfaceFormat format;
    format.setVersion(4, 3); format.setProfile(QSurfaceFormat::CoreProfile);
    context.setFormat(format); assert(context.create());
    QOffscreenSurface surface;
    surface.setFormat(context.format()); surface.create();
    assert(context.makeCurrent(&surface));
    auto *gl = context.extraFunctions();
    BqtRequest request{};
    const auto functions = own(&request, new QOpenGLFunctions, BQT_GL_FUNCTIONS_TYPE);
    GLuint texture = 0, buffer = 0, framebuffer = 0;
    gl->glGenTextures(1, &texture); gl->glBindTexture(GL_TEXTURE_2D, texture);
    gl->glGenBuffers(1, &buffer); gl->glBindBuffer(GL_PIXEL_UNPACK_BUFFER, buffer);
    const unsigned char pixels[8] = {0, 0, 0, 0, 11, 22, 33, 255};
    auto upload = [&](uint64_t offset, GLenum type = GL_UNSIGNED_BYTE) {
        request = {}; request.self = functions;
        request.arguments[0].word = GL_TEXTURE_2D; request.arguments[2].word = GL_RGBA8;
        request.arguments[3].word = 1; request.arguments[4].word = 1;
        request.arguments[6].word = GL_RGBA; request.arguments[7].word = type;
        request.arguments[8] = wide_value(offset); BQT_PIXEL_OFFSET_UPLOAD(&request);
    };
    gl->glBufferData(GL_PIXEL_UNPACK_BUFFER, 7, pixels, GL_STATIC_DRAW);
    upload(4); assert(request.error == ERANGE);
    gl->glBufferData(GL_PIXEL_UNPACK_BUFFER, 8, pixels, GL_STATIC_DRAW);
    upload(1, GL_UNSIGNED_INT_8_8_8_8); assert(request.error == ERANGE);
    upload(4); assert(!request.error && gl->glGetError() == GL_NO_ERROR);
    gl->glBindBuffer(GL_PIXEL_UNPACK_BUFFER, 0);
    upload(4); assert(request.error == EINVAL);
    gl->glGenFramebuffers(1, &framebuffer); gl->glBindFramebuffer(GL_FRAMEBUFFER, framebuffer);
    gl->glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, texture, 0);
    assert(gl->glCheckFramebufferStatus(GL_FRAMEBUFFER) == GL_FRAMEBUFFER_COMPLETE);
    gl->glBindBuffer(GL_PIXEL_PACK_BUFFER, buffer);
    auto read = [&] {
        request = {}; request.self = functions;
        request.arguments[2].word = 1; request.arguments[3].word = 1;
        request.arguments[4].word = GL_RGBA; request.arguments[5].word = GL_UNSIGNED_BYTE;
        request.arguments[6] = wide_value(4); BQT_PIXEL_OFFSET_READ(&request);
    };
    read(); assert(!request.error && gl->glGetError() == GL_NO_ERROR);
    auto *mapped = static_cast<unsigned char *>(gl->glMapBufferRange(GL_PIXEL_PACK_BUFFER, 0, 8, GL_MAP_READ_BIT));
    assert(mapped && std::memcmp(mapped + 4, pixels + 4, 4) == 0);
    read(); assert(request.error == EBUSY);
    assert(gl->glUnmapBuffer(GL_PIXEL_PACK_BUFFER));
    gl->glBindBuffer(GL_PIXEL_PACK_BUFFER, 0);
    gl->glBindBuffer(GL_PIXEL_UNPACK_BUFFER, buffer);
    auto *native_texture = new QOpenGLTexture(QOpenGLTexture::Target2D);
    const auto texture_handle = own(&request, native_texture, BQT_TEXTURE_TYPE);
    native_texture->setSize(1, 1); native_texture->setFormat(QOpenGLTexture::RGBA8_UNorm);
    native_texture->allocateStorage();
    request = {}; request.self = texture_handle;
    request.arguments[0].word = QOpenGLTexture::RGBA;
    request.arguments[1].word = QOpenGLTexture::UInt8;
    request.arguments[2] = wide_value(4); BQT_PIXEL_OFFSET_TEXTURE(&request);
    assert(!request.error && gl->glGetError() == GL_NO_ERROR);
    gl->glBindBuffer(GL_PIXEL_UNPACK_BUFFER, 0);
    gl->glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, native_texture->textureId(), 0);
    unsigned char returned[4]{};
    gl->glReadPixels(0, 0, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, returned);
    assert(std::memcmp(returned, pixels + 4, 4) == 0);
    // Nondefault compressed pixel storage contributes to the checked PBO
    // extent, including the caller's starting byte offset.
    gl->glBindTexture(GL_TEXTURE_2D, texture);
    gl->glBindBuffer(GL_PIXEL_UNPACK_BUFFER, buffer);
    const unsigned char compressed[40]{};
    gl->glPixelStorei(0x9127, 4); gl->glPixelStorei(0x9128, 4);
    gl->glPixelStorei(0x9129, 1); gl->glPixelStorei(0x912A, 8);
    gl->glPixelStorei(GL_UNPACK_ROW_LENGTH, 8); gl->glPixelStorei(GL_UNPACK_SKIP_ROWS, 4);
    gl->glPixelStorei(GL_UNPACK_SKIP_PIXELS, 4);
    auto compressed_upload = [&] {
        request = {}; request.self = functions;
        request.arguments[0].word = GL_TEXTURE_2D; request.arguments[2].word = 0x83F0;
        request.arguments[3].word = 4; request.arguments[4].word = 4;
        request.arguments[6].word = 8; request.arguments[7] = wide_value(8);
        BQT_PIXEL_OFFSET_COMPRESSED(&request);
    };
    gl->glBufferData(GL_PIXEL_UNPACK_BUFFER, 39, compressed, GL_STATIC_DRAW);
    compressed_upload(); assert(request.error == ERANGE);
    gl->glBufferData(GL_PIXEL_UNPACK_BUFFER, 40, compressed, GL_STATIC_DRAW);
    compressed_upload(); assert(!request.error && gl->glGetError() == GL_NO_ERROR);
    gl->glBindBuffer(GL_PIXEL_UNPACK_BUFFER, 0);
    gl->glDeleteFramebuffers(1, &framebuffer); gl->glDeleteTextures(1, &texture); gl->glDeleteBuffers(1, &buffer);
    for (auto id : {functions, texture_handle}) {
        request = {}; request.self = id; destroy_object(&request); assert(!request.error);
    }
    std::puts("QT612_NATIVE_PIXEL_OFFSETS_OK upload=1 readback=1 extent=1 datum_alignment=1 mapped_rejected=1 missing_binding=1 qt_texture=1 compressed_layout=1");
}
#endif
