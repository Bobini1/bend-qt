"""QByteArray positions with checked ownership, bounds and storage generation."""
from pathlib import Path

METHODS = {'begin', 'end', 'cbegin', 'cend', 'constBegin', 'constEnd', 'erase'}


def handles(f):
    return f['declaring_class'] == 'QByteArray' and f['name'] in METHODS


def install(classes, selected):
    if 'QByteArray' not in selected:
        return
    name = 'QByteArrayIterator'
    classes[name] = dict(name=name, object=False, value=True, qobject=False, copyable=False,
        public_destructor=True, abstract=False, namespace=False, generate=False, template=False,
        bases=[], functions=[], enums=[], adapter=True)
    selected.append(name)


def aliases(g, inside):
    if 'QByteArrayIterator' not in g.ids:
        return ''
    return ('struct QByteArrayIterator { uint32_t owner; qsizetype offset; QByteArray storage; bool writable; };\n'
            if inside else 'namespace bendqt { struct QByteArrayIterator; }\n')


def handle():
    return dict(kind='value', name='QByteArrayIterator', cpp='QByteArrayIterator', bend='QByteArrayIterator', raw='U32')


def adapt(g, f):
    return handle() if handles(f) else None


def parameters(g, f):
    if not handles(f):
        return None
    args = [handle() for _ in f['arguments']]
    return args, [dict(type=t, source=i, input=i, output=False, mutable=False) for i, t in enumerate(args)], []


def method_case(g, m):
    f = m['function']
    if not handles(f):
        return None
    lines = ['NativeCallScope scope;',
             f'auto *self = get<QByteArray>(r, r->self, {g.ids["QByteArray"]}, false, {str(not f["const"]).lower()});',
             'if (r->error) return true;']
    if f['name'] == 'erase':
        for i in range(len(m['args'])):
            lines += [f'auto *it{i} = get<QByteArrayIterator>(r, r->arguments[{i}].word, {g.ids["QByteArrayIterator"]}, false, false);',
                      f'if (r->error || !byte_iterator_source(r, *it{i}, false)) return true;',
                      f'if (it{i}->owner != r->self) return fail(r, EXDEV, "QByteArray erase iterator belongs to another array");']
        last = 'it1->offset' if len(m['args']) == 2 else 'it0->offset + 1'
        lines += ['auto first = it0->offset;', f'auto last = {last};',
                  'if (first > last || last > self->size()) return fail(r, ERANGE, "QByteArray erase range is outside the array");',
                  'self->remove(first, last - first);',
                  'r->result.word = new_byte_iterator(r, r->self, first, true);']
    else:
        offset = 'self->size()' if f['name'].lower().endswith('end') else '0'
        lines += [f'r->result.word = new_byte_iterator(r, r->self, {offset}, {str(not f["const"]).lower()});']
    return lines + ['r->result.owned_handle = r->result.word;', 'return true;']


def emit(g):
    if 'QByteArrayIterator' not in g.ids:
        return
    integer = dict(kind='i64', bend='Int64', raw='U32 & U32', cpp='qint64')
    word = dict(kind='u32', bend='U32', raw='U32', cpp='uint')
    unit = dict(kind='void', bend='Unit', raw='Unit', cpp='void')
    for name, args, result, code in [
        ('position', [], integer, ['r->result = wide_value(uint64_t(value->offset));']),
        ('advance', [('distance', integer)], handle(), [
            'auto distance = int64_t(wide_bits(r->arguments[0]));',
            'if (distance < -value->offset || distance > source->size() - value->offset) return fail(r, ERANGE, "QByteArray iterator displacement exceeds the array");',
            'r->result.word = new_byte_iterator(r, value->owner, value->offset + distance, value->writable);',
            'r->result.owned_handle = r->result.word;']),
        ('read', [], word, ['if (value->offset == source->size()) return fail(r, ERANGE, "Cannot read the QByteArray end iterator");',
                           'r->result.word = uchar(source->at(value->offset));']),
        ('write', [('byte', word)], unit, [
            'if (!value->writable) return fail(r, EPERM, "QByteArray iterator is const");',
            'if (value->offset == source->size() || r->arguments[0].word > 255) return fail(r, ERANGE, "QByteArray iterator write exceeds its byte range");',
            '(*source)[value->offset] = char(r->arguments[0].word);',
            'value->storage = *source;']),
    ]:
        operation = g.next_id; g.next_id += 1
        lines = ['NativeCallScope scope;', f'auto *value = get<QByteArrayIterator>(r, r->self, {g.ids["QByteArrayIterator"]});',
                 'if (r->error) return true;', f'auto *source = byte_iterator_source(r, *value, {str(name == "write").lower()});',
                 'if (r->error) return true;'] + code + ['return true;']
        g.cases.append(f'case {operation}: {{\n' + '\n'.join('    ' + line for line in lines) + '\n}')
        g.emit_effect('QByteArrayIterator.' + name, [('self', handle())] + args, result, operation, has_self=True)


def cpp(g):
    if 'QByteArrayIterator' not in g.ids:
        return ''
    return (Path(__file__).with_name('templates').joinpath('byte_iterators.cpp').read_text()
            .replace('@ARRAY@', str(g.ids['QByteArray'])).replace('@ITERATOR@', str(g.ids['QByteArrayIterator'])))
