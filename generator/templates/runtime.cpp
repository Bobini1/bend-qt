// Shared Qt runtime. Qt and Bend run on the main thread: generated wrappers
// are called directly by Bend effects and use this registry.
#ifndef BQT_HAS_RHI
#define BQT_HAS_RHI 1
#endif
#include <QtCore/QMetaObject>
#include <QtCore/qtmocconstants.h>
#include <QtCore/QThread>
#include <QtCore/QTimer>
#include <QtCore/QEventLoop>
#include <QtCore/QEvent>
#include <QtCore/QMutex>
#include <QtCore/QSocketNotifier>
#include <QtCore/QAbstractEventDispatcher>
#include <QtCore/QCoreApplication>
#include <QtCore/QResource>
#include <QtCore/QFile>
#include <QtCore/QLibraryInfo>
#include <QtCore/QElapsedTimer>
#include <QtCore/QDeadlineTimer>
#include <QtCore/QAbstractItemModel>
#include <QtCore/QCoreApplication>
// The Core-based shared group compiles without GUI modules. Every source that
// includes a QtGui or QtWidgets header has that module's global header.
#if !defined(BQT_HAS_GUI) && defined(QTGUIGLOBAL_H)
#define BQT_HAS_GUI 1
#endif
#if !defined(BQT_HAS_WIDGETS) && defined(QTWIDGETSGLOBAL_H)
#define BQT_HAS_WIDGETS 1
#endif
#if defined(BQT_HAS_WIDGETS)
#include <QtWidgets/QApplication>
#endif
#if defined(BQT_HAS_GUI)
#include <QtGui/QGuiApplication>
#include <QtGui/QAccessible>
#endif
#include <cstdint>
#include <climits>
#include <cstdlib>
#include <cstring>
#include <cerrno>
#include <type_traits>
#include <utility>
#include <limits>
#include <optional>
#include <cstdio>
#include <vector>
#include <exception>
#include <stdexcept>
#include <system_error>
#include <string>
#include <new>
#include <memory>
#include <atomic>
#include <algorithm>
#include <array>
#include <functional>
#include <set>
#include <map>
#include <deque>
#include <iterator>
#include <sys/mman.h>
#include <unistd.h>

// @ABI@

