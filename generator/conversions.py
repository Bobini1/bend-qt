"""Recursive Bend/native conversions, discovered from extracted signatures."""
import hashlib
import re


def safe(name):
    return re.sub(r'[^a-zA-Z0-9_]', '_', name)


def native(t):
    if t['kind'] == 'object':
        # Object references travel as identity pointers, never by C++ copy.
        # Call sites take the address of reference-valued signal arguments.
        return ('const ' if t.get('readonly') or t.get('native_const') else '') + t['name'] + ' *'
    if t['kind'] == 'object_snapshot':
        return 'const ' + t['name'] + ' *'
    # Remove only top-level const. Nested pointee const in e.g.
    # QList<const QInputDevice *> is part of the actual container type.
    return t['cpp'].removeprefix('const ').replace('&', '').strip()


class Conversions:
    def __init__(self, generator):
        self.g = generator
        self.pure = {}
        self.cpp = {}

    def register(self, t):
        if 'codec' not in t:
            prefix = 'Owned_' if t['kind'] == 'object' and t.get('owned') else 'Snapshot_' if t['kind'] == 'object_snapshot' else 'Copy_' if t['kind'] == 'value' and self.g.classes[t['name']].get('object') else 'Convert_'
            t['codec'] = prefix + safe(t['bend'])
        if 'cpp' in t:
            policy = (t['kind'] + ':' + str(bool(t.get('owned'))) + ':' + str(bool(t.get('clone')))
                      + ':' + ','.join(c.get('native_codec', c['codec']) for c in t.get('children', [])))
            t['native_codec'] = 'wire_' + hashlib.sha256((native(t) + '|' + policy).encode()).hexdigest()[:12]
            self.cpp.setdefault(t['native_codec'], t)
        self.pure.setdefault(t['codec'], t)
        return t

    def owned_objects(self, t):
        """Give factory/take containers distinct owning element codecs."""
        if t['kind'] == 'object':
            if self.g.classes[t['name']].get('borrow_only'):
                raise ValueError('Ownership result requires a class with a public destructor')
            copied = dict(t, owned=True)
            copied.pop('codec', None)
            copied.pop('native_codec', None)
            return self.register(copied)
        if 'children' in t:
            children = [self.owned_objects(child) for child in t['children']]
            if any(a is not b for a, b in zip(children, t['children'])):
                copied = dict(t, children=children, codec='Owned_' + t['codec'])
                copied.pop('native_codec', None)
                return self.register(copied)
        return t

    def container(self, t, result):
        name = t['name']
        if name not in ('QList', 'QVector', 'QSet', 'QMap', 'QHash', 'QMultiMap', 'QMultiHash', 'std::pair', 'QPair', 'std::optional', 'std::array'):
            raise ValueError(f"Container conversion is not implemented for {name}")
        count = None
        arguments = t['instantiations']
        if name == 'std::array':
            if len(arguments) != 2 or not re.fullmatch(r'[0-9]+', arguments[1]['cpp'].strip()):
                raise ValueError('Fixed array extent requires an extracted numeric constant')
            count = int(arguments[1]['cpp'])
            arguments = arguments[:1]
        children = [self.register(self.g.type(x, result=result)) for x in arguments]
        if any(x['kind'] in ('void', 'string_view') for x in children):
            raise ValueError('Container elements require owning representations')
        if name == 'std::array':
            kind, label = 'array', 'Array_' + str(count) + '_' + children[0]['codec'].removeprefix('Convert_')
            bend = 'List<&2, ' + children[0]['bend'] + '>'
        elif name == 'std::optional':
            if len(children) != 1:
                raise ValueError('Optional conversion requires one element type')
            kind, label = 'optional', 'Optional_' + children[0]['codec'].removeprefix('Convert_')
            bend = 'Maybe<&2, ' + children[0]['bend'] + '>'
        elif name in ('std::pair', 'QPair'):
            kind, label = 'pair', 'Pair_' + '_'.join(x['codec'].removeprefix('Convert_') for x in children)
            bend = 'PairValue<' + ', '.join(x['bend'] for x in children) + '>'
        elif name in ('QList', 'QVector', 'QSet'):
            kind, label = 'list', 'List_' + children[0]['codec'].removeprefix('Convert_')
            bend = 'List<&2, ' + children[0]['bend'] + '>'
        else:
            # Maps use a list of entries. Qt controls ordering and duplicate-key
            # semantics; the wire layer preserves the native iteration order.
            pair = self.register({'kind': 'pair', 'children': children,
                'bend': 'PairValue<' + ', '.join(x['bend'] for x in children) + '>',
                'raw': 'Wire', 'codec': 'Pair_' + '_'.join(x['codec'].removeprefix('Convert_') for x in children),
                'cpp': 'std::pair<' + ', '.join(native(x) for x in children) + '>'})
            children = [pair]
            kind, label = 'map', 'List_' + pair['codec']
            bend = 'List<&2, ' + pair['bend'] + '>'
        return self.register({'kind': kind, 'name': name, 'children': children, 'bend': bend,
                              'raw': 'Wire', 'cpp': t['cpp'], 'codec': label,
                              **({'count': count} if kind == 'array' else {})})

    def record(self, children, prefix='Args_'):
        children = [self.register(c) for c in children]
        label = prefix + '_'.join(c['codec'].removeprefix('Convert_') for c in children)
        return self.register({'kind': 'record', 'children': children, 'bend': label, 'raw': 'Wire', 'codec': label})

    def contains(self, t, kinds):
        return t['kind'] in kinds or any(self.contains(c, kinds) for c in t.get('children', []))

    def bend(self):
        lines = []
        for name, t in self.pure.items():
            kind, typ = t['kind'], t['bend']
            children = t.get('children', [])
            if kind == 'record':
                fields = t.get('field_names', [f'arg{i}' for i in range(len(children))])
                lines += [f'type {typ} is Data:', f"  {typ}{{" + ', '.join(f'{fields[i]}: {c["bend"]}' for i, c in enumerate(children)) + '}', '']
                for i, c in enumerate(children):
                    lines += [f'def {typ}.{fields[i]}(value: {typ}) -> {c["bend"]}:', '  match value:',
                              f'    case {typ}{{' + ', '.join(f'a{j}' for j in range(len(children))) + f'}}: a{i}', '']
            lines += [f'def {name}.encode(value: {typ}) -> Wire:']
            if kind in ('void', 'nullptr'):
                lines += ['  Codec.word(0)']
            elif kind in ('list', 'map', 'array'):
                c = children[0]
                lines += [f'  Codec.encode_list(~{c["bend"]}, ~{c["codec"]}.encode, value)']
            elif kind == 'optional':
                c = children[0]
                lines += [f'  Codec.encode_optional(~{c["bend"]}, ~{c["codec"]}.encode, value)']
            elif kind in ('pair', 'record'):
                ctor = 'PairValue' if kind == 'pair' else typ
                args = [f'a{i}' for i in range(len(children))]
                items = [f'{c["codec"]}.encode({a})' for c, a in zip(children, args)]
                expr = 'Codec.pair(' + ', '.join(items) + ')' if kind == 'pair' else 'Codec.sequence(' + ' <> '.join(items + ['Nil{}']) + ')'
                lines += ['  match value:', f'    case {ctor}{{' + ', '.join(args) + '}: ' + expr]
            elif kind in ('string', 'string_view'): lines += ['  Codec.text(value)']
            elif kind in ('real', 'i64', 'u64', 'enum64', 'flags64', 'duration'): lines += ['  match value:', f'    case {typ}{{lo, hi}}: Codec.wide(lo, hi)']
            elif kind == 'bool': lines += ['  Codec.word(bool_word(value))']
            elif typ == 'U32': lines += ['  Codec.word(value)']
            else: lines += [f'  Codec.word({typ}.word(value))']
            lines += ['', f'def {name}.decode(value: Wire) -> Maybe<&2, {typ}>:']
            if kind in ('void', 'nullptr'):
                lines += ['  match value:', '    case WireScalar{0, 0}: Some{Unit{}}', '    case _: None{}']
            elif kind == 'array':
                c = children[0]
                lines += [f'  Codec.decode_array(~{c["bend"]}, ~{c["codec"]}.decode, {t["count"]}, value)']
            elif kind in ('list', 'map'):
                c = children[0]
                lines += [f'  Codec.decode_list(~{c["bend"]}, ~{c["codec"]}.decode, value)']
            elif kind == 'optional':
                c = children[0]
                lines += [f'  Codec.decode_optional(~{c["bend"]}, ~{c["codec"]}.decode, value)']
            elif kind in ('pair', 'record'):
                ctor = 'PairValue' if kind == 'pair' else typ
                args = [f'a{i}' for i in range(len(children))]
                lines += ['  match value:', '    case WireSequence{' + ' <> '.join(args + ['Nil{}']) + '}:',
                          f'      do Maybe<&2, {typ}>:']
                for i, c in enumerate(children):
                    lines += [f'        v{i}: {c["bend"]} <- {c["codec"]}.decode(a{i})']
                lines += [f'        return {ctor}{{' + ', '.join(f'v{i}' for i in range(len(children))) + '}', '    case _: None{}']
            elif kind in ('string', 'string_view'): lines += ['  Codec.read_text(value)']
            else:
                expr = f'{typ}{{lo, hi}}' if kind in ('real', 'i64', 'u64', 'enum64', 'flags64', 'duration') else ('lo' if typ == 'U32' else 'U32.is_ne(lo, 0)' if kind == 'bool' else f'{typ}{{lo}}')
                lines += ['  match value:', f'    case WireScalar{{lo, hi}}: Some{{{expr}}}', '    case _: None{}']
            lines += ['', f'def {name}.decoded(value: Maybe<&2, {typ}>) -> Result<&1, &1, U32 & String, {typ}>:',
                      '  match value:', '    case Some{value}: Done{value}',
                      '    case None{}: Fail{(22, "Malformed Qt payload")}', '',
                      f'def {name}.wrap(result: Result<&1, &1, U32 & String, Wire>) -> Result<&1, &1, U32 & String, {typ}>:',
                      '  match result:', '    case Fail{error}: Fail{error}', f'    case Done{{value}}: {name}.decoded({name}.decode(value))', '',
                      f'def {name}.release(value: {typ}) -> Action(Unit):']
            if kind == 'object' and t.get('owned'): lines += [f'  Action.cleanup({typ}.release(value))']
            elif kind in ('value', 'byte_view', 'latin1_view', 'std_string', 'object_snapshot'): lines += [f'  Action.cleanup({typ}.release(value))']
            elif kind in ('list', 'map', 'array'):
                c = children[0]
                lines += ['  match value:', '    case Nil{}: Action.pure(Unit, Unit{})',
                          f'    case head <> tail: Action.finally(Unit, {c["codec"]}.release(head), {name}.release(tail))']
            elif kind == 'optional':
                c = children[0]
                lines += ['  match value:', '    case None{}: Action.pure(Unit, Unit{})',
                          f'    case Some{{item}}: {c["codec"]}.release(item)']
            elif kind in ('pair', 'record'):
                ctor = 'PairValue' if kind == 'pair' else typ
                release = 'Action.pure(Unit, Unit{})'
                for i, c in reversed(list(enumerate(children))):
                    release = f'Action.finally(Unit, {c["codec"]}.release(a{i}), {release})'
                lines += ['  match value:', f'    case {ctor}{{' + ', '.join(f'a{i}' for i in range(len(children))) + '}: ' + release]
            else: lines += ['  Action.pure(Unit, Unit{})']
            lines += ['', f'def {name}.with(-A: Type, acquire: Action({typ}), body: {typ} -> Action(A)) -> Action(A):',
                      f'  Action.using({typ}, A, acquire, {name}.release, body)', '']
        return '\n'.join(lines) + '\n'

    def cpp_code(self):
        lines = [
            'struct ConversionValueGuard {',
            '    BqtValue value;',
            '    explicit ConversionValueGuard(BqtValue initial) : value(initial) {}',
            '    ~ConversionValueGuard() { discard_value(value); }',
            '    BqtValue release() { auto result = value; value = {}; return result; }',
            '};',
        ]
        for name, t in self.cpp.items():
            typ = native(t)
            lines += [f'static std::optional<{typ}> read_{name}(BqtRequest *, const BqtValue &);',
                      f'static BqtValue write_{name}(BqtRequest *, {typ} const &);']
        for name, t in self.cpp.items():
            kind, typ = t['kind'], native(t)
            children = t.get('children', [])
            tag = 2 if children else 1 if kind in ('string', 'string_view') else 0
            count = ', 2' if kind == 'pair' else ', ' + str(t['count']) if kind == 'array' else ''
            lines += [f'static std::optional<{typ}> read_{name}(BqtRequest *r, const BqtValue &v) {{',
                      f'    if (!wire_shape(r, v, {tag}{count})) return std::nullopt;']
            if kind == 'optional':
                c = children[0]
                lines += ['    if (v.count > 1) { fail(r, EINVAL, "Optional payload has more than one element"); return std::nullopt; }',
                          f'    if (!v.count) return std::optional<{typ}>{{std::in_place}};',
                          f'    auto item = read_{c["native_codec"]}(r, v.items[0]);',
                          '    if (!item) return std::nullopt;',
                          f'    return std::optional<{typ}>{{std::in_place, std::in_place, std::move(*item)}};']
            elif kind == 'array':
                c = children[0]
                for i in range(t['count']):
                    lines += [f'    auto a{i} = read_{c["native_codec"]}(r, v.items[{i}]);',
                              f'    if (!a{i}) return std::nullopt;']
                lines += [f'    return {typ}{{' + ', '.join(f'std::move(*a{i})' for i in range(t['count'])) + '};']
            elif kind in ('list', 'map'):
                c = children[0]
                lines += [f'    {typ} result;', '    for (size_t i = 0; i < v.count; ++i) {']
                # Reverse insertion preserves the native order of equal-key entries.
                index = 'v.count - 1 - i' if t['name'] in ('QMultiMap', 'QMultiHash') else 'i'
                lines += [f'        auto item = read_{c["native_codec"]}(r, v.items[{index}]);',
                          '        if (!item) return std::nullopt;']
                expr = 'result.insert(item->first, item->second)' if kind == 'map' else 'result.insert(*item)' if t['name'] == 'QSet' else 'result.append(*item)'
                lines += [f'        {expr};', '    }', '    return result;']
            elif kind == 'pair':
                for i, c in enumerate(children): lines += [f'    auto a{i} = read_{c["native_codec"]}(r, v.items[{i}]);', f'    if (!a{i}) return std::nullopt;']
                lines += [f'    return {typ}{{*a0, *a1}};']
            elif kind in ('object', 'value'):
                writable = kind == 'object' and not (t.get('native_const') or t.get('readonly'))
                lines += [f'    auto *item = get<{t["name"]}>(r, v.word, {self.g.ids[t["name"]]}, ' + ('true' if kind == 'object' else 'false') + ', ' + str(writable).lower() + ');',
                          '    if (r->error) return std::nullopt;', '    return ' + ('item;' if kind == 'object' else f'std::optional<{typ}>{{std::in_place, *item}};')]
            else:
                declarations, expr = self.g.argument(t, 0)
                lines += ['    ' + s.replace('r->arguments[0]', 'v') for s in declarations]
                lines += ['    if (r->error) return std::nullopt;', '    return ' + expr.replace('r->arguments[0]', 'v') + ';']
            lines += ['}', f'static BqtValue write_{name}(BqtRequest *r, {typ} const &value) {{']
            if kind == 'optional':
                c = children[0]
                lines += ['    ConversionValueGuard guard(sequence_value(value ? 1 : 0));', '    auto &result = guard.value;',
                          f'    if (value) result.items[0] = write_{c["native_codec"]}(r, *value);',
                          '    return guard.release();']
            elif kind in ('list', 'map', 'array'):
                c = children[0]
                lines += ['    ConversionValueGuard guard(sequence_value(size_t(value.size())));', '    auto &result = guard.value;', '    size_t i = 0;',
                          '    for (auto it = value.cbegin(); it != value.cend(); ++it) {']
                expr = f'{native(c)}{{it.key(), it.value()}}' if kind == 'map' else '*it'
                lines += [f'        result.items[i++] = write_{c["native_codec"]}(r, {expr});',
                          '        if (r->error) break;', '    }', '    return guard.release();']
            elif kind == 'pair':
                lines += ['    ConversionValueGuard guard(sequence_value(2));', '    auto &result = guard.value;']
                for i, field in enumerate(('first', 'second')):
                    lines += [f'    if (!r->error) result.items[{i}] = write_{children[i]["native_codec"]}(r, value.{field});']
                lines += ['    return guard.release();']
            else:
                code = self.g.store_result(t, 'value')
                lines += ['    BqtValue result{};']
                lines += ['    ' + s.replace('r->result', 'result') for s in code]
                if kind in ('value', 'byte_view', 'latin1_view', 'std_string', 'object_snapshot'): lines += ['    result.owned_handle = result.word;']
                if kind == 'object': lines += ['    result.' + ('owned_handle' if t.get('owned') else 'borrowed_handle') + ' = result.word;']
                lines += ['    return result;']
            lines += ['}']
        return '\n'.join(lines) + '\n'
