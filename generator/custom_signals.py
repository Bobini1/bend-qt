"""Typed declarations of Qt signals owned by Bend-created QObjects."""
from pathlib import Path
import re
from callbacks import _conversion
from conversions import native as native_type
import abi_cohorts
import effect_transport
import protected_members
from module_partitions import argument_entries

HERE = Path(__file__).resolve().parent
UNIT = dict(kind='void', bend='Unit', raw='Unit')
WORD = dict(kind='u32', bend='U32', raw='U32')
WIRE = dict(kind='wire', bend='Wire', raw='Wire', codec='WireIdentity')
OBJECT = dict(kind='object', name='QObject', bend='QObject', raw='U32', owned=True)
CONNECTION = dict(kind='connection', bend='Connection', raw='U32')


def native_meta_type_body(native):
    # Keep the originating interface instead of reconstructing it from a
    # process-wide numeric ID. Distinct native modules may use the same C++
    # spelling for different types. The direct Qt 6 interface also avoids
    # deprecated registration paths that reference optional extern helpers.
    return [f'static const QMetaType meta = QMetaType::fromType<{native}>();',
            'static const bool registered = [] {',
            '    (void)meta.id(); // Allocate the ID before installing aliases.',
            f'    QMetaType::registerNormalizedTypedef(QByteArrayLiteral("{native}"), meta);',
            '    return true;', ' }();', '(void)registered;', 'return meta;']


def qualified_native(g, native):
    return any(re.search(r'(?<![A-Za-z0-9_:])' + re.escape(name) + r'(?![A-Za-z0-9_])', native)
               for name in getattr(g, 'partition_metatype_aliases', {}))


def meta_name(g, native):
    aliases = getattr(g, 'partition_metatype_aliases', {})
    pattern = r'(?<![A-Za-z0-9_:])(?:' + '|'.join(map(re.escape, sorted(aliases, key=len, reverse=True))) + r')(?![A-Za-z0-9_])'
    return re.sub(pattern, lambda match: aliases[match[0]], native) if aliases else native


def meta_family(g, native):
    aliases = getattr(g, 'partition_metatype_aliases', {})
    for name in sorted((name for name in aliases if name in g.classes), key=len, reverse=True):
        if re.search(r'(?<![A-Za-z0-9_:])' + re.escape(name) + r'(?![A-Za-z0-9_])', native):
            package = g.classes[name].get('package', '')
            if package.startswith('PySide6.Qt'):
                return package.removeprefix('PySide6.')
    for name, source in g.api.get('typedefs', {}).items():
        if name == native and source != native:
            return meta_family(g, source)
    return ''


def meta_expression(g, native, conversion):
    qualified = qualified_native(g, native)
    children = conversion.get('children', [])
    if conversion['kind'] == 'map':
        children = children[0]['children']
    arguments = [meta_expression(g, native_type(child), child) for child in children]
    if conversion['kind'] in ('list', 'set', 'array'):
        function = 'sequence' if qualified else 'native_sequence'
        return f'BendQualifiedTypes::{function}<{native}>("{meta_name(g, native)}", {arguments[0]}, "{meta_family(g, native) if qualified else ""}")'
    if conversion['kind'] == 'map':
        function = 'association' if qualified else 'native_association'
        return f'BendQualifiedTypes::{function}<{native}>("{meta_name(g, native)}", {arguments[0]}, {arguments[1]}, "{meta_family(g, native) if qualified else ""}")'
    return (f'BendQualifiedTypes::plain(QMetaType::fromType<{native}>(), "{meta_name(g, native)}", "{meta_family(g, native)}")'
            if qualified else f'QMetaType::fromType<{native}>()')


def native_names(native, conversion):
    names = [native]
    if conversion.get('children'):
        children = conversion['children'][0]['children'] if conversion['kind'] == 'map' else conversion['children']
        if conversion['kind'] in ('list', 'map', 'optional', 'pair', 'array'):
            name = conversion.get('name') or ('std::pair' if conversion['kind'] == 'pair' else '')
            arguments = [native_type(child) for child in children]
            if conversion['kind'] == 'array':
                arguments.append(str(conversion['count']))
            if name:
                names.append(name + '<' + ','.join(arguments) + '>')
                if name in ('QList', 'QVector'):
                    names.extend(alias + '<' + ','.join(arguments) + '>' for alias in ('QList', 'QVector'))
                if name in ('QPair', 'std::pair'):
                    names.extend(alias + '<' + ','.join(arguments) + '>' for alias in ('QPair', 'std::pair'))
    return list(dict.fromkeys(names))


