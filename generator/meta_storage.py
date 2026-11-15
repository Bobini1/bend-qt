"""Typed storage for Qt's runtime metatype and gadget APIs."""
from pathlib import Path

METHODS = {'create', 'construct', 'destroy', 'destruct', 'compare', 'equals', 'convert', 'view', 'load', 'save'}


def install(classes, selected):
    if 'QMetaType' not in selected:
        return
    classes['MetaStorage'] = dict(name='MetaStorage', object=False, value=True,
        qobject=False, public_destructor=True, abstract=False, copyable=False,
        namespace=False, generate=False, template=False, bases=[], functions=[],
        enums=[], adapter=True)
    selected.append('MetaStorage')


def aliases(g, inside):
    if 'MetaStorage' not in g.ids:
        return ''
    if not inside:
        return 'namespace bendqt { struct MetaStorage; }\n'
    return '''struct MetaStorage {
    QMetaType type;
    void *data;
    bool initialized = false;
    bool owns_storage = true;
    uint32_t alias_owner = 0;
    uint32_t source = 0;
    explicit MetaStorage(QMetaType meta) : type(meta),
        data(::operator new(size_t(meta.sizeOf()), std::align_val_t(meta.alignOf()))) {}
    MetaStorage(QMetaType meta, void *address, uint32_t owner) : type(meta), data(address),
        initialized(true), owns_storage(false), alias_owner(owner) {}
    ~MetaStorage() {
        if (owns_storage) {
            if (initialized) type.destruct(data);
            ::operator delete(data, std::align_val_t(type.alignOf()));
        }
    }
    MetaStorage(const MetaStorage &) = delete;
};\n'''


def handles(f):
    if f['declaring_class'] == 'QtRemoteObjects' and f['name'] == 'copyStoredProperties':
        return True
    if f['declaring_class'] == 'QJSPrimitiveValue':
        return f['name'] in ('data', 'constData') or (f['constructor'] and any(
            a['type']['name'] == 'void' and a['type']['pointers'] == 1 for a in f['arguments']))
    return ((f['declaring_class'] == 'QMetaType' and f['name'] in METHODS) or
            (f['declaring_class'] == 'QMetaProperty' and f['name'].endswith('OnGadget'))) and any(
                a['type']['name'] == 'void' and a['type']['pointers'] == 1 for a in f['arguments'])


def handle():
    return dict(kind='value', name='MetaStorage', cpp='MetaStorage', bend='MetaStorage', raw='U32')


def adapt(g, f):
    if handles(f) and f['return']['name'] == 'void' and f['return']['pointers']:
        return handle()
    return None


def parameters(g, f):
    if not handles(f):
        return None
    args, plan, outputs = [], [], []
    for i, a in enumerate(f['arguments']):
        t = a['type']
        out = t['name'] == 'int' and t['pointers'] == 1 and not t['const']
        if t['name'] == 'void' and t['pointers'] == 1:
            converted = handle()
        else:
            converted = g.type(dict(t, pointers=0, cpp='int') if out else t)
        item = dict(type=converted, source=i, input=None if out else len(args), output=out, mutable=False)
        plan.append(item)
        if out:
            g.conversions.register(converted)
            outputs.append(item)
        else:
            args.append(converted)
    return args, plan, outputs


