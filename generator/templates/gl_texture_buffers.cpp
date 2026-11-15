static uint64_t gl_texture_pixel_extent(BqtRequest *r, QOpenGLTexture *texture, bool partial,
                                        int width, int height, int depth, int mip, int layers,
                                        GLenum format, GLenum type, const GlPixelLayout *options, int64_t compressed_size = -1)
{
    if (!check_graphics_context(r)) return 0;
    if (!texture->isCreated()) { fail(r, EINVAL, "Texture upload requires a created texture"); return 0; }
    const auto target = texture->target();
    if (target == QOpenGLTexture::TargetRectangle) mip = 0;
    if (mip < 0 || mip >= 31) { fail(r, ERANGE, "Texture mip level is outside the native shift range"); return 0; }
    if (!partial) {
        width = std::max(1, texture->width() >> mip);
        height = std::max(1, texture->height() >> mip);
        depth = std::max(1, texture->depth() >> mip);
    }
    bool volume = false;
    switch (target) {
    case QOpenGLTexture::Target1D: height = depth = 1; break;
    case QOpenGLTexture::Target1DArray: height = layers; depth = 1; break;
    case QOpenGLTexture::Target2D: case QOpenGLTexture::TargetCubeMap:
    case QOpenGLTexture::TargetRectangle: depth = 1; break;
    case QOpenGLTexture::Target2DArray: case QOpenGLTexture::TargetCubeMapArray:
        depth = layers; volume = true; break;
    case QOpenGLTexture::Target3D: volume = true; break;
    default: fail(r, EINVAL, "Texture target cannot accept host pixel data"); return 0;
    }
    if (compressed_size >= 0)
        return gl_compressed_extent(r, true, target == QOpenGLTexture::Target1D ? 1 : volume ? 3 : 2,
                                    width, height, depth, compressed_size, options);
    return gl_pixel_extent(r, true, volume, width, height, depth, format, type, options);
}
