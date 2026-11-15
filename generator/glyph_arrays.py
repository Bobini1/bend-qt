"""Explicit owning alternative to QGlyphRun's externally retained arrays.

Qt setRawData never copies its two input arrays. A Bend list is immutable and
temporary after conversion, so the public Snapshot adapter uses Qt's owning
list setters and commits both arrays together. Copies then use Qt's own shared
storage instead of carrying an untracked external pointer.
"""


def handles(f):
    return f['declaring_class'] == 'QGlyphRun' and f['name'] == 'setRawData'


def parameters(g, f):
    if not handles(f):
        return None
    args = []
    for a in f['arguments'][:2]:
        child = dict(a['type'], pointers=0, const=False, reference=0,
                     cpp=a['type']['name'])
        args.append(g.conversions.container(dict(child, name='QList',
            cpp='QList<' + child['cpp'] + '>', container=True, instantiations=[child]), False))
    args.append(g.type(f['arguments'][2]['type']))
    f['adaptation'] = 'QGlyphRun.setRawDataSnapshot uses owning Qt list storage; external mutable raw-array aliasing is not exposed'
    return args, [dict(type=t, source=i, input=i, output=False, mutable=False) for i,t in enumerate(args)], []


def method_case(g, m):
    if not handles(m['function']):
        return None
    lines = ['NativeCallScope scope;',
             f'auto *self = get<QGlyphRun>(r, r->self, {g.ids["QGlyphRun"]});']
    args = []
    for i,t in enumerate(m['args']):
        before, value = g.argument(t, i)
        lines += before
        args.append(value)
    lines += ['if (r->error) return true;', f'const auto count = {args[2]};',
              'const bool nonnegative = count >= 0;',
              f'const bool glyphs_fit = uint64_t(count) <= uint64_t(({args[0]}).size());',
              f'const bool positions_fit = uint64_t(count) <= uint64_t(({args[1]}).size());',
              'if (!lifetime_paired_array[(unsigned(nonnegative) << 2) | (unsigned(glyphs_fit) << 1) | unsigned(positions_fit)])',
              '    return fail(r, ERANGE, "Glyph and position arrays must both contain the requested count");',
              'QGlyphRun replacement(*self);',
              f'replacement.setGlyphIndexes(({args[0]}).first(count));',
              f'replacement.setPositions(({args[1]}).first(count));',
              'self->swap(replacement);', 'return true;']
    return lines


def limitations(g):
    if 'QGlyphRun' not in g.ids:
        return []
    return [dict(owner='QGlyphRun', signature='setRawData(const quint32*,const QPointF*,int)',
        partial_adapter='QGlyphRun.setRawDataSnapshot',
        supported='Copies both counted inputs into owning Qt lists and commits them together; QGlyphRun copies preserve that storage',
        unsupported='Aliasing externally mutable native arrays after the call',
        behavior='Use the explicitly named snapshot alternative with ordinary immutable Bend lists')]