def method_case(g, m):
    f = m['function']
    if not handles(f):
        return None
    name, owner = f['name'], f['declaring_class']
    if owner == 'QtRemoteObjects':
        return remote_properties_case(g, m)
    if owner == 'QJSPrimitiveValue':
        return primitive_case(g, m)
    lines = ['NativeCallScope call_scope;']
    if not f['static']:
        lines += [f'auto *self = get<{owner}>(r, r->self, {g.ids[owner]}, false, false);']
    values, storage = {}, {}
    for p in m['parameters']:
        i, a = p['source'], f['arguments'][p['source']]
        if p['output']:
            lines += [f'int output_{i} = 0;']
            values[a['name']] = f'&output_{i}'
        elif p['type'].get('name') == 'MetaStorage':
            index = p['input']
            nullable = a['name'] == 'copy'
            word = f'r->arguments[{index}].word' if index < len(m['args']) else '0'
            lines += [f'auto *storage_{i} = get<MetaStorage>(r, {word}, {g.ids["MetaStorage"]}, {str(nullable).lower()}, false);']
            storage[a['name']] = (f'storage_{i}', word, a['type']['const'])
            values[a['name']] = f'(storage_{i} ? storage_{i}->data : nullptr)'
        else:
            code, expr = g.argument(p['type'], p['input'])
            lines += code
            lines += [f'auto &&native_{i} = {expr};']
            values[a['name']] = f'std::move(native_{i})' if a['type']['reference'] == 2 else f'native_{i}'
    lines += ['if (r->error) return true;']
    if owner == 'QMetaProperty':
        pointer, word, const = storage['gadget']
        lines += [f'if (!meta_storage_ready(r, {pointer}, {pointer}->type, true, {str(not const).lower()}, {word})) return true;',
                  f'const QMetaObject *origin = {pointer}->type.metaObject();',
                  'if (!origin || !origin->inherits(self->enclosingMetaObject()) || !self->isValid())',
                  '    return fail(r, EINVAL, "Property does not belong to this gadget metatype");',
                  f'if (!{pointer}->type.flags().testFlag(QMetaType::IsGadget)) return fail(r, EINVAL, "Storage is not a Qt gadget");']
    elif name in ('convert', 'view'):
        for side in ('from', 'to'):
            pointer, word, const = storage[side]
            meta = values.get(side + 'Type') or f'QMetaType({values[side + "TypeId"]})'
            lines += [f'if (!meta_storage_ready(r, {pointer}, {meta}, true, {str(side == "to").lower()}, {word})) return true;']
        if name == 'view':
            lines += [f'if ({storage["from"][1]} == {storage["to"][1]}) return fail(r, ELOOP, "A metatype view cannot retain itself");',
                      f'BqtRequest edge_request{{}}; edge_request.self = {storage["to"][1]};',
                      f'int edge = prepare_retention(&edge_request, meta_storage_slot, 0, {storage["from"][1]});',
                      'if (edge < 0) return fail(r, edge_request.error, edge_request.message);',
                      f'RetentionReservation reservation(edge, edge_request.self, meta_storage_slot, 0);']
    else:
        meta = '*self' if not f['static'] else f'QMetaType({values.get("type", values.get("typeId"))})'
        lines += [f'QMetaType operation_type = {meta};', 'if (!meta_storage_type(r, operation_type)) return true;']
        for key, (pointer, word, const) in storage.items():
            initialized = key != 'where' or name != 'construct'
            if name == 'construct' and key != 'copy':
                initialized = False
            prefix = f'{pointer} && ' if key == 'copy' else ''
            lines += [f'if ({prefix}!meta_storage_ready(r, {pointer}, operation_type, {str(initialized).lower()}, {str(not const).lower()}, {word})) return true;']
    if name == 'create':
        lines += [f'r->result.word = create_meta_storage(r, operation_type, {values["copy"]});',
                  'r->result.owned_handle = r->result.word;',
                  f'if ({storage["copy"][0]} && !preserve_variant_origin(r, r->result.word, {storage["copy"][1]})) return true;',
                  'return true;']
        return lines
    if name == 'construct':
        pointer, word, _ = storage['where']
        lines += [f'if (operation_type.construct({pointer}->data, {values["copy"]})) {{',
                  f'    {pointer}->initialized = true; r->result.word = {word};',
                  f'    if ({storage["copy"][0]} && !preserve_variant_origin(r, {word}, {storage["copy"][1]})) {{ operation_type.destruct({pointer}->data); {pointer}->initialized = false; r->result.word = 0; return true; }}',
                  f'    if (!finish_model_index_ownership(r, {word})) {{ r->result.word = 0; return true; }}',
                  '}', 'return true;']
        return lines
    if name in ('destroy', 'destruct'):
        pointer, word, _ = next(iter(storage.values()))
        lines += [f'if (!{pointer}->owns_storage) return fail(r, EPERM, "Cannot destroy storage borrowed from a live native value");']
        if name == 'destruct':
            lines += [f'operation_type.destruct({pointer}->data);', f'{pointer}->initialized = false;',
                      f'meta_storage_clear_source({word}); clear_variant_origin({word}); {pointer}->source = 0;', 'return true;']
        else:
            lines += [f'invalidate({word});', f'delete {pointer};', 'return true;']
        return lines
    target = owner + '::' if f['static'] else 'self->'
    args = ', '.join(values[a['name']] for a in f['arguments'])
    lines += [f'auto value = {target}{name}({args});']
    if name == 'view':
        lines += [f'if (value) {{ commit_retention(edge, edge_request.self, meta_storage_slot, 0, {storage["from"][1]}, nullptr); {storage["to"][0]}->source = {storage["from"][1]}; }}']
    if name == 'convert':
        # A conversion may leave a destination value unchanged on failure.
        # Keep any existing origin until a successful owning conversion.
        lines += [f'if (value) {{ meta_storage_clear_source({storage["to"][1]}); {storage["to"][0]}->source = 0; }}']
    if name in ('convert', 'view'):
        lines += [f'if (value && !replace_meta_storage_origin(r, {storage["to"][1]}, {storage["from"][1]})) return true;']
        lines += [f'if (value && !finish_model_index_ownership(r, {storage["to"][1]})) return true;']
    if name == 'load':
        target = next(iter(storage.values()))[1]
        lines += [f'if (value) {{ clear_variant_origin({target}); if (!finish_model_index_ownership(r, {target})) return true; }}']
    if m['outputs']:
        lines += [f'r->result = sequence_value({len(m["outputs"]) + 1});', 'r->result.items[0].word = uint32_t(value);']
        for i, p in enumerate(m['outputs'], 1):
            lines += [f'r->result.items[{i}].word = uint32_t(output_{p["source"]});']
    else:
        lines += g.store_result(m['return'], 'value')
    return lines + ['return true;']


