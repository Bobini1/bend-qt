// Qt's aggregate does not delete its pointers. Each field holds one shared
// ownership lease; copying the aggregate shares those leases, not raw owners.
struct TakenRowItem {
    QLayoutItem *pointer;
    uint32_t id;
    QPointer<QLayout> layout;
    bool is_layout;
    bool owns;
    TakenRowItem(QLayoutItem *value, uint32_t token, bool owned)
        : pointer(value), id(token), layout(value->layout()), is_layout(layout != nullptr), owns(owned) {}
    ~TakenRowItem() {
        if (!pointer || !owns) return;
        invalidate(id);
        if (!is_layout || layout) delete pointer;
    }
};
struct TakenRowRecord {
    uint32_t id = 0;
    QFormLayout::TakeRowResult *pointer = nullptr;
    std::shared_ptr<TakenRowItem> items[2];
};
static SlotTable<TakenRowRecord> taken_rows;
static void take_row_native_deleted(uint32_t id) {
    for (auto &record : taken_rows) for (auto &item : record.items)
        if (item && item->id == id) { item->pointer = nullptr; item->owns = false; }
}
static QLayoutItem *&taken_row_member(QFormLayout::TakeRowResult &row, int index)
{ return index ? row.fieldItem : row.labelItem; }
static TakenRowRecord *taken_row_record(uint32_t id) {
    auto &record = taken_rows[id & 65535u];
    return record.id == id && entry(id) ? &record : nullptr;
}
static void destroy_taken_row(void *pointer) {
    TakenRowRecord old;
    for (auto &record : taken_rows) if (record.pointer == pointer) {
        old = std::move(record); record = {}; break;
    }
    delete static_cast<QFormLayout::TakeRowResult *>(pointer);
    // Entry invalidation has already removed the holder edges. The native
    // item remains ours even if that pruned its borrowed registry identity.
}
struct TakenRowGuard {
    QLayoutItem *items[2];
    explicit TakenRowGuard(const QFormLayout::TakeRowResult &row) : items{row.labelItem, row.fieldItem} {}
    void release(QLayoutItem *pointer) { for (auto &item : items) if (item == pointer) item = nullptr; }
    ~TakenRowGuard() {
        if (items[0] == items[1]) items[1] = nullptr;
        for (auto *item : items) if (item) { native_forget_pointer(item, @ITEM_TYPE@); delete item; }
    }
};
static std::shared_ptr<TakenRowItem> make_taken_row_item(BqtRequest *r, QLayoutItem *pointer, TakenRowGuard &guard, bool owns = true) {
    if (!pointer) return {};
    auto id = native_known_token(pointer, @ITEM_TYPE@);
    if (!id) id = insert(r, pointer, pointer->layout(), @ITEM_TYPE@,
        native_deleter<QLayoutItem>(), false, NativeTraits<QLayoutItem>::cast);
    if (!id || !can_transfer_handle(r, id)) return {};
    auto value = std::make_shared<TakenRowItem>(pointer, id, owns);
    guard.release(pointer);
    native_model_detach(id);
    if (!set_native_owner(r, id, 0)) return {};
    if (auto *widget = pointer->widget()) {
        auto widget_id = borrow(r, widget, @WIDGET_TYPE@);
        RetentionBatch retained;
        if (r->error || !retained.add(r, id, 0xb4000001u, widget_id, nullptr) || !retained.finish(r)) return {};
    }
    return value;
}
static TakenRowRecord *taking_row;
static uint32_t fail_taken_row(BqtRequest *r, uint32_t id) {
    if (auto *e = entry(id)) { auto *p = e->value; auto destroy = e->destroy; invalidate(id); if (destroy) destroy(p); }
    return 0;
}
static uint32_t finish_take_row_ownership(BqtRequest *r, uint32_t id) {
    auto *e = entry(id);
    if (!e || e->type != @ROW_TYPE@) return id;
    auto *value = static_cast<QFormLayout::TakeRowResult *>(e->value);
    TakenRowRecord next; next.id = id; next.pointer = value;
    auto *source = taking_row;
    if (!source && native_call_scope) source = taken_row_record(native_call_scope->value_origin);
    for (int n = 0; n < 2; ++n) {
        auto *pointer = taken_row_member(*value, n);
        if (!pointer) continue;
        if (source) for (const auto &item : source->items)
            if (item && item->pointer == pointer) { next.items[n] = item; break; }
        if (!next.items[n] || !entry(next.items[n]->id)) {
            fail(r, ESTALE, "Taken row copy has no live item ownership origin");
            return fail_taken_row(r, id);
        }
    }
    RetentionBatch retained;
    for (int n = 0; n < 2; ++n)
        if (!retained.add(r, id, shared_holder_slot, next.items[n] ? next.items[n]->id : 0,
                          nullptr, false, false, uint32_t(n))) return fail_taken_row(r, id);
    if (!retained.finish(r)) return fail_taken_row(r, id);
    auto old = std::move(taken_rows[id & 65535u]);
    taken_rows[id & 65535u] = std::move(next);
    e->destroy = destroy_taken_row;
    for (const auto &item : taken_rows[id & 65535u].items) if (item) {
        auto *child = entry(item->id); child->shared_managed = true; child->owned = false;
    }
    return id;
}
static uint32_t store_taken_row(BqtRequest *r, const QFormLayout::TakeRowResult &value, bool adopt) {
    if (!adopt) return own(r, new QFormLayout::TakeRowResult(value), @ROW_TYPE@);
    TakenRowGuard guard(value);
    TakenRowRecord source;
    for (int n = 0; n < 2; ++n) {
        auto *pointer = n ? value.fieldItem : value.labelItem;
        if (n && pointer == value.labelItem) source.items[n] = source.items[0];
        else source.items[n] = make_taken_row_item(r, pointer, guard);
        if (r->error) return 0;
    }
    struct Origin { TakenRowRecord *old; ~Origin() { taking_row = old; } } origin{taking_row};
    taking_row = &source;
    return own(r, new QFormLayout::TakeRowResult(value), @ROW_TYPE@);
}
static uint32_t taken_row_field(BqtRequest *r, uint32_t id, int index) {
    auto *row = taken_row_record(id);
    if (!row) { fail(r, ESTALE, "Taken row ownership has expired"); return 0; }
    auto &item = row->items[index];
    if (!item) return 0;
    if (!entry(item->id)) { fail(r, ESTALE, "Taken row item was destroyed natively"); return 0; }
    if (native_call_scope) native_call_scope->pin(r, item->id);
    return r->error ? 0 : item->id;
}
static bool set_taken_row_field(BqtRequest *r, uint32_t id, int index, uint32_t target) {
    auto *row = taken_row_record(id);
    if (!row) { fail(r, ESTALE, "Taken row ownership has expired"); return false; }
    if (row->items[index] && row->items[index]->id == target) return true;
    RetentionBatch changes;
    if (!changes.add(r, id, shared_holder_slot, target, nullptr, false, false, uint32_t(index))) return false;
    std::shared_ptr<TakenRowItem> next;
    if (target) {
        for (const auto &other : taken_rows) for (const auto &item : other.items)
            if (item && item->id == target) next = item;
        if (!next) {
            auto *e = entry(target);
            if (!e || !e->owned || e->native_owner || e->shared_managed || e->read_only) {
                fail(r, EPERM, "Row field adoption requires an independently owned layout item"); return false;
            }
            if (retained(target) || e->active_calls > 1) { fail(r, EBUSY, "Row field item is in use"); return false; }
            auto *pointer = static_cast<QLayoutItem *>(e->cast(e->value, @ITEM_TYPE@));
            QFormLayout::TakeRowResult incoming{}; incoming.labelItem = pointer;
            TakenRowGuard guard(incoming);
            guard.release(pointer); // Failure before commit leaves the input owned by its caller.
            next = make_taken_row_item(r, pointer, guard, false);
            if (r->error) return false;
        }
    }
    if (!changes.finish(r)) return false;
    auto old = std::move(row->items[index]);
    row->items[index] = std::move(next);
    taken_row_member(*row->pointer, index) = row->items[index] ? row->items[index]->pointer : nullptr;
    if (target) { auto *child = entry(target); row->items[index]->owns = true; child->shared_managed = true; child->owned = false; }
    return true;
}
static uint32_t take_row_item(BqtRequest *r, uint32_t id, int index) {
    auto *row = taken_row_record(id);
    if (!row) { fail(r, ESTALE, "Taken row ownership has expired"); return 0; }
    auto &item = row->items[index];
    if (!item) return 0;
    if (item.use_count() != 1) { fail(r, EBUSY, "Clear or release other aggregate copies before taking this shared row item"); return 0; }
    auto *child = entry(item->id);
    if (!child) { fail(r, ESTALE, "Taken row item was destroyed natively"); return 0; }
    if (child->active_calls) {
        fail(r, EBUSY, "Taken row item is in an active native call"); return 0;
    }
    RetentionBatch retained;
    if (!retained.add(r, id, shared_holder_slot, 0, nullptr, false, false, uint32_t(index)) || !retained.finish(r)) return 0;
    auto result = item->id;
    item->pointer = nullptr;
    child->shared_managed = false; child->owned = true; child->pending_release = false;
    item.reset(); taken_row_member(*row->pointer, index) = nullptr;
    return result;
}