def prepare(g):
    if 'QObject' not in g.ids:
        return
    g.custom_signal_arguments = []
    g.custom_signal_excluded = {}
    g.custom_signal_excluded_types = {}
    g.custom_signal_excluded_values = {}
    used_names = set()
    def add(public, cpp, source):
        converted = _conversion(g, source)
        if g.conversions.contains(converted, ('string_view', 'byte_view', 'latin1_view')):
            raise ValueError('Queued signal arguments require owning representations, not borrowed views')
        # Public enum descriptors are named outside a derived proxy. Unlike a
        # protected virtual signature, they can use the ordinary native codec.
        if converted.get('callback_enum'):
            converted = g.conversions.register(dict(converted, callback_enum=False))
        if cpp in used_names:
            return
        if public is not None:
            previous = next(((native, value) for name, native, value in g.custom_signal_arguments if name == public), None)
            if previous:
                old_native, old = previous
                if (old['kind'], old['bend'], old.get('name')) != (converted['kind'], converted['bend'], converted.get('name')):
                    raise ValueError('Incompatible native argument descriptors share public name: ' + public)
                # Extracted aliases of one enum/flags type share its public
                # codec. Qt resolves the alternative spelling to that metatype.
                if converted['kind'] not in ('enum', 'enum64', 'flags', 'flags64'):
                    raise ValueError('Distinct native argument types share public name: ' + public)
                used_names.add(cpp)
                return
        used_names.add(cpp)
        g.custom_signal_arguments.append((public, cpp, converted))

    def source(name, cpp=None, pointers=0, **extra):
        return dict(name=name, cpp=cpp or name, const=False, pointers=pointers, reference=0,
                    container=False, enum=False, flags=False, instantiations=[], **extra)

    for public, cpp in [('bool', 'bool'), ('int8', 'qint8'), ('u8', 'quint8'),
                        ('int16', 'qint16'), ('u16', 'quint16'), ('int32', 'int'), ('u32', 'uint'),
                        ('int64', 'qint64'), ('u64', 'quint64'),
                        ('f32', 'float'), ('f64', 'double'), ('qreal', 'qreal'),
                        ('long', 'long'), ('ulong', 'unsigned long'), ('size', 'size_t'),
                        ('qintptr', 'qintptr'), ('quintptr', 'quintptr'),
                        ('char', 'char'), ('char16', 'char16_t'), ('char32', 'char32_t'), ('qchar', 'QChar'),
                        ('string', 'QString'), ('nullptr', 'std::nullptr_t')]:
        add(public, cpp, source(cpp))
    for name in g.selected:
        cls = g.classes[name]
        if cls['qobject'] or cls.get('native_object'):
            cpp, pointers = name + '*', 1
        elif (cls.get('copyable')
              and not cls.get('object') and cls.get('public_destructor')):
            cpp, pointers = name, 0
        else:
            g.custom_signal_excluded[name] = 'Requires a guarded native pointer or a public, copyable value type'
            continue
        public = name.replace('::', '.') + '.arg'
        if any(m['bend_name'] == public for m in g.methods):
            raise ValueError('Native method conflicts with signal descriptor: ' + public)
        try:
            add(public, cpp, source(name, cpp, pointers))
        except ValueError as error:
            g.custom_signal_excluded[name] = str(error)
        if cls.get('object') and not cls.get('qobject'):
            if not cls.get('copyable') or not cls.get('public_destructor'):
                g.custom_signal_excluded_values[name] = 'Native value arguments require a public copy constructor and destructor'
                continue
            public_value = name.replace('::', '.') + '.valueArg'
            if any(method['bend_name'] == public_value for method in g.methods):
                raise ValueError('Native method conflicts with owning argument descriptor: ' + public_value)
            if name not in used_names:
                value = g.conversions.register(dict(kind='value', name=name, cpp=name,
                    bend=name.replace('::', '.'), raw='U32'))
                used_names.add(name)
                g.custom_signal_arguments.append((public_value, name, value))
    # The extractor records public access and PySide flag registrations. Older
    # snapshots are accepted conservatively until the maintainer re-extracts:
    # only enums in a namespace or in an already emitted public signature are
    # then known to be nameable by a free codec.
    signature_types = {}
    def remember(t):
        if t.get('kind') in ('enum', 'enum64', 'flags', 'flags64'):
            signature_types[t['name']] = t
        for child in t.get('children', []):
            remember(child)
    for method in g.methods:
        for t in [*method['args'], method['return'], *method.get('signal_args', [])]:
            remember(t)
    for name, enum in sorted(g.enums.items()):
        owner = name.rpartition('::')[0]
        if owner and owner not in g.selected and owner not in g.namespaces:
            continue
        if enum.get('anonymous'):
            g.custom_signal_excluded_types[name] = 'An anonymous enum has no native metatype name'
            continue
        accessible = enum.get('public', owner in g.namespaces or name in signature_types) or protected_members.enum_accessible(g, name)
        if not accessible:
            g.custom_signal_excluded_types[name] = 'Enum is not public, or the cached extraction has no public-access evidence'
            continue
        try:
            add(name.replace('::', '.') + '.arg', name, dict(source(name), enum=True))
            flags = enum.get('flags')
            if flags:
                cpp = 'QFlags<' + name + '>'
                t = g.type(dict(source(cpp), flags=True))
                add(t['bend'] + '.arg', cpp, dict(source(cpp), flags=True))
        except ValueError as error:
            g.custom_signal_excluded_types[name] = str(error)
    for name, t in sorted(signature_types.items()):
        if t['kind'].startswith('flags') and native_type(t) not in used_names:
            enum_name = name[7:-1] if name.startswith('QFlags<') else name
            enum = g.enums.get(enum_name, {})
            if enum.get('public', True) or protected_members.enum_accessible(g, enum_name):
                add(t['bend'] + '.arg', native_type(t), dict(source(name), flags=True))
    if 'QVariant' in g.ids:
        variant = source('QVariant')
        text = source('QString')
        add('variantMap', 'QVariantMap', dict(source('QMap', 'QMap<QString,QVariant>'),
                                            container=True, instantiations=[text, variant]))
        add('variantList', 'QVariantList', dict(source('QList', 'QList<QVariant>'),
                                              container=True, instantiations=[variant]))
    # Compile native container metatypes from the same inventory that drives
    # ordinary methods. Generic Bend constructors select these registrations;
    # they never silently substitute QVariantList for an unknown QList<T>.
    for _, cpp, _ in list(g.custom_signal_arguments):
        if cpp in ('bool', 'qint8', 'quint8', 'qint16', 'quint16', 'int', 'uint',
                   'qint64', 'quint64', 'float', 'double', 'QString'):
            child = source(cpp)
            add(None, 'QList<' + cpp + '>', dict(source('QList', 'QList<' + cpp + '>'),
                                                container=True, instantiations=[child]))
    for t in list(g.conversions.cpp.values()):
        if t['kind'] not in ('list', 'map', 'pair', 'optional', 'array') or 'cpp' not in t:
            continue
        cpp = native_type(t)
        if cpp in used_names or g.conversions.contains(t, ('string_view', 'byte_view', 'latin1_view', 'record')):
            continue
        if any(leaf['kind'] != 'object' and leaf.get('name') in g.classes and not g.classes[leaf['name']].get('public_destructor', True)
               for leaf in _leaves(t)):
            g.custom_signal_excluded_types[cpp] = 'Container element needs a public native destructor'
            continue
        used_names.add(cpp)
        g.custom_signal_arguments.append((None, cpp, t))


