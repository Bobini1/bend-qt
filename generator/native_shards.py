"""Split generated operations while preserving one C++17 inline runtime.

Only maintainer compilation changes. The partial-linked object still feeds the
same two-export ELF payload and stock Bend consumer effect.
"""
import argparse
from ctypes import Structure, byref, c_char_p, c_uint, c_void_p
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import threading
import signal
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from public_records import Clang, Cursor, Location
from native_workspace import diagnostic_path


class NativeCompileFailure(RuntimeError):
    def __init__(self, name, status, log):
        self.name, self.status, self.log = name, status, log
        super().__init__(f'Native shard {name} failed ({status}); see {log}')

    def __reduce__(self):
        return type(self), (self.name, self.status, self.log)


def write_changed(path, content):
    data = content.encode() if isinstance(content, str) else content
    if not path.exists() or path.read_bytes() != data:
        path.write_bytes(data)


class Range(Structure):
    _fields_ = [('ptr_data', c_void_p * 2), ('begin_int_data', c_uint), ('end_int_data', c_uint)]


def split_source(source):
    operations = list(re.finditer(r'^static bool __attribute__\(\(noinline\)\) bqt_op_(\d+)\(BqtRequest \*r\) \{\n', source, re.M))
    if not operations:
        raise ValueError('Native source has no generated operation boundaries')
    end = source.find('\nstatic bool dispatch(BqtRequest *r) {', operations[-1].end())
    if end < 0:
        raise ValueError('Native source has no final generated dispatcher')
    ids = [int(match[1]) for match in operations]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate generated native operation identifiers')
    bodies = [(identifier, source[match.start():operations[i + 1].start() if i + 1 < len(operations) else end])
              for i, (identifier, match) in enumerate(zip(ids, operations))]
    return source[:operations[0].start()], bodies, source[end:]


def split_auxiliary(source):
    """Extract generated out-of-line helpers without parsing their C++ bodies.

    The markers are emitted by the generator and identify complete definitions.
    Declarations stay in the shared header, retaining ordinary hidden C++
    linkage while each typed implementation is compiled in exactly one unit.
    """
    pattern = re.compile(r'^// BQT_AUXILIARY_BEGIN ([a-z][a-z0-9_]*) ([0-9]+)\n'
                         r'(.*?)^// BQT_AUXILIARY_END \1 \2\n', re.M | re.S)
    units, identities = [], set()
    for match in pattern.finditer(source):
        if 'BQT_AUXILIARY_' in match[3]:
            raise ValueError('Nested native auxiliary definition boundary')
        identity = (match[1], int(match[2]))
        if identity in identities:
            raise ValueError('Duplicate native auxiliary definition: ' + repr(identity))
        identities.add(identity)
        units.append((identity[0], identity[1], match[3]))
    stripped = pattern.sub('', source)
    if 'BQT_AUXILIARY_BEGIN' in stripped or 'BQT_AUXILIARY_END' in stripped:
        raise ValueError('Malformed native auxiliary definition boundary')
    return stripped, units


