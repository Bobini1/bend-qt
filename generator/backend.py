"""Linux x86-64 code packaging backend. Only the maintainer runs this module."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import ctypes
import os
import shlex
import time


def _exports(library, symbol):
    try:
        getattr(library, symbol)
        return True
    except AttributeError:
        return False


def command(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, text=True,
                          capture_output=True, **kwargs)


def versioned_include_paths(qt: Path, modules):
    # The pinned kit places the documented, limited-ABI RHI headers here.
    # Adding an include search path does not select these headers or APIs.
    from qt_targets import installed_version
    version = installed_version(qt)
    return [path for module in modules
            if (qt / 'include' / module / version / module).is_dir()
            for path in (qt / 'include' / module / version,
                         qt / 'include' / module / version / module)]


def compiler_flags(qt: Path, cxx: str, modules):
    # O2's global value numbering becomes pathological on the full generated
    # proxy inventory. O1 keeps ordinary native optimization without that pass;
    # wrapper calls already cross the native effect boundary.
    flags = [cxx, "-std=c++17", "-O1", "-fPIC", "-fvisibility=hidden", "-ferror-limit=0",
             "-fexceptions", "-frtti", "-fno-addrsig", "-fno-stack-protector",
             "-DQT_NO_VERSION_TAGGING", "-DQT_NO_DEBUG", "-DNDEBUG",
             "-I" + str(qt / "include"), "-I" + str(qt / "mkspecs/linux-g++")]
    for module in modules:
        flags.append("-I" + str(qt / "include" / module))
    flags += ['-I' + str(path) for path in versioned_include_paths(qt, modules)]
    return flags


def validate_backend(source: Path, qt: Path, work: Path, cxx: str, modules):
    flags = compiler_flags(qt, cxx, modules)
    text = source.read_text()
    if 'bqt_op_' in text and (source.stat().st_size > 8_000_000 or
                              text.count('// BQT_AUXILIARY_BEGIN ') >= 128):
        from native_shards import check_syntax
        check_syntax(source, work, flags, int(os.environ.get('BQT_SHARD_OPERATIONS', '2048')) or 2048)
        (work / 'syntax.log').write_text('PASS complete bounded native syntax; see native-syntax.json\n')
        return
    # Large profiles can take minutes to parse. Keep diagnostics readable while
    # compilation is still running instead of buffering them until completion.
    with (work / 'syntax.log').open('w') as log:
        result = subprocess.run([*flags, '-ferror-limit=5', '-fsyntax-only', str(source)],
                                text=True, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'Generated native code failed syntax checking; see {work / "syntax.log"}')


def compile_backend(source: Path, qt: Path, work: Path, cxx: str, modules):
    from native_workspace import open_workspace
    with open_workspace(source, work) as workspace:
        result = _compile_backend(source, qt, workspace.work, cxx, modules, workspace)
        workspace.publish([name for name in ('native.so', 'proxy-traits.bin') if (workspace.work / name).is_file()])
        return result


def _compile_backend(source: Path, qt: Path, work: Path, cxx: str, modules, workspace):
    started = time.monotonic()
    flags = compiler_flags(qt, cxx, modules)
    obj = work / "wrappers.o"
    dependencies = work / 'wrappers.d'
    stamp = work / 'native-compile-cache.json'
    compiler_version = command([cxx, '--version']).stdout
    key = {'source': hashlib.sha256(source.read_bytes()).hexdigest(),
           'source_path': str(source.resolve()),
           'logical_source_path': str(source.absolute()),
           'flags': flags, 'compiler': compiler_version}
    shard_limit = int(os.environ.get('BQT_SHARD_OPERATIONS', '2048'))
    source_text = source.read_text()
    auxiliary_functions = source_text.count('// BQT_AUXILIARY_BEGIN ')
    sharded = shard_limit > 0 and (source.stat().st_size > 8_000_000 or
        'BQT_SHARD_OPERATIONS' in os.environ or auxiliary_functions >= 128) and 'bqt_op_' in source_text
    del source_text
    if sharded:
        from native_linker import select
        key['linker'] = select(cxx)['identity']
        key['sharding'] = {name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
                           for name in ('native_shards.py', 'public_records.py')}
        key['shard_operations'] = shard_limit
        key['auxiliary_functions_per_shard'] = int(os.environ.get('BQT_AUXILIARY_FUNCTIONS', '128'))
    def digest(path):
        hasher = hashlib.sha256()
        with Path(path).open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                hasher.update(chunk)
        return hasher.hexdigest()
    cached = False
    workspace.import_legacy_artifact('wrappers.o', 'native-compile-cache.json', expected_key=key)
    if stamp.exists() and obj.exists():
        try:
            saved = json.loads(stamp.read_text())
            cached = (saved['key'] == key and saved['object'] == digest(obj)
                      and all(Path(path).is_file() and digest(path) == value
                              for path, value in saved['dependencies'].items()))
        except (OSError, KeyError, ValueError):
            cached = False
    if not cached:
        # Full profiles take minutes to compile. Publish diagnostics as Clang
        # produces them, including errors before the translation unit finishes.
        if sharded:
            from native_shards import compile_objects
            shard_metadata = compile_objects(source, work, flags, shard_limit)
            (work / 'native-shards.json').write_text(json.dumps(shard_metadata, indent=2) + '\n')
        else:
            from native_workspace import diagnostic_path
            invocation = [str(x) for x in [*flags, '-MD', '-MF', dependencies, '-MT', 'wrappers.o', '-c', source, '-o', obj]]
            timer = Path('/usr/bin/time')
            if timer.exists():
                invocation = [str(timer), '-q', '-f', '{"elapsed_seconds": %e, "peak_rss_kib": %M}',
                              '-o', str(diagnostic_path(work / 'native-resources.json')), *invocation]
            compile_log = diagnostic_path(work / 'native-compile.log')
            with compile_log.open('w') as log:
                result = subprocess.run(invocation, text=True, stdout=log, stderr=subprocess.STDOUT)
            if result.returncode:
                raise RuntimeError(f'Generated C++ compilation failed; see {compile_log}')
        paths = shlex.split(dependencies.read_text().replace('\\\n', '').partition(':')[2])
        stamp.write_text(json.dumps(dict(key=key, object=digest(obj),
            dependencies={str(Path(path).resolve()): digest(path) for path in paths}), indent=2) + '\n')
    compiled = time.monotonic()
    metadata = json.loads(command(["llvm-readobj-19", "--elf-output-style=JSON",
                                   "--file-headers", obj]).stdout)[0]
    if metadata["FileSummary"]["Format"] != "elf64-x86-64":
        raise RuntimeError("Only the Linux x86-64 ELF backend is implemented")
    proxy_constructibility = None
    trait_bytes = work / 'proxy-traits.bin'
    # Extract just the tiny diagnostic section, without serializing hundreds
    # of thousands of symbols or copying the complete relocatable object.
    with tempfile.TemporaryDirectory(prefix='bend-qt-proxy-traits-') as tmp:
        extracted = Path(tmp) / 'traits.bin'
        command(['llvm-objcopy-19', '--only-section=.bqt.proxy_traits', '--output-target=binary', obj, extracted])
        values = extracted.read_bytes()
    if values:
        if any(value not in (0, 1) for value in values):
            raise RuntimeError('Unexpected native proxy constructibility representation')
        trait_bytes.write_bytes(values)
        proxy_constructibility = [bool(value) for value in values]
    else:
        trait_bytes.unlink(missing_ok=True)
    undefined = sorted(command(['llvm-nm-19', '--undefined-only', '--format=just-symbols', obj]).stdout.splitlines())
    # The native shared object provides its own C++ finalization cookie.
    undefined = [s for s in undefined if s != '__dso_handle']
    inspected = time.monotonic()
    # Successful header compilation is insufficient: some baseline headers
    # declare overloads absent from their shipped libraries. Check every import
    # against the actual selected runtime before producing a consumer package.
    libraries = [ctypes.CDLL(str(qt / 'lib' / ('libQt6' + module[2:] + '.so.6')),
                             mode=os.RTLD_NOW | os.RTLD_LOCAL) for module in modules]
    missing = []
    for name in undefined:
        if not any(_exports(library, name) for library in libraries):
            missing.append(name)
    if missing:
        (work / 'missing-symbols.json').write_text(json.dumps(missing, indent=2) + '\n')
        raise RuntimeError('Baseline Qt/C++ symbols are unavailable: ' + ', '.join(missing[:12]))
    verified = time.monotonic()
    from embedded_elf import package
    embedded, loader, payload = package(obj, qt, work, cxx, modules, command)
    receipt = {"platform": "linux-x86_64", "undefined_symbols": undefined,
               "compiler": compiler_version.splitlines()[0],
               "exceptions": True, "rtti": True, 'optimization': 'O1',
               'proxy_constructibility': proxy_constructibility,
               'compile_cache_hit': cached, 'payload': payload}
    receipt['native_dependency_manifests'] = [str(stamp), str(work / 'native-package-cache.json')]
    if sharded:
        receipt['shards'] = json.loads((work / 'native-shards.json').read_text())
    (work / "backend.json").write_text(json.dumps(receipt, indent=2) + "\n")
    (work / 'native-backend-resources.json').write_text(json.dumps(dict(
        compile_seconds=compiled-started, inventory_seconds=inspected-compiled,
        import_validation_seconds=verified-inspected, package_seconds=time.monotonic()-verified,
        elapsed_seconds=time.monotonic()-started, compile_cache_hit=cached), indent=2) + '\n')
    return embedded, loader, receipt
