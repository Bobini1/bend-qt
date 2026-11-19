"""Build the single distribution from compatible, selectively retained modules."""
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from portable_paths import portable
from qt_licenses import Inventory, allows


def plan(profile, qt):
    requested = set(profile['qt_modules'])
    configured = profile['native_modules']
    claimed, parts = set(), []
    for row in configured:
        modules = set(row['qt_modules']) & requested
        if not modules:
            continue
        if modules & claimed:
            raise ValueError('Native module groups must partition the selected Qt modules')
        claimed.update(modules)
        parts.append(dict(row, qt_modules=sorted(modules)))
    base = sorted(requested - claimed)
    if 'QtCore' not in base:
        raise ValueError('The shared native module needs Qt Core')
    Inventory(qt).require(base, 'lgpl')
    names = [row['name'] for row in parts]
    if 'base' in names or len(names) != len(set(names)):
        raise ValueError('Native module group names must be unique and cannot use base')
    return [dict(name='base', qt_modules=base, namespaces={}), *parts]


def merged_lock(parts, original):
    from overload_names import NameLock
    result = NameLock(original.path, removed=copy.deepcopy(original.removed))
    for part in parts:
        current = part.generator.name_lock
        for attribute in ('names', 'removed'):
            target = getattr(result, attribute)
            for owner, rows in getattr(current, attribute).items():
                for key, value in rows.items():
                    preferred = getattr(part, 'lock_preferences', {}).get((owner, key))
                    if preferred is not None and attribute == 'names':
                        if parts[preferred] is part:
                            target.setdefault(owner, {})[key] = copy.deepcopy(value)
                        continue
                    if key in target.setdefault(owner, {}) and target[owner][key] != value:
                        raise ValueError('Native modules disagree about a public name: ' + owner + '/' + key)
                    target[owner][key] = copy.deepcopy(value)
        for attribute in ('created', 'carried', 'tombstoned', 'reshaped'):
            getattr(result, attribute).extend(getattr(current, attribute))
    missing = set(original.names) - set(result.names)
    if missing:
        raise ValueError('Native module selection lost locked owners: ' + ', '.join(sorted(missing)))
    # A restored entry must not remain retired in a different partition. A
    # class whose members span groups (see member_assignments) retires the
    # other group's members in each group's own lock.
    for owner, rows in result.names.items():
        for key in rows:
            result.removed.get(owner, {}).pop(key, None)
    current = {(owner, name) for owner, rows in result.names.items() for name, _ in rows.values()}
    result.tombstoned = [row for row in result.tombstoned if (row[0], row[1]) not in current]
    return result