def primitive_case(g, m):
    f = m['function']
    lines = ['NativeCallScope scope;']
    if f['constructor']:
        lines += [f'auto *type = get<QMetaType>(r, r->arguments[0].word, {g.ids["QMetaType"]}, false, false);',
                  f'auto *value = get<MetaStorage>(r, r->arguments[1].word, {g.ids["MetaStorage"]}, true, false);',
                  'if (r->error) return true;',
                  'const void *data = nullptr;',
                  'switch (type->id()) {',
                  'case QMetaType::Bool: case QMetaType::Int: case QMetaType::Double: case QMetaType::QString:',
                  '    if (!value) return fail(r, EINVAL, "JavaScript primitive storage is missing");',
                  '    if (!meta_storage_ready(r, value, *type, true, false, r->arguments[1].word)) return true;',
                  '    data = value->data; break;',
                  'default: break;',
                  '}', f'r->result.word = own(r, new QJSPrimitiveValue(*type, data), {g.ids["QJSPrimitiveValue"]});']
    else:
        readonly = f['const'] or f['name'] == 'constData'
        lines += [f'auto *self = get<QJSPrimitiveValue>(r, r->self, {g.ids["QJSPrimitiveValue"]}, false, {str(not readonly).lower()});',
                  'if (r->error) return true;',
                  f'r->result.word = primitive_storage(r, self, r->self, {str(readonly).lower()});']
    return lines + ['r->result.owned_handle = r->result.word;', 'return true;']


def emit(g):
    if 'MetaStorage' not in g.ids:
        return
    types = {name: dict(kind='value', name=name, bend=name, raw='U32') for name in ('MetaStorage', 'QMetaType', 'QVariant')}
    specs = [
        ('allocate', 'QMetaType', 'MetaStorage', 'allocate_meta_storage(r, *value)'),
        ('fromVariant', 'QVariant', 'MetaStorage', 'create_meta_storage(r, value->metaType(), value->constData())'),
        ('toVariant', 'MetaStorage', 'QVariant', None),
        ('metaType', 'MetaStorage', 'QMetaType', None),
        ('isInitialized', 'MetaStorage', 'Bool', None),
    ]
    for method, argument, result, expr in specs:
        op = g.next_id; g.next_id += 1
        lines = ['NativeCallScope call_scope;', f'auto *value = get<{argument}>(r, r->arguments[0].word, {g.ids[argument]}, false, false);', 'if (r->error) return true;']
        if method in ('fromVariant', 'toVariant'):
            lines += ['call_scope.value_origin = variant_source_origin(r->arguments[0].word);']
        if method == 'toVariant':
            lines += ['if (!meta_storage_ready(r, value, value->type, true, false, r->arguments[0].word)) return true;',
                      'if (!value->type.isCopyConstructible()) return fail(r, ENOTSUP, "Metatype cannot be copied into QVariant");',
                      'if (value->source) return fail(r, ENOTSUP, "A metatype view cannot escape its storage origin as an untracked QVariant");',
                      f'r->result.word = own(r, new QVariant(value->type, value->data), {g.ids["QVariant"]});']
        elif method == 'metaType':
            lines += [f'r->result.word = own(r, new QMetaType(value->type), {g.ids["QMetaType"]});']
        elif method == 'isInitialized':
            lines += ['r->result.word = value->initialized;']
        else:
            lines += [f'r->result.word = {expr};']
        if result != 'Bool':
            lines += ['r->result.owned_handle = r->result.word;']
        if method in ('fromVariant', 'toVariant'):
            lines += ['if (!preserve_variant_origin(r, r->result.word, r->arguments[0].word)) return true;']
        lines += ['return true;']
        g.cases.append(f'case {op}: {{\n' + '\n'.join('    ' + line for line in lines) + '\n}')
        g.emit_effect('MetaStorage.' + method, [('value', types[argument])],
                      types[result] if result != 'Bool' else dict(kind='bool', bend='Bool', raw='U32'), op)


