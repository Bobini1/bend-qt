"""Owning Bend snapshots for the legacy DataVisualization array API.

Qt copies items and adopts heap-allocated rows/arrays. Bend callers pass lists
of owning value handles; none of their storage is surrendered to Qt.
"""
FAMILIES = {
    'QScatterDataProxy': ('QScatterDataItem', None),
    'QBarDataProxy': ('QBarDataItem', 'QBarDataArray'),
    'QSurfaceDataProxy': ('QSurfaceDataItem', 'QSurfaceDataArray'),
}
METHODS = {'array', 'itemAt', 'resetArray', 'addItem', 'addItems', 'insertItem',
           'insertItems', 'setItem', 'setItems', 'addRow', 'addRows', 'insertRow',
           'insertRows', 'setRow', 'setRows'}


def family(owner):
    prefix, separator, name = owner.rpartition('::')
    item, array = FAMILIES[name if separator else owner]
    qualify = lambda value: prefix + '::' + value if prefix and value else value
    return qualify(item), qualify(array)


def handles(g, f):
    owner = f['declaring_class']
    return (owner.rsplit('::', 1)[-1] in FAMILIES and f['name'] in METHODS and not f['user_added']
            and g.classes[owner].get('package') == 'PySide6.QtDataVisualization')


def shape(g, f, t):
    item, array = family(f['declaring_class'])
    if t['name'] == item:
        return 0
    if array and t['name'] == array:
        return 2
    if t['name'] in ('QList', 'QVector') and t.get('instantiations') and t['instantiations'][0]['name'] == item:
        return 1
    return None


def copied(g, f, t):
    depth = shape(g, f, t)
    if depth is None:
        return g.type(t)
    item = family(f['declaring_class'])[0]
    value = g.conversions.register(dict(kind='value', name=item, cpp=item, bend=item.replace('::', '.'), raw='U32'))
    for _ in range(depth):
        value = g.conversions.register(dict(kind='list', name='QList', cpp='QList<' + value['cpp'] + '>',
            children=[value], bend='List<&2, ' + value['bend'] + '>', raw='Wire', codec='List_' + value['codec']))
    return dict(value, native_copy_adoption=True)


def parameters(g, f):
    if not handles(g, f):
        return None
    args = [copied(g, f, a['type']) for a in f['arguments']]
    return args, [dict(type=t, source=i, input=i, output=False, mutable=False) for i, t in enumerate(args)], []


def adapt(g, f):
    if handles(g, f) and f['name'] in ('array', 'itemAt'):
        return copied(g, f, f['return'])
    return None


def method_case(g, m):
    f = m['function']
    if not handles(g, f):
        return None
    owner, method = f['declaring_class'], f['name']
    item, array = family(owner)
    lines = ['NativeCallScope scope;', f'auto *self = get<{owner}>(r, r->self, {g.ids[owner]}, false, {str(not f["const"]).lower()});']
    arguments, transfers = [], []
    for i, t in enumerate(m['args']):
        before, expression = g.argument(t, i)
        lines += before
        arguments.append(expression)
    lines += ['if (r->error) return true;']
    if method in ('insertItem', 'insertItems', 'setItems', 'insertRow', 'insertRows', 'setRow', 'setRows'):
        count = 'rowCount' if array else 'itemCount'
        extent = f'({arguments[1]}).size()' if method.endswith(('Items', 'Rows')) else '1'
        lines += [f'auto start = {arguments[0]}; auto available = self->{count}();',
                  'if (start < 0 || start > available' + (f' || {extent} > available - start' if method.startswith('set') else '') + ')',
                  '    return fail(r, ERANGE, "Data proxy range is outside its array");']
    # Qt's itemAt() and indexed setters use unchecked QList indexing.
    if method in ('itemAt', 'setItem') and arguments:
        if array:
            if f['arguments'][0]['type']['name'] == 'QPoint':
                row, column = f'({arguments[0]}).x()', f'({arguments[0]}).y()'
            else:
                row, column = arguments[:2]
            lines += [f'auto row = {row}; auto column = {column};',
                      'if (row < 0 || row >= self->rowCount() || column < 0 || !self->array()->at(row) || column >= self->array()->at(row)->size())',
                      '    return fail(r, ERANGE, "Data proxy item index is outside its array");']
        else:
            lines += [f'if ({arguments[0]} < 0 || {arguments[0]} >= self->itemCount()) return fail(r, ERANGE, "Data proxy item index is outside its array");']
    for i, argument in enumerate(f['arguments']):
        raw = argument['type']
        depth = shape(g, f, raw)
        if depth == 1 and raw['pointers']:
            lines += [f'auto copied{i} = std::make_unique<QList<{item}>>({arguments[i]});']
            arguments[i] = f'copied{i}.get()'
            transfers.append(f'copied{i}.release();')
        elif depth == 2:
            lines += [f'std::vector<std::unique_ptr<QList<{item}>>> rows{i};',
                      f'auto copied{i} = std::make_unique<{array}>();',
                      f'rows{i}.reserve(({arguments[i]}).size()); copied{i}->reserve(({arguments[i]}).size());',
                      f'for (const auto &row : {arguments[i]}) {{',
                      f'    rows{i}.push_back(std::make_unique<QList<{item}>>(row));',
                      f'    copied{i}->append(rows{i}.back().get());', '}',
                      ]
            arguments[i] = f'copied{i}.get()' if raw['pointers'] else f'*copied{i}'
            transfers.append(f'for (auto &row : rows{i}) row.release();')
            if raw['pointers']:
                transfers.append(f'copied{i}.release();')
    call = f'self->{method}({", ".join(arguments)})'
    ret = m.get('native_return', m['return'])
    if method == 'array' and array:
        lines += [f'{ret["cpp"]} snapshot;', 'if (const auto *data = self->array()) {',
                  '    snapshot.reserve(data->size());',
                  f'    for (const auto *row : *data) snapshot.append(row ? *row : QList<{item}>{{}});', '}']
        lines += g.store_result(ret, 'snapshot')
    elif method in ('array', 'itemAt'):
        lines += [f'const auto *value = {call};', 'if (!value) return fail(r, ENOENT, "Data proxy returned no data");']
        lines += g.store_result(ret, '*value')
    elif ret['kind'] == 'void':
        lines += [call + ';', *transfers]
    else:
        lines += [f'auto returned = {call};', *transfers]
        lines += g.store_result(ret, 'returned')
    return lines + ['return true;']