def runtime_owners(prepared, parts, qt):
    """Attribute files by module roots and actual ELF dependency closure."""
    qt = Path(qt).resolve()
    selection = prepared['selection']
    binaries = selection['files']; dependencies = selection['dependencies']
    roots, evidence_owners = {}, {}
    module_groups = {module: part.name for part in parts for module in part.owned_modules}
    inventory = Inventory(qt)
    for part in parts:
        for module in part.owned_modules:
            evidence = inventory.modules.get(module, {}).get('evidence')
            if evidence:
                evidence_owners.setdefault(evidence, set()).add(part.name)
            path = qt / 'lib' / ('lib' + module.replace('Qt', 'Qt6', 1) + '.so.6')
            if path.is_file():
                relative = path.resolve().relative_to(qt).as_posix()
                if relative not in binaries:
                    raise ValueError('The selected runtime lacks a native module: ' + module)
                roots[relative] = part.name

    def optional_dependencies(name, active=None):
        if name in roots:
            return {roots[name]} - {'base'}
        active = set() if active is None else active
        if name in active:
            raise ValueError('Cyclic native runtime ownership: ' + name)
        return set().union(*(optional_dependencies(child, active | {name})
                             for child in dependencies.get(name, [])))

    # A group needs the groups owning its compiled modules: Multimedia needs Gui.
    needs = {part.name: {module_groups[module] for module in
                         getattr(part, 'profile', {}).get('qt_modules', part.owned_modules)
                         if module in module_groups} - {part.name} for part in parts}
    # ...and the groups its own libraries link, such as WebEngineQuick -> Quick.
    def linked(name, seen):
        for child in dependencies.get(name, []):
            if child not in seen:
                seen.add(child)
                linked(child, seen)
        return seen
    for library, group in roots.items():
        needs.setdefault(group, set()).update({roots[child] for child in linked(library, set())
                                               if child in roots} - {group})

    def ancestors(group, seen=None):
        seen = set() if seen is None else seen
        for parent in needs.get(group, ()):
            if parent not in seen:
                seen.add(parent)
                ancestors(parent, seen)
        return seen

    def specific(groups):
        # A plugin needing Multimedia and Gui belongs to Multimedia alone.
        return {group for group in groups if not any(group in ancestors(other) for other in groups if other != group)}

    def general(groups):
        # An asset that Quick and QuickWidgets list belongs to Quick; groups
        # built on Quick receive it with Quick's files.
        return {group for group in groups if not any(other in ancestors(group) for other in groups if other != group)}

    def attribute(linked, repository):
        """The groups of a file outside the selected modules.

        Prefer the most general group of its own repository that provides
        everything it links: Qt.labs.platform links Quick and Widgets, so it
        belongs to QuickWidgets, not to Quick or Widgets. Otherwise keep its
        repository's groups among those it links (Qt3DQuick: Qt3D), or the most
        specific groups it links.
        """
        linked, repository = linked - {'base'}, repository - {'base'}
        covering = {group for group in repository if linked - {group} <= ancestors(group)}
        if covering:
            return {group for group in covering if not any(other in ancestors(group) for other in covering if other != group)}
        return specific(repository & linked) or specific(linked) or repository

    owners = {}
    for name, row in binaries.items():
        evidence = evidence_owners.get(row.get('evidence'), set())
        explicit = {module_groups[module] for module in row.get('modules', []) if module in module_groups}
        if name in roots:
            choices = {roots[name]}
        elif explicit:
            choices = explicit
        else:
            # A library outside the selected modules, such as Qt3DQuick, belongs
            # to its repository's groups among those it builds on: Qt3D, not
            # every group (Gui, Quick) it links.
            choices = attribute(optional_dependencies(name), evidence)
        if choices:
            owners[name] = specific(choices - {'base'}) or {'base'}
        else:
            # Private/dependency-only libraries inherit their actual users.
            # They must not become shared merely because they lack an
            # independently selected public Qt module.
            owners[name] = set()
    # A file's dependencies travel with every module that needs that file.
    def propagate(*, libraries_only=False):
        while True:
            changed = False
            for name, children in dependencies.items():
                if libraries_only and not name.startswith('lib/'):
                    continue
                for child in children:
                    before = len(owners[child]); owners[child].update(owners[name])
                    changed |= before != len(owners[child])
            if not changed:
                break
    # Each file's own attribution, before users' groups propagate into it.
    attributed = {name: set(groups) for name, groups in owners.items()}
    propagate(libraries_only=True)
    # Dependency-only Qt libraries can acquire their owners from another
    # library's users. Resolve plugins after that pass, so e.g. QuickTimeline's
    # QML plugin follows its actual Quick3D owner instead of defaulting to Core.
    def dependency_owner(child):
        # A Qt library's own group, not every group that uses the library:
        # QuickTemplates2 belongs to Quick although LabsStyleKit uses it too.
        own = {roots[child]} if child in roots else (attributed.get(child) or owners[child])
        return {'base'} if 'base' in own else own

    for name in binaries:
        if name.startswith('lib/'):
            continue
        explicit = {module_groups[module] for module in binaries[name].get('modules', []) if module in module_groups}
        if explicit:
            # A recorded module, e.g. the WebView plugin's QtWebView, decides.
            owners[name] = specific(explicit - {'base'}) or {'base'}
            continue
        # Multimedia's QML plugin links Quick and Multimedia; it belongs to the
        # group of its own repository, Multimedia.
        linked = owners[name] | set().union(*(dependency_owner(child) for child in dependencies.get(name, [])))
        owners[name] = attribute(linked, evidence_owners.get(binaries[name].get('evidence'), set())) or {'base'}
    propagate()
    for name, row in prepared['manifest'].get('assets', {}).items():
        directory = str(Path(name).parent)
        nearby = [value for path, value in owners.items() if path in binaries and str(Path(path).parent) == directory]
        native_owners = set().union(*nearby)
        if row.get('modules'):
            unknown = set(row['modules']) - set(module_groups)
            if unknown:
                raise ValueError('Runtime data names unselected Qt modules: ' + repr(unknown))
            choices = {module_groups[module] for module in row['modules']} | native_owners
        else:
            choices = native_owners or {'base'}
        owners[name] = general(choices - {'base'}) or {'base'}
    assets = prepared['manifest'].get('assets', {})
    qml_modules = {row['provenance']['uri']: name.rsplit('/', 1)[0]
                   for name, row in assets.items()
                   if row.get('provenance', {}).get('kind') == 'generated-qmldir'}
    directories = {directory: uri for uri, directory in qml_modules.items()}
    qml_files = {uri: [] for uri in qml_modules}
    for name in [*binaries, *assets]:
        if not name.startswith('qml/'):
            continue
        directory = Path(name).parent
        while directory != Path('.'):
            if directory.as_posix() in directories:
                qml_files[directories[directory.as_posix()]].append(name)
                break
            directory = directory.parent
    # QML dependencies do not necessarily appear in ELF DT_NEEDED. Propagate
    # the importing file's module owners to the dependency's files and plugin,
    # then include the plugin's actual ELF dependencies too. Optional imports
    # remain optional, as in Qt's own qmldir semantics.
    while True:
        changed = False
        for name, row in assets.items():
            for dependency in row.get('qml_imports', []):
                if dependency.get('optional'):
                    continue
                uri = dependency['uri']
                if uri not in qml_files:
                    # Qt also writes C++ module target names to DEPENDENCIES
                    # (e.g. QtCanvasPainter and QtQuickControls2). Those are
                    # native library dependencies rather than QML URIs.
                    if uri in module_groups:
                        library = qt / 'lib' / ('libQt6' + uri[2:] + '.so.6')
                        child = library.resolve().relative_to(qt).as_posix()
                        if child in owners:
                            before = len(owners[child]); owners[child].update(owners[name])
                            changed |= before != len(owners[child])
                            continue
                    raise ValueError('A bundled QML dependency is absent: ' + name + ' -> ' + uri)
                for child in qml_files[uri]:
                    before = len(owners[child]); owners[child].update(owners[name])
                    changed |= before != len(owners[child])
        if not changed:
            break
    propagate()
    # A component notice and its SBOM travel with the files they cover, so a
    # Core-only program does not carry, e.g., WebEngine's notices. A notice
    # covering any shared-group file stays with the shared group.
    source_rows = prepared['manifest'].get('sources', {})
    covered = {}
    for name, row in {**binaries, **assets}.items():
        sources = [*row.get('sources', []), *([row['source']] if row.get('source') else []),
                   *(root['downloadLocation'] for root in row.get('repositories', []))]
        notices = row.get('notices') or [notice for source in sources
                                         for notice in source_rows.get(source, {}).get('notices', [])]
        if row.get('evidence'):
            notices = [*notices, 'notices/sbom/' + Path(row['evidence']).name]
        for notice in notices:
            if isinstance(notice, str) and owners.get(name):
                covered.setdefault(notice, set()).update(owners[name])
    for name in prepared['files']:
        if name.startswith('notices/') and name in covered:
            owners.setdefault(name, covered[name])
        owners.setdefault(name, {'base'})
    for name, row in {**binaries, **prepared['manifest'].get('assets', {})}.items():
        if not owners[name]:
            if allows(row['expression'], 'lgpl') is True:
                owners[name] = {'base'}
            else:
                raise ValueError('A restricted runtime file has no selected owning module: ' + name)
        if 'base' in owners[name] and allows(row['expression'], 'lgpl') is not True:
            raise ValueError('A Core-only consumer would retain restricted Qt code: ' + name)
    # A group's program also runs on the files of the groups it builds on: a
    # Widgets program needs Gui's platform plugins even if it calls no QtGui API.
    for name, groups in owners.items():
        if 'base' not in groups:
            owners[name] = groups | {group for group in needs if groups & ancestors(group)}
    return owners


