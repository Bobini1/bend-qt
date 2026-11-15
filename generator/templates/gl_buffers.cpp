// OpenGL memory extents follow the pinned Khronos registry and glPixelStore
// reference. GPU offsets are accepted only with a bound, size-checked buffer.
static bool gl_host_binding(BqtRequest *r, GLenum binding)
{
    if (!check_graphics_context(r)) return false;
    GLint buffer = 0;
    QOpenGLContext::currentContext()->functions()->glGetIntegerv(binding, &buffer);
    if (buffer) { fail(r, EBUSY, "Host bytes require the corresponding OpenGL buffer binding to be zero"); return false; }
    return true;
}

static uint64_t gl_component_bytes(GLenum type)
{
    switch (type) {
    case GL_BYTE: case GL_UNSIGNED_BYTE: return 1;
    case GL_SHORT: case GL_UNSIGNED_SHORT: case GL_HALF_FLOAT: case 0x8D61: return 2;
    case GL_INT: case GL_UNSIGNED_INT: case GL_FLOAT: case GL_FIXED: return 4;
    case GL_DOUBLE: return 8;
    default: return 0;
    }
}

static uint64_t gl_index_extent(BqtRequest *r, int64_t count, GLenum type)
{
    if (!gl_host_binding(r, GL_ELEMENT_ARRAY_BUFFER_BINDING)) return 0;
    if (type != GL_UNSIGNED_BYTE && type != GL_UNSIGNED_SHORT && type != GL_UNSIGNED_INT) {
        fail(r, EINVAL, "OpenGL index type must be unsigned byte, short, or int"); return 0;
    }
    if (count < 0) { fail(r, ERANGE, "OpenGL index count is negative"); return 0; }
    return uint64_t(count) * gl_component_bytes(type);
}

static const void *gl_checked_offset(BqtRequest *r, GLenum target, GLenum binding,
                                     uint64_t offset, uint64_t extent, uint64_t alignment)
{
    if (!check_graphics_context(r)) return nullptr;
    auto *context = QOpenGLContext::currentContext();
    GLint buffer = 0;
    context->functions()->glGetIntegerv(binding, &buffer);
    if (!buffer) { fail(r, EINVAL, "A GPU buffer offset requires a bound OpenGL buffer"); return nullptr; }
    GLint64 size = 0;
    const auto version = context->format().version();
    const bool wide_size = context->isOpenGLES() ? version.first >= 3
        : (version.first > 3 || (version.first == 3 && version.second >= 2));
    if (wide_size) context->extraFunctions()->glGetBufferParameteri64v(target, GL_BUFFER_SIZE, &size);
    else { GLint narrow = 0; context->functions()->glGetBufferParameteriv(target, GL_BUFFER_SIZE, &narrow); size = narrow; }
    if (size < 0 || offset > uint64_t(size) || extent > uint64_t(size) - offset || offset % alignment) {
        fail(r, ERANGE, "GPU buffer offset or extent is outside its allocated storage"); return nullptr;
    }
    return reinterpret_cast<const void *>(uintptr_t(offset));
}

static uint64_t gl_pixel_type_alignment(GLenum type)
{
    switch (type) {
    case GL_BITMAP: case GL_UNSIGNED_BYTE_3_3_2: case GL_UNSIGNED_BYTE_2_3_3_REV: return 1;
    case GL_UNSIGNED_SHORT_5_6_5: case GL_UNSIGNED_SHORT_5_6_5_REV:
    case GL_UNSIGNED_SHORT_4_4_4_4: case GL_UNSIGNED_SHORT_4_4_4_4_REV:
    case GL_UNSIGNED_SHORT_5_5_5_1: case GL_UNSIGNED_SHORT_1_5_5_5_REV: return 2;
    case GL_UNSIGNED_INT_8_8_8_8: case GL_UNSIGNED_INT_8_8_8_8_REV:
    case GL_UNSIGNED_INT_10_10_10_2: case GL_UNSIGNED_INT_2_10_10_10_REV:
    case GL_UNSIGNED_INT_10F_11F_11F_REV: case GL_UNSIGNED_INT_5_9_9_9_REV:
    case GL_UNSIGNED_INT_24_8: return 4;
    case GL_FLOAT_32_UNSIGNED_INT_24_8_REV: return 8;
    default: return gl_component_bytes(type);
    }
}

