static constexpr uint32_t native_function_slot = 0xffffffe5;

static bool native_function_owner_mutable(BqtRequest *r, uint32_t owner)
{
    for (const auto &edge : retentions)
        if (edge.owner && edge.slot == native_function_slot && edge.target == owner)
            return fail(r, EBUSY, "Native function capabilities still retain this library"), false;
    return true;
}

static bool native_function_ready(BqtRequest *r, const NativeFunction &value)
{
    auto *owner = entry(value.owner);
    if (!owner || !owner->object) return fail(r, ESTALE, "Native function owner was destroyed"), false;
    if (!value.value) return true;
    if (auto *library = qobject_cast<QLibrary *>(owner->object); library && !library->isLoaded())
        return fail(r, ESTALE, "Native function library was unloaded"), false;
    if (auto *context = qobject_cast<QOpenGLContext *>(owner->object)) {
        auto *current = QOpenGLContext::currentContext();
        if (!context->isValid() || !current || (current != context && !QOpenGLContext::areSharing(current, context)))
            return fail(r, EXDEV, "Native OpenGL function requires its current or sharing context"), false;
    }
    return true;
}

static uint32_t own_native_function(BqtRequest *r, QFunctionPointer pointer)
{
    // QLibrary's static resolve overloads keep the library loaded until exit.
    // Platform functions likewise remain tied to the package's QApplication.
    const auto owner = r->self ? r->self : borrow(r, application, @OBJECT_TYPE@);
    if (!owner || !entry(owner) || !entry(owner)->object) {
        if (!r->error) fail(r, ESTALE, "Native function needs an observable owner");
        return 0;
    }
    const auto id = own(r, new NativeFunction{pointer, owner}, @FUNCTION_TYPE@);
    if (!id) return 0;
    BqtRequest relationship{};
    relationship.self = id;
    const auto index = prepare_retention(&relationship, native_function_slot, 0, owner);
    if (relationship.error) {
        auto *value = static_cast<NativeFunction *>(entry(id)->value);
        invalidate(id); delete value;
        fail(r, relationship.error, relationship.message);
        return 0;
    }
    commit_retention(index, id, native_function_slot, 0, owner, nullptr);
    return id;
}
