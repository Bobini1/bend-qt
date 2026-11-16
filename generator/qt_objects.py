"""Runtime QObject schemas layered on the generated native subclass wrappers."""
from pathlib import Path
import json
import abi_cohorts
import effect_transport
from module_partitions import argument_entries

HERE = Path(__file__).resolve().parent
WORD = dict(kind='u32', bend='U32', raw='U32')
UNIT = dict(kind='void', bend='Unit', raw='Unit')
WIRE = dict(kind='wire', bend='Wire', raw='Wire', codec='WireIdentity')
OBJECT = dict(kind='object', name='QObject', bend='QObject', raw='U32')
TEXT = dict(kind='string', bend='String', raw='String')
BOOL = dict(kind='bool', bend='Bool', raw='U32')


def eligible(g, c):
    return (g.classes[c['name']]['qobject'] and
            not any(f.get('final_cpp') and f['name'] in ('metaObject', 'qt_metacall', 'qt_metacast')
                    for f in g.inherited(c['name'])))


def static_metadata(g, name):
    # QQmlPropertyMap's observing proxy uses its protected constructor with
    # the runtime schema as the base of its own mutable map metadata.
    return True


def qml_default(g, name):
    return bool(getattr(g, 'runtime_default_constructors', {}).get(name)) and static_metadata(g, name)


def extension_metadata(g, name):
    # Qt's extension proxy assumes a static top metaobject. QQmlPropertyMap
    # keeps an OpenMetaObject above the declared schema; PySide has the same
    # unsupported combination. Ordinary maps and attached maps remain valid.
    return 'QQmlPropertyMap' not in (name, *g.all_bases(name))


