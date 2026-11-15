"""Stable mutable storage and checked origins for QModelRoleDataSpan."""


def install(classes, selected):
    if 'QModelRoleDataSpan' not in selected:
        return
    classes['RoleDataBuffer'] = dict(name='RoleDataBuffer', object=False, value=True,
        qobject=False, public_destructor=True, abstract=False, copyable=False,
        namespace=False, generate=False, template=False, bases=[], functions=[],
        enums=[], adapter=True)
    selected.append('RoleDataBuffer')


def parameters(g, f):
    if f['declaring_class'] != 'QModelRoleDataSpan' or not f['constructor']:
        return None
    args = []
    for arg in f['arguments']:
        t = arg['type']
        if t['name'] == 'QModelRoleData' and t['pointers']:
            args.append(dict(kind='value', name='RoleDataBuffer', cpp='RoleDataBuffer', bend='RoleDataBuffer', raw='U32'))
        else:
            args.append(g.type(dict(t, const=False, pointers=0, reference=0, cpp=t['name'])))
    return args, [dict(type=t, source=i, input=i, output=False, mutable=False) for i, t in enumerate(args)], []


def restores_method(f):
    return f['declaring_class'] == 'QModelRoleDataSpan' and f['name'] == 'dataForRole'


def restores_addition(f):
    # Upstream spells this specialization of the public C++ forwarding template
    # as a Python addition. QVariant is also the Bend native value carrier.
    return (f['declaring_class'] == 'QModelRoleData' and f['name'] == 'setData'
            and len(f['arguments']) == 1 and f['arguments'][0]['type']['name'] == 'QVariant')


def adapt(g, f):
    if not restores_method(f):
        return None
    return dict(g.type(dict(f['return'], const=False, pointers=0, reference=0, cpp='QVariant'), result=True), role_variant=True)


def method_case(g, m):
    f = m['function']
    if f['declaring_class'] != 'QModelRoleDataSpan':
        return None
    tid = g.ids['QModelRoleDataSpan']
    if f['constructor']:
        lines = ['NativeCallScope call_scope;']
        args = m['args']
        if not args:
            expression = 'new QModelRoleDataSpan()'
        else:
            name = args[0]['name']
            writable = str(name != 'QModelRoleDataSpan').lower()
            lines += [f'auto *source = get<{name}>(r, r->arguments[0].word, {g.ids[name]}, false, {writable});',
                      'if (r->error) return true;', 'call_scope.value_origin = r->arguments[0].word;']
            if name == 'RoleDataBuffer':
                lines += ['auto count = int64_t(wide_bits(r->arguments[1]));',
                          'if (count < 0 || count > source->values.size()) return fail(r, ERANGE, "Role span exceeds its backing buffer");']
                expression = 'new QModelRoleDataSpan(source->values.data(), qsizetype(count))'
            else:
                expression = 'new QModelRoleDataSpan(*source)'
        return lines + [f'r->result.word = own(r, {expression}, {tid});', 'r->result.owned_handle = r->result.word;', 'return true;']
    if f['name'] == 'dataForRole':
        return ['NativeCallScope call_scope;', f'auto *self = get<QModelRoleDataSpan>(r, r->self, {tid});',
                'if (r->error) return true;', 'int role = int32_t(r->arguments[0].word);',
                'qsizetype index = 0;', 'while (index < self->size() && self->data()[index].role() != role) ++index;',
                'if (index == self->size()) return fail(r, ERANGE, "Role is absent from the native role span");',
                'if (uint64_t(index) > UINT32_MAX) return fail(r, EOVERFLOW, "Role span index exceeds the view representation");',
                f'r->result.word = create_value_view(r, &self->data()[index].data(), {g.ids["QVariant"]}, r->self, uint32_t(index), observe_role_variant);',
                'r->result.owned_handle = r->result.word;', 'return true;']
    return None


def before_call(g, m):
    f = m['function']
    if f['declaring_class'] == 'QModelRoleDataSpan' and f['name'] == 'operator=':
        return ['call_scope.value_origin = r->arguments[0].word;']
    return []


def after_native(g, m):
    f = m['function']
    if f['declaring_class'] == 'QModelRoleDataSpan' and f['name'] == 'operator=':
        return ['if (!finish_role_span_ownership(r, r->self)) return true;']
    return []


def prepare(g):
    if 'RoleDataBuffer' in g.ids:
        native = dict(name='QList', cpp='QList<int>', const=False, pointers=0, reference=0,
                      enum=False, flags=False, container=True, instantiations=[dict(name='int', cpp='int',
                      const=False, pointers=0, reference=0, enum=False, flags=False, container=False, instantiations=[])])
        g.role_list = g.conversions.container(native, False)


