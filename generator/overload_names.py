"""Public Bend names for generated C++ overloads.

Every generated entry is a C++ overload, a default-argument variant of one
(its trailing native defaults supplied), a signal, or an adapter derived from
an already named entry. Names are assigned per receiver class and base name:

1. A default variant is an ordinary overload named by its own arguments.
2. C++ name hiding: an entry is dropped when a subclass of its declaring class
   declares an entry with the same Bend inputs in the same group.
3. Entries with identical Bend inputs and result collapse to the overload that
   C++ resolution prefers for Bend's argument representations (see `rank`).
   Dropped entries stay in coverage as merged overloads.
4. A group with one Bend input shape, and no overload that passed every policy
   check but still lacks a conversion, keeps the bare name. Zero-argument
   entries keep it as well. Other entries append their Bend argument types.
   If a published overload already owns the bare name, a new parameterless
   overload uses `__NoArgs` without renaming that published overload.
5. Remaining collisions (same inputs, different results) first drop colliding
   default variants, then spell C++ parameter types. Anything still ambiguous
   is a generation error, never a hash.

Callback families (virtual overrides, function callbacks,
`...WithHandler` methods and `newOverride` constructors) follow
rules 4 and 5 within their own namespace; see `assign_family`.

The name lock pins each published name to its C++ identity. Locked entries
always survive rules 2 and 3. A removed entry leaves a tombstone that keeps
its name reserved, unless a new entry has exactly the removed Bend shape; that
entry inherits the name. A locked name that spells a Bend type the package no
longer defines is tombstoned too, and its entry is named again. Tombstones
must be acknowledged before verification passes, because they break consumers
of the published package.
"""
from collections import defaultdict
import json
import re

import native_operators

SCHEMA = 1
VIEWS = {'QStringView', 'QAnyStringView', 'QByteArrayView'}
NARROW_TEXT = {'QLatin1String', 'QLatin1StringView', 'QUtf8StringView'}
BYTE_POINTEES = {'char', 'uchar', 'unsigned char', 'signed char', 'qint8', 'quint8', 'uint8_t', 'int8_t'}
# A narrower native integer or float loses range or precision for the same
# Bend value. Linux x86-64 `long` is 64 bits wide.
NUMERIC_PENALTY = {name: 1 for name in ('int', 'uint', 'unsigned', 'unsigned int', 'qint32', 'quint32',
                                        'int32_t', 'uint32_t', 'char32_t', 'float')}
NUMERIC_PENALTY.update({name: 2 for name in ('short', 'ushort', 'unsigned short', 'qint16', 'quint16',
                                             'int16_t', 'uint16_t', 'char16_t')})
NUMERIC_PENALTY.update({name: 3 for name in BYTE_POINTEES})
# Lock keys of callback-family entries start with their family. Ordinary
# entries never do: their keys are C++ identities or `signal-descriptor `
# identities. `signal-with-type ` keys name retired connect_<signal>With entries.
FAMILIES = ('virtual ', 'callback ', 'with-callback ', 'handler ', 'with-handler ', 'override ', 'schema-constructor ', 'signal-with-type ')


def key(m):
    """Stable C++ identity of one public entry within its receiver class."""
    f = m['function']
    text = native_operators.identity(f)
    if f['signal']:
        text = 'signal-descriptor ' + text
    if m.get('default_constructor'):
        text += ' /0'
    elif 'omitted_defaults' in m:
        text += f' /{len(m["args"])}'
    if 'pixel_buffer_alternative' in m:
        text += ' /bufferOffset' + ''.join(f'_{i}' for i in m['pixel_buffer_alternative'])
    return text


def implementing(m):
    """The class whose declaration C++ name lookup finds (it may override)."""
    f = m['function']
    return f.get('implementing_class') or f['declaring_class']


def has_self(m):
    f = m['function']
    return not (f['constructor'] or f['static'])


def inputs(m):
    return has_self(m), tuple(a['bend'] for a in m.get('signal_args', m['args']))


