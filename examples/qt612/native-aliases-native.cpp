// Exercise the production alias validator with a minimal registry. Real Qt
// objects and native heap storage are used; the Bend/effect ABI is not tested.
#include <QtCore/QCoreApplication>
#include <QtCore/QObject>
#include <QtCore/QThread>
#include <QtCore/QFutureInterfaceBase>
#include <QtCore/QMutexLocker>
#include <array>
#include <atomic>
#include <cassert>
#include <cerrno>
#include <cstdint>
#include <functional>
#include <iostream>
#include <memory>
#include <type_traits>

struct BqtRequest { int error = 0; const char *message = nullptr; };
struct Entry {
    uint32_t token = 0, native_owner = 0;
    uint16_t generation = 0;
    void *value = nullptr;
    QObject *object = nullptr;
    std::shared_ptr<std::atomic<bool>> *alive = nullptr;
    bool destroying = false, read_only = false;
    bool (*validate)(BqtRequest *, uint32_t) = nullptr;
    void *(*cast)(void *, uint16_t) = nullptr;
};
static constexpr uint32_t capacity = 32;
template<class T> using SlotTable = std::array<T, capacity>;
static SlotTable<Entry> entries;
struct Retention { uint32_t owner = 0, target = 0; };
static SlotTable<Retention> retentions;
static QThread *main_thread;
static Entry *entry(uint32_t id) {
    auto &value = entries[id & 65535u];
    return value.value && value.token == id ? &value : nullptr;
}
static uint32_t token(uint32_t index, uint16_t generation) { return (uint32_t(generation) << 16) | index; }
static bool entry_inside(uint32_t child, uint32_t owner) {
    for (uint32_t depth = 0; child && depth < capacity; ++depth) {
        if (child == owner) return true;
        auto *value = entry(child);
        if (!value) return false;
        child = value->native_owner;
    }
    return false;
}
static void invalidate(uint32_t id) {
    if (auto *value = entry(id)) value->value = nullptr;
    for (auto &child : entries) if (child.value && child.native_owner == id) invalidate(child.token);
}
static bool fail(BqtRequest *r, int error, const char *message) { r->error = error; r->message = message; return true; }
static bool rhi_validate_dependencies(BqtRequest *, uint32_t) { return true; }
static bool value_provenance_validate(BqtRequest *, uint32_t) { return true; }
struct NativeCallScope {
    NativeCallScope *previous;
    static inline NativeCallScope *current = nullptr;
    NativeCallScope() : previous(current) { current = this; }
    ~NativeCallScope() { current = previous; }
    void pin(BqtRequest *, uint32_t) {}
};
#define native_call_scope NativeCallScope::current
template<class T> static T *get(BqtRequest *r, uint32_t id, uint16_t type,
        bool = false, bool writable = true, bool validate = true) {
    auto *value = entry(id);
    if (!value) { fail(r, ESTALE, "Expired test registry handle"); return nullptr; }
    if (validate && value->validate && !value->validate(r, id)) return nullptr;
    if (writable && value->read_only) { fail(r, EPERM, "Readonly test view"); return nullptr; }
    return static_cast<T *>(value->cast(value->value, type));
}
template<class T> static uint32_t register_native_borrow(BqtRequest *, T *pointer, uint16_t type, uint32_t owner) {
    for (uint32_t i = 1; i < capacity; ++i) if (!entries[i].value) {
        auto &value = entries[i];
        const auto generation = uint16_t((value.token >> 16) + 1);
        value = {};
        value.generation = generation;
        value.token = token(i, generation);
        value.value = const_cast<std::remove_const_t<T> *>(pointer);
        value.native_owner = owner;
        value.cast = [](void *source, uint16_t id) -> void * { return id == sizeof(T) ? source : nullptr; };
        assert(type == sizeof(T));
        return value.token;
    }
    std::abort();
}

#include "protected-field-views.h"

struct Leaf { uint64_t value = 42; };
struct Parent { std::unique_ptr<Leaf> child = std::make_unique<Leaf>(); uint64_t padding = 1; };
struct Root { std::unique_ptr<Parent> parent = std::make_unique<Parent>(); uint64_t padding[2] = {}; };
struct ObjectRoot : QObject { Parent parent; };