def _leaves(t):
    return [t] if not t.get('children') else [leaf for child in t['children'] for leaf in _leaves(child)]


def emit(g):
    if not hasattr(g, 'custom_signal_arguments'):
        return
    g.bend += ['def WireIdentity.encode(value: Wire) -> Wire:', '  value', '']
    g.bend += ['def WireIdentity.wrap(value: Result<&1, &1, U32 & String, Wire>) -> Result<&1, &1, U32 & String, Wire>:', '  value', '']
    import bend_data
    bend_data.emit(g)
    g.bend.append((HERE / 'templates/custom_signals.bend').read_text())
    g.bend.append(bend_data.public(g))
    from module_partitions import schema_dependency
    for public, cpp, t in g.custom_signal_arguments:
        if public is None:
            continue
        from module_partitions import exports_class
        if t.get('name') in g.classes and not exports_class(g, t['name']):
            continue
        enum = g.enums.get(t.get('name'))
        exports = getattr(g, 'partition_export_packages', None)
        if exports and enum and enum.get('package') not in exports:
            continue
        g.bend += [f'def {public}() -> TypeDescriptor:',
            f'  TypeDescriptor{{{t["bend"]}, "{cpp}", value => {t["codec"]}.encode(value), wire => {t["codec"]}.decode(wire), {schema_dependency(g)}}}', '']
    if 'QObject' in g.ids:
        g.bend += ['def qobject() -> TypeDescriptor:', '  QObject.arg()', '']
    if 'QVariant' in g.ids:
        g.bend += ['def variant() -> TypeDescriptor:', '  QVariant.arg()', '']
    if not any(public == 'QChar.arg' for public, _, _ in g.custom_signal_arguments):
        g.bend += ['def QChar.arg() -> TypeDescriptor:', '  qchar()', '']
    for alias, descriptor in [('qint8', 'int8'), ('quint8', 'u8'), ('qint16', 'int16'), ('quint16', 'u16'),
                              ('qint32', 'int32'), ('quint32', 'u32'), ('qint64', 'int64'), ('quint64', 'u64'),
                              ('short', 'int16'), ('ushort', 'u16'), ('int', 'int32'), ('uint', 'u32'),
                              ('float', 'f32'), ('double', 'f64'), ('qsizetype', 'int64')]:
        g.bend += [f'def {alias}() -> TypeDescriptor:', f'  {descriptor}()', '']
    create, connect, emission, available, connect_typed, connect_member = range(g.next_id, g.next_id + 6)
    g.next_id += 6
    g.custom_signal_operations = dict(create=create, connect=connect, emit=emission, available=available,
                                     connect_typed=connect_typed, connect_member=connect_member)
    bodies = {
        create: 'return BendSignalApi::create(r);',
        connect: 'return BendSignalApi::connect(r);',
        emission: 'return BendSignalApi::emit_signal(r);',
        connect_typed: 'return BendSignalApi::connect_typed(r);',
        connect_member: 'return BendSignalApi::connect_member(r);',
    }
    for operation, body in bodies.items():
        g.cases.append(f'case {operation}: {{\n    {body}\n}}')
    g.cases.append(f'case {available}: {{\n    r->result.word = true; return true;\n}}')
    g.emit_effect('Runtime.hasCustomSignals', [], dict(kind='bool', bend='Bool', raw='U32'), available)
    g.emit_effect('QObject.newWithSignals_raw', [('name', dict(kind='string', bend='String', raw='String')),
                  ('signals', WIRE)], OBJECT, create)
    g.bend += ['def QObject.newWithSignals(name: String, signals: List<&1, Signal>) -> Action(QObject):',
               '  do Action<QObject>:', '    schema: Wire <- SignalSchemas.encode(signals)',
               '    QObject.newWithSignals_raw(name, schema)', '']
    g.emit_effect('Signal.emit_raw', [('self', OBJECT), ('declaration', WIRE), ('values', WIRE)],
                  UNIT, emission, has_self=True)
    handler = effect_transport.handler('', '')
    raw = effect_transport.reserve(g, 'Signal.connect', [('self', OBJECT), ('declaration', WIRE),
                                   ('handler', handler)], CONNECTION, connect, has_self=True)
    g.bend += [
        'def Signal.connect(~signal: Signal, ~S: Data, ~handler: S -> SignalArguments.Handler(Signal.arguments(signal)), self: QObject, state: S) -> Action(Connection):',
        '  do Action<Connection>:', '    schema: Wire <- Signal.schema(signal)',
        f'    word: U32 <- {raw["name"]}(S, {connect}, QObject.word(self), schema, pair => run(Unit, Signal.invoke(~signal, ~S, ~handler, pair)), state)',
        '    return Connection{word}', '',
        'def Signal.emit_values(~signal: Signal, self: QObject, values: List<&2, Wire>) -> Action(Unit):',
        '  do Action<Unit>:', '    schema: Wire <- Signal.schema(signal)',
        '    Signal.emit_raw(self, schema, WireSequence{values})', '',
        'def Signal.emit(~signal: Signal, self: QObject) -> SignalArguments.Handler(Signal.arguments(signal)):',
        '  SignalArguments.emit(Signal.arguments(signal), values => Signal.emit_values(~signal, self, values), EncodedArguments.empty(Unit))', '']
    raw = effect_transport.reserve(g, 'Signal.connectWith', [('self', OBJECT), ('declaration', WIRE),
                                   ('connectionType', WORD), ('handler', handler)], CONNECTION, connect_typed, has_self=True)
    g.bend += [
        'def Signal.connectWith(~signal: Signal, ~S: Data, ~handler: S -> SignalArguments.Handler(Signal.arguments(signal)), self: QObject, connectionType: Qt.ConnectionType, state: S) -> Action(Connection):',
        '  do Action<Connection>:', '    schema: Wire <- Signal.schema(signal)',
        f'    word: U32 <- {raw["name"]}(S, {connect_typed}, QObject.word(self), schema, Qt.ConnectionType.word(connectionType), pair => run(Unit, Signal.invoke(~signal, ~S, ~handler, pair)), state)',
        '    return Connection{word}', '']
    g.emit_effect('Signal.connect_member_raw', [('self', OBJECT), ('declaration', WIRE), ('receiver', OBJECT),
                  ('member', WIRE), ('kind', WORD), ('connectionType', WORD)], CONNECTION, connect_member, has_self=True)


