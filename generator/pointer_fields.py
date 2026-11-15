"""Owned backing and observed origins for public native pointer fields."""
from pathlib import Path
import resource_swaps

ATTRIBUTES = 'QSGGeometry::AttributeSet'


def attributes_type(g):
    child = g.conversions.register(g.type(dict(name='QSGGeometry::Attribute', cpp='QSGGeometry::Attribute',
                       pointers=0, reference=0, const=False, enum=False, flags=False, container=False), result=True))
    return g.conversions.register(dict(kind='list', name='QList', children=[child],
        cpp='QList<QSGGeometry::Attribute>', bend='List<&2, QSGGeometry.Attribute>', raw='Wire',
        codec='List_QSGGeometry_Attribute'))


def field_type(g, name, field, setter):
    if name == ATTRIBUTES and field['name'] == 'attributes' and not setter:
        return attributes_type(g)
    return None


def field_access(g, field, expression, argument=None):
    if field['class'] != ATTRIBUTES: return None
    if field['field'] == 'attributes':
        return ['if (!validate_geometry_attributes(r, r->self)) return true;',
                'QList<QSGGeometry::Attribute> field_attributes;',
                'for (int i=0; i<self->count; ++i) field_attributes.append(self->attributes[i]);'] + g.store_result(field['type'], 'field_attributes')
    if field['setter'] and field['field'] in ('count', 'stride'):
        check = 'geometry_attribute_count_allowed' if field['field'] == 'count' else 'geometry_attribute_stride_allowed'
        return [f'if (!{check}(r, r->self, {argument})) return true;', f'{expression} = {argument};']
    return None


def before_call(g, m):
    f = m['function']; owner, name = f['declaring_class'], f['name']
    if owner == ATTRIBUTES and not f['const'] and not f['static'] and not f['constructor']:
        return ['if (!geometry_attribute_mutation_allowed(r, r->self)) return true;']
    if owner == 'QSGGeometry' and f['constructor']:
        index_count = g.argument(m['args'][2], 2)[1] if len(m['args']) > 2 else '0'
        index_type = g.argument(m['args'][3], 3)[1] if len(m['args']) > 3 else 'QSGGeometry::UnsignedShortType'
        return [f'if (!geometry_allocation_allowed(r, *a0, {g.argument(m["args"][1], 1)[1]}, {index_count}, {index_type})) return true;']
    if owner == 'QSGGeometry' and name == 'allocate':
        index_count = g.argument(m['args'][1], 1)[1] if len(m['args']) > 1 else '0'
        return [f'if (!geometry_allocation_allowed(r, {{self->attributeCount(), self->sizeOfVertex(), self->attributes()}}, {g.argument(m["args"][0], 0)[1]}, {index_count}, self->indexType())) return true;']
    return []


def after_call(g, m):
    f = m['function']
    if f['declaring_class'] == ATTRIBUTES and not (f['const'] or f['constructor'] or f['static']):
        return ['if (!finish_pointer_field_ownership(r, r->self)) return true;']
    return []


def after_native(g, m):
    if m['function']['declaring_class'] == ATTRIBUTES and resource_swaps.handles(g, m):
        return ['swap_geometry_attributes(r->self, r->arguments[0].word);']
    return []


def emit(g):
    if ATTRIBUTES not in g.ids: return
    tid = g.ids[ATTRIBUTES]; values = attributes_type(g)
    i32 = dict(kind='i32', bend='Int32', raw='U32')
    handle = dict(kind='value', name=ATTRIBUTES, bend='QSGGeometry.AttributeSet', raw='U32')
    declarations, value = g.argument(values, 1)
    lines = ['NativeCallScope call_scope;'] + declarations + ['if (r->error) return true;',
        f'auto data = std::make_shared<std::vector<QSGGeometry::Attribute>>(({value}).begin(), ({value}).end());',
        'int32_t stride = int32_t(r->arguments[0].word);',
        'if (stride < 0 || data->size() > INT_MAX) return fail(r, EINVAL, "Invalid geometry attribute layout");',
        'auto value = std::make_unique<QSGGeometry::AttributeSet>(QSGGeometry::AttributeSet{int(data->size()), stride, data->empty() ? nullptr : data->data()});',
        f'r->result.word = own(r, value.release(), {tid});',
        'r->result.owned_handle = r->result.word;', 'return true;']
    operation = g.next_id; g.next_id += 1
    g.cases.append(f'case {operation}: {{\n' + '\n'.join(lines) + '\n}')
    g.emit_effect('QSGGeometry.AttributeSet.fromAttributes', [('stride', i32), ('attributes', values)], handle, operation)


def cpp(g):
    if ATTRIBUTES not in g.ids:
        return 'static void pointer_fields_forget(uint32_t) {}\nstatic uint32_t finish_pointer_field_ownership(BqtRequest *, uint32_t id) { return id; }\n'
    return ((Path(__file__).parent / 'templates/pointer_fields.cpp').read_text()
            .replace('@ATTRIBUTE_SET@', str(g.ids[ATTRIBUTES]))
            .replace('@ATTRIBUTE@', str(g.ids['QSGGeometry::Attribute'])))
