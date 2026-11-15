"""Audited call-duration value pointers and bounded NMEA parser input."""
from adapters import VALUE_POINTER_CALLS


def contract(f):
    value = dict(VALUE_POINTER_CALLS.get((f['declaring_class'], f['name']), {}))
    if (f['declaring_class'], f['name']) == ('QNmeaPositionInfoSource', 'parsePosInfoFromNmeaData'):
        for index, argument in enumerate(f['arguments']):
            if argument['type']['name'] == 'QGeoPositionInfo': value[index] = ('QGeoPositionInfo', False)
    return value


def nmea(f):
    return ((f['declaring_class'], f['name']) in {
        ('QNmeaPositionInfoSource', 'parsePosInfoFromNmeaData'),
        ('QNmeaSatelliteInfoSource', 'parseSatelliteInfoFromNmea'),
        ('QNmeaSatelliteInfoSource', 'parseSatellitesInUseFromNmea')})


def handles(f):
    return bool(contract(f)) or nmea(f)


def parameters(g, f):
    pointers = contract(f)
    if not pointers and not nmea(f): return None
    args, plan, outputs = [], [], []
    for index, argument in enumerate(f['arguments']):
        source = argument['type']
        output = nmea(f) and source['name'] == 'bool' and source['pointers'] == 1
        if index in pointers:
            expected, nullable = pointers[index]
            if source['name'] != expected or source['pointers'] != 1 or source['reference']:
                raise ValueError('The audited value-pointer signature changed')
            value = g.type(dict(source, cpp=source['name'], const=False, pointers=0, reference=0))
            value = dict(value, cpp=source['cpp'], pointer=True, native_const=bool(source['const']),
                         required_pointer=not nullable, call_duration_value_pointer=True)
            if expected == 'QQuickItem::UpdatePaintNodeData':
                # Qt supplies this as an input, despite the non-const pointer.
                # Its checked callback copy may already be pinned by the outer
                # render callback; forward an independent call-local copy.
                value.update(native_const=True, render_input_copy=True)
        elif nmea(f) and index == 0:
            if not ((source['name'] == 'char' and source['pointers'] == 1 and source['const'])
                    or source['name'] == 'QByteArrayView'):
                raise ValueError('The audited NMEA byte-input signature changed')
            value = dict(kind='value', name='QByteArray', bend='QByteArray', raw='U32', cpp='QByteArray',
                         pointer=False, nmea_bytes=True, nmea_view=source['name'] == 'QByteArrayView')
        elif output:
            value = g.type(dict(source, cpp=source['name'], pointers=0, reference=0))
        elif argument.get('removed'):
            raise ValueError('An audited value-pointer call has another removed argument')
        else:
            value = g.type(source)
        mutable = (source['reference'] == 1 and not source['const'] and value['kind'] not in ('object', 'value'))
        item = dict(type=value, source=index, input=None if output else len(args), output=output, mutable=mutable)
        if not output: args.append(value)
        if output or mutable:
            g.conversions.register(value); outputs.append(item)
        plan.append(item)
    return args, plan, outputs


def before_call(g, m):
    if not handles(m['function']): return []
    lines = []
    if (m['function']['declaring_class'], m['function']['name']) == ('QQuickItem', 'updatePaintNode'):
        lines += ['if (!gui_render_depth) return fail(r, EPERM, "updatePaintNode requires an active GUI render callback");']
    for index, value in enumerate(m['args']):
        if value.get('render_input_copy'):
            lines += [f'{value["name"]} native_render_data{index}(*a{index});',
                      f'a{index} = &native_render_data{index};']
        if value.get('call_duration_value_pointer') and not value.get('native_const'):
            lines += [f'if (r->arguments[{index}].word && entry(r->arguments[{index}].word)->active_calls > 1)',
                      '    return fail(r, EBUSY, "The output value is in another active native call");']
        if value.get('nmea_bytes') and not value.get('nmea_view'):
            length = g.argument(m['args'][index + 1], index + 1)[1]
            lines += [f'if ({length} < 0 || uint64_t({length}) > uint64_t(a{index}->size()))',
                      '    return fail(r, ERANGE, "NMEA input length exceeds its owned byte storage");']
    return lines


def call_arguments(f, arguments):
    if not nmea(f): return arguments
    values = list(arguments)
    if f['arguments'][0]['type']['name'] == 'QByteArrayView': values[0] = 'QByteArrayView(' + values[0] + ')'
    else: values[0] = '(' + values[0] + ').constData()'
    return values


def after_call(g, m):
    if not handles(m['function']): return []
    return [f'if (r->arguments[{index}].word && !finish_aggregate_ownership(r, r->arguments[{index}].word)) return true;'
            for index, value in enumerate(m['args']) if value.get('call_duration_value_pointer') and not value.get('native_const')]


def inventory(g):
    return dict(methods=sorted({m['function']['declaring_class'] + '::' + m['function']['minimal_signature']
        for m in g.methods if handles(m['function'])}),
        contract='Checked value handles borrowed synchronously; mutable fields recapture their value dependencies after the call',
        nmea='Owned QByteArray input, checked explicit byte counts for legacy overloads, returned scalar/container outputs',
        rendering='updatePaintNode accepts only live render-callback data inside the active GUI render scope')
