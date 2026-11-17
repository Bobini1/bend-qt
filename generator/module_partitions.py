"""Separate conflicting native modules behind one generated Bend interface."""
import copy
import re
from pathlib import Path
from types import SimpleNamespace


def function_packages(api, function):
    source = set(re.findall(r'/(Qt[A-Z][A-Za-z0-9]+)/', function.get('source_file', '')))
    if source:
        return {'PySide6.' + module for module in source}
    declarations = {row['name']: row.get('package') for row in [*api['classes'], *api.get('enums', [])]}
    result = set()
    def visit(value):
        if isinstance(value, dict):
            if 'pointers' in value and declarations.get(value.get('name')):
                result.add(declarations[value['name']])
            for child in value.values(): visit(child)
        elif isinstance(value, list):
            for child in value: visit(child)
    visit(function)
    return result


def qualify(g, namespaces):
    """Qualify a module's classes without changing its upstream discovery.

    `namespaces` maps pinned PySide packages to public/native alias namespaces.
    Common classes keep their existing identities in every native partition.
    """
    if 'Global' in g.classes:
        declaration = g.classes.pop('Global')
        g.namespaces.remove('Global')
        groups = {}
        for function in declaration['functions']:
            owners = function_packages(g.api, function)
            choices = {namespaces[package] for package in owners if package in namespaces}
            if len(choices) > 1:
                raise ValueError('A free function has conflicting qualified module origins: ' + function['name'])
            name = next(iter(choices), 'Global')
            groups.setdefault(name, []).append(function)
        for name, functions in groups.items():
            g.classes[name] = dict(declaration, name=name, functions=functions, partition_global=True)
            g.namespaces.append(name)
    replacements = {}
    carriers = {name for name, row in g.classes.items()
                if row.get('shared_cpp') or row.get('future_cpp') or row.get('future_watcher_cpp')}
    for name, cls in g.classes.items():
        namespace = namespaces.get(cls.get('package'))
        if namespace:
            replacements[name] = namespace + '::' + name
    # Typedefs such as the legacy data arrays have no independent class row.
    # Their owning module is recorded on the class using their source type.
    for name, native in g.api.get('typedefs', {}).items():
        owner = next((key for key in replacements if re.search(r'\b' + re.escape(key) + r'\b', native)), None)
        if owner:
            replacements[name] = replacements[owner].split('::', 1)[0] + '::' + name
    if not replacements:
        g.partition_aliases = ''
        return
    pattern = re.compile(r'(?<![A-Za-z0-9_:])(?:' + '|'.join(map(re.escape,
        sorted(replacements, key=len, reverse=True))) + r')(?![A-Za-z0-9_])')

    def text(value):
        return pattern.sub(lambda match: replacements[match[0]], value)

    def rewrite(value):
        if isinstance(value, list):
            return [rewrite(item) for item in value]
        if not isinstance(value, dict):
            return text(value) if isinstance(value, str) else value
        result = {}
        for key, item in value.items():
            # Names of methods, parameters and fields remain identifiers.
            # Native provenance is preserved for coverage and source checks.
            if key in ('name', 'source_file', 'source_signatures', 'package'):
                result[key] = copy.deepcopy(item)
            else:
                result[key] = rewrite(item)
        if ('functions' in value or 'pointers' in value or 'used_bits' in value
                or ('value' in value and value.get('name', '').find('::') >= 0)):
            result['name'] = text(value['name'])
        return result

    g.api = rewrite(g.api)
    g.api['typedefs'] = {text(name): text(native) for name, native in g.api['typedefs'].items()}
    g.classes = {text(name): rewrite(cls) for name, cls in g.classes.items()}
    g.selected = [text(name) for name in g.selected]
    g.excluded_classes = rewrite(g.excluded_classes)
    g.namespaces = [text(name) for name in g.namespaces]
    g.ids = {text(name): number for name, number in g.ids.items()}
    g.enums = {text(name): rewrite(enum) for name, enum in g.enums.items()}
    g.types = {text(name.replace('.', '::')).replace('::', '.'): kind for name, kind in g.types.items()}
    # Qualified type aliases are emitted inside their namespace; they cannot
    # use C++'s unqualified `using Name = ...` declaration at global scope.
    aliases = []
    for name, qualified in sorted(replacements.items()):
        if '::' not in name and name not in carriers:
            namespace, alias = qualified.rsplit('::', 1)
            aliases.append(f'namespace {namespace} {{ using {alias} = ::{name}; }}\n')
    g.partition_aliases = ''.join(aliases)
    g.partition_qualified_types = replacements