def combined_coverage(reports, parts, bundle, licensing):
    """Preserve complete per-module evidence and expose one public inventory."""
    result = copy.deepcopy(reports[0])
    result['native_modules'] = [dict(name=part.name, qt_modules=part.owned_modules,
        operation_begin=part.operation_begin, operation_end=part.operation_end,
        coverage=report) for part, report in zip(parts, reports)]
    for name in ('classes', 'namespaces', 'generated_enums', 'container_conversions'):
        result[name] = sorted({value for report in reports for value in report[name]})
    for name in ('generated', 'excluded', 'excluded_classes', 'extraction_omissions', 'merged_overloads'):
        seen, rows = set(), []
        for report in reports:
            for row in report[name]:
                key = row['bend_name'] if name == 'generated' else json.dumps(row, sort_keys=True)
                if key not in seen:
                    seen.add(key); rows.append(row)
        result[name] = rows
    result['generated_count'] = len(result['generated'])
    result['generated_native_method_count'] = len({row['operation'] for row in result['generated']})
    result['qt_modules'] = sorted({module for part in parts for module in part.owned_modules})
    result['qt_licensing'] = licensing
    result['bundled_runtime'] = bundle['manifest'] if bundle else None
    result['full_coverage'] = False
    result['native_payload'] = dict(selective=True,
        modules={part.name: report['native_payload'] for part, report in zip(parts, reports)})
    result['external_symbol_count'] = sum(report['external_symbol_count'] for report in reports)
    # Aggregate the lists consumed by existing audits, retaining every complete
    # module report above for module-specific operation/policy dictionaries.
    for name in ('callbacks', 'native_coverage'):
        for key, value in result[name].items():
            if isinstance(value, list):
                seen, merged = set(), []
                for report in reports:
                    for row in report[name].get(key, []):
                        identity = json.dumps(row, sort_keys=True)
                        if identity not in seen:
                            seen.add(identity); merged.append(row)
                result[name][key] = merged
    return result