namespace bendqt {
#if defined(BQT_HAS_GUI)
namespace NativeFunctionCallbacks {
static uint32_t accessible_borrow(BqtRequest *, QAccessibleInterface *);
static uint32_t accessible_borrow(BqtRequest *, const QAccessibleInterface *);
}
#endif
// A native constructor sees its immutable Bend schema before its base starts.
// The guard spans one synchronous Qt call and restores nested constructions.
static thread_local const QMetaObject *runtime_construction_meta = nullptr;
static thread_local bool runtime_construction_placement = false;
struct RuntimeConstructionMeta {
    const QMetaObject *previous;
    bool previous_placement;
    explicit RuntimeConstructionMeta(const QMetaObject *meta, bool allow_placement = false)
        : previous(runtime_construction_meta), previous_placement(runtime_construction_placement) {
        runtime_construction_meta = meta; runtime_construction_placement = allow_placement;
    }
    ~RuntimeConstructionMeta() { runtime_construction_meta = previous; runtime_construction_placement = previous_placement; }
};
struct RuntimePendingPlacement {
    const QMetaObject *schema;
    uint16_t base;
    void *memory;
    QObject *object = nullptr;
    uint32_t handle = 0;
    bool claimed = false;
};
static thread_local RuntimePendingPlacement *runtime_pending_placement = nullptr;
struct RuntimePlacementScope {
    RuntimePendingPlacement *previous;
    const QMetaObject *previous_meta;
    bool previous_placement;
    explicit RuntimePlacementScope(RuntimePendingPlacement *value)
        : previous(runtime_pending_placement), previous_meta(runtime_construction_meta), previous_placement(runtime_construction_placement) {
        runtime_pending_placement = value; runtime_construction_meta = nullptr; runtime_construction_placement = false;
    }
    ~RuntimePlacementScope() {
        runtime_pending_placement = previous; runtime_construction_meta = previous_meta; runtime_construction_placement = previous_placement;
    }
};
static uint32_t native_request_scope;
static uint32_t scope_track(BqtRequest *, uint32_t, uint8_t);
static void scope_forget_aux(uint8_t, uint32_t);
static bool scope_valid(uint32_t);
static bool scope_adopt_result(BqtRequest *, QObject *, uint32_t, std::vector<uint32_t> * = nullptr);
static bool scope_adopt_native_result(BqtRequest *, uint32_t, uint32_t, std::vector<uint32_t> * = nullptr);
static bool scope_release_aux(BqtRequest *, uint8_t, uint32_t);
namespace OpaqueData {
static void release(uint32_t) noexcept;
static void drain();
static void shutdown();
}
struct RuntimeObjectState;
static bool runtime_object_signal_declared(const std::shared_ptr<RuntimeObjectState> &, const QMetaObject *);
struct RuntimeObjectHost {
    std::shared_ptr<RuntimeObjectState> bqt_object;
    bool bqt_exposed = false;
    virtual ~RuntimeObjectHost() = default;
    virtual uint16_t runtime_base_id() const noexcept = 0;
    virtual void runtime_observe(uint32_t) = 0;
};
static const QMetaObject *runtime_object_meta(const std::shared_ptr<RuntimeObjectState> &, const QMetaObject *);
static bool runtime_object_cast(const std::shared_ptr<RuntimeObjectState> &, const char *);
static int runtime_object_metacall(QObject *, const std::shared_ptr<RuntimeObjectState> &, QMetaObject::Call, int, void **, const std::shared_ptr<std::atomic<bool>> &);
static int runtime_argument_index(BqtRequest *, const QByteArray &, const BqtValue *);
static QMetaType runtime_argument_meta(int);
static QVariant runtime_argument_read(BqtRequest *, int, const BqtValue &);
static BqtValue runtime_argument_write(BqtRequest *, int, const void *);
static bool runtime_argument_assign(BqtRequest *, int, void *, const void *);
#if defined(BQT_NATIVE_PARTITIONS)
static void runtime_register_partition_arguments();
static void runtime_register_partition_bases();
#endif
// Immutable native names can be retained by Qt plugins and QML registrations.
// Set nodes keep their string addresses through further insertions. This pool
// lives as long as the embedded native host; names are deduplicated.
static const char *intern_native_name(const char *text, size_t size) {
    // Native plugin atexit handlers may run after C++ static destructors.
    // Deliberately keep this deduplicated arena until the process is reclaimed.
    static auto *mutex = new QMutex;
    static auto *names = new std::set<std::string>;
    QMutexLocker lock(mutex);
    return names->emplace(text ? text : "", size).first->c_str();
}
struct QStringBuffer { QString value; };
struct NativeEvent { QByteArray type; void *message; };
struct RoleDataBuffer { QList<QModelRoleData> values; };
struct ModelData { quintptr address; uint32_t index; bool persistent, was_valid; };
struct ImageBuffer { std::shared_ptr<std::vector<uint64_t>> storage; size_t size = 0; };
struct IncubationFlag { std::atomic<bool> value; explicit IncubationFlag(bool initial) : value(initial) {} };
struct CallbackHandlers;
static uint32_t capacity = 4096;
static constexpr uint32_t slot_limit = uint32_t(UINT16_MAX) + 1;
struct SlotTableBase {
    SlotTableBase *next;
    void (*resize)(SlotTableBase *, uint32_t);
    static SlotTableBase *&first() { static SlotTableBase *head = nullptr; return head; }
};
// deque growth preserves references: native calls and reentrant Bend handlers
// may hold Entry/Connection pointers while another allocation grows the tables.
// Sidecars grow together, before any token from the new range can be issued.
template<class T> class SlotTable : public SlotTableBase {
    std::deque<T> values;
public:
    template<bool Constant> class Iterator {
        using Table = std::conditional_t<Constant, const SlotTable, SlotTable>;
        Table *table = nullptr;
        uint32_t index = 0;
    public:
        using iterator_category = std::forward_iterator_tag;
        using value_type = T;
        using difference_type = std::ptrdiff_t;
        using reference = std::conditional_t<Constant, const T &, T &>;
        using pointer = std::conditional_t<Constant, const T *, T *>;
        Iterator() = default;
        Iterator(Table *owner, uint32_t position) : table(owner), index(position) {}
        reference operator*() const { return table->values[index]; }
        pointer operator->() const { return std::addressof(operator*()); }
        Iterator &operator++() { ++index; return *this; }
        Iterator operator++(int) { auto previous = *this; ++*this; return previous; }
        bool operator==(const Iterator &other) const { return table == other.table && index == other.index; }
        bool operator!=(const Iterator &other) const { return !(*this == other); }
    };
    SlotTable() : values(capacity) {
        next = first(); first() = this;
        resize = [](SlotTableBase *base, uint32_t size) { static_cast<SlotTable *>(base)->values.resize(size); };
    }
    T &operator[](size_t index) { return values.at(index); }
    const T &operator[](size_t index) const { return values.at(index); }
    // deque iterators are invalidated by growth. Index iterators remain valid
    // when a getter/destruction handler grows the tables during a scan.
    auto begin() { return Iterator<false>(this, 0); }
    auto end() { return Iterator<false>(this, capacity); }
    auto begin() const { return Iterator<true>(this, 0); }
    auto end() const { return Iterator<true>(this, capacity); }
};
static bool grow_registry() {
    if (capacity == slot_limit) return false;
    uint32_t next = std::min(capacity * 2, slot_limit);
    for (auto *table = SlotTableBase::first(); table; table = table->next) table->resize(table, next);
    // An allocation failure leaves the old visible range intact. A table that
    // already grew can safely keep its still-unused default-initialized tail.
    capacity = next;
    return true;
}
constexpr uint32_t shared_holder_slot = 0xfffffff0u;
struct NativeDestructionScope;
struct Entry {
    uint16_t slot_index;
    uint32_t scope_owner;
    RuntimeObjectState *dynamic_state;
    void *value;
    QObject *object;
    QObject *parent;
    void (*destroy)(void *);
    uint16_t generation;
    uint16_t type;
    bool owned;
    bool retired;
    bool pending_release;
    uint32_t active_calls;
    // Cleared by a destruction observer, which Qt may run on another thread
    // before the registry itself is updated on the main thread.
    std::shared_ptr<std::atomic<bool>> *alive;
    // A generated override object: its destructor reports to the registry,
    // and these are the Bend handlers installed on it.
    bool proxy;
    CallbackHandlers *handlers;
    bool destroying;
    bool deferred_invalidation = false;
    const NativeDestructionScope *deferred_scope = nullptr;
    uint32_t native_owner;
    void *(*cast)(void *, uint16_t);
    bool read_only;
    bool native_observed;
    bool shared_managed;
    bool render_only;
    uint32_t render_window;
    uint32_t graphics_context;
    uint32_t file_mappings;
    bool shared_memory_writable;
    uint64_t text_epoch;
    bool text_observed;
    uint32_t text_edit_depth;
    bool (*validate)(BqtRequest *, uint32_t);
};
struct Retention {
    uint32_t owner, slot, key, target;
    QObject *(*current)(QObject *, uint32_t);
    uint32_t (*native_current)(uint32_t, uint32_t) = nullptr;
};
static uint32_t render_factory_retention_owner(uint32_t);
static bool render_factory_sync_owner(BqtRequest *, uint32_t, uint32_t);
static SlotTable<Retention> retentions;
static SlotTable<bool> retention_reserved;
struct RetentionReservationKey { uint32_t owner, slot, key; };
static SlotTable<RetentionReservationKey> retention_reservation_keys;

static void reserve_retention(int index, uint32_t owner, uint32_t slot, uint32_t key)
{
    if (index < 0) return;
    owner = render_factory_retention_owner(owner);
    retention_reserved[index] = true;
    retention_reservation_keys[index] = {owner, slot, key};
}

static void unreserve_retention(int index)
{
    if (index < 0) return;
    retention_reserved[index] = false;
    retention_reservation_keys[index] = {};
}

struct RetentionReservation {
    int index;
    RetentionReservation(int i, uint32_t owner, uint32_t slot, uint32_t key) : index(i)
    { reserve_retention(i, owner, slot, key); }
    RetentionReservation(const RetentionReservation &) = delete;
    ~RetentionReservation() { unreserve_retention(index); }
};
// One signal connection made by Bend. The context object lives on the main
// thread, so Qt runs the handler there: directly for a signal emitted on the
// main thread, through its queued delivery otherwise.
struct Connection {
    uint32_t scope_owner;
    QMetaObject::Connection *connection;
    QObject *context;
    uint32_t sender;
    uint32_t handler;
    uint16_t generation;
    bool active;
    bool retired;
    // Runs once, with the sender's identity, when the registry forgets the
    // sender, then closes.
    bool terminal;
};
static SlotTable<Entry> entries;
static SlotTable<Connection> connections;
// The program constructs its application explicitly, as in C++, through
// QCoreApplication.new, QGuiApplication.new or QApplication.new.
static QCoreApplication *application;
// Set once the first Qt effect has started the runtime, before any
// application object exists.
static bool runtime_started;
static const BqtHost *bend;
// Bend and the Qt application run here. Other threads read these to bring a
// call to the main thread, so neither depends on `application` staying set.
static QThread *main_thread;
static thread_local unsigned native_destructor_depth = 0;
static thread_local NativeDestructionScope *native_destruction_scope = nullptr;
static void flush_native_destruction(NativeDestructionScope *);
struct NativeDestructionScope {
    bool active = QThread::currentThread() == main_thread;
    NativeDestructionScope *previous = nullptr;
    bool flushing = false;
    NativeDestructionScope() {
        if (active) { previous = native_destruction_scope; native_destruction_scope = this; ++native_destructor_depth; }
    }
    ~NativeDestructionScope() {
        if (active) {
            flush_native_destruction(this);
            native_destruction_scope = previous;
            --native_destructor_depth;
        }
    }
};
static void dynamic_properties_event(QObject *, QEvent *);
static void dynamic_properties_forget(uint32_t);
template<class Base> class BendApplication final : public Base {
public:
    using Base::Base;
    bool notify(QObject *receiver, QEvent *event) override {
        NativeDestructionScope notification;
        dynamic_properties_event(receiver, event);
        return Base::notify(receiver, event);
    }
};
static std::atomic<QObject *> main_context{nullptr};
static unsigned gui_render_depth;
static uint32_t gui_render_window;
static bool gui_render_enabled;
static bool render_type(uint16_t type);
static void schedule_render_collection(uint32_t id);
static void prepare_render_shutdown();
static bool attach_graphics_context(BqtRequest *r, uint32_t id);
static bool graphics_context_ready(uint32_t id);
static bool attach_rhi_identity(BqtRequest *, uint32_t);
static bool rhi_validate_dependencies(BqtRequest *, uint32_t);
static void rhi_forget(uint32_t);
static bool rhi_release_ready(uint32_t);
static bool rhi_destroy_root(BqtRequest *);
static bool rhi_cleanup_operation(BqtRequest *, uint32_t);
static void rhi_shutdown();
static bool borrow_rhi_identity(BqtRequest *, void *, uint16_t, void *(*)(void *, uint16_t), void (*)(void *), uint32_t *);
static void reconcile_native_layouts();
static void message_handler_shutdown();
static void native_function_callbacks_shutdown();
static bool post_routines_entry(const Entry &);
static void post_routines_prepare();
static const char *construct_application(int);
static bool create_application(BqtRequest *, int, uint32_t);
static bool require_application(BqtRequest *, int);
static int post_routines_shutdown();
static void callback_drain_released();
static void prune_qml_list_leases();
// Installed with the first QML list view: whether a signal snapshot queued from
// another thread still holds a QML list owner inside this subtree.
// Spelled through an alias: the shared-state rewrite of runtime globals
// handles a plain declarator, not a function-pointer one.
using QmlListQueuedOwner = bool (*)(uint32_t);
static QmlListQueuedOwner qml_list_queued_owner = nullptr;
// Installed with the first text value guard: QObject.blockSignals and
// QSignalBlocker, in the Core group, must still invalidate text iterators.
using TextMutationHook = bool (*)(BqtRequest *, QObject *);
static TextMutationHook text_mutation_hook = nullptr;
// Set by runtime startup: connects Bend's sources to the event dispatcher that
// the program's application object creates.
using ApplicationHook = void (*)();
static ApplicationHook application_constructed = nullptr;
static bool note_object_text_mutation(BqtRequest *r, QObject *object) {
    return !text_mutation_hook || text_mutation_hook(r, object);
}
static void protected_fields_reconcile();
static void release_static_native_view(void *);
static bool cursor_guard_cleanup_ready(BqtRequest *, uint32_t);
static bool cursor_guard_defer_release(BqtRequest *, uint32_t);
static void static_native_view_forget(uint32_t);
template<class T> static uint32_t borrow_static_native_view(BqtRequest *, T *, uint16_t,
    std::function<const void *(BqtRequest *)> = {}, bool = false);

// Tables evaluated from the proved Bend definitions by the maintainer generator.
// @LIFETIME@

static uint64_t wide_bits(BqtValue value)
{ return (uint64_t(value.high) << 32) | value.word; }
static BqtValue wide_value(uint64_t bits)
{ return BqtValue{uint32_t(bits), nullptr, 0, uint32_t(bits >> 32)}; }
static double real_value(BqtValue value)
{
    uint64_t bits = wide_bits(value);
    double number;
    static_assert(sizeof number == sizeof bits);
    std::memcpy(&number, &bits, sizeof number);
    return number;
}
static BqtValue real_bits(double number)
{
    uint64_t bits;
    std::memcpy(&bits, &number, sizeof number);
    return wide_value(bits);
}

static const char *own_request_message(const char *) noexcept;
static bool fail(BqtRequest *r, int code, const char *message)
{
    r->error = code;
    r->message = own_request_message(message);
    return true;
}

// One Qt operation started by Bend. Qt may run Bend handlers during it: from
// a signal, a virtual method or, when the operation runs an event loop, from
// any event. A handler that fails has no caller of its own to tell, so the
// first failure is kept here and the operation itself fails with it.
struct CallFrame {
    static inline CallFrame *current = nullptr;
    CallFrame *previous = current;
    int handler_error = 0;
    std::string handler_message;
    std::vector<std::unique_ptr<std::string>> native_messages;
    // Set by an operation that runs an event loop (see event_loops.py): a
    // failed handler then ends that loop at once instead of waiting for it.
    QEventLoop *loop = nullptr;
    bool application_loop = false;
    std::function<void()> stop;
    CallFrame() { current = this; }
    ~CallFrame() { current = previous; }
    void handler_failed(int code, const char *text)
    {
        if (handler_error) return;
        handler_error = code;
        handler_message = text ? text : "";
        if (loop) loop->exit(-1);
        else if (application_loop) QCoreApplication::exit(-1);
        else if (stop) stop();
    }
};

static const char *own_request_message(const char *message) noexcept {
    if (!message || !CallFrame::current || QThread::currentThread() != main_thread) return message;
    try {
        auto owned = std::make_unique<std::string>(message);
        const char *data = owned->c_str();
        CallFrame::current->native_messages.push_back(std::move(owned));
        return data;
    } catch (...) { return "Unable to copy the native Qt error message"; }
}

static uint32_t token(uint32_t index, uint16_t generation)
{ return (uint32_t(generation) << 16) | index; }

static Entry *entry(uint32_t id)
{
    uint32_t i = id & 65535u;
    if (!i || i >= capacity || !entries[i].value || entries[i].generation != id >> 16)
        return nullptr;
    return &entries[i];
}

static bool inside(QObject *object, QObject *root)
{
    if (!root) return false;
    for (auto *p = object; p; p = p->parent()) if (p == root) return true;
    return false;
}

// Native item trees supplement QObject parenting. Tokens, rather than raw
// owner pointers, keep invalidation and slot reuse unambiguous.
static bool entry_inside(uint32_t child, uint32_t root)
{
    auto *root_entry = entry(root);
    if (!root_entry) return false;
    for (uint32_t depth = 0; child && depth < capacity; ++depth) {
        if (child == root) return true;
        auto *e = entry(child);
        if (!e) return false;
        if (root_entry->object && !root_entry->destroying && !e->destroying
                && (!root_entry->alive || (*root_entry->alive)->load(std::memory_order_acquire))
                && (!e->alive || (*e->alive)->load(std::memory_order_acquire))
                && inside(e->object, root_entry->object)) return true;
        child = e->native_owner;
    }
    return false;
}

static void schedule_collection() noexcept;
static bool is_value_view_handle(uint32_t id);

static bool callback_pin(BqtRequest *r, uint32_t id)
{
    auto *e = entry(id);
    if (!e) { fail(r, ESTALE, "Qt object was destroyed"); return false; }
    if (e->active_calls == UINT32_MAX) { fail(r, EOVERFLOW, "Too many active Qt calls"); return false; }
    ++e->active_calls;
    return true;
}

static void callback_unpin(uint32_t id)
{
    if (auto *e = entry(id)) {
        if (e->active_calls) --e->active_calls;
        if (e->pending_release) schedule_collection();
    }
}

static bool __attribute__((noinline)) active_in_subtree(uint32_t id)
{
    auto *root = entry(id);
    if (!root) return false;
    if (qml_list_queued_owner && qml_list_queued_owner(id)) return true;
    for (uint32_t i = 1; i < capacity; ++i)
        if (entries[i].value && (entries[i].active_calls ||
                (entries[i].object && qobject_cast<QThread *>(entries[i].object) &&
                 qobject_cast<QThread *>(entries[i].object)->isRunning()))) {
            auto active = token(i, entries[i].generation);
            if (entry_inside(active, id)) return true;
            for (const auto &edge : retentions)
                if (edge.slot == shared_holder_slot && entry_inside(edge.owner, id)
                        && entry_inside(active, edge.target)) return true;
        }
    return false;
}

struct NativeCallScope;
static NativeCallScope *native_call_scope;

// A native method may run Bend handlers or a nested Qt event loop. Checked
// arguments must survive until the original native method has returned.
struct NativeCallScope {
    NativeCallScope *previous = native_call_scope;
    std::optional<NativeDestructionScope> destruction{std::in_place};
    std::vector<uint32_t> pins;
    uint32_t value_origin = 0;
    // Only notes the checked handles; its owner pins them afterwards.
    bool noting = false;
    NativeCallScope() { native_call_scope = this; }
    void allow_event_loop() { destruction.reset(); }
    __attribute__((noinline)) ~NativeCallScope() {
        native_call_scope = previous;
        if (!noting) for (auto id : pins) callback_unpin(id);
    }
    void __attribute__((noinline)) pin(BqtRequest *r, uint32_t id) {
        for (auto existing : pins) if (existing == id) return;
        pins.push_back(id);
        if (!noting && !callback_pin(r, id)) pins.pop_back();
    }
};

struct NativeDispatchIsolation {
    NativeCallScope *previous = native_call_scope;
    NativeDispatchIsolation() { native_call_scope = nullptr; }
    ~NativeDispatchIsolation() { native_call_scope = previous; }
};

// After QObject::moveToThread, Bend can no longer use the moved tree (EXDEV),
// but the registry's own links into it are still followed on the main thread.
// The move is refused while any remain: an operation in progress, a native
// value or view owned by the tree, or a dependency, owner or render link
// between the tree and anything outside it.
static bool object_move_allowed(BqtRequest *r, uint32_t id)
{
    auto *root = entry(id);
    if (!root || !root->object) return true;
    auto inside = [id](uint32_t other) { return other && entry_inside(other, id); };
    auto own_pins = [](uint32_t other) {
        uint32_t count = 0;
        for (auto *scope = native_call_scope; scope; scope = scope->previous)
            for (auto pinned : scope->pins) if (pinned == other) ++count;
        return count;
    };
    for (uint32_t i = 1; i < capacity; ++i) {
        const auto &e = entries[i];
        if (!e.value) continue;
        const uint32_t other = token(i, e.generation);
        if (inside(other)) {
            if (e.active_calls > own_pins(other) || e.destroying || e.pending_release) {
                fail(r, EXDEV, "A Qt operation is still using this object tree"); return false;
            }
            if (!e.object || e.read_only || e.render_only || e.shared_managed || e.graphics_context || e.validate) {
                fail(r, EXDEV, "This object tree holds native values that stay on the main thread"); return false;
            }
            if (e.native_owner && !inside(e.native_owner)) {
                fail(r, EXDEV, "This object tree is owned from outside it"); return false;
            }
        } else if (inside(e.native_owner) || inside(e.graphics_context) || inside(e.render_window)) {
            fail(r, EXDEV, "Objects outside this tree depend on it"); return false;
        }
    }
    for (const auto &edge : retentions)
        if (edge.owner && entry(edge.owner) && entry(edge.target) && inside(edge.owner) != inside(edge.target)) {
            fail(r, EXDEV, "A Qt dependency links this object tree with objects outside it"); return false;
        }
    return true;
}

// Follow both binding references and native parent ownership without recursion.
static bool __attribute__((noinline)) reaches_token(uint32_t start, uint32_t goal)
{
    if (!entry(start) || !entry(goal)) return false;
    std::vector<uint32_t> queue(capacity);
    std::vector<bool> seen(capacity);
    uint32_t head = 0, tail = 1;
    queue[0] = start;
    seen[start & 65535u] = true;
    while (head < tail) {
        auto current = queue[head++];
        if (entry_inside(goal, current)) return true;
        for (const auto &edge : retentions) {
            if (!entry(edge.owner) || !entry(edge.target) || seen[edge.target & 65535u]
                    || !entry_inside(edge.owner, current)) continue;
            seen[edge.target & 65535u] = true;
            queue[tail++] = edge.target;
        }
    }
    return false;
}

static bool __attribute__((noinline)) reaches(QObject *start, QObject *goal)
{
    if (!start || !goal) return false;
    std::vector<QObject *> queue(capacity + 1);
    std::vector<bool> seen(capacity);
    uint32_t head = 0, tail = 1;
    queue[0] = start;
    while (head < tail) {
        auto *object = queue[head++];
        if (inside(goal, object)) return true;
        for (const auto &edge : retentions) {
            auto *owner = entry(edge.owner), *target = entry(edge.target);
            if (!owner || !target || owner->destroying || target->destroying
                    || (owner->alive && !(*owner->alive)->load(std::memory_order_acquire))
                    || (target->alive && !(*target->alive)->load(std::memory_order_acquire))
                    || seen[edge.target & 65535u] || !inside(owner->object, object)) continue;
            // An intermediate native value can retain a QObject, too.
            for (uint32_t i = 1; i < capacity; ++i)
                if (entries[i].value && entries[i].object == goal
                        && reaches_token(edge.target, token(i, entries[i].generation))) return true;
            seen[edge.target & 65535u] = true;
            queue[tail++] = target->object;
        }
    }
    return false;
}

static bool __attribute__((noinline)) retained(uint32_t id)
{
    auto *root = entry(id);
    if (!root) return false;
    for (const auto &e : entries)
        if (e.value && e.owned && ((e.render_only && e.render_window == id) || e.graphics_context == id)) return true;
    for (const auto &edge : retentions) {
        auto *owner = entry(edge.owner), *target = entry(edge.target);
        if (owner && target && entry_inside(edge.target, id) && !entry_inside(edge.owner, id)) return true;
    }
    return false;
}

static int __attribute__((noinline)) prepare_retention(BqtRequest *r, uint32_t slot, uint32_t key, uint32_t target_id)
{
    const auto owner_id = render_factory_retention_owner(r->self);
    auto *owner = entry(owner_id), *target = entry(target_id);
    if (!owner || (target_id && !target)) { fail(r, ESTALE, "Invalid retained object"); return -1; }
    if (target && reaches_token(target_id, owner_id)) { fail(r, ELOOP, "Qt retention would create a cycle"); return -1; }
    for (uint32_t i = 0; i < capacity; ++i) {
        const auto &reserved = retention_reservation_keys[i];
        if (retention_reserved[i] && reserved.owner == owner_id && reserved.slot == slot && reserved.key == key) {
            fail(r, EBUSY, "Qt relationship is being changed by an active native call");
            return -1;
        }
    }
    int free = -1;
    for (uint32_t i = 0; i < capacity; ++i) {
        const auto &edge = retentions[i];
        if (edge.owner == owner_id && edge.slot == slot && edge.key == key) return int(i);
        if (!edge.owner && !retention_reserved[i] && free < 0) free = int(i);
    }
    if (!target_id) return -1;
    if (free < 0) {
        uint32_t previous = capacity;
        if (grow_registry()) free = int(previous);
        else fail(r, ENOSPC, "Qt retention token range is exhausted");
    }
    return free;
}

static void commit_retention(int index, uint32_t owner, uint32_t slot, uint32_t key,
                             uint32_t target, QObject *(*current)(QObject *, uint32_t))
{
    owner = render_factory_retention_owner(owner);
    if (index >= 0) retentions[index] = target ? Retention{owner, slot, key, target, current} : Retention{};
}

static void __attribute__((noinline)) reconcile_retentions()
{
    static bool reconciling = false;
    if (reconciling) return;
    struct ReconcileGuard { bool &value; ~ReconcileGuard() { value = false; } } guard{reconciling};
    reconciling = true;
    reconcile_native_layouts();
    protected_fields_reconcile();
    for (auto &edge : retentions) {
        if (!edge.owner) continue;
        auto *owner = entry(edge.owner);
        if (!owner) { edge = {}; continue; }
        if (owner->destroying || (owner->alive && !(*owner->alive)->load(std::memory_order_acquire))) continue;
        if (edge.native_current) {
            auto previous = edge;
            uint32_t actual = edge.target;
            try { actual = edge.native_current(edge.owner, edge.key); }
            catch (...) { continue; }
            if (edge.owner != previous.owner || edge.slot != previous.slot || edge.key != previous.key
                    || edge.target != previous.target || edge.current != previous.current
                    || edge.native_current != previous.native_current) continue;
            if (!entry(edge.owner)) { edge = {}; continue; }
            // Preserve the observer for a native target not yet registered by
            // Bend. A later getter can establish its handle and dependency.
            edge.target = entry(actual) ? actual : 0;
            continue;
        }
        if (!edge.current) {
            if (!entry(edge.target)) edge = {};
            continue;
        }
        auto previous = edge;
        QObject *actual = nullptr;
        try { actual = edge.current(owner->object, edge.key); }
        catch (...) { continue; } // An unobservable relationship keeps its old pin.
        // Observable properties may call user code. Do not overwrite an edge
        // changed or invalidated by a reentrant mutation/destruction callback.
        if (edge.owner != previous.owner || edge.slot != previous.slot || edge.key != previous.key
                || edge.target != previous.target || edge.current != previous.current) continue;
        if (!entry(edge.owner)) { edge = {}; continue; }
        if (!actual) { edge = {}; continue; }
        auto *target = entry(edge.target);
        if (target && actual == target->object) continue;
        edge.target = 0;
        for (uint32_t i = 1; i < capacity; ++i) {
            if (entries[i].value && entries[i].object == actual) {
                edge.target = token(i, entries[i].generation);
                break;
            }
        }
        // Keep observing an unregistered Qt-owned target. A later getter can
        // register it. Indirect native changes are observed, never rolled back;
        // an externally introduced cycle conservatively keeps its members alive.
    }
    prune_qml_list_leases();
}

static void collect_pending();
static void schedule_collection() noexcept;

static void set_owned(uint32_t id, bool owned)
{
    if (auto *e = entry(id)) {
        e->owned = owned && e->destroy && !e->native_owner && !e->shared_managed && (!e->object || (e->object != application && !e->object->parent()));
        if (e->owned && !e->scope_owner) e->scope_owner = scope_track(nullptr, id, 0);
    }
}

static bool can_transfer_handle(BqtRequest *r, uint32_t id)
{
    if (auto *e = entry(id); e && e->destroy == release_static_native_view) {
        fail(r, EPERM, "A process-wide Qt object cannot transfer its native ownership"); return false;
    }
    if (auto *e = entry(id); e && e->destroying) {
        fail(r, EBUSY, "Qt object destruction is in progress"); return false;
    }
    if (is_value_view_handle(id)) {
        fail(r, EPERM, "A Qt storage view cannot transfer its native pointee ownership");
        return false;
    }
    if (auto *e = entry(id); e && e->shared_managed) {
        fail(r, EPERM, "Shared Qt pointee ownership belongs to its shared-pointer control block");
        return false;
    }
    return true;
}

static void __attribute__((noinline)) reconcile_parents()
{
    for (auto &e : entries) {
        if (!e.value || !e.object || (e.alive && !(*e.alive)->load(std::memory_order_acquire))) continue;
        auto *parent = e.object->parent();
        if (parent == e.parent) continue;
        e.owned = e.destroy && !e.native_owner && !e.shared_managed && lifetime_reparent[unsigned(e.owned) * 4 + unsigned(e.parent != nullptr) * 2 + unsigned(parent != nullptr)];
        e.parent = parent;
        if (e.owned && !e.scope_owner) e.scope_owner = scope_track(nullptr, token(e.slot_index, e.generation), 0);
    }
}

static bool can_adopt(BqtRequest *r, QObject *parent, QObject *child)
{
    for (uint32_t i = 1; child && i < capacity; ++i)
        if (entries[i].value && entries[i].object == child && !can_transfer_handle(r, token(i, entries[i].generation))) return false;
    if (child == application) {
        fail(r, EPERM, "The binding owns the Qt application lifecycle");
        return false;
    }
    for (auto *p = parent; p; p = p->parent()) {
        if (p == child) {
            fail(r, EINVAL, "Qt parenting would create an ownership cycle");
            return false;
        }
    }
    if (reaches(child, parent)) {
        fail(r, ELOOP, "Qt parenting would create a retention cycle");
        return false;
    }
    return true;
}

static Connection *connection(uint32_t id)
{
    uint32_t i = id & 65535u;
    if (!i || i >= capacity || !connections[i].active
        || connections[i].generation != id >> 16)
        return nullptr;
    return &connections[i];
}

static void native_pointer_publish(uint32_t);
static void native_pointer_forget(uint32_t);
static std::vector<uint32_t> native_pointer_died(const void *);
static void native_pointer_destroying(const void *);
static bool native_pointer_destructing(uint32_t);
// Declared before the native base so its destructor runs after that base.
// No QObject metadata or fake derived-layout assumptions are involved.
class NativeDeletionObserver {
    void *value = nullptr;
    std::optional<NativeDestructionScope> scope;
public:
    std::atomic<bool> active{false};
    void observe(void *pointer) noexcept { value = pointer; }
    void begin();
    ~NativeDeletionObserver();
};

static void discard_value(BqtValue &value);
static void native_model_forget(uint32_t id);
static void value_guard_forget(uint32_t id);
static void dismiss_native_guards(uint32_t id);
static uint32_t finish_value_ownership(BqtRequest *, uint32_t);
static uint32_t finish_borrowed_value_ownership(BqtRequest *, uint32_t);
static uint32_t finish_resource_value_ownership(BqtRequest *, uint32_t);
static uint32_t finish_metadata_ownership(BqtRequest *, uint32_t);
static uint32_t finish_role_span_ownership(BqtRequest *, uint32_t);
static uint32_t finish_model_index_ownership(BqtRequest *, uint32_t);
static void model_index_forget(uint32_t);
static uint32_t finish_generic_argument_ownership(BqtRequest *, uint32_t);
static void generic_argument_forget(uint32_t);
static uint32_t finish_boundary_finder_ownership(BqtRequest *, uint32_t);
static uint32_t finish_take_row_ownership(BqtRequest *, uint32_t);
static void take_row_native_deleted(uint32_t);
static uint32_t finish_value_provenance(BqtRequest *, uint32_t);
static bool value_provenance_validate(BqtRequest *, uint32_t);
static bool aggregate_validate(BqtRequest *, uint32_t);
static void aggregate_forget(uint32_t);
static uint32_t finish_aggregate_ownership(BqtRequest *, uint32_t);
static void video_buffers_forget(uint32_t);
static uint32_t finish_video_ownership(BqtRequest *, uint32_t);
static uint32_t finish_lazy_value_ownership(BqtRequest *, uint32_t);
static void lazy_value_forget(uint32_t);
static void pointer_fields_forget(uint32_t);
static uint32_t finish_pointer_field_ownership(BqtRequest *, uint32_t);
static void value_provenance_before_invalidate(uint32_t);
static void boundary_finder_forget(uint32_t);
static bool has_boundary_backing(uint32_t);
static void mark_callback_ephemeral_value(uint32_t);
static void finish_callback_ephemeral_value(uint32_t);

// Ends a connection and gives its handler back to Bend.
static void close_connection(Connection &c)
{
    if (c.connection) {
        QObject::disconnect(*c.connection);
        delete c.connection;
        c.connection = nullptr;
    }
    delete c.context;
    c.context = nullptr;
    auto handler = c.handler;
    c.handler = 0;
    c.sender = 0;
    c.active = false;
    if (++c.generation == 0)
        c.retired = true;
    if (handler && bend) bend->release(handler);
}

static void connection_terminal(Connection &c, uint32_t identity);
static void invalidate(uint32_t id);
static void dispatch_terminal_connections(uint32_t id) {
    for (auto &c : connections) {
        if (!c.active || c.sender != id || !c.terminal) continue;
        c.terminal = false;
        connection_terminal(c, id);
    }
}

static void invalidate_now(uint32_t id)
{
    auto *e = entry(id);
    if (!e)
        return;
    e->deferred_invalidation = false;
    e->deferred_scope = nullptr;
    dynamic_properties_forget(id);
    native_pointer_forget(id);
    static_native_view_forget(id);
    value_provenance_before_invalidate(id);
    aggregate_forget(id);
    video_buffers_forget(id);
    lazy_value_forget(id);
    pointer_fields_forget(id);
    rhi_forget(id);
    dismiss_native_guards(id);
    native_model_forget(id);
    value_guard_forget(id);
    model_index_forget(id);
    generic_argument_forget(id);
    boundary_finder_forget(id);
    e->value = nullptr;
    e->object = nullptr;
    e->owned = false;
    e->scope_owner = 0;
    e->dynamic_state = nullptr;
    e->pending_release = false;
    e->active_calls = 0;
    if (e->alive) (*e->alive)->store(false, std::memory_order_release);
    delete e->alive;
    e->alive = nullptr;
    e->proxy = false;
    e->handlers = nullptr;
    e->native_owner = 0;
    e->cast = nullptr;
    // Child invalidation, terminal handlers and collection may register a new
    // object in this now-empty slot. Retire the old identity before reentry.
    if (++e->generation == 0)
        e->retired = true;
    for (uint32_t i = 1; i < capacity; ++i)
        if (entries[i].value && entries[i].native_owner == id)
            invalidate(token(i, entries[i].generation));
    for (auto &edge : retentions) {
        if (edge.owner == id) edge = {};
        else if (edge.target == id) edge.target = 0;
    }
    for (uint32_t i = 1; i < capacity; ++i) {
        auto &alias = entries[i];
        if (!alias.value || !alias.shared_managed) continue;
        uint32_t alias_id = token(i, alias.generation);
        bool held = false;
        for (const auto &edge : retentions)
            if (edge.slot == shared_holder_slot && edge.target == alias_id && entry(edge.owner)) { held = true; break; }
        if (!held && !(alias.native_observed && alias.proxy)) invalidate(alias_id);
    }
    schedule_collection();
    for (auto &c : connections) {
        if (!c.active || c.sender != id) continue;
        const auto generation = c.generation;
        if (c.terminal) { c.terminal = false; connection_terminal(c, id); }
        if (c.active && c.generation == generation && c.sender == id) close_connection(c);
    }
}

static void invalidate(uint32_t id)
{
    auto *e = entry(id);
    if (!e) return;
    if (native_destruction_scope || native_pointer_destructing(id)) {
        // Retain dependency and handler roots until all native base/child
        // destructors have completed, including reentrant event processing.
        if (!e->deferred_invalidation || !e->deferred_scope) e->deferred_scope = native_destruction_scope;
        e->deferred_invalidation = true;
        e->destroying = true;
        if (e->alive) (*e->alive)->store(false, std::memory_order_release);
        e->object = nullptr; e->parent = nullptr;
        if (!native_pointer_destructing(id)) dispatch_terminal_connections(id);
        return;
    }
    invalidate_now(id);
}

static void flush_native_destruction(NativeDestructionScope *scope)
{
    if (scope->flushing) return;
    struct Guard { bool &value; ~Guard() { value = false; } } guard{scope->flushing};
    scope->flushing = true;
    bool changed;
    do {
        changed = false;
        for (uint32_t i = 1; i < capacity; ++i)
            if (entries[i].value && entries[i].deferred_invalidation && entries[i].deferred_scope == scope) {
                if (native_pointer_destructing(token(i, entries[i].generation))) {
                    entries[i].deferred_scope = nullptr;
                    continue;
                }
                invalidate_now(token(i, entries[i].generation)); changed = true;
            }
    } while (changed);
}

static void invalidate_native_children(uint32_t owner)
{
    for (uint32_t i = 1; i < capacity; ++i)
        if (entries[i].value && entries[i].native_owner == owner)
            invalidate(token(i, entries[i].generation));
}

static bool set_native_owner(BqtRequest *r, uint32_t child, uint32_t owner)
{
    if (!child) return true;
    if (!can_transfer_handle(r, child)) return false;
    auto *e = entry(child);
    if (!e || (owner && !entry(owner))) {
        fail(r, ESTALE, "Invalid native owner or object");
        return false;
    }
    if (owner && reaches_token(child, owner)) {
        fail(r, ELOOP, "Native Qt ownership would create a cycle");
        return false;
    }
    e->native_owner = owner;
    e->owned = !owner && e->destroy && (!e->object || (e->object != application && !e->object->parent()));
    return true;
}

static uint32_t __attribute__((noinline)) insert(BqtRequest *r, void *value, QObject *object,
                       uint16_t type, void (*destroy)(void *), bool owned,
                       void *(*cast)(void *, uint16_t) = nullptr)
{
    if (!value)
        return 0;
    QObject *observed_parent = nullptr;
    if (object) {
        if (object->thread() != main_thread) {
            fail(r, EXDEV, "Qt object belongs to another thread");
            return 0;
        }
        observed_parent = object->parent();
        for (uint32_t i = 1; i < capacity; ++i)
            if (entries[i].value && entries[i].object == object) {
                const auto previous_id = token(i, entries[i].generation);
                if (native_pointer_destructing(previous_id)) {
                    fail(r, ESTALE, "Qt object native destruction is still in progress");
                    return 0;
                }
                if (entries[i].destroying || (entries[i].alive && !(*entries[i].alive)->load(std::memory_order_acquire))) {
                    // Worker completion queues exact old tokens. An address
                    // reused before that queue runs is a new QObject identity.
                    invalidate(previous_id);
                    // Terminal handlers may have registered the replacement
                    // reentrantly in an earlier slot. Search from the start.
                    i = 0;
                    continue;
                }
                if (owned) {
                    if (!can_transfer_handle(r, token(i, entries[i].generation))) return 0;
                    if (!entries[i].destroy) {
                        entries[i].value = value;
                        entries[i].destroy = destroy;
                        entries[i].cast = cast;
                        entries[i].type = type;
                    }
                    entries[i].read_only = false;
                    entries[i].owned = destroy && object != application && observed_parent == nullptr;
                    entries[i].pending_release = false;
                    if (entries[i].owned && !entries[i].scope_owner)
                        entries[i].scope_owner = scope_track(r, token(i, entries[i].generation), 0);
                }
                const auto id = token(i, entries[i].generation);
                native_pointer_publish(id);
                return id;
            }
    }
    std::shared_ptr<std::atomic<bool>> alive;
    std::unique_ptr<std::shared_ptr<std::atomic<bool>>> alive_slot;
    if (object) {
        alive = std::make_shared<std::atomic<bool>>(true);
        alive_slot = std::make_unique<std::shared_ptr<std::atomic<bool>>>(alive);
    }
    for (uint32_t i = 1; i < capacity; ++i) {
        auto &e = entries[i];
        if (!e.value && !e.retired) {
            e.slot_index = uint16_t(i);
            if (!e.generation) e.generation = 1;
            e.value = value;
            e.scope_owner = 0;
            e.dynamic_state = nullptr;
            e.object = object;
            e.parent = observed_parent;
            e.type = type;
            e.destroy = destroy;
            e.owned = owned && destroy && (!object || (object != application && !observed_parent));
            e.pending_release = false;
            e.active_calls = 0;
            e.alive = alive_slot.release();
            e.proxy = false;
            e.handlers = nullptr;
            e.destroying = false;
            e.deferred_invalidation = false;
            e.deferred_scope = nullptr;
            e.native_owner = 0;
            e.cast = cast;
            e.read_only = false;
            e.native_observed = object != nullptr;
            e.shared_managed = false;
            e.render_only = render_type(type);
            e.render_window = e.render_only ? gui_render_window : 0;
            e.graphics_context = 0;
            e.file_mappings = 0;
            e.shared_memory_writable = false;
            e.text_epoch = 0;
            e.text_observed = false;
            e.text_edit_depth = 0;
            e.validate = nullptr;
            const uint32_t id = token(i, e.generation);
            try {
            native_pointer_publish(id);
            if (object) {
                // The registry must outlive QApplication's receiver connections:
                // its QObject destructor disconnects them before deleting children.
                auto *registry_thread = main_thread;
                auto *final_observer = dynamic_cast<NativeDeletionObserver *>(object);
                QObject::connect(object, &QObject::destroyed, [id, registry_thread, alive, final_observer] {
                    // An object moved to another thread is destroyed there. The
                    // flag stops every later use at once; the registry itself
                    // changes only on the main thread.
                    alive->store(false, std::memory_order_release);
                    if (final_observer && final_observer->active.load(std::memory_order_acquire)) return;
                    if (QThread::currentThread() == registry_thread) invalidate(id);
                    else if (auto *context = main_context.load(std::memory_order_acquire)) QMetaObject::invokeMethod(context, [id] { invalidate(id); }, Qt::QueuedConnection);
                });
                if (auto *thread = qobject_cast<QThread *>(object))
                    if (auto *context = main_context.load(std::memory_order_acquire))
                        QObject::connect(thread, &QThread::finished, context, [] { schedule_collection(); }, Qt::QueuedConnection);
            }
            if (!attach_graphics_context(r, id) || !attach_rhi_identity(r, id)) {
                invalidate(id);
                if (owned && destroy) destroy(value);
                return 0;
            }
            if (e.owned) e.scope_owner = scope_track(r, id, 0);
            return id;
            } catch (...) {
                // Registration owns only the slot. The calling owning helper
                // owns native deletion.
                invalidate(id);
                throw;
            }
        }
    }
    if (grow_registry()) return insert(r, value, object, type, destroy, owned, cast);
    fail(r, ENOSPC, "Qt object token range is exhausted");
    if (owned) destroy(value);
    return 0;
}

template<class T> struct NativeTraits {
    static constexpr bool object = false;
    static constexpr bool observable = false;
    static void *cast(void *, uint16_t) { return nullptr; }
};

struct AccessibleFacet { int kind = -1; uint32_t target = 0; void *pointer = nullptr; };

struct NativeFileMapping {
    uint32_t owner;
    QPointer<QFileDevice> file;
    uchar *address = nullptr;
    qint64 offset;
    bool active = false;
    NativeFileMapping(uint32_t id, QFileDevice *source, qint64 start)
        : owner(id), file(source), offset(start)
    { if (auto *e = entry(owner)) ++e->file_mappings; }
    ~NativeFileMapping() {
        if (active && file) file->unmap(address);
        if (auto *e = entry(owner)) --e->file_mappings;
    }
};

struct NativeGLMapping;
struct NativeRawGLMapping;
struct NativeRhiMapping;
struct MemoryView {
    uint32_t owner;
    void *address;
    size_t size;
    int auxiliary;
    bool readonly;
    bool (*observe)(BqtRequest *, const MemoryView &, bool);
    std::shared_ptr<NativeFileMapping> mapping;
    std::shared_ptr<NativeGLMapping> gl_mapping;
    bool readable = true;
    std::shared_ptr<NativeRawGLMapping> raw_gl_mapping;
    std::shared_ptr<NativeRhiMapping> rhi_mapping;
};

template<class T> static constexpr auto native_deleter() -> void (*)(void *)
{
    if constexpr (std::is_destructible_v<T>) return [](void *p) { delete static_cast<T *>(p); };
    else return nullptr;
}

static void native_deleted(void *value)
{
    auto identities = native_pointer_died(value);
    if (QThread::currentThread() != main_thread) {
        if (identities.empty()) return;
        if (auto *context = main_context.load(std::memory_order_acquire))
            QMetaObject::invokeMethod(context, [identities = std::move(identities)] {
                for (auto id : identities) if (entry(id)) {
                    take_row_native_deleted(id);
                    invalidate(id);
                }
            }, Qt::QueuedConnection);
        return;
    }
    for (auto id : identities) if (entry(id)) {
        take_row_native_deleted(id);
        invalidate(id);
    }
    // Values without public native aliases or QObject identity need no worker
    // index. Complete all matching main-thread identities, including views.
    for (uint32_t i = 1; i < capacity; ++i)
        if (entries[i].value == value && !entries[i].deferred_invalidation) {
            auto id = token(i, entries[i].generation);
            take_row_native_deleted(id);
            invalidate(id);
        }
}

void NativeDeletionObserver::begin() {
    if (!value || active.exchange(true, std::memory_order_acq_rel)) return;
    scope.emplace();
    native_pointer_destroying(value);
    if (QThread::currentThread() == main_thread)
        for (auto &record : entries) if (record.value == value) record.destroying = true;
}
NativeDeletionObserver::~NativeDeletionObserver() {
    if (value) native_deleted(value);
    scope.reset();
}

template<class T> class NativeTracked : public NativeDeletionObserver, public T {
public:
    template<class... A> explicit NativeTracked(A&&... args) : T(std::forward<A>(args)...) {
        NativeDeletionObserver::observe(static_cast<T *>(this));
    }
    ~NativeTracked() override { NativeDeletionObserver::begin(); }
};

// This exact allocation has an accessible derived deleter even when T's
// protected destructor is nonvirtual. It cannot observe deletion through an
// arbitrary native base pointer and is never marked externally observable.
template<class T> class NativeConstructed : public NativeDeletionObserver, public T {
public:
    template<class... A> explicit NativeConstructed(A&&... args) : T(std::forward<A>(args)...) {
        NativeDeletionObserver::observe(static_cast<T *>(this));
    }
    ~NativeConstructed() { NativeDeletionObserver::begin(); }
};

// @NATIVE_OBJECTS@

template<class T> static T *__attribute__((noinline)) get(BqtRequest *r, uint32_t id, uint16_t type, bool nullable = false, bool writable = true, bool validate = true)
{
    if (!id && nullable)
        return nullptr;
    auto *e = entry(id);
    if (!e) {
        fail(r, ESTALE, "Invalid or destroyed Qt object handle");
        return nullptr;
    }
    if (e->alive && !(*e->alive)->load(std::memory_order_acquire)) {
        fail(r, ESTALE, "Qt object has been destroyed");
        return nullptr;
    }
    if (e->object && e->object->thread() != main_thread) {
        fail(r, EXDEV, "Qt object belongs to another thread"); return nullptr;
    }
    if (e->destroying) { fail(r, EBUSY, "Qt object destruction is in progress"); return nullptr; }
    if (validate && !rhi_validate_dependencies(r, id)) return nullptr;
    if (validate && !value_provenance_validate(r, id)) return nullptr;
    if (validate && !aggregate_validate(r, id)) return nullptr;
    e = entry(id);
    if (!e) { fail(r, ESTALE, "Qt aggregate owner expired during validation"); return nullptr; }
    if (validate && e->validate) {
        if (!e->validate(r, id)) return nullptr;
        e = entry(id);
        if (!e) { fail(r, ESTALE, "Qt native view expired during validation"); return nullptr; }
    }
    if (writable && e->read_only) {
        fail(r, EPERM, "Qt handle is a const native view");
        return nullptr;
    }
    if constexpr (std::is_base_of_v<QObject, T>) {
        T *object = nullptr;
        if constexpr (QtPrivate::HasQ_OBJECT_Macro<T>::Value)
            object = e->object ? qobject_cast<T *>(e->object) : nullptr;
        else if (e->object && e->type == type)
            object = static_cast<T *>(e->value);
        if (!object) fail(r, EINVAL, "Qt object handle has the wrong type");
        else if (object->thread() != main_thread) {
            fail(r, EXDEV, "Qt object belongs to another thread");
            return nullptr;
        }
        if (object && !r->error && native_call_scope) native_call_scope->pin(r, id);
        return object;
    } else {
        if constexpr (NativeTraits<T>::object) {
            auto *value = e->cast ? static_cast<T *>(e->cast(e->value, type)) : nullptr;
            if (!value) fail(r, EINVAL, "Qt native object handle has the wrong type");
            else if (native_call_scope) native_call_scope->pin(r, id);
            return value;
        }
        if (e->object || e->type != type) {
            fail(r, EINVAL, "Qt value handle has the wrong type");
            return nullptr;
        }
        if (native_call_scope) native_call_scope->pin(r, id);
        return static_cast<T *>(e->value);
    }
}

template<class T> static uint32_t __attribute__((noinline)) own(BqtRequest *r, T *value, uint16_t type)
{
    if constexpr (NativeTraits<T>::object && !std::is_base_of_v<QObject, T>) {
        for (uint32_t i = 1; value && i < capacity; ++i) {
            auto &e = entries[i];
            if (e.value && e.cast && e.cast(e.value, type) == value) {
                if (!can_transfer_handle(r, token(i, e.generation))) return 0;
                if (!e.destroy) {
                    e.value = value;
                    e.type = type;
                    e.destroy = native_deleter<T>();
                    e.cast = NativeTraits<T>::cast;
                }
                e.read_only = false;
                e.owned = true;
                if (!e.scope_owner) e.scope_owner = scope_track(r, token(i, e.generation), 0);
                e.pending_release = false;
                e.native_owner = 0;
                native_model_forget(token(i, e.generation));
                native_pointer_publish(token(i, e.generation));
                return token(i, e.generation);
            }
        }
    }
    QObject *object = nullptr;
    if constexpr (std::is_base_of_v<QObject, T>) object = value;
    static_assert(std::is_destructible_v<T>, "Owning a Qt value requires an accessible native destructor");
    uint32_t id;
    try {
        id = insert(r, value, object, type, native_deleter<T>(), true, NativeTraits<T>::cast);
    } catch (...) {
        for (uint32_t i = 1; i < capacity; ++i)
            if (entries[i].value == value) invalidate(token(i, entries[i].generation));
        delete value;
        throw;
    }
    try {
        return finish_lazy_value_ownership(r, finish_video_ownership(r, finish_pointer_field_ownership(r, finish_aggregate_ownership(r, finish_value_provenance(r, finish_take_row_ownership(r, finish_boundary_finder_ownership(r, finish_generic_argument_ownership(r, finish_model_index_ownership(r, finish_role_span_ownership(r, finish_metadata_ownership(r, finish_resource_value_ownership(r, finish_borrowed_value_ownership(r, finish_value_ownership(r, id))))))))))))));
    } catch (...) {
        // The result is not yet in r->result, so dispatch cannot roll it back.
        // Hooks may already have removed it; check the original generation.
        if (auto *e = entry(id); e && e->owned && e->value == value) {
            auto destroy = e->destroy;
            invalidate(id);
            if (destroy) destroy(value);
        }
        throw;
    }
}

// Only constructors use this path. An arbitrary native T* is never assumed to
// have the derived layout or accessible destructor of our observing subclass.
template<class T, class Derived> static uint32_t own_derived(BqtRequest *r, Derived *value, uint16_t type)
{
    static_assert(std::is_base_of_v<T, Derived>);
    static_assert(std::is_destructible_v<Derived>);
    QObject *object = nullptr;
    if constexpr (std::is_base_of_v<QObject, T>) object = value;
    auto destroy = +[](void *p) { delete static_cast<Derived *>(static_cast<T *>(p)); };
    uint32_t id;
    try { id = insert(r, static_cast<T *>(value), object, type, destroy, true, NativeTraits<T>::cast); }
    catch (...) {
        // insert owns ordinary failure cleanup, but an exception can occur
        // before it returns the newly registered identity to this caller.
        for (uint32_t i = 1; i < capacity; ++i)
            if (entries[i].value == static_cast<T *>(value)) invalidate(token(i, entries[i].generation));
        delete value;
        throw;
    }
    if (auto *e = entry(id)) e->native_observed = std::has_virtual_destructor_v<T>;
    return id;
}

template<class T> static uint32_t __attribute__((noinline)) borrow(BqtRequest *r, T *value, uint16_t type)
{
    if (!value) return 0;
#if defined(BQT_HAS_GUI)
    if constexpr (std::is_same_v<std::remove_const_t<T>, QAccessibleInterface>) {
        return NativeFunctionCallbacks::accessible_borrow(r, value);
    } else
#endif
    if constexpr (std::is_base_of_v<QObject, T>) {
        auto id = insert(r, value, value, type, native_deleter<T>(), false,
                         NativeTraits<T>::cast);
        // A mutable native return establishes writable storage. Pure Bend
        // upcasts keep the same token and never pass through this operation.
        if (auto *e = entry(id)) e->read_only = false;
        return id;
    }
    else {
        static_assert(NativeTraits<T>::object);
        for (uint32_t i = 1; i < capacity; ++i) {
            auto &e = entries[i];
            if (e.value && e.cast && e.cast(e.value, type) == value) {
                e.read_only = false;
                return token(i, e.generation);
            }
        }
        uint32_t rhi_result = 0;
        if (borrow_rhi_identity(r, value, type, NativeTraits<T>::cast, native_deleter<T>(), &rhi_result)) return rhi_result;
        if constexpr (std::is_polymorphic_v<T>) {
            // Interfaces such as QSurface can be implemented by a QObject.
            // Its real destruction notification establishes the native origin.
            if (auto *object = dynamic_cast<QObject *>(value))
                return insert(r, value, object, type, native_deleter<T>(), false, NativeTraits<T>::cast);
        }
        fail(r, ENOTSUP, "Native Qt object needs an observable owner before borrowing");
        return 0;
    }
}

template<class T> static uint32_t __attribute__((noinline)) register_native_borrow(BqtRequest *r, T *value,
                                                        uint16_t type, uint32_t owner)
{
    if (!value) return 0;
    for (uint32_t i = 1; i < capacity; ++i) {
        auto &e = entries[i];
        if (e.value && e.cast && e.cast(e.value, type) == value) {
            if constexpr (!std::is_const_v<T>) e.read_only = false;
            return token(i, e.generation);
        }
    }
    if (!owner || !entry(owner)) {
        fail(r, ESTALE, "Borrowed native Qt object has no observable owner");
        return 0;
    }
    using Value = std::remove_const_t<T>;
    // A non-QObject base (notably QPaintDevice) can refer to a QWidget. Keep
    // Qt's real destruction observer instead of assuming the getter owns it.
    QObject *object = nullptr;
    if constexpr (std::is_polymorphic_v<Value>) object = dynamic_cast<QObject *>(const_cast<Value *>(value));
    auto id = insert(r, const_cast<Value *>(value), object, type,
                     native_deleter<Value>(), false, NativeTraits<Value>::cast);
    if (id && !object && !set_native_owner(r, id, owner)) { invalidate(id); return 0; }
    if (id) entry(id)->read_only = std::is_const_v<T>;
    return id;
}

template<class T> static uint32_t __attribute__((noinline)) borrow_const(BqtRequest *r, const T *value, uint16_t type)
{
    if (!value) return 0;
#if defined(BQT_HAS_GUI)
    if constexpr (std::is_same_v<T, QAccessibleInterface>)
        return NativeFunctionCallbacks::accessible_borrow(r, value);
#endif
    for (uint32_t i = 1; i < capacity; ++i) {
        auto &e = entries[i];
        if (!e.value) continue;
        if constexpr (std::is_base_of_v<QObject, T>) {
            if (e.object == value) return token(i, e.generation);
        } else if (e.cast && e.cast(e.value, type) == value) return token(i, e.generation);
    }
    auto id = borrow(r, const_cast<T *>(value), type);
    if (id) entry(id)->read_only = true;
    return id;
}

static void mark_native_observed(uint32_t id)
{
    if (auto *e = entry(id)) e->native_observed = true;
}

template<class T> static uint32_t __attribute__((noinline)) borrow_shared(BqtRequest *r, T *value, uint16_t type, uint32_t holder)
{
    if (!value) return 0;
    if (!entry(holder)) { fail(r, ESTALE, "Shared Qt holder was destroyed"); return 0; }
    uint32_t id = 0;
    for (uint32_t i = 1; i < capacity; ++i) {
        auto &e = entries[i];
        if (!e.value) continue;
        bool same;
        if constexpr (std::is_base_of_v<QObject, T>) same = e.object == value;
        else same = e.cast && e.cast(e.value, type) == value;
        if (same) { id = token(i, e.generation); break; }
    }
    int slot = -1;
    for (uint32_t i = 0; i < capacity; ++i) {
        const auto &edge = retentions[i];
        if (id && edge.owner == holder && edge.slot == shared_holder_slot && edge.target == id) return id;
        if (!edge.owner && !retention_reserved[i] && slot < 0) slot = int(i);
    }
    if (slot < 0) {
        uint32_t previous = capacity;
        if (grow_registry()) slot = int(previous);
        else { fail(r, ENOSPC, "Shared Qt holder token range is exhausted"); return 0; }
    }
    if (!id) {
        QObject *object = nullptr;
        if constexpr (std::is_base_of_v<QObject, T>) object = value;
        id = insert(r, value, object, type, native_deleter<T>(), false, NativeTraits<T>::cast);
        if (!id) return 0;
    }
    auto *e = entry(id);
    e->owned = false;
    e->native_owner = 0;
    e->shared_managed = true;
    commit_retention(slot, holder, shared_holder_slot, id, id, nullptr);
    return id;
}

static uint32_t register_memory_view(BqtRequest *r, const MemoryView &value, uint16_t type)
{
    if (!value.address) return 0;
    if (!entry(value.owner)) { fail(r, ESTALE, "Memory view owner was destroyed"); return 0; }
    auto id = own(r, new MemoryView(value), type);
    if (!id) return 0;
    BqtRequest claim{};
    claim.self = id;
    constexpr uint32_t memory_owner_slot = 0xffffffed;
    int slot = prepare_retention(&claim, memory_owner_slot, 0, value.owner);
    if (claim.error) {
        BqtRequest rollback{}; rollback.self = id;
        auto *e = entry(id);
        auto *storage = e->value;
        auto destroy = e->destroy;
        invalidate(id);
        destroy(storage);
        fail(r, claim.error, claim.message);
        return 0;
    }
    commit_retention(slot, id, memory_owner_slot, 0, value.owner, nullptr);
    return id;
}

static BqtValue string_value(const QString &text)
{
    const QByteArray utf8 = text.toUtf8();
    BqtValue result{};
    result.tag = 1;
    result.size = size_t(utf8.size());
    result.text = static_cast<char *>(std::malloc(result.size + 1));
    if (!result.text) std::abort();
    std::memcpy(result.text, utf8.constData(), result.size);
    result.text[result.size] = '\0';
    return result;
}

static uint32_t new_connection(BqtRequest *r, uint32_t handler)
{
    for (uint32_t i = 1; i < capacity; ++i) {
        auto &c = connections[i];
        if (!c.active && !c.retired) {
            if (!c.generation) c.generation = 1;
            c.scope_owner = scope_track(r, token(i, c.generation), 1);
            c.active = true;
            c.sender = r->self;
            c.handler = handler;
            c.connection = nullptr;
            c.context = nullptr;
            c.terminal = false;
            return token(i, c.generation);
        }
    }
    if (grow_registry()) return new_connection(r, handler);
    fail(r, ENOSPC, "Qt connection token range is exhausted");
    return 0;
}

static bool destroy_object(BqtRequest *r)
{
    auto *e = entry(r->self);
    if (!e) return fail(r, ESTALE, "Invalid or destroyed Qt object handle");
    if (e->destroying) return fail(r, EBUSY, "Qt object destruction is already in progress");
    if (!rhi_cleanup_operation(r, r->self)) return true;
    if (e->alive && !(*e->alive)->load(std::memory_order_acquire)) {
        invalidate(r->self);
        return fail(r, ESTALE, "Qt object has been destroyed");
    }
    if (!e->owned) return fail(r, EPERM, "Cannot destroy a borrowed Qt object");
    if (e->render_only && !gui_render_depth) return fail(r, EBUSY, "Scene graph destruction requires a GUI render callback");
    if (!graphics_context_ready(r->self)) return fail(r, EBUSY, "OpenGL destruction requires its current or sharing context");
    if (!rhi_release_ready(r->self)) return fail(r, EBUSY, "RHI destruction requires the current frame to be submitted");
    if (active_in_subtree(r->self)) return fail(r, EBUSY, "Qt object is in an active native call");
    if (retained(r->self)) return fail(r, EBUSY, "Qt still retains this object or its children");
    if (!cursor_guard_cleanup_ready(r, r->self)) return true;
    e = entry(r->self);
    if (!e) return fail(r, ESTALE, "Qt object expired during cleanup");
    NativeDestructionScope destruction;
    // Public access stops now; dependency roots survive native base teardown.
    e->destroying = true;
    if (e->object) {
        for (uint32_t i = 1; i < capacity; ++i)
            if (entries[i].value && entry_inside(token(i, entries[i].generation), r->self)) entries[i].destroying = true;
        e->destroy(e->value);
        invalidate(r->self);
    }
    else {
        auto *value = e->value;
        auto destroy = e->destroy;
        if (rhi_destroy_root(r)) return true;
        destroy(value);
        invalidate(r->self);
    }
    return true;
}

static bool release_object(BqtRequest *r)
{
    auto *e = entry(r->self);
    if (!e) return fail(r, ESTALE, "Invalid or destroyed Qt object handle");
    if (e->destroying) return true;
    if (!rhi_cleanup_operation(r, r->self)) return true;
    if (e->alive && !(*e->alive)->load(std::memory_order_acquire)) {
        invalidate(r->self);
        return fail(r, ESTALE, "Qt object has been destroyed");
    }
    if (cursor_guard_defer_release(r, r->self)) return true;
    if (e->destroy == release_static_native_view) {
        if (retained(r->self) || active_in_subtree(r->self)) e->pending_release = true;
        else invalidate(r->self);
        return true;
    }
    if (e->owned && !graphics_context_ready(r->self)) { e->pending_release = true; return true; }
    if (e->owned && !rhi_release_ready(r->self)) { e->pending_release = true; return true; }
    if (e->owned && e->render_only && !gui_render_depth) {
        e->pending_release = true;
        schedule_render_collection(r->self);
        return true;
    }
    switch (lifetime_scoped[unsigned(e->owned) * 2 + unsigned(retained(r->self) || active_in_subtree(r->self))]) {
    case 1: return destroy_object(r);
    case 2: e->pending_release = true; return true;
    default: return true;
    }
}

static void collect_pending()
{
    static bool collecting = false;
    if (collecting) return;
    collecting = true;
    struct Reset { bool &value; ~Reset() { value = false; } } reset{collecting};
    bool changed;
    do {
        changed = false;
        for (uint32_t i = 1; i < capacity; ++i) {
            auto &e = entries[i];
            if (!e.value || !e.pending_release || e.destroying) continue;
            if (e.render_only && !gui_render_depth) continue;
            uint32_t id = token(i, e.generation);
            if (e.destroy == release_static_native_view) {
                if (!retained(id) && !active_in_subtree(id)) { invalidate(id); changed = true; }
                continue;
            }
            if (!graphics_context_ready(id)) continue;
            if (!rhi_release_ready(id)) continue;
            if (!lifetime_collect[4 + unsigned(e.owned) * 2 + unsigned(retained(id) || active_in_subtree(id))]) continue;
            BqtRequest release{}; release.self = id;
            destroy_object(&release);
            if (!release.error) changed = true;
        }
    } while (changed);
}

static void schedule_collection() noexcept
{
    // QObject::destroyed runs before its native destructor is finished. Never
    // destroy its retained arguments from that callback's stack.
    static bool scheduled = false;
    if (scheduled || !application) return;
    scheduled = true;
    try {
        if (!QMetaObject::invokeMethod(application, []() noexcept {
            scheduled = false;
            try {
                reconcile_parents();
                reconcile_retentions();
                collect_pending();
            } catch (...) {
                // This is a maintenance pass inside a Qt event loop. Every
                // Bend call and the final teardown also collect pending
                // entries. Leave them eligible for those checked retry paths.
            }
        }, Qt::QueuedConnection)) scheduled = false;
    } catch (...) {
        // Posting may allocate. Invalidation and pin release must finish even
        // when the optional wakeup fails, and a later wakeup must be admitted.
        scheduled = false;
    }
}

// Rolls back copied value handles. Normal delivery transfers ownership to
// Bend; the C effect then frees only memory.
static void discard_value(BqtValue &value)
{
    for (size_t i = 0; i < value.count; ++i) discard_value(value.items[i]);
    if (value.owned_data) OpaqueData::release(value.owned_data);
    if (value.owned_handle && entry(value.owned_handle)) {
        BqtRequest release{};
        release.self = value.owned_handle;
        destroy_object(&release);
    }
    std::free(value.items);
    std::free(value.text);
    value = {};
}

static BqtValue sequence_value(size_t count)
{
    BqtValue value{};
    value.tag = 2;
    value.count = count;
    value.items = static_cast<BqtValue *>(std::calloc(count, sizeof(BqtValue)));
    if (count && !value.items) std::abort();
    return value;
}

static bool wire_shape(BqtRequest *r, const BqtValue &value, uint32_t tag, size_t count = SIZE_MAX)
{
    if (value.tag == tag && (count == SIZE_MAX || value.count == count)) return true;
    fail(r, EINVAL, "Malformed Qt container payload");
    return false;
}

// A Qt operation that waits: it runs a Qt event loop until `ready` answers
// true or the deadline passes, as Qt's own waiting operations do. Qt keeps
// processing events and Bend's other computations keep running meanwhile.
// The result word is whether `ready` answered true.
static bool wait_until(BqtRequest *r, std::function<bool()> ready, QDeadlineTimer deadline,
                       std::function<void(BqtRequest *)> finish = {})
{
    bool value = ready();
    if (!value && !deadline.hasExpired()) {
        if (r->self && !callback_pin(r, r->self)) return true;
        struct Unpin { uint32_t id; ~Unpin() { if (id) callback_unpin(id); } } unpin{r->self};
        QEventLoop loop;
        QTimer timer;
        int error = 0;
        QObject::connect(&timer, &QTimer::timeout, &loop, [&] {
            try {
                value = ready();
            } catch (const std::bad_alloc &) { error = ENOMEM; }
              catch (...) { error = EFAULT; }
            if (value || error || deadline.hasExpired()) loop.quit();
        });
        // A failed Bend handler ends the wait: the operation fails with it.
        auto *frame = CallFrame::current;
        auto *outer = frame ? frame->loop : nullptr;
        if (frame) frame->loop = &loop;
        timer.start(1);
        loop.exec();
        if (frame) frame->loop = outer;
        if (error) return fail(r, error, "A Qt wait raised a native exception");
        if (frame && frame->handler_error) return true;
    }
    r->result.word = value;
    if (finish) finish(r);
    return true;
}

static bool disconnect_signal(BqtRequest *r)
{
    auto *c = connection(r->self);
    if (!c) return fail(r, ESTALE, "Invalid or closed Qt connection");
    close_connection(*c);
    return true;
}

static int application_argc;
static char **application_argv;

enum ApplicationKind : int { CoreApplication = 0, GuiApplication = 1, WidgetsApplication = 2 };

static int application_kind() {
    if (!application) return -1;
    if (application->inherits("QApplication")) return WidgetsApplication;
    if (application->inherits("QGuiApplication")) return GuiApplication;
    return CoreApplication;
}

// Constructs the program's single application object from Bend's argv. Qt
// keeps argc and argv for the application's lifetime and removes the options
// it recognizes, so it gets the runtime's own copy. Returns an error or null.
static const char *construct_application(int kind) {
    if (application) return "The Qt application object already exists; construct it once";
    try {
        // Each kind is constructed by the native group that owns its class.
        if (kind == WidgetsApplication) {
#if defined(BQT_HAS_WIDGETS)
            application = new BendApplication<QApplication>(application_argc, application_argv);
#else
            return "This native group cannot construct a QApplication";
#endif
        } else if (kind == GuiApplication) {
#if defined(BQT_HAS_GUI)
            application = new BendApplication<QGuiApplication>(application_argc, application_argv);
#else
            return "This native group cannot construct a QGuiApplication";
#endif
        } else application = new BendApplication<QCoreApplication>(application_argc, application_argv);
        if (bend && bend->runtime_root)
            QCoreApplication::setLibraryPaths({QString::fromUtf8(bend->runtime_root) + QStringLiteral("/plugins")});
        if (application_constructed) application_constructed();
    } catch (const std::bad_alloc &) {
        return "Cannot allocate the Qt application";
    }
    return nullptr;
}

static bool create_application(BqtRequest *r, int kind, uint32_t type) {
    if (application) return fail(r, EEXIST, "The Qt application object already exists; construct it once");
    if (const char *error = construct_application(kind)) return fail(r, ENOMEM, error);
    r->result.word = borrow(r, application, type);
    return true;
}

// Constructors and functions of classes from modules that need a GUI
// application call this first: Qt aborts the process instead of failing when,
// for example, a QWidget is created before a QApplication.
static bool require_application(BqtRequest *r, int kind) {
    if (application_kind() >= kind) return true;
    fail(r, ENXIO, kind == WidgetsApplication
        ? "Construct a QApplication (Qt.QApplication.new) before using QtWidgets"
        : "Construct a QGuiApplication or QApplication (Qt.QGuiApplication.new) before using this Qt GUI API");
    return false;
}


// @DISPATCH@

// While Qt waits for events, Bend's waiting computations must still wake: a
// socket becomes readable, a sleep ends, a helper thread finishes. Qt watches
// those sources and continues the ready computations from its event dispatch.
// Outside a Qt event loop this does nothing; Bend's own loop is in charge.
class BendHost final : public QObject {
    struct Watch {
        int fd;
        bool writable;
        QSocketNotifier *notifier;
        bool armed;
    };
    std::vector<Watch> watches;
    QTimer deadline;
    QElapsedTimer since_run;
    bool armed = false;
    bool scheduled = false;