def emit(g):
    if 'RoleDataBuffer' not in g.ids:
        return
    handle = dict(kind='value', name='RoleDataBuffer', bend='RoleDataBuffer', raw='U32')
    span = dict(kind='value', name='QModelRoleDataSpan', bend='QModelRoleDataSpan', raw='U32')
    declarations, roles = g.argument(g.role_list, 0)
    body = ['NativeCallScope call_scope;'] + declarations + ['if (r->error) return true;',
            'auto value = std::make_unique<RoleDataBuffer>();', f'value->values.reserve(({roles}).size());',
            f'for (int role : ({roles})) value->values.append(QModelRoleData(role));',
            f'r->result.word = own(r, value.release(), {g.ids["RoleDataBuffer"]});',
            'r->result.owned_handle = r->result.word;']
    for name, args, result, lines, has_self in [
            ('new', [('roles', g.role_list)], handle, body, False),
            ('span', [('self', handle)], span, ['NativeCallScope call_scope;',
                f'auto *self = get<RoleDataBuffer>(r, r->self, {g.ids["RoleDataBuffer"]});',
                'if (r->error) return true;', 'call_scope.value_origin = r->self;',
                f'r->result.word = own(r, new QModelRoleDataSpan(self->values.data(), self->values.size()), {g.ids["QModelRoleDataSpan"]});',
                'r->result.owned_handle = r->result.word;'], True)]:
        operation = g.next_id
        g.next_id += 1
        g.cases.append(f'case {operation}: {{\n' + '\n'.join('    ' + line for line in lines + ['return true;']) + '\n}')
        g.emit_effect('RoleDataBuffer.' + name, args, result, operation, has_self=has_self)


def cpp(g):
    if 'RoleDataBuffer' not in g.ids:
        return 'static uint32_t finish_role_span_ownership(BqtRequest *, uint32_t id) { return id; }\n'
    return f'''
struct RoleSpanOrigin {{ uint32_t id = 0, owner = 0; }};
static SlotTable<RoleSpanOrigin> role_span_origins;
static bool validate_role_span(BqtRequest *r, uint32_t id) {{
    auto *value = entry(id);
    if (!value) {{ fail(r, ESTALE, "Role span was destroyed"); return false; }}
    auto callback = borrowed_value_origins[id & 65535u];
    if (callback.id == id && (callback.callback_root || callback.origin)) return validate_borrowed_value(r, id);
    auto *span = static_cast<QModelRoleDataSpan *>(value->value);
    auto origin = role_span_origins[id & 65535u];
    if (origin.id != id) {{ fail(r, ESTALE, "Role span has no checked storage origin"); return false; }}
    if (!origin.owner && span->size() == 0) return true;
    auto *owner = entry(origin.owner);
    if (!owner) {{ fail(r, ESTALE, "Role span storage was destroyed"); return false; }}
    const QModelRoleData *start = nullptr;
    qsizetype count = 0;
    if (owner->type == {g.ids['RoleDataBuffer']}) {{
        auto *buffer = get<RoleDataBuffer>(r, origin.owner, {g.ids['RoleDataBuffer']}, false, false);
        if (r->error) return false;
        start = buffer->values.constData(); count = buffer->values.size();
    }} else if (owner->type == {g.ids['QModelRoleData']}) {{
        start = get<QModelRoleData>(r, origin.owner, {g.ids['QModelRoleData']}, false, false); count = 1;
        if (r->error) return false;
    }}
    if (span->data() != start || span->size() < 0 || span->size() > count) {{
        fail(r, ESTALE, "Role span no longer matches its backing storage"); return false;
    }}
    return true;
}}
static uint32_t finish_role_span_ownership(BqtRequest *r, uint32_t id) {{
    auto *value = entry(id);
    if (!value || value->type != {g.ids['QModelRoleDataSpan']}) return id;
    uint32_t source = native_call_scope && native_call_scope->value_origin ? native_call_scope->value_origin : r->self;
    uint32_t owner = 0;
    if (auto *origin = entry(source)) {{
        if (origin->type == {g.ids['RoleDataBuffer']} || origin->type == {g.ids['QModelRoleData']}) owner = source;
        else if (origin->type == {g.ids['QModelRoleDataSpan']}) {{
            auto old = role_span_origins[source & 65535u];
            if (old.id == source) owner = old.owner;
        }}
    }}
    BqtRequest check{{}}; check.self = id;
    constexpr uint32_t slot = 0xffffffe9u;
    int index = prepare_retention(&check, slot, 0, owner);
    if (check.error) {{
        auto *storage = value->value; auto destroy = value->destroy;
        invalidate(id); destroy(storage); if (!r->error) fail(r, check.error, check.message); return 0;
    }}
    commit_retention(index, id, slot, 0, owner, nullptr);
    role_span_origins[id & 65535u] = {{id, owner}};
    value->validate = validate_role_span;
    return id;
}}
static bool observe_role_variant(BqtRequest *r, const BorrowedValueOrigin &view) {{
    auto *span = get<QModelRoleDataSpan>(r, view.owner, {g.ids['QModelRoleDataSpan']}, false, false);
    if (r->error) return false;
    if (view.auxiliary >= uint64_t(span->size()) || &span->data()[view.auxiliary].data() != view.address) {{
        fail(r, ESTALE, "Role data value no longer belongs to its span"); return false;
    }}
    return true;
}}
'''
