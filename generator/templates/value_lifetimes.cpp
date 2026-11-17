// Text values contain private document pointers; copying them does not keep
// their storage alive. Track the document and its monotonic mutation epoch.
struct ValueGuard {
    uint32_t document = 0;
    uint32_t tree = 0;
    uint64_t epoch = 0;
    int revision = 0;
    QTextBlock::iterator block_begin;
    QTextFrame::iterator frame_begin;
    QPointer<QTextFrame> frame;
    QMetaObject::Connection tree_destroyed;
    ValueGuard() = default;
    ValueGuard(const ValueGuard &other)
        : document(other.document), tree(other.tree), epoch(other.epoch), revision(other.revision),
          block_begin(other.block_begin), frame_begin(other.frame_begin), frame(other.frame) {}
    ~ValueGuard() { QObject::disconnect(tree_destroyed); }
};
static SlotTable<ValueGuard *> value_guards;

static ValueGuard *value_guard(uint32_t id)
{ return entry(id) ? value_guards[id & 0xffff] : nullptr; }

static void value_guard_forget(uint32_t id)
{
    auto *guard = value_guards[id & 0xffff];
    value_guards[id & 0xffff] = nullptr;
    delete guard;
}

static bool validate_value_guard(BqtRequest *r, uint32_t id)
{
    auto *guard = value_guard(id);
    if (!guard) return true;
    if (guard->document) {
        auto *owner = entry(guard->document);
        if (!owner || owner->text_epoch != guard->epoch) {
            fail(r, ESTALE, "Text storage changed or its document was destroyed"); return false;
        }
        auto *document = qobject_cast<QTextDocument *>(owner->object);
        if (!document || document->revision() != guard->revision) {
            fail(r, ESTALE, "Text document revision changed"); return false;
        }
        if (owner->text_edit_depth || document->signalsBlocked()) {
            fail(r, EBUSY, "Text storage views require completed edits and enabled document signals"); return false;
        }
        if (entry(id)->type == @QTextFrame::iterator@ && !guard->frame) {
            fail(r, ESTALE, "Text iterator frame was destroyed"); return false;
        }
        if (native_call_scope) native_call_scope->pin(r, guard->document);
        if (r->error) return false;
    }
    if (guard->tree) {
        if (!entry(guard->tree)) { fail(r, ESTALE, "Tree iterator widget was destroyed"); return false; }
        if (native_call_scope) native_call_scope->pin(r, guard->tree);
        if (r->error) return false;
    }
    return true;
}

static bool guard_document(BqtRequest *r, ValueGuard &guard, const QTextDocument *document)
{
    if (!document) return true;
    if (document->thread() != main_thread) { fail(r, EXDEV, "Text document belongs to another thread"); return false; }
    auto id = borrow_const(r, document, @QTextDocument@);
    if (!id) return false;
    NativeCallScope observation;
    observation.pin(r, id);
    if (r->error) return false;
    auto *owner = entry(id);
    if (owner->text_edit_depth || document->signalsBlocked()) {
        fail(r, EBUSY, "Text storage views require completed edits and enabled document signals"); return false;
    }
    const auto observed_epoch = owner->text_epoch;
    const int observed_revision = document->revision();
    if (!owner->text_observed) {
        owner->text_observed = true;
        try { QObject::connect(document, &QTextDocument::contentsChanged, [id] {
            if (auto *current = entry(id)) {
                // Saturation permanently rejects future guarded reads instead
                // of allowing an old epoch to become valid again after wrap.
                if (current->text_epoch != UINT64_MAX) ++current->text_epoch;
            }
        }); } catch (...) { if (auto *current = entry(id)) current->text_observed = false; throw; }
        owner = entry(id);
        if (!owner) { fail(r, ESTALE, "Text document disappeared during observation"); return false; }
    }
    if (owner->text_epoch != observed_epoch || document->revision() != observed_revision) {
        fail(r, ESTALE, "Text storage changed while registering its observer"); return false;
    }
    if (owner->text_epoch == UINT64_MAX) { fail(r, EOVERFLOW, "Text storage epoch exhausted"); return false; }
    guard.document = id;
    guard.epoch = owner->text_epoch;
    guard.revision = document->revision();
    return true;
}

static bool note_text_mutation(BqtRequest *r, const QTextDocument *document, int edit = 0)
{
    if (!document) return true;
    auto id = borrow_const(r, document, @QTextDocument@);
    if (!id) return false;
    if (native_call_scope) native_call_scope->pin(r, id);
    if (r->error) return false;
    auto *owner = entry(id);
    if (owner->text_epoch == UINT64_MAX || (edit > 0 && owner->text_edit_depth == UINT32_MAX)) {
        fail(r, EOVERFLOW, "Text storage epoch or edit nesting exhausted"); return false;
    }
    ++owner->text_epoch;
    if (edit > 0) ++owner->text_edit_depth;
    if (edit < 0 && owner->text_edit_depth) --owner->text_edit_depth;
    return true;
}