def emit(g):
    if not hasattr(g, 'custom_signal_arguments'):
        return
    g.qt_object_bases = [c for c in g.callback_classes if eligible(g, c)]
    import runtime_enums
    runtime_enums.emit(g)
    g.bend += [(HERE / 'templates/qt_object_types.bend').read_text()]
    native_names = {m['bend_name'] for m in g.methods}
    from module_partitions import schema_dependency
    for c in g.qt_object_bases:
        name = c['name'].replace('::', '.')
        if name + '.define' in native_names:
            raise ValueError('Native method conflicts with QObject class declaration: ' + name + '.define')
        g.bend += [f'def {name}.define(name: String, properties: List<&1, Property>) -> ObjectType:',
                   f'  Internal.ObjectType.define(name, QtBase{{{name}, {g.ids[c["name"]]}, {schema_dependency(g)}, value => {name}.word(value), word => {name}{{word}}}}, properties)', '']
    g.qt_object_constructors = []
    for c in g.qt_object_bases:
        for constructor in c.get('schema_constructors', []):
            operation = g.next_id
            g.next_id += 1
            public = constructor['name']
            inputs = [(f'arg{i}', t) for i, t in enumerate(constructor['inputs'])]
            internal = 'Internal.ObjectType.new_' + str(operation)
            from callbacks import ident
            body = f'return RuntimeQtObjects::create_with(r, {constructor["operation"]}, {g.ids[c["name"]]}, &BqtProxy_{ident(c["name"])}::bqt_create_{constructor["operation"]});'
            g.cases.append(f'case {operation}: {{\n    ' + abi_cohorts.operation(g, operation, body) + '\n}')
            g.emit_effect(internal, [('schema', WIRE), *inputs], WORD, operation)
            parameters = ', '.join(('+' if t['raw'] == 'U32 & U32' else '') + name + ': ' + t['bend'] for name, t in inputs)
            arguments = ', '.join(name for name, _ in inputs)
            g.bend += [f'def {public}(~schema: ObjectType' + (', ' + parameters if parameters else '') + ') -> Action(ObjectType.Instance(schema)):',
                       '  do Action<ObjectType.Instance(schema)>:',
                       '    declaration: Wire <- ObjectType.schema(schema)',
                       f'    word: U32 <- {internal}(declaration' + (', ' + arguments if arguments else '') + ')',
                       '    return QtInstance{word}', '']
            g.qt_object_constructors.append(dict(name=public, native_base=c['name'], operation=operation,
                                                  constructor=constructor['operation']))
    operations = [
        ('create_raw', [('schema', WIRE)], WORD, 'create', False),
        ('attach_raw', [('self', WORD), ('schema', WIRE)], WORD, 'attach', True),
        ('cast_raw', [('self', OBJECT), ('schema', WIRE)], WORD, 'cast', True),
        ('get_raw', [('self', OBJECT), ('property', WIRE), ('storage', WORD)], WIRE, 'get_property', True),
        ('set_raw', [('self', OBJECT), ('property', WIRE), ('value', WIRE), ('storage', WORD)], UNIT, 'set_property', True),
        ('notify_raw', [('self', OBJECT), ('property', WIRE)], UNIT, 'notify_property', True),
        ('call_raw', [('self', OBJECT), ('method', WIRE), ('values', WIRE)], WIRE, 'call_method', True),
        ('reset_raw', [('self', OBJECT), ('property', WIRE)], UNIT, 'reset_property', True),
        ('bind_raw', [('self', OBJECT), ('property', WIRE), ('source', OBJECT), ('sourceProperty', WIRE)], UNIT, 'bind_property', True),
        ('unbind_raw', [('self', OBJECT), ('property', WIRE)], UNIT, 'unbind_property', True),
        ('hasBinding_raw', [('self', OBJECT), ('property', WIRE)], BOOL, 'has_binding', True),
    ]
    g.qt_object_operations = {}
    for public, params, result, native, self in operations:
        operation = g.next_id
        g.next_id += 1
        g.qt_object_operations[native] = operation
        g.cases.append(f'case {operation}: {{\n    return RuntimeQtObjects::{native}(r);\n}}')
        g.emit_effect('ObjectType.' + public, params, result, operation, has_self=self)
    g.bend += [(HERE / 'templates/qt_objects.bend').read_text()]
    import custom_signals
    custom_signals.emit_destinations(g)
    operation = g.next_id
    g.next_id += 1
    g.qt_object_operations['install'] = operation
    handler = effect_transport.handler('', '')
    raw = effect_transport.reserve(g, 'ObjectType.install', [('self', OBJECT), ('member', WIRE),
                                   ('kind', WORD), ('handler', handler)], UNIT, operation, has_self=True)
    g.cases.append(f'case {operation}: {{\n    return RuntimeQtObjects::install(r);\n}}')
    for public, descriptor, callback, signature, kind in [
        ('Method.handle', 'method: Method', 'method', 'Method.Handler(~method)', 0),
        ('Property.handleGetter', 'property: Property', 'Property.getter(property)', 'Method.Handler(~Property.getter(property))', 1),
        ('Property.handleSetter', 'property: Property', 'Property.setter(property)', 'Method.Handler(~Property.setter(property))', 2),
        ('Property.handleResetter', 'property: Property', 'Property.resetter(property)', 'Method.Handler(~Property.resetter(property))', 3),
        ('Property.handleBinding', 'property: Property', 'Property.getter(property)', 'Method.Handler(~Property.getter(property))', 4),
    ]:
        schema = 'Method.schema(method)' if kind == 0 else 'Property.schema(property)'
        g.bend += [f'def {public}(~{descriptor}, ~S: Data, ~f: S -> {signature}, self: QObject, state: S) -> Action(Unit):',
            '  do Action<Unit>:', f'    schema: Wire <- {schema}',
            f'    {raw["name"]}(S, {operation}, QObject.word(self), schema, {kind}, pair => run(Unit, Method.invoke(~{callback}, ~S, ~f, pair)), state)', '']
    # Script singleton convenience APIs also use registration handles when
    # virtual QML callback support is disabled in a focused profile.
    g.bend += [(HERE / 'templates/qml_registrations.bend').read_text()]
    if g.callback_qml:
        params = [('schema', WIRE), ('uri', TEXT), ('major', WORD), ('minor', WORD), ('name', TEXT)]
        for public, tail, function in [
            ('singleton_raw', [('instance', OBJECT), ('mode', WORD), ('revision', WIRE)], 'register_singleton'),
            ('factory_raw', [('revision', WIRE), ('handler', handler)], 'register_factory'),
            ('type_raw', [], 'register_type'),
        ]:
            operation = g.next_id; g.next_id += 1
            g.qt_object_operations[function] = operation
            g.cases.append(f'case {operation}: {{\n    return RuntimeQtObjects::{function}(r);\n}}')
            if public != 'factory_raw':
                g.emit_effect('Qml.' + public, params + tail, OBJECT, operation)
            else:
                raw = effect_transport.reserve(g, 'Qml.' + public, params + tail, OBJECT, operation)
                g.bend += [
                    'def Internal.Qml.registerSingletonFactoryRevision(~object: ObjectType, ~S: Data, ~f: S -> Method.Handler(~Qml.factoryMethod(object)), uri: String, major: U32, minor: U32, name: String, revisionMajor: U32, revisionMinor: U32, state: S) -> Action(Qml.Registration(object)):',
                    '  do Action<Qml.Registration(object)>:', '    schema: Wire <- ObjectType.qmlSchema(object)',
                    f'    word: U32 <- {raw["name"]}(S, {operation}, 0, schema, uri, major, minor, name, WireScalar{{revisionMajor, revisionMinor}}, pair => run(Unit, Method.invoke(~Qml.factoryMethod(object), ~S, ~f, pair)), state)',
                    '    return QmlRegistration{word}', '',
                    'def Qml.registerSingletonFactoryVersionRevision(~object: ObjectType, ~S: Data, ~f: S -> Method.Handler(~Qml.factoryMethod(object)), uri: String, major: U32, minor: U32, name: String, revisionMajor: U32, revisionMinor: U32, state: S) -> Action(Qml.Registration(object)):',
                    '  Internal.Qml.registerSingletonFactoryRevision(~object, ~S, ~f, uri, major, minor, name, Internal.Revision.major(revisionMajor), revisionMinor, state)', '',
                    'def Qml.registerSingletonFactoryRevision(~object: ObjectType, ~S: Data, ~f: S -> Method.Handler(~Qml.factoryMethod(object)), uri: String, major: U32, minor: U32, name: String, revision: U32, state: S) -> Action(Qml.Registration(object)):',
                    '  Internal.Qml.registerSingletonFactoryRevision(~object, ~S, ~f, uri, major, minor, name, 65535, revision, state)', '',
                    'def Qml.registerSingletonFactory(~object: ObjectType, ~S: Data, ~f: S -> Method.Handler(~Qml.factoryMethod(object)), uri: String, major: U32, minor: U32, name: String, state: S) -> Action(Qml.Registration(object)):',
                    '  Internal.Qml.registerSingletonFactoryRevision(~object, ~S, ~f, uri, major, minor, name, 65535, 0, state)', '']
        for public, arguments, function in [
            ('type_mode_raw', params + [('mode', WORD), ('reason', TEXT)], 'register_type_mode'),
            ('unavailable_raw', [('uri', TEXT), ('major', WORD), ('minor', WORD),
                                 ('name', TEXT), ('reason', TEXT)], 'register_unavailable'),
        ]:
            operation = g.next_id; g.next_id += 1
            g.qt_object_operations[function] = operation
            g.cases.append(f'case {operation}: {{\n    return RuntimeQtObjects::{function}(r);\n}}')
            g.emit_effect('Qml.' + public, arguments, OBJECT, operation)
        operation = g.next_id; g.next_id += 1
        g.qt_object_operations['related_object'] = operation
        g.cases.append(f'case {operation}: {{\n    return RuntimeQtObjects::related_object(r);\n}}')
        g.emit_effect('Qml.related_raw', [('self', OBJECT), ('target', OBJECT), ('schema', WIRE), ('kind', WORD)], WORD, operation, has_self=True)
        operation = g.next_id; g.next_id += 1
        g.qt_object_operations['register_type_revision'] = operation
        g.cases.append(f'case {operation}: {{\n    return RuntimeQtObjects::register_type_revision(r);\n}}')
        g.emit_effect('Qml.type_revision_raw', params + [('revision', WIRE)], OBJECT, operation)
        g.bend += [(HERE / 'templates/qt_object_qml.bend').read_text()]
        operation = g.next_id; g.next_id += 1
        g.qt_object_operations['install_qml'] = operation
        g.cases.append(f'case {operation}: {{\n    return RuntimeQtObjects::install_qml(r);\n}}')
        raw = effect_transport.reserve(g, 'Qml.install', [('self', OBJECT), ('schema', WIRE), ('kind', WORD), ('handler', handler)], UNIT, operation, has_self=True)
        for public, descriptor, kind in [('handleCreate', 'creationMethod', 0), ('handleAttached', 'attachedMethod', 1), ('handleExtension', 'extensionMethod', 2), ('handleConstructor', 'constructorMethod', 3)]:
            g.bend += [f'def Qml.{public}(~object: ObjectType, ~S: Data, ~f: S -> Method.Handler(~Qml.{descriptor}(object)), registration: Qml.Registration(object), state: S) -> Action(Unit):',
                '  do Action<Unit>:', '    schema: Wire <- ObjectType.qmlSchema(object)',
                f'    {raw["name"]}(S, {operation}, Internal.Qml.registrationWord(ObjectType.name(object), registration), schema, {kind}, pair => run(Unit, Method.invoke(~Qml.{descriptor}(object), ~S, ~f, pair)), state)', '']
    g.bend += [(HERE / 'templates/object_type_access.bend').read_text()]


