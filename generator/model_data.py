"""Opaque, origin-checked identities for model-owned internal data pointers."""


def install(classes, selected):
    classes['ModelData'] = dict(name='ModelData', object=False, value=True, qobject=False,
        public_destructor=True, abstract=False, copyable=False, namespace=False,
        generate=False, template=False, bases=[], functions=[], enums=[], adapter=True)
    selected.append('ModelData')


def adapt(g, f):
    if f['declaring_class'] in ('QModelIndex', 'QPersistentModelIndex') and f['name'] in ('internalPointer', 'constInternalPointer'):
        return dict(kind='value', name='ModelData', cpp='ModelData', bend='ModelData', raw='U32',
                    model_data=f['declaring_class'])
    return None


def parameters(g, f):
    if (f['declaring_class'], f['name']) != ('QAbstractProxyModel', 'createSourceIndex'):
        return None
    args = [g.type(a['type']) for a in f['arguments'][:2]]
    args.append(dict(kind='value', name='ModelData', cpp='ModelData', bend='ModelData', raw='U32'))
    plan = [dict(type=t, source=i, input=i, output=False, mutable=False) for i, t in enumerate(args)]
    return args, plan, []


def method_case(g, m):
    f = m['function']
    if (f['declaring_class'], f['name']) != ('QAbstractProxyModel', 'createSourceIndex'):
        return None
    import protected_members
    lines = ['NativeCallScope scope;',
             f'auto *self = get<QAbstractProxyModel>(r, r->self, {g.ids["QAbstractProxyModel"]}, false, false);',
             f'auto *data = get<ModelData>(r, r->arguments[2].word, {g.ids["ModelData"]}, false, false);',
             'if (r->error) return true;',
             'const QAbstractItemModel *origin = nullptr;',
             'if (data->persistent) {',
             f'    auto *index = get<QPersistentModelIndex>(r, data->index, {g.ids["QPersistentModelIndex"]}, false, false);',
             '    if (index) origin = index->model();',
             '} else {',
             f'    auto *index = get<QModelIndex>(r, data->index, {g.ids["QModelIndex"]}, false, false);',
             '    if (index) origin = index->model();',
             '}',
             'if (r->error) return true;',
             'if (!origin || self->sourceModel() != origin) return fail(r, EINVAL, "Internal data does not belong to this proxy source model");']
    arguments = []
    for i, t in enumerate(m['args'][:2]):
        declarations, value = g.argument(t, i)
        lines += declarations
        arguments.append(value)
    arguments.append('reinterpret_cast<void *>(data->address)')
    expression = protected_members.expression(g, f, arguments)
    lines += ['if (r->error) return true;', 'auto returned = ' + expression + ';']
    lines += g.store_result(m.get('native_return', m['return']), 'returned')
    return lines + ['return true;']


def store(g, t, expression):
    if not t.get('model_data'):
        return None
    source = t['model_data']
    return [f'r->result.word = make_model_data(r, *self, {g.ids[source]}, reinterpret_cast<quintptr>({expression}));',
            'r->result.owned_handle = r->result.word;']


def emit(g):
    handle = dict(kind='value', name='ModelData', bend='ModelData', raw='U32')
    boolean = dict(kind='bool', bend='Bool', raw='U32')
    for name in ('isNull', 'same'):
        operation = g.next_id; g.next_id += 1
        args = [('self', handle)] + ([('other', handle)] if name == 'same' else [])
        lines = ['NativeCallScope scope;', f'auto *self = get<ModelData>(r, r->self, {g.ids["ModelData"]}, false, false);']
        if name == 'same':
            lines += [f'auto *other = get<ModelData>(r, r->arguments[0].word, {g.ids["ModelData"]}, false, false);']
        lines += ['if (r->error) return true;',
                  'r->result.word = ' + ('self->address == other->address' if name == 'same' else 'self->address == 0') + ';',
                  'return true;']
        g.cases.append(f'case {operation}: {{\n' + '\n'.join('    ' + line for line in lines) + '\n}')
        g.emit_effect('ModelData.' + name, args, boolean, operation, has_self=True)


def cpp(g):
    return f'''
static bool validate_model_data(BqtRequest *r, uint32_t id) {{
    auto *e = entry(id);
    if (!e) {{ fail(r, ESTALE, "Model data identity expired"); return false; }}
    auto *value = static_cast<ModelData *>(e->value);
    quintptr current = 0;
    if (value->persistent) {{
        auto *index = get<QPersistentModelIndex>(r, value->index, {g.ids['QPersistentModelIndex']}, false, false);
        if (!index) return false;
        if (value->was_valid && !index->isValid()) {{ fail(r, ESTALE, "Persistent model data was removed"); return false; }}
        current = reinterpret_cast<quintptr>(index->internalPointer());
    }} else {{
        auto *index = get<QModelIndex>(r, value->index, {g.ids['QModelIndex']}, false, false);
        if (!index) return false;
        current = reinterpret_cast<quintptr>(index->internalPointer());
    }}
    if (current != value->address) {{ fail(r, ESTALE, "Model internal data identity changed"); return false; }}
    return true;
}}
template <typename T> static uint32_t make_model_data(BqtRequest *r, const T &source, uint16_t type, quintptr address) {{
    auto index = own(r, new T(source), type);
    if (!index) return 0;
    struct IndexGuard {{
        uint32_t id; bool keep = false;
        ~IndexGuard() {{ if (!keep) if (auto *e = entry(id)) {{ auto *value = e->value; auto destroy = e->destroy; invalidate(id); destroy(value); }} }}
    }} index_guard{{index}};
    auto id = own(r, new ModelData{{address, index, std::is_same_v<T, QPersistentModelIndex>, source.isValid()}}, {g.ids['ModelData']});
    if (!id) return 0;
    BqtRequest claim{{}}; claim.self = id;
    // Must differ from value_provenance_slot: provenance
    // validation treats every edge in that slot as a QObject origin.
    constexpr uint32_t slot = 0xffffffdeu;
    int edge = prepare_retention(&claim, slot, 0, index);
    if (claim.error) {{
        auto *value = static_cast<ModelData *>(entry(id)->value);
        invalidate(id); delete value; schedule_collection();
        fail(r, claim.error, claim.message); return 0;
    }}
    commit_retention(edge, id, slot, 0, index, nullptr);
    entry(index)->pending_release = true;
    index_guard.keep = true;
    entry(id)->validate = validate_model_data;
    return id;
}}
'''
