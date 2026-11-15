"""QVariant value converters discovered from measured Qt metatype traits."""
from pathlib import Path
import re


def cleanup_safe(g, name):
    cls = g.classes[name]
    return name in ('QVariant', 'MetaStorage') or (cls.get('copyable')
        and not cls.get('object') and cls.get('public_destructor'))


def before_call(g, m):
    f = m['function']
    if f['declaring_class'] == 'QVariant' and not (f['constructor'] or f['const'] or f['static']):
        return ['const QMetaType variant_previous_type = self->metaType();']
    return []


def after_native(g, m):
    f = m['function']
    if f['declaring_class'] != 'QVariant' or f['constructor'] or f['static'] or f['const']:
        return []
    if f['name'] == 'swap':
        return ['swap_variant_origins(r->self, r->arguments[0].word);']
    if f['name'] == 'operator=' and m['args'] and m['args'][0].get('name') == 'QVariant':
        return ['if (!assign_variant_origin(r, r->self, r->arguments[0].word)) return true;']
    if hasattr(g, 'custom_signal_arguments') and 'QVariant' in g.ids:
        return ['if (self->metaType() != variant_previous_type) {',
                '    clear_variant_origin(r->self);',
                '    if (!generic_variant_refresh(r, r->self)) return true;', '}']
    return ['if (self->metaType() != variant_previous_type) clear_variant_origin(r->self);']


def after_call(g, m):
    f = m['function']
    if f['declaring_class'] != 'QVariant' or m['return'].get('name') != 'QVariant':
        return []
    if f['constructor']:
        source = next((f'r->arguments[{i}].word' for i, t in enumerate(m['args'])
                       if t.get('name') == 'QVariant'), None)
    else:
        source = None if f['static'] else 'r->self'
    return [f'if (!preserve_variant_origin(r, r->result.word, {source})) return true;'] if source else []


def emit(g):
    variant = dict(kind='value', name='QVariant', bend='QVariant', raw='U32')
    unit = dict(kind='void', bend='Unit', raw='Unit')
    # QVariant is a synthetic carrier: upstream PySide's custom implementation
    # does not expose these ordinary value operations through ApiExtractor.
    for method in ('copy', 'assign', 'swap'):
        op = g.next_id; g.next_id += 1
        params = [('self', variant)] + ([('other', variant)] if method != 'copy' else [])
        lines = ['NativeCallScope call_scope;',
                 f'auto *self = get<QVariant>(r, r->self, {g.ids["QVariant"]}, false, {str(method != "copy").lower()});']
        if method != 'copy':
            lines += [f'auto *other = get<QVariant>(r, r->arguments[0].word, {g.ids["QVariant"]}, false, {str(method == "swap").lower()});']
        lines += ['if (r->error) return true;']
        if method == 'copy':
            lines += ['call_scope.value_origin = variant_source_origin(r->self);',
                      f'r->result.word = own(r, new QVariant(*self), {g.ids["QVariant"]});',
                      'r->result.owned_handle = r->result.word;',
                      'if (!preserve_variant_origin(r, r->result.word, r->self)) return true;']
        elif method == 'assign':
            lines += ['if (entry(r->self)->active_calls > 1) return fail(r, EBUSY, "QVariant is in another active native call");',
                      '*self = *other;',
                      'if (!assign_variant_origin(r, r->self, r->arguments[0].word)) return true;',
                      'if (!finish_model_index_ownership(r, r->self)) return true;']
        else:
            lines += ['if (!prepare_resource_swap(r, r->arguments[0].word)) return true;',
                      'self->swap(*other);',
                      'finish_resource_swap(r->self, r->arguments[0].word);',
                      'swap_variant_origins(r->self, r->arguments[0].word);']
        lines += ['return true;']
        g.cases.append(f'case {op}: {{\n' + '\n'.join('    ' + line for line in lines) + '\n}')
        g.emit_effect('QVariant.' + method, params, variant if method == 'copy' else unit,
                      op, has_self=True)
    for name in g.selected:
        cls = g.classes[name]
        if (name == 'QVariant' or not cls.get('copyable')
                or cls.get('object') or not cls.get('public_destructor')):
            continue
        typ = dict(kind='value', name=name, bend=name.replace('::', '.'), raw='U32')
        label = re.sub(r'[^A-Za-z0-9_]', '_', name)
        for to_variant in (True, False):
            source, result = (typ, variant) if to_variant else (variant, typ)
            op = g.next_id; g.next_id += 1
            lines = ['NativeCallScope call_scope;',
                f'auto *value = get<{source["name"]}>(r, r->arguments[0].word, {g.ids[source["name"]]}, false, false);',
                'if (r->error) return true;',
                'call_scope.value_origin = variant_source_origin(r->arguments[0].word);']
            if to_variant:
                expression = 'new QVariant(QVariant::fromValue(*value))'
            else:
                lines += [f'if (value->metaType() != QMetaType::fromType<{name}>()) return fail(r, EINVAL, "QVariant has a different native metatype");']
                expression = f'new {name}(*static_cast<const {name} *>(value->constData()))'
            lines += [f'r->result.word = own(r, {expression}, {g.ids[result["name"]]});',
                      'r->result.owned_handle = r->result.word;',
                      ('if (!generic_variant_finish(r, r->result, r->arguments[0].word)) return true;'
                       if 'QObject' in g.ids else
                       'if (!preserve_variant_origin(r, r->result.word, r->arguments[0].word)) return true;'),
                      'return true;']
            g.cases.append(f'case {op}: {{\n' + '\n'.join('    ' + line for line in lines) + '\n}')
            g.emit_effect('QVariant.' + ('from_' if to_variant else 'to_') + label,
                          [('value', source)], result, op)


def cpp(g):
    import abi_cohorts
    cases = []
    for name in g.selected:
        cls = g.classes[name]
        if (name not in ('QVariant', 'QTextBoundaryFinder') and (not cls.get('copyable')
                or cls.get('object') or not cls.get('public_destructor'))):
            continue
        body = f'case {g.ids[name]}: result = own(r, new {name}(*static_cast<const {name} *>(source->value)), {g.ids[name]}); break;'
        if abi_cohorts.required(g, body):
            body = '#if BQT_HAS_RHI\n' + body + '\n#endif'
        cases.append(body)
    cases.append(f'''case {g.ids['MetaStorage']}: {{
        auto *storage = static_cast<MetaStorage *>(source->value);
        if (!storage->initialized) {{ fail(r, ENODATA, "Cannot copy uninitialized metatype storage"); return 0; }}
        result = create_meta_storage(r, storage->type, storage->data); break;
    }}''')
    code = (Path(__file__).parent / 'templates/variant_values.cpp').read_text()
    return code + '''
static uint32_t create_meta_storage(BqtRequest *, QMetaType, const void *);
static uint32_t make_variant_snapshot(BqtRequest *r, uint32_t id) {
    auto *source = entry(id);
    if (!source) { fail(r, ESTALE, "Variant origin was destroyed"); return 0; }
    NativeCallScope scope; scope.value_origin = id;
    uint32_t result = 0;
    switch (source->type) {
''' + '\n'.join(cases) + '''
    default: fail(r, ENOTSUP, "Native value has no immutable QVariant origin representation"); return 0;
    }
    if (auto *snapshot = entry(result)) {
        snapshot->read_only = true;
        snapshot->pending_release = true;
        variant_snapshots[result & 65535u] = result;
        schedule_collection();
    }
    return result;
}
'''
