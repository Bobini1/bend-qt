"""Observed ownership for Qt's non-QObject item families.

The rules describe ownership operations and model observations, not class
selection. Class discovery and pointer adjustment remain metadata driven.
"""

FAMILIES = ('QStandardItem', 'QTreeWidgetItem', 'QListWidgetItem', 'QTableWidgetItem',
            'QGraphicsItem', 'QLayoutItem', 'QUndoCommand')


def family(g, name):
    for base in FAMILIES:
        if name == base or base in g.all_bases(name):
            return base
    return None


def prepare(g):
    if getattr(g, '_native_lifetimes_prepared', False):
        return
    g._native_lifetimes_prepared = True
    common = '''
template<class T> static uint32_t native_known_token(T *value, uint16_t type) {
    if (!value) return 0;
    for (uint32_t i = 1; i < capacity; ++i) {
        auto &e = entries[i];
        if (e.value && e.cast && e.cast(e.value, type) == value) return token(i, e.generation);
    }
    return 0;
}
template<class T> static void native_forget_pointer(T *value, uint16_t type) {
    uint32_t id = native_known_token(value, type);
    if (id) invalidate(id);
}
template<class T> static bool native_pointer_idle(BqtRequest *r, T *value, uint16_t type) {
    uint32_t id = native_known_token(value, type);
    if (id && active_in_subtree(id)) { fail(r, EBUSY, "Native item is active in a suspended callback"); return false; }
    return true;
}
static bool native_children_idle(BqtRequest *r, uint32_t owner) {
    for (uint32_t i = 1; i < capacity; ++i) {
        auto &e = entries[i];
        uint32_t id = token(i, e.generation);
        uint32_t current_calls = 0;
        if (native_call_scope) for (auto pin : native_call_scope->pins) if (pin == id) ++current_calls;
        if (e.value && id != owner && e.active_calls > current_calls && reaches_token(owner, id)) {
            fail(r, EBUSY, "A native child is active in a suspended callback"); return false;
        }
    }
    return true;
}
static bool native_model_idle(BqtRequest *r, QAbstractItemModel *model) {
    for (uint32_t depth = 0; model && depth < capacity; ++depth) {
        for (uint32_t i = 1; i < capacity; ++i)
            if (entries[i].value && entries[i].object == model && !native_children_idle(r, token(i, entries[i].generation))) return false;
        auto *proxy = qobject_cast<QAbstractProxyModel *>(model);
        model = proxy ? proxy->sourceModel() : nullptr;
    }
    return true;
}
'''
    g.retention_accessors['native_lifetime_common'] = common
    if 'QUndoCommand' in g.ids and 'QUndoStack' in g.ids:
        g.retention_accessors['native_undo_observation'] = f'''
struct NativeUndoObservation {{ uint32_t id, owner; const QUndoCommand *value; }};
static SlotTable<NativeUndoObservation> native_undo_observations;
static bool validate_native_undo(BqtRequest *r, uint32_t id) {{
    auto record = native_undo_observations[id & 65535u];
    if (record.id != id) return true;
    auto *owner = entry(record.owner);
    if (owner && owner->validate && !owner->validate(r, record.owner)) return false;
    owner = entry(record.owner);
    bool found = false;
    if (owner && owner->object) {{
        if (auto *stack = qobject_cast<QUndoStack *>(owner->object))
            for (int n = 0; n < stack->count(); ++n) if (stack->command(n) == record.value) found = true;
    }} else if (owner && owner->cast) {{
        if (auto *command = static_cast<QUndoCommand *>(owner->cast(owner->value, {g.ids['QUndoCommand']})))
            for (int n = 0; n < command->childCount(); ++n) if (command->child(n) == record.value) found = true;
    }}
    if (found) return true;
    invalidate(id);
    fail(r, ESTALE, "Undo command is no longer present in its native owner");
    return false;
}}
'''
    for cls in FAMILIES:
        if cls not in g.ids:
            continue
        tid = g.ids[cls]
        lines = [f'template<class T> static uint32_t native_observe_{cls}(BqtRequest *r, T *value, uint32_t hint = 0, bool adopt = false, uint16_t type = {tid}) {{',
                 '    if (!value) return 0;', '    uint32_t owner = hint;']
        if cls == 'QStandardItem':
            lines += ['    auto *model = value->model();',
                      f'    uint32_t model_id = model ? borrow(r, model, {g.ids["QStandardItemModel"]}) : 0;',
                      f'    if (value->parent()) owner = native_observe_{cls}(r, value->parent());',
                      '    else if (model_id) owner = model_id;']
        elif cls in ('QTreeWidgetItem', 'QListWidgetItem', 'QTableWidgetItem'):
            view, getter = {'QTreeWidgetItem': ('QTreeWidget', 'treeWidget'),
                            'QListWidgetItem': ('QListWidget', 'listWidget'),
                            'QTableWidgetItem': ('QTableWidget', 'tableWidget')}[cls]
            lines += [f'    auto *view = value->{getter}();',
                      f'    uint32_t view_id = view ? borrow(r, view, {g.ids[view]}) : 0;',
                      f'    uint32_t model_id = view ? borrow(r, view->model(), {g.ids["QAbstractItemModel"]}) : 0;']
            if cls == 'QTreeWidgetItem':
                lines += [f'    if (value->parent()) owner = native_observe_{cls}(r, value->parent());',
                          '    else if (view_id) owner = view_id;']
            else:
                lines += ['    if (view_id) owner = view_id;']
        elif cls == 'QGraphicsItem':
            lines += [f'    if (value->parentItem()) owner = native_observe_{cls}(r, value->parentItem());',
                      f'    else if (value->scene()) owner = borrow(r, value->scene(), {g.ids["QGraphicsScene"]});']
        lines += ['    if (r->error) return 0;', '    uint32_t known = native_known_token(value, type);']
        if cls == 'QStandardItem':
            lines += ['    if (!known && model && !value->index().isValid() && value != model->invisibleRootItem()) {',
                      '        fail(r, ENOTSUP, "A native-created header item needs a deletion observer"); return 0;', '    }']
        elif cls in ('QTreeWidgetItem', 'QTableWidgetItem'):
            root = ' && value != view->invisibleRootItem()' if cls == 'QTreeWidgetItem' else ''
            lines += [f'    if (!known && view && !view->indexFromItem(value).isValid(){root}) {{',
                      '        fail(r, ENOTSUP, "A native-created header item needs a deletion observer"); return 0;', '    }']
        if cls == 'QGraphicsItem':
            lines += [f'    if (auto *object = value->toGraphicsObject()) {{',
                      f'        uint32_t id = borrow(r, object, {g.ids["QGraphicsObject"]});',
                      '        if (adopt && id) set_native_owner(r, id, owner);', '        return id;', '    }']
        elif cls == 'QLayoutItem':
            lines += ['    if (auto *layout = value->layout()) {',
                      f'        uint32_t id = borrow(r, layout, {g.ids["QLayout"]});',
                      '        if (adopt && id) set_native_owner(r, id, owner);', '        return id;', '    }']
        lines += ['    uint32_t id = register_native_borrow(r, value, type, owner);',
                  '    if (r->error || !id) return 0;',
                  '    if (adopt && !set_native_owner(r, id, owner)) return 0;']
        if cls == 'QStandardItem':
            lines += ['    if (model_id && value->index().isValid())',
                      '        observe_native_model_item(r, id, model_id, value->index());']
        elif cls in ('QTreeWidgetItem', 'QListWidgetItem', 'QTableWidgetItem'):
            lines += ['    if (model_id && view->indexFromItem(value).isValid())',
                      '        observe_native_model_item(r, id, model_id, view->indexFromItem(value));']
        elif cls == 'QLayoutItem':
            lines += ['    observe_native_layout_item(id, owner, value);',
                      '    if (!known && owner && value->widget()) QObject::connect(value->widget(), &QObject::destroyed,',
                      '        [id] { auto *e = entry(id); if (!e) return;',
                      '            auto *pointer = e->value; auto destroy = e->destroy;',
                      '            bool detached = e->owned && !e->native_owner && !e->shared_managed;',
                      '            invalidate(id); if (detached && destroy) destroy(pointer); });']
        elif cls == 'QUndoCommand':
            lines += ['    if (!known && owner) {',
                      '        native_undo_observations[id & 65535u] = {id, owner, value};',
                      '        entry(id)->validate = validate_native_undo;', '    }']
        lines += ['    return id;', '}', '']
        g.retention_accessors['native_observe_' + cls] = '\n'.join(lines)