def emit_destinations(g):
    if not hasattr(g, 'custom_signal_arguments'):
        return
    for name, descriptor, schema, kind in [('Method', 'Method', 'Method.schema', 0), ('Signal', 'Signal', 'Signal.schema', 1)]:
        g.bend += [
            f'def Signal.connect{name}With(~signal: Signal, ~destination: {descriptor}, self: QObject, receiver: QObject, connectionType: Qt.ConnectionType) -> Action(Connection):',
            '  do Action<Connection>:', '    source: Wire <- Signal.schema(signal)',
            f'    target: Wire <- {schema}(destination)',
            f'    Signal.connect_member_raw(self, source, receiver, target, {kind}, Qt.ConnectionType.word(connectionType))', '',
            f'def Signal.connect{name}(~signal: Signal, ~destination: {descriptor}, self: QObject, receiver: QObject) -> Action(Connection):',
            f'  Signal.connect{name}With(~signal, ~destination, self, receiver, Qt.ConnectionType.AutoConnection())', '']


def cpp(g):
    if not hasattr(g, 'custom_signal_arguments'):
        return ''
    if len(g.custom_signal_arguments) >= (1 << 30):
        raise ValueError('Native argument codecs exceed the type-code range reserved before runtime enums')
    meta, reads, writes, assignments, assignable, registrations = [], [], [], [], [], []
    declarations, definitions = [], []
    def guarded(native, lines):
        return ['#if BQT_HAS_RHI', *lines, '#endif'] if abi_cohorts.required(g, native) else lines
    import metadata_lifetimes
    guards, owned, temporary = [], [], []
    for i, _, native, t in argument_entries(g):
        prefix = f'bqt_native_signal_argument_{i}_'
        current_declarations, current_definitions = [], []
        def helper(suffix, result, parameters, body):
            name = prefix + suffix
            current_declarations.append(f'extern __attribute__((visibility("hidden"))) {result} {name}({parameters});')
            current_definitions.append(f'{result} __attribute__((noinline)) BendSignalApi::{name}({parameters}) {{\n' +
                                       '\n'.join('    ' + line for line in body) + '\n}\n')
            return name
        qualified = qualified_native(g, native)
        meta_helper = helper('meta', 'QMetaType', '',
            [f'static const QMetaType meta = {meta_expression(g, native, t)};', 'return meta;']
            if qualified or t.get('children') else native_meta_type_body(native))
        meta += guarded(native, [f'case {i}: return {meta_helper}();'])
        packed = '*value' if native == 'QVariant' else f'QVariant({meta_helper}(), &*value)'
        read_helper = helper('read', 'QVariant', 'BqtRequest *r, const BqtValue &wire',
            [f'auto value = read_{t["native_codec"]}(r, wire);', f'return value ? {packed} : QVariant();'])
        write_helper = helper('write', 'BqtValue', 'BqtRequest *r, const void *value',
            [f'return write_{t["native_codec"]}(r, *static_cast<{native} const *>(value));'])
        assign_helper = helper('assign', 'bool', 'BqtRequest *r, void *target, const void *source',
            [f'return assign_native<{native}>(r, target, source);'])
        assignable_helper = helper('assignable', 'bool', '', [f'return std::is_copy_assignable_v<{native}>;'])
        reads += guarded(native, [f'case {i}: return {read_helper}(r, wire);'])
        writes += guarded(native, [f'case {i}: return {write_helper}(r, value);'])
        assignments += guarded(native, [f'case {i}: return {assign_helper}(r, target, source);'])
        assignable += guarded(native, [f'case {i}: return {assignable_helper}();'])
        type_helper = None
        if t.get('children') or (t['kind'] == 'object' and not g.classes[t['name']]['qobject']) or (t.get('name') in metadata_lifetimes.VALUES and t['kind'] == 'value'):
            # Guard/snapshot comparisons must not register every unrelated
            # descriptor as a side effect of examining a single QVariant.
            type_helper = helper('type', 'QMetaType', '',
                [f'return BendQualifiedTypes::existing("{meta_name(g, native)}");'] if qualified
                else [f'return QMetaType::fromType<{native}>();'])
        owned_helper = None
        if t.get('children'):
            owned_helper = helper('snapshot', 'QVariant', 'const QVariant &value, unsigned depth',
                [f'auto copy = native_owned_snapshot(*static_cast<const {native} *>(value.constData()), depth + 1);',
                 f'return QVariant({meta_helper}(), &copy);'])
            owned += guarded(native, [f'if (BendQualifiedTypes::compatible(value.metaType(), BendSignalApi::{type_helper}()))',
                      f'    return BendSignalApi::{owned_helper}(value, depth);'])
        guard_body = []
        if t['kind'] == 'object' and not g.classes[t['name']]['qobject']:
            guard_body += [f'auto *pointer = *static_cast<{native} const *>(value.constData());',
                f'if (pointer) snapshot.native_objects.push_back(native_pointer_capture(pointer, {g.ids[t["name"]]}, native_frame));']
            temporary += guarded(native, [f'case {g.ids[t["name"]]}:',
                f'    arguments.borrow_argument(r, static_cast<{native}>(const_cast<void *>(capture.pointer)), {g.ids[t["name"]]}, receiver);',
                '    break;'])
        if t.get('name') in metadata_lifetimes.VALUES and t['kind'] == 'value':
            guard_body += [f'snapshot.guard_metadata(static_cast<const {native} *>(value.constData())->enclosingMetaObject());']
        if t.get('children') and any(leaf['kind'] == 'object' or leaf.get('name') == 'QVariant' or
                                    leaf.get('name') in metadata_lifetimes.VALUES for leaf in _leaves(t)):
            guard_body += [f'const auto &items = *static_cast<const {native} *>(value.constData());']
            if t['kind'] == 'map':
                guard_body += ['for (auto it = items.cbegin(); it != items.cend(); ++it) {',
                           '    snapshot.guard(QVariant::fromValue(it.key()), depth + 1, native_frame);',
                           '    snapshot.guard(QVariant::fromValue(it.value()), depth + 1, native_frame);', '}']
            elif t['kind'] == 'pair':
                guard_body += ['snapshot.guard(QVariant::fromValue(items.first), depth + 1, native_frame);',
                           'snapshot.guard(QVariant::fromValue(items.second), depth + 1, native_frame);']
            elif t['kind'] == 'optional':
                guard_body += ['if (items) snapshot.guard(QVariant::fromValue(*items), depth + 1, native_frame);']
            else:
                guard_body += ['for (const auto &item : items) snapshot.guard(QVariant::fromValue(item), depth + 1, native_frame);']
        guard_helper = None
        if guard_body:
            guard_helper = helper('guard', 'void', 'Snapshot &snapshot, const QVariant &value, unsigned depth, bool native_frame', guard_body)
            guards += guarded(native, [f'else if (BendQualifiedTypes::compatible(value.metaType(), {type_helper}()))',
                                      f'    {guard_helper}(*this, value, depth, native_frame);'])
        if owned_helper or guard_helper:
            match_helper = helper('matches', 'bool', 'QMetaType type',
                [f'const auto expected = {type_helper}();',
                 'return expected.isValid() && BendQualifiedTypes::compatible(type, expected);'])
        else:
            match_helper = None
        functions = [meta_helper, read_helper, write_helper, assign_helper, assignable_helper,
                     match_helper, owned_helper, guard_helper]
        aliases = list(dict.fromkeys(alias for original in native_names(native, t)
                                     for alias in (original, meta_name(g, original))))
        registrations += guarded(native, [f'    {{{i}, "{alias}", ' + ', '.join(
            '&BendSignalApi::' + name if name else 'nullptr' for name in functions) + '},' for alias in aliases])
        declarations += guarded(native, current_declarations)
        definitions += [f'// BQT_AUXILIARY_BEGIN native_signal_arguments {i}\n' +
                        '\n'.join(guarded(native, current_definitions)) + '\n' +
                        f'// BQT_AUXILIARY_END native_signal_arguments {i}\n']
    names = ', '.join('{"' + alias + '", ' + str(index) + '}'
        for index, _, cpp, conversion in argument_entries(g)
        for alias in dict.fromkeys(alias for original in native_names(cpp, conversion)
                                  for alias in (original, meta_name(g, original))))
    import qml_list_properties
    import value_types
    source = ((HERE / 'templates/dynamic_metadata.cpp').read_text() + '\n'
              + (HERE / 'templates/partition_metatypes.cpp').read_text() + '\n'
              + (HERE / 'templates/value_types.cpp').read_text() + '\n' + value_types.declarations()
              + qml_list_properties.cpp(g) + (HERE / 'templates/custom_signals.cpp').read_text())
    for key, value in [('META_TYPES', '\n'.join(meta)), ('READ_VALUES', '\n'.join(reads)),
                       ('WRITE_VALUES', '\n'.join(writes)), ('ASSIGN_VALUES', '\n'.join(assignments)), ('ASSIGNABLE_VALUES', '\n'.join(assignable)), ('TYPE_NAMES', names), ('GUARD_CONTAINERS', '\n'.join(guards)), ('TEMPORARY_POINTERS', '\n'.join(temporary)), ('OWNED_CONTAINER_VALUES', '\n'.join(owned)), ('ARGUMENT_DECLARATIONS', '\n'.join(declarations)), ('ARGUMENT_DEFINITIONS', ''.join(definitions)), ('QOBJECT_ID', str(g.ids['QObject']))]:
        source = source.replace('@' + key + '@', value)
    import runtime_dispatch
    source += '''
#if defined(BQT_NATIVE_PARTITIONS)
static void runtime_register_partition_arguments() {
    static const BendSignalApi::NativeCodec codecs[] = {
''' + '\n'.join(registrations) + '''
    };
    std::lock_guard<std::recursive_mutex> lock(BendSignalApi::partition_codec_mutex);
    for (const auto &codec : codecs) {
        BendSignalApi::partition_codecs.emplace(codec.code, codec);
        BendSignalApi::partition_argument_names.emplace(QMetaObject::normalizedType(codec.name), codec.code);
    }
}
#endif
'''
    return runtime_dispatch.cpp(source)


def inventory(g):
    if not hasattr(g, 'custom_signal_arguments'):
        return dict(available=False)
    return dict(available=True, minimum_qt='6.12.0',
                argument_types={name: t['bend'] for name, _, t in g.custom_signal_arguments if name is not None},
                container_types={cpp: t['bend'] for name, cpp, t in g.custom_signal_arguments if name is None},
                container_policy='Native list/set/map/hash/pair/optional descriptors select compiled instantiations from supported selected signatures; unknown instantiations fail ENOTSUP without QVariant substitution',
                excluded_class_descriptors=g.custom_signal_excluded,
                excluded_value_descriptors=g.custom_signal_excluded_values,
                excluded_type_descriptors=g.custom_signal_excluded_types,
                operations=g.custom_signal_operations,
                base_class='QObject', limits='Qt native metadata index range and available memory',
                metadata_lifetime='Immutable cached schemas live until native payload teardown',
                argument_lifetime='QObject references are borrowed and guarded at emission; native value arguments are scoped copies',
                metadata_abi='Qt 6 moc revision 13; public QMetaObject connection API')
