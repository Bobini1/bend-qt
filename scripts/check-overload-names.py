#!/usr/bin/env python3
"""Overload naming rules, the name lock, and the generated package's names.

The synthetic cases exercise generator/overload_names.py directly: merging,
C++ name hiding, default variants, C++-spelled disambiguation, removed-name
tombstones and carry-over. The package section checks the committed lock
against coverage.json. It needs no Qt installation.
"""
from collections import Counter
import json
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
import overload_names as names

OUT = ROOT / 'build/qt612/check/overload-names'


def cpp_type(cpp, name, pointers=0):
    return dict(cpp=cpp, name=name, pointers=pointers)


def function(owner, name, params, *, const=False, impl=None, static=False, constructor=False, signal=False):
    signature = f'{name}({", ".join(cpp for cpp, *_ in params)})' + (' const' if const else '')
    return dict(name=name, declaring_class=owner, implementing_class=impl or owner, const=const, static=static,
                constructor=constructor, signal=signal, operator=False, free_operator=None,
                signature=signature, minimal_signature=signature.replace(' ', ''), source_signatures=[signature],
                arguments=[dict(type=cpp_type(cpp, base, ptr), native_default=default)
                           for cpp, base, ptr, _, default in params])


def entry(receiver, f, ret='Unit', count=None):
    params = f['arguments'] if count is None else f['arguments'][:count]
    bend = [p['bend'] for p in PARAMS[id(f)]][:len(params)]
    plan = [dict(input=i, source=i, type=dict(bend=b, rvalue='&&' in f['arguments'][i]['type']['cpp']))
            for i, b in enumerate(bend)]
    m = {'class': receiver, 'function': f, 'args': [{'bend': b} for b in bend], 'return': {'bend': ret},
         'parameters': plan, 'default_constructor': False}
    if count is not None:
        m['omitted_defaults'] = [a['native_default'] for a in f['arguments'][count:]]
    return m


PARAMS = {}


def fn(owner, name, params, **options):
    """params: (cpp, base type, pointers, Bend type, native default)."""
    f = function(owner, name, params, **options)
    PARAMS[id(f)] = [dict(bend=bend) for _, _, _, bend, _ in params]
    return f


class FakeGenerator:
    def __init__(self, methods, bases=None, unbound=None):
        self.methods = methods
        self.bases = bases or {}
        self.classes = {name: {} for name in set(self.bases) | {b for v in self.bases.values() for b in v}}
        self.unbound_overloads = Counter(unbound or {})
        self.excluded_identities = {}

    def all_bases(self, name):
        found = set()
        for base in self.bases.get(name, []):
            found |= {base} | set(self.all_bases(base))
        return sorted(found)

    @staticmethod
    def base_name(m):
        f = m['function']
        return 'new' if f['constructor'] else f['name']


def run(methods, lock=None, **options):
    g = FakeGenerator(methods, **options)
    lock = lock or names.NameLock()
    names.assign(g, lock)
    names.finalize(g, lock)
    return g, lock, {m['function']['signature'] + (f' /{len(m["args"])}' if 'omitted_defaults' in m else ''): m['bend_name']
                     for m in g.methods}


def expect(condition, message):
    if not condition:
        raise AssertionError(message)


def raises(action, kind, text):
    try:
        action()
    except kind as error:
        expect(text in str(error), f'Unexpected error: {error}')
        return
    raise AssertionError(f'Expected {kind.__name__}: {text}')


STRING = [('const QString &', 'QString', 0, 'String', '')]