def policy(g, name, f, args):
    import ownership_collections
    collection = ownership_collections.policy(g, name, f, args)
    if collection:
        prepare(g)
        return collection
    import graphics_layouts
    graphics_layout = graphics_layouts.policy(g, name, f, args)
    if graphics_layout:
        return graphics_layout
    declaring, method = f['declaring_class'], f['name']
    if declaring == 'QOpenGLContext' and method in ('functions', 'extraFunctions', 'create'):
        prepare(g)
        return {'kind': 'gl_context'}
    native_args = [(i, family(g, a.get('name', ''))) for i, a in enumerate(args) if a['kind'] == 'object' and a.get('pointer')]
    native_args = [(i, cls) for i, cls in native_args if cls]
    lists = [(i, family(g, a['children'][0].get('name', ''))) for i, a in enumerate(args)
             if a['kind'] == 'list' and len(a.get('children', [])) == 1
             and a['children'][0]['kind'] == 'object']
    lists = [(i, cls) for i, cls in lists if cls]
    if f['constructor']:
        own_family = family(g, name)
        if own_family:
            parents = [(i, a) for i, a in enumerate(args) if a['kind'] == 'object' and a.get('pointer') and
                       (family(g, a.get('name', '')) or a.get('name') in ('QTreeWidget', 'QListWidget', 'QTableWidget'))]
            if parents:
                prepare(g)
                return {'kind': 'constructor', 'family': own_family, 'parent': parents[-1][0]}
    adopt = {
        'QStandardItemModel': {'setItem', 'setHorizontalHeaderItem', 'setVerticalHeaderItem', 'setItemPrototype', 'appendRow', 'insertRow', 'appendColumn', 'insertColumn'},
        'QStandardItem': {'setChild', 'appendRow', 'insertRow', 'appendRows', 'insertRows', 'appendColumn', 'insertColumn'},
        'QTreeWidget': {'addTopLevelItem', 'insertTopLevelItem', 'addTopLevelItems', 'insertTopLevelItems', 'setHeaderItem'},
        'QTreeWidgetItem': {'addChild', 'insertChild', 'addChildren', 'insertChildren'},
        'QListWidget': {'addItem', 'insertItem'},
        'QTableWidget': {'setItem', 'setHorizontalHeaderItem', 'setVerticalHeaderItem', 'setItemPrototype'},
        'QGraphicsScene': {'addItem'},
        'QGraphicsItem': {'setParentItem', 'setGroup'}, 'QGraphicsItemGroup': {'addToGroup'},
        'QLayout': {'addItem'}, 'QBoxLayout': {'addItem', 'insertItem'},
        'QGridLayout': {'addItem'}, 'QFormLayout': {'setItem'},
    }
    if method in adopt.get(declaring, set()) and native_args:
        prepare(g)
        i, cls = native_args[-1]
        return {'kind': 'adopt', 'input': i, 'family': cls}
    if method in adopt.get(declaring, set()) and lists:
        prepare(g)
        i, cls = lists[-1]
        return {'kind': 'adopt_many', 'input': i, 'family': cls}
    if (declaring, method) == ('QGraphicsScene', 'removeItem'):
        prepare(g)
        return {'kind': 'detach', 'input': 0, 'family': 'QGraphicsItem'}
    if (declaring, method) in (('QTreeWidgetItem', 'removeChild'), ('QLayout', 'removeItem'), ('QGraphicsItemGroup', 'removeFromGroup')):
        prepare(g)
        return {'kind': 'detach', 'input': 0, 'family': native_args[0][1]}
    if declaring == 'QGraphicsScene' and method == 'destroyItemGroup':
        prepare(g)
        return {'kind': 'destroy_group'}
    if declaring == 'QGraphicsScene' and method == 'createItemGroup':
        prepare(g)
        return {'kind': 'create_group'}
    if declaring == 'QStandardItem' and method in ('removeRow', 'removeRows', 'removeColumn', 'removeColumns', 'setRowCount', 'setColumnCount'):
        prepare(g)
        return {'kind': 'remove_children', 'row': 'Row' in method, 'many': method.endswith('s'), 'resize': method.startswith('set')}
    is_model = name == 'QAbstractItemModel' or 'QAbstractItemModel' in g.all_bases(name)
    if is_model and method in ('removeRow', 'removeRows', 'removeColumn', 'removeColumns', 'setRowCount', 'setColumnCount'):
        prepare(g)
        return {'kind': 'model_remove'}
    if declaring == 'QTableWidget' and method in ('removeRow', 'removeColumn', 'setRowCount', 'setColumnCount', 'clearContents'):
        prepare(g)
        return {'kind': 'view_remove'}
    if declaring == 'QFormLayout' and method == 'removeRow':
        prepare(g)
        return {'kind': 'view_remove'}
    if declaring in ('QStandardItemModel', 'QTreeWidget', 'QListWidget', 'QTableWidget', 'QGraphicsScene') and method == 'clear':
        prepare(g)
        return {'kind': 'clear'}
    take_getters = {('QListWidget', 'takeItem'): 'item', ('QTreeWidget', 'takeTopLevelItem'): 'topLevelItem',
                    ('QTreeWidgetItem', 'takeChild'): 'child', ('QTableWidget', 'takeItem'): 'item',
                    ('QTableWidget', 'takeHorizontalHeaderItem'): 'horizontalHeaderItem',
                    ('QTableWidget', 'takeVerticalHeaderItem'): 'verticalHeaderItem',
                    ('QStandardItemModel', 'takeItem'): 'item', ('QStandardItem', 'takeChild'): 'child',
                    ('QLayout', 'takeAt'): 'itemAt', ('QBoxLayout', 'takeAt'): 'itemAt',
                    ('QGridLayout', 'takeAt'): 'itemAt', ('QFormLayout', 'takeAt'): 'itemAt',
                    ('QStackedLayout', 'takeAt'): 'itemAt'}
    if (declaring, method) in take_getters:
        prepare(g)
        return {'kind': 'take', 'getter': take_getters[declaring, method], 'family': family(g, f['return']['name'])}
    if declaring in ('QStandardItem', 'QStandardItemModel') and method in ('takeRow', 'takeColumn'):
        prepare(g)
        return {'kind': 'take_many', 'family': 'QStandardItem', 'row': method == 'takeRow',
                'getter': 'item' if declaring == 'QStandardItemModel' else 'child'}
    if declaring == 'QTreeWidgetItem' and method == 'takeChildren':
        prepare(g)
        return {'kind': 'take_many', 'family': 'QTreeWidgetItem', 'getter': 'child'}
    return None