def shape(m):
    self_marker, args = inputs(m)
    return ('self ' if self_marker else '') + '(' + ', '.join(args) + ') -> ' + m['return']['bend']


def variant(m):
    return bool(m.get('default_constructor')) or 'omitted_defaults' in m


def bend_token(bend):
    text = re.sub(r'&\d+\s*,?\s*', '', bend)
    return re.sub(r'[^A-Za-z0-9_]+', '_', text).strip('_')


def spelled_types(text):
    """Names of the Bend types in a lock shape such as `self (List<&2, X>) -> Y`."""
    return set(re.findall(r'[A-Za-z_][A-Za-z0-9_.]*', text)) - {'self'}


def defined_types(g, shapes):
    found = set(getattr(g, 'types', {}))
    for text in shapes:
        found |= spelled_types(text)
    return found


def cpp_token(t):
    text = re.sub(r'\b(?:const|volatile)\b', '', t['cpp'])
    pointers = text.count('*')
    rvalue = '&&' in text
    text = re.sub(r'[&*\s]', '', text)
    return re.sub(r'[^A-Za-z0-9_]+', '_', text).strip('_') + 'Ptr' * pointers + ('Rvalue' if rvalue else '')


def native_inputs(m):
    """Raw C++ types and their conversions for the entry's Bend inputs."""
    f = m['function']
    if 'signal_args' in m:
        return [(a['type'], {}) for a in f['arguments']]
    plan = m.get('parameters')
    if plan is None:
        return []
    return [(f['arguments'][p['source']]['type'], p['type']) for p in plan
            if p['input'] is not None and p['input'] < len(m['args'])]


def penalty(raw, converted):
    """How far an overload's parameter is from Bend's natural representation."""
    name = raw['name']
    cost = 1 if converted.get('rvalue') or '&&' in raw['cpp'] else 0
    if raw.get('enum'):
        cost += 1  # E and QFlags<E> share a Bend type; only QFlags takes combined flags.
    if name in VIEWS:
        cost += 1
    elif name in NARROW_TEXT:
        cost += 2
    elif raw['pointers'] and name in BYTE_POINTEES:
        cost += 3
    elif not raw['pointers']:
        cost += NUMERIC_PENALTY.get(name, 0)
    return cost


def rank(m):
    """Lower wins among Bend-equivalent entries.

    A real overload beats a default variant. Bend passes owning values, so a
    const reference beats an rvalue copy, an owning string or byte array beats
    a view, a C string is last, wider numbers beat narrower ones, and a QFlags
    parameter beats its single enum. A call on a mutable handle resolves to the
    non-const member in C++.
    """
    cost = sum(penalty(raw, converted) for raw, converted in native_inputs(m))
    return variant(m), cost, bool(m['function']['const']), key(m)


def cpp_parameters(m):
    f = m['function']
    arguments = f['arguments'][:len(m['args'])] if variant(m) else f['arguments']
    return [a['type'] for a in arguments]


def public_prefix(owner):
    """Bend namespace of a receiver class (generate.ident plus a dot)."""
    return owner.replace('::', '.') + '.'