def declaring_module(function):
    """The Qt module whose header declares a function, e.g. QtPositioning."""
    match = re.search(r'/(Qt[A-Z0-9][A-Za-z0-9]+)/', function.get('source_file', ''))
    return match[1] if match else None


def member_assignments(groups):
    """Assign members declared by another group's module to that group.

    PySide attaches some free functions to classes of other modules, such as
    QDataStream's stream operators for QGeoCoordinate, declared in a
    QtPositioning header. A group compiles only its own modules' headers and
    their dependencies, so such a member is emitted by the group that owns its
    declaring module, as PySide generates it with that module.

    `groups` holds (name, owned modules, compile modules, api) per group, the
    shared group first. Returns the declaring-module owners and, per group,
    the members it emits for classes it does not own.
    """
    owners = {module: name for name, own, _, _ in groups for module in own}
    available = {name: set(modules) for name, _, modules, _ in groups}
    members = {}
    for index, (name, own, modules, api) in enumerate(groups):
        packages = {'PySide6.' + module for module in own}
        classes = {row['name']: row for row in api['classes']}

        def functions(row, visited):
            # Start from the row itself: a namespace has one row per module.
            visited.add(row['name'])
            yield from row.get('functions', [])
            for base in row.get('bases', []):
                if base not in visited and base in classes:
                    yield from functions(classes[base], visited)

        for row in api['classes']:
            if not (row.get('package') in packages or (index == 0 and not row.get('package'))):
                continue
            for function in functions(row, set()):
                module = declaring_module(function)
                target = owners.get(module)
                if not target or target == name or module in available[name]:
                    continue
                if row.get('package') and row['package'].removeprefix('PySide6.') not in available[target]:
                    raise ValueError('A member of ' + row['name'] + ' is declared by ' + module +
                                     ', whose group cannot compile its class')
                members.setdefault(target, {}).setdefault(row['name'], set()).add(function['minimal_signature'])
    return owners, members