def _argument(g, m, i):
    return g.argument(m['args'][i], i)[1]


def _old_getter(g, m, p):
    method = m['function']['name']
    getter = {'setItem': 'item', 'setChild': 'child', 'setHorizontalHeaderItem': 'horizontalHeaderItem',
              'setVerticalHeaderItem': 'verticalHeaderItem', 'setHeaderItem': 'headerItem',
              'setItemPrototype': 'itemPrototype'}.get(method)
    if not getter:
        return None
    if m['function']['declaring_class'] == 'QFormLayout' and method == 'setItem':
        getter = 'itemAt'
    inputs = [_argument(g, m, i) for i in range(p['input'])]
    # The 2-argument setItem(row,item) / setChild(row,item) selects column zero.
    return f'self->{getter}({", ".join(inputs)})'


def before(g, m):
    p = (m.get('retention') or {}).get('native')
    if not p:
        return []
    import ownership_collections
    collection = ownership_collections.before(g, m, p)
    if collection is not None:
        return collection
    import graphics_layouts
    graphics_layout = graphics_layouts.before(g, m, p)
    if graphics_layout is not None:
        if not m['function']['constructor']:
            graphics_layout.insert(0, 'if (entry(r->self)->active_calls > 1) return fail(r, EBUSY, "Graphics layout mutation during a suspended callback is unsafe");')
        return graphics_layout
    kind = p['kind']
    if kind == 'clear':
        return ['if (!native_children_idle(r, r->self)) return true;', 'invalidate_native_children(r->self);']
    if kind == 'model_remove':
        return ['if (!native_model_idle(r, self)) return true;']
    if kind == 'view_remove':
        return ['if (!native_children_idle(r, r->self)) return true;']
    if kind == 'gl_context' and m['function']['name'] == 'create':
        return ['if (!native_children_idle(r, r->self)) return true;']
    if kind == 'detach':
        return [f'NativeTakeScope native_take_scope(r->arguments[{p["input"]}].word);']
    if kind == 'destroy_group':
        tid = g.ids['QGraphicsItem']
        return ['if (!a0 || a0->scene() != self) return fail(r, EINVAL, "Graphics group does not belong to this scene");',
                'if (auto *e = entry(r->arguments[0].word); e && e->active_calls > 1) return fail(r, EBUSY, "Graphics group is active in a suspended callback");',
                'uint32_t next_owner = a0->parentItem() ? native_observe_QGraphicsItem(r, a0->parentItem()) : r->self;',
                'if (r->error) return true;',
                'for (auto *child : a0->childItems()) {',
                '    uint32_t id = native_observe_QGraphicsItem(r, child);',
                '    if (r->error || !set_native_owner(r, id, next_owner)) return true;', '}',
                f'native_forget_pointer(static_cast<QGraphicsItem *>(a0), {tid});']
    if kind == 'create_group':
        return ['for (auto *value : *a0) {',
                '    if (!value) return fail(r, EINVAL, "Graphics group members must not be null");',
                '    if (value->scene() != self) return fail(r, EINVAL, "Graphics group members must belong to this scene");',
                f'    uint32_t id = native_known_token(value, {g.ids["QGraphicsItem"]});',
                '    if (!can_transfer_handle(r, id)) return true;',
                '}']
    if kind == 'remove_children':
        start = _argument(g, m, 0)
        count = _argument(g, m, 1) if p['many'] else '1'
        outer = 'self->rowCount()' if p['row'] else 'self->columnCount()'
        inner = 'self->columnCount()' if p['row'] else 'self->rowCount()'
        if p.get('resize'):
            count = f'int64_t({outer}) - int64_t({start})'
        child = 'self->child(int(n), j)' if p['row'] else 'self->child(j, int(n))'
        return ['if (!native_children_idle(r, r->self)) return true;',
                f'int64_t native_first = {start}, native_count = {count};',
                f'if (native_first >= 0 && native_count > 0) for (int64_t n = native_first; n < native_first + native_count && n < {outer}; ++n)',
                f'    for (int j = 0; j < {inner}; ++j) native_forget_pointer({child}, {g.ids["QStandardItem"]});']
    if kind == 'take_many':
        cls = p['family']
        if cls == 'QTreeWidgetItem':
            count, value = 'self->childCount()', 'self->child(n)'
        else:
            count = 'self->columnCount()' if p['row'] else 'self->rowCount()'
            arg = _argument(g, m, 0)
            value = f'self->{p["getter"]}({arg}, n)' if p['row'] else f'self->{p["getter"]}(n, {arg})'
        return ['NativeTakeBatch native_take_batch;', f'for (int n = 0; n < {count}; ++n) {{',
                f'    uint32_t id = native_observe_{cls}(r, {value}, r->self);',
                '    if (r->error) return true;', '    native_take_batch.add(id);', '}']
    if kind == 'adopt_many':
        i, cls = p['input'], p['family']
        return ['std::vector<uint32_t> native_adopted_ids;', f'for (auto *value : *a{i}) {{',
                '    if (!value) continue;', f'    uint32_t id = native_known_token(value, {g.ids[cls]});',
                '    auto *e = entry(id);', '    if (!e) return fail(r, ESTALE, "Invalid native item in collection");',
                '    if (!can_transfer_handle(r, id)) return true;',
                '    for (auto previous : native_adopted_ids) if (previous == id) return fail(r, EINVAL, "An owning item collection cannot contain duplicate items");',
                '    native_adopted_ids.push_back(id);',
                '    if (e->native_owner) return fail(r, EBUSY, "Detach native item before bulk adoption");',
                '    if (reaches_token(id, r->self)) return fail(r, ELOOP, "Bulk native item adoption would create a cycle");', '}']
    if kind == 'take':
        args = ', '.join(_argument(g, m, i) for i in range(len(m['args'])))
        cls = p['family']
        if not cls:
            return []
        return [f'auto *native_taken = self->{p["getter"]}({args});',
                f'uint32_t native_taken_id = native_observe_{cls}(r, native_taken, r->self);',
                'if (r->error) return true;', 'NativeTakeScope native_take_scope(native_taken_id);']
    if kind == 'adopt':
        i, cls = p['input'], p['family']
        declaring, method = m['function']['declaring_class'], m['function']['name']
        reverse = m['function']['name'] in ('setParentItem', 'setGroup')
        owner = f'r->arguments[{i}].word' if reverse else 'r->self'
        child = 'r->self' if reverse else f'r->arguments[{i}].word'
        lines = [f'if (!can_transfer_handle(r, {child})) return true;',
                 f'if ({owner} && {child} && reaches_token({child}, {owner})) return fail(r, ELOOP, "Native item parenting would create a cycle");']
        # Validate before deleting the replaced entry. Several Qt setters
        # reject already-adopted inputs without replacing the existing item.
        old = _old_getter(g, m, p)
        if old:
            lines += [f'auto *native_replaced = {old};',
                      f'if (native_replaced == a{i}) return true;']
        if declaring not in ('QGraphicsItem', 'QGraphicsScene', 'QGraphicsItemGroup'):
            lines += [f'if (auto *e = entry(r->arguments[{i}].word); e && e->native_owner) return fail(r, EBUSY, "Detach the native item from its current owner before adoption");']
        if declaring == 'QTableWidget' and method == 'setItem':
            row, column = _argument(g, m, 0), _argument(g, m, 1)
            lines += [f'if ({row} < 0 || {row} >= self->rowCount() || {column} < 0 || {column} >= self->columnCount()) return fail(r, EINVAL, "Table item position is outside the existing table");']
        if method in ('setHorizontalHeaderItem', 'setVerticalHeaderItem'):
            position = _argument(g, m, 0)
            lines += [f'if ({position} < 0) return fail(r, EINVAL, "Header position must not be negative");']
            if declaring == 'QTableWidget':
                bound = 'columnCount' if method == 'setHorizontalHeaderItem' else 'rowCount'
                lines += [f'if ({position} >= self->{bound}()) return fail(r, EINVAL, "Header position is outside the existing table");']
        if declaring == 'QFormLayout' and method == 'setItem':
            row, role = _argument(g, m, 0), _argument(g, m, 1)
            lines += ['if (native_replaced) return fail(r, EBUSY, "Form layout cell is already occupied");',
                      f'if (!a2 || {row} < 0 || int({role}) < 0 || int({role}) > int(QFormLayout::SpanningRole)) return fail(r, EINVAL, "Invalid form layout item or cell");']
        if cls == 'QLayoutItem':
            lines += [f'for (int n = 0; n < self->count(); ++n) if (self->itemAt(n) == a{i}) return fail(r, EBUSY, "Layout already contains this item");']
        if m['function']['name'] in ('setHorizontalHeaderItem', 'setVerticalHeaderItem', 'setHeaderItem', 'setItemPrototype'):
            lines += [f'if (auto *e = entry(r->arguments[{i}].word); e && !e->native_observed) return fail(r, ENOTSUP, "Native header/prototype adoption requires a destructor-observed item");']
        if old:
            lines += [f'if (!native_pointer_idle(r, native_replaced, {g.ids[cls]})) return true;',
                      f'native_forget_pointer(native_replaced, {g.ids[cls]});']
        return lines
    return []


