"""Typed access to public data members from Shiboken's extracted class model."""
import copy
import converter_cleanup
import persistent_storage
import rhi_lifetimes
import constant_fields
import form_rows
import aggregate_fields
import pointer_fields
import video_buffers
import lazy_values
import durations
import protected_fields


def _inherited(g, name, stack=()):
    if name in stack:
        return {}
    own = {f['name']: [dict(f, declaring_class=f.get('declaring_class') or name)]
           for f in g.classes[name].get('fields', [])}
    inherited = {}
    for base in g.classes[name]['bases']:
        if base not in g.classes:
            continue
        for field, candidates in _inherited(g, base, (*stack, name)).items():
            if field not in own:
                inherited.setdefault(field, []).extend(candidates)
    return dict(inherited, **own)


def _value_type(g, source, setter):
    if setter and source.get('const'):
        raise ValueError('Const field or array element is read-only')
    if source.get('pointers') or source.get('reference'):
        raise ValueError('Pointer/reference fields require an explicit observed-alias and retention contract')
    duration = durations.normalize(source)
    if duration:
        return g.conversions.register(g.type(duration, result=not setter))
    if source['name'] == 'std::atomic' and len(source.get('instantiations', [])) == 1:
        element = _value_type(g, source['instantiations'][0], setter)
        if element['kind'] not in ('bool', 'i32', 'u32', 'i64', 'u64', 'real', 'duration', 'enum', 'enum64', 'flags', 'flags64'):
            raise ValueError('Atomic fields require a trivially copyable scalar representation')
        return dict(element, atomic_field=True)
    if source.get('array'):
        count = source.get('array_count', -1)
        child = source.get('array_element')
        if not child or count <= 0:
            raise ValueError('Array field requires a known positive fixed extent')
        element = _value_type(g, child, setter)
        native = element['cpp'].removeprefix('const ').replace('&', '').strip()
        return g.conversions.register({'kind': 'list', 'name': 'QList', 'children': [element],
            'cpp': f'QList<{native}>', 'bend': f'List<&2, {element["bend"]}>', 'raw': 'Wire',
            'codec': 'List_' + element['codec'].removeprefix('Convert_'),
            'field_count': count})
    for child in source.get('instantiations', []):
        _value_type(g, child, setter)
    source = dict(source, const=False, reference=0, cpp=source['cpp'].removeprefix('const ').strip())
    converted = dict(g.type(source, result=not setter))
    if converted['kind'] in ('object', 'void'):
        raise ValueError('Field requires an independently copyable value representation')
    if converted['kind'] == 'value':
        cls = g.classes[converted['name']]
        if not cls.get('copyable'):
            raise ValueError('Field getter requires a public native copy constructor')
        if setter and not cls.get('native_copy_assignable', cls.get('copyable', False)):
            raise ValueError('Field setter requires public native copy assignment')
        converted.pop('move_result', None)
    if setter and (converted['kind'] in ('string_view', 'byte_view', 'latin1_view')
                   or source['name'] == 'std::string_view'):
        raise ValueError('A view field setter requires persistent backing storage')
    return g.conversions.register(converted)


def prepare(g):
    if hasattr(g, 'field_bindings'):
        return
    g.field_bindings, g.public_fields, g.excluded_fields = [], [], []
    for name in g.selected + g.namespaces:
        for field, candidates in sorted(_inherited(g, name).items()):
            details = {'class': name, 'field': field}
            if len(candidates) != 1:
                g.excluded_fields.append(dict(details, operation='both', reason='Ambiguous field inherited through multiple base paths'))
                continue
            f = candidates[0]
            details.update(declaring_class=f['declaring_class'], cpp=f['type']['cpp'])
            if not (f['public'] or protected_fields.permitted(g, f, name)) or f['removed']:
                g.excluded_fields.append(dict(details, operation='both', reason='Not a public field' if not f['public'] else 'Removed by upstream type system'))
                continue
            static = f['static'] or g.classes[name].get('namespace', False)
            inventory = dict(details, static=static, getter=None, setter=None,
                             array_count=f['type'].get('array_count'))
            for setter in (False, True):
                operation = 'set' if setter else 'get'
                try:
                    enabled = f.get('setter_enabled' if setter else 'getter_enabled', f.get('setter' if setter else 'getter', False))
                    if not enabled:
                        raise ValueError('Accessor disabled by upstream type system')
                    converted = (lazy_values.field_type(g, name, f, setter) or
                                 video_buffers.field_type(g, name, f, setter) or
                                 pointer_fields.field_type(g, name, f, setter) or
                                 aggregate_fields.field_type(g, name, f, setter) or
                                 form_rows.field_type(g, name, f, setter) or
                                 constant_fields.field_type(g, name, f, setter) or
                                 rhi_lifetimes.field_type(g, name, f, setter) or
                                 persistent_storage.field_type(g, name, f, setter) or
                                 protected_fields.field_type(g, name, f, setter))
                    if setter and f['type'].get('const') and not converted:
                        raise ValueError('Const field is read-only')
                    converted = converted or _value_type(g, copy.deepcopy(f['type']), setter)
                    public = name.replace('::', '.') + '.Fields.' + ('set_' if setter else '') + field
                    g.field_bindings.append(dict(details, source=f, type=converted, setter=setter,
                                                 static=static, public=public))
                    inventory['setter' if setter else 'getter'] = public
                except ValueError as error:
                    g.excluded_fields.append(dict(details, operation=operation, reason=str(error)))
            g.public_fields.append(inventory)


