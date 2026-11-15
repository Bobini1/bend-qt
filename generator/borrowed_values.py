"""Snapshots and checked aliases for explicitly documented value-pointer APIs."""

EPHEMERAL_TYPES = {'QSGMaterialShader::RenderState', 'QQuickItem::UpdatePaintNodeData',
                   'QMetaMethod', 'QMetaProperty', 'QMetaEnum', 'QMetaClassInfo', 'QModelRoleDataSpan'}
VIEW_TYPES = {'QCursor', 'QEventPoint', 'QGraphsThemeDirtyBitField', 'QVariant', 'QMetaObject'}


def install(classes, selected):
    classes['QStringBuffer'] = dict(name='QStringBuffer', object=False, value=True,
        qobject=False, public_destructor=True, abstract=False, copyable=True,
        namespace=False, generate=False, template=False, bases=[], functions=[],
        enums=[], adapter=True)
    if 'QStringBuffer' not in selected:
        selected.append('QStringBuffer')


def parameters(g, f):
    if f['declaring_class'] not in ('QTextStream', 'QXmlStreamWriter') or not (f['constructor'] or f['name'] == 'setString'):
        return None
    if not f['arguments'] or f['arguments'][0]['type']['name'] != 'QString' or f['arguments'][0]['type']['pointers'] != 1:
        return None
    args, plan = [], []
    for index, argument in enumerate(f['arguments']):
        t = (dict(kind='value', name='QStringBuffer', cpp='QStringBuffer *', bend='QStringBuffer',
                  raw='U32', pointer=True, string_buffer=True, required_pointer=f['declaring_class'] == 'QXmlStreamWriter') if index == 0 else g.type(argument['type']))
        args.append(t)
        plan.append(dict(type=t, source=index, input=index, output=False, mutable=False))
    return args, plan, []


def restores_method(f):
    return (f['declaring_class'] in ('QTextStream', 'QXmlStreamWriter') and (f['constructor'] or f['name'] == 'setString')
            and bool(f['arguments']) and f['arguments'][0]['type']['name'] == 'QString'
            and f['arguments'][0]['type']['pointers'] == 1)


def argument(g, t, index):
    if not t.get('string_buffer'):
        return None
    nullable = str(not t.get('required_pointer', False)).lower()
    return [f'auto *a{index} = get<QStringBuffer>(r, r->arguments[{index}].word, {g.ids["QStringBuffer"]}, {nullable});'], f'(a{index} ? &a{index}->value : nullptr)'


def emit(g):
    unit = dict(kind='void', bend='Unit', raw='Unit')
    string = dict(kind='string', bend='String', raw='String')
    handle = dict(kind='value', name='QStringBuffer', bend='QStringBuffer', raw='U32')
    tid = g.ids['QStringBuffer']
    operations = [
        ('new', [('text', string)], handle,
         f'r->result.word = own(r, new QStringBuffer{{QString::fromUtf8(r->arguments[0].text, qsizetype(r->arguments[0].size))}}, {tid});\n'
         'r->result.owned_handle = r->result.word;'),
        ('value', [('self', handle)], string, 'r->result = string_value(self->value);'),
        ('replace', [('self', handle), ('text', string)], unit,
         'self->value = QString::fromUtf8(r->arguments[0].text, qsizetype(r->arguments[0].size));'),
    ]
    for name, args, result, body in operations:
        operation = g.next_id
        g.next_id += 1
        has_self = name != 'new'
        lines = ['NativeCallScope scope;']
        if has_self:
            lines += [f'auto *self = get<QStringBuffer>(r, r->self, {tid});', 'if (r->error) return true;']
        lines += [body, 'return true;']
        g.cases.append(f'case {operation}: {{\n' + '\n'.join(lines) + '\n}')
        g.emit_effect('QStringBuffer.' + name, args, result, operation, has_self=has_self)