    void run()
    {
        since_run.restart();
        if (bend) bend->run();
    }

    // Runs ready computations from event dispatch, never from inside the
    // dispatcher's own bookkeeping.
    void schedule()
    {
        if (scheduled) return;
        scheduled = true;
        QMetaObject::invokeMethod(this, [this] { scheduled = false; run(); }, Qt::QueuedConnection);
    }

    void about_to_block()
    {
        if (!bend) return;
        bend->flush();
        if (bend->runnable()) { schedule(); return; }
        constexpr size_t limit = 256;
        BqtSource sources[limit];
        int64_t wait_ms = -1;
        size_t count = bend->sources(sources, limit, &wait_ms);
        if (count > limit) {
            // More descriptors than are watched here: look again soon.
            count = limit;
            if (wait_ms < 0 || wait_ms > 10) wait_ms = 10;
        }
        for (size_t i = 0; i < count; ++i) {
            Watch *found = nullptr;
            for (auto &watch : watches)
                if (watch.fd == sources[i].fd && watch.writable == bool(sources[i].writable)) { found = &watch; break; }
            if (!found) {
                auto *notifier = new QSocketNotifier(sources[i].fd,
                    sources[i].writable ? QSocketNotifier::Write : QSocketNotifier::Read, this);
                notifier->setEnabled(false);
                connect(notifier, &QSocketNotifier::activated, this, [this] { run(); });
                watches.push_back({sources[i].fd, bool(sources[i].writable), notifier, false});
                found = &watches.back();
            }
            if (!found->armed) { found->notifier->setEnabled(true); found->armed = true; }
        }
        if (wait_ms >= 0) deadline.start(int(std::min<int64_t>(wait_ms, std::numeric_limits<int>::max())));
        armed = true;
    }

