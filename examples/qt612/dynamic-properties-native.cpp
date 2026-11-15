// Production dynamic-property adapter with real Qt objects and a minimal
// registry/origin carrier. The complete generic codecs and Bend ABI are
// exercised separately by scripts/fixtures/dynamic-properties.bend.
#include <QtCore/QCoreApplication>
#include <QtCore/QEvent>
#include <QtCore/QMetaProperty>
#include <QtCore/QPointer>
#include <QtCore/QThread>
#include <QtCore/QVariant>
#include <QtQml/QQmlPropertyMap>
#include <algorithm>
#include <cassert>
#include <cerrno>
#include <cstdint>
#include <deque>
#include <functional>
#include <iostream>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>
#include <system_error>
#include <vector>

struct BqtValue { uint32_t word = 0, owned_handle = 0; };
struct BqtRequest {
    uint32_t self = 0, scope = 0;
    int error = 0;
    const char *message = nullptr;
    BqtValue result;
};
struct Entry {
    void *value = nullptr;
    QObject *object = nullptr;
    bool read_only = false, pending_release = false;
    uint32_t scope_owner = 0, active_calls = 0;
    std::function<void()> destroy;
    std::vector<std::shared_ptr<void>> leases;
};
static std::deque<Entry> entries(1);
static Entry *entry(uint32_t id) { return id && id < entries.size() && entries[id].value ? &entries[id] : nullptr; }
struct Retention { uint32_t owner = 0, slot = 0, key = 0, target = 0; };
static std::deque<Retention> retentions;
static QThread *main_thread;
static int reported = 0;
static bool refuse_retention = false;
static bool fail(BqtRequest *r, int code, const char *message) {
    if (!r->error) { r->error = code; r->message = message; }
    return true;
}
static void callback_report_error(int code, const char *) { if (!reported) reported = code; }
static void schedule_collection() {}
static void dynamic_properties_event(QObject *, QEvent *);
static void dynamic_properties_forget(uint32_t);
static void collect() {
    bool changed;
    do {
        changed = false;
        for (uint32_t id = 1; id < entries.size(); ++id) {
            auto *record = entry(id);
            if (!record || !record->pending_release || record->active_calls) continue;
            if (std::any_of(retentions.begin(), retentions.end(), [id](auto edge) { return edge.target == id; })) continue;
            if (record->object) dynamic_properties_forget(id);
            auto destroy = std::move(record->destroy);
            record->value = nullptr;
            if (destroy) destroy();
            record->leases.clear();
            for (auto &edge : retentions) if (edge.owner == id) edge = {};
            changed = true;
        }
    } while (changed);
}
static void drop(uint32_t id) { if (auto *record = entry(id)) record->pending_release = true; collect(); }
struct NativeCallScope;
static NativeCallScope *native_call_scope;
struct NativeCallScope {
    NativeCallScope *previous = native_call_scope;
    std::vector<uint32_t> pins;
    NativeCallScope() { native_call_scope = this; }
    ~NativeCallScope() {
        native_call_scope = previous;
        for (auto id : pins) if (auto *record = entry(id)) --record->active_calls;
    }
    void pin(BqtRequest *r, uint32_t id) {
        if (std::find(pins.begin(), pins.end(), id) != pins.end()) return;
        auto *record = entry(id);
        if (!record) { fail(r, ESTALE, "Expired native test origin"); return; }
        pins.push_back(id); ++record->active_calls;
    }
};
template<class T> static uint32_t own(BqtRequest *, T *value, uint16_t) {
    Entry next; next.value = value; next.destroy = [value] { delete value; };
    entries.push_back(std::move(next)); return uint32_t(entries.size() - 1);
}
struct ConversionValueGuard {
    BqtValue value;
    explicit ConversionValueGuard(BqtValue input) : value(input) {}
    ~ConversionValueGuard() { drop(value.owned_handle); }
    BqtValue release() { auto result = value; value = {}; return result; }
};
static int prepare_retention(BqtRequest *r, uint32_t slot, uint32_t key, uint32_t) {
    if (refuse_retention) { fail(r, ENOMEM, "Injected dynamic property preflight failure"); return -1; }
    for (size_t i = 0; i < retentions.size(); ++i)
        if ((retentions[i].owner == r->self && retentions[i].slot == slot && retentions[i].key == key) || !retentions[i].owner) return int(i);
    retentions.push_back({}); return int(retentions.size() - 1);
}
static void commit_retention(int index, uint32_t owner, uint32_t slot, uint32_t key, uint32_t target, std::nullptr_t) {
    retentions.at(size_t(index)) = target ? Retention{owner, slot, key, target} : Retention{};
}
static QVariant native_owned_snapshot(const QVariant &value) { return value; }
namespace BendSignalApi {
struct Snapshot {
    std::vector<QPointer<QObject>> objects;
    void guard(const QVariant &value) {
        if (value.metaType().flags().testFlag(QMetaType::PointerToQObject))
            if (auto *object = value.value<QObject *>()) objects.push_back(object);
    }
    bool live() const { return std::all_of(objects.begin(), objects.end(), [](auto value) { return !value.isNull(); }); }
    bool pin_metadata(BqtRequest *) const { return true; }
};
}
static bool generic_variant_validate(BqtRequest *r, uint32_t id) {
    if (id && !entry(id)) fail(r, ESTALE, "Expired dynamic test snapshot");
    return !r->error;
}
static bool generic_variant_finish(BqtRequest *, BqtValue &, uint32_t) { return true; }
namespace GenericVariants {
static bool attach_origins(BqtRequest *, uint32_t result, const QVariant &, const std::vector<uint32_t> &inputs) {
    auto *destination = entry(result);
    for (auto source : inputs) if (auto *record = entry(source))
        destination->leases.insert(destination->leases.end(), record->leases.begin(), record->leases.end());
    return true;
}
}
static uint32_t generic_variant_snapshot(BqtRequest *r, const QVariant &value, uint32_t excluded, bool) {
    std::vector<uint32_t> inputs;
    if (native_call_scope) for (auto id : native_call_scope->pins) if (id != excluded) inputs.push_back(id);
    bool dependent = false;
    for (auto id : inputs) if (auto *record = entry(id)) dependent |= !record->leases.empty();
    if (!dependent || !value.isValid()) return 0;
    auto result = own(r, new QVariant(value), 1);
    GenericVariants::attach_origins(r, result, value, inputs);
    return result;
}
#include "dynamic-properties-runtime.h"

