"""Scene graph lifetime adaptation, used only behind the GUI render guard."""


def derives(g, name, base):
    return name in g.classes and (name == base or base in g.all_bases(name))


def prepare(g):
    if getattr(g, '_qsg_lifetimes_prepared', False) or 'QSGNode' not in g.ids:
        return
    g._qsg_lifetimes_prepared = True
    g.qsg_lifetime_slots = {name: g.retention_slots.setdefault('QSG.' + name, len(g.retention_slots) + 1)
                            for name in ('children', 'geometry', 'material', 'opaqueMaterial')}
    node_type = g.ids['QSGNode']
    g.retention_accessors['qsg_lifetimes'] = f'''
static uint32_t qsg_token(const void *pointer, uint16_t type) {{
    if (!pointer) return 0;
    for (uint32_t i = 1; i < capacity; ++i) {{
        auto &e = entries[i];
        if (e.value && e.cast && e.cast(e.value, type) == pointer) return token(i, e.generation);
    }}
    return 0;
}}
static void qsg_clear_pin(uint32_t owner, uint32_t slot, uint32_t key) {{
    owner = render_factory_retention_owner(owner);
    for (auto &edge : retentions)
        if (edge.owner == owner && edge.slot == slot && edge.key == key) edge = {{}};
}}
static uint32_t qsg_observe_node(BqtRequest *r, QSGNode *node) {{
    if (!node) return 0;
    uint32_t known = qsg_token(node, {node_type});
    if (known) return known;
    if (auto restored = render_factory_restore(r, node, {node_type}, 0)) return restored;
    if (r->error) return 0;
    if (!node->parent() || !(node->flags() & QSGNode::OwnedByParent)) {{
        fail(r, ENOTSUP, "Scene graph node has no observable owning parent"); return 0;
    }}
    uint32_t owner = qsg_observe_node(r, node->parent());
    if (r->error) return 0;
    return register_native_borrow(r, node, {node_type}, owner);
}}
static bool qsg_parent_allowed(BqtRequest *r, QSGNode *parent, QSGNode *child) {{
    if (!parent || !child) {{ fail(r, EINVAL, "Scene graph parent and child must not be null"); return false; }}
    for (auto *p = parent; p; p = p->parent())
        if (p == child) {{ fail(r, ELOOP, "Scene graph parenting would create a cycle"); return false; }}
    return true;
}}
static bool qsg_sync_child(BqtRequest *r, QSGNode *child, uint32_t id) {{
    uint32_t parent = child->parent() ? qsg_token(child->parent(), {node_type}) : 0;
    if (child->parent() && !parent) {{ fail(r, ENOTSUP, "Scene graph parent is not observed"); return false; }}
    return render_factory_sync_owner(r, id, (child->flags() & QSGNode::OwnedByParent) ? render_factory_retention_owner(parent) : 0);
}}
static bool qsg_member_owned_allowed(BqtRequest *r, uint32_t owner, uint32_t target) {{
    owner = render_factory_retention_owner(owner);
    if (!can_transfer_handle(r, target)) return false;
    if (target && reaches_token(target, owner)) {{ fail(r, ELOOP, "Scene graph member ownership would create a cycle"); return false; }}
    auto *e = entry(target);
    if (!e || (!e->owned && !e->native_observed)) {{
        fail(r, EINVAL, "Inline or unobserved scene graph members cannot become owned allocations"); return false;
    }}
    if (e->native_owner && e->native_owner != owner) {{ fail(r, EBUSY, "Scene graph member already has an owner"); return false; }}
    for (const auto &edge : retentions)
        if (edge.owner && edge.owner != owner && edge.target == target) {{ fail(r, EBUSY, "Scene graph member is shared by another owner"); return false; }}
    return true;
}}
'''


def policy(g, name, f, args):
    if not derives(g, name, 'QSGNode'):
        return None
    prepare(g)
    method = f['name']
    if method in ('appendChildNode', 'prependChildNode', 'insertChildNodeBefore', 'insertChildNodeAfter'):
        return {'kind': 'child_add', 'anchor': method.startswith('insert')}
    if method in ('removeChildNode', 'removeAllChildNodes', 'reparentChildNodesTo'):
        return {'kind': 'children_remove', 'method': method}
    if method in ('setFlag', 'setFlags'):
        return {'kind': 'flags'}
    members = {'setGeometry': ('geometry', 'QSGGeometry', 'OwnsGeometry'),
               'setMaterial': ('material', 'QSGMaterial', 'OwnsMaterial'),
               'setOpaqueMaterial': ('opaqueMaterial', 'QSGMaterial', 'OwnsOpaqueMaterial')}
    if method in members:
        prop, target, flag = members[method]
        return {'kind': 'member', 'property': prop, 'target': target, 'flag': flag}
    return None


