"""Observe graphics-layout ownership independently of graphics-item parenting."""


def prepare(g):
    if getattr(g, '_graphics_layouts_prepared', False):
        return
    g._graphics_layouts_prepared = True
    import native_lifetimes
    from retention import _slot
    native_lifetimes.prepare(g)
    slot = _slot(g, 'QGraphicsLayout.members')
    g.graphics_layout_slot = slot
    tid = g.ids['QGraphicsLayoutItem']
    g.retention_accessors['native_graphics_layout'] = f'''
static bool native_graphics_layout_contains(BqtRequest *r, QGraphicsLayoutItem *parent, QGraphicsLayoutItem *value) {{
    if (!parent) return false;
    uint32_t parent_id = native_known_token(parent, {tid});
    if (parent_id && native_call_scope) native_call_scope->pin(r, parent_id);
    if (r->error) return false;
    if (parent->isLayout()) {{
        auto *layout = static_cast<QGraphicsLayout *>(parent);
        for (int n = 0; n < layout->count(); ++n) if (layout->itemAt(n) == value) return true;
        return false;
    }}
    auto *item = parent->graphicsItem();
    return item && item->isWidget() && static_cast<QGraphicsWidget *>(item)->layout() == value;
}}
static void native_graphics_layout_forget_pins(uint32_t target, uint32_t keep_owner = 0) {{
    for (auto &edge : retentions)
        if (edge.slot == {slot} && edge.target == target && edge.owner != keep_owner) edge = {{}};
}}
// A standalone layout may point at a parent before it is inserted. Its
// child->parent pin must become parent->child ownership atomically on insertion.
struct NativeGraphicsParentEdge {{
    int index = -1;
    Retention saved{{}};
    bool accepted = false;
    bool suspend(BqtRequest *r, uint32_t child, uint32_t parent) {{
        for (uint32_t n = 0; n < capacity; ++n) {{
            auto &edge = retentions[n];
            if (edge.owner != child || edge.target != parent || edge.slot != {slot} || edge.key != 0) continue;
            if (retention_reserved[n]) {{ fail(r, EBUSY, "Graphics layout parent change is already active"); return false; }}
            saved = edge; index = int(n);
            reserve_retention(index, edge.owner, edge.slot, edge.key);
            edge = {{}};
            break;
        }}
        return true;
    }}
    ~NativeGraphicsParentEdge() {{
        if (index < 0) return;
        if (!accepted && entry(saved.owner) && entry(saved.target)) retentions[index] = saved;
        unreserve_retention(index);
    }}
}};
struct NativeGraphicsLayoutObservation {{ uint32_t id, owner; QGraphicsLayoutItem *value; bool checking; }};
static SlotTable<NativeGraphicsLayoutObservation> native_graphics_layout_observations;
static bool validate_native_graphics_layout(BqtRequest *r, uint32_t id) {{
    auto &record = native_graphics_layout_observations[id & 65535u];
    if (record.id != id) return true;
    if (record.checking) {{ fail(r, EBUSY, "Graphics layout validation is already active"); return false; }}
    record.checking = true;
    struct Reset {{ bool &value; ~Reset() {{ value = false; }} }} reset{{record.checking}};
    auto *owner = entry(record.owner);
    if (owner && owner->validate && !owner->validate(r, record.owner)) return false;
    owner = entry(record.owner);
    auto *parent = owner && owner->cast ? static_cast<QGraphicsLayoutItem *>(owner->cast(owner->value, {tid})) : nullptr;
    bool found = parent && native_graphics_layout_contains(r, parent, record.value);
    if (r->error) return false;
    if (found) return true;
    invalidate(id);
    fail(r, ESTALE, "Graphics layout item is no longer present in its owner");
    return false;
}}
static uint32_t native_observe_graphics_layout(BqtRequest *r, QGraphicsLayoutItem *value, bool adopt = false, uint32_t depth = 0) {{
    if (!value) return 0;
    if (depth >= capacity) {{ fail(r, ELOOP, "Graphics layout ancestry is cyclic"); return 0; }}
    if (auto *item = value->graphicsItem(); item && item->toGraphicsObject())
        return native_observe_QGraphicsItem(r, item, 0, adopt);
    uint32_t owner = 0;
    auto *parent = value->parentLayoutItem();
    if (parent) {{
        uint32_t parent_id = native_observe_graphics_layout(r, parent, false, depth + 1);
        if (r->error) return 0;
        if (native_graphics_layout_contains(r, parent, value)) owner = parent_id;
        if (r->error) return 0;
    }}
    uint32_t known = native_known_token(value, {tid});
    if (!known && !value->ownedByLayout()) {{ fail(r, ENOTSUP, "An external graphics-layout item requires observed destruction"); return 0; }}
    uint32_t id = register_native_borrow(r, value, {tid}, owner);
    if (r->error) return 0;
    if (adopt && value->ownedByLayout() && !set_native_owner(r, id, owner)) return 0;
    if (owner && !entry(id)->native_observed) {{
        native_graphics_layout_observations[id & 65535u] = {{id, owner, value, false}};
        entry(id)->validate = validate_native_graphics_layout;
    }} else if (!owner && entry(id)->validate == validate_native_graphics_layout) {{
        native_graphics_layout_observations[id & 65535u] = {{}};
        entry(id)->validate = nullptr;
    }}
    return id;
}}
static bool native_graphics_layout_idle(BqtRequest *r, QGraphicsLayoutItem *value) {{
    uint32_t id = native_known_token(value, {tid});
    if (id && !native_children_idle(r, id)) return false;
    auto *e = entry(id);
    uint32_t own_pin = 0;
    if (native_call_scope) for (auto pin : native_call_scope->pins) if (pin == id) own_pin = 1;
    if (e && e->active_calls > own_pin) {{ fail(r, EBUSY, "Graphics layout is active in a suspended callback"); return false; }}
    return true;
}}
'''


