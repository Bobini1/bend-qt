"""Typed QDataStream values matching the pinned PySide stream conveniences.

Each named width calls its actual C++ streaming overload. Native byte order,
floating-point precision, transaction state and status reporting stay with Qt.
"""


VALUES = (
    ('Bool', 'bool'), ('Int8', 'qint8'), ('UInt8', 'quint8'),
    ('Int16', 'qint16'), ('UInt16', 'quint16'),
    ('Int32', 'qint32'), ('UInt32', 'quint32'),
    ('Int64', 'qint64'), ('UInt64', 'quint64'),
    ('Float', 'float'), ('Double', 'double'),
    ('String', 'QString'), ('QString', 'QString'), ('QChar', 'QChar'),
    ('QStringList', 'QStringList'), ('QVariant', 'QVariant'),
)


def prepare(g):
    g.data_stream_values = []
    if 'QDataStream' not in g.ids:
        return
    for suffix, native in VALUES:
        if native == 'QVariant' and 'QVariant' not in g.ids:
            continue
        source = dict(name=native, cpp=native, const=False, pointers=0, reference=0,
                      container=False, enum=False, flags=False, instantiations=[])
        value = g.conversions.register(g.type(source))
        g.data_stream_values.append((suffix, native, value))


def emit(g):
    entries = getattr(g, 'data_stream_values', ())
    if not entries:
        return
    stream = dict(kind='object', name='QDataStream', bend='QDataStream', raw='U32')
    unit = dict(kind='void', bend='Unit', raw='Unit')
    g.data_stream_operations = {}
    for suffix, native, value in entries:
        for reading in (True, False):
            name = 'QDataStream.' + ('read' if reading else 'write') + suffix
            if any(method['bend_name'] == name for method in g.methods):
                raise ValueError('Native method conflicts with typed data stream operation: ' + name)
            operation = g.next_id
            g.next_id += 1
            g.data_stream_operations[name] = operation
            lines = ['NativeCallScope scope;',
                     f'auto *self = get<QDataStream>(r, r->self, {g.ids["QDataStream"]});',
                     'if (r->error) return true;']
            if reading:
                lines += [f'{native} value{{}};', '*self >> value;']
                lines += g.store_result(value, 'value')
            else:
                declarations, expression = g.argument(value, 0)
                lines += [*declarations, 'if (r->error) return true;', f'*self << {expression};']
            lines.append('return true;')
            g.cases.append(f'case {operation}: {{\n' + '\n'.join('    ' + line for line in lines) + '\n}')
            g.emit_effect(name, [('self', stream)] + ([] if reading else [('value', value)]),
                          value if reading else unit, operation, has_self=True)
    for excluded in g.excluded:
        if excluded['class'] != 'QDataStream':
            continue
        name = 'QDataStream.' + excluded['signature'].split('(', 1)[0]
        if name not in g.data_stream_operations:
            continue
        excluded.setdefault('alternatives', []).append(dict(
            bend_name=name, contract='typed_data_stream_value',
            reason='Calls the exact Qt stream overload with owning outputs; Qt retains byte order, precision, transaction and status semantics'))


def inventory(g):
    return dict(available=bool(getattr(g, 'data_stream_values', ())),
                operations=getattr(g, 'data_stream_operations', {}),
                values={suffix: dict(native=native, bend=value['bend'])
                        for suffix, native, value in getattr(g, 'data_stream_values', ())},
                contract='Read/write exact native widths; Qt status and transaction semantics are unchanged; narrow input ranges are checked before stream mutation')