def scoped_api(api, modules, *, root=False, compile_modules=None, module_owners=None, assigned=None):
    """Keep an upstream module's complete API and discovered type dependencies.

    Imported classes retain their declarations for inheritance and conversion,
    while public methods/proxies are emitted by their owning module. There is
    no class catalogue: every owning class and every referenced class comes
    from the pinned extractor model.

    With `compile_modules`, members declared by a header outside them that
    another group owns are left to that group (see member_assignments), and
    `assigned` names the members this group emits for classes it does not own.
    """
    packages = {'PySide6.' + module for module in modules}
    rows = api['classes']
    if compile_modules is not None and module_owners:
        available = set(compile_modules)

        def compiled(function):
            module = declaring_module(function)
            return module not in module_owners or module in available
        # Filter each row: a namespace such as Qt has one row per module.
        rows = [dict(row, functions=[f for f in row.get('functions', []) if compiled(f)]) for row in rows]
    classes = {row['name']: row for row in rows}
    assigned = assigned or {}
    owned = {name for name, row in classes.items()
             if row.get('package') in packages or (root and not row.get('package'))}
    needed = set(owned)
    from adapters import runtime_type_dependencies
    needed.update(name for name in runtime_type_dependencies(needed) if name in classes)
    enum_names = {row['name'] for row in api['enums']}
    needed_enums = set()

    def references(value):
        if isinstance(value, dict):
            if 'pointers' in value and isinstance(value.get('name'), str):
                name = value['name']
                if name in enum_names:
                    needed_enums.add(name)
                if name in classes:
                    needed.add(name)
                else:
                    parent = name.rpartition('::')[0]
                    if parent in classes:
                        needed.add(parent)
            for child in value.values():
                references(child)
        elif isinstance(value, list):
            for child in value:
                references(child)

    visited_bases = set()

    def inherited(name):
        if name in visited_bases or name not in classes:
            return
        visited_bases.add(name); needed.add(name)
        references(classes[name].get('functions', []))
        for base in classes[name].get('bases', []):
            inherited(base)

    for name in [*owned, *assigned]:
        inherited(name)
    functions = [row for row in api.get('global_functions', [])
                 if (function_packages(api, row) & packages) or (root and not function_packages(api, row))]
    references(functions)
    while True:
        previous = len(needed)
        needed.update(name for name in runtime_type_dependencies(needed) if name in classes)
        for name in list(needed):
            row = classes[name]
            needed.update(base for base in row.get('bases', []) if base in classes)
            references(row.get('fields', []))
        if len(needed) == previous:
            break
    result = copy.deepcopy({key: value for key, value in api.items() if key != 'classes'})
    result['classes'] = [copy.deepcopy(row) for row in rows if row['name'] in needed]
    for row in result['classes']:
        if row['name'] in assigned and row['name'] not in owned:
            row['partition_members'] = sorted(assigned[row['name']])
    result['enums'] = [row for row in result['enums'] if row.get('package') in packages
                       or row['name'] in needed_enums or row['name'].rpartition('::')[0] in needed]
    result['global_functions'] = copy.deepcopy(functions)
    result['native_export_packages'] = sorted(packages)
    return result


def exports_class(g, name):
    if g.classes[name].get('partition_global'):
        return True
    packages = getattr(g, 'partition_export_packages', None)
    package = g.classes[name].get('package')
    return not packages or package in packages or (not package and not getattr(g, 'partition_secondary', False))


def assign_type_ids(g, registry):
    for name in g.selected:
        if name not in registry:
            registry[name] = len(registry) + 1
    if len(registry) > 65535:
        raise ValueError('Combined Qt type inventory exceeds the native type-id range')
    g.ids = {name: registry[name] for name in g.selected}


def isolate_metatypes(parts):
    packages = {}
    for part in parts:
        for row in part.api['classes']:
            if row.get('package'):
                packages.setdefault(row['name'], set()).add(row['package'])
    collisions = {name for name, values in packages.items() if len(values) > 1}
    for part in parts:
        g = part.generator
        aliases = {name: name for name in getattr(g, 'partition_qualified_types', {}).values()}
        for row in part.api['classes']:
            name = row['name']
            if name in collisions and name in g.classes:
                namespace = row['package'].removeprefix('PySide6.Qt')
                aliases[name] = namespace + '::' + name
        for name, source in g.api.get('typedefs', {}).items():
            owner = next((key for key in aliases if re.search(r'(?<![A-Za-z0-9_:])' + re.escape(key) + r'(?![A-Za-z0-9_])', source)), None)
            if owner and '::' not in name:
                aliases[name] = aliases[owner].split('::', 1)[0] + '::' + name
        g.partition_metatype_aliases = aliases


def argument_entries(g):
    registry = getattr(g, 'partition_argument_ids', None)
    for local, (public, native, conversion) in enumerate(g.custom_signal_arguments):
        if registry is not None and native not in registry:
            registry[native] = len(registry)
        yield (registry[native] if registry is not None else local), public, native, conversion


def schema_dependency(g):
    module = getattr(g, 'foreign_effect_module', None)
    return ('Internal.Modules.' + module + '.schema()' if module
            else 'Action.pure(Wire, WireScalar{0, 0})')