def policy(g, name, f, args):
    declaring, method = f['declaring_class'], f['name']
    kind, index = None, None
    if f['constructor'] and ('QGraphicsLayout' in (name, *g.all_bases(name))):
        indices = [i for i, arg in enumerate(args) if arg.get('name') == 'QGraphicsLayoutItem' and arg.get('pointer')]
        if indices:
            kind, index = 'graphics_layout_constructor', indices[-1]
    elif declaring in ('QGraphicsGridLayout', 'QGraphicsLinearLayout'):
        if method in ('addItem', 'insertItem', 'removeItem'):
            kind = 'graphics_layout_remove' if method == 'removeItem' else 'graphics_layout_add'
            index = next(i for i, arg in enumerate(args) if arg.get('name') == 'QGraphicsLayoutItem')
        elif method == 'removeAt':
            kind = 'graphics_layout_remove_at'
    elif declaring == 'QGraphicsWidget' and method == 'setLayout':
        kind, index = 'graphics_layout_install', 0
    elif declaring == 'QGraphicsLayoutItem' and method == 'setParentLayoutItem':
        kind, index = 'graphics_layout_parent', 0
    if not kind:
        return None
    prepare(g)
    return dict(kind=kind, input=index)


def before(g, m, p):
    kind, i = p['kind'], p.get('input')
    if not kind.startswith('graphics_layout_'):
        return None
    slot = g.graphics_layout_slot
    if kind == 'graphics_layout_remove_at':
        index = g.argument(m['args'][0], 0)[1]
        return [f'if ({index} < 0 || {index} >= self->count()) return fail(r, EINVAL, "Graphics layout index is out of bounds");',
                f'auto *native_layout_member = self->itemAt({index});',
                'uint32_t native_layout_member_id = native_observe_graphics_layout(r, native_layout_member);',
                'if (r->error) return true;', 'if (!native_graphics_layout_idle(r, native_layout_member)) return true;']
    if kind == 'graphics_layout_parent':
        return ['if (self->parentLayoutItem() == a0) return true;',
                'if (native_graphics_layout_contains(r, self->parentLayoutItem(), self)) return fail(r, EBUSY, "Remove the item from its installed layout before changing its raw parent pointer");',
                'for (auto *parent = a0; parent; parent = parent->parentLayoutItem()) if (parent == self) return fail(r, ELOOP, "Graphics layout parenting would create a cycle");',
                'RetentionBatch retention_batch;',
                f'if (!retention_batch.add(r, r->self, {slot}, r->arguments[0].word, nullptr, false, false, 0)) return true;']
    if kind == 'graphics_layout_constructor':
        return [f'auto *native_layout_parent_item = a{i} ? a{i}->graphicsItem() : nullptr;',
                'auto *native_layout_parent_widget = native_layout_parent_item && native_layout_parent_item->isWidget() ? static_cast<QGraphicsWidget *>(native_layout_parent_item) : nullptr;',
                'uint32_t native_previous_layout_id = 0;',
                'if (native_layout_parent_widget) {',
                '    auto *old = native_layout_parent_widget->layout();',
                '    if (!native_graphics_layout_idle(r, old)) return true;',
                '    native_previous_layout_id = native_observe_graphics_layout(r, old);',
                '    if (r->error) return true;', '}',
                'RetentionBatch retention_batch;',
                f'if (!retention_batch.add(r, 0, {slot}, r->arguments[{i}].word, nullptr, false, true, 0)) return true;']
    if kind == 'graphics_layout_install':
        return ['if (self->layout() == a0) return true;',
                'if (!native_children_idle(r, r->self)) return true;',
                'if (a0 && a0->parentLayoutItem() && a0->parentLayoutItem() != self) return fail(r, EBUSY, "Graphics layout already has a different parent");',
                'if (!can_transfer_handle(r, r->arguments[0].word)) return true;',
                'NativeGraphicsParentEdge native_raw_parent;',
                'if (!native_raw_parent.suspend(r, r->arguments[0].word, r->self)) return true;',
                'if (a0 && reaches_token(r->arguments[0].word, r->self)) return fail(r, ELOOP, "Graphics layout installation would create a cycle");',
                'auto *native_previous_layout = self->layout();',
                'if (!native_graphics_layout_idle(r, native_previous_layout)) return true;',
                'uint32_t native_previous_layout_id = native_observe_graphics_layout(r, native_previous_layout);',
                'if (r->error) return true;']
    if kind == 'graphics_layout_remove':
        return [f'auto *native_layout_member = a{i};', f'uint32_t native_layout_member_id = r->arguments[{i}].word;',
                'if (!native_graphics_layout_idle(r, native_layout_member)) return true;']
    lines = [f'if (!a{i}) return fail(r, EINVAL, "Graphics layout member must not be null");',
             'NativeGraphicsParentEdge native_raw_parent;',
             f'if (!native_raw_parent.suspend(r, r->arguments[{i}].word, r->self)) return true;',
             f'if (reaches_token(r->arguments[{i}].word, r->self)) return fail(r, ELOOP, "Graphics layout adoption would create a cycle");',
             f'if (!native_graphics_layout_idle(r, a{i})) return true;',
             f'if (a{i}->ownedByLayout() && !can_transfer_handle(r, r->arguments[{i}].word)) return true;',
             'RetentionBatch retention_batch;',
             f'if (!retention_batch.add(r, r->self, {slot}, r->arguments[{i}].word, nullptr)) return true;']
    return lines