def inline_runtime(header, flags):
    """Use declaration scopes, not indentation, to identify shared storage.

    Function-local statics stay local to the now-inline function. Class members
    and included Qt headers are untouched. Every shard then refers to the same
    inline registry, TLS and helper-function identities in the final ELF.
    """
    clang = Clang()
    def function(name, result, *arguments):
        fn = getattr(clang.lib, 'clang_' + name)
        fn.restype = result; fn.argtypes = arguments
        setattr(clang, name, fn)
    function('getCursorExtent', Range, Cursor)
    function('getRangeStart', Location, Range)
    function('getCursorLinkage', c_uint, Cursor)
    source = header.read_bytes()
    filename = str(header.resolve())
    edits = []
    facts = []
    try:
        clang.index = clang.createIndex(0, 0)
        argv = (c_char_p * len(flags))(*(value.encode() for value in flags))
        # Skip function bodies only in this declaration-analysis pass. PCH and
        # object compilation still parse and compile every selected body.
        clang.tu = clang.parseTranslationUnit(clang.index, str(header).encode(), argv, len(flags), None, 0, 0x40)
        if not clang.tu:
            raise RuntimeError('Unable to analyse shared native declarations')
        errors = []
        for i in range(clang.getNumDiagnostics(clang.tu)):
            diagnostic = clang.getDiagnostic(clang.tu, i)
            if clang.getDiagnosticSeverity(diagnostic) >= 3:
                errors.append(clang.string(clang.formatDiagnostic(diagnostic, 0)))
            clang.disposeDiagnostic(diagnostic)
        if errors:
            raise RuntimeError('Shared runtime declaration analysis failed:\n' + '\n'.join(errors))

        def offset(location):
            result = c_uint()
            clang.getSpellingLocation(location, None, None, None, byref(result))
            return result.value

        def visit(cursor):
            for child in clang.children(cursor):
                file, _ = clang.location(child)
                if file != filename:
                    continue
                kind = clang.kind(child)
                if kind == 'Namespace':
                    if not clang.spelling(child):
                        raise RuntimeError('Shared native runtime cannot contain an anonymous namespace')
                    visit(child)
                    continue
                if kind not in ('FunctionDecl', 'FunctionTemplate', 'VarDecl', 'CXXMethod',
                                'Constructor', 'Destructor', 'CXXConstructor', 'CXXDestructor'):
                    continue
                start = offset(clang.getRangeStart(clang.getCursorExtent(child)))
                name = offset(clang.getCursorLocation(child))
                prefix = source[start:name]
                storage = re.search(rb'\bstatic\b', prefix)
                if storage:
                    edits.append((start + storage.start(), start + storage.end(), b'inline'))
                elif kind != 'FunctionTemplate' and not re.search(rb'\b(inline|extern)\b', prefix):
                    edits.append((start, start, b'inline '))
                facts.append(dict(name=clang.spelling(child), kind=kind, offset=start,
                                  replaced_static=bool(storage), linkage=clang.getCursorLinkage(child)))
        visit(clang.getTranslationUnitCursor(clang.tu))
    finally:
        clang.close()
    # Multiple declaration cursors must never overlap or change a local static.
    unique = sorted(set(edits))
    boundary = 0
    fragments = []
    for start, end, text in unique:
        if start < boundary:
            raise RuntimeError('Overlapping native declaration transformations')
        fragments += [source[boundary:start], text]
        boundary = end
    fragments.append(source[boundary:])
    return b''.join(fragments), facts


