static std::pair<int, int> gl_evaluator_shape(BqtRequest *r, GLenum target)
{
    switch (target) {
    case GL_MAP1_INDEX: case GL_MAP1_TEXTURE_COORD_1: return {1, 1};
    case GL_MAP1_TEXTURE_COORD_2: return {1, 2};
    case GL_MAP1_NORMAL: case GL_MAP1_TEXTURE_COORD_3: case GL_MAP1_VERTEX_3: return {1, 3};
    case GL_MAP1_COLOR_4: case GL_MAP1_TEXTURE_COORD_4: case GL_MAP1_VERTEX_4: return {1, 4};
    case GL_MAP2_INDEX: case GL_MAP2_TEXTURE_COORD_1: return {2, 1};
    case GL_MAP2_TEXTURE_COORD_2: return {2, 2};
    case GL_MAP2_NORMAL: case GL_MAP2_TEXTURE_COORD_3: case GL_MAP2_VERTEX_3: return {2, 3};
    case GL_MAP2_COLOR_4: case GL_MAP2_TEXTURE_COORD_4: case GL_MAP2_VERTEX_4: return {2, 4};
    default: fail(r, EINVAL, "Unknown OpenGL evaluator target"); return {0, 0};
    }
}

static uint64_t gl_evaluator_input_extent(BqtRequest *r, GLenum target,
                                         int64_t ustride, int64_t uorder, int64_t vstride, int64_t vorder)
{
    const auto [dimension, components] = gl_evaluator_shape(r, target);
    if (r->error) return 0;
    if (uorder < 1 || ustride < components || (dimension == 2 && (vorder < 1 || vstride < components))) {
        fail(r, ERANGE, "OpenGL evaluator order or stride is invalid"); return 0;
    }
    // Native stride/order are GLint. Their largest combined extent fits U64;
    // the actual QList capacity check still rejects values outside qsizetype.
    return uint64_t(uorder - 1) * uint64_t(ustride) + uint64_t(components)
        + (dimension == 2 ? uint64_t(vorder - 1) * uint64_t(vstride) : 0);
}

static uint64_t gl_evaluator_result_extent(BqtRequest *r, GLenum target, GLenum query)
{
    const auto [dimension, components] = gl_evaluator_shape(r, target);
    if (r->error) return 0;
    if (query == GL_ORDER) return uint64_t(dimension);
    if (query == GL_DOMAIN) return uint64_t(dimension * 2);
    if (query != GL_COEFF) { fail(r, EINVAL, "Unknown OpenGL evaluator query"); return 0; }
    const auto get = reinterpret_cast<void (*)(GLenum, GLenum, GLint *)>(
        QOpenGLContext::currentContext()->getProcAddress("glGetMapiv"));
    if (!get) { fail(r, ENOTSUP, "OpenGL context has no evaluator query entry point"); return 0; }
    GLint orders[2] = {0, 1};
    get(target, GL_ORDER, orders);
    if (orders[0] < 1 || orders[1] < 1) { fail(r, ERANGE, "OpenGL evaluator has an invalid native order"); return 0; }
    return uint64_t(components) * uint64_t(orders[0]) * uint64_t(orders[1]);
}