def _base_info_parts(g):
    from callbacks import ident
    base_cases, base_declarations, base_factories = [], [], []
    for c in g.qt_object_bases:
        name = c['name']
        default = getattr(g, 'runtime_default_constructors', {}).get(name, 0)
        factory = f'&BqtProxy_{ident(name)}::bqt_create_{default}' if default else 'nullptr'
        expression = f'base_info_for<BqtProxy_{ident(name)}, {"true" if qml_default(g, name) else "false"}>({g.ids[name]}, &{name}::staticMetaObject, {factory}, {"true" if static_metadata(g, name) else "false"}, {"true" if extension_metadata(g, name) else "false"})'
        helper = f'bqt_qml_base_info_factory_{g.ids[name]}'
        base_declarations.append(f'extern __attribute__((visibility("hidden"))) BaseInfo {helper}();')
        definition = f'RuntimeQtObjects::BaseInfo __attribute__((noinline)) RuntimeQtObjects::{helper}() {{\n    return {expression};\n}}\n'
        line = f'case {g.ids[name]}: return {helper}();'
        if abi_cohorts.required(g, expression):
            definition = '#if BQT_HAS_RHI\n' + definition + '#endif\n'
            line = '#if BQT_HAS_RHI\n' + line + '\n#endif'
        base_factories.append(f'// BQT_AUXILIARY_BEGIN qml_base_info {g.ids[name]}\n' + definition +
                              f'// BQT_AUXILIARY_END qml_base_info {g.ids[name]}\n')
        base_cases.append(line)
    return base_cases, base_declarations, base_factories