def remote_properties_case(g, m):
    """The native functions use readOnGadget/writeOnGadget, never QObject casts."""
    lines = ['NativeCallScope call_scope;']
    expressions, storages = [], []
    for i, (source, t) in enumerate(zip(m['function']['arguments'], m['args'])):
        if t.get('name') == 'MetaStorage':
            writing = not source['type']['const']
            lines += [f'auto *storage_{i} = get<MetaStorage>(r, r->arguments[{i}].word, {g.ids["MetaStorage"]}, false, false);']
            expressions.append(f'storage_{i}->data')
            storages.append((i, writing))
        else:
            declarations, expression = g.argument(t, i)
            lines += declarations + [f'auto &&native_{i} = {expression};']
            expressions.append(f'native_{i}')
    lines += ['if (r->error) return true;',
              'if (!native_0) return fail(r, EINVAL, "Stored-property copying requires gadget metadata");']
    source = next((i for i, writing in storages if not writing), None)
    target = next((i for i, writing in storages if writing), None)
    for i, writing in storages:
        lines += [f'if (!meta_storage_ready(r, storage_{i}, storage_{i}->type, true, {str(writing).lower()}, r->arguments[{i}].word)) return true;',
                  f'if (!storage_{i}->type.flags().testFlag(QMetaType::IsGadget) || storage_{i}->type.metaObject() != native_0)',
                  '    return fail(r, EINVAL, "Stored-property metadata must exactly match the gadget storage type");']
    if target is not None:
        lines += [f'if (!storage_{target}->owns_storage || storage_{target}->source || entry(r->arguments[{target}].word)->validate)',
                  '    return fail(r, EBUSY, "Stored-property destination must be independent owning gadget storage");',
                  'struct PropertyWriteGuard {',
                  '    uint32_t id; int exceptions = std::uncaught_exceptions();',
                  '    ~PropertyWriteGuard() {',
                  '        if (std::uncaught_exceptions() > exceptions) if (auto *e = entry(id)) {',
                  '            auto *value = e->value; auto destroy = e->destroy; invalidate(id); destroy(value);',
                  '        }', '    }', f'}} write_guard{{r->arguments[{target}].word}};']
    lines += [f'QtRemoteObjects::copyStoredProperties({", ".join(expressions)});']
    if target is not None and source is not None:
        lines += [f'if (!replace_meta_storage_origin(r, r->arguments[{target}].word, r->arguments[{source}].word)) return true;']
    if target is not None:
        lines += [f'if (!finish_model_index_ownership(r, r->arguments[{target}].word)) return true;']
    return lines + ['return true;']


def cpp(g):
    if 'MetaStorage' not in g.ids:
        return ''
    code = (Path(__file__).parent / 'templates/meta_storage.cpp').read_text().replace('@TYPE@', str(g.ids['MetaStorage']))
    if 'QJSPrimitiveValue' in g.ids:
        code += (Path(__file__).parent / 'templates/primitive_storage.cpp').read_text().replace('@TYPE@', str(g.ids['MetaStorage'])).replace('@PRIMITIVE@', str(g.ids['QJSPrimitiveValue']))
    return code
