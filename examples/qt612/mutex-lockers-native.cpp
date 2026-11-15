// Native helper control with a minimal registry; the complete effect/Action
// and scope contracts are exercised by scripts/fixtures/mutex-lockers.bend.
#include <QtCore/QtCore>
#include <array>
#include <cassert>
#include <cerrno>
#include <cstdint>
#include <iostream>
#include <memory>
#include <thread>
#include <vector>

struct BqtValue { uint32_t word = 0, owned_handle = 0, borrowed_handle = 0; };
struct BqtRequest { uint32_t self = 0; BqtValue arguments[1], result; int error = 0; const char *message = nullptr; };
struct Entry {
    void *value = nullptr;
    void (*destroy)(void *) = nullptr;
    uint16_t type = 0, generation = 0;
    bool owned = false, destroying = false, pending_release = false;
    uint32_t active_calls = 0;
};
struct Retention { uint32_t owner = 0, target = 0; };
static constexpr uint32_t capacity = 64;
static std::array<Entry, capacity> entries;
static std::array<Retention, capacity> retentions;
static QThread *main_thread;
static bool fail_next_retention = false;
static bool (*cleanup_hook)(BqtRequest *, uint32_t) = nullptr;
static bool (*defer_hook)(BqtRequest *, uint32_t) = nullptr;
static uint32_t token(uint32_t i, uint16_t generation) { return i | (uint32_t(generation) << 16); }
static Entry *entry(uint32_t id) {
    auto &e = entries[id & 65535u];
    return e.value && token(id & 65535u, e.generation) == id ? &e : nullptr;
}
static bool fail(BqtRequest *r, int code, const char *message) { r->error = code; r->message = message; return true; }
static void invalidate(uint32_t id) {
    if (auto *e = entry(id)) e->value = nullptr;
    for (auto &edge : retentions) if (edge.owner == id) edge = {};
}
struct NativeCallScope {
    NativeCallScope *previous;
    std::vector<uint32_t> pins;
    static inline NativeCallScope *current = nullptr;
    NativeCallScope() : previous(current) { current = this; }
    ~NativeCallScope() {
        current = previous;
        for (auto id : pins) if (auto *e = entry(id)) --e->active_calls;
    }
    void pin(BqtRequest *r, uint32_t id) {
        if (std::find(pins.begin(), pins.end(), id) != pins.end()) return;
        if (auto *e = entry(id)) { pins.push_back(id); ++e->active_calls; }
        else fail(r, ESTALE, "Expired test resource");
    }
};
#define native_call_scope NativeCallScope::current
template<class T> static T *get(BqtRequest *r, uint32_t id, uint16_t type, bool nullable = false, bool = true) {
    if (!id && nullable) return nullptr;
    auto *e = entry(id);
    if (!e) { fail(r, ESTALE, "Expired test source"); return nullptr; }
    if (e->type != type) { fail(r, EINVAL, "Wrong test source type"); return nullptr; }
    if (native_call_scope) native_call_scope->pin(r, id);
    return static_cast<T *>(e->value);
}
static uint32_t insert(BqtRequest *, void *value, QObject *, uint16_t type, void (*destroy)(void *), bool owned) {
    for (uint32_t i = 1; i < capacity; ++i) if (!entries[i].value) {
        auto &e = entries[i]; ++e.generation;
        e.value = value; e.type = type; e.destroy = destroy; e.owned = owned;
        return token(i, e.generation);
    }
    std::abort();
}
static int prepare_retention(BqtRequest *r, uint32_t, uint32_t, uint32_t target) {
    if (fail_next_retention) { fail_next_retention = false; fail(r, ENOSPC, "Injected retention failure"); return -1; }
    if (!entry(r->self) || (target && !entry(target))) { fail(r, ESTALE, "Expired retention"); return -1; }
    for (size_t i = 0; i < retentions.size(); ++i) if (retentions[i].owner == r->self) return int(i);
    for (size_t i = 0; i < retentions.size(); ++i) if (!retentions[i].owner) return int(i);
    std::abort();
}
static void commit_retention(int i, uint32_t owner, uint32_t, uint32_t, uint32_t target, QObject *(*)(QObject *, uint32_t)) {
    if (i >= 0) retentions[size_t(i)] = target ? Retention{owner, target} : Retention{};
}
struct RetentionBatch {
    struct Change { int index; uint32_t owner, target; };
    std::vector<Change> changes;
    bool add(BqtRequest *r, uint32_t owner, uint32_t slot, uint32_t target, QObject *(*f)(QObject *, uint32_t), bool, bool, uint32_t key) {
        BqtRequest check{}; check.self = owner;
        const int index = prepare_retention(&check, slot, key, target);
        if (check.error) { fail(r, check.error, check.message); return false; }
        changes.push_back({index, owner, target}); return true;
    }
    bool finish(BqtRequest *) {
        for (auto c : changes) commit_retention(c.index, c.owner, 1, 0, c.target, nullptr);
        return true;
    }
};
static bool destroy_object(BqtRequest *r) {
    auto *e = entry(r->self);
    if (!e) return fail(r, ESTALE, "Expired object");
    if (e->active_calls) return fail(r, EBUSY, "Active object");
    for (auto edge : retentions) if (edge.target == r->self && entry(edge.owner)) return fail(r, EBUSY, "Retained object");
    if (cleanup_hook && !cleanup_hook(r, r->self)) return true;
    auto *value = e->value; auto destroy = e->destroy;
    invalidate(r->self); if (destroy) destroy(value);
    return true;
}
static bool release_object(BqtRequest *r) {
    if (defer_hook && defer_hook(r, r->self)) return true;
    return destroy_object(r);
}