def _members(g, m):
    result = []
    if 'QSGBasicGeometryNode' in g.ids:
        result.append(('geometry', 'QSGGeometry', 'OwnsGeometry'))
    if 'QSGGeometryNode' in g.ids:
        result += [('material', 'QSGMaterial', 'OwnsMaterial'), ('opaqueMaterial', 'QSGMaterial', 'OwnsOpaqueMaterial')]
    return result


def before(g, m):
    p = (m.get('retention') or {}).get('qsg')
    if not p:
        return []
    slots = g.qsg_lifetime_slots
    kind = p['kind']
    if kind == 'child_add':
        lines = ['if (!qsg_parent_allowed(r, self, a0)) return true;',
                 'if ((a0->flags() & QSGNode::OwnedByParent) && !can_transfer_handle(r, r->arguments[0].word)) return true;',
                 'if (reaches_token(r->arguments[0].word, r->self)) return fail(r, ELOOP, "Scene graph parenting would create a retention cycle");',
                 'if (a0->parent()) return fail(r, EBUSY, "Detach the scene graph node before adding it");',
                 'if (auto *e = entry(r->arguments[0].word); e && e->native_owner) return fail(r, EBUSY, "The scene graph node already has a native owner");',
                 'RetentionBatch qsg_batch;']
        if p['anchor']:
            lines += ['if (!a1 || a1->parent() != self) return fail(r, EINVAL, "Scene graph insertion anchor is not a child of this node");']
        lines += [f'if (!(a0->flags() & QSGNode::OwnedByParent) && !qsg_batch.add(r, r->self, {slots["children"]}, r->arguments[0].word, nullptr)) return true;']
        lines += ['auto qsg_factory_adoption = (a0->flags() & QSGNode::OwnedByParent) ? render_factory_prepare_adoption(r, r->arguments[0].word, r->self) : nullptr;',
                  'if (r->error) return true;']
        return lines
    if kind == 'children_remove':
        method = p['method']
        lines = ['std::vector<uint32_t> qsg_children;', 'RetentionBatch qsg_batch;']
        if method == 'removeChildNode':
            lines += ['if (!a0 || a0->parent() != self) return fail(r, EINVAL, "Scene graph node is not a child of this parent");',
                      'qsg_children.push_back(r->arguments[0].word);']
        else:
            if method == 'reparentChildNodesTo':
                lines += ['if (!a0 || a0 == self) return fail(r, EINVAL, "Scene graph reparenting requires another parent");']
            lines += ['for (auto *node = self->firstChild(); node; node = node->nextSibling()) {',
                      '    uint32_t id = qsg_observe_node(r, node);', '    if (r->error) return true;',
                      '    qsg_children.push_back(id);']
            if method == 'reparentChildNodesTo':
                lines += ['    if (!qsg_parent_allowed(r, a0, node)) return true;',
                          '    if (!can_transfer_handle(r, id)) return true;',
                          '    if (reaches_token(id, r->arguments[0].word)) return fail(r, ELOOP, "Scene graph reparenting would create a retention cycle");',
                          f'    if (!(node->flags() & QSGNode::OwnedByParent) && !qsg_batch.add(r, r->arguments[0].word, {slots["children"]}, id, nullptr)) return true;']
            lines += ['}']
        return lines
    if kind == 'member':
        prop, target, flag = p['property'], p['target'], p['flag']
        sid = slots[prop]
        lines = [f'auto *qsg_previous = self->{prop}();',
                'if (qsg_previous == a0) return true;',
                f'bool qsg_owns_member = bool(self->flags() & QSGNode::{flag});',
                f'uint32_t qsg_previous_id = qsg_token(qsg_previous, {g.ids[target]});',
                'uint32_t qsg_previous_anchor = render_factory_retention_owner(qsg_previous_id);',
                'if (qsg_owns_member && qsg_previous_id && active_in_subtree(qsg_previous_id)) return fail(r, EBUSY, "Scene graph member is active in a callback");',
                'if (qsg_owns_member && a0 && !qsg_member_owned_allowed(r, r->self, r->arguments[0].word)) return true;',
                'RetentionBatch qsg_batch;',
                f'if (!qsg_batch.add(r, r->self, {sid}, qsg_owns_member ? 0 : r->arguments[0].word, nullptr, false, false, 0)) return true;',
                'if (qsg_owns_member && qsg_previous_id) { render_factory_replacing_allocation(qsg_previous_anchor); invalidate(qsg_previous_id); }']
        if prop in ('material', 'opaqueMaterial'):
            other, other_flag = ('opaqueMaterial', 'OwnsOpaqueMaterial') if prop == 'material' else ('material', 'OwnsMaterial')
            lines.insert(3, f'if (a0 && (qsg_owns_member || (self->flags() & QSGNode::{other_flag})) && self->{other}() == a0) return fail(r, EINVAL, "An owned material allocation cannot be shared between node slots");')
            lines.insert(4, f'if (qsg_owns_member && qsg_previous && self->{other}() == qsg_previous) return fail(r, EINVAL, "Clear the other material slot before replacing this owned material");')
        lines[-1:-1] = ['auto qsg_factory_adoption = qsg_owns_member ? render_factory_prepare_adoption(r, r->arguments[0].word, r->self) : nullptr;',
                       'if (r->error) return true;']
        return lines
    if kind == 'flags':
        enabled = g.argument(m['args'][1], 1)[1] if len(m['args']) > 1 else 'true'
        flag = g.argument(m['args'][0], 0)[1]
        lines = ['auto qsg_before = self->flags();', f'auto qsg_after = {enabled} ? (qsg_before | {flag}) : (qsg_before & ~QSGNode::Flags({flag}));',
                 'auto *qsg_geometry_node = (self->type() == QSGNode::GeometryNodeType || self->type() == QSGNode::ClipNodeType) ? static_cast<QSGBasicGeometryNode *>(static_cast<QSGNode *>(self)) : nullptr;',
                 'auto *qsg_material_node = self->type() == QSGNode::GeometryNodeType ? static_cast<QSGGeometryNode *>(static_cast<QSGNode *>(self)) : nullptr;',
                 'if (qsg_material_node && (qsg_after & (QSGNode::OwnsMaterial | QSGNode::OwnsOpaqueMaterial)) && qsg_material_node->material() && qsg_material_node->material() == qsg_material_node->opaqueMaterial()) return fail(r, EINVAL, "An owned material allocation cannot be shared between node slots");',
                 'uint32_t qsg_parent = self->parent() ? qsg_token(self->parent(), ' + str(g.ids['QSGNode']) + ') : 0;',
                 'bool qsg_child_changed = bool((qsg_before ^ qsg_after) & QSGNode::OwnedByParent);',
                 'if (qsg_child_changed && self->parent() && !qsg_parent) return fail(r, ENOTSUP, "Cannot change ownership under an unobserved scene graph parent");',
                 'if (qsg_child_changed && qsg_parent && !can_transfer_handle(r, r->self)) return true;',
                 'if (qsg_child_changed && qsg_parent && (qsg_after & QSGNode::OwnedByParent) && reaches_token(r->self, qsg_parent)) return fail(r, ELOOP, "Scene graph ownership would create a retention cycle");',
                 'RetentionBatch qsg_batch;',
                 f'if (qsg_child_changed && qsg_parent && !(qsg_after & QSGNode::OwnedByParent) && !qsg_batch.add(r, qsg_parent, {slots["children"]}, r->self, nullptr)) return true;',
                 'auto qsg_child_adoption = qsg_child_changed && qsg_parent && (qsg_after & QSGNode::OwnedByParent) ? render_factory_prepare_adoption(r, r->self, qsg_parent) : nullptr;',
                 'if (r->error) return true;']
        for prop, target, own in _members(g, m):
            receiver = 'qsg_geometry_node' if prop == 'geometry' else 'qsg_material_node'
            lines += [f'auto *qsg_ptr_{prop} = {receiver} ? {receiver}->{prop}() : nullptr;',
                      f'uint32_t qsg_{prop} = qsg_token(qsg_ptr_{prop}, {g.ids[target]});',
                      f'bool qsg_change_{prop} = bool((qsg_before ^ qsg_after) & QSGNode::{own});',
                      f'if (qsg_change_{prop} && qsg_ptr_{prop} && !qsg_{prop} && (qsg_before & QSGNode::{own})) qsg_{prop} = register_native_borrow(r, qsg_ptr_{prop}, {g.ids[target]}, r->self);',
                      'if (r->error) return true;',
                      f'if (qsg_change_{prop} && (qsg_after & QSGNode::{own}) && !{receiver}) return fail(r, EINVAL, "Ownership flag is not valid for this node type");',
                      f'if (qsg_change_{prop} && qsg_ptr_{prop} && (qsg_after & QSGNode::{own}) && !qsg_member_owned_allowed(r, r->self, qsg_{prop})) return true;',
                      f'if (qsg_change_{prop} && !(qsg_after & QSGNode::{own}) && !qsg_batch.add(r, r->self, {slots[prop]}, qsg_{prop}, nullptr, false, false, 0)) return true;',
                      f'auto qsg_adoption_{prop} = qsg_change_{prop} && qsg_{prop} && (qsg_after & QSGNode::{own}) ? render_factory_prepare_adoption(r, qsg_{prop}, r->self) : nullptr;',
                      'if (r->error) return true;']
        return lines
    return []