class NameLock:
    """Published names per receiver class and C++ identity (see module doc).

    On disk, names omit their class prefix and each row is one line, so a
    regeneration diff shows exactly the added and removed public names.
    """
    def __init__(self, path=None, names=None, removed=None):
        self.path = path
        self.names = names or {}
        self.removed = removed or {}
        self.carried = []
        self.created = []
        self.tombstoned = []
        self.reshaped = []

    @classmethod
    def load(cls, path):
        if not path.exists():
            return cls(path)
        data = json.loads(path.read_text())
        if data.get('schema') != SCHEMA:
            raise ValueError(f'Unsupported name lock schema in {path}')
        names = {owner: {k: (public_prefix(owner) + v[0], v[1]) for k, v in rows.items()}
                 for owner, rows in data['names'].items()}
        removed = {owner: {k: dict(row, name=public_prefix(owner) + row['name']) for k, row in rows.items()}
                   for owner, rows in data['removed'].items()}
        return cls(path, names, removed)

    def pinned(self, owner, entry_key):
        row = self.names.get(owner, {}).get(entry_key)
        return row[0] if row else None

    def reserved(self, owner):
        return {row['name'] for row in self.removed.get(owner, {}).values()}

    def unacknowledged(self):
        return sorted((owner, row['name']) for owner, rows in self.removed.items()
                      for row in rows.values() if not row['acknowledged'])

    def retire(self, owner, entry_key, reason, tombstone=None):
        name, old_shape = self.names[owner].pop(entry_key)
        tombstone = tombstone or entry_key
        if tombstone in self.removed.get(owner, {}):
            raise ValueError(f'A tombstone already holds {owner} {tombstone}')
        self.removed.setdefault(owner, {})[tombstone] = dict(name=name, shape=old_shape, reason=reason, acknowledged=False)
        self.tombstoned.append((owner, name, reason))

    def rename_stale(self, owner, entry_key, defined):
        """Retire a live entry's name that spells a Bend type no longer defined.

        The entry is then named again, so no public name spells a type that
        does not exist. A conversion that changes an argument to another
        existing type keeps its pinned name.
        """
        row = self.names.get(owner, {}).get(entry_key)
        suffix = row and row[0].rpartition('.')[2].partition('__')[2]
        if not suffix:
            return
        for t in sorted(spelled_types(row[1]) - defined):
            if re.search(r'(?:^|_)' + re.escape(bend_token(t)) + r'(?:_|$)', suffix):
                self.retire(owner, entry_key, f'Renamed: the Bend type {t} no longer exists',
                            tombstone=entry_key + ' /renamed')
                return

    def acknowledge(self):
        for rows in self.removed.values():
            for row in rows.values():
                row['acknowledged'] = True

    def write(self):
        if self.path is None:
            raise ValueError('This name lock is read-only; only a full generation persists names')

        def section(table, row):
            owners = [(owner, rows) for owner, rows in sorted(table.items()) if rows]
            lines = []
            for i, (owner, rows) in enumerate(owners):
                lines.append(f' {json.dumps(owner)}: {{')
                items = sorted(rows.items())
                for j, (k, value) in enumerate(items):
                    lines.append(f'  {json.dumps(k, ensure_ascii=False)}: '
                                 f'{json.dumps(row(owner, value), ensure_ascii=False)}' + (',' if j + 1 < len(items) else ''))
                lines.append(' }' + (',' if i + 1 < len(owners) else ''))
            return lines

        def short(owner, name):
            prefix = public_prefix(owner)
            if not name.startswith(prefix):
                raise ValueError(f'Public name {name} is outside its class namespace {prefix}')
            return name[len(prefix):]
        text = ['{', f' "schema": {SCHEMA},', ' "names": {']
        text += section(self.names, lambda owner, v: [short(owner, v[0]), v[1]])
        text += [' },', ' "removed": {']
        text += section(self.removed, lambda owner, row: dict(row, name=short(owner, row['name'])))
        text += [' }', '}']
        import output_files
        output_files.write_text(self.path, '\n'.join(text) + '\n')


def removal_reason(g, owner, entry_key, present=()):
    if entry_key.startswith('signal-with-type '):
        return 'Replaced by Signal.connectWith and the signal declaration'
    if entry_key.startswith('connect-signal '):
        # The same in every native module partition (see merged_lock).
        return 'Replaced by Signal.connect and the signal declaration'
    if entry_key.startswith(FAMILIES):
        signature = entry_key.split(' ', 1)[1]
        return next((item['reason'] for item in getattr(g, 'callback_excluded', [])
                     if item['signature'] == signature and item['class_name'] == owner), 'No longer generated')
    return g.excluded_identities.get((owner, entry_key.split(' /')[0]), 'No longer generated')