def generate(args, profile, source_inputs, prepared_release):
    import generate as driver
    import callbacks
    import module_partitions
    import native_objects
    import output_files
    import overload_names
    import qt_targets
    import runtime_release
    from backend import compiler_flags, compile_backend, validate_backend
    from lifetime import evaluate_tables
    from shared_state import transform
    from upstream import prepare

    extraction_identity = driver.extraction_inputs(args.profile)
    reviewed_digest = hashlib.sha256(args.reviewed_name_removals.read_bytes()).hexdigest() if args.reviewed_name_removals else None
    groups = plan(profile, args.qt_prefix)
    args.work.mkdir(parents=True, exist_ok=True)
    driver.json_write(args.work / 'module-plan.json', groups)
    separate = {module for row in groups if row.get('separate_headers') for module in row['qt_modules']}
    primary_modules = [module for module in profile['qt_modules'] if module not in separate]
    primary_profile = dict(profile, qt_modules=primary_modules)
    primary = driver.extract_api(args, primary_profile, primary_modules, args.work)
    api, _, _, _, _ = primary
    records, snapshots, staged = [], {}, []
    for index, group in enumerate(groups):
        work = args.work / 'modules' / group['name']; work.mkdir(parents=True, exist_ok=True)
        own = group['qt_modules']
        # Each group compiles its own modules, Qt Core and their type-system
        # dependencies; the shared group needs no GUI module.
        selected = sorted(set(own) | {'QtCore'})
        part_profile = dict(profile, qt_modules=selected)
        part_profile.pop('native_modules', None)
        if group.get('separate_headers'):
            raw, headers, modules, upstream, logs = driver.extract_api(args, part_profile, selected, work)
        else:
            raw = api
            headers, _, modules, _, upstream = prepare(args.pyside_source, args.qt_prefix, selected, work,
                limited_abi=profile.get('limited_abi', False))
            logs = primary[4]
        part_profile['qt_modules'] = modules
        staged.append((index, group, work, own, part_profile, raw, headers, modules, upstream, logs))
    module_owners, assigned = module_partitions.member_assignments(
        [(group['name'], own, modules, raw) for _, group, _, own, _, raw, _, modules, _, _ in staged])
    driver.json_write(args.work / 'module-members.json',
                      {group: {name: sorted(rows) for name, rows in classes.items()} for group, classes in assigned.items()})
    for index, group, work, own, part_profile, raw, headers, modules, upstream, logs in staged:
        scoped = module_partitions.scoped_api(raw, own, root=index == 0, compile_modules=modules,
                                              module_owners=module_owners, assigned=assigned.get(group['name']))
        driver.json_write(work / 'scoped-api.json', scoped)
        snapshots[(work / 'scoped-api.json').relative_to(args.work).as_posix()] = hashlib.sha256(
            (work / 'scoped-api.json').read_bytes()).hexdigest()
        snapshots[(work / 'headers.h').relative_to(args.work).as_posix()] = hashlib.sha256(headers.read_bytes()).hexdigest()
        traits = None if args.extract_only else native_objects.refine_traits(
            scoped, args.qt_prefix, modules, work, args.cxx)
        records.append(SimpleNamespace(name=group['name'], api=scoped, profile=part_profile,
            owned_modules=own, namespaces=group.get('namespaces', {}), work=work, headers=headers,
            upstream=upstream, logs=logs, traits=traits))
    if args.extract_only:
        for name in ('api.json', 'headers.h', 'typesystem.xml', 'upstream.json',
                     'qobject-interfaces.json', 'qio-pipe.json'):
            if (args.work / name).is_file():
                snapshots[name] = hashlib.sha256((args.work / name).read_bytes()).hexdigest()
        if driver.extraction_inputs(args.profile) != extraction_identity:
            raise RuntimeError('Generator inputs changed during native module extraction')
        driver.json_write(args.work / 'extraction.json', dict(schema=1, verification_complete=True,
            source_sha256=driver.extraction_inputs(args.profile), snapshot_sha256=snapshots,
            qt=api['qt_headers'], shiboken_commit=api['shiboken_commit'], profile=profile))
        print('Compatible native module extractions prepared', flush=True)
        return
    original = overload_names.NameLock.load(args.profile / 'names.lock.json')
    parts = module_partitions.prepare_generators(records, original, selective=True)
    lock = merged_lock(parts, original)
    proxy = SimpleNamespace(name_lock=lock, methods=[row for part in parts for row in part.generator.methods])
    preflight = driver.preflight_names(proxy, args.work, source_inputs,
        args.reviewed_name_removals, args.acknowledge_removed_names)
    capacity = max(part.generator.argument_capacity for part in parts)
    abi = qt_targets.abi((driver.HERE / 'templates/abi.h').read_text(), capacity, api['qt_headers'])
    policy = evaluate_tables(args.work)
    prefix = '#define BQT_NATIVE_PARTITIONS 1\n' + ''.join(
        '#include "' + str(driver.HERE / 'templates' / name) + '"\n'
        for name in ('shared_runtime.h', 'shared_runtime.cpp'))
    for part in parts:
        source = part.work / 'unshared-wrappers.cpp'
        source.write_text(prefix + driver.native_source(part.generator, part.generator.api, part.headers,
            args.qt_prefix, part.work, abi, policy).replace('// @DISPATCH@', part.native))
        print('Analysing native module ' + part.name, flush=True)
        rewritten, state = transform(source, compiler_flags(args.qt_prefix, args.cxx, part.profile['qt_modules'])[1:])
        (part.work / 'wrappers.cpp').write_text(rewritten)
        driver.json_write(part.work / 'shared-state.json', state)
    if args.emit_only or args.syntax_only:
        if args.syntax_only:
            for part in parts:
                validate_backend(part.work / 'wrappers.cpp', args.qt_prefix, part.work, args.cxx,
                                 part.profile['qt_modules'])
        if driver.generation_inputs(args.profile) != source_inputs:
            raise RuntimeError('Generator inputs changed during native module emission')
        output_files.write_text(args.work / 'emitted-api.bend', module_partitions.merge_bend([part.bend for part in parts], getattr(parts[0], 'bend_preferences', None)))
        print('Native module source emission complete', flush=True)
        return
    reports, manifests = [], []
    inventory = Inventory(args.qt_prefix)
    for part in parts:
        print('Compiling native module ' + part.name, flush=True)
        embedded, _, backend = compile_backend(part.work / 'wrappers.cpp', args.qt_prefix, part.work,
            args.cxx, part.profile['qt_modules'])
        part.embedded = embedded
        traits = backend.get('proxy_constructibility')
        if traits is not None:
            if len(traits) != len(part.generator.callback_classes):
                raise RuntimeError('Native proxy trait inventory changed: ' + part.name)
            part.generator.callback_native_constructible = dict(zip(
                (row['name'] for row in part.generator.callback_classes), traits))
        omissions = []
        for path in sorted(part.logs.glob('*.log')):
            category = ''
            for line in path.read_text().splitlines():
                if line and not line.startswith(('*', ' -')):
                    category = line
                if line.startswith(' -') and any(name + '::' in line for name in part.generator.selected):
                    omissions.append(dict(log=path.name, category=category,
                        detail=line.strip().replace(str(args.qt_prefix), '<QT>')))
        report = driver.coverage_report(part.generator, part.generator.api, part.profile,
            inventory.require(part.owned_modules, 'gpl'), None, policy, backend, part.traits,
            part.owned_modules, part.upstream, omissions)
        reports.append(report)
        driver.json_write(part.work / 'coverage.json', report)
        manifests.extend(backend.get('native_dependency_manifests', []))
    if prepared_release is None:
        raise ValueError('The selective distribution requires verified bundled-runtime release inputs')
    owners = runtime_owners(prepared_release, parts, args.qt_prefix)
    bundle = runtime_release.package(prepared_release, profile, args.work, owners=owners,
                                     include_loader=False)
    emitted = module_partitions.selective_package(parts, abi,
        runtime=dict(bundle=bundle, selection=prepared_release['selection']))
    licensing = inventory.require(profile['qt_modules'], 'gpl')
    coverage = combined_coverage(reports, parts, bundle, licensing)
    coverage['removed_names'] = lock.removed
    if driver.generation_inputs(args.profile) != source_inputs:
        raise RuntimeError('Generator inputs changed during native module compilation; package not replaced')
    if args.reviewed_name_removals and hashlib.sha256(args.reviewed_name_removals.read_bytes()).hexdigest() != reviewed_digest:
        raise RuntimeError('Reviewed name removals changed during native module compilation; package not replaced')
    refreshed = runtime_release.prepare(args.runtime_manifest, args.qt_prefix, profile)
    if (refreshed['manifest_sha256'] != prepared_release['manifest_sha256']
            or refreshed['expected_sha256'] != prepared_release['expected_sha256']):
        raise RuntimeError('Runtime release inputs changed during native compilation; package not replaced')
    args.output.mkdir(parents=True, exist_ok=True)
    files = dict(emitted['assets'], **{'qt.bend': emitted['bend'], 'qt.c': emitted['c'],
        'coverage.json': json.dumps(portable(coverage, args.qt_prefix), indent=2) + '\n',
        'LICENSE': prepared_release['package_license'].read_text()})
    for name, text in files.items():
        output_files.write_text(args.output / name, text)
    # Generated C files of an earlier layout, such as runtime pieces beyond
    # this bundle's count, must not remain beside the new package.
    for path in args.output.glob('qt-*.c'):
        if path.name not in files:
            path.unlink()
    lock.write()
    completed = driver.generation_inputs(args.profile)
    lock_key = str(lock.path.relative_to(driver.ROOT) if lock.path.is_relative_to(driver.ROOT) else lock.path)
    if any(source_inputs.get(path) != completed.get(path)
           for path in source_inputs.keys() | completed.keys() if path != lock_key):
        raise RuntimeError('Generator inputs changed while completing the module name lock')
    driver.json_write(args.work / 'generation.json', dict(
        generated_sha256={name: hashlib.sha256((args.output / name).read_bytes()).hexdigest() for name in files},
        source_sha256=completed, input_name_lock_sha256=source_inputs.get(lock_key),
        runtime_release_manifest=str(args.runtime_manifest.resolve()), qt=api['qt_headers'],
        extractor=api['extractor'], profile=profile, native_dependency_manifests=sorted(set(manifests)),
        native_modules=[part.name for part in parts]))
    print('Generated selective Qt distribution: ' + str(args.output), flush=True)