def after(g, m, p):
    kind, i = p['kind'], p.get('input')
    if not kind.startswith('graphics_layout_'):
        return None
    if kind in ('graphics_layout_remove', 'graphics_layout_remove_at'):
        return ['if (native_layout_member && !native_graphics_layout_contains(r, self, native_layout_member)) {',
                '    native_graphics_layout_forget_pins(native_layout_member_id);',
                '    native_observe_graphics_layout(r, native_layout_member, true);',
                '    if (r->error) return true;', '}']
    if kind == 'graphics_layout_constructor':
        return [f'auto *native_layout_created = get<{m["class"]}>(r, r->result.word, {g.ids[m["class"]]});',
                'if (r->error) return true;', 'if (native_previous_layout_id) invalidate(native_previous_layout_id);',
                'native_observe_graphics_layout(r, native_layout_created, true);',
                'if (r->error || !retention_batch.finish(r, r->result.word, true)) return true;']
    if kind == 'graphics_layout_parent':
        return ['if (!retention_batch.finish(r, 0, true)) return true;']
    if kind == 'graphics_layout_install':
        return ['native_raw_parent.accepted = true;',
                'if (native_previous_layout_id) invalidate(native_previous_layout_id);',
                'native_observe_graphics_layout(r, a0, true);', 'if (r->error) return true;']
    return [f'if (!entry(r->self) || !entry(r->arguments[{i}].word)) return fail(r, ESTALE, "Graphics layout item was destroyed");',
            f'if (!native_graphics_layout_contains(r, self, a{i})) return fail(r, EINVAL, "Qt rejected graphics layout adoption");',
            'native_raw_parent.accepted = true;',
            f'native_graphics_layout_forget_pins(r->arguments[{i}].word, r->self);',
            f'native_observe_graphics_layout(r, a{i}, true);',
            'if (r->error || !retention_batch.finish(r, 0, true)) return true;']


def before_result(g, m):
    ret = m.get('native_return', m['return'])
    if ret['kind'] != 'object' or not ret.get('pointer') or ret.get('owned'):
        return None
    name = ret['name']
    if 'QGraphicsLayoutItem' not in (name, *g.all_bases(name)) or g.classes[name]['qobject']:
        return None
    prepare(g)
    return ['native_observe_graphics_layout(r, returned);', 'if (r->error) return true;']