def adapt(g, f):
    t = f['return']
    if t['pointers'] != 1:
        return None
    member = f['declaring_class'], f['name']
    snapshot = member in {
        ('QBrush', 'gradient'), ('QTextStream', 'string'),
        ('QSGRenderNode', 'matrix'), ('QSGRenderNode', 'projectionMatrix'),
        ('QSGBasicGeometryNode', 'matrix'),
        ('QSGRenderNode::RenderState', 'projectionMatrix'), ('QSGRenderNode::RenderState', 'clipRegion'),
    }
    if snapshot:
        value = dict(t, cpp=t['name'], pointers=0, reference=0, const=False)
        converted = g.conversions.container(dict(name='std::optional', cpp='std::optional<' + t['name'] + '>',
            pointers=0, reference=0, const=False, container=True, enum=False, flags=False, instantiations=[value]), True)
        return dict(converted, result_conversion='value_pointer_snapshot', snapshot_cpp=t['name'])
    if member in (('QGuiApplication', 'overrideCursor'), ('QPointerEvent', 'pointById')):
        converted = g.type(dict(t, cpp=t['name'], pointers=0, reference=0, const=False), result=True)
        return dict(converted, value_view='cursor' if member[1] == 'overrideCursor' else 'event_point')
    if member == ('QGraphsTheme', 'dirtyBits'):
        converted = g.type(dict(t, cpp=t['name'], pointers=0, reference=0, const=False), result=True)
        return dict(converted, value_view='graph_dirty_bits')
    return None


def expression(t, value):
    if t.get('result_conversion') == 'value_pointer_snapshot':
        return f'(({value}) ? std::optional<{t["snapshot_cpp"]}>(*({value})) : std::nullopt)'
    return None


def before_call(g, m):
    f, args = m['function'], m['args']
    lines = []
    if f['declaring_class'] in EPHEMERAL_TYPES and args and (f['constructor'] or f['name'] == 'operator='):
        lines += ['call_scope.value_origin = r->arguments[0].word;']
    if f['declaring_class'] == 'QGuiApplication' and f['name'] in ('setOverrideCursor', 'changeOverrideCursor', 'restoreOverrideCursor'):
        if args:
            # The source itself may alias the current stack entry. Qt pops that
            # entry during changeOverrideCursor, so preserve the input first.
            lines += ['QCursor native_cursor_input = *a0;', 'a0 = &native_cursor_input;']
        lines += ['if (!invalidate_cursor_value_views(r)) return true;']
    return lines


def after_call(g, m):
    if m['function']['declaring_class'] in EPHEMERAL_TYPES and m['function']['name'] == 'operator=':
        return ['if (!finish_borrowed_value_ownership(r, r->self)) return true;']
    return []


def store(g, t, value):
    view = t.get('value_view')
    if not view:
        return None
    if view == 'cursor':
        return [f'r->result.word = create_value_view(r, {value}, {g.ids["QCursor"]}, 0, 0, observe_cursor_value, true);',
                'r->result.owned_handle = r->result.word;']
    if view == 'graph_dirty_bits':
        return [f'r->result.word = create_value_view(r, {value}, {g.ids["QGraphsThemeDirtyBitField"]}, r->self, 0, observe_graph_dirty_bits);',
                'r->result.owned_handle = r->result.word;']
    return [f'r->result.word = create_value_view(r, {value}, {g.ids["QEventPoint"]}, r->self, r->arguments[0].word, observe_event_point_value);',
            'r->result.owned_handle = r->result.word;']