def assign(g, lock):
    """Name `g.methods` and drop hidden or Bend-equivalent duplicates."""
    # Retire vanished identities first so a replacement can inherit the name.
    # Pixel-buffer variants are derived after naming; finalize retires them.
    present = {(m['class'], key(m)) for m in g.methods}
    defined = defined_types(g, [shape(m) for m in g.methods])
    for owner, k in sorted(present):
        lock.rename_stale(owner, k, defined)
    for owner, rows in lock.names.items():
        for k in [k for k in rows if (owner, k) not in present and ' /bufferOffset' not in k
                  and not k.startswith(FAMILIES)]:
            lock.retire(owner, k, removal_reason(g, owner, k, present))
    groups = defaultdict(list)
    for m in g.methods:
        groups[(m['class'], g.base_name(m))].append(m)
    dropped = {}
    for (owner, base), group in groups.items():
        pins = {id(m): lock.pinned(owner, key(m)) for m in group}
        pins = {i: name for i, name in pins.items() if name}
        alive = list(group)

        def drop(m, reason, kept):
            dropped[id(m)] = (m, reason, kept)
            alive.remove(m)

        by_inputs = defaultdict(list)
        for m in alive:
            by_inputs[inputs(m)].append(m)
        for same in by_inputs.values():
            for m in list(same):
                if id(m) in pins or m['function'].get('free_operator'):
                    continue
                declaring = implementing(m)
                hider = next((d for d in same if d is not m and not d['function'].get('free_operator')
                              and implementing(d) in g.classes
                              and declaring in g.all_bases(implementing(d))), None)
                if hider is not None:
                    drop(m, 'Hidden by a derived declaration with the same Bend arguments', hider)
        by_shape = defaultdict(list)
        for m in alive:
            by_shape[shape(m)].append(m)
        for same in by_shape.values():
            winners = [m for m in same if id(m) in pins] or [min(same, key=rank)]
            for m in same:
                if m not in winners:
                    drop(m, 'Same Bend arguments and result as the preferred overload', winners[0])

        bare = len({inputs(m)[1] for m in alive}) == 1 and not g.unbound_overloads.get((owner, base))
        prefix = public_prefix(owner)
        names = {id(m): pins[id(m)] for m in alive if id(m) in pins}
        # A replacement C++ signature inherits a removed name only when its
        # complete Bend shape is unchanged, and only when the match is unique.
        tombstones = lock.removed.get(owner, {})
        claims = defaultdict(list)
        for m in alive:
            if id(m) in names:
                continue
            for k, row in tombstones.items():
                if row['shape'] == shape(m) and (row['name'] == prefix + base or row['name'].startswith(prefix + base + '__')):
                    claims[k].append(m)
        for k, ms in sorted(claims.items()):
            if len(ms) == 1 and sum(ms[0] in other for other in claims.values()) == 1:
                lock.carried.append((owner, k, key(ms[0]), tombstones[k]['name']))
                names[id(ms[0])] = tombstones.pop(k)['name']
        reserved = lock.reserved(owner)
        fixed = {names[id(m)]: m for m in alive if id(m) in names}
        candidates = defaultdict(list)
        for m in alive:
            if id(m) in names:
                continue
            args = inputs(m)[1]
            candidates[prefix + (base if bare or not args else base + '__' + '_'.join(map(bend_token, args)))].append(m)
        for candidate, ms in candidates.items():
            # A default variant yields to a full overload or a live locked
            # entry with its name; the full form remains callable.
            real = [m for m in ms if not variant(m)]
            locked = fixed.get(candidate)
            owner_entry = (locked if locked and any(inputs(locked) == inputs(m) for m in ms)
                           else real[0] if real and len(ms) > 1 else None)
            if owner_entry is not None:
                for m in ms:
                    if variant(m):
                        drop(m, 'Default variant has the same Bend arguments as a full overload', owner_entry)
                ms = [m for m in ms if id(m) not in dropped]
                if not ms:
                    continue
            if len(ms) == 1 and candidate not in reserved and candidate not in fixed:
                names[id(ms[0])] = candidate
                fixed[candidate] = ms[0]
                continue
            spelled = {}
            for m in ms:
                # A parameterless overload keeps the plain name; the others
                # (output-only, for example) spell their C++ parameters.
                tokens = list(map(cpp_token, cpp_parameters(m)))
                name = prefix + base + ('__' + '_'.join(tokens) if tokens else '')
                if not tokens and (name in reserved or name in fixed):
                    name += '__NoArgs'
                spelled.setdefault(name, []).append(m)
            for name, same in list(spelled.items()):
                if len(same) > 1 and len({m['function']['const'] for m in same}) == len(same):
                    del spelled[name]
                    for m in same:
                        spelled[name + ('_const' if m['function']['const'] else '')] = [m]
            for name, same in spelled.items():
                if len(same) > 1 or name in reserved or name in fixed:
                    raise ValueError('Ambiguous overload names need an explicit policy: '
                                     + ', '.join(m['function']['signature'] for m in same) + ' -> ' + name)
                names[id(same[0])] = name
                fixed[name] = same[0]
        for m in alive:
            m['bend_name'] = names[id(m)]
    g.methods = [m for m in g.methods if id(m) not in dropped]
    final = {}
    for m, reason, kept in dropped.values():
        while id(kept) in dropped:
            kept = dropped[id(kept)][2]
        final[id(m)] = dict(**{'class': m['class']}, signature=m['function']['signature'],
                            omitted_defaults=m.get('omitted_defaults', []), bend_name=kept['bend_name'], reason=reason)
    g.merged_overloads = [final[id(m)] for m, _, _ in sorted(dropped.values(), key=lambda row: (row[0]['class'], key(row[0])))]