def before_result(g, m):
    import ownership_collections
    collection = ownership_collections.before_result(g, m)
    if collection is not None:
        return collection
    import graphics_layouts
    graphics_layout = graphics_layouts.before_result(g, m)
    if graphics_layout is not None:
        return graphics_layout
    f = m['function']
    ret = m.get('native_return', m['return'])
    p = (m.get('retention') or {}).get('native') or {}
    if p.get('kind') == 'gl_context' and f['name'] in ('functions', 'extraFunctions'):
        g.retention_accessors['native_gl_context'] = '''
static SlotTable<uint32_t> native_gl_context_observed;
static void native_observe_gl_context(uint32_t id, QOpenGLContext *context) {
    auto slot = id & 65535u;
    if (native_gl_context_observed[slot] == id) return;
    QObject::connect(context, &QOpenGLContext::aboutToBeDestroyed, context,
        [id] { invalidate_native_children(id); });
    native_gl_context_observed[slot] = id;
}
'''
        return ['native_observe_gl_context(r->self, self);',
                f'if (returned) register_native_borrow(r, self->extraFunctions(), {g.ids["QOpenGLExtraFunctions"]}, r->self);',
                'if (r->error) return true;']
    if ret['kind'] == 'list' and len(ret.get('children', [])) == 1 and ret['children'][0]['kind'] == 'object':
        value = ret['children'][0]
        cls = family(g, value['name'])
        if not cls or g.classes[value['name']]['qobject']:
            return []
        prepare(g)
        if p.get('kind') == 'take_many':
            return ['for (auto *value : returned) if (value) {',
                    f'    uint32_t id = native_known_token(value, {g.ids[cls]});',
                    '    if (id) { native_model_detach(id); if (!set_native_owner(r, id, 0)) return true; }', '}']
        lines = ['for (auto *value : returned) if (value) {']
        if value.get('readonly'):
            lines += [f'    uint32_t known = native_known_token(value, {g.ids[value["name"]]});']
        lines += [f'    uint32_t id = native_observe_{cls}(r, const_cast<{value["name"]} *>(value), 0, false, {g.ids[value["name"]]});',
                  '    if (r->error) return true;']
        if value.get('readonly'):
            lines += ['    if (!known && id) entry(id)->read_only = true;']
        return lines + ['}']
    if f['constructor'] or ret['kind'] != 'object' or not ret.get('pointer'):
        return []
    if g.classes[ret['name']]['qobject']:
        return []
    cls = family(g, ret['name'])
    if not cls:
        return []
    prepare(g)
    if p.get('kind') == 'take':
        return [f'if (returned) {{ uint32_t id = native_known_token(returned, {g.ids[cls]});',
                '    if (id) { native_model_detach(id); if (!set_native_owner(r, id, 0)) return true; } }']
    if ret.get('owned'):
        return []
    if cls == 'QLayoutItem':
        if f['declaring_class'] not in ('QLayout', 'QBoxLayout', 'QGridLayout', 'QFormLayout', 'QStackedLayout'):
            return []
        hint = 'r->self'
    elif cls == 'QUndoCommand':
        hint = 'r->self' if f['declaring_class'] in ('QUndoCommand', 'QUndoStack') else '0'
    else:
        hint = '0'
    native = ret['name']
    lines = []
    if ret.get('readonly'):
        lines += [f'uint32_t native_previous_alias = native_known_token(returned, {g.ids[native]});']
    lines += [f'uint32_t native_observed_result = returned ? native_observe_{cls}(r, const_cast<{native} *>(returned), {hint}, false, {g.ids[native]}) : 0;',
              'if (r->error) return true;']
    if ret.get('readonly'):
        lines += ['if (!native_previous_alias && native_observed_result) entry(native_observed_result)->read_only = true;']
    return lines


