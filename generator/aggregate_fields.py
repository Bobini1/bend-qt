"""Copy-aware lifetime guards for public aggregate fields with dependent values."""
from pathlib import Path
import hashlib
import value_provenance
import resource_swaps
import borrowed_values
import generic_arguments
import metadata_lifetimes
import model_indices
import value_lifetimes
import boundary_finders
import retention
import form_rows
import pointer_fields
import video_buffers
import lazy_values
import protected_fields


def dependent_types():
    """Seed aggregate closure from the existing origin-aware value adapters."""
    return (value_provenance.TYPES | value_lifetimes.TYPES | model_indices.TYPES |
            borrowed_values.EPHEMERAL_TYPES | metadata_lifetimes.VALUES |
            generic_arguments.TYPES | boundary_finders.ORIGIN_TYPES |
            retention.COPY_ORIGIN_TYPES |
            {'QVariant', form_rows.TYPE, pointer_fields.ATTRIBUTES, video_buffers.MAP})


def prepare(g):
    if hasattr(g, 'aggregate_fields'):
        return
    lazy_values.prepare(g)
    dependent = dependent_types() | g.lazy_values.keys()
    def pointer(t, owner):
        return t.get('pointers') == 1 and not t.get('array') and t.get('name') in g.ids and (
            g.classes.get(t.get('name'), {}).get('qobject', False) or
            (t['name'] == 'QMetaObject' and t.get('const')) or
            (owner == 'QQuickItem::UpdatePaintNodeData' and t['name'] == 'QSGTransformNode'))
    def contains(t):
        if t.get('pointers') or t.get('reference'): return False
        return t.get('name') in dependent or any(contains(x) for x in t.get('instantiations', []))
    def fields(name, seen=()):
        if name in seen: return {}
        result = {}
        for base in g.classes[name]['bases']:
            if base in g.classes: result.update(fields(base, (*seen, name)))
        for f in g.classes[name].get('fields', []):
            if (f.get('public') or protected_fields.permitted(g, f, name)) and not f.get('removed') and not f.get('static'):
                result[f['name']] = dict(f, declaring_class=f.get('declaring_class') or name)
        return result
    all_fields = {name: fields(name) for name in g.selected}
    while True:
        more = {name for name, members in all_fields.items() if any(contains(f['type']) or pointer(f['type'], name) for f in members.values())}
        if more <= dependent: break
        dependent |= more
    slots, specs = {}, {}
    for name, members in all_fields.items():
        for f in members.values():
            if not (contains(f['type']) or pointer(f['type'], name)): continue
            t = g.conversions.register(g.type(f['type'], result=True))
            key = f['declaring_class'] + '.' + f['name']
            slot = 0xda000000 | (int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) & 0xffffff)
            if slot in slots and slots[slot] != key: raise ValueError('Aggregate field slot collision')
            slots[slot] = key
            specs.setdefault(name, []).append(dict(field=f, type=t, slot=slot,
                observed_object=bool(f['type'].get('pointers')),
                callback_pointer=name == 'QQuickItem::UpdatePaintNodeData' and f['type']['name'] == 'QSGTransformNode'))
    g.aggregate_fields = specs
    g.aggregate_field_slots = slots


def sources(t, expression, depth=0):
    if t['kind'] in ('value', 'object'):
        return [f'if ({expression}.word) field_sources.push_back({expression}.word);']
    children = t.get('children', [])
    if not children: return []
    if t['kind'] in ('list', 'map', 'array', 'optional'):
        variable = f'field_source_{depth}'
        body = sources(children[0], f'{expression}.items[{variable}]', depth + 1)
        return ([f'for (size_t {variable}=0; {variable}<{expression}.count; ++{variable}) {{'] +
                ['    ' + line for line in body] + ['}']) if body else []
    result = []
    for i, child in enumerate(children): result += sources(child, f'{expression}.items[{i}]', depth + 1)
    return result


def before_call(g, m):
    prepare(g)
    f = m['function']
    if f['declaring_class'] not in g.aggregate_fields: return []
    guard = [] if f['constructor'] or f['const'] or f['static'] else ['if (entry(r->self)->active_calls > 1) return fail(r, EBUSY, "Aggregate value is in another active native call");']
    if f['constructor'] or f['name'] == 'operator=':
        if len(m['args']) == 1 and m['args'][0].get('name') == f['declaring_class']:
            return guard + ['call_scope.value_origin = r->arguments[0].word;']
        lines = ['std::vector<uint32_t> field_sources;']
        for i, t in enumerate(m['args']): lines += sources(t, f'r->arguments[{i}]')
        return guard + lines + ['ValueProvenanceScope field_origins(&call_scope, std::move(field_sources));']
    return guard


def after_call(g, m):
    f = m['function']
    if f['declaring_class'] in g.aggregate_fields and not f['const'] and not f['static'] and not f['constructor']:
        return ['if (!finish_aggregate_ownership(r, r->self)) return true;']
    return []


def after_native(g, m):
    return ['aggregate_swap(r->self, r->arguments[0].word);'] if resource_swaps.handles(g, m) else []