    void awake()
    {
        const bool waited = armed;
        if (armed) {
            for (auto &watch : watches)
                if (watch.armed) { watch.notifier->setEnabled(false); watch.armed = false; }
            deadline.stop();
            armed = false;
        }
        if (!bend) return;
        // A loop that never waits still lets Bend look at its sources.
        if (bend->runnable() || (!waited && since_run.elapsed() >= 10)) schedule();
    }

public:
    BendHost()
    {
        deadline.setSingleShot(true);
        deadline.setTimerType(Qt::PreciseTimer);
        connect(&deadline, &QTimer::timeout, this, [this] { run(); });
        since_run.start();
        attach();
    }
    // The event dispatcher exists once the program constructs its application.
    void attach()
    {
        auto *dispatcher = QAbstractEventDispatcher::instance();
        if (attached || !dispatcher) return;
        attached = true;
        connect(dispatcher, &QAbstractEventDispatcher::aboutToBlock, this, [this] { about_to_block(); });
        connect(dispatcher, &QAbstractEventDispatcher::awake, this, [this] { awake(); });
    }

private:
    bool attached = false;
};

static BendHost *bend_host;

} // namespace bendqt

// Runs one generated operation for a Bend effect, on the main thread.
extern "C" __attribute__((visibility("default"))) void bqt_abi_call(BqtRequest *r)
{
    using namespace bendqt;
    if (!scope_valid(r->scope)) { fail(r, ESTALE, "Qt resource scope has ended"); return; }
    struct RequestScope {
        uint32_t previous;
        explicit RequestScope(uint32_t scope) : previous(native_request_scope) { native_request_scope = scope; }
        ~RequestScope() { native_request_scope = previous; }
    } resource_context(r->scope);
    CallFrame frame;
    // A Bend handler's own Qt calls pin their handles for themselves, not for
    // the native method that ran the handler.
    NativeDispatchIsolation isolation;
    try {
        callback_drain_released();
        OpaqueData::drain();
        reconcile_parents();
        reconcile_retentions();
        collect_pending();
        dispatch(r);
        reconcile_parents();
        reconcile_retentions();
        collect_pending();
        OpaqueData::drain();
    } catch (const std::bad_alloc &) {
        if (!r->error && !frame.handler_error) fail(r, ENOMEM, "Native Qt allocation failed");
    } catch (const std::system_error &error) {
        if (!r->error && !frame.handler_error)
            fail(r, error.code().value(), "Native Qt operation reported a system error");
    } catch (const std::exception &) {
        if (!r->error && !frame.handler_error) fail(r, EFAULT, "Native Qt operation raised an exception");
    } catch (...) {
        if (!r->error && !frame.handler_error) fail(r, EFAULT, "Native Qt operation raised an unknown exception");
    }
    // A Bend handler Qt ran during this operation failed: so does the operation.
    if (!r->error && frame.handler_error) {
        fail(r, frame.handler_error, frame.handler_message.c_str());
    }
    if (r->error) {
        // Cleanup may re-enter Qt and publish another error. Keep the current
        // text alive, then publish it after cleanup and before its frame dies.
        const char *message = own_request_message(r->message);
        discard_value(r->result);
        if (message) {
            static thread_local std::string returned_message;
            try { returned_message = message; r->message = returned_message.c_str(); }
            catch (...) { r->message = "Unable to copy the native Qt error message"; }
        }
    }
}