#include "mutex-lockers-runtime.h"

template<class Mutex> static bool available(Mutex &mutex) {
    bool result = false;
    std::thread worker([&] { result = mutex.tryLock(); if (result) mutex.unlock(); });
    worker.join(); return result;
}
static void release(uint32_t id, unsigned kind) {
    BqtRequest request{}; request.self = id;
    NativeMutexLockers::release(&request, kind); assert(!request.error);
}
int main(int argc, char **argv) {
    QCoreApplication app(argc, argv); main_thread = QThread::currentThread();
    QMutex first, second;
    const auto first_id = insert(nullptr, &first, nullptr, 1, nullptr, false);
    const auto second_id = insert(nullptr, &second, nullptr, 1, nullptr, false);
    BqtRequest a{}; a.arguments[0].word = first_id;
    NativeMutexLockers::create<QMutex, 0>(&a); assert(!a.error && a.result.owned_handle);
    const auto a_id = a.result.word;
    assert(!available(first));
    BqtRequest request{}; request.self = a_id;
    NativeMutexLockers::unlock(&request, 0); assert(!request.error && available(first));
    request = {}; request.self = first_id; destroy_object(&request); assert(request.error == EBUSY);
    request = {}; request.self = a_id; NativeMutexLockers::relock(&request, 0);
    assert(!request.error && !available(first));
    BqtRequest b{}; b.arguments[0].word = second_id;
    NativeMutexLockers::create<QMutex, 0>(&b); assert(!b.error);
    const auto b_id = b.result.word;
    request = {}; request.self = a_id; request.arguments[0].word = b_id;
    NativeMutexLockers::swap(&request, 0); assert(!request.error);
    request = {}; request.self = a_id; NativeMutexLockers::mutex(&request, 0);
    assert(!request.error && request.result.word == second_id);
    release(a_id, 0); assert(available(second) && !available(first));
    release(b_id, 0); assert(available(first));
    QRecursiveMutex recursive;
    const auto recursive_id = insert(nullptr, &recursive, nullptr, 2, nullptr, false);
    a = {}; a.arguments[0].word = recursive_id;
    b = {}; b.arguments[0].word = recursive_id;
    NativeMutexLockers::create<QRecursiveMutex, 1>(&a);
    NativeMutexLockers::create<QRecursiveMutex, 1>(&b);
    assert(!a.error && !b.error && !available(recursive));
    request = {}; request.self = a.result.word; NativeMutexLockers::locked(&request, 0);
    assert(request.error == EINVAL);
    release(a.result.word, 1); assert(!available(recursive));
    release(b.result.word, 1); assert(available(recursive));
    a = {}; NativeMutexLockers::create<QMutex, 0>(&a); assert(!a.error);
    request = {}; request.self = a.result.word; NativeMutexLockers::locked(&request, 0);
    assert(!request.error && !request.result.word); release(a.result.word, 0);
    fail_next_retention = true;
    a = {}; a.arguments[0].word = first_id;
    NativeMutexLockers::create<QMutex, 0>(&a);
    assert(a.error == ENOSPC && a.result.owned_handle && !available(first));
    release(a.result.owned_handle, 0); assert(available(first));
    for (auto edge : retentions) assert(!edge.owner);
    std::cout << "MUTEX_LOCKERS_NATIVE_OK locking=1 recursive=1 swap=1 nullable=1 leases=1 failed_result_cleanup=1\n";
    return 0;
}