int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    main_thread = QThread::currentThread();
    BqtRequest request{};
    Root root;
    const auto root_id = register_native_borrow(&request, &root, sizeof(Root), 0);
    auto captured = std::make_shared<int>(1);
    std::weak_ptr<int> released = captured;
    const auto parent_id = protected_fields_borrow(&request, root.parent.get(), sizeof(Parent), root_id,
        [captured](BqtRequest *r, uint32_t id) -> const void * {
            auto *value = protected_fields_owner<Root>(r, id, sizeof(Root));
            return value ? value->parent.get() : nullptr;
        }, false);
    captured.reset();
    const auto child_id = protected_fields_borrow(&request, root.parent->child.get(), sizeof(Leaf), parent_id,
        [](BqtRequest *r, uint32_t id) -> const void * {
            auto *value = protected_fields_owner<Parent>(r, id, sizeof(Parent));
            return value ? value->child.get() : nullptr;
        }, false);
    assert(protected_fields_alias_validate(&request, child_id));
    assert(!request.error);
    // Allocate the replacement while the original is alive, so pointer
    // identity has changed independently of the allocator's reuse policy.
    root.parent = std::make_unique<Parent>();
    assert(!protected_fields_alias_validate(&request, child_id));
    assert(request.error == ESTALE);
    protected_fields_reconcile();
    assert(released.expired());

    // A native QObject ancestor can die on another thread before the main
    // registry consumes its queued destruction notification.
    auto object = std::make_unique<ObjectRoot>();
    auto alive = std::make_shared<std::atomic<bool>>(true);
    const auto object_id = register_native_borrow(&request, object.get(), sizeof(ObjectRoot), 0);
    entry(object_id)->object = object.get();
    entry(object_id)->alive = &alive;
    request = {};
    // A previously observed native member can already have an owner edge
    // without an alias-specific validation callback of its own.
    const auto parent2 = register_native_borrow(&request, &object->parent, sizeof(Parent), object_id);
    const auto child2 = protected_fields_borrow(&request, object->parent.child.get(), sizeof(Leaf), parent2,
        [](BqtRequest *r, uint32_t id) -> const void * {
            auto *value = protected_fields_owner<Parent>(r, id, sizeof(Parent));
            return value ? value->child.get() : nullptr;
        }, false);
    alive->store(false, std::memory_order_release);
    object.reset();
    assert(!protected_fields_alias_validate(&request, child2));
    assert(request.error == ESTALE);
    protected_fields_reconcile();
    // A real native locker must release its mutex before replacement can free
    // the future's state. Merely invalidating the Bend view would leave the
    // locker holding a freed QMutex and make its destructor unsafe.
    QFutureInterfaceBase future;
    request = {};
    const auto future_id = register_native_borrow(&request, &future, sizeof(future), 0);
    auto *mutex = &future.mutex();
    const auto mutex_id = protected_fields_borrow(&request, mutex, sizeof(QMutex), future_id,
        [](BqtRequest *r, uint32_t id) -> const void * {
            auto *value = protected_fields_owner<QFutureInterfaceBase>(r, id, sizeof(QFutureInterfaceBase));
            return value ? &value->mutex() : nullptr;
        }, false);
    QMutexLocker<QMutex> locker(mutex);
    const auto locker_id = register_native_borrow(&request, &locker, sizeof(locker), 0);
    retentions[0] = {locker_id, mutex_id};
    assert(!protected_fields_children_mutable(&request, future_id));
    assert(request.error == EBUSY);
    assert(entry(mutex_id));
    locker.unlock();
    retentions[0] = {};
    request = {};
    assert(protected_fields_children_mutable(&request, future_id));
    protected_fields_expire_children(future_id);
    future = QFutureInterfaceBase();
    assert(!entry(mutex_id));
    std::cout << "NATIVE_ALIASES_OK nested_replacement=1 captured_release=1 destroyed_qobject_ancestor=1 retained_future_mutex=1\n";
}