class Application : public QCoreApplication {
public:
    using QCoreApplication::QCoreApplication;
    bool notify(QObject *object, QEvent *event) override {
        dynamic_properties_event(object, event);
        return QCoreApplication::notify(object, event);
    }
};
static uint32_t register_object(QObject *value) {
    BqtRequest r; auto id = own(&r, value, 0); entry(id)->object = value; return id;
}
static BqtRequest write(uint32_t owner, const char *name, const QVariant &value, uint32_t source = 0) {
    NativeCallScope call;
    BqtRequest r; r.self = owner; call.pin(&r, owner);
    if (source) call.pin(&r, source);
    DynamicProperties::write(&r, entry(owner)->object, name, value);
    return r;
}
static uint32_t read(uint32_t owner, const char *name) {
    NativeCallScope call;
    BqtRequest r; r.self = owner; call.pin(&r, owner);
    DynamicProperties::read(&r, entry(owner)->object, name);
    assert(!r.error); return r.result.word;
}
static QVariant *variant(uint32_t id) { return static_cast<QVariant *>(entry(id)->value); }
static int integer(uint32_t owner, const char *name) {
    auto id = read(owner, name); int result = variant(id)->toInt(); drop(id); return result;
}
static size_t leases() {
    return size_t(std::count_if(retentions.begin(), retentions.end(), [](auto edge) { return edge.target; }));
}
class Reentrant : public QObject {
public:
    uint32_t id = 0;
    bool armed = false, error = false;
    bool event(QEvent *event) override {
        if (event->type() == QEvent::DynamicPropertyChange) {
            if (armed) {
                armed = false;
                assert(integer(id, "counter") == 1);
                setProperty("counter", 2);
            }
            if (error) callback_report_error(73, "Injected native event handler failure");
        }
        return QObject::event(event);
    }
};
int main(int argc, char **argv) {
    Application app(argc, argv); main_thread = app.thread();
    auto host = register_object(new QObject);
    auto first = write(host, "counter", 1);
    assert(!first.error && !first.result.word && integer(host, "counter") == 1);
    entry(host)->object->setProperty("counter", 2);
    assert(integer(host, "counter") == 2);
    for (unsigned i = 0; i < 100; ++i) {
        assert(!write(host, "counter", int(i)).error);
        assert(!write(host, "counter", QVariant()).error);
        collect(); assert(leases() == 0);
    }
    auto map = std::make_shared<QQmlPropertyMap>();
    map->insert("dynamicMember", 7);
    auto meta = map->metaObject();
    const QVariant descriptor = QVariant::fromValue(meta->property(meta->indexOfProperty("dynamicMember")));
    BqtRequest request;
    const uint32_t source = own(&request, new QVariant(descriptor), 1);
    entry(source)->leases.push_back(map);
    std::weak_ptr<QQmlPropertyMap> weak = map;
    assert(!write(host, "descriptor", descriptor, source).error);
    map.reset(); drop(source);
    assert(!weak.expired());
    const uint32_t outgoing = read(host, "descriptor");
    assert(std::string(variant(outgoing)->value<QMetaProperty>().name()) == "dynamicMember");
    assert(!write(host, "descriptor", QVariant()).error);
    collect(); assert(!weak.expired());
    drop(outgoing); collect(); assert(weak.expired());
    // Raw native replacement observes the input lease before user filters.
    assert(!write(host, "descriptor", 0).error);
    auto native_map = std::make_shared<QQmlPropertyMap>();
    native_map->insert("nativeMember", 9);
    auto native_meta = native_map->metaObject();
    const uint32_t native_source = own(&request, new QVariant(QVariant::fromValue(native_meta->property(native_meta->indexOfProperty("nativeMember")))), 1);
    entry(native_source)->leases.push_back(native_map);
    std::weak_ptr<QQmlPropertyMap> native_weak = native_map;
    {
        NativeCallScope call; call.pin(&request, native_source);
        entry(host)->object->setProperty("descriptor", *variant(native_source));
    }
    native_map.reset(); drop(native_source);
    assert(!native_weak.expired());
    const uint32_t native_copy = read(host, "descriptor");
    assert(std::string(variant(native_copy)->value<QMetaProperty>().name()) == "nativeMember");
    drop(native_copy);
    refuse_retention = true;
    auto refused = write(host, "descriptor", 3);
    assert(refused.error == ENOMEM);
    refuse_retention = false;
    const uint32_t unchanged = read(host, "descriptor");
    assert(std::string(variant(unchanged)->value<QMetaProperty>().name()) == "nativeMember");
    drop(unchanged);
    assert(!write(host, "descriptor", QVariant()).error);
    collect(); assert(native_weak.expired() && leases() == 0);
    // QObject pointers remain weak in native stored values.
    auto peer = new QObject;
    assert(!write(host, "peer", QVariant::fromValue(peer)).error);
    delete peer;
    {
        NativeCallScope call; BqtRequest stale; stale.self = host;
        DynamicProperties::read(&stale, entry(host)->object, "peer");
        assert(stale.error == ESTALE);
    }
    assert(!write(host, "peer", QVariant()).error);
    auto receiver = new Reentrant;
    const uint32_t receiver_id = register_object(receiver); receiver->id = receiver_id;
    receiver->armed = true;
    assert(!write(receiver_id, "counter", 1).error);
    assert(integer(receiver_id, "counter") == 2 && receiver->property("counter").toInt() == 2);
    receiver->error = true;
    assert(!write(receiver_id, "counter", 3).error);
    assert(reported == 73 && integer(receiver_id, "counter") == 3);
    drop(receiver_id); drop(host); collect();
    assert(DynamicProperties::states.empty() && leases() == 0);
    for (uint32_t id = 1; id < entries.size(); ++id) assert(!entry(id));
    std::cout << "DYNAMIC_PROPERTIES_NATIVE_OK raw_observer=1 metadata_lifetime=1 output_snapshot=1 weak_objects=1 reentrant=1 preflight=1 removals=100 cleanup=1\n";
}
