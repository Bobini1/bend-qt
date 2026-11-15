namespace NativeCursorGuards {
struct Guard { bool active = false; };
static void delete_guard(void *pointer) { delete static_cast<Guard *>(pointer); }
static Guard *get_guard(BqtRequest *r, uint32_t id, bool pin = true) {
    auto *record = entry(id);
    if (!record || record->destroy != delete_guard) {
        fail(r, ESTALE, "The override cursor guard has expired"); return nullptr;
    }
    if (record->destroying) { fail(r, EBUSY, "The cursor guard is being destroyed"); return nullptr; }
    if (QThread::currentThread() != main_thread) {
        fail(r, EXDEV, "The override cursor stack belongs to the GUI thread"); return nullptr;
    }
    if (pin && native_call_scope) native_call_scope->pin(r, id);
    return r->error ? nullptr : static_cast<Guard *>(record->value);
}
static bool ready(BqtRequest *r, uint32_t id) {
    auto *record = entry(id);
    if (!record || record->destroy != delete_guard) return true;
    auto *guard = static_cast<Guard *>(record->value);
    if (!guard->active) return true;
    NativeCallScope scope;
    scope.pin(r, id);
    if (r->error || !invalidate_cursor_value_views(r)) return false;
    // A platform cursor update can run Bend handlers. Mark this restoration
    // before calling Qt so a reentrant restore cannot pop the stack twice.
    guard->active = false;
    QGuiApplication::restoreOverrideCursor();
    return !r->error;
}
static bool defer_release(BqtRequest *r, uint32_t id) {
    auto *record = entry(id);
    if (!record || record->destroy != delete_guard || !static_cast<Guard *>(record->value)->active) return false;
    BqtRequest probe{};
    if (invalidate_cursor_value_views(&probe)) return false;
    if (probe.error != EBUSY) { fail(r, probe.error, probe.message); return true; }
    // Keep the resource pending until the enclosing native value-view call
    // unwinds. The common collector retries through ready() before deletion.
    record = entry(id);
    if (record) record->pending_release = true;
    schedule_collection();
    return true;
}
static bool create(BqtRequest *r) {
    NativeCallScope scope;
    auto *cursor = get<QCursor>(r, r->arguments[0].word, @QCursor@, false, false);
    if (r->error) return true;
    QCursor copy(*cursor);
    if (!invalidate_cursor_value_views(r)) return true;
    auto *guard = new Guard;
    try { r->result.word = insert(r, guard, nullptr, 0, delete_guard, true); }
    catch (...) {
        for (uint32_t i = 1; i < capacity; ++i)
            if (entries[i].value == guard) invalidate(token(i, entries[i].generation));
        delete guard;
        throw;
    }
    r->result.owned_handle = r->result.word;
    if (r->error || !r->result.word) return true;
    scope.pin(r, r->result.word);
    if (r->error) return true;
    QGuiApplication::setOverrideCursor(copy);
    guard->active = true;
    return true;
}
static bool restore(BqtRequest *r) {
    NativeCallScope scope;
    if (get_guard(r, r->self)) ready(r, r->self);
    return true;
}
static bool active(BqtRequest *r) {
    NativeCallScope scope;
    if (auto *guard = get_guard(r, r->self)) r->result.word = guard->active;
    return true;
}
static bool destroy(BqtRequest *r, bool release) {
    if (!get_guard(r, r->self, false)) return true;
    return release ? release_object(r) : destroy_object(r);
}
} // namespace NativeCursorGuards
static bool cursor_guard_cleanup_ready(BqtRequest *r, uint32_t id) { return NativeCursorGuards::ready(r, id); }
static bool cursor_guard_defer_release(BqtRequest *r, uint32_t id) { return NativeCursorGuards::defer_release(r, id); }
