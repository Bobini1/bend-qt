// Results a Bend handler hands to Qt: transferred, retained or borrowed.
static bool callback_transfer_result(BqtRequest *r, uint32_t id, bool render_node = false)
{
    if (!id) return true;
    auto *e = entry(id);
    if (!e) { fail(r, ESTALE, "Invalid factory result"); return false; }
    if (!can_transfer_handle(r, id)) return false;
    auto *frame = callback_frame(r->self);
    bool old_node = render_node && frame && frame->arguments.count && frame->arguments.items[0].word == id;
    if (e->read_only || (!e->owned && !(e->object && e->object->parent()) && !old_node)) {
        fail(r, EPERM, "A factory result must be Bend-owned, Qt-parented, or the existing render node");
        return false;
    }
    const bool consumable = !e->object && !e->native_observed && !old_node && render_factory_consumable(id);
    if (!e->object && !e->native_observed && !old_node && !consumable) {
        fail(r, ENOTSUP, "A native factory result requires observed destruction");
        return false;
    }
    if (!old_node && (retained(id) || active_in_subtree(id))) {
        fail(r, EBUSY, "Cannot transfer a result retained by an active native call");
        return false;
    }
    if (consumable) {
        if (!frame || !frame->receiver) { fail(r, ESTALE, "A native factory transfer needs its calling Qt receiver"); return false; }
        // Ownership stays with Bend until callback_invoke commits the complete
        // successful answer. A failed handler releases it through its scope.
        frame->pending_factory_results.push_back({id, render_node});
        return true;
    }
    if (render_node && !old_node) {
        if (!frame || !set_native_owner(r, id, frame->receiver)) return false;
    }
    set_owned(id, false);
    return true;
}

// A native caller may keep an earlier result after another virtual call. Keep
// every distinct result until the proxy is destroyed, rather than replacing a
// method's previous edge. This is a binding lifetime, not native ownership.
static bool callback_prepare_retained(BqtRequest *r, uint32_t id, RetentionBatch &batch)
{
    if (!id) return true;
    auto *frame = callback_frame(r->self);
    auto *value = entry(id);
    if (!frame || !entry(frame->receiver) || !value) {
        fail(r, ESTALE, "Invalid retained result"); return false;
    }
    if (!value->object && !value->native_observed) {
        fail(r, ENOTSUP, "A retained native result needs observed destruction"); return false;
    }
    // Self and native ancestors already keep the receiver alive. A native
    // descendant is invalidated with its owner and needs no additional edge.
    // Check observation first: temporary argument tokens must not escape.
    if (entry_inside(id, frame->receiver) || entry_inside(frame->receiver, id)) return true;
    constexpr uint32_t slot = 0xffffffefu;
    return batch.add(r, frame->receiver, slot, id, nullptr, false, false, id);
}

static bool callback_retain_result(BqtRequest *r, uint32_t id)
{
    RetentionBatch batch;
    return callback_prepare_retained(r, id, batch) && batch.finish(r);
}

// Event and other non-QObject pointers are valid for the native invocation.
// Publish temporary, non-owning identities and invalidate only identities
// created here when the native call returns. Existing tracked objects retain
// their independently established ownership/lifetime policy.
struct CallbackNativeArguments {
    std::vector<uint32_t> temporary;
    template<class T> BqtValue borrow_argument(BqtRequest *r, T *value, uint16_t type, uint32_t receiver) {
        BqtValue result{};
        if (!value) return result;
        for (uint32_t i = 1; i < capacity; ++i) {
            auto &e = entries[i];
            if (e.value && e.cast && e.cast(e.value, type) == value) {
                result.word = result.borrowed_handle = token(i, e.generation);
                return result;
            }
        }
        if (const auto restored = render_factory_restore(r, value, type, receiver)) {
            result.word = result.borrowed_handle = restored;
            return result;
        }
        if (r->error) return result;
        temporary.push_back(0);
        result.word = result.borrowed_handle = register_native_borrow(r, value, type, receiver);
        temporary.back() = result.word;
        return result;
    }
    ~CallbackNativeArguments() { for (auto id : temporary) if (entry(id)) invalidate(id); }
};
