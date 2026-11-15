static uint64_t gl_texture_readback_extent(BqtRequest *r, GLenum target, GLint level,
                                            GLenum format, GLenum type, bool compressed)
{
    if (!check_graphics_context(r)) return 0;
    const auto query = reinterpret_cast<void (*)(GLenum, GLint, GLenum, GLint *)>(
        QOpenGLContext::currentContext()->getProcAddress("glGetTexLevelParameteriv"));
    if (!query) { fail(r, ENOTSUP, "OpenGL context has no texture-level query entry point"); return 0; }
    GLint width = 0, height = 1, depth = 1;
    query(target, level, GL_TEXTURE_WIDTH, &width);
    const bool volume = target == GL_TEXTURE_3D || target == GL_TEXTURE_2D_ARRAY || target == GL_TEXTURE_CUBE_MAP_ARRAY;
    if (target != GL_TEXTURE_1D) query(target, level, GL_TEXTURE_HEIGHT, &height);
    if (volume) query(target, level, GL_TEXTURE_DEPTH, &depth);
    if (compressed) {
        GLint size = 0;
        query(target, level, GL_TEXTURE_COMPRESSED_IMAGE_SIZE, &size);
        return gl_compressed_extent(r, false, target == GL_TEXTURE_1D ? 1 : volume ? 3 : 2, width, height, depth, size);
    }
    return gl_pixel_extent(r, false, volume, width, height, depth, format, type);
}

static uint64_t gl_legacy_readback_extent(BqtRequest *r, int family, GLenum target,
                                         GLenum format, GLenum type, int axis)
{
    if (!check_graphics_context(r)) return 0;
    const char *entry_point = family == 0 ? "glGetColorTableParameteriv" :
        family == 2 ? "glGetHistogramParameteriv" : "glGetConvolutionParameteriv";
    const auto query = reinterpret_cast<void (*)(GLenum, GLenum, GLint *)>(
        QOpenGLContext::currentContext()->getProcAddress(entry_point));
    if (!query && family != 3) { fail(r, ENOTSUP, "OpenGL context has no imaging query entry point"); return 0; }
    GLint width = 0, height = 1;
    switch (family) {
    case 0: query(target, GL_COLOR_TABLE_WIDTH, &width); break;
    case 1:
        query(target, GL_CONVOLUTION_WIDTH, &width);
        if (target == GL_CONVOLUTION_2D) query(target, GL_CONVOLUTION_HEIGHT, &height);
        break;
    case 2: query(target, GL_HISTOGRAM_WIDTH, &width); break;
    case 3: width = 2; break;
    case 4: query(target, axis ? GL_CONVOLUTION_HEIGHT : GL_CONVOLUTION_WIDTH, &width); break;
    default: fail(r, EINVAL, "Unknown OpenGL imaging query"); return 0;
    }
    return gl_pixel_extent(r, false, false, width, height, 1, format, type);
}
