"""Ownership operations whose Qt contract is not represented by QObject.parent.

The collection getter is the acceptance test. Native ownership is changed only
after that test, and retention reservations happen before calling into Qt.
"""


def policy(g, name, f, args):
    from retention import _group
    declaring, method = f['declaring_class'], f['name']
    spec = None
    if declaring == 'QBarSeries' and method in ('append', 'insert', 'replace', 'take', 'remove', 'removeMultiple', 'clear'):
        spec = ('QBarSet', 'barSets', 'add' if method in ('append', 'insert', 'replace') else 'take' if method == 'take' else 'delete')
    if declaring == 'Qt3DCore::QAspectEngine' and method in ('registerAspect', 'unregisterAspect'):
        if args and args[0].get('name') == 'Qt3DCore::QAbstractAspect':
            spec = ('Qt3DCore::QAbstractAspect', 'aspects', 'add' if method == 'registerAspect' else 'delete')
    if declaring in ('Q3DBarsWidgetItem', 'Q3DScatterWidgetItem', 'Q3DSurfaceWidgetItem'):
        if method in ('addAxis', 'releaseAxis', 'setRowAxis', 'setColumnAxis', 'setValueAxis', 'setAxisX', 'setAxisY', 'setAxisZ'):
            spec = (args[0]['name'], 'axes', 'take' if method == 'releaseAxis' else 'add')
    if declaring == 'Q3DGraphsWidgetItem':
        if method in ('addTheme', 'releaseTheme', 'setActiveTheme'):
            spec = ('QGraphsTheme', 'themes', 'take' if method == 'releaseTheme' else 'add')
        if method in ('addCustomItem', 'releaseCustomItem', 'removeCustomItem', 'removeCustomItems', 'removeCustomItemAt'):
            spec = ('QCustom3DItem', 'customItems', 'take' if method == 'releaseCustomItem' else 'add' if method == 'addCustomItem' else 'delete')
    if spec:
        target, getter, operation = spec
        indices = [i for i, a in enumerate(args) if a.get('name') == target or
                   (a['kind'] == 'list' and a.get('children') and a['children'][0].get('name') == target)]
        index = indices[-1] if indices else None
        group = _group(g, declaring, target, f'owner->{getter}().contains(target)', declaring + '.' + getter,
                       index, bulk=index is not None and args[index]['kind'] == 'list')
        return dict(kind='owning_collection', group=group, getter=getter, operation=operation,
                    returns_bool=f['return']['name'] == 'bool', index_check=declaring == 'QBarSeries' and method == 'insert',
                    detach_parent=declaring == 'QBarSeries', nullable=method.startswith('set'),
                    replacement=declaring == 'QBarSeries' and method == 'replace')
    if declaring == 'QUndoStack' and method in ('push', 'undo', 'redo', 'setIndex', 'clear', 'beginMacro', 'endMacro'):
        return dict(kind='undo_stack', push=method == 'push')
    if declaring == 'QItemEditorFactory' and method == 'registerEditor':
        g.retention_accessors['native_editor_factory_records'] = '''
struct NativeEditorRegistration { uint32_t factory, creator; int user_type; };
static SlotTable<NativeEditorRegistration> native_editor_registrations;
static int native_editor_registration(BqtRequest *r, uint32_t factory, int user_type) {
    int free_slot = -1;
    for (uint32_t n = 0; n < capacity; ++n) {
        auto &record = native_editor_registrations[n];
        if (!entry(record.factory) || !entry(record.creator)) record = {};
        if (record.factory == factory && record.user_type == user_type) return int(n);
        if (!record.factory && free_slot < 0) free_slot = int(n);
    }
    if (free_slot < 0) fail(r, ENOSPC, "Qt editor registration table is full");
    return free_slot;
}
'''
        return dict(kind='editor_registration')
    return None