def emit_loader(g):
    module = getattr(g, 'foreign_effect_module', None)
    if module:
        g.bend += [f'def native_Runtime_load_{module}() -> IO(Result<&1, &1, U32 & String, Unit>):',
                   '  import "' + g.foreign_effect_file + '"', '',
                   f'def Modules.{module}.load() -> Action(Unit):',
                   f'  Action.fromIO(Unit, native_Runtime_load_{module}())', '',
                   f'def Internal.Modules.{module}.schema() -> Action(Wire):',
                   '  do Action<Wire>:', f'    Modules.{module}.load()',
                   '    return WireScalar{0, 0}', '']


def loader_effect(module, *, instance=None):
    effect = 'native_Runtime_load_' + module
    return f'''
#ifdef CID({effect})
static Term bqt_module_load_{module}_run(Env e, Term *f, IoWork *w) {{
    const char *error = bqt_start();
    {f'if (!error) error = bqt_module_ensure(&{instance});' if instance else ''}
    return error ? io_fail(e, ELIBACC, error) : io_done(e, term_pak(CID(Unit), 0));
}}
static void __attribute__((constructor)) bqt_module_load_{module}_register(void) {{
    io_eff(CID({effect}), bqt_module_load_{module}_run);
}}
#endif
'''


def merge_bend(parts):
    """Keep shared definitions once, with the primary partition's operations.

    Definitions are emitted at column zero by the Bend generator. Complete
    blocks, including their indented bodies, are retained without rewriting
    any Bend code. Names belonging to a secondary module remain distinct.
    """
    seen, result = set(), []
    for source in parts:
        starts = list(re.finditer(r'^(?:def|type)\s+([^\s(<:]+)', source, re.M))
        if not starts:
            raise ValueError('A native partition emitted no Bend definitions')
        if not result:
            result.append(source[:starts[0].start()])
        for index, match in enumerate(starts):
            name = match[1]
            if name in seen:
                continue
            seen.add(name)
            result.append(source[match.start():starts[index + 1].start() if index + 1 < len(starts) else len(source)])
    return ''.join(result)


def prepare_generators(records, lock, *, selective=False):
    """Collect each native part with process-wide handle and operation IDs.

    Records supply independently extracted APIs, profiles and namespace maps.
    This function is also used by native fixture controls, so those controls
    exercise the same collection, conversions and typed public definitions.
    """
    from generate import Generator
    import callbacks
    import overload_names
    type_ids, argument_ids, layouts, operations, slots = {}, {}, {}, {}, {}
    parts = []
    for index, record in enumerate(records):
        generator = Generator(record.api, record.profile, overload_names.NameLock())
        if selective:
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', record.name):
                raise ValueError('Invalid native module effect name: ' + record.name)
            generator.foreign_effect_module = record.name
            generator.foreign_effect_file = './qt.c' if index == 0 else './qt-' + record.name + '.c'
        qualify(generator, record.namespaces)
        generator.partition_export_packages = set(record.api.get('native_export_packages', []))
        assign_type_ids(generator, type_ids)
        generator.partition_argument_ids = argument_ids
        generator.partition_secondary = index > 0
        generator.raw_effect_layouts = layouts
        generator.raw_effect_operations = operations
        generator.retention_slots = slots
        parts.append(SimpleNamespace(**vars(record), generator=generator))
    # Synthetic adapter classes, such as QFuture<QStringList> or an array view
    # of Qt3DAnimation::QChannel, have no package unless their element has one,
    # and the shared group exports them. One that only separate groups use is
    # exported by the first of those groups.
    shared, claimed = parts[0].generator.classes if parts else {}, set()
    for part in parts[1:]:
        for name, row in part.generator.classes.items():
            if (not row.get('package') and name not in shared and name not in claimed
                    and row.get('adapter')):
                row['partition_global'] = True
                claimed.add(name)
    reserved = sorted({name for part in parts for name in (*part.generator.selected, *part.generator.enums)})
    isolate_metatypes(parts)
    next_operation = 10
    for part in parts:
        generator = part.generator
        generator.partition_native_names = reserved
        owners = {name for name in generator.classes
                  if exports_class(generator, name) or generator.classes[name].get('partition_members')}
        owners.update(generator.namespaces if not generator.partition_export_packages else
                      [name for name in generator.namespaces if name == 'Global'])
        generator.name_lock = overload_names.NameLock(names=copy.deepcopy({
            name: rows for name, rows in lock.names.items() if name in owners}), removed=copy.deepcopy({
            name: rows for name, rows in lock.removed.items() if name in owners}))
        generator.next_id = next_operation
        part.operation_begin = next_operation
        generator.collect()
        callbacks.prepare(generator)
        overload_names.finalize(generator, generator.name_lock)
        part.bend, _, part.native = generator.emit()
        part.operation_end = next_operation = generator.next_id
    return parts


