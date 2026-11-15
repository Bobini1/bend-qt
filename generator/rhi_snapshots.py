"""Discover bounded immutable RHI descriptor access from native At/Count pairs."""


def count_method(g, f):
    if (not f['declaring_class'].startswith('QRhi') or not f['name'].endswith('At')
            or len(f['arguments']) != 1 or not f['const'] or f['return']['pointers'] != 1
            or not f['return']['const']):
        return None
    count = f['name'][:-2] + 'Count'
    matches = [candidate for candidate in g.inherited(f['declaring_class'])
               if candidate['name'] == count and not candidate['arguments']
               and candidate['public'] and candidate['const']]
    return count if len(matches) == 1 else None


def adapt(g, f):
    count = count_method(g, f)
    if not count:
        return None
    source = f['return']
    converted = g.type(dict(source, cpp=source['name'], const=False, pointers=0, reference=0), result=True)
    return dict(converted, result_conversion='rhi_descriptor_snapshot', rhi_count_method=count)


def before_call(g, m):
    count = m['return'].get('rhi_count_method')
    if not count:
        return []
    _, index = g.argument(m['args'][0], 0)
    return [f'if ({index} < 0 || uint64_t({index}) >= uint64_t(self->{count}()))',
            '    return fail(r, ERANGE, "RHI descriptor index is outside its native extent");']


def alternatives(g):
    """Raw begin/end iterators have a checked count/index traversal equivalent."""
    by_owner = {}
    for method in g.methods:
        if method['return'].get('rhi_count_method'):
            by_owner.setdefault(method['class'], []).append(method)
    for excluded in g.excluded:
        owner = excluded['class']
        if not owner.startswith('QRhi'):
            continue
        functions = [f for f in g.inherited(owner) if f['signature'] == excluded['signature']]
        for f in functions:
            if not f['name'].startswith(('cbegin', 'cend')) or not f['declaring_class'].startswith('QRhi'):
                continue
            matching = [m for m in by_owner.get(owner, [])
                        if m['return'].get('name') == f['return']['name']]
            if len(matching) != 1:
                continue
            method = matching[0]
            count = method['return']['rhi_count_method']
            counters = [m for m in g.methods if m['class'] == owner and m['function']['name'] == count and not m['args']]
            if len(counters) != 1:
                continue
            excluded['alternatives'] = [dict(bend_names=[counters[0]['bend_name'], method['bend_name']],
                behavior='Iterate indices from zero to count, taking owned descriptor snapshots with retained resource dependencies; raw iterator addresses are not exposed.')]