def before(g, m, p):
    kind = p['kind']
    if kind == 'owning_collection':
        group, operation = p['group'], p['operation']
        i = group['input']
        lines = ['if (!native_children_idle(r, r->self)) return true;']
        if p['index_check']:
            index = g.argument(m['args'][0], 0)[1]
            lines += [f'if ({index} < 0 || {index} > self->count()) return fail(r, EINVAL, "Bar-set insertion index is outside the series");']
        if i is None:
            return lines
        values = f'*a{i}' if group['bulk'] else f'std::initializer_list<decltype(a{i})>{{a{i}}}'
        lines += ['RetentionBatch retention_batch;', 'std::vector<uint32_t> native_collection_ids;',
                  f'for (auto *value : {values}) {{',
                  '    uint32_t id = retention_token(r, value);',
                  '    if (r->error) return true;',
                  ('    if (!id) continue;' if p['nullable'] else '    if (!id) return fail(r, EINVAL, "An owning collection member must not be null");'),
                  '    auto *e = entry(id);',
                  '    if (!can_transfer_handle(r, id)) return true;',
                  '    if (e->native_owner && e->native_owner != r->self) return fail(r, EBUSY, "Detach the collection member from its current owner first");',
                  '    for (auto previous : native_collection_ids) if (previous == id) return fail(r, EINVAL, "An owning collection cannot contain duplicates");',
                  '    native_collection_ids.push_back(id);']
        if operation == 'add':
            lines += ['    if (!can_adopt(r, self, value)) return true;',
                      f'    if (!retention_batch.add(r, r->self, {group["slot"]}, id, {group["accessor"]})) return true;']
            if p['replacement']:
                lines += [f'    if (self->{p["getter"]}().contains(value)) return fail(r, EBUSY, "Replacement must not reuse a member that Qt will delete");']
        elif operation == 'take':
            lines += [f'    if (!self->{p["getter"]}().contains(value)) return true;',
                      f'    if (!retention_batch.add(r, r->self, {group["slot"]}, id, {group["accessor"]}, true)) return true;']
        lines += ['}']
        if p['replacement'] and group['bulk']:
            # Qt 6.12's range loop removes from the same implicitly-shared list.
            # Compose its public remove/append operations without stale iterators.
            lines += ['while (!self->barSets().isEmpty()) self->remove(self->barSets().first());',
                      f'r->result.word = self->append(*a{i}) ? 1 : 0;', 'reconcile_parents();']
            lines += after(g, m, p) + ['return true;']
        return lines
    if kind == 'undo_stack':
        lines = ['if (entry(r->self)->active_calls > 1) return fail(r, EBUSY, "Undo stack mutation from an active command callback is unsupported by Qt");',
                 'if (!native_children_idle(r, r->self)) return true;']
        if p['push']:
            lines += ['if (!a0) return fail(r, EINVAL, "Undo command must not be null");',
                      'auto *native_command = entry(r->arguments[0].word);',
                      'if (native_command->active_calls > 1) return fail(r, EBUSY, "Undo command is active in a suspended callback");',
                      'if (!native_command->native_observed) return fail(r, ENOTSUP, "Undo commands require observed destruction before stack transfer");',
                      'if (native_command->native_owner || !native_command->owned) return fail(r, EBUSY, "Undo command already has an owner");',
                      'if (!can_transfer_handle(r, r->arguments[0].word)) return true;',
                      'if (reaches_token(r->arguments[0].word, r->self)) return fail(r, ELOOP, "Undo command ownership would create a retention cycle");']
        return lines
    if kind == 'editor_registration':
        user_type = g.argument(m['args'][0], 0)[1]
        return ['if (!native_children_idle(r, r->self)) return true;',
                'if (!a1) return fail(r, EINVAL, "Item editor creator must not be null");',
                'auto *native_creator = entry(r->arguments[1].word);',
                'if (!native_creator->native_observed) return fail(r, ENOTSUP, "Item editor creators require observed destruction before factory transfer");',
                'if (native_creator->native_owner && native_creator->native_owner != r->self) return fail(r, EBUSY, "Editor creator already belongs to another factory");',
                'if (!can_transfer_handle(r, r->arguments[1].word)) return true;',
                'if (reaches_token(r->arguments[1].word, r->self)) return fail(r, ELOOP, "Editor creator ownership would create a retention cycle");',
                f'int native_registration = native_editor_registration(r, r->self, {user_type});',
                'if (r->error) return true;',
                'if (native_editor_registrations[native_registration].creator == r->arguments[1].word) return true;']
    return None


def before_result(g, m):
    declaring, method = m['function']['declaring_class'], m['function']['name']
    if ((declaring == 'QBarSeries' and method == 'barSets') or
            (declaring == 'Qt3DCore::QAspectEngine' and method == 'aspects') or
            (declaring in ('Q3DBarsWidgetItem', 'Q3DScatterWidgetItem', 'Q3DSurfaceWidgetItem') and
             method in ('axes', 'axisX', 'axisY', 'axisZ', 'valueAxis', 'rowAxis', 'columnAxis')) or
            (declaring == 'Q3DGraphsWidgetItem' and method in ('themes', 'activeTheme', 'customItems'))):
        ret = m.get('native_return', m['return'])
        item = ret['children'][0] if ret['kind'] == 'list' else ret
        values = 'returned' if ret['kind'] == 'list' else 'std::initializer_list<decltype(returned)>{returned}'
        return [f'for (auto *value : {values}) {{',
                f'    uint32_t id = borrow(r, value, {g.ids[item["name"]]});',
                '    if (r->error || !set_native_owner(r, id, r->self)) return true;', '}']
    return None


def after(g, m, p):
    kind = p['kind']
    if kind == 'owning_collection':
        group, operation = p['group'], p['operation']
        if group['input'] is None or operation == 'delete':
            return []
        # after_call is emitted after result conversion. Use the native return
        # stored in r->result, since the C++ returned variable is scoped earlier.
        lines = ['if (!r->result.word) return true;'] if p['returns_bool'] else []
        lines += ['if (!entry(r->self)) return fail(r, ESTALE, "Owning collection was destroyed during mutation");']
        if operation == 'add':
            lines += ['if (!retention_batch.finish(r)) return true;',
                      'for (auto id : native_collection_ids) if (!set_native_owner(r, id, r->self)) return true;']
        else:
            if p['detach_parent']:
                lines += ['for (auto id : native_collection_ids) {',
                          '    auto *e = entry(id);',
                          '    if (!e) return fail(r, ESTALE, "Taken member was destroyed during removal");',
                          # Qt 6.12 append reparents; take does not undo it.
                          '    if (e->object->parent() == self) e->object->setParent(nullptr);', '}']
            lines += ['reconcile_parents();', 'if (!retention_batch.finish(r)) return true;',
                      'for (auto id : native_collection_ids) if (!set_native_owner(r, id, 0)) return true;']
        return lines
    if kind == 'undo_stack':
        if p['push']:
            # push may merge, obsolete, or discard the incoming command.
            return ['if (entry(r->arguments[0].word) && !set_native_owner(r, r->arguments[0].word, r->self)) return true;']
        return []
    if kind == 'editor_registration':
        user_type = g.argument(m['args'][0], 0)[1]
        return ['if (!set_native_owner(r, r->arguments[1].word, r->self)) return true;',
                f'native_editor_registrations[native_registration] = {{r->self, r->arguments[1].word, {user_type}}};']
    return None
