"""Owner-checked typed spans for public Qt contiguous container storage.

These are live aliases. Reads copy one element; writes change the native
container. Both operations re-check the public pointer and element count.
"""
import re


def carrier(element):
    return 'ArrayView_' + re.sub(r'[^A-Za-z0-9_]', '_', element)


def restores_method(f):
    return (bool(re.fullmatch(r'QMatrix([234])x([234])', f['declaring_class']))
            and f['name'] in ('data','constData') and not f['arguments']
            and f['return']['pointers'] == 1 and f['return']['name'] == 'float')


def policy(classes, f):
    owner, method, t = f['declaring_class'], f['name'], f['return']
    if f['arguments'] or f['static'] or t['pointers'] != 1 or t['reference']:
        return None
    matrix = re.fullmatch(r'QMatrix([234])x([234])', owner)
    if matrix and method in ('data', 'constData') and t['name'] == 'float':
        return dict(owner=owner, element='float', count=str(int(matrix[1]) * int(matrix[2])), fixed_count=True,
                    read='constData()', write='data()', readonly=bool(t['const'] or f['const']), end=False)
    element = classes.get(t['name'])
    if not element or not element.get('copyable') or element.get('qobject') or not element.get('public_destructor'):
        return None
    members = classes.get(owner, {}).get('functions', [])
    has = lambda name: any(m['name'] == name and m['public'] and not m['static'] and not m['arguments'] for m in members)
    if method in ('data', 'constData') and has('constData') and has('size'):
        return dict(owner=owner, element=t['name'], count='size()', read='constData()', write='data()',
                    readonly=t['const'], end=False)
    if owner == 'QModelRoleDataSpan' and method in ('data', 'begin', 'end'):
        end = method == 'end'
        return dict(owner=owner, element=t['name'], count='0' if end else 'size()',
                    read='end()' if end else 'data()', write='end()' if end else 'data()', readonly=False, end=end)
    if owner == 'QSGGeometry' and method == 'attributes':
        return dict(owner=owner, element=t['name'], count='attributeCount()', read='attributes()',
                    write='attributes()', readonly=True, end=False)
    bounded_ranges = {'QRegion': 'rectCount()', 'Qt3DAnimation::QAnimationClipData': 'channelCount()',
                      'Qt3DAnimation::QChannel': 'channelComponentCount()'}
    if owner in bounded_ranges and method in ('begin', 'cbegin', 'end', 'cend') and t['const']:
        end = method in ('end', 'cend')
        return dict(owner=owner, element=t['name'], count='0' if end else bounded_ranges[owner],
                    read='end()' if end else 'begin()', write='end()' if end else 'begin()', readonly=True, end=end)
    return None


def install(classes, selected):
    elements = set()
    # Native object discovery follows carrier installation. Include upstream
    # generated owners now so QSGGeometry and other noncopyable owners can
    # expose their typed spans once native_objects selects their handles.
    owners = set(selected) | {name for name, cls in classes.items() if cls.get('generate')}
    for name in sorted(owners):
        for f in classes[name].get('functions', []):
            p = policy(classes, f)
            if p:
                elements.add(p['element'])
    for element in sorted(elements):
        import borrowed_values
        if element in classes:
            borrowed_values.VIEW_TYPES.add(element)
        name = carrier(element)
        classes[name] = dict(name=name, object=False, value=True, qobject=False,
            public_destructor=True, abstract=False, copyable=True, namespace=False,
            generate=False, template=False, bases=[], functions=[], enums=[], adapter=True,
            span_element=element)
        if name not in selected:
            selected.append(name)


def aliases(g, inside=False):
    names = [name for name in g.selected if g.classes[name].get('span_element')]
    body = 'struct MemoryView;\n' + ''.join(f'using {name} = MemoryView;\n' for name in names)
    return (body if inside else 'namespace bendqt {\n' + body + '}\n') if names else ''


def adapt(g, f):
    p = policy(g.classes, f)
    if not p:
        return None
    name = carrier(p['element'])
    if name not in g.ids:
        return None
    return dict(kind='value', name=name, cpp=name, bend=name, raw='U32', typed_view=p)


def prepare(g):
    for name in g.selected:
        element = g.classes[name].get('span_element')
        if not element:
            continue
        native = dict(name=element, cpp=element, const=False, pointers=0, reference=0,
                      enum=False, flags=False, instantiations=[], container=False)
        value = g.type(native, result=True)
        if value['kind'] == 'object':
            value = dict(value, kind='value', pointer=False)
        g.classes[name]['span_value'] = g.conversions.register(value)