def synthetic():
    cases = []
    # Bare name, suffixed overloads, zero-argument entry and default variant.
    size = fn('QFoo', 'size', [])
    resize = fn('QFoo', 'resize', [('int', 'int', 0, 'Int32', ''), ('int', 'int', 0, 'Int32', '0')])
    find = fn('QFoo', 'find', STRING)
    find_char = fn('QFoo', 'find', [('char', 'char', 0, 'Int32', '')])
    find_none = fn('QFoo', 'find', [])
    _, _, got = run([entry('QFoo', size, 'Int32'), entry('QFoo', resize), entry('QFoo', resize, count=1),
                     entry('QFoo', find, 'Bool'), entry('QFoo', find_char, 'Bool'), entry('QFoo', find_none, 'Bool')])
    expect(got['size()'] == 'QFoo.size', got)
    expect(got['resize(int, int)'] == 'QFoo.resize__Int32_Int32' and got['resize(int, int) /1'] == 'QFoo.resize__Int32', got)
    expect(got['find(const QString &)'] == 'QFoo.find__String' and got['find()'] == 'QFoo.find', got)
    cases.append('bare, Bend-typed and own-argument variant names')

    # A native signal is a Signal declaration named like the signal, with its
    # own lock identity. Overloads spell their Bend arguments; connectors of
    # the earlier design are tombstoned with their replacement named.
    def declaration(owner, f):
        m = entry(owner, f, 'Signal')
        m['signal_args'], m['args'], m['signal'] = m['args'], [], dict(args=[])
        return m
    INT = ('int', 'int', 0, 'Int32', '')
    changed = fn('QSlider', 'rangeChanged', [INT, INT], signal=True)
    connect_key = 'connect-signal ' + names.native_operators.identity(changed)
    old_lock = names.NameLock(names={'QSlider': {connect_key: ('QSlider.connect_rangeChanged', 'self (Int32, Int32) -> Connection')}})
    g, lock, got = run([declaration('QSlider', changed)], old_lock)
    expect(got == {changed['signature']: 'QSlider.rangeChanged'}, got)
    expect(list(lock.names['QSlider']) == ['signal-descriptor rangeChanged(int,int)'], lock.names['QSlider'])
    expect(lock.removed['QSlider'][connect_key]['reason'] == 'Replaced by Signal.connect and the signal declaration', lock.removed)
    activated = [fn('QCompleter', 'activated', STRING, signal=True),
                 fn('QCompleter', 'activated', [('const QModelIndex &', 'QModelIndex', 0, 'QModelIndex', '')], signal=True)]
    _, _, got = run([declaration('QCompleter', f) for f in activated])
    expect(set(got.values()) == {'QCompleter.activated__String', 'QCompleter.activated__QModelIndex'}, got)
    cases.append('signal declarations: names, overloads and replaced connectors')

    # QFlags<E> and E share E's Bend type. A name spelling the retired flags
    # type is tombstoned and assigned again; names without it stay pinned.
    def aligned(owner, name, enum, flags, **options):
        f = fn(owner, name, [(f'QFlags<{enum}>' if flags else enum, enum, 0, 'Qt.AlignmentFlag', '')], **options)
        f['arguments'][0]['type'].update(enum=not flags, flags=flags)
        return f
    paint = aligned('QIcon', 'paint', 'Qt::AlignmentFlag', True)
    getter = fn('QLabel', 'alignment', [], const=True)
    old = names.NameLock(names={
        'QIcon': {names.key(entry('QIcon', paint)): ('QIcon.paint__Flags_Qt__AlignmentFlag', 'self (Flags_Qt__AlignmentFlag) -> Unit')},
        'QLabel': {names.key(entry('QLabel', getter)): ('QLabel.alignment', 'self () -> Flags_Qt__AlignmentFlag')}})
    _, lock, got = run([entry('QIcon', paint), entry('QLabel', getter, 'Qt.AlignmentFlag')], old)
    expect(got == {paint['signature']: 'QIcon.paint', getter['signature']: 'QLabel.alignment'}, got)
    expect(lock.unacknowledged() == [('QIcon', 'QIcon.paint__Flags_Qt__AlignmentFlag')], lock.removed)
    expect(lock.removed['QIcon'][names.key(entry('QIcon', paint)) + ' /renamed']['reason'] ==
           'Renamed: the Bend type Flags_Qt__AlignmentFlag no longer exists', lock.removed)
    expect(lock.reshaped and lock.names['QLabel'][names.key(entry('QLabel', getter))] ==
           ('QLabel.alignment', 'self () -> Qt.AlignmentFlag'), lock.names)
    _, again, got = run([entry('QIcon', paint), entry('QLabel', getter, 'Qt.AlignmentFlag')], lock)
    expect(got[paint['signature']] == 'QIcon.paint' and len(again.unacknowledged()) == 1, (got, again.removed))
    single, combined = (aligned('QItem', 'setTextAlignment', 'Qt::AlignmentFlag', flags) for flags in (False, True))
    g, _, got = run([entry('QItem', single), entry('QItem', combined)])
    expect(list(got) == [combined['signature']] and g.merged_overloads[0]['signature'] == single['signature'], got)
    cases.append('flags share their enum type: stale names renamed, QFlags overloads preferred')

    # Bend-equivalent overloads collapse to the owning const-reference form.
    variants = [fn('QFoo', 'setText', [(cpp, base, ptr, 'String', '')])
                for cpp, base, ptr in (('const char *', 'char', 1), ('QString &&', 'QString', 0),
                                       ('QAnyStringView', 'QAnyStringView', 0), ('const QString &', 'QString', 0))]
    g, _, got = run([entry('QFoo', f) for f in variants])
    expect(list(got.items()) == [('setText(const QString &)', 'QFoo.setText')], got)
    expect(len(g.merged_overloads) == 3 and {m['bend_name'] for m in g.merged_overloads} == {'QFoo.setText'}, g.merged_overloads)
    narrow, wide = (fn('QFoo', 'scale', [(cpp, cpp, 0, 'F64', '')]) for cpp in ('float', 'double'))
    _, _, got = run([entry('QFoo', narrow), entry('QFoo', wide)])
    expect(list(got) == ['scale(double)'], got)
    mutable, readonly = fn('QFoo', 'at', [], const=False), fn('QFoo', 'at', [], const=True)
    _, _, got = run([entry('QFoo', readonly, 'Int32'), entry('QFoo', mutable, 'Int32')])
    expect(list(got) == ['at()'], got)
    cases.append('merging prefers owning, wide and non-const overloads')

    # C++ name hiding by a subclass declaration, including a default variant.
    inherited = fn('QBase', 'update', [])
    derived = fn('QBase', 'update', [('const QRect &', 'QRect', 0, 'QRect', 'QRect()')], impl='QDerived')
    g, _, got = run([entry('QDerived', inherited), entry('QDerived', derived), entry('QDerived', derived, count=0)],
                    bases={'QDerived': ['QBase']})
    expect(got == {'update(const QRect &)': 'QDerived.update__QRect', 'update(const QRect &) /0': 'QDerived.update'}, got)
    expect(g.merged_overloads[0]['reason'].startswith('Hidden'), g.merged_overloads)
    cases.append('derived declarations hide base overloads')

    # Same inputs, different results: variant yields, then C++ spelling.
    full = fn('QDoc', 'setContent', STRING + [('QString *', 'QString', 1, 'String', '')])
    full['arguments'][1]['type']['cpp'] = 'QString *'
    PARAMS[id(full)] = PARAMS[id(full)][:1]
    newer = fn('QDoc', 'setContent', STRING + [('ParseOptions', 'ParseOptions', 0, 'Flags', 'Default')])
    wide_out = fn('QStream', 'readBytes', [('qint64 &', 'qint64', 0, 'Int64', '')])
    narrow_out = fn('QStream', 'readBytes', [('uint &', 'uint', 0, 'U32', '')])
    PARAMS[id(wide_out)] = PARAMS[id(narrow_out)] = []
    g, _, got = run([entry('QDoc', full, 'Outputs'), entry('QDoc', newer, 'Result'), entry('QDoc', newer, 'Result', count=1),
                     entry('QStream', wide_out, 'Int64'), entry('QStream', narrow_out, 'U32')])
    expect(got['setContent(const QString &, QString *)'] == 'QDoc.setContent__String', got)
    expect(got['setContent(const QString &, ParseOptions)'] == 'QDoc.setContent__String_Flags', got)
    expect('setContent(const QString &, ParseOptions) /1' not in got, got)
    expect(got['readBytes(qint64 &)'] == 'QStream.readBytes__qint64' and got['readBytes(uint &)'] == 'QStream.readBytes__uint', got)
    cases.append('default variants yield; remaining collisions spell C++ types')

    published = fn('QHeader', 'resize', [('int', 'int', 0, 'Int32', '')])
    added = fn('QHeader', 'resize', [])
    _, pinned, _ = run([entry('QHeader', published)])
    _, pinned, got = run([entry('QHeader', published), entry('QHeader', added)], lock=pinned)
    expect(got['resize(int)'] == 'QHeader.resize' and got['resize()'] == 'QHeader.resize__NoArgs', got)
    # A locked one-argument form must not erase a newly usable default call.
    defaulted = fn('QDefault', 'resize', [('int', 'int', 0, 'Int32', '1')])
    _, pinned, _ = run([entry('QDefault', defaulted)])
    _, _, got = run([entry('QDefault', defaulted), entry('QDefault', defaulted, count=0)], lock=pinned)
    expect(got['resize(int) /0'] == 'QDefault.resize__NoArgs', got)
    cases.append('new parameterless calls preserve published overload names')

    array = fn('QEngine', 'draw', [('const QRect *', 'QRect', 1, 'QRect', '')])
    _, pinned, _ = run([entry('QEngine', array)])
    PARAMS[id(array)] = [dict(bend='List<&2, QRect>')]
    _, pinned, got = run([entry('QEngine', array)], lock=pinned)
    expect(got[array['signature']] == 'QEngine.draw', got)
    expect(pinned.names['QEngine'][names.key(entry('QEngine', array))][1].endswith(' -> Unit')
           and 'List<&2, QRect>' in pinned.names['QEngine'][names.key(entry('QEngine', array))][1], pinned.names)
    expect(len(pinned.reshaped) == 1, pinned.reshaped)
    cases.append('corrected conversions refresh locked shapes while preserving native names')

    # An overload awaiting a conversion keeps the bound one suffixed.
    one = fn('QFoo', 'load', STRING)
    _, _, got = run([entry('QFoo', one)], unbound={('QFoo', 'load'): 1})
    expect(got == {'load(const QString &)': 'QFoo.load__String'}, got)
    cases.append('unbound overloads keep names suffixed')

    # Lock: stable rerun, carry-over, tombstones, reservation, round trip.
    copy_old = fn('QFile', 'copy', STRING)
    other = fn('QFile', 'rename', STRING)
    _, lock, got = run([entry('QFile', copy_old, 'Bool'), entry('QFile', other, 'Bool')])
    expect(got['copy(const QString &)'] == 'QFile.copy', got)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'names.lock.json'
        lock.path = path
        lock.write()
        lock = names.NameLock.load(path)
        copy_new = fn('QFile', 'copy', STRING + [('std::optional<Permissions>', 'optional', 0, 'Maybe', 'std::nullopt')])
        _, lock, got = run([entry('QFile', copy_new, 'Bool'), entry('QFile', copy_new, 'Bool', count=1)], lock)
        expect(got['copy(const QString &, std::optional<Permissions>) /1'] == 'QFile.copy', got)
        expect(got['copy(const QString &, std::optional<Permissions>)'] == 'QFile.copy__String_Maybe', got)
        expect(len(lock.carried) == 1, lock.carried)
        expect([row['name'] for row in lock.removed['QFile'].values()] == ['QFile.rename'], lock.removed)
        expect(lock.unacknowledged() == [('QFile', 'QFile.rename')], lock.unacknowledged())
        cases.append('replacement C++ signatures inherit names with the same Bend shape')
        # A different shape cannot take the reserved name.
        renamed = fn('QFile', 'rename', [('int', 'int', 0, 'Int32', '')])
        _, lock2, got = run([entry('QFile', copy_new, 'Bool'), entry('QFile', copy_new, 'Bool', count=1),
                             entry('QFile', renamed, 'Bool')], lock)
        expect(got['rename(int)'] == 'QFile.rename__int', got)
        lock.write()
        reloaded = names.NameLock.load(path)
        expect(reloaded.names == lock.names and reloaded.removed == lock.removed, 'lock round trip changed rows')
        reloaded.acknowledge()
        expect(not reloaded.unacknowledged(), 'acknowledgement did not apply')
        cases.append('removed names stay reserved and require acknowledgement')
    corrupt = names.NameLock(names={'QFoo': {'size()': ('QFoo.size', 'self () -> Int32'),
                                             'find()': ('QFoo.size', 'self () -> Bool')}})
    raises(lambda: run([entry('QFoo', size, 'Int32'), entry('QFoo', find_none, 'Bool')], corrupt), ValueError, 'Duplicate public name')
    cases.append('a lock cannot give two C++ functions one name')
    cases += families()
    return cases