def effects(parts):
    import effect_transport
    combined = copy.copy(parts[0].generator)
    combined.effects = [line for part in parts for line in part.generator.effects]
    return effect_transport.effects(combined)


def rename_c(source, prefix):
    # Macro identifiers must be renamed too, but dlsym strings and compressed
    # payload bytes must remain exact. Ordinary C lexical tokens suffice here.
    tokens = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*.*?\*/|\b[A-Za-z_]\w*', re.S)
    return tokens.sub(lambda match: prefix + match[0][4:] if match[0].startswith('bqt_') else match[0], source)


def package(parts, abi):
    """Combine compiled native families behind one synchronous C transport.

    Each ELF retains its own local dependency scope. Handles and callbacks use
    the process-wide runtime service. Only the primary payload owns application
    startup/teardown; all family-specific destructors stay loaded for its use.
    """
    templates = Path(__file__).with_name('templates')
    header = '#define BQT_NATIVE_PARTITIONS 1\n' + (templates / 'shared_runtime.h').read_text()
    assembly = [(templates / 'shared_runtime.c').read_text(),
        'static BqtSharedStore bqt_partition_store;\nstatic BqtRuntimeServices bqt_partition_services;\n'
        'static BqtHost bqt_partition_host;\n']
    imports, dispatch, starts = [], [], []
    for index, part in enumerate(parts):
        prefix = f'bqt_part{index}_'
        assembly.append(rename_c(part.embedded, prefix))
        imports += [f'    const char *part{index}_error = {prefix}load_payload();',
                    f'    if (part{index}_error) return part{index}_error;']
        if index:
            dispatch += [f'    if (r->operation >= {part.operation_begin}u && r->operation < {part.operation_end}u) '
                         + '{ ' + prefix + 'abi_call(r); return; }']
        starts += [f'    error = {prefix}abi_start(&bqt_partition_host);',
                   '    if (error) { bqt_part0_abi_stop(); return error; }']
    assembly += ['void bqt_abi_call(BqtRequest *r) {\n' + '\n'.join(dispatch)
                 + '\n    bqt_part0_abi_call(r);\n}',
        'const char *bqt_abi_start(const BqtHost *host) {\n'
        '    if (!bqt_shared_store_init(&bqt_partition_store, &bqt_partition_services)) return "Cannot initialize the shared Qt runtime";\n'
        '    bqt_partition_host = *host;\n    bqt_partition_host.shared_runtime = &bqt_partition_services;\n'
        '    const char *error = NULL;\n' + '\n'.join(starts) + '\n    return NULL;\n}',
        # Qt plugins can use runtime state in late process finalizers. Explicit
        # Qt teardown releases application handles; shared metadata/storage
        # intentionally remains valid until process exit.
        'int bqt_abi_stop(void) { return bqt_part0_abi_stop(); }\n']
    modules = list(dict.fromkeys(module for part in parts for module in part.profile['qt_modules']))
    additional = [module for module in modules if module not in ('QtCore', 'QtGui', 'QtWidgets')]
    libraries = [f'    void *libraries[{len(additional) + 1}] = {{lib}};']
    for index, module in enumerate(additional, 1):
        libraries += [f'    libraries[{index}] = dlopen("libQt6{module[2:]}.so.6", RTLD_NOW | RTLD_LOCAL);',
                      f'    if (!libraries[{index}]) return dlerror();']
    effect = (templates / 'effects.c').read_text()
    for key, value in dict(RUNTIME=header, ABI=abi, ASSEMBLY='\n'.join(assembly),
                           IMPORTS='\n'.join(imports), LIBRARIES='\n'.join(libraries), EFFECTS=effects(parts)).items():
        effect = effect.replace('// @' + key + '@', value)
    return merge_bend([part.bend for part in parts]), effect