static bool note_object_document_mutation(BqtRequest *r, QObject *object)
{
    return note_text_mutation(r, qobject_cast<QTextDocument *>(object));
}

static uint32_t value_source(BqtRequest *r)
{ return native_call_scope && native_call_scope->value_origin ? native_call_scope->value_origin : r->self; }

static ValueGuard *source_value_guard(BqtRequest *r, uint16_t type)
{
    auto id = value_source(r);
    auto *candidate = entry(id);
    if (!candidate) return nullptr;
    bool tree = type == @QTreeWidgetItemIterator@;
    if (tree != (candidate->type == @QTreeWidgetItemIterator@)) return nullptr;
    return value_guard(id);
}

static bool reset_value_guard(BqtRequest *r, uint32_t id)
{
    text_mutation_hook = note_object_document_mutation;
    auto *e = entry(id);
    if (!e) return false;
    switch (e->type) {
    @VALUE_LIFETIME_CASES@ break;
    default: return true;
    }
    try {
        auto guard = std::make_unique<ValueGuard>();
        if (auto *source = source_value_guard(r, e->type))
            guard = std::make_unique<ValueGuard>(*source);
        if (e->type == @QTextBlock@) {
            auto *value = static_cast<QTextBlock *>(e->value);
            if (value->isValid() && !guard_document(r, *guard, value->document())) return false;
        } else if (e->type == @QTextFragment@ && !guard->document && static_cast<QTextFragment *>(e->value)->isValid()) {
            fail(r, ENOTSUP, "Text fragment requires an observed document origin"); return false;
        } else if (e->type == @QTextTableCell@) {
            auto *value = static_cast<QTextTableCell *>(e->value);
            if (value->isValid() && !guard_document(r, *guard, value->firstCursorPosition().document())) return false;
        } else if (e->type == @QTextFrame::iterator@) {
            auto *value = static_cast<QTextFrame::iterator *>(e->value);
            if (auto *frame = value->parentFrame()) {
                if (!guard_document(r, *guard, frame->document())) return false;
                guard->frame = frame;
                guard->frame_begin = frame->begin();
            }
        } else if (e->type == @QTextBlock::iterator@) {
            auto *origin = entry(r->self);
            if (origin && origin->type == @QTextBlock@) {
                auto *block = static_cast<QTextBlock *>(origin->value);
                if (block->isValid()) {
                    if (!guard_document(r, *guard, block->document())) return false;
                    guard->block_begin = block->begin();
                }
            }
#if defined(BQT_HAS_WIDGETS)
        } else if (e->type == @QTreeWidgetItemIterator@ && !guard->tree) {
            if (auto *source = entry(value_source(r))) {
                QTreeWidget *tree = source->object ? qobject_cast<QTreeWidget *>(source->object) : nullptr;
                if (!tree && source->cast)
                    if (auto *item = static_cast<QTreeWidgetItem *>(source->cast(source->value, @QTreeWidgetItem@)))
                        tree = item->treeWidget();
                if (tree) guard->tree = borrow(r, tree, @QTreeWidget@);
            }
            if (!guard->tree) { fail(r, ENOTSUP, "Tree iterator has no observed widget origin"); return false; }
#endif
        }
        uint32_t owner = guard->document ? guard->document : guard->tree;
        {
            BqtRequest claim{}; claim.self = id;
            constexpr uint32_t value_origin_slot = 0xffffffec;
            int slot = prepare_retention(&claim, value_origin_slot, 0, owner);
            if (claim.error) { fail(r, claim.error, claim.message); return false; }
            commit_retention(slot, id, value_origin_slot, 0, owner, nullptr);
        }
        if (guard->tree) {
            auto *tree = entry(guard->tree);
            if (!tree || !tree->object) { fail(r, ESTALE, "Tree iterator origin expired"); return false; }
            // QObject emits destroyed before deleting children. The tree's
            // private model is its child; remove the iterator from that model
            // while the model's own iterator list is still alive.
            guard->tree_destroyed = QObject::connect(tree->object, &QObject::destroyed, [id] {
                if (auto *value = entry(id)) {
                    auto *storage = value->value;
                    auto destroy = value->destroy;
                    invalidate(id);
                    destroy(storage);
                }
            });
        }
        value_guard_forget(id);
        value_guards[id & 0xffff] = guard.release();
        e->validate = validate_value_guard;
        return true;
    } catch (const std::bad_alloc &) {
        fail(r, ENOMEM, "Qt value origin allocation failed"); return false;
    }
}

static uint32_t finish_value_ownership(BqtRequest *r, uint32_t id)
{
    if (!id || reset_value_guard(r, id)) return id;
    auto *e = entry(id);
    auto *storage = e->value;
    auto destroy = e->destroy;
    invalidate(id);
    destroy(storage);
    return 0;
}
