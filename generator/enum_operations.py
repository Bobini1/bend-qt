"""Bit operations on the enums that Qt combines into QFlags.

As in PySide, a QFlags<E> parameter takes E itself, and a value of E may hold
several flags. Inside `(a .|. b : E)`, Bend's `.|.`, `.&.` and `.^.` call
`E.or`, `E.and` and `E.xor`. `E.without(value, flags)` clears flags, and
`E.has(value, flag)` is Qt's testFlag: a zero flag is set only in a zero value.
"""

OPERATIONS = ('or', 'and', 'xor', 'without', 'has')


def lines(name, wide, values):
    clash = sorted(set(OPERATIONS) & set(values))
    if clash:
        raise ValueError(f'Enum {name} has values named like its flag operations: {clash}')
    t = name
    out = []
    if wide:
        for op, word in (('or', 'U32.or({x}, {y})'), ('and', 'U32.and({x}, {y})'),
                         ('xor', 'U32.xor({x}, {y})'), ('without', 'U32.and({x}, U32.not({y}))')):
            out += [f'def {t}.{op}(a: {t}, b: {t}) -> {t}:', '  match a b:',
                    f'    case {t}{{al, ah}} {t}{{bl, bh}}: {t}{{{word.format(x="al", y="bl")}, {word.format(x="ah", y="bh")}}}', '']
        out += [f'def {t}.has(+value: {t}, +flag: {t}) -> Bool:',
                f'  (U32.is_eq(U32.and({t}.lo(value), {t}.lo(flag)), {t}.lo(flag))'
                f' && U32.is_eq(U32.and({t}.hi(value), {t}.hi(flag)), {t}.hi(flag))'
                f' && (U32.is_ne({t}.lo(flag), 0) || U32.is_ne({t}.hi(flag), 0)'
                f' || (U32.is_eq({t}.lo(value), 0) && U32.is_eq({t}.hi(value), 0))))', '']
        return out
    for op, word in (('or', 'U32.or(x, y)'), ('and', 'U32.and(x, y)'),
                     ('xor', 'U32.xor(x, y)'), ('without', 'U32.and(x, U32.not(y))')):
        out += [f'def {t}.{op}(a: {t}, b: {t}) -> {t}:', '  match a b:',
                f'    case {t}{{x}} {t}{{y}}: {t}{{{word}}}', '']
    out += [f'def {t}.has(+value: {t}, +flag: {t}) -> Bool:',
            f'  U32.is_eq(U32.and({t}.word(value), {t}.word(flag)), {t}.word(flag))'
            f' && (U32.is_ne({t}.word(flag), 0) || U32.is_eq({t}.word(value), 0))', '']
    return out