def selective_package(parts, abi, *, runtime=None):
    """Emit one interface with separately retained and lazily loaded C modules."""
    templates = Path(__file__).with_name('templates')
    common = '#define BQT_NATIVE_PARTITIONS 1\n' + (templates / 'shared_runtime.h').read_text()
    common += abi + '\n' + (templates / 'native_modules.h').read_text()
    base = parts[0]
    assembly = rename_c(base.embedded, 'bqt_base_') + '\n'
    assembly += (templates / 'shared_runtime.c').read_text() + '\n'
    assembly += (templates / 'native_modules.c').read_text()
    assembly += loader_effect(base.name)
    additional = [module for module in base.profile['qt_modules'] if module not in ('QtCore', 'QtGui', 'QtWidgets')]
    libraries = [f'    void *libraries[{len(additional) + 1}] = {{lib}};']
    for index, module in enumerate(additional, 1):
        libraries += [f'    libraries[{index}] = dlopen("libQt6{module[2:]}.so.6", RTLD_NOW | RTLD_LOCAL);',
                      f'    if (!libraries[{index}]) return dlerror();']
    # Validation is global metadata; only the base's actual foreign effect
    # bodies are in qt.c. Other modules have distinct foreign effect names.
    runtime_c = ''
    if runtime:
        from runtime_deployment import loader
        runtime_c = '#define BQT_BUNDLED_RUNTIME 1\n' + runtime['bundle']['c']
        runtime_c += '\n' + loader(runtime['selection'], base.profile['qt_modules'],
            preload_modules=sorted({module for part in parts for module in part.profile['qt_modules']})) + '\n'
    effect = (templates / 'effects.c').read_text()
    for key, value in dict(RUNTIME=runtime_c + common, ABI='', ASSEMBLY=assembly,
                           IMPORTS='    return bqt_base_load_payload();',
                           LIBRARIES='\n'.join(libraries), EFFECTS=__import__('effect_transport').effects(base.generator)).items():
        effect = effect.replace('// @' + key + '@', value)
    assets = {}
    for part in parts[1:]:
        prefix = 'bqt_' + part.name + '_'
        source = common + '\n' + rename_c(part.embedded, prefix)
        source += f'\nstatic BqtNativeModule {prefix}module = {{\n'
        source += f'    "{part.name}", BQT_QT_RUNTIME, {part.operation_begin}u, {part.operation_end}u,\n'
        source += f'    {prefix}load_payload, {prefix}abi_start, {prefix}abi_call, 0\n}};\n'
        source += f'static void __attribute__((constructor)) {prefix}register(void) {{\n'
        source += f'    (void)FID(native_Runtime_moduleHost);\n'
        if runtime:
            source += '    (void)FID(' + runtime['bundle']['module_effects'][part.name] + ');\n'
        source += f'    bqt_module_register(&{prefix}module);\n}}\n'
        source += loader_effect(part.name, instance=prefix + 'module')
        # Root validation and marshalling helpers are shared by these bodies.
        source += '\n'.join(part.generator.effects)
        assets['qt-' + part.name + '.c'] = source
    bend = merge_bend([part.bend for part in parts])
    bend += '\ndef native_Runtime_moduleHost() -> IO(Unit):\n  import "./qt.c"\n'
    if runtime:
        bend += '\n' + runtime['bundle']['bend']
        assets.update(runtime['bundle']['assets'])
    return dict(bend=bend, c=effect, assets=assets)
