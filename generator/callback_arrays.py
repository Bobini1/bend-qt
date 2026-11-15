"""Copies for reverse array arguments with audited native extents."""


def argument(g, function, index, argument):
    import buffers
    policies, _ = buffers.policies(function)
    policy = policies.get(index, {})
    # PySide removes redundant count parameters after converting an array to
    # a Python sequence. The native virtual still has that scalar parameter.
    # Restore exactly the extents belonging to the audited read-only arrays.
    if argument.get('removed'):
        for source_index, source_policy in policies.items():
            source_argument = function['arguments'][source_index]
            graphics = (function['declaring_class'], function['name']) == ('QGraphicsView', 'drawItems')
            if (source_policy.get('count_source') == index and not source_policy.get('bytes')
                    and not source_policy.get('writable') and not source_policy.get('writable_array')
                    and (graphics or source_argument['type'].get('const'))):
                return g.conversions.register(g.type(argument['type']))
    if ('count_source' not in policy or policy.get('bytes') or policy.get('writable')
            or policy.get('writable_array')):
        return None
    source = argument['type']
    graphics = (function['declaring_class'], function['name']) == ('QGraphicsView', 'drawItems')
    if not graphics and not source.get('const'):
        return None
    if source.get('array') and source.get('array_element'):
        child = dict(source['array_element'])
    elif source['pointers']:
        child = dict(source, pointers=source['pointers'] - 1,
                     cpp=source['cpp'].rstrip().removesuffix('*').strip())
    else:
        return None
    child.update(const=False, reference=0, cpp=child['cpp'].removeprefix('const ').strip())
    converted = g.type(child)
    if converted['kind'] == 'value' and not g.classes[converted['name']].get('copyable'):
        raise ValueError('A reverse array element needs a copyable value or guarded identity')
    value = g.conversions.container(dict(name='QList', cpp='QList<' + child['cpp'] + '>',
        pointers=0, reference=0, const=False, container=True, instantiations=[child],
        enum=False, flags=False), False)
    return dict(value, callback_array_count=policy['count_source'],
                callback_array_multiplier=policy.get('multiplier', 1))


def encode(g, index, value, has_result):
    count = f'a{value["callback_array_count"]}'
    multiplier = value['callback_array_multiplier']
    child = value['children'][0]
    done = 'return {};' if has_result else 'return;'
    lines = [f'        if ({count} < 0 || uint64_t({count}) > uint64_t(INT_MAX) / {multiplier} || (!a{index} && {count})) {{',
             f'            callback_report_error(ERANGE, "Native array extent is invalid"); {done}', '        }',
             f'        const size_t array_count{index} = size_t({count}) * {multiplier};',
             f'        arguments.value.items[{index}] = sequence_value(array_count{index});',
             f'        for (size_t n = 0; n < array_count{index}; ++n) {{']
    if child['kind'] == 'object' and not g.classes[child['name']]['qobject']:
        lines += [f'            arguments.value.items[{index}].items[n] = native_arguments.borrow_argument(&conversion, a{index}[n], {g.ids[child["name"]]}, bqt_receiver);']
    else:
        lines += [f'            arguments.value.items[{index}].items[n] = write_{child["native_codec"]}(&conversion, native_owned_snapshot(a{index}[n]));']
    lines += ['            if (conversion.error) break;', '        }']
    return lines