def family_shape(e):
    return '(' + ', '.join(e['inputs']) + ') -> ' + e['result']


def assign_family(g, lock, entries):
    """Name callback-family entries without hashes.

    Each entry has `owner` (the C++ class whose namespace holds the name),
    `base` (relative to that namespace, such as `Virtual.event`), `key`
    (starting with one of FAMILIES), Bend `inputs`, a Bend `result` and
    native `cpp` parameter types (None when unavailable). A group with one
    input shape keeps the bare base; the others append Bend input types, then
    C++ types. Locked names and same-shape tombstones apply as for ordinary
    entries. Sets `name` on every entry.
    """
    kinds = tuple(sorted({e['key'].split(' ', 1)[0] + ' ' for e in entries}))
    present = {(e['owner'], e['key']) for e in entries}
    if len(present) != len(entries):
        raise ValueError('Two callback-family entries share one lock identity')
    for owner, rows in lock.names.items():
        for k in [k for k in rows if k.startswith(kinds) and (owner, k) not in present]:
            lock.retire(owner, k, removal_reason(g, owner, k, present))
    defined = defined_types(g, [family_shape(e) for e in entries] + [shape(m) for m in getattr(g, 'methods', [])])
    for owner, k in sorted(present):
        lock.rename_stale(owner, k, defined)
    groups = defaultdict(list)
    for e in entries:
        if not e['key'].startswith(FAMILIES):
            raise ValueError(f'Callback-family key without a family: {e["key"]}')
        groups[(e['owner'], e['base'])].append(e)
    for (owner, base), group in sorted(groups.items()):
        prefix = public_prefix(owner)
        names = {id(e): lock.pinned(owner, e['key']) for e in group}
        names = {i: name for i, name in names.items() if name}
        tombstones = lock.removed.get(owner, {})
        claims = defaultdict(list)
        for e in group:
            if id(e) in names:
                continue
            family = e['key'].split(' ', 1)[0] + ' '
            for k, row in tombstones.items():
                if (k.startswith(family) and row['shape'] == family_shape(e) and
                        (row['name'] == prefix + base or row['name'].startswith(prefix + base + '__'))):
                    claims[k].append(e)
        for k, es in sorted(claims.items()):
            if len(es) == 1 and sum(es[0] in other for other in claims.values()) == 1:
                lock.carried.append((owner, k, es[0]['key'], tombstones[k]['name']))
                names[id(es[0])] = tombstones.pop(k)['name']
        reserved = lock.reserved(owner)
        fixed = set(names.values())
        bare = len({e['inputs'] for e in group}) == 1
        candidates = defaultdict(list)
        for e in group:
            if id(e) not in names:
                suffix = '' if bare or not e['inputs'] else '__' + '_'.join(map(bend_token, e['inputs']))
                candidates[prefix + base + suffix].append(e)
        for candidate, es in sorted(candidates.items()):
            if len(es) == 1 and candidate not in reserved and candidate not in fixed:
                names[id(es[0])] = candidate
                fixed.add(candidate)
                continue
            for e in es:
                if e.get('cpp') is None:
                    raise ValueError(f'Ambiguous callback name needs native parameter types: {candidate} ({e["key"]})')
                tokens = list(map(cpp_token, e['cpp']))
                name = prefix + base + ('__' + '_'.join(tokens) if tokens else '')
                if not tokens and (name in reserved or name in fixed):
                    name += '__NoArgs'
                if name in fixed or name in reserved:
                    raise ValueError('Ambiguous callback names need an explicit policy: '
                                     + '; '.join(x['key'] for x in es) + ' -> ' + name)
                names[id(e)] = name
                fixed.add(name)
        for e in group:
            e['name'] = names[id(e)]
    g.family_entries = list(getattr(g, 'family_entries', [])) + list(entries)