def family(owner, base, k, inputs, result='Unit', cpp=None):
    return dict(owner=owner, base=base, key=k, inputs=tuple(inputs), result=result,
                cpp=[dict(cpp=c) for c in cpp] if cpp is not None else None)


def run_family(entries, lock=None):
    g = FakeGenerator([])
    lock = lock or names.NameLock()
    names.assign_family(g, lock, entries)
    names.finalize(g, lock)
    return lock, {e['key']: e['name'] for e in entries}


def families():
    cases = []
    entries = [family('QObject', 'Virtual.event', 'virtual event(QEvent*)', ['QEvent'], 'Bool', ['QEvent*']),
               family('QStyle', 'Virtual.polish', 'virtual polish(QWidget*)', ['QWidget'], cpp=['QWidget*']),
               family('QStyle', 'Virtual.polish', 'virtual polish(QPalette&)', ['QPalette'], 'QPalette', ['QPalette&']),
               family('QObject', 'newOverride', 'override /0', [], 'QObject', []),
               family('QObject', 'newOverride', 'override QObject(QObject*)', ['QObject'], 'QObject', ['QObject*']),
               family('QTimer', 'newOverride', 'override QTimer(QObject*)', ['QObject'], 'QTimer', ['QObject*']),
               family('QPaint', 'Virtual.draw', 'virtual draw(float)', ['F64'], cpp=['float']),
               family('QPaint', 'Virtual.draw', 'virtual draw(double)', ['F64'], cpp=['double'])]
    lock, got = run_family(entries)
    expect(got['virtual event(QEvent*)'] == 'QObject.Virtual.event', got)
    expect(got['virtual polish(QWidget*)'] == 'QStyle.Virtual.polish__QWidget' and
           got['virtual polish(QPalette&)'] == 'QStyle.Virtual.polish__QPalette', got)
    expect(got['override /0'] == 'QObject.newOverride' and got['override QObject(QObject*)'] == 'QObject.newOverride__QObject', got)
    expect(got['override QTimer(QObject*)'] == 'QTimer.newOverride', got)
    # Virtual overloads are never merged: each one needs its own override.
    expect(got['virtual draw(float)'] == 'QPaint.Virtual.draw__float' and
           got['virtual draw(double)'] == 'QPaint.Virtual.draw__double', got)
    cases.append('callback families: bare virtuals and overrides, Bend-typed overloads, C++ spelling for collisions')
    # A newly bound overload keeps the published bare name and is suffixed itself.
    added = entries[:1] + [family('QObject', 'Virtual.event', 'virtual event(QEvent*,int)', ['QEvent', 'Int32'], 'Bool', ['QEvent*', 'int'])]
    lock2, got = run_family(added, names.NameLock(names={o: dict(r) for o, r in lock.names.items()}))
    expect(got['virtual event(QEvent*)'] == 'QObject.Virtual.event', got)
    expect(got['virtual event(QEvent*,int)'] == 'QObject.Virtual.event__QEvent_Int32', got)
    expect(('QStyle', 'QStyle.Virtual.polish__QWidget') in lock2.unacknowledged(), lock2.unacknowledged())
    cases.append('callback family names are locked and removals are tombstoned')
    raises(lambda: run_family([family('QX', 'Handler.f', 'handler f:a', ['Int32']),
                               family('QX', 'Handler.f', 'handler f:b', ['Int32'])]), ValueError, 'native parameter types')
    cases.append('ambiguous function callbacks are a generation error, never a hash')
    return cases


