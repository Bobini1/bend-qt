#!/usr/bin/env python3
"""Run explicit focused checks, then resume a stable Qt package validation.

Run the setup script once before using this maintainer-only workflow.
`prepare` extracts metadata without collecting bindings. `focus --only NAME`
uses that snapshot without production generation. `final` builds the active
package once and runs the unchanged canonical check; --charts adds the legacy
Charts/DataVisualization complete-module gate. No command publishes to the Hub.
Cached results are accepted by content and dependency identity, never mtime.
"""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
from generate import extraction_inputs, generation_inputs

SCHEMA = 1
PACKAGE_FILES = ('qt.bend', 'qt.c', 'coverage.json')
SNAPSHOT_FILES = ('api.json', 'headers.h', 'typesystem.xml', 'upstream.json',
                  'qobject-interfaces.json', 'qio-pipe.json')
CHART_FIXTURES = ('resource-growth', 'pool-await', 'callback-depth', 'qt-object-worker',
                  'qml-created-objects', 'qml-extension-inheritance', 'qml-factory-failures',
                  'legacy-charts', 'properties')
ENV_NAMES = {'PATH', 'HOME', 'CC', 'CXX', 'CFLAGS', 'CXXFLAGS', 'LDFLAGS',
             'LIBRARY_PATH', 'LD_LIBRARY_PATH', 'LD_PRELOAD', 'CPATH',
             'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'PKG_CONFIG_PATH',
             'CMAKE_PREFIX_PATH', 'PYTHONPATH', 'PYTHONHOME', 'BENDRTS',
             'COMPILER_PATH', 'GCC_EXEC_PREFIX', 'LDEMULATION', 'LD_RUN_PATH',
             'SOURCE_DATE_EPOCH'}
EXTRACTION_TOOLS = frozenset(('python3', 'extractor', 'git'))
NATIVE_BUILD_ENV = frozenset((
    'BQT_SHARD_JOBS', 'BQT_SHARD_OPERATIONS', 'BQT_AUXILIARY_FUNCTIONS',
    'BQT_COMPILER_AS_MIB', 'BQT_SHARD_KEEP_GOING', 'BQT_NATIVE_WORKSPACE', 'BQT_LINKER'))


def execution_environment(jobs=None):
    environment = dict(os.environ)
    if jobs is not None:
        environment.setdefault('BQT_SHARD_JOBS', str(jobs))
    environment.setdefault('BQT_SHARD_KEEP_GOING', '1')
    environment.setdefault('BQT_SHARD_OPERATIONS', '512')
    return environment