def after(g, m):
    p = (m.get('retention') or {}).get('native')
    if not p:
        return []
    import ownership_collections
    collection = ownership_collections.after(g, m, p)
    if collection is not None:
        return collection
    import graphics_layouts
    graphics_layout = graphics_layouts.after(g, m, p)
    if graphics_layout is not None:
        return graphics_layout
    kind = p['kind']
    if kind == 'constructor':
        cls, i = p['family'], p['parent']
        name = m['class']
        return [f'auto *native_created = get<{name}>(r, r->result.word, {g.ids[name]});',
                'if (r->error) return true;',
                f'uint32_t owner = r->arguments[{i}].word;',
                'if (owner && !set_native_owner(r, r->result.word, owner)) return true;',
                f'native_observe_{cls}(r, static_cast<{cls} *>(native_created), owner);', 'if (r->error) return true;']
    if kind == 'detach':
        return [f'native_model_detach(r->arguments[{p["input"]}].word);',
                f'native_observe_{p["family"]}(r, a{p["input"]}, 0, true);', 'if (r->error) return true;']
    if kind == 'adopt':
        i, cls = p['input'], p['family']
        if m['function']['name'] in ('setParentItem', 'setGroup'):
            return ['native_observe_QGraphicsItem(r, static_cast<QGraphicsItem *>(self), 0, true);', 'if (r->error) return true;']
        owner = m['function']['declaring_class']
        check = {'QStandardItemModel': f'a{i}->model() == self', 'QStandardItem': f'a{i}->parent() == self',
                 'QTreeWidget': f'a{i}->treeWidget() == self', 'QTreeWidgetItem': f'a{i}->parent() == self',
                 'QListWidget': f'a{i}->listWidget() == self', 'QTableWidget': f'a{i}->tableWidget() == self',
                 'QGraphicsScene': f'a{i}->scene() == self', 'QGraphicsItemGroup': f'a{i}->parentItem() == self'}.get(owner)
        old = _old_getter(g, m, p)
        if owner == 'QTableWidget' and m['function']['name'] == 'setItem':
            # Sorting can move the accepted item to another row immediately.
            check = f'a{i}->tableWidget() == self && self->indexFromItem(a{i}).isValid()'
        elif old:
            check = f'{old} == a{i}'
        lines = [f'if (a{i}) {{']
        if check:
            lines += [f'    if (!({check})) return fail(r, EINVAL, "Qt rejected native item adoption");']
        if cls == 'QLayoutItem':
            lines += ['    bool accepted = false;', f'    for (int n = 0; n < self->count(); ++n) if (self->itemAt(n) == a{i}) accepted = true;',
                      '    if (!accepted) return fail(r, EINVAL, "Qt rejected layout item adoption");']
        lines += [f'    native_observe_{cls}(r, a{i}, r->self, true);',
                  '    if (r->error) return true;', '}']
        return lines
    if kind == 'adopt_many':
        i, cls = p['input'], p['family']
        declaring = m['function']['declaring_class']
        check = {'QStandardItemModel': 'value->model() == self', 'QStandardItem': 'value->parent() == self',
                 'QTreeWidget': 'value->treeWidget() == self', 'QTreeWidgetItem': 'value->parent() == self'}[declaring]
        return ['bool native_all_adopted = true;', f'for (auto *value : *a{i}) {{',
                '    if (!value) continue;', f'    if (!({check})) {{ native_all_adopted = false; continue; }}',
                f'    native_observe_{cls}(r, value, r->self, true);',
                '    if (r->error) return true;', '}',
                'if (!native_all_adopted) return fail(r, EINVAL, "Qt rejected a bulk native item adoption");']
    if kind == 'create_group':
        return ['for (auto *value : *a0) {',
                '    native_observe_QGraphicsItem(r, value, 0, true);',
                '    if (r->error) return true;', '}']
    return []