def package():
    coverage = json.loads((ROOT / 'packages/qt612/coverage.json').read_text())
    lock = names.NameLock.load(ROOT / 'generator/qt612/names.lock.json')
    generated = coverage['generated']
    public = [m['bend_name'] for m in generated]
    expect(len(public) == len(set(public)), 'Duplicate generated names')
    # Every top-level definition, including callback families and adapters.
    defined = re.findall(r'^def ([A-Za-z0-9_.]+)', (ROOT / 'packages/qt612/qt.bend').read_text(), re.M)
    internal_painters = [name for name in defined
                         if name.endswith('.sharedPainter') or '.Virtual.sharedPainter' in name]
    expect(not internal_painters, f'Qt-internal sharedPainter API remains: {internal_painters[:5]}')
    # Native signals are Signal declarations named like the signal, as in PySide.
    signals = {m['bend_name'] for m in generated if 'signal' in m}
    expect({'QAbstractSlider.rangeChanged', 'QObject.destroyed', 'QCompleter.activated__String'} <= signals
           and all(m['return'] == 'Signal' for m in generated if 'signal' in m),
           f'Native signal declarations are missing or misnamed: {sorted(signals)[:5]}')
    connectors = sorted(n for n in defined if re.search(r'\.(connect|emit)_[A-Za-z]', n)
                        and not n.startswith(('Signal.', 'Internal.')))
    expect(not connectors, f'Per-signal connectors or emitters remain: {connectors[:5]}')
    # Operation IDs stay inside the raw transport calls. Every definition name,
    # including Internal helpers, callbacks and adapters, is stable and readable.
    legacy = sorted({n for n in defined if re.search(r'_[0-9a-f]{8}(\.|$)|_[0-9]{5,}(\.|$)|_default\d+(\.|$)', n)})
    expect(not legacy, f'Hash, operation or _defaultN names remain: {legacy[:5]}')
    flag_types = sorted(set(re.findall(r'\bFlags_[A-Za-z0-9_]+', (ROOT / 'packages/qt612/qt.bend').read_text())))
    expect(not flag_types, f'QFlags types must use their enum type: {flag_types[:5]}')
    locked = {name for rows in lock.names.values() for name, _ in rows.values()}
    expect(set(public) <= locked, f'Unlocked names: {sorted(set(public) - locked)[:5]}')
    callbacks = coverage['callbacks']
    families = ([m['bend_name'] for m in callbacks['virtual_methods']] +
                [m['bend_name'] for m in callbacks['function_callbacks']] +
                [m['response'] for m in callbacks['function_callbacks']])
    # Qt's own callWithCallback methods keep their upstream names. The
    # Handler convention applies to our generated adapter families.
    old_handlers = [n for n in families if '.Callback.' in n or 'WithCallback' in n]
    expect(not old_handlers, f'Legacy callback adapter names remain: {old_handlers[:5]}')
    families = [n for n in families if re.search(r'\.(Virtual|Handler)\.|WithHandler', n)]  # not MessageHandler.message
    expect(families and set(families) <= locked, f'Unlocked callback names: {sorted(set(families) - locked)[:5]}')
    merged = coverage['merged_overloads']
    expect(all(m['bend_name'] in set(public) for m in merged), 'A merged overload names a missing binding')
    unacknowledged = lock.unacknowledged()
    expect(not unacknowledged, 'Removed public names need --acknowledge-removed-names before publication: '
           + ', '.join(name for _, name in unacknowledged[:20]))
    return dict(names=len(public), merged_overloads=len(merged), locked=len(locked),
                removed=sum(len(rows) for rows in lock.removed.values()))


def main():
    receipt = dict(maintainer_test=True, synthetic_cases=synthetic())
    if '--synthetic-only' not in sys.argv:
        receipt['package'] = package()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('PASS overload names: ' + '; '.join(receipt['synthetic_cases']))


if __name__ == '__main__':
    main()