static void *gl_pixel_offset(BqtRequest *r, GLenum target, GLenum binding,
                              uint64_t offset, uint64_t extent, uint64_t alignment)
{
    if (!alignment) { fail(r, EINVAL, "Pixel buffer type has no native datum alignment"); return nullptr; }
    const auto *pointer = gl_checked_offset(r, target, binding, offset, extent, alignment);
    if (r->error) return nullptr;
    auto *context = QOpenGLContext::currentContext();
    GLint mapped = 0;
    context->functions()->glGetBufferParameteriv(target, GL_BUFFER_MAPPED, &mapped);
    if (mapped) {
        GLint flags = 0;
        const auto version = context->format().version();
        if (version.first >= 3) context->functions()->glGetBufferParameteriv(target, GL_BUFFER_ACCESS_FLAGS, &flags);
        if (!(flags & 0x0040)) { // GL_MAP_PERSISTENT_BIT permits server access.
            fail(r, EBUSY, "Unmap a nonpersistent pixel buffer before native transfer"); return nullptr;
        }
    }
    return const_cast<void *>(pointer);
}

struct GlPixelLayout { GLint alignment, row_length, skip_rows, skip_pixels, image_height, skip_images; };

static uint64_t gl_compressed_extent(BqtRequest *r, bool unpack, int dimensions,
                                     int64_t width, int64_t height, int64_t depth,
                                     int64_t serialized_size, const GlPixelLayout *provided = nullptr)
{
    if (!check_graphics_context(r)) return 0;
    if (width < 0 || height < 0 || depth < 0 || serialized_size < 0) {
        fail(r, ERANGE, "Compressed texture dimensions and size cannot be negative"); return 0;
    }
    auto *context = QOpenGLContext::currentContext();
    const auto version = context->format().version();
    GLint block[4]{};
    if ((!context->isOpenGLES() && (version.first > 4 || (version.first == 4 && version.second >= 2)))
        || context->hasExtension(QByteArrayLiteral("GL_ARB_compressed_texture_pixel_storage"))) {
        const GLenum first = unpack ? 0x9127 : 0x912B;
        for (int i = 0; i < 4; ++i) context->functions()->glGetIntegerv(first + GLenum(i), block + i);
    }
    if (!block[0] || !block[3]) return uint64_t(serialized_size);
    for (auto value : block) if (value < 0) { fail(r, EINVAL, "Invalid compressed pixel block layout"); return 0; }
    if (!width || !height || !depth) return 0;
    const uint64_t limit = uint64_t(std::numeric_limits<qsizetype>::max());
    auto multiply = [r, limit](uint64_t a, uint64_t b, uint64_t &out) {
        if (a && b > limit / a) { fail(r, ERANGE, "Compressed pixel extent overflows the native range"); return false; }
        out = a * b; return true;
    };
    auto add = [r, limit](uint64_t a, uint64_t b, uint64_t &out) {
        if (a > limit || b > limit - a) { fail(r, ERANGE, "Compressed pixel extent overflows the native range"); return false; }
        out = a + b; return true;
    };
    auto ceil_div = [](uint64_t count, uint64_t divisor) { return count / divisor + uint64_t(count % divisor != 0); };
    const uint64_t bytes = uint64_t(block[3]), nx = ceil_div(uint64_t(width), uint64_t(block[0]));
    const bool rows_known = dimensions < 2 || block[1];
    const bool images_known = dimensions < 3 || block[2];
    uint64_t ny = dimensions >= 2 && block[1] ? ceil_div(uint64_t(height), uint64_t(block[1])) : 1;
    uint64_t nz = dimensions >= 3 && block[2] ? ceil_div(uint64_t(depth), uint64_t(block[2])) : 1;
    uint64_t known_size = 0;
    if (!multiply(nx, ny, known_size) || !multiply(known_size, nz, known_size) || !multiply(known_size, bytes, known_size)) return 0;
    if (!known_size || uint64_t(serialized_size) % known_size) {
        fail(r, EINVAL, "Compressed byte size disagrees with its block dimensions"); return 0;
    }
    // A zero height/depth block field disables the corresponding pixel-store
    // selectors. The serialized size still determines the remaining packed
    // block count, without guessing the compression format's natural blocks.
    const auto remaining = uint64_t(serialized_size) / known_size;
    if (!rows_known) ny = remaining;
    else if (!images_known) nz = remaining;
    else if (remaining != 1) { fail(r, EINVAL, "Compressed byte size disagrees with its block dimensions"); return 0; }
    if (!ny || !nz) return 0;
    GlPixelLayout layout{1, 0, 0, 0, 0, 0};
    if (provided) layout = *provided;
    else {
        auto *functions = context->functions();
        functions->glGetIntegerv(unpack ? GL_UNPACK_ROW_LENGTH : GL_PACK_ROW_LENGTH, &layout.row_length);
        functions->glGetIntegerv(unpack ? GL_UNPACK_SKIP_PIXELS : GL_PACK_SKIP_PIXELS, &layout.skip_pixels);
        if (dimensions >= 2 && block[1]) {
            functions->glGetIntegerv(unpack ? GL_UNPACK_SKIP_ROWS : GL_PACK_SKIP_ROWS, &layout.skip_rows);
            functions->glGetIntegerv(unpack ? GL_UNPACK_IMAGE_HEIGHT : GL_PACK_IMAGE_HEIGHT, &layout.image_height);
        }
        if (dimensions >= 3 && block[2]) functions->glGetIntegerv(unpack ? GL_UNPACK_SKIP_IMAGES : GL_PACK_SKIP_IMAGES, &layout.skip_images);
    }
    if (layout.row_length < 0 || layout.skip_pixels < 0 || layout.skip_rows < 0 || layout.image_height < 0 || layout.skip_images < 0 ||
        layout.skip_pixels % block[0] || (dimensions >= 2 && block[1] && layout.skip_rows % block[1]) ||
        (dimensions >= 3 && block[2] && layout.skip_images % block[2])) {
        fail(r, EINVAL, "Compressed pixel skips must align to whole blocks"); return 0;
    }
    const uint64_t row_blocks = layout.row_length ? ceil_div(uint64_t(layout.row_length), uint64_t(block[0])) : nx;
    const uint64_t image_rows = dimensions >= 2 && block[1] && layout.image_height ? ceil_div(uint64_t(layout.image_height), uint64_t(block[1])) : ny;
    const uint64_t skip_rows = dimensions >= 2 && block[1] ? uint64_t(layout.skip_rows / block[1]) : 0;
    const uint64_t skip_images = dimensions >= 3 && block[2] ? uint64_t(layout.skip_images / block[2]) : 0;
    uint64_t row_bytes = 0, image_bytes = 0, result = 0, tail = 0;
    if (!multiply(row_blocks, bytes, row_bytes) || !multiply(row_bytes, image_rows, image_bytes) ||
        !multiply(skip_images + nz - 1, image_bytes, result) || !multiply(skip_rows + ny - 1, row_bytes, tail) ||
        !add(result, tail, result) || !multiply(uint64_t(layout.skip_pixels / block[0]) + nx, bytes, tail) ||
        !add(result, tail, result)) return 0;
    return result;
}