def after(g, m):
    p = (m.get('retention') or {}).get('qsg')
    if not p:
        return []
    slots, kind = g.qsg_lifetime_slots, p['kind']
    if kind == 'child_add':
        return ['if (!qsg_sync_child(r, a0, r->arguments[0].word)) return true;',
                'if (!qsg_batch.finish(r, 0, true)) return true;',
                'if (qsg_factory_adoption && !qsg_factory_adoption->commit(r)) return true;']
    if kind == 'children_remove':
        return ['for (auto id : qsg_children) {',
                f'    qsg_clear_pin(r->self, {slots["children"]}, id);',
                f'    auto *node = get<QSGNode>(r, id, {g.ids["QSGNode"]});',
                '    if (r->error || !qsg_sync_child(r, node, id)) return true;', '}',
                'if (!qsg_batch.finish(r, 0, true)) return true;']
    if kind == 'member':
        return ['if (qsg_owns_member && qsg_previous_id) render_factory_replaced_allocation(qsg_previous_anchor);',
                'if (qsg_owns_member && a0 && !render_factory_sync_owner(r, r->arguments[0].word, render_factory_retention_owner(r->self))) return true;',
                'if (!qsg_batch.finish(r, 0, true)) return true;',
                'if (qsg_factory_adoption && !qsg_factory_adoption->commit(r)) return true;']
    if kind == 'flags':
        lines = ['if (qsg_child_changed && self->parent()) {',
                 '    if (!qsg_sync_child(r, self, r->self)) return true;',
                 f'    if (qsg_after & QSGNode::OwnedByParent) qsg_clear_pin(qsg_parent, {slots["children"]}, r->self);', '}']
        for prop, _, own in _members(g, m):
            lines += [f'if (qsg_change_{prop} && qsg_{prop}) {{',
                      f'    if (!render_factory_sync_owner(r, qsg_{prop}, (qsg_after & QSGNode::{own}) ? render_factory_retention_owner(r->self) : 0)) return true;',
                      f'    if (qsg_after & QSGNode::{own}) qsg_clear_pin(r->self, {slots[prop]}, 0);', '}']
        lines += ['if (!qsg_batch.finish(r, 0, true)) return true;',
                  'if (qsg_child_adoption && !qsg_child_adoption->commit(r)) return true;']
        for prop, _, _ in _members(g, m):
            lines += [f'if (qsg_adoption_{prop} && !qsg_adoption_{prop}->commit(r)) return true;']
        return lines
    return []


def before_result(g, m):
    f, ret = m['function'], m.get('native_return', m['return'])
    if f['constructor'] or ret['kind'] != 'object' or ret.get('owned'):
        return None
    if derives(g, ret['name'], 'QSGNode'):
        prepare(g)
        return ['if (returned) qsg_observe_node(r, const_cast<QSGNode *>(static_cast<const QSGNode *>(returned)));',
                'if (r->error) return true;']
    if derives(g, m['class'], 'QSGNode') and ret.get('name') in ('QSGGeometry', 'QSGMaterial'):
        prepare(g)
        native = ret['name']
        return [f'if (returned) register_native_borrow(r, returned, {g.ids[native]}, r->self);',
                'if (r->error) return true;']
    return None