def field_access(g, field, expression, argument=None):
    prepare(g)
    spec = next((x for x in g.aggregate_fields.get(field['class'], [])
                 if x['field']['name'] == field['field']), None)
    if not spec and (protected_fields.permitted(g, field['source'], field['declaring_class'])
                     and protected_fields.native_pointer(g, field['class'], field['source']['type'])):
        key = field['declaring_class'] + '.' + field['field']
        slot = 0xda000000 | (int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) & 0xffffff)
        if slot in g.aggregate_field_slots and g.aggregate_field_slots[slot] != key:
            raise ValueError('Aggregate field slot collision')
        g.aggregate_field_slots[slot] = key
        spec = dict(field=field['source'], type=field['type'], slot=slot, observed_object=True, callback_pointer=False)
    if not spec: return None
    if spec['observed_object']:
        guard = ['if (!gui_render_depth) return fail(r, EPERM, "Scene graph fields require an active GUI render callback");'] if spec['callback_pointer'] else []
        if not field['setter']:
            return guard + g.store_result(field['type'], expression)
        return guard + ['if (entry(r->self)->active_calls > 1) return fail(r, EBUSY, "Aggregate field is in an active native call");',
                'AggregateFieldUpdate field_update(r, r->self);',
                f'if (!field_update.capture_pointer({spec["slot"]}u, {argument}, {g.ids[field["type"]["name"]]}) || !field_update.prepare()) return true;',
                f'{expression} = {argument};', 'if (!field_update.commit()) return true;']
    if not field['setter']:
        return [f'auto field_sources = aggregate_source_field(r, {spec["slot"]}u);',
                'NativeCallScope field_copy_scope;',
                'ValueProvenanceScope field_origins(&field_copy_scope, std::move(field_sources));'] + g.store_result(field['type'], expression)
    t = field['type']
    return ['if (entry(r->self)->active_calls > 1) return fail(r, EBUSY, "Aggregate field is in an active native call");',
            'std::vector<uint32_t> field_sources;'] + sources(t, 'r->arguments[0]') + [
            'AggregateFieldUpdate field_update(r, r->self);',
            f'if (!field_update.capture({spec["slot"]}u, std::move(field_sources), [&] {{ return write_{t["native_codec"]}(r, {argument}); }})) return true;',
            'if (!field_update.prepare()) return true;',
            'try {', f'    {expression} = {argument};',
            '} catch (...) { field_update.native_failed(); throw; }',
            'if (!field_update.commit()) return true;']


def field_type(g, name, field, setter):
    t = field['type']
    if t.get('pointers') == 1 and not t.get('array') and t.get('name') in g.ids and (
            g.classes.get(t.get('name'), {}).get('qobject', False) or
            (t['name'] == 'QMetaObject' and t.get('const')) or
            (name == 'QQuickItem::UpdatePaintNodeData' and t['name'] == 'QSGTransformNode')):
        return g.conversions.register(g.type(t, result=not setter))
    return None


def cpp(g):
    prepare(g)
    cases = []
    for name, fields in g.aggregate_fields.items():
        lines = [f'case {g.ids[name]}: {{', f'auto *value = static_cast<{name} *>(e->value);']
        for spec in fields:
            t, slot = spec['type'], spec['slot']
            access = protected_fields.expression(g, dict(source=spec['field'], field=spec['field']['name'],
                declaring_class=spec['field']['declaring_class']), 'value') or f'value->{spec["field"]["name"]}'
            if spec['observed_object']:
                callback = ', true' if spec['callback_pointer'] else ''
                trust = spec['field'].get('protected') and g.classes.get(t.get('name'), {}).get('qobject')
                if trust: lines += ['{ NativeAggregateInputScope native_field(r);']
                lines += [f'if (!update.capture_pointer({slot}u, {access}, {g.ids[t["name"]]}{callback})) {{ update.invalidate_destination(); return 0; }}']
                if trust: lines += ['}']
                continue
            lines += [f'if (!update.capture({slot}u, aggregate_source_field(r, {slot}u), [&] {{',
                      f'    return write_{t["native_codec"]}(r, {access});',
                      '})) { update.invalidate_destination(); return 0; }']
        lines += ['break;', '}']
        cases += lines
    return ((Path(__file__).parent / 'templates/aggregate_fields.cpp').read_text()
            .replace('// @AGGREGATE_CASES@', '\n'.join(cases))
            .replace('// @AGGREGATE_SUPPORTED@', ' '.join(f'case {g.ids[name]}:' for name in g.aggregate_fields) + (' supported = true; break;' if g.aggregate_fields else '')))


def inventory(g):
    prepare(g)
    return {
        'fields': [dict(class_name=name, field=spec['field']['name'], cpp=spec['field']['type']['cpp'],
                        retention=('callback-origin alias' if spec['callback_pointer'] else
                                   'compiled metadata lease or observed dynamic origin' if spec['type'].get('name') == 'QMetaObject' else
                                   'already observed native identity' if spec['observed_object'] else 'private immutable dependency snapshots'))
                   for name, specs in sorted(g.aggregate_fields.items()) for spec in specs],
        'copy_paths': ['native construction and copy construction', 'native assignment',
                       'recursive container codecs', 'QVariant origin snapshots', 'resource swap'],
        'replacement': 'Convert and reserve the complete changed field before native mutation; failed preflight leaves old fields and dependencies intact',
        'native_failure': 'A throwing native assignment invalidates and destroys the uncertain destination',
        'limitations': ['Unobserved native pointer fields reject ENOTSUP outside their explicit callback or compiled-metadata contracts',
                        'Opaque native QVariant payload graphs still require an observed origin',
                        'Other fixed arrays and native pointer fields require separate extent and lifetime adapters'],
        'verification': 'Pure commit decision is proved; native graph observation and destruction require integration tests',
    }