def _binding_factory_parts(g):
    binding_cases, binding_declarations, binding_factories = [], [], []
    for index, _, native, _ in argument_entries(g):
        factory = f'bqt_property_binding_factory_{index}'
        signature = f'std::shared_ptr<BendPropertyBindings::Storage> {factory}(QMetaType type, BendPropertyBindings::Read read, BendPropertyBindings::Write write)'
        binding_declarations.append('extern ' + signature + ';')
        definition = signature.replace(factory, '__attribute__((noinline)) ' + factory) + ' {\n' + \
            f'    return BendPropertyBindings::make<{native}>(type, std::move(read), std::move(write));\n}}\n'
        if abi_cohorts.required(g, native): definition = '#if BQT_HAS_RHI\n' + definition + '#endif\n'
        binding_factories.append(f'// BQT_AUXILIARY_BEGIN property_bindings {index}\n' + definition +
                                 f'// BQT_AUXILIARY_END property_bindings {index}\n')
        line = f'case {index}: return {factory}(type, std::move(read), std::move(write));'
        if abi_cohorts.required(g, native): line = '#if BQT_HAS_RHI\n' + line + '\n#endif'
        binding_cases.append(line)
    return binding_cases, binding_declarations, binding_factories


def cpp(g):
    if not hasattr(g, 'qt_object_bases'):
        return ''
    base_cases, base_declarations, base_factories = _base_info_parts(g)
    native_names = sorted(set(getattr(g, 'partition_native_names', [])) | set(g.selected) | set(g.enums) | {native for _, native, _ in g.custom_signal_arguments})
    binding_cases, binding_declarations, binding_factories = _binding_factory_parts(g)
    import runtime_enums
    import qml_list_properties
    source = (('' if g.callback_qml else (HERE / 'templates/property_bindings.cpp').read_text()) + '\n' +
              '\n'.join(binding_declarations) + '\n' + ''.join(binding_factories) +
              runtime_enums.cpp(g) + (HERE / 'templates/qt_objects.cpp').read_text() + ''.join(base_factories) + qml_list_properties.runtime_cpp(g) +
              (HERE / 'templates/qt_object_qml.cpp').read_text())
    source = source.replace('@NATIVE_CLASS_NAMES@', ', '.join(json.dumps(name) for name in native_names)).replace(
        '@HAS_QML@', '1' if g.callback_qml else '0').replace('@BASE_DECLARATIONS@', '\n'.join(base_declarations)).replace('@BASE_CASES@', '\n'.join(base_cases)).replace('@BINDING_CASES@', '\n'.join(binding_cases)).replace(
        '@QOBJECT_ID@', str(g.ids['QObject'])).replace('@QML_ENGINE_ID@', str(g.ids.get('QQmlEngine', g.ids['QObject'])))
    registrations = []
    for cls in g.qt_object_bases:
        name, number = cls['name'], g.ids[cls['name']]
        line = f'    RuntimeQtObjects::partition_bases.emplace({number}, &RuntimeQtObjects::bqt_qml_base_info_factory_{number});'
        registrations += ['#if BQT_HAS_RHI', line, '#endif'] if abi_cohorts.required(g, name) else [line]
    for index, _, native, _ in argument_entries(g):
        line = f'    RuntimeQtObjects::partition_bindings.emplace({index}, &bqt_property_binding_factory_{index});'
        registrations += ['#if BQT_HAS_RHI', line, '#endif'] if abi_cohorts.required(g, native) else [line]
    source += '\n#if defined(BQT_NATIVE_PARTITIONS)\nstatic void runtime_register_partition_bases() {\n' + '\n'.join(registrations) + '\n}\n#endif\n'
    import runtime_dispatch
    return runtime_dispatch.cpp(source)