// Starts the Qt runtime for the Bend program. Called once, by the first Qt
// effect, on the main thread. The program then constructs its application
// object explicitly (create_application), as a C++ main would.
extern "C" __attribute__((visibility("default"))) const char *bqt_abi_start(const BqtHost *host)
{
    using namespace bendqt;
    try {
#if defined(BQT_NATIVE_PARTITIONS)
        module_runtime_services = host->shared_runtime;
        if (!module_runtime_services || module_runtime_services->version != BQT_RUNTIME_SERVICES_VERSION)
            return "Cannot attach the shared Qt runtime";
        runtime_register_partition_arguments();
        runtime_register_partition_bases();
        if (runtime_started) return nullptr;
#endif
#if defined(BQT_BUNDLED_RUNTIME_NATIVE)
        if (const char *error = RuntimePaths::configure(host->runtime_root)) return error;
#endif
        // Qt keeps argc and argv for the application's lifetime and removes
        // the options it recognizes, so it gets its own copy.
        application_argc = host->argc;
        application_argv = static_cast<char **>(std::calloc(size_t(host->argc) + 1, sizeof(char *)));
        if (!application_argv) return "Cannot allocate the Qt argument list";
        for (int i = 0; i < host->argc; ++i) application_argv[i] = host->argv[i];
        bend = host;
        OpaqueData::host.store(host, std::memory_order_release);
        if (host->runtime_root &&
                QLibraryInfo::path(QLibraryInfo::PrefixPath) != QString::fromUtf8(host->runtime_root))
            return "The Qt path configuration does not match the selected runtime";
        main_thread = QThread::currentThread();
        bend_host = new BendHost;
        main_context.store(bend_host, std::memory_order_release);
        application_constructed = [] { if (bend_host) bend_host->attach(); };
        runtime_started = true;
        return nullptr;
    } catch (const std::bad_alloc &) {
        return "Cannot allocate the Qt runtime";
    } catch (...) {
        return "Qt runtime startup raised an exception";
    }
}