def finalize(g, lock):
    """Check every public entry against the lock and record changes.

    Call after `assign` and after callback families are named.
    """
    rows_now = [(m['class'], key(m), m['bend_name'], shape(m)) for m in g.methods]
    rows_now += [(e['owner'], e['key'], e['name'], family_shape(e)) for e in getattr(g, 'family_entries', [])]
    current = {}
    seen = {}
    for owner, k, name, entry_shape in rows_now:
        if (owner, k) in current:
            raise ValueError(f'Two public entries share one C++ identity: {(owner, k)}')
        current[(owner, k)] = (name, entry_shape)
        if name in seen:
            raise ValueError(f'Duplicate public name {name}: {seen[name]}, {k}')
        seen[name] = k
    for owner, rows in lock.names.items():
        for k, (name, old_shape) in list(rows.items()):
            now = current.get((owner, k))
            if now is not None:
                if now[0] != name:
                    raise AssertionError(f'Locked name {name} would now mean {now[0]} ({k})')
                if now[1] != old_shape:
                    # The native identity/name stays pinned when a conversion
                    # policy is corrected. Carry-over must use its current
                    # Bend shape in subsequent generations.
                    rows[k] = (name, now[1])
                    lock.reshaped.append((owner, k, old_shape, now[1]))
                continue
            if name in seen:
                raise AssertionError(f'Locked name {name} would now call a different C++ function: {seen[name]}')
            lock.retire(owner, k, removal_reason(g, owner, k, current))
    for owner, rows in lock.removed.items():
        for row in rows.values():
            if row['name'] in seen:
                raise AssertionError(f'Removed name {row["name"]} is reserved but was assigned again')
    for (owner, k), (name, entry_shape) in current.items():
        rows = lock.names.setdefault(owner, {})
        if k not in rows:
            rows[k] = (name, entry_shape)
            lock.created.append(name)


def signature_comment(m):
    f = m['function']
    owner = f.get('declaring_class') or m['class']
    text = f'# C++: {f["native_comment"]}' if f.get('native_comment') else f'# C++: {owner}::{f["signature"]}'
    if m.get('omitted_defaults'):
        text += ' [defaults: ' + ', '.join(m['omitted_defaults']) + ']'
    return ' '.join(text.split())