def extraction_dependencies(dependencies):
    """Project build provenance onto tools and controls used by extraction."""
    result = dict(dependencies)
    result.pop('selected_linker', None)
    if 'tools' in dependencies:
        result['tools'] = {name: value for name, value in dependencies['tools'].items()
                           if name in EXTRACTION_TOOLS}
    if 'tool_libraries' in dependencies:
        result.pop('tool_libraries', None)
        result['native_tool_libraries'] = {
            path: value for name, libraries in dependencies['tool_libraries'].items()
            if name in EXTRACTION_TOOLS for path, value in libraries.items()}
    if 'environment' in dependencies:
        result['environment'] = {name: value for name, value in dependencies['environment'].items()
                                 if name not in NATIVE_BUILD_ENV}
    return result


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent,
                                         prefix='.' + path.name, delete=False) as output:
            temporary = Path(output.name)
            json.dump(value, output, indent=2, sort_keys=True)
            output.write('\n')
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def files_under(path):
    return sorted(p for p in Path(path).rglob('*')
                  if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')


def file_set(paths):
    # Resolving shared-library symlinks avoids hashing a large Qt binary twice.
    hashes = {}
    result = {}
    for path in sorted(set(map(Path, paths))):
        target = path.resolve(strict=True)
        if target not in hashes:
            hashes[target] = sha(target)
        result[str(path.absolute())] = dict(resolved=str(target), sha256=hashes[target])
    return result


def artifact_hash(path, mode='file'):
    if mode == 'file':
        return sha(path)
    value = read_json(path)
    if mode == 'generation':
        # Canonical deterministic regeneration refreshes incoming-lock history
        # and cache diagnostics. The completed source/package identity stays.
        keys = ('generated_sha256', 'source_sha256', 'qt', 'extractor', 'profile')
        selected = {key: value[key] for key in keys}
        if 'native_dependency_manifests' in value:
            selected['native_dependency_manifests'] = value['native_dependency_manifests']
        return identity(selected)
    if mode == 'names':
        sources = {key: digest for key, digest in value['source_sha256'].items()
                   if not key.endswith('/names.lock.json')}
        return identity(dict(source_sha256=sources, methods=value['methods'],
                             native_source_sha256=value['native_source_sha256']))
    raise ValueError('Unknown artifact identity mode: ' + mode)


def artifacts(paths, modes=None):
    modes = modes or {}
    return {str(Path(path).resolve()): dict(mode=modes.get(str(Path(path).resolve()), 'file'),
                 sha256=artifact_hash(path, modes.get(str(Path(path).resolve()), 'file')))
            for path in paths}


@contextmanager
def exclusive(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another maintainer workflow owns ' + str(path)) from None
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


class Stages:
    def __init__(self, directory, root, runner=None, force=False, force_stages=(), jobs=None):
        self.directory, self.root = Path(directory), Path(root)
        self.runner = runner or self.execute
        self.force = force
        self.force_stages = set(force_stages)
        self.jobs = jobs

    def execute(self, command, log):
        with log.open('w') as output:
            result = subprocess.run(command, cwd=self.root, stdout=output,
                                    stderr=subprocess.STDOUT, check=False, env=execution_environment(self.jobs))
        if result.returncode:
            raise RuntimeError(f'Command failed ({result.returncode}); see {log}')

    def valid(self, name, command, inputs):
        try:
            record = read_json(self.directory / (name + '.json'))
            return (record['schema'] == SCHEMA and record['complete'] is True
                    and record['command'] == command and record['inputs'] == inputs
                    and bool(record['artifacts'])
                    and all(artifact_hash(path, spec['mode']) == spec['sha256']
                            for path, spec in record['artifacts'].items())
                    and all(Path(path).is_file() and str(Path(path).resolve()) == spec['resolved']
                            and sha(path) == spec['sha256']
                            for path, spec in record.get('native_dependencies', {}).items()))
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def require(self, name, command, inputs):
        if not self.valid(name, command, inputs):
            raise RuntimeError('The prepared extraction is missing or stale; run prepare explicitly')
        return read_json(self.directory / (name + '.json'))

    def run(self, name, command, inputs, validate, outputs, *, reuse=True, after_command=None):
        before = inputs()
        if reuse and not self.force and name not in self.force_stages and self.valid(name, command, before):
            try:
                validate()
            except (OSError, ValueError, RuntimeError, KeyError, TypeError):
                pass
            else:
                print('REUSE ' + name, flush=True)
                return read_json(self.directory / (name + '.json'))
        self.directory.mkdir(parents=True, exist_ok=True)
        record = dict(schema=SCHEMA, complete=False, command=command, inputs=before,
                      public_hub_publication=False)
        path, log = self.directory / (name + '.json'), self.directory / (name + '.log')
        write_json(path, record)  # Retire any earlier success before starting.
        print('RUN ' + name + ' (log: ' + str(log) + ')', flush=True)
        try:
            self.runner(command, log)
            if after_command is not None:
                after_command()
            evidence = validate()
            if inputs() != before:
                raise RuntimeError('Inputs changed during ' + name + '; the result is not reusable')
            record.update(artifacts=outputs(), evidence=evidence, complete=True,
                          native_dependencies=evidence.get('native_dependencies', {}))
            write_json(path, record)
        except BaseException as error:
            record.update(complete=False, error=str(error) or type(error).__name__)
            write_json(path, record)
            raise
        print('PASS ' + name, flush=True)
        return record


def validate_hashes(paths, base):
    for name, expected in paths.items():
        path = Path(name)
        if not path.is_absolute():
            path = Path(base) / path
        if sha(path) != expected:
            raise RuntimeError('Changed artifact or dependency: ' + str(path))


def validate_generation(root, work, profile):
    value = read_json(work / 'generation.json')
    expected = generation_inputs(profile)
    if value.get('verification_complete') is False or value['source_sha256'] != expected:
        raise RuntimeError('The generated package does not match current generator inputs')
    generated = set(value['generated_sha256'])
    extra = generated - set(PACKAGE_FILES)
    configuration = read_json(profile / 'profile.json')
    native_modules = ['base', *[row['name'] for row in configuration.get('native_modules', [])]]
    module_files = {'qt-' + name + '.c' for name in native_modules if name != 'base'}
    module_files.update('qt-runtime-module-' + name + '.c' for name in native_modules)
    if (not set(PACKAGE_FILES) <= generated or value['qt'] != '6.12.0'
            or any(name != 'LICENSE' and name not in module_files
                   and not re.fullmatch(r'qt-runtime-\d+\.c', name) for name in extra)):
        raise RuntimeError('The generation receipt is incomplete or targets another Qt release')
    validate_hashes(value['generated_sha256'], root / 'packages/qt612')
    validate_hashes(value['source_sha256'], root)
    keys = ('generated_sha256', 'source_sha256', 'qt', 'extractor', 'profile')
    result = {key: value[key] for key in keys}
    if 'native_dependency_manifests' in value:
        result['native_dependency_manifests'] = value['native_dependency_manifests']
    return result


def native_dependencies(work):
    """Accept backend additions while requiring actual dependency hash evidence."""
    result, visited = {}, set()
    generation = Path(work) / 'generation.json'
    roots = ([generation] if generation.is_file() else
             [path for path in (Path(work) / 'backend.json', Path(work) / 'public-abi/backend.json')
              if path.is_file()])
    if not roots:
        raise RuntimeError('Backend dependency evidence is missing: ' + str(work))
    pending = list(roots)
    if not any('native_dependency_manifests' in read_json(path) for path in roots):
        pending += list(Path(work).rglob('*cache.json'))
    while pending:
        path = pending.pop()
        if path.resolve() in visited:
            continue
        visited.add(path.resolve())
        value = read_json(path)
        key = value.get('key', {})
        for directory, expected in key.get('search_directories', {}).items():
            directory = Path(directory)
            current = (sorted([item.name, os.readlink(item) if item.is_symlink() else '']
                              for item in directory.iterdir()) if directory.is_dir() else None)
            if current != expected:
                raise RuntimeError('Native library search directory changed: ' + str(directory))
        for name, expected in key.get('environment', {}).items():
            if execution_environment().get(name) != expected:
                raise RuntimeError('Native linker environment changed: ' + name)
        for field in ('dependencies', 'native_dependencies'):
            rows = value.get(field, {})
            if not isinstance(rows, dict):
                raise RuntimeError('Malformed dependency evidence: ' + str(path))
            for name, fingerprint in rows.items():
                if isinstance(fingerprint, str):
                    fingerprint = dict(resolved=str(Path(name).resolve()), sha256=fingerprint)
                if (not Path(name).is_absolute() or not isinstance(fingerprint, dict)
                        or not isinstance(fingerprint.get('sha256'), str)
                        or len(fingerprint['sha256']) != 64
                        or not isinstance(fingerprint.get('resolved'), str)
                        or not Path(fingerprint['resolved']).is_absolute()):
                    raise RuntimeError('Malformed dependency fingerprint in ' + str(path))
                fingerprint = {key: fingerprint[key] for key in ('resolved', 'sha256')}
                if name in result and result[name] != fingerprint:
                    raise RuntimeError('Conflicting native dependency evidence: ' + name)
                result[name] = fingerprint
        manifests = value.get('native_dependency_manifests', [])
        if not isinstance(manifests, list):
            raise RuntimeError('Malformed dependency manifest list: ' + str(path))
        pending += [Path(name) if Path(name).is_absolute() else Path(work) / name for name in manifests]
    if not result:
        raise RuntimeError('Native dependency evidence is missing; regenerate with dependency manifests')
    for name, fingerprint in result.items():
        if str(Path(name).resolve()) != fingerprint['resolved'] or sha(name) != fingerprint['sha256']:
            raise RuntimeError('Changed native dependency or symlink target: ' + name)
    return result


def validate_verification(path, *, canonical=False):
    value = read_json(path)
    if value.get('verification_complete') is not True:
        raise RuntimeError('Verification is incomplete: ' + str(path))
    if canonical and (value.get('deterministic_regeneration') is not True
                      or value.get('public_hub_publication') is not False):
        raise RuntimeError('The complete canonical gate was not recorded')
    return value


def verification_outputs(path, persistent_root=None):
    files = {Path(path)}
    persistent_root = Path(persistent_root or Path(path).parent).resolve()
    def visit(value, top=False):
        if isinstance(value, dict):
            for key in ('executable', 'validation_executable'):
                target = value.get(key)
                if isinstance(target, str) and Path(target).is_absolute():
                    target = Path(target)
                    if not target.resolve().is_relative_to(persistent_root):
                        # Canonical extension controls intentionally remove
                        # their temporary directories after successful runs.
                        if top:
                            raise RuntimeError('Validation executable is outside its persistent work directory')
                        continue
                    if not target.is_file():
                        raise RuntimeError('A verified executable is missing: ' + str(target))
                    if value.get('executable_sha256') and sha(target) != value['executable_sha256']:
                        raise RuntimeError('A verified executable changed: ' + str(target))
                    files.add(target)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(read_json(path), top=True)
    return artifacts(sorted(files))


def backend_outputs(work):
    paths = set()
    for root in (Path(work) / 'backend.json', Path(work) / 'public-abi/backend.json'):
        if root.is_file():
            paths.add(root)
            paths.update(Path(name) if Path(name).is_absolute() else Path(work) / name
                         for name in read_json(root).get('native_dependency_manifests', []))
    return artifacts(sorted(paths))


class Workflow:
    def __init__(self, root, args, stages=None, dependency_reader=None):
        self.root, self.args = Path(root), args
        self.state = args.state_dir.resolve()
        self.source = args.source_work.resolve() if args.source_work else self.state / 'source'
        self.profile = self.root / 'generator/qt612'
        self.work = self.root / 'build/qt612'
        self.stages = stages or Stages(self.state / 'stages', self.root, force=args.force,
                                       force_stages=args.force_stage, jobs=getattr(args, 'jobs', None))
        self.dependencies = dependency_reader or self.dependency_identity
        self._dependencies = None
        self._requirements = []
        for name in ('qt_root', 'extractor', 'pyside_source'):
            setattr(args, name, getattr(args, name).resolve())
        if getattr(args, 'reviewed_removals', None):
            args.reviewed_removals = args.reviewed_removals.resolve()

    def dependency_identity(self):
        tools = {}
        for name in ('python3', self.args.cxx, 'clang', 'clang-19', 'g++', 'gcc', 'bend',
                     'cmake', 'ninja', 'git', 'bash', 'llvm-readobj-19', 'llvm-strip-19',
                     'llvm-objcopy-19', 'llvm-nm-19', 'readelf', 'nm', 'ld'):
            found = shutil.which(name)
            if found is None:
                raise RuntimeError('Missing maintainer tool: ' + name + '; run scripts/setup-qt-generator.sh')
            tools[name] = dict(path=str(Path(found).resolve()), sha256=sha(found))
        if not self.args.extractor.is_file():
            raise RuntimeError('Missing ApiExtractor; run scripts/setup-qt-generator.sh')
        tools['extractor'] = dict(path=str(self.args.extractor.resolve()), sha256=sha(self.args.extractor))
        from native_linker import select
        linker = select(self.args.cxx)['identity']
        tools['selected_linker'] = dict(path=linker['path'], sha256=linker['sha256'],
                                       resolved=str(Path(linker['path']).resolve()))
        linked, by_tool = set(), {}
        for name, tool in tools.items():
            by_tool[name] = set()
            # ldd's paths describe the installed native toolchain, including
            # libclang/LLVM and libstdc++; script executables have no ELF deps.
            target = Path(tool['path'])
            with target.open('rb') as source:
                elf = source.read(4) == b'\x7fELF'
            if elf:
                import re
                resolved = subprocess.run(['ldd', str(target)], capture_output=True, text=True, check=False)
                static = 'not a dynamic executable' in (resolved.stdout + resolved.stderr)
                if resolved.returncode and not static:
                    raise RuntimeError('Cannot identify native tool dependencies: ' + str(target))
                libraries = {Path(value) for value in re.findall(r'(?:=>\s+|^\s*)(/\S+)\s+\(', resolved.stdout, re.M)}
                by_tool[name].update(libraries)
                linked.update(libraries)
        pyside = self.args.pyside_source
        extractor_sources = pyside / 'sources/shiboken6_generator/ApiExtractor'
        if not (extractor_sources / 'apiextractor.h').is_file():
            raise RuntimeError('The pinned ApiExtractor source checkout is missing')
        commit = subprocess.check_output(['git', '-C', str(pyside), 'rev-parse', 'HEAD'], text=True).strip()
        subprocess.run(['git', '-C', str(pyside), 'diff', '--exit-code', 'HEAD', '--',
                        'sources/pyside6/PySide6', 'sources/shiboken6_generator/ApiExtractor'],
                       check=True, stdout=subprocess.DEVNULL)
        from upstream import PIN
        if commit != PIN:
            raise RuntimeError('PySide checkout differs from the pinned source')
        qt_files = files_under(self.args.qt_root)
        if not qt_files:
            raise RuntimeError('The Qt kit is missing; run scripts/setup-qt-generator.sh')
        system = [*files_under('/usr/include'), *files_under('/usr/lib/llvm-19/lib/clang'),
                  *files_under('/usr/lib/gcc')]
        library_identity = file_set(linked)
        per_tool = {name: {str(path.absolute()): library_identity[str(path.absolute())] for path in paths}
                    for name, paths in by_tool.items()}
        return dict(tools=tools, selected_linker=linker, native_tool_libraries=library_identity,
                    tool_libraries=per_tool,
                    system_headers_and_runtime=file_set(system), qt=file_set(qt_files),
                    platform=dict(system=sys.platform, machine=platform.machine(), release=platform.release(),
                                  python=sys.version,
                                  machine_id_sha256=sha('/etc/machine-id') if Path('/etc/machine-id').is_file() else None),
                    pyside=dict(commit=commit, files=file_set(files_under(pyside / 'sources/pyside6/PySide6')),
                                extractor_sources=file_set(files_under(extractor_sources))),
                    environment={key: value for key, value in execution_environment(getattr(self.args, 'jobs', None)).items()
                                 if key in ENV_NAMES or key.startswith(('BQT_', 'BEND_', 'QT_'))})

    def deps(self):
        # Memoize within one workflow, but invalidate after each executed stage
        # so dependency drift cannot be hidden by a cached initial snapshot.
        if self._dependencies is None:
            self._dependencies = self.dependencies()
        return self._dependencies

    def stage(self, name, command, inputs, validate, outputs, **kwargs):
        self.stages.jobs = getattr(self.args, 'jobs', None)
        def invalidate_dependencies():
            self._dependencies = None
        result = self.stages.run(name, command, inputs, validate, outputs,
                                 after_command=invalidate_dependencies, **kwargs)
        self._requirements.append((name, command, inputs))
        return result

    def extraction_command(self, profile, work):
        return ['python3', 'generator/generate.py', '--extract-only', '--profile', str(profile),
                '--work', str(work), '--qt-prefix', str(self.args.qt_root),
                '--extractor', str(self.args.extractor), '--pyside-source', str(self.args.pyside_source)]

    def extraction_key(self, profile):
        return dict(dependency_scope='api-extraction-v2', sources=extraction_inputs(profile),
                    dependencies=extraction_dependencies(self.deps()))

    def validate_extraction(self, profile, work):
        value = read_json(work / 'extraction.json')
        if (value.get('verification_complete') is not True or value.get('qt') != '6.12.0'
                or value['source_sha256'] != extraction_inputs(profile)
                or not {'api.json', 'headers.h', 'upstream.json'} <= set(value['snapshot_sha256'])):
            raise RuntimeError('The extraction receipt is incomplete or stale')
        validate_hashes(value['snapshot_sha256'], work)
        return value

    def prepare(self, profile=None, work=None, name='prepare'):
        write_json(self.state / 'receipt.json', dict(schema=SCHEMA, verification_complete=False,
                   scope='extraction', public_hub_publication=False))
        profile, work = profile or self.profile, work or self.source
        command = self.extraction_command(profile, work)
        return self.stage(name, command, lambda: self.extraction_key(profile),
                          lambda: self.validate_extraction(profile, work),
                          lambda: artifacts([work / 'extraction.json',
                              *(work / p for p in read_json(work / 'extraction.json')['snapshot_sha256'])]))

    def focus(self):
        self._dependencies = None
        write_json(self.state / 'receipt.json', dict(schema=SCHEMA, verification_complete=False,
                   scope='focused', public_hub_publication=False))
        self.stages.require('prepare', self.extraction_command(self.profile, self.source),
                            self.extraction_key(self.profile))
        self.validate_extraction(self.profile, self.source)
        command = ['python3', 'scripts/check-qt-callbacks.py', '--skip-examples',
                   '--source-work', str(self.source), '--work', str(self.state / 'focus'),
                   '--name-lock', str(self.profile / 'names.lock.json'), '--jobs', str(self.args.jobs),
                   '--qt-root', str(self.args.qt_root)]
        for name in self.args.only:
            command += ['--only', name]
        for module in self.args.module:
            command += ['--module', module]
        if self.args.rhi:
            command.append('--rhi')
        def inputs():
            return dict(sources=generation_inputs(self.profile), dependencies=self.deps(),
                        checks=file_set(files_under(self.root / 'scripts')))
        before = inputs()
        write_json(self.state / 'focus-result.json', dict(verification_complete=False, scope='focused'))
        subprocess.run(command, cwd=self.root, check=True, env=execution_environment(self.args.jobs))
        self._dependencies = None
        receipt = self.state / 'focus/receipt.json'
        value = validate_verification(receipt)
        if set(value.get('expected_programs', [])) != set(self.args.only):
            raise RuntimeError('The focused receipt does not contain exactly the requested fixtures')
        if inputs() != before:
            raise RuntimeError('Inputs changed during the focused check; rerun it against stable sources')
        write_json(self.state / 'focus-result.json', dict(verification_complete=False,
            focused_verification_complete=True, scope='focused', inputs=before,
            artifacts=verification_outputs(receipt),
            native_dependencies=native_dependencies(self.state / 'focus'), public_hub_publication=False))
        print('Focused check complete; production generation and canonical validation were not run')

    def final_inputs(self, reviewed):
        lock = str((self.profile / 'names.lock.json').relative_to(self.root))
        result = dict(sources={key: value for key, value in generation_inputs(self.profile).items() if key != lock},
                    reviewed_sha256=sha(reviewed), dependencies=self.deps())
        manifest = getattr(self.args, 'runtime_manifest', None)
        if manifest:
            from runtime_release import prepare
            prepared = prepare(manifest, self.args.qt_root, read_json(self.profile / 'profile.json'))
            result['runtime_release'] = dict(manifest=prepared['manifest_sha256'], files=prepared['expected_sha256'],
                sources={name: row['sha256'] for name, row in prepared['sources'].items()})
        return result

    def final(self):
        self._requirements = []
        self._dependencies = None
        write_json(self.state / 'receipt.json', dict(schema=SCHEMA, verification_complete=False,
                   charts_requested=self.args.charts, public_hub_publication=False))
        from generate import CACHE
        if self.args.cxx != 'clang++-19' or self.args.pyside_source.resolve() != (CACHE / 'pyside-setup').resolve():
            raise ValueError('The unchanged canonical checker requires clang++-19 and its default pinned PySide checkout')
        reviewed = self.args.reviewed_removals
        if reviewed is None:
            reviewed = self.state / 'empty-reviewed-removals.json'
            write_json(reviewed, {'reviewed': []})
        from generate import reviewed_name_removals
        allowed = reviewed_name_removals(reviewed)
        command = ['python3', 'generator/generate.py', '--reviewed-name-removals', str(reviewed),
                   '--acknowledge-removed-names', '--qt-prefix', str(self.args.qt_root),
                   '--extractor', str(self.args.extractor), '--pyside-source', str(self.args.pyside_source),
                   '--cxx', self.args.cxx]
        if getattr(self.args, 'runtime_manifest', None):
            command += ['--runtime-manifest', str(self.args.runtime_manifest)]

        def validate():
            value = validate_generation(self.root, self.work, self.profile)
            preflight = read_json(self.work / 'name-lock-preflight.json')
            if set(map(tuple, preflight['unacknowledged'])) - allowed:
                raise RuntimeError('Generation acknowledged an unreviewed public name removal')
            return dict(generation=value, reviewed=sorted(allowed), native_dependencies=native_dependencies(self.work),
                        preflight=preflight['unacknowledged'])

        def outputs():
            metadata = self.work / 'generation.json'
            names = self.work / 'name-lock-preflight.json'
            paths = [metadata, names, self.profile / 'names.lock.json',
                     *(self.root / 'packages/qt612' / name for name in read_json(metadata)['generated_sha256']),
                     *(self.work / name for name in SNAPSHOT_FILES if (self.work / name).is_file()),
                     self.work / 'wrappers.cpp']
            paths += [Path(name) if Path(name).is_absolute() else self.work / name
                      for name in read_json(metadata).get('native_dependency_manifests', [])]
            return artifacts(paths, {str(metadata.resolve()): 'generation', str(names.resolve()): 'names'})

        generation = self.stage('generation', command, lambda: self.final_inputs(reviewed), validate, outputs)
        # A resumed result must still satisfy semantic receipt checks.
        validate()
        canonical = ['python3', 'scripts/check-qt612.py', '--bundle', '--generator-checks', '--reject-system-qt']
        if getattr(self.args, 'runtime_manifest', None):
            canonical += ['--runtime-manifest', str(self.args.runtime_manifest)]
        default_qt = Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64'
        default_extractor = Path.home() / '.cache/bend-qt-generator/build/bend-qt-extract'
        if self.args.qt_root.resolve() != default_qt.resolve() or self.args.extractor.resolve() != default_extractor.resolve():
            canonical += ['--qt-prefix', str(self.args.qt_root), '--qt-root', str(self.args.qt_root),
                          '--extractor', str(self.args.extractor)]
        receipt = self.work / 'check/receipt.json'

        def check_inputs():
            sources = file_set([*files_under(self.root / 'scripts'), *files_under(self.root / 'examples'),
                                *self.root.glob('*.bend')])
            return dict(generation=validate_generation(self.root, self.work, self.profile),
                        native_dependencies=native_dependencies(self.work),
                        check_sources=sources, dependencies=self.deps())

        checked = self.stage('canonical', canonical, check_inputs,
                             lambda: validate_verification(receipt, canonical=True),
                             lambda: verification_outputs(receipt, self.work))
        validate_verification(receipt, canonical=True)
        charts = self.charts() if self.args.charts else None
        if self.args.setup_examples:
            self.stage('setup-examples', ['bash', 'scripts/check.sh'], check_inputs,
                       lambda: {'passed': True},
                       lambda: artifacts([self.root / 'scripts/check.sh', self.root / 'build/hello',
                                          self.root / 'build/parallel']))
        self._dependencies = None
        for name, command, inputs in self._requirements:
            if not self.stages.valid(name, command, inputs()):
                raise RuntimeError('State changed after ' + name + '; final verification is incomplete')
        write_json(self.state / 'receipt.json', dict(schema=SCHEMA, verification_complete=True,
            generation_stage=identity(generation), canonical_stage=identity(checked),
            charts_stage=identity(charts) if charts else None, setup_examples=self.args.setup_examples,
            public_hub_publication=False))
        print('PASS stable generation and complete canonical validation' + (' with Charts/DataVisualization' if charts else ''))

    def charts(self):
        profile, source, work = (self.root / 'generator/qt612-legacy-charts',
                                 self.state / 'charts-source', self.state / 'charts-native')
        prepared = self.prepare(profile, source, 'charts-extraction')
        command = ['python3', 'scripts/check-qt-callbacks.py', '--source-work', str(source),
                   '--name-lock', str(profile / 'names.lock.json'), '--work', str(work),
                   '--qt-root', str(self.args.qt_root), '--jobs', str(self.args.jobs),
                   '--complete-module', 'QtCharts', '--complete-module', 'QtDataVisualization']
        for fixture in CHART_FIXTURES:
            command += ['--only', fixture]
        def validate():
            value = validate_verification(work / 'receipt.json')
            return dict(receipt=value, native_dependencies=native_dependencies(work))
        return self.stage('charts-native', command,
            lambda: dict(extraction=identity(prepared), source=generation_inputs(profile),
                         checks=file_set(files_under(self.root / 'scripts')), dependencies=self.deps()),
            validate,
            lambda: dict(verification_outputs(work / 'receipt.json'), **backend_outputs(work)))


def arguments(argv=None):
    cache = Path(os.environ.get('BEND_QT_GENERATOR_CACHE', Path.home() / '.cache/bend-qt-generator'))
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--state-dir', type=Path, default=ROOT / 'build/qt612-maintain')
    parser.add_argument('--source-work', type=Path)
    parser.add_argument('--qt-root', type=Path, default=cache / 'Qt/6.12.0/gcc_64')
    parser.add_argument('--extractor', type=Path, default=cache / 'build/bend-qt-extract')
    parser.add_argument('--pyside-source', type=Path, default=cache / 'pyside-setup')
    parser.add_argument('--cxx', default='clang++-19')
    parser.add_argument('--force', action='store_true', help='Rerun requested stages even when their identities match')
    parser.add_argument('--force-stage', action='append', default=[],
                        choices=('prepare', 'generation', 'canonical', 'charts-extraction',
                                 'charts-native', 'setup-examples'),
                        help='Rerun this stage while retaining valid earlier stages')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('prepare', help='Extract a reusable API model without collecting bindings')
    focus = commands.add_parser('focus', help='Run only explicitly selected regression fixtures')
    focus.add_argument('--only', action='append', required=True)
    focus.add_argument('--module', action='append', default=[])
    focus.add_argument('--rhi', action='store_true')
    focus.add_argument('--jobs', type=int, default=2)
    final = commands.add_parser('final', help='Resume production generation and the required canonical gate')
    final.add_argument('--reviewed-removals', type=Path)
    final.add_argument('--runtime-manifest', type=Path, help='Verified bundled runtime and corresponding-source release manifest')
    final.add_argument('--jobs', type=int, default=2)
    final.add_argument('--charts', action='store_true')
    final.add_argument('--setup-examples', action='store_true')
    return parser.parse_args(argv)


def main(argv=None):
    if sys.platform != 'linux' or platform.machine() != 'x86_64':
        raise RuntimeError('Run this maintainer workflow in Ubuntu-24.04 WSL as bobini')
    args = arguments(argv)
    if getattr(args, 'jobs', 1) < 1:
        raise ValueError('--jobs must be positive')
    workflow = Workflow(ROOT, args)
    # One writer per workflow state; final also reserves production artifacts
    # across helpers using different state directories.
    with exclusive(workflow.state / '.lock'):
        if args.command == 'final':
            with exclusive(ROOT / 'build/qt612/.maintain.lock'):
                workflow.final()
        else:
            getattr(workflow, args.command)()


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