static uint64_t gl_pixel_extent(BqtRequest *r, bool unpack, bool volume, int64_t width, int64_t height,
                                int64_t depth, GLenum format, GLenum type, const GlPixelLayout *provided = nullptr)
{
    if (!check_graphics_context(r)) return 0;
    if (width < 0 || height < 0 || depth < 0) { fail(r, ERANGE, "Pixel dimensions cannot be negative"); return 0; }
    if (!width || !height || !depth) return 0;
    uint64_t components = 0;
    switch (format) {
    case GL_RED: case GL_RED_INTEGER: case GL_DEPTH_COMPONENT: case GL_STENCIL_INDEX:
    case GL_ALPHA: case GL_LUMINANCE: case GL_COLOR_INDEX: components = 1; break;
    case GL_RG: case GL_RG_INTEGER: case GL_LUMINANCE_ALPHA: case GL_DEPTH_STENCIL: components = 2; break;
    case GL_RGB: case GL_RGB_INTEGER: case GL_BGR: case GL_BGR_INTEGER: components = 3; break;
    case GL_RGBA: case GL_RGBA_INTEGER: case GL_BGRA: case GL_BGRA_INTEGER: components = 4; break;
    default: fail(r, ENOTSUP, "Pixel format has no audited storage representation"); return 0;
    }
    uint64_t bits = 0;
    switch (type) {
    case GL_BITMAP: bits = 1; break;
    case GL_UNSIGNED_BYTE_3_3_2: case GL_UNSIGNED_BYTE_2_3_3_REV: bits = 8; break;
    case GL_UNSIGNED_SHORT_5_6_5: case GL_UNSIGNED_SHORT_5_6_5_REV:
    case GL_UNSIGNED_SHORT_4_4_4_4: case GL_UNSIGNED_SHORT_4_4_4_4_REV:
    case GL_UNSIGNED_SHORT_5_5_5_1: case GL_UNSIGNED_SHORT_1_5_5_5_REV: bits = 16; break;
    case GL_UNSIGNED_INT_8_8_8_8: case GL_UNSIGNED_INT_8_8_8_8_REV:
    case GL_UNSIGNED_INT_10_10_10_2: case GL_UNSIGNED_INT_2_10_10_10_REV:
    case GL_UNSIGNED_INT_10F_11F_11F_REV: case GL_UNSIGNED_INT_5_9_9_9_REV:
    case GL_UNSIGNED_INT_24_8: bits = 32; break;
    case GL_FLOAT_32_UNSIGNED_INT_24_8_REV: bits = 64; break;
    default: bits = gl_component_bytes(type) * components * 8; break;
    }
    if (!bits) { fail(r, ENOTSUP, "Pixel type has no audited storage representation"); return 0; }
    auto *context = QOpenGLContext::currentContext();
    auto *functions = context->functions();
    GLint alignment = 0, row_length = 0, skip_rows = 0, skip_pixels = 0;
    GLint image_height = 0, skip_images = 0;
    if (provided) {
        alignment = provided->alignment; row_length = provided->row_length;
        skip_rows = provided->skip_rows; skip_pixels = provided->skip_pixels;
        if (volume) { image_height = provided->image_height; skip_images = provided->skip_images; }
    } else {
    functions->glGetIntegerv(unpack ? GL_UNPACK_ALIGNMENT : GL_PACK_ALIGNMENT, &alignment);
    const bool rows = !context->isOpenGLES() || context->format().majorVersion() >= 3
        || (unpack && context->hasExtension(QByteArrayLiteral("GL_EXT_unpack_subimage")));
    if (rows) {
        functions->glGetIntegerv(unpack ? GL_UNPACK_ROW_LENGTH : GL_PACK_ROW_LENGTH, &row_length);
        functions->glGetIntegerv(unpack ? GL_UNPACK_SKIP_ROWS : GL_PACK_SKIP_ROWS, &skip_rows);
        functions->glGetIntegerv(unpack ? GL_UNPACK_SKIP_PIXELS : GL_PACK_SKIP_PIXELS, &skip_pixels);
    }
    if (volume && (!context->isOpenGLES() || context->format().majorVersion() >= 3
                   || (unpack && context->hasExtension(QByteArrayLiteral("GL_OES_texture_3D"))))) {
        functions->glGetIntegerv(unpack ? GL_UNPACK_IMAGE_HEIGHT : GL_PACK_IMAGE_HEIGHT, &image_height);
        functions->glGetIntegerv(unpack ? GL_UNPACK_SKIP_IMAGES : GL_PACK_SKIP_IMAGES, &skip_images);
    }
    }
    if ((alignment != 1 && alignment != 2 && alignment != 4 && alignment != 8)
        || row_length < 0 || image_height < 0 || skip_rows < 0 || skip_pixels < 0 || skip_images < 0) {
        fail(r, EINVAL, "OpenGL reported an invalid pixel storage layout"); return 0;
    }
    const uint64_t limit = uint64_t(std::numeric_limits<qsizetype>::max());
    auto multiply = [r, limit](uint64_t a, uint64_t b, uint64_t &out) {
        if (a && b > limit / a) { fail(r, ERANGE, "Pixel storage extent overflows the native range"); return false; }
        out = a * b; return true;
    };
    auto add = [r, limit](uint64_t a, uint64_t b, uint64_t &out) {
        if (a > limit || b > limit - a) { fail(r, ERANGE, "Pixel storage extent overflows the native range"); return false; }
        out = a + b; return true;
    };
    uint64_t row_bits = 0, tail_bits = 0, image_bytes = 0, result = 0, skip_bytes = 0;
    if (!multiply(uint64_t(row_length ? row_length : width), bits, row_bits)
        || !multiply(uint64_t(skip_pixels) + uint64_t(width), bits, tail_bits)) return 0;
    const auto row_bytes = (row_bits + 7) / 8;
    const auto stride = (row_bytes + uint64_t(alignment) - 1) / uint64_t(alignment) * uint64_t(alignment);
    if (!multiply(stride, uint64_t(image_height ? image_height : height), image_bytes)
        || !multiply(uint64_t(skip_images) + uint64_t(depth - 1), image_bytes, result)
        || !multiply(uint64_t(skip_rows) + uint64_t(height - 1), stride, skip_bytes)
        || !add(result, skip_bytes, result) || !add(result, (tail_bits + 7) / 8, result)) return 0;
    return result;
}