def store(g, t, value):
    p = t.get('typed_view')
    if not p:
        return None
    count = p['count'] if p['end'] or p.get('fixed_count') else 'self->' + p['count']
    observed_count = p['count'] if p['end'] or p.get('fixed_count') else 'source->' + p['count']
    readonly = str(p['readonly']).lower()
    return [f'auto span_count = {count};',
        'if (span_count < 0) return fail(r, ERANGE, "Qt span reports a negative extent");',
        f'MemoryView view{{r->self, const_cast<void *>(static_cast<const void *>({value})), size_t(span_count), 0, {readonly}, nullptr}};',
        'view.observe = [](BqtRequest *check, const MemoryView &view, bool writing) {',
        f'    auto *source = get<{p["owner"]}>(check, view.owner, {g.ids[p["owner"]]}, false, writing);',
        '    if (check->error) return false;',
        f'    auto count = {observed_count};',
        f'    const void *pointer = writing ? static_cast<const void *>(source->{p["write"]}) : static_cast<const void *>(static_cast<const {p["owner"]} *>(source)->{p["read"]});',
        '    if (count < 0 || size_t(count) != view.size || pointer != view.address) {',
        '        fail(check, ESTALE, "Qt typed storage changed since this span was acquired"); return false;', '    }',
        '    return true;', '};',
        # Empty spans still have identities; a null begin pointer is a valid
        # zero-length range, unlike a nullable missing native object.
        f'r->result.word = own(r, new {t["name"]}(view), {g.ids[t["name"]]});',
        'if (!retain_typed_view_owner(r, r->result.word, r->self)) return true;',
        'r->result.owned_handle = r->result.word;']


def cpp(g):
    return '''
static bool retain_typed_view_owner(BqtRequest *r, uint32_t id, uint32_t owner) {
    if (!id) return false;
    BqtRequest check{}; check.self = id;
    constexpr uint32_t slot = 0xffffffebu;
    int index = prepare_retention(&check, slot, 0, owner);
    if (check.error) {
        auto *value = entry(id); auto *storage = value->value; auto destroy = value->destroy;
        invalidate(id); destroy(storage); fail(r, check.error, check.message); return false;
    }
    commit_retention(index, id, slot, 0, owner, nullptr);
    return true;
}
'''


def emit(g):
    wide = dict(kind='u64', bend='UInt64', raw='U32 & U32')
    unit = dict(kind='void', bend='Unit', raw='Unit')
    boolean = dict(kind='bool', bend='Bool', raw='U32')
    for name in g.selected:
        c = g.classes[name]
        if 'span_element' not in c:
            continue
        value = c['span_value']
        native = c['span_element']
        handle = dict(kind='value', name=name, bend=name, raw='U32')
        def effect(method, args, result, body):
            operation = g.next_id
            g.next_id += 1
            lines = ['NativeCallScope scope;', f'auto *view = get<{name}>(r, r->self, {g.ids[name]}, false, false);',
                     'if (r->error) return true;'] + body + ['return true;']
            g.cases.append(f'case {operation}: {{\n' + '\n'.join('    ' + line for line in lines) + '\n}')
            g.emit_effect(name + '.' + method, [('self', handle)] + args, result, operation, has_self=True)
        effect('size', [], wide, ['if (!view->observe(r, *view, false)) return true;', 'r->result = wide_value(view->size);'])
        effect('isReadOnly', [], boolean, ['r->result.word = view->readonly;'])
        checked_index = ['auto index = wide_bits(r->arguments[0]);',
                         'if (index >= view->size) return fail(r, ERANGE, "Typed span index exceeds its extent");']
        effect('at', [('index', wide)], value,
               ['if (!view->observe(r, *view, false)) return true;'] + checked_index +
               g.store_result(value, f'static_cast<const {native} *>(view->address)[size_t(index)]'))
        if native in g.ids:
            effect('ref', [('index', wide)], value,
               ['if (!view->observe(r, *view, false)) return true;'] + checked_index + [
                   'if (index > UINT32_MAX) return fail(r, EOVERFLOW, "Typed span index exceeds view representation");',
                   f'auto observe_element = [](BqtRequest *check, const BorrowedValueOrigin &element) {{',
                   f'    auto *span = get<{name}>(check, element.owner, {g.ids[name]}, false, false);',
                   '    if (check->error || !span->observe(check, *span, false)) return false;',
                   f'    if (element.auxiliary >= span->size || static_cast<{native} *>(span->address) + element.auxiliary != element.address) {{',
                   '        fail(check, ESTALE, "Typed element no longer belongs to its span"); return false;', '    }',
                   '    return true;', '};',
                   f'r->result.word = create_value_view(r, static_cast<{native} *>(view->address) + size_t(index), {g.ids[native]}, r->self, uint32_t(index), observe_element);',
                   'if (auto *element = entry(r->result.word)) element->read_only = view->readonly;',
                   'r->result.owned_handle = r->result.word;'])
        if not g.classes.get(native, {}).get('native_copy_assignable', True):
            continue
        declarations, expression = g.argument(value, 1)
        effect('set', [('index', wide), ('value', value)], unit,
               ['if (view->readonly) return fail(r, EPERM, "Typed span is read only");',
                'if (!view->observe(r, *view, true)) return true;'] + checked_index + declarations +
               ['if (r->error) return true;', f'static_cast<{native} *>(view->address)[size_t(index)] = {expression};'])