// Tears Qt down after the Bend program's main has returned: objects Bend still
// owns are destroyed, then the application, as a C++ main would on return.
extern "C" __attribute__((visibility("default"))) int bqt_abi_stop(void)
{
    using namespace bendqt;
    struct DataStop { ~DataStop() { OpaqueData::shutdown(); } } data_stop;
    if (!runtime_started) return 0;
    post_routines_prepare();
    native_function_callbacks_shutdown();
    // Ordinary handlers stop here. Explicit post routines use the still-live
    // Bend 2.0.40 heap while Qt calls them from its application destructor.
    message_handler_shutdown();
    bend = nullptr;
    try { runnable_jobs_shutdown(); } catch (...) {}
    main_context.store(nullptr, std::memory_order_release);
    delete bend_host;
    bend_host = nullptr;
    try {
        if (application) QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
        reconcile_parents();
        reconcile_retentions();
        for (auto &c : connections)
            if (c.active) close_connection(c);
        rhi_shutdown();
        for (auto &e : entries)
            if (e.value && e.owned && !post_routines_entry(e)) e.pending_release = true;
        prepare_render_shutdown();
        collect_pending();
    } catch (...) {
        // Teardown continues: the application must still be destroyed.
    }
    auto *app = application;
    // Objects Qt owns may outlive this point until the application destroys
    // them. Their destruction observers must not post to a dying application.
    application = nullptr;
    if (app) { NativeDestructionScope destruction; delete app; }
    int post_error = post_routines_shutdown();
    collect_pending();
    // Maintainer-only diagnostic: deliberate external cycles can keep resources
    // alive, and must never be hidden by forcing deletion in an unsafe order.
    if (std::getenv("BEND_QT_CHECK_SHUTDOWN")) {
        uint32_t owned = 0;
        for (const auto &e : entries) if (e.value && e.owned) ++owned;
        if (owned) {
            std::fprintf(stderr, "QT612_SHUTDOWN_LEAK owned=%u\n", owned);
            return 126;
        }
        std::fputs("QT612_SHUTDOWN_OK owned=0\n", stdout);
        std::fflush(stdout);
    }
    return post_error;
}
