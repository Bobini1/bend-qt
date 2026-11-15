"""Owning snapshot adaptations for APIs that otherwise retain raw byte pointers.

Bend has no stable raw allocation token. These overloads therefore copy the
requested prefix into Qt-owned storage, preserving the source lifetime across
value copies, mutation and asynchronous use without hidden pinning requirements.
"""


def handles(f):
    owner, name = f['declaring_class'], f['name']
    return (len(f['arguments']) == 2 and
            ((owner == 'QByteArray' and name in ('fromRawData', 'setRawData')) or
             (owner == 'QCborStreamReader' and f['constructor'])) and
            f['arguments'][0]['type']['pointers'] == 1 and
            f['arguments'][0]['type']['const'] and
            f['arguments'][0]['type']['name'] in ('char', 'quint8', 'uchar', 'unsigned char'))


def parameters(g, f):
    if not handles(f):
        return None
    array = dict(kind='value', name='QByteArray', cpp='const QByteArray &',
                 bend='QByteArray', raw='U32', retained_bytes_snapshot=True)
    args = [array, g.type(f['arguments'][1]['type'])]
    return args, [dict(type=t, source=i, input=i, output=False, mutable=False)
                  for i, t in enumerate(args)], []


def method_case(g, m):
    f = m['function']
    if not handles(f):
        return None
    lines = ['NativeCallScope call_scope;']
    if not f['static'] and not f['constructor']:
        lines += [f'auto *self = get<QByteArray>(r, r->self, {g.ids["QByteArray"]});']
    lines += [f'auto *source = get<QByteArray>(r, r->arguments[0].word, {g.ids["QByteArray"]}, false, false);',
              'if (r->error) return true;',
              f'auto count = {g.argument(m["args"][1], 1)[1]};',
              'if (count < 0 || uint64_t(count) > uint64_t(source->size()))',
              '    return fail(r, ERANGE, "Retained byte snapshot exceeds the source extent");',
              'QByteArray snapshot(source->constData(), qsizetype(count));']
    if f['declaring_class'] == 'QCborStreamReader':
        lines += [f'r->result.word = own(r, new QCborStreamReader(snapshot), {g.ids["QCborStreamReader"]});',
                  'r->result.owned_handle = r->result.word;']
    else:
        value = 'std::move(snapshot)'
        if f['name'] == 'setRawData':
            lines += ['*self = std::move(snapshot);']
            value = '*self'
        lines += g.store_result(m.get('native_return', m['return']), value)
    return lines + ['return true;']
