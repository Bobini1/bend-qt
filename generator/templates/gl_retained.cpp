struct NativeGLRetainedOutput {
    QPointer<QOpenGLContext> context = QOpenGLContext::currentContext();
    bool installed = false;
    GLenum mode;
    explicit NativeGLRetainedOutput(GLenum value) : mode(value) {}
};
struct NativeGLFeedbackBuffer : NativeGLRetainedOutput {
    std::vector<GLfloat> values;
    explicit NativeGLFeedbackBuffer(size_t count) : NativeGLRetainedOutput(GL_FEEDBACK), values(count) {}
};
struct NativeGLSelectionBuffer : NativeGLRetainedOutput {
    std::vector<GLuint> values;
    explicit NativeGLSelectionBuffer(size_t count) : NativeGLRetainedOutput(GL_SELECT), values(count) {}
};
struct RetainedGLOutputs {
    QOpenGLContext *context;
    std::shared_ptr<NativeGLFeedbackBuffer> feedback;
    std::shared_ptr<NativeGLSelectionBuffer> selection;
};
static std::vector<RetainedGLOutputs> &retained_gl_outputs()
{
    static auto *values = new std::vector<RetainedGLOutputs>;
    return *values;
}
static RetainedGLOutputs &retained_gl_output_slot(QOpenGLContext *context)
{
    auto &outputs = retained_gl_outputs();
    for (auto &item : outputs) if (item.context == context) return item;
    QObject::connect(context, &QObject::destroyed, [context] {
        auto &outputs = retained_gl_outputs();
        for (auto i = outputs.begin(); i != outputs.end(); ++i) if (i->context == context) {
            if (i->feedback) i->feedback->installed = false;
            if (i->selection) i->selection->installed = false;
            outputs.erase(i);
            break;
        }
    });
    outputs.push_back({context, {}, {}});
    return outputs.back();
}
static bool retained_gl_output_readable(BqtRequest *r, const NativeGLRetainedOutput &value)
{
    if (!value.installed || !value.context) return true;
    if (QOpenGLContext::currentContext() != value.context)
        return fail(r, EXDEV, "OpenGL feedback/selection output requires its own current context"), false;
    GLint mode = 0;
    value.context->functions()->glGetIntegerv(GL_RENDER_MODE, &mode);
    if (GLenum(mode) == value.mode)
        return fail(r, EBUSY, "Leave OpenGL feedback/selection mode before reading output"), false;
    return true;
}