def inventory(g):
    bases = {c['name']: dict(
        define=c['name'].replace('::', '.') + '.define',
        default_constructor=bool(getattr(g, 'runtime_default_constructors', {}).get(c['name'])),
        qml_default_constructor=qml_default(g, c['name']),
        native_proxy_constructible=getattr(g, 'callback_native_constructible', {}).get(c['name']))
        for c in getattr(g, 'qt_object_bases', [])}
    return dict(available=True, bases=bases,
        derive='ObjectType.derive(~parentSchema, name, properties)',
        constructors=getattr(g, 'qt_object_constructors', []),
        operations=getattr(g, 'qt_object_operations', {}),
        members='Stored and accessor properties, authored typed QQmlListProperty views, every Qt property attribute, typed notifications, bindings, named methods, class info, enums and native virtual handlers',
        property_attributes=['READ', 'WRITE', 'MEMBER', 'RESET', 'NOTIFY', 'REVISION', 'DESIGNABLE', 'SCRIPTABLE', 'STORED', 'USER', 'BINDABLE', 'CONSTANT', 'FINAL', 'VIRTUAL', 'OVERRIDE', 'REQUIRED'],
        qml_singletons=['existing instance for one engine', 'default instance per engine', 'typed Bend factory per engine'] if g.callback_qml else [],
        qml_types=['creatable native QObject proxies', 'uncreatable types', 'anonymous types', 'unavailable types', 'typed per-instance initializer', 'attached properties', 'extension objects', 'typed QML lists', 'metadata revisions'] if g.callback_qml else [],
        qml_construction='Default native construction or a typed Bend pre-construction handler using schema-aware constructors; initializers run before QML bindings',
        metadata_abi='Qt 6 moc revision 13 and public Qt connection/registration header ABI; available in the public payload',
        property_and_return_types='Supported native types with owning copies; nondefault backing fields need store or a getter; native method result buffers require copy assignment',
        native_base_policy='Native proxies use their declared metadata; QQmlPropertyMap open metadata is constructed on the runtime schema and preserved; Qt cannot use that open metadata as QML extension metadata',
        schema_lifetime='Immutable process-lifetime metadata and registered pointer metatypes',
        class_names='One consistent schema per name; bound native QObject names and ancestor-name reuse are rejected with EEXIST',
        enum_types='Bend-authored scoped or unscoped Q_ENUM/Q_FLAG declarations with distinct native metatypes, signed or unsigned 32/64-bit storage, standalone immutable namespace metadata, QMetaEnum and QML access',
        public_dispatch='Property and method descriptors; numeric Qt meta-call indices remain internal')