def cpp(g):
    cases = ' '.join(f'case {g.ids[name]}:' for name in sorted(EPHEMERAL_TYPES) if name in g.ids)
    render_state = g.ids.get('QSGMaterialShader::RenderState', 0)
    point_event = g.ids.get('QPointerEvent', 0)
    graphs = f'''static bool observe_graph_dirty_bits(BqtRequest *r, const BorrowedValueOrigin &view) {{
    auto *theme = get<QGraphsTheme>(r, view.owner, {g.ids['QGraphsTheme']}, false, false);
    if (r->error) return false;
    if (theme->dirtyBits() != view.address) {{ fail(r, ESTALE, "Graph theme storage changed"); return false; }}
    return true;
}}
''' if 'QGraphsTheme' in g.ids and 'QGraphsThemeDirtyBitField' in g.ids else ''
    return f'''
struct BorrowedValueOrigin {{
    uint32_t id, owner, origin, auxiliary;
    void *address;
    bool (*observe)(BqtRequest *, const BorrowedValueOrigin &);
    bool callback_root, cursor;
}};
static SlotTable<BorrowedValueOrigin> borrowed_value_origins;
static void destroy_value_view(void *) {{}}
static bool is_value_view_handle(uint32_t id) {{
    auto *e = entry(id);
    return e && e->owned && e->destroy == destroy_value_view;
}}
static bool ephemeral_value_type(uint16_t type) {{
    switch (type) {{ {cases} return true; default: return false; }}
}}
static bool validate_borrowed_value(BqtRequest *r, uint32_t id) {{
    auto record = borrowed_value_origins[id & 65535u];
    if (record.id != id) {{ fail(r, ESTALE, "Qt value origin is unavailable"); return false; }}
    if (record.callback_root) return true;
    if (record.origin) {{
        auto original = borrowed_value_origins[record.origin & 65535u];
        if (!entry(record.origin) || original.id != record.origin || !original.callback_root) {{
            fail(r, ESTALE, "Qt value belongs to a completed native callback"); return false;
        }}
    }} else if (entry(id)->type == {render_state}) {{
        fail(r, EINVAL, "RenderState requires a live native callback origin"); return false;
    }}
    if (record.observe && !record.observe(r, record)) return false;
    return !r->error;
}}
static void mark_callback_ephemeral_value(uint32_t id) {{
    auto *e = entry(id);
    if (!e || !ephemeral_value_type(e->type)) return;
    borrowed_value_origins[id & 65535u] = {{id, 0, 0, 0, nullptr, nullptr, true, false}};
    e->validate = validate_borrowed_value;
}}
static void finish_callback_ephemeral_value(uint32_t id) {{
    auto *e = entry(id);
    auto record = borrowed_value_origins[id & 65535u];
    if (!e || record.id != id || !record.callback_root) return;
    auto *storage = e->value;
    auto destroy = e->destroy;
    invalidate(id);
    if (destroy) destroy(storage);
}}
static uint32_t finish_borrowed_value_ownership(BqtRequest *r, uint32_t id) {{
    auto *e = entry(id);
    if (!e || !ephemeral_value_type(e->type)) return id;
    // These are owning C++ value copies. Their trivial value destruction is
    // safe after a frame; only dereferencing their internal pointers expires.
    e->render_only = false;
    uint32_t source = native_call_scope && native_call_scope->value_origin ? native_call_scope->value_origin : r->self;
    auto old = borrowed_value_origins[source & 65535u];
    uint32_t origin = entry(source) && old.id == source ? (old.callback_root ? source : old.origin) : 0;
    if (id == source && old.id == source && old.callback_root) return id;
    borrowed_value_origins[id & 65535u] = {{id, 0, origin, 0, nullptr, nullptr, false, false}};
    if (origin || e->type == {render_state}) e->validate = validate_borrowed_value;
    return id;
}}
template<class T> static uint32_t create_value_view(BqtRequest *r, T *value, uint16_t type,
        uint32_t owner, uint32_t auxiliary, bool (*observe)(BqtRequest *, const BorrowedValueOrigin &), bool cursor = false) {{
    if (!value) return 0;
    if (owner && !entry(owner)) {{ fail(r, ESTALE, "Qt value view has no live owner"); return 0; }}
    auto id = insert(r, value, nullptr, type, destroy_value_view, true, NativeTraits<T>::cast);
    if (!id) return 0;
    borrowed_value_origins[id & 65535u] = {{id, owner, 0, auxiliary, value, observe, false, cursor}};
    entry(id)->validate = validate_borrowed_value;
    if (owner) {{
        BqtRequest claim{{}}; claim.self = id;
        constexpr uint32_t slot = 0xffffffeb;
        int index = prepare_retention(&claim, slot, 0, owner);
        if (claim.error) {{ invalidate(id); fail(r, claim.error, claim.message); return 0; }}
        commit_retention(index, id, slot, 0, owner, nullptr);
    }}
    return id;
}}
static bool observe_cursor_value(BqtRequest *r, const BorrowedValueOrigin &view) {{
    if (QGuiApplication::overrideCursor() != view.address) {{ fail(r, ESTALE, "Override cursor stack changed"); return false; }}
    return true;
}}
static bool observe_event_point_value(BqtRequest *r, const BorrowedValueOrigin &view) {{
    auto *event = get<QPointerEvent>(r, view.owner, {point_event}, false, false);
    if (r->error) return false;
    if (event->pointById(int32_t(view.auxiliary)) != view.address) {{ fail(r, ESTALE, "Pointer event storage changed"); return false; }}
    return true;
}}
static bool invalidate_cursor_value_views(BqtRequest *r) {{
    for (const auto &view : borrowed_value_origins) {{
        auto *e = entry(view.id);
        if (!e || !view.cursor) continue;
        uint32_t local = 0;
        if (native_call_scope) for (auto pin : native_call_scope->pins) if (pin == view.id) local = 1;
        if (e->active_calls > local) {{ fail(r, EBUSY, "Override cursor is active in a suspended native call"); return false; }}
    }}
    for (const auto &view : borrowed_value_origins) if (view.cursor && entry(view.id)) invalidate(view.id);
    return true;
}}
{graphs}
'''