def prepare(source_path, work, flags, maximum_operations=2048, maximum_bytes=3_000_000,
            maximum_auxiliary_functions=128):
    source_path = source_path.resolve()
    work = work.resolve()
    if maximum_operations < 1 or maximum_bytes < 1 or maximum_auxiliary_functions < 1:
        raise ValueError('Native shard size limits must be positive')
    prefix, operations, suffix = split_source(source_path.read_text())
    prefix, auxiliary = split_auxiliary(prefix)
    if any('BQT_AUXILIARY_' in body for _, body in operations) or 'BQT_AUXILIARY_' in suffix:
        raise ValueError('Native auxiliary definitions must precede operation dispatch')
    work.mkdir(parents=True, exist_ok=True)
    # Keep the diagnostic trait section in exactly one object; concatenating
    # multiple identical sections would corrupt the measured class inventory.
    trait = re.compile(r'__attribute__\(\(used, section\("\.bqt\.proxy_traits"\)\)\)\s*static const unsigned char bqt_proxy_traits\[\] = \{[^;]*\};\s*')
    traits = trait.findall(prefix)
    if len(traits) > 1:
        raise RuntimeError('Multiple proxy trait arrays in native source')
    prefix = trait.sub('', prefix)
    analysis = work / 'shared-analysis.hpp'
    write_changed(analysis, prefix + '\n} // namespace bendqt\n')
    shared, declarations = inline_runtime(analysis, flags)
    header = work / 'shared.hpp'
    write_changed(header, b'#pragma once\n' + shared)
    groups = []
    current = []
    size = 0
    for identifier, body in operations:
        if current and (len(current) >= maximum_operations or size + len(body) > maximum_bytes):
            groups.append(current); current = []; size = 0
        current.append((identifier, body)); size += len(body)
    if current:
        groups.append(current)
    sources = []
    for i, group in enumerate(groups):
        path = work / f'operations-{i:03}.cpp'
        write_changed(path, '#include "shared.hpp"\nnamespace bendqt {\n' +
                      '\n'.join(body.removeprefix('static ') for _, body in group) + '\n}\n')
        sources.append(path)
    auxiliary_groups, current, size = [], [], 0
    for family, identifier, body in auxiliary:
        if current and (current[0][0] != family or len(current) >= maximum_auxiliary_functions or
                        size + len(body) > maximum_bytes):
            auxiliary_groups.append(current); current = []; size = 0
        current.append((family, identifier, body)); size += len(body)
    if current:
        auxiliary_groups.append(current)
    for i, group in enumerate(auxiliary_groups):
        path = work / f'auxiliary-{group[0][0]}-{i:03}.cpp'
        write_changed(path, '#include "shared.hpp"\nnamespace bendqt {\n' +
                      '\n'.join(body for _, _, body in group) + '\n}\n')
        sources.append(path)
    runtime = work / 'runtime.cpp'
    prototypes = '\n'.join(f'bool bqt_op_{identifier}(BqtRequest *);' for identifier, _ in operations)
    write_changed(runtime, '#include "shared.hpp"\nnamespace bendqt {\n' + ''.join(traits) + prototypes + suffix)
    sources.append(runtime)
    manifest = dict(source_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),
                    shared_sha256=hashlib.sha256(header.read_bytes()).hexdigest(),
                    shared_bytes=header.stat().st_size, operation_count=len(operations),
                    shard_count=len(groups), declarations=declarations,
                    auxiliary_function_count=len(auxiliary), auxiliary_shard_count=len(auxiliary_groups),
                    auxiliary_groups=[dict(family=group[0][0], identifiers=[item[1] for item in group])
                                      for group in auxiliary_groups],
                    files=[str(path) for path in sources])
    (work / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return header, sources, manifest


def check_syntax(source, work, flags, maximum_operations=2048):
    from native_workspace import open_workspace
    with open_workspace(source, work) as workspace:
        return _check_syntax(source, workspace.work, flags, maximum_operations)


def _check_syntax(source, work, flags, maximum_operations=2048):
    """Check every generated body without instantiating all factories at once.

    The PCH checks the complete shared runtime. Each bounded operation/factory
    unit is then checked against that same PCH, including the dispatcher.
    Nothing is erased or omitted to make the syntax pass cheaper.
    """
    started = time.monotonic()
    source, work = source.resolve(), work.resolve()
    directory = work / 'syntax-shards'
    flags = [flag for flag in flags if flag != '-fsyntax-only']
    flags += ['-iquote', str(source.parent)]
    header, sources, manifest = prepare(source, directory, flags[1:], maximum_operations,
        maximum_auxiliary_functions=int(os.environ.get('BQT_AUXILIARY_FUNCTIONS', '128')))
    limit_mib = int(os.environ.get('BQT_COMPILER_AS_MIB', '12288'))
    jobs = int(os.environ.get('BQT_SHARD_JOBS', '2'))
    if limit_mib <= 0 or jobs < 1:
        raise ValueError('Native syntax checking requires a positive compiler memory limit and worker count')
    active, lock, cancelled, resources = {}, threading.Lock(), threading.Event(), []
    def run(command, name):
        report = diagnostic_path(directory / (name + '-resources.json'))
        command = ['prlimit', '--as=' + str(limit_mib * 1024 * 1024), '--',
            '/usr/bin/time', '-q', '-f', '{"elapsed_seconds": %e, "peak_rss_kib": %M}', '-o', str(report),
            *map(str, command)]
        if cancelled.is_set(): raise RuntimeError('Native syntax checking cancelled after another unit failed')
        log_path = diagnostic_path(directory / (name + '.log'))
        with log_path.open('w') as log:
            with subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, text=True, start_new_session=True) as process:
                with lock:
                    active[name] = process
                    if cancelled.is_set():
                        try: os.killpg(process.pid, signal.SIGTERM)
                        except ProcessLookupError: pass
                try: status = process.wait()
                finally:
                    with lock: active.pop(name, None)
        if status: raise RuntimeError(f'Native syntax unit {name} failed ({status}); see {log_path}')
        resources.append(dict(name=name, **json.loads(report.read_text())))
    pch = directory / 'shared.pch'
    run([*flags, '-x', 'c++-header', header, '-o', pch], 'shared')
    with ThreadPoolExecutor(max_workers=jobs) as workers:
        pending = [workers.submit(run, [*flags, '-include-pch', pch, '-fsyntax-only', part], part.stem)
                   for part in sources]
        try:
            for future in as_completed(pending): future.result()
        except BaseException:
            cancelled.set()
            for future in pending: future.cancel()
            with lock:
                for process in active.values():
                    try: os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError: pass
            raise
    receipt = dict(passed=True, source_sha256=manifest['source_sha256'],
        shared_sha256=manifest['shared_sha256'], operation_count=manifest['operation_count'],
        operation_units=manifest['shard_count'], auxiliary_functions=manifest['auxiliary_function_count'],
        auxiliary_units=manifest['auxiliary_shard_count'], checked_units=[part.name for part in sources],
        compiler=flags[0], flags=flags[1:], compiler_jobs=jobs, compiler_address_limit_mib=limit_mib,
        elapsed_seconds=time.monotonic() - started, resources=resources,
        max_command_peak_rss_kib=max(item['peak_rss_kib'] for item in resources))
    (work / 'native-syntax.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def compile_objects(source, work, flags, maximum_operations=2048, *, combine=True):
    started = time.monotonic()
    source = source.resolve()
    work = work.resolve()
    directory = work / 'shards'
    flags = [*flags, '-iquote', str(source.parent)]
    maximum_auxiliary = int(os.environ.get('BQT_AUXILIARY_FUNCTIONS', '128'))
    header, sources, manifest = prepare(source, directory, flags[1:], maximum_operations,
                                      maximum_auxiliary_functions=maximum_auxiliary)
    # Every compiler is bounded independently, including PCH generation. This
    # limit is maintainer configuration and has no effect on the native payload.
    limit = int(os.environ.get('BQT_COMPILER_AS_MIB', '12288')) * 1024 * 1024
    jobs = int(os.environ.get('BQT_SHARD_JOBS', '1'))
    if limit <= 0 or jobs < 1:
        raise ValueError('Native shard compilation requires a positive memory limit and worker count')
    resources = []
    cached = []
    digests = {}
    active = {}
    active_lock = threading.Lock()
    cancelled = threading.Event()
    def digest(path):
        path = str(Path(path).resolve())
        if path not in digests:
            value = hashlib.sha256()
            with Path(path).open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    value.update(block)
            digests[path] = value.hexdigest()
        return digests[path]
    def run(command, name):
        report = diagnostic_path(directory / (name + '-resources.json'))
        args = ['prlimit', '--as=' + str(limit) + ':' + str(limit), '--',
                '/usr/bin/time', '-q', '-f', '{"elapsed_seconds": %e, "peak_rss_kib": %M}', '-o', str(report), *map(str, command)]
        if cancelled.is_set():
            raise RuntimeError('Native shard compilation was cancelled after another unit failed')
        log_path = diagnostic_path(directory / (name + '.log'))
        with log_path.open('w') as output:
            # prlimit avoids preexec_fn, which is unsafe after Python creates
            # worker threads. A process group lets a failed unit stop its peer's
            # compiler and timer, rather than leave an orphan consuming memory.
            with subprocess.Popen(args, stdout=output, stderr=subprocess.STDOUT, text=True, start_new_session=True) as process:
                with active_lock:
                    active[name] = process
                    if cancelled.is_set():
                        try: os.killpg(process.pid, signal.SIGTERM)
                        except ProcessLookupError: pass
                try:
                    status = process.wait()
                finally:
                    with active_lock:
                        active.pop(name, None)
        if status:
            raise NativeCompileFailure(name, status, log_path)
        resources.append(dict(name=name, **json.loads(report.read_text())))
    def file_stats(paths):
        return {path: [Path(path).stat().st_size, Path(path).stat().st_mtime_ns] for path in paths}
    def compile_cached(command, name, output, dependencies, key, *, timestamps=False, compatible_keys=()):
        stamp = directory / (name + '-cache.json')
        if stamp.exists() and output.exists():
            try:
                old = json.loads(stamp.read_text())
                if (old['key'] in (key, *compatible_keys) and old['output'] == digest(output)
                        and all(Path(path).is_file() and digest(path) == value for path, value in old['dependencies'].items())
                        and (not timestamps or old.get('dependency_stats') == file_stats(old['dependencies']))):
                    if old['key'] != key:
                        old['key'] = key
                        stamp.write_text(json.dumps(old, indent=2) + '\n')
                    cached.append(name)
                    return set(old['dependencies'])
            except (OSError, KeyError, ValueError):
                pass
        run(command, name)
        digests.pop(str(output.resolve()), None)
        paths = set(shlex.split(dependencies.read_text().replace('\\\n', '').partition(':')[2])) if dependencies else set()
        tracked = {str(Path(path).resolve()): digest(path) for path in paths}
        record = dict(key=key, output=digest(output), dependencies=tracked)
        if timestamps:
            record['dependency_stats'] = file_stats(tracked)
        stamp.write_text(json.dumps(record, indent=2) + '\n')
        return paths
    pch = directory / 'shared.pch'
    dependencies = directory / 'shared.d'
    version = subprocess.run([flags[0], '--version'], check=True, text=True, capture_output=True).stdout
    base_key = dict(flags=flags, compiler=version)
    pch_key = dict(base_key, source=digest(header))
    # Old object caches used the binary PCH hash. A timestamp-only rebuild may
    # preserve those objects, but only with a verified certificate that every
    # previous PCH input, compiler flag and compiler version is unchanged.
    previous_pch = None
    try:
        old = json.loads((directory / 'shared-cache.json').read_text())
        if (old['key'] == pch_key and old['output'] == digest(pch)
                and all(Path(path).is_file() and digest(path) == value for path, value in old['dependencies'].items())):
            previous_pch = old['output']
    except (OSError, KeyError, ValueError):
        pass
    paths = compile_cached([*flags, '-x', 'c++-header', '-MD', '-MF', dependencies, header, '-o', pch],
                           'shared', pch, dependencies, pch_key, timestamps=True)
    pch_record = json.loads((directory / 'shared-cache.json').read_text())
    # Objects depend on the PCH's complete semantic inputs, not its serialized
    # timestamps. Clang still validates the actual PCH for each new compilation.
    pch_inputs = hashlib.sha256(json.dumps(dict(key=pch_record['key'], dependencies=pch_record['dependencies']),
                                           sort_keys=True).encode()).hexdigest()
    objects = []
    def compile_part(part):
        obj = part.with_suffix('.o')
        dep = part.with_suffix('.d')
        key = dict(base_key, source=digest(part), pch_inputs=pch_inputs)
        compatible = (dict(base_key, source=digest(part), pch=previous_pch),) if previous_pch else ()
        return compile_cached([*flags, '-include-pch', pch, '-MD', '-MF', dep, '-c', part, '-o', obj],
                              part.stem, obj, dep, key, compatible_keys=compatible)
    # Hash common PCH data before workers start, avoiding repeated large reads.
    digest(pch)
    keep_going = os.environ.get('BQT_SHARD_KEEP_GOING', '0') == '1'
    failures = []
    completed = 0
    def progress():
        report = dict(source_sha256=manifest['source_sha256'], total=len(sources), completed=completed,
                      cached=list(cached), failures=[dict(name=error.name, status=error.status, log=str(error.log))
                                                     for error in failures])
        diagnostic_path(work / 'native-build-progress.json').write_text(json.dumps(report, indent=2) + '\n')
    progress()
    with ThreadPoolExecutor(max_workers=jobs) as workers:
        pending = [workers.submit(compile_part, part) for part in sources]
        try:
            for future in as_completed(pending):
                try:
                    paths.update(future.result())
                except NativeCompileFailure as error:
                    if not keep_going:
                        raise
                    failures.append(error)
                    print(str(error), flush=True)
                completed += 1
                progress()
                if completed % 10 == 0 or completed == len(sources):
                    print(f'Native C++: {completed}/{len(sources)} units checked, {len(failures)} failed', flush=True)
        except BaseException:
            cancelled.set()
            for future in pending:
                future.cancel()
            with active_lock:
                for process in active.values():
                    try: os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError: pass
            raise
    if failures:
        raise RuntimeError(f'Native C++ compilation failed in {len(failures)} units; successful units remain cached:\n'
                           + '\n'.join(str(error) for error in failures))
    objects = [part.with_suffix('.o') for part in sources]
    output = work / 'wrappers.o'
    if combine:
        from native_linker import select
        linker = select(flags[0])
        compile_cached([flags[0], *linker['flags'], '-nostdlib', '-r', *objects, '-o', output], 'combined', output, None,
                       dict(base_key, linker=linker['identity'], objects=[digest(path) for path in objects]))
    # The ordinary cache records all actual inputs, including the generated
    # common header and shards, instead of trusting a stale PCH timestamp.
    (work / 'wrappers.d').write_text('wrappers.o: ' + ' '.join(shlex.quote(path) for path in sorted(paths)) + '\n')
    (work / 'native-resources.json').write_text(json.dumps(dict(
        elapsed_seconds=time.monotonic() - started,
        sum_command_elapsed_seconds=sum(item['elapsed_seconds'] for item in resources),
        max_command_peak_rss_kib=max((item['peak_rss_kib'] for item in resources), default=0),
        combined_job_peak_rss_measured=False,
        compiler_address_limit_mib=limit // 1024 // 1024,
        compiler_jobs=jobs, shards=resources, cached=cached), indent=2) + '\n')
    result = dict(operation_shards=manifest['shard_count'], operation_count=manifest['operation_count'],
                auxiliary_shards=manifest['auxiliary_shard_count'],
                auxiliary_functions=manifest['auxiliary_function_count'],
                common_header_bytes=manifest['shared_bytes'], shared_runtime='C++17 inline ODR',
                compiler_address_limit_mib=limit // 1024 // 1024)
    if not combine:
        result['object_files'] = [str(path) for path in objects]
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('work', type=Path)
    parser.add_argument('flags', type=Path)
    parser.add_argument('--operations', type=int, default=2048)
    parser.add_argument('--auxiliary-functions', type=int, default=128)
    args = parser.parse_args()
    prepare(args.source.resolve(), args.work.resolve(), json.loads(args.flags.read_text()), args.operations,
            maximum_auxiliary_functions=args.auxiliary_functions)
