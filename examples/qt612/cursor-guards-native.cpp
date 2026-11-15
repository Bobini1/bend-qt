// Reuse the minimal registry contract, then exercise the actual cursor helper
// against the real Qt GUI cursor stack. Complete Action scopes are separate.
#include <QtGui/QGuiApplication>
#include <QtGui/QCursor>
#define main mutex_locker_fixture_main
#include "mutex-lockers-native.cpp"
#undef main

static bool cursor_view_active = false;
static unsigned collections = 0;
static bool invalidate_cursor_value_views(BqtRequest *r) {
    if (cursor_view_active) { fail(r, EBUSY, "Active native cursor view"); return false; }
    return true;
}
static void schedule_collection() { ++collections; }

#include "cursor-guards-runtime.h"

static uint32_t push(uint32_t cursor) {
    BqtRequest request{}; request.arguments[0].word = cursor;
    NativeCursorGuards::create(&request);
    assert(!request.error && request.result.word == request.result.owned_handle);
    return request.result.word;
}
int main(int argc, char **argv) {
    QGuiApplication app(argc, argv); main_thread = QThread::currentThread();
    cleanup_hook = cursor_guard_cleanup_ready;
    defer_hook = cursor_guard_defer_release;
    assert(!QGuiApplication::overrideCursor());
    QCursor wait(Qt::WaitCursor), busy(Qt::BusyCursor);
    const auto wait_id = insert(nullptr, &wait, nullptr, 3, nullptr, false);
    const auto busy_id = insert(nullptr, &busy, nullptr, 3, nullptr, false);
    const auto outer = push(wait_id);
    assert(QGuiApplication::overrideCursor()->shape() == Qt::WaitCursor);
    const auto inner = push(busy_id);
    assert(QGuiApplication::overrideCursor()->shape() == Qt::BusyCursor);
    BqtRequest request{}; request.self = inner;
    NativeCursorGuards::restore(&request); assert(!request.error);
    NativeCursorGuards::restore(&request); assert(!request.error);
    assert(QGuiApplication::overrideCursor()->shape() == Qt::WaitCursor);
    NativeCursorGuards::destroy(&request, true); assert(!request.error);
    request = {}; request.self = outer;
    QGuiApplication::changeOverrideCursor(busy);
    NativeCursorGuards::destroy(&request, false); assert(!request.error);
    assert(!QGuiApplication::overrideCursor());
    NativeCursorGuards::active(&request); assert(request.error == ESTALE);
    const auto pending = push(wait_id);
    cursor_view_active = true;
    request = {}; request.self = pending;
    NativeCursorGuards::restore(&request); assert(request.error == EBUSY);
    request = {}; request.self = pending;
    NativeCursorGuards::destroy(&request, true);
    assert(!request.error && entry(pending)->pending_release && collections);
    assert(QGuiApplication::overrideCursor()->shape() == Qt::WaitCursor);
    request = {}; request.self = pending;
    destroy_object(&request); assert(request.error == EBUSY && entry(pending));
    cursor_view_active = false;
    request = {}; request.self = pending;
    destroy_object(&request); assert(!request.error && !entry(pending));
    assert(!QGuiApplication::overrideCursor());
    std::cout << "CURSOR_GUARDS_NATIVE_OK stack=1 nested=1 idempotent=1 cleanup=1 active_view_deferral=1\n";
}