def _array_get(t, expression, result, depth=0):
    lines = [f'{t["cpp"]} {result};', f'{result}.reserve({t["field_count"]});']
    index = f'field_index_{depth}'
    lines += [f'for (qsizetype {index} = 0; {index} < {t["field_count"]}; ++{index}) {{']
    child, item = t['children'][0], f'{expression}[{index}]'
    if 'field_count' in child:
        inner = f'field_values_{depth + 1}'
        lines += ['    ' + line for line in _array_get(child, item, inner, depth + 1)]
        item = f'std::move({inner})'
    lines += [f'    {result}.append({item});', '}']
    return lines


def _array_validate(t, values, depth=0):
    lines = [f'if ({values}.size() != {t["field_count"]}) return fail(r, EINVAL, "Fixed field array has the wrong element count");']
    child = t['children'][0]
    if 'field_count' in child:
        index = f'field_check_{depth}'
        lines += [f'for (qsizetype {index} = 0; {index} < {t["field_count"]}; ++{index}) {{']
        lines += ['    ' + line for line in _array_validate(child, f'{values}[{index}]', depth + 1)]
        lines += ['}']
    return lines


def _array_set(t, target, values, depth=0):
    index = f'field_index_{depth}'
    lines = [f'for (qsizetype {index} = 0; {index} < {t["field_count"]}; ++{index}) {{']
    child = t['children'][0]
    if 'field_count' in child:
        lines += ['    ' + line for line in _array_set(child, f'{target}[{index}]', f'{values}[{index}]', depth + 1)]
    else:
        lines += [f'    {target}[{index}] = {values}[{index}];']
    return lines + ['}']


def emit(g):
    prepare(g)
    void = {'kind': 'void', 'bend': 'Unit', 'raw': 'Unit'}
    for field in g.field_bindings:
        name, t, setter = field['class'], field['type'], field['setter']
        params, lines = [], ['NativeCallScope call_scope;']
        if field['static']:
            expression = protected_fields.expression(g, field) or field['declaring_class'] + '::' + field['field']
        else:
            params.append(('self', {'bend': name.replace('::', '.'), 'raw': 'U32'}))
            getter = (f'protected_fields_owner<{name}>(r, r->self, {g.ids[name]}, true)'
                      if protected_fields.setter_uses_owner_view(g, field) else
                      f'get<{name}>(r, r->self, {g.ids[name]}, false, {str(setter).lower()})')
            lines += [f'auto *self = {getter};',
                      'if (r->error) return true;']
            expression = protected_fields.expression(g, field) or 'self->' + field['field']
        if setter:
            params.append(('value', t))
            declarations, argument = g.argument(t, 0)
            lines += declarations + ['if (r->error) return true;']
            lines += converter_cleanup.field_guard(g, field, argument)
            adapted = protected_fields.field_access(g, field, expression, argument)
            if adapted is None:
                adapted = lazy_values.field_access(g, field, expression, argument)
            if adapted is None:
                adapted = video_buffers.field_access(g, field, expression, argument)
            if adapted is None:
                adapted = pointer_fields.field_access(g, field, expression, argument)
            if adapted is None:
                adapted = aggregate_fields.field_access(g, field, expression, argument)
            if adapted is None:
                adapted = form_rows.field_access(g, field, expression, argument)
            if adapted is None:
                adapted = constant_fields.field_access(g, field, expression, argument)
            if adapted is None:
                adapted = rhi_lifetimes.field_access(g, field, expression, argument)
            if adapted is None:
                adapted = persistent_storage.field_access(g, field, expression, argument)
            if adapted is not None:
                lines += adapted
            elif t.get('atomic_field'):
                lines += [f'{expression}.store({argument});']
            elif 'field_count' in t:
                lines += _array_validate(t, '(' + argument + ')')
                lines += _array_set(t, expression, '(' + argument + ')')
            else:
                lines += [f'{expression} = {argument};']
        elif 'field_count' in t:
            lines += _array_get(t, expression, 'field_values')
            lines += g.store_result(t, 'field_values')
        else:
            adapted = protected_fields.field_access(g, field, expression)
            if adapted is None:
                adapted = lazy_values.field_access(g, field, expression)
            if adapted is None:
                adapted = video_buffers.field_access(g, field, expression)
            if adapted is None:
                adapted = pointer_fields.field_access(g, field, expression)
            if adapted is None:
                adapted = aggregate_fields.field_access(g, field, expression)
            if adapted is None:
                adapted = form_rows.field_access(g, field, expression)
            if adapted is None:
                adapted = constant_fields.field_access(g, field, expression)
            if adapted is None:
                adapted = rhi_lifetimes.field_access(g, field, expression)
            if adapted is None:
                adapted = persistent_storage.field_access(g, field, expression)
            lines += adapted if adapted is not None else g.store_result(t, expression + '.load()' if t.get('atomic_field') else expression)
        operation = g.next_id
        g.next_id += 1
        g.cases.append(f'case {operation}: {{\n' + '\n'.join('    ' + line for line in lines) + '\n    return true;\n}')
        g.emit_effect(field['public'], params, void if setter else t, operation, has_self=not field['static'])
