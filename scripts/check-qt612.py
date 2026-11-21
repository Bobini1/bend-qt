#!/usr/bin/env python3
"""Integration checks for the generated package. Never publishes to the public hub."""
import argparse
import errno
import functools
import hashlib
import http.server
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import time
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build/qt612/check"
BEND = Path.home() / ".bend/bin/bend"
EXAMPLES = {
    'main': 'QT612_OK', 'lifetimes': 'QT612_LIFETIMES_OK',
    'actions': 'QT612_ACTIONS_OK', 'quick': 'QT612_QUICK_OK',
    'numbers': 'QT612_NUMBERS_OK', 'containers': 'QT612_CONTAINERS_OK',
    'signals': 'QT612_SIGNALS_OK', 'references': 'QT612_REFERENCES_OK',
    'custom-signals': 'QT612_CUSTOM_SIGNALS_OK',
    'typed-data': 'QT612_TYPED_DATA_OK', 'qml-creatable': 'QT612_QML_CREATABLE_OK',
    'properties': 'QT612_PROPERTIES_OK',
    'thread-pool-await': 'QT612_THREAD_POOL_AWAIT_OK',
    'ownership': 'QT612_OWNERSHIP_OK', 'host-lifetime': 'QT612_HOST_LIFETIME_OK',
    'retention': 'QT612_RETENTION_OK', 'retention-parent': 'QT612_RETENTION_PARENT_OK',
    'shutdown-retention': 'QT612_SHUTDOWN_OK', 'object-signals': 'QT612_OBJECT_SIGNALS_OK',
    'child-lookup': 'QT612_CHILD_LOOKUP_OK',
    'bytes': 'QT612_BYTES_OK', 'representations': 'QT612_REPRESENTATIONS_OK',
    'buffers': 'QT612_BUFFERS_OK', 'callbacks': 'QT612_CALLBACKS_OK',
    'collections-retention': 'QT612_COLLECTION_RETENTION_OK', 'destruction': 'QT612_DESTRUCTION_OK',
    'owning-collections': 'QT612_OWNING_COLLECTIONS_OK',
    'native-items': 'QT612_NATIVE_ITEMS_OK', 'qml-types': 'QT612_QML_TYPES_OK',
    'exceptions': 'QT612_EXCEPTIONS_OK',
    'optional': 'QT612_OPTIONAL_OK', 'shared': 'QT612_SHARED_OK',
    'outputs-extended': 'QT612_OUTPUTS_EXTENDED_OK',
    'mutable-callbacks': 'QT612_MUTABLE_CALLBACKS_OK',
    'factory-callbacks': 'QT612_FACTORY_CALLBACKS_OK',
    'readonly': 'QT612_READONLY_OK',
    'borrowed-only': 'QT612_BORROWED_ONLY_OK',
    'borrowed-values': 'QT612_BORROWED_VALUES_OK',
    'raw-storage': 'QT612_RAW_STORAGE_OK',
    'persistent-storage': 'QT612_PERSISTENT_STORAGE_OK',
    'network-retention': 'QT612_NETWORK_RETENTION_OK',
    'typed-views': 'QT612_TYPED_VIEWS_OK',
    'role-data': 'QT612_ROLE_DATA_OK',
    'model-indices': 'QT612_MODEL_INDICES_OK',
    'qml-lists': 'QT612_QML_LISTS_OK',
    'generic-invocation': 'QT612_GENERIC_INVOCATION_OK',
    'geometry-outputs': 'QT612_GEOMETRY_OUTPUTS_OK',
    'metadata-origins': 'QT612_METADATA_ORIGINS_OK',
    'gl-mappings': 'QT612_GL_MAPPINGS_OK',
    'graphics-callbacks': 'QT612_GRAPHICS_CALLBACKS_OK',
    'scenegraph-callbacks': 'QT612_SCENEGRAPH_CALLBACKS_OK',
    'retained-callbacks': 'QT612_RETAINED_CALLBACKS_OK',
    'futures': 'QT612_FUTURES_OK',
    'opengl': 'QT612_OPENGL_OK',
    'buffers-extended': 'QT612_BUFFERS_EXTENDED_OK',
    'graphics-buffers': 'QT612_GRAPHICS_BUFFERS_OK',
    'memory-views': 'QT612_MEMORY_VIEWS_OK',
    'image-buffers': 'QT612_IMAGE_BUFFERS_OK',
    'boundary-finders': 'QT612_BOUNDARY_FINDERS_OK',
    'incubation': 'QT612_INCUBATION_OK',
    'file-mappings': 'QT612_FILE_MAPPINGS_OK',
    'shared-memory': 'QT612_SHARED_MEMORY_OK',
    'iterators': 'QT612_ITERATORS_OK',
    'moves': 'QT612_MOVES_OK',
    'dbus': 'QT612_DBUS_OK',
    'thread-pool': 'QT612_THREAD_POOL_OK',
    'render-jobs': 'QT612_RENDER_JOBS_OK',
    'metadata': 'QT612_METADATA_OK',
    'metatypes': 'QT612_METATYPES_OK',
    'primitive-storage': 'QT612_PRIMITIVE_STORAGE_OK',
    'testlib': 'QT612_TESTLIB_OK',
    'variants': 'QT612_VARIANTS_OK',
    'public-fields': 'QT612_PUBLIC_FIELDS_OK',
    'operators': 'QT612_OPERATORS_OK',
    'value-pointers': 'QT612_VALUE_POINTERS_OK',
    'xpm-arrays': 'QT612_XPM_ARRAYS_OK',
    'text-indexing': 'QT612_TEXT_INDEXING_OK',
    'byte-extents': 'QT612_BYTE_EXTENTS_OK',
    'bounded-inputs': 'QT612_BOUNDED_INPUTS_OK',
    'allocated-bytes': 'QT612_ALLOCATED_BYTES_OK',
    'gl-sync': 'QT612_GL_SYNC_OK',
    'gl-raw-mappings': 'QT612_GL_RAW_MAPPINGS_OK',
    'gl-retained': 'QT612_GL_RETAINED_OK',
    'gl-pixel-offsets': 'QT612_GL_PIXEL_OFFSETS_OK',
    'native-platform': 'QT612_NATIVE_PLATFORM_OK',
    'byte-iterators': 'QT612_BYTE_ITERATORS_OK',
    'volume-data': 'QT612_VOLUME_DATA_OK',
    'native-interop': 'QT612_NATIVE_INTEROP_OK',
    'url-handlers': 'QT612_URL_HANDLERS_OK',
    'state-properties': 'QT612_STATE_PROPERTIES_OK',
    'qml-enums': 'QT612_QML_ENUMS_OK',
    'modules': 'QT612_MODULES_OK',
}


# Timeouts stop a hung check and are sized for a maintainer workstation. A
# slower machine, such as a 4-core CI runner, multiplies them by this factor.
TIMEOUT_SCALE = float(os.environ.get('BQT_CHECK_TIMEOUT_SCALE', '1'))


def run(command, env, cwd, expected=0, timeout=300):
    result = subprocess.run([str(x) for x in command], env=env, cwd=cwd, text=True,
                            capture_output=True, timeout=timeout * TIMEOUT_SCALE)
    if result.returncode != expected:
        raise RuntimeError(f"{command}: {result.returncode}\n{result.stdout[-6000:]}\n{result.stderr[-6000:]}")
    return result


def qt_environment(env, qt, *, bundled_runtime=False):
    result = dict(env, QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software', BEND_QT_CHECK_SHUTDOWN='1')
    result.pop('BEND_QT_RUNTIME', None); result.pop('BEND_QT_LIBRARY', None)
    if qt is None:
        return result
    result.update(LD_LIBRARY_PATH=str(qt / "lib"),
                QT_PLUGIN_PATH=str(qt / "plugins"),
                QT_QPA_PLATFORM_PLUGIN_PATH=str(qt / "plugins/platforms"),
                QT_QPA_PLATFORM="offscreen",
                QML_IMPORT_PATH=str(qt / "qml"), QT_QUICK_BACKEND="software", BEND_QT_CHECK_SHUTDOWN="1")
    result['BEND_QT_RUNTIME' if bundled_runtime else 'BEND_QT_LIBRARY'] = str(qt if bundled_runtime else qt / 'lib/libQt6Widgets.so.6')
    return result


def bundled_main(programs):
    imports = ['import Base']
    cases = []
    for index, _ in enumerate(programs):
        imports.append(f'import ./fixture-{index}.bend as Fixture{index}')
        cases.append(f'    case {index}: Fixture{index}.main()')
    return '\n'.join(imports) + '\n\ndef dispatch(id: U32) -> IO(Unit):\n  match id:\n' + '\n'.join(cases) + '''
    case _: IO.die(Unit, 64, "Unknown bundled fixture")

def parsed(value: Maybe<&2, U32>) -> IO(Unit):
  match value:
    case Some{id}: dispatch(id)
    case None{}: IO.die(Unit, 64, "Expected a fixture number")

def select(arguments: List<String>) -> IO(Unit):
  match arguments:
    case program <> selected <> Nil{}: parsed(U32.read(selected))
    case _: IO.die(Unit, 64, "Expected exactly one fixture selector")

def main() -> IO(Unit):
  do IO<Unit>:
    arguments: List<String> <- IO.args()
    select(arguments)
'''


def package_file_names(package_dir):
    """Mirror the generated package's foreign imports, including runtime assets.

    A two-file test registry would silently omit the bundled runtime, unlike
    stock Bend's publisher which includes each imported foreign C file.
    """
    root = Path(package_dir).resolve()
    names = {'qt.bend', 'qt.c'}
    source = (root / 'qt.bend').read_text()
    for imported in re.findall(r'^\s*import\s+"([^"\n]+\.(?:c|js))"\s*$', source, re.M):
        candidate = (root / imported).resolve()
        if not candidate.is_relative_to(root) or not candidate.is_file():
            raise ValueError('A generated foreign import is absent or escapes its package: ' + imported)
        names.add(candidate.relative_to(root).as_posix())
    for name in list(names):
        license_path = (root / name).parent / 'LICENSE'
        if license_path.is_file():
            names.add(license_path.relative_to(root).as_posix())
    if (root / 'README.md').is_file():
        if (root / 'README.md').stat().st_size > 65536:
            raise ValueError('Package README exceeds Bend 2.0.40\'s 65536-byte publication limit')
        names.add('README.md')
    return sorted(names)


def package_files(package_dir):
    root = Path(package_dir).resolve()
    return {name: (root / name).read_bytes() for name in package_file_names(root)}


def consumer_build_slots(files, jobs):
    """How many consumer builds of this package fit in memory at once.

    The Bend compiler holds about 106 bytes per byte of package Bend source
    while it builds a consumer: 9.1 GB for the 86 MB Qt 6.12 qt.bend. Parallel
    builds past the available memory get the machine OOM-killed, as happened to
    16 GB CI runners, so builds take a slot; fixture runs stay parallel."""
    source = sum(len(data) for name, data in files.items() if name.endswith('.bend'))
    need = source * 128 + (512 << 20)
    try:
        meminfo = Path('/proc/meminfo').read_text()
        available = int(re.search(r'^MemAvailable:\s+(\d+) kB$', meminfo, re.M).group(1)) * 1024
    except (OSError, AttributeError):
        return 1
    return max(1, min(jobs, available // need))


def check_package(package_dir, programs, env, runtimes, output, jobs=1, bundle=False, runtime_overrides=None):
    programs = list(programs)
    if not programs or jobs < 1:
        raise ValueError('Consumer checks require at least one program and one job')
    package_dir, output = Path(package_dir).resolve(), Path(output).resolve()
    files = package_files(package_dir)
    build_slots = consumer_build_slots(files, jobs)
    build_gate = threading.BoundedSemaphore(build_slots)
    coverage = package_dir / 'coverage.json'
    bundled_runtime = bool(json.loads(coverage.read_text()).get('bundled_runtime')) if coverage.is_file() else False
    if bundled_runtime:
        runtimes = list(dict.fromkeys([None, *runtimes]))
    manifest = "".join(f"{hashlib.sha256(data).hexdigest()} {name}\n" for name, data in sorted(files.items()))
    package = "0x" + hashlib.sha256(manifest.encode()).hexdigest()[:32]
    output.mkdir(parents=True, exist_ok=True)
    requests = []
    results = []
    builds = []
    failures = []
    mode = 'bundled' if bundle else 'standalone'
    validation_executable = output / ('bundled-app' if bundle else programs[0][0])
    validation_arguments = ['0'] if bundle else []
    with tempfile.TemporaryDirectory(prefix="bend-qt612-consumer-") as directory:
        tmp = Path(directory)
        registry = tmp / "registry"
        target = registry / package
        target.mkdir(parents=True)
        for name, data in files.items():
            destination = target / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        (target / "manifest").write_text(manifest)

        class Handler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                super().do_GET()

            def log_message(self, *args): pass

        class RegistryServer(http.server.ThreadingHTTPServer):
            # Each fresh Bend consumer fetches runtime assets concurrently.
            # The default backlog of five can drop bursts from parallel builds.
            request_queue_size = 256

        server = RegistryServer(
            ("127.0.0.1", 0), functools.partial(Handler, directory=str(registry)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            build_env = dict(env, BEND_HUB=f"http://127.0.0.1:{server.server_port}",
                             CXX="/no-consumer-cxx",
                             CPLUS_INCLUDE_PATH="/no-consumer-qt-headers", PKG_CONFIG_LIBDIR="/no-consumer-pc")
            def capture(command, environment, cwd, log, timeout):
                timeout *= TIMEOUT_SCALE
                try:
                    result = subprocess.run(command, env=environment, cwd=cwd, text=True,
                                            capture_output=True, timeout=timeout)
                except subprocess.TimeoutExpired as error:
                    def text(value):
                        return value.decode(errors='replace') if isinstance(value, bytes) else value or ''
                    log.write_text(text(error.stdout) + text(error.stderr) + f'\nTimed out after {timeout} seconds\n')
                    raise
                log.write_text(result.stdout + result.stderr)
                return result

            def compile_program(label, consumer, executable, included):
                consumer_env = dict(build_env, BEND_LIB=str(tmp / 'empty-cache' / label))
                command = [str(BEND), 'main.bend', '-o', str(executable)]
                started = time.monotonic()
                record = {'mode': mode, 'programs': included, 'executable': str(executable),
                          'command': command, 'fresh_hub_cache': True,
                          'exit_code': None, 'validated': False}
                builds.append(record)
                try:
                    with build_gate:
                        compiled = capture(command, consumer_env, consumer, output / f'{label}-build.log', 600)
                    record['exit_code'] = compiled.returncode
                finally:
                    record['elapsed_seconds'] = time.monotonic() - started
                if compiled.returncode or compiled.stderr:
                    raise RuntimeError(f'Consumer compilation failed: {compiled.returncode}\n'
                                       + compiled.stdout[-6000:] + compiled.stderr[-6000:])
                dependencies = run(["ldd", executable], env, consumer).stdout
                (output / f"{label}-dependencies.log").write_text(dependencies)
                if "libQt" in dependencies or "libstdc++" in dependencies:
                    raise RuntimeError("Consumer unexpectedly links Qt or C++ at build time")
                record.update(validated=True, executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
                              no_build_time_qt_or_cpp_link=True)

            def check_program(indexed):
                index, program = indexed
                name, source, marker = program
                consumer = tmp / 'consumer' / name
                consumer.mkdir(parents=True)
                runs = []
                if bundle:
                    executable = validation_executable
                    arguments = [str(index)]
                else:
                    source = source.replace("../../packages/qt612/qt.bend", f"{package}/qt.bend")
                    (consumer / "main.bend").write_text(source)
                    executable = output / name
                    arguments = []
                    compile_program(name, consumer, executable, [name])
                for qt in runtimes:
                    command = [str(executable), *arguments, "+RTS", "--threads", "2"]
                    if name == 'dbus':
                        command = ['dbus-run-session', '--', *command]
                    if name in ('scenegraph-material-render', 'scenegraph-material-instances'):
                        command = ['bash', str(ROOT / 'scripts/run-qt-render-check.sh'), *command]
                    label = hashlib.sha256(str(qt).encode()).hexdigest()[:8]
                    runtime_environment = qt_environment(env, qt, bundled_runtime=bundled_runtime)
                    overrides = (runtime_overrides or {}).get(name, {})
                    runtime_environment.update(overrides)
                    tested = capture(command, runtime_environment, consumer,
                                     output / f"{name}-{label}.log", 300)
                    if tested.returncode or marker not in tested.stdout:
                        raise RuntimeError(f'Native fixture failed: {tested.returncode}\n' + tested.stdout + tested.stderr)
                    runs.append({"program": name, "qt_root": str(qt), "marker": marker,
                                 'build_mode': mode, 'executable': str(executable), 'arguments': arguments,
                                 'fresh_process': True, 'isolated_working_directory': True,
                                 'runtime_overrides': overrides})
                    print(f"PASS {name}: {qt}", flush=True)
                return runs

            def checked(indexed):
                try:
                    return check_program(indexed)
                except Exception as error:
                    program = indexed[1]
                    failures.append({'program': program[0], 'error': str(error)})
                    print(f"FAIL {program[0]}: {error}", flush=True)
                    return []

            if bundle:
                consumer = tmp / 'bundle-build'
                consumer.mkdir()
                for index, (_, source, _) in enumerate(programs):
                    (consumer / f'fixture-{index}.bend').write_text(source.replace(
                        '../../packages/qt612/qt.bend', f'{package}/qt.bend'))
                source = bundled_main(programs)
                (consumer / 'main.bend').write_text(source)
                (output / 'bundled-main.bend').write_text(source)
                try:
                    compile_program('bundled', consumer, validation_executable, [program[0] for program in programs])
                except Exception as error:
                    failures.append({'program': 'bundled compilation', 'error': str(error)})
                    print(f'FAIL bundled compilation: {error}', flush=True)
            if not failures:
                with ThreadPoolExecutor(max_workers=jobs) as pool:
                    for runs in pool.map(checked, enumerate(programs)): results.extend(runs)
            (output / 'failures.json').write_text(json.dumps(failures, indent=2) + '\n')
            builds.sort(key=lambda build: build['executable'])
            (output / 'consumer-builds.json').write_text(json.dumps(builds, indent=2) + '\n')
            if failures:
                raise RuntimeError('Consumer checks failed: ' + ', '.join(item['program'] for item in failures)
                                   + f'; details: {output / "failures.json"}')
            if {f"/{package}/qt.bend", f"/{package}/qt.c", f"/{package}/manifest"} - set(requests):
                raise RuntimeError(f"Required Hub files were not fetched: {requests}")
            if set(requests) - {f"/{package}/{name}" for name in (*files, "manifest")}:
                raise RuntimeError(f"Unexpected Hub fetches: {requests}")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
    return {"package": package, "fetches": requests, "runs": results,
            "consumer_build": "bend main.bend -o app", "generator_used_by_consumer": False,
            'build_mode': mode, 'builds': builds, 'compile_count': len(builds), 'build_slots': build_slots,
            'validation_executable': str(validation_executable), 'validation_arguments': validation_arguments}


def extension_check(env, qt, extractor):
    """Add QtXml to a minimal module profile without specifying any classes."""
    with tempfile.TemporaryDirectory(prefix="bend-qt612-extension-") as directory:
        tmp = Path(directory)
        profile = tmp / "profile"
        profile.mkdir()
        config = json.loads((ROOT / "generator/qt612/profile.json").read_text())
        config["qt_modules"] = ["QtCore", "QtGui", "QtWidgets", "QtXml"]
        # This is an installed-runtime API discovery fixture, not a release.
        # The production selective distribution has separate release gates.
        config.pop('license_flavor', None)
        config.pop('native_modules', None)
        assert "classes" not in config and "owned_value_types" not in config
        (profile / "profile.json").write_text(json.dumps(config))
        package = tmp / "package"
        try:
            generated = run(["python3", ROOT / "generator/generate.py", "--profile", profile,
                             "--qt-prefix", qt, "--extractor", extractor,
                             "--work", tmp / "work", "--output", package], env, ROOT, timeout=1800)
        except Exception:
            # Preserve the actual compiler/extractor diagnostics before the
            # temporary generation tree is cleaned up.
            failure = OUT / 'extension-failures' / tmp.name
            failure.mkdir(parents=True)
            for source in tmp.rglob('*'):
                target = failure / source.relative_to(tmp)
                if source.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    # Mounted Windows workspaces do not support copy2's
                    # Unix metadata preservation. Keep file contents only.
                    shutil.copyfile(source, target)
            print(f'Extension failure artifacts: {failure}', flush=True)
            raise
        (OUT / "extension-generation.log").write_text(generated.stdout + generated.stderr)
        coverage = json.loads((package / "coverage.json").read_text())
        if not any(m["class"] == "QDomDocument" and m["bend_name"] == "QDomDocument.isNull" for m in coverage["generated"]):
            raise RuntimeError("QtXml was not automatically extracted and generated")
        gui_gl = run(['python3', ROOT / 'scripts/check-qt-gl-gui-native.py',
                      '--work', tmp / 'work', '--qt-root', qt], env, ROOT, timeout=900)
        (OUT / 'extension-gui-gl.log').write_text(gui_gl.stdout + gui_gl.stderr)
        gui_gl_receipt = json.loads((tmp / 'work/gui-gl-native-check/receipt.json').read_text())
        source = '''import Base
import ../../packages/qt612/qt.bend as Qt
def check(ok: Bool) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, "Generated extension failed")
def document(value: Qt.QDomDocument) -> Qt.Action(Bool):
  Qt.QDomNode.with(Bool, Qt.QDomDocument.as_QDomNode(value), Qt.QDomNode.isNull)

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    empty: Bool <- Qt.QDomDocument.with(Bool, Qt.QDomDocument.new(), document)
    check(empty)
    objects: U32 <- Qt.Runtime.liveObjects()
    check(U32.is_eq(objects, 0))
    Qt.Action.lift(Unit, IO.print("QT612_EXTENSION_OK QtXml.QDomDocument=1 scopes=1 objects=0"))
def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => demo())))
'''
        receipt = check_package(package, [("extension", source, "QT612_EXTENSION_OK")],
                                env, [qt], OUT / "extension")
        receipt['gui_only_gl_native'] = gui_gl_receipt
        return receipt


PARTS = ('consumers', 'runtime', 'native', 'conversions', 'callbacks', 'signals', 'regeneration', 'extension')


def generation_digest(package=ROOT / 'packages/qt612', lock=ROOT / 'generator/qt612/names.lock.json'):
    """Hashes of what a generation writes: the published files, coverage and the name lock."""
    package = Path(package)
    digest = {name: hashlib.sha256(data).hexdigest() for name, data in package_files(package).items()}
    digest['coverage.json'] = hashlib.sha256((package / 'coverage.json').read_bytes()).hexdigest()
    digest['names.lock.json'] = hashlib.sha256(Path(lock).read_bytes()).hexdigest()
    return digest


def digest_id(digest):
    return hashlib.sha256(json.dumps(digest, sort_keys=True).encode()).hexdigest()


def differences(first, second):
    return sorted(name for name in first.keys() | second.keys() if first.get(name) != second.get(name))


def checker_id():
    """The check sources a part ran with; the parts of one receipt must share them."""
    digest = hashlib.sha256()
    paths = [*ROOT.glob('*.bend'), *(path for folder in ('scripts', 'examples') for path in (ROOT / folder).rglob('*'))]
    for path in sorted(path for path in paths if path.is_file() and '__pycache__' not in path.parts):
        digest.update(path.relative_to(ROOT).as_posix().encode() + b'\0' + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def part_options(args):
    """The options that decide what a part checks; combined parts must agree on them."""
    return dict(bundle=args.bundle, generator_checks=args.generator_checks,
                reject_system_qt=args.reject_system_qt,
                reject_qt_roots=[str(root) for root in args.reject_qt_root],
                qt_roots=[str(root) for root in args.qt_root or []],
                examples=sorted(args.example or EXAMPLES))


def consumers(c):
    """Proofs, the module check, fresh Hub consumers and rejection of other Qt runtimes."""
    args, env, package = c.args, c.env, c.package
    proved = run(["python3", ROOT / "scripts/check-qt-action-proofs.py", "--mutation-checks"], env, ROOT)
    print(proved.stdout, end="", flush=True)
    formal = json.loads((ROOT / "build/qt612/proofs/receipt.json").read_text())
    checked = run([BEND, package / "qt.bend", "--check-only"], env, ROOT, expected=1)
    (OUT / "module-check.log").write_text(checked.stdout + checked.stderr)
    # The type checker explicitly excludes foreign effects from its proof
    # guarantee. Accept only that diagnostic, never a type error or an unsafe def.
    diagnostic = (checked.stdout + checked.stderr).strip()
    if not re.fullmatch(r"SOME PROOFS FAIL\nError: \d+ defs rely on unsafe or foreign code:\n"
                        r"defs that depend on foreign effects: [A-Za-z0-9_., \n]+", diagnostic):
        raise RuntimeError(diagnostic[:6000])
    distribution_check = None
    if args.generator_checks:
        checked_distribution = run(['python3', ROOT / 'scripts/check-qt-distribution-package.py',
            '--package', package, '--qt-root', args.qt_prefix, '--work', OUT / 'distribution-package'],
            env, ROOT, timeout=2400)
        print(checked_distribution.stdout, end='', flush=True)
        distribution_check = dict(passed=True, stdout=checked_distribution.stdout.strip())
    programs = [(name, (ROOT / f"examples/qt612/{name}.bend").read_text(), marker)
                for name, marker in EXAMPLES.items()
                if not args.example or name in args.example]
    receipt = check_package(package, programs, env, c.runtimes, OUT, jobs=args.jobs, bundle=args.bundle)
    if distribution_check is not None:
        receipt['distribution_package'] = distribution_check
    if args.bundle:
        smoke = [program for program in programs if program[0] in ('main', 'quick', 'actions')]
        if not smoke:
            smoke = programs[:1]
        receipt['standalone_smoke'] = check_package(package, smoke, env, c.runtimes,
            OUT / 'standalone-smoke', jobs=args.jobs)
        receipt['validation_executable'] = receipt['standalone_smoke']['validation_executable']
        receipt['validation_arguments'] = receipt['standalone_smoke']['validation_arguments']
    receipt["consumer_cc_environment"] = "unset"
    receipt["consumer_compiler"] = run(["clang", "--version"], env, ROOT).stdout.splitlines()[0]
    receipt["formal_proofs"] = formal
    executable = Path(receipt['validation_executable'])
    validation_arguments = receipt['validation_arguments']
    receipt["version_test_executable"] = executable.name
    rejections = []
    for root in ([None] if args.reject_system_qt else []) + args.reject_qt_root:
        case_env = qt_environment(env, root, bundled_runtime=c.bundled_runtime)
        if c.bundled_runtime and root is None:
            # A system update must not affect a bundled application. Reject
            # an incompatible runtime only when explicitly selected or already
            # loaded, rather than expecting a failure from system search paths.
            conflict = dict(case_env, LD_LIBRARY_PATH='/usr/lib/x86_64-linux-gnu',
                QT_PLUGIN_PATH='/usr/lib/x86_64-linux-gnu/qt6/plugins',
                QML_IMPORT_PATH='/usr/lib/x86_64-linux-gnu/qt6/qml')
            run([executable, *validation_arguments], conflict, ROOT)
            library = Path('/usr/lib/x86_64-linux-gnu/libQt6Core.so.6')
            if not library.is_file():
                raise RuntimeError('--reject-system-qt needs the conflicting system Qt control')
            case_env = dict(case_env, LD_PRELOAD=str(library))
        # Qt loads on the first Qt call, which then fails with ELIBACC; the
        # program's IO.try boundary reports it on stderr and exits with it.
        result = run([executable, *validation_arguments], case_env, ROOT, expected=errno.ELIBACC)
        markers = ('already loaded', 'does not match this package', 'cannot open shared object') if c.bundled_runtime else (
            'requires Qt 6.12.0; install the matching Qt runtime', 'does not match this package')
        if not any(marker in result.stderr for marker in markers):
            raise RuntimeError(result.stderr)
        rejections.append({"qt_root": str(root or "system"), "diagnostic": result.stderr.strip(),
                           "exit_code": result.returncode})
    for library, marker in (("/missing/libQt6Widgets.so", "/missing/libQt6Widgets.so"), ("libm.so.6", "missing qVersion")):
        if c.bundled_runtime:
            marker = 'BEND_QT_LIBRARY cannot replace a bundled runtime'
        result = run([executable, *validation_arguments], dict(env, BEND_QT_LIBRARY=library), ROOT,
                     expected=errno.ELIBACC)
        if marker not in result.stderr: raise RuntimeError(result.stderr)
    receipt["old_qt_rejections"] = rejections
    receipt["executable_sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
    return receipt


def runtime(c):
    """Runtime bundles and module partitions, naming, effect transport and the native build layout."""
    args, env, package = c.args, c.env, c.package
    receipt = {}
    for name, script, extra in (
            ('selective_runtime', 'check-qt-selective-runtime.py', []),
            ('runtime_cache', 'check-qt-runtime-bundle.py', ['--work', OUT / 'runtime-bundle']),
            ('distribution_modules', 'check-qt-distribution-modules.py', ['--qt-root', args.qt_prefix]),
            ('source_snapshots', 'check-qt-source-snapshots.py', []),
            ('shared_state_analysis', 'check-qt-shared-state-analysis.py', ['--work', OUT / 'shared-state-analysis']),
            ('proxy_meta_provider', 'check-qt-proxy-meta-provider.py', ['--qt-root', args.qt_prefix,
                '--work', OUT / 'proxy-meta-provider']),
            ('range_model_versions', 'check-qt-range-model-versions.py', ['--qt-root', args.qt_prefix,
                '--work', OUT / 'range-model-versions']),
            ('protected_lvalue_getters', 'check-qt-protected-lvalue-getters.py', ['--qt-root', args.qt_prefix,
                '--work', OUT / 'protected-lvalue-getters']),
            ('selective_native_modules', 'check-qt-module-partitions.py', [
                '--qt-root', args.qt_prefix, '--selective', '--scoped', '--bundle-runtime',
                '--value-metatypes', '--qml-imports', '--run', '--work', OUT / 'selective-native-modules'])):
        case_env = dict(env, BQT_STATE_SOURCE_BYTES='0') if name == 'selective_native_modules' else env
        result = run(['python3', ROOT / 'scripts' / script, *extra], case_env, ROOT, timeout=2400)
        print(result.stdout, end='', flush=True)
        receipt[name] = dict(passed=True, stdout=result.stdout.strip())
    output_writes = run(['python3', ROOT / 'scripts/check-qt-generation-writes.py'], env, ROOT, timeout=60)
    print(output_writes.stdout, end='', flush=True)
    receipt['generation_output_writes'] = dict(passed=True, stdout=output_writes.stdout.strip())
    portable = run(['python3', ROOT / 'scripts/check-qt-portable-package.py', '--package', package,
                    '--qt-root', args.qt_prefix], env, ROOT, timeout=900)
    print(portable.stdout, end='', flush=True)
    receipt['portable_package'] = dict(passed=True, stdout=portable.stdout.strip())
    overloads = run(["python3", ROOT / "scripts/check-overload-names.py"], env, ROOT, timeout=300)
    print(overloads.stdout, end="", flush=True)
    receipt['overload_names'] = json.loads((OUT / 'overload-names/receipt.json').read_text())
    boundary = run(["python3", ROOT / "scripts/check-pyside-boundary.py",
                    "--qt-root", args.qt_prefix], env, ROOT, timeout=600)
    print(boundary.stdout, end="", flush=True)
    receipt['pyside_boundary'] = json.loads(
        (ROOT / 'build/qt612/pyside-boundary-check/receipt.json').read_text())
    transport = run(["python3", ROOT / "scripts/check-qt612-effect-transport.py",
                     "--qt-root", args.qt_prefix], env, ROOT, timeout=900)
    print(transport.stdout, end="", flush=True)
    receipt['effect_transport'] = json.loads((OUT / 'effect-transport/receipt.json').read_text())
    publication = run(["python3", ROOT / "scripts/check-qt612-publication.py",
                       "--package", package], env, ROOT, timeout=660)
    print(publication.stdout, end="", flush=True)
    receipt['local_publication_client'] = json.loads((OUT / 'publication/receipt.json').read_text())
    native_backend = run(["python3", ROOT / "scripts/check-qt612-backend.py",
                          "--qt-root", args.qt_prefix], env, ROOT, timeout=180)
    print(native_backend.stdout, end="", flush=True)
    receipt['native_payload_backend'] = json.loads((ROOT / 'build/qt612/backend-test/receipt.json').read_text())
    native_shards = run(["python3", ROOT / "scripts/check-qt-native-shards.py",
                         "--qt-root", args.qt_prefix,
                         "--work", OUT / "native-shards"],
                        dict(env, BQT_SHARD_JOBS="2"), ROOT, timeout=600)
    print(native_shards.stdout, end="", flush=True)
    receipt['native_compilation_units'] = json.loads((OUT / 'native-shards/receipt.json').read_text())
    abi_cohorts = run(["python3", ROOT / "scripts/check-qt612-abi-cohorts.py",
                       "--qt-root", args.qt_prefix], env, ROOT, timeout=180)
    print(abi_cohorts.stdout, end="", flush=True)
    receipt['native_abi_cohorts'] = json.loads((ROOT / 'build/qt612/abi-cohort-test/receipt.json').read_text())
    native_events = run(["python3", ROOT / "scripts/check-qt612-native-events.py",
                         "--qt-root", args.qt_prefix, "--extractor", args.extractor],
                        env, ROOT, timeout=900)
    print(native_events.stdout, end="", flush=True)
    receipt['native_event_filters'] = json.loads((OUT / 'native-events/receipt.json').read_text())
    native_names = run(["python3", ROOT / "scripts/check-qt612-native-names.py",
                        "--qt-root", args.qt_prefix, "--extractor", args.extractor],
                       env, ROOT, timeout=900)
    print(native_names.stdout, end="", flush=True)
    receipt['native_names'] = json.loads((OUT / 'native-names/receipt.json').read_text())
    return receipt


def native(c):
    """Native signal, conversion, protected member, destruction and storage guards."""
    args, env = c.args, c.env
    receipt = {}
    native_signals = run(["python3", ROOT / "scripts/check-qt612-signal-native.py",
                          "--qt-prefix", args.qt_prefix], env, ROOT, timeout=1200)
    print(native_signals.stdout, end="", flush=True)
    receipt["native_signal_guards"] = json.loads((OUT / "signal-native/receipt.json").read_text())
    native_conversions = run(["python3", ROOT / "scripts/check-qt612-conversions-native.py",
                              "--qt-root", args.qt_prefix, "--extractor", args.extractor],
                             env, ROOT, timeout=1800)
    print(native_conversions.stdout, end="", flush=True)
    receipt['native_conversion_guards'] = json.loads((ROOT / 'build/qt612/conversions-native-check/receipt.json').read_text())
    explicit_copies = run(['python3', ROOT / 'scripts/check-qt-explicit-copies.py',
                           '--qt-root', args.qt_prefix, '--work', OUT / 'explicit-copies'],
                          env, ROOT, timeout=300)
    print(explicit_copies.stdout, end='', flush=True)
    receipt['explicit_copy_values'] = json.loads((OUT / 'explicit-copies/receipt.json').read_text())
    protected_fields = run(['python3', ROOT / 'scripts/check-qt-protected-fields.py',
                            '--qt-root', args.qt_prefix, '--source-work', ROOT / 'build/qt612',
                            '--work', OUT / 'protected-fields'], env, ROOT, timeout=300)
    print(protected_fields.stdout.strip())
    receipt['protected_fields'] = json.loads((OUT / 'protected-fields/receipt.json').read_text())
    protected_fields_sanitized = run(['python3', ROOT / 'scripts/check-qt-protected-fields.py',
                                      '--qt-root', args.qt_prefix, '--source-work', ROOT / 'build/qt612',
                                      '--work', OUT / 'protected-fields-sanitized', '--sanitize'], env, ROOT, timeout=300)
    print(protected_fields_sanitized.stdout.strip())
    receipt['protected_fields_sanitized'] = json.loads((OUT / 'protected-fields-sanitized/receipt.json').read_text())
    protected_methods = run(['python3', ROOT / 'scripts/check-qt-protected-methods.py',
                              '--qt-root', args.qt_prefix, '--source-work', ROOT / 'build/qt612',
                              '--work', OUT / 'protected-methods'], env, ROOT, timeout=300)
    print(protected_methods.stdout.strip())
    receipt['protected_methods'] = json.loads((OUT / 'protected-methods/receipt.json').read_text())
    signal_shards = run(['python3', ROOT / 'scripts/check-qt-native-signal-shards.py',
                          '--qt-root', args.qt_prefix, '--work', OUT / 'native-signal-shards'],
                         env, ROOT, timeout=600)
    print(signal_shards.stdout.strip())
    receipt['native_signal_shards'] = json.loads((OUT / 'native-signal-shards/receipt.json').read_text())
    audio_buffer_bytes = run(['python3', ROOT / 'scripts/check-qt-audio-buffer-bytes.py',
                              '--qt-root', args.qt_prefix, '--work', OUT / 'audio-buffer-native-bytes'],
                             env, ROOT, timeout=180)
    print(audio_buffer_bytes.stdout.strip())
    receipt['audio_buffer_native_bytes'] = json.loads((OUT / 'audio-buffer-native-bytes/receipt.json').read_text())
    maintenance = run(['python3', ROOT / 'scripts/check-qt-maintenance-workflow.py'],
                      env, ROOT, timeout=120)
    count = re.search(r'Ran (\d+) tests?', maintenance.stderr)
    if not count or int(count[1]) == 0:
        raise RuntimeError('The maintainer workflow regression gate did not execute its tests')
    receipt['maintenance_workflow'] = dict(passed=True, tests=int(count[1]))
    for name, script, extra in (
        ('native_aliases', 'check-qt-native-aliases.py', ['--mutation-checks']),
        ('native_linker', 'check-qt-native-linker.py', []),
        ('qt_link_dependencies', 'check-qt-link-dependencies.py', []),
        ('linked_runtime_preloads', 'check-qt-linked-preloads.py', []),
        ('callback_cpp_spellings', 'check-qt-callback-spellings.py', []),
        ('native_workspace', 'check-qt-native-workspace.py', ['--backend']),
        ('proxy_constructor_shards', 'check-qt-proxy-constructor-shards.py', []),
        ('runtime_dispatch_shards', 'check-qt-runtime-dispatch-shards.py', []),
        ('proxy_virtual_shards', 'check-qt-proxy-virtual-shards.py', []),
    ):
        checked = run(['python3', ROOT / 'scripts' / script, '--qt-root', args.qt_prefix,
                       '--work', OUT / name, *extra], env, ROOT, timeout=600)
        print(checked.stdout.strip())
        receipt[name] = json.loads((OUT / name / 'receipt.json').read_text())
    for name, script, extra in (
        ('render_factories', 'check-qt-render-factories.py', []),
        ('native_destruction', 'check-qt-native-destruction.py', []),
        ('native_worker_destruction', 'check-qt-native-worker-destruction.py', []),
        ('io_pipe', 'check-qt-io-pipe.py', []),
        ('mutex_lockers', 'check-qt-mutex-lockers.py', []),
        ('cursor_guards', 'check-qt-mutex-lockers.py', ['--cursor-guards']),
        ('dynamic_properties', 'check-qt-dynamic-properties.py', []),
    ):
        for sanitized in (False, True):
            key = name + ('_sanitized' if sanitized else '')
            directory = OUT / key.replace('_', '-')
            command = ['python3', ROOT / 'scripts' / script, '--qt-root', args.qt_prefix,
                       '--work', directory, *extra]
            if sanitized:
                command.append('--sanitize')
                if script not in ('check-qt-mutex-lockers.py', 'check-qt-dynamic-properties.py'):
                    command += ['--cxx', 'g++']
            checked = run(command, env, ROOT, timeout=600)
            print(checked.stdout.strip())
            receipt[key] = json.loads((directory / 'receipt.json').read_text())
    native_value_lifetimes = run(["python3", ROOT / "scripts/check-qt612-value-lifetimes-native.py",
                                  "--qt-root", args.qt_prefix, "--extractor", args.extractor],
                                 env, ROOT, timeout=900)
    print(native_value_lifetimes.stdout, end="", flush=True)
    receipt['native_value_lifetime_guards'] = json.loads((OUT / 'value-lifetimes-native/receipt.json').read_text())
    metatypes = run(["python3", ROOT / "scripts/check-qt612-metatypes-native.py",
                    "--qt-root", args.qt_prefix, "--extractor", args.extractor],
                    env, ROOT, timeout=900)
    print(metatypes.stdout, end="", flush=True)
    receipt['native_metatype_storage'] = json.loads((OUT / 'metatypes-native/receipt.json').read_text())
    resource_bounds = run(["python3", ROOT / "scripts/check-qt612-resource-bounds.py",
                           "--qt-root", args.qt_prefix], env, ROOT, timeout=180)
    print(resource_bounds.stdout, end="", flush=True)
    receipt['native_resource_bounds'] = json.loads((OUT / 'resource-bounds/receipt.json').read_text())
    return receipt


def conversions(c):
    """Restored API, dependent fields, converter cleanup and output/array conversions."""
    args, env = c.args, c.env
    receipt = {}
    restoration = run(["python3", ROOT / "scripts/check-qt612-restoration.py",
                       "--qt-root", args.qt_prefix], env, ROOT, timeout=1200)
    print(restoration.stdout, end="", flush=True)
    receipt['restored_native_api'] = json.loads((OUT / 'restoration/receipt.json').read_text())
    aggregate_fields = run(["python3", ROOT / "scripts/check-qt612-dependent-fields.py",
                            "--qt-root", args.qt_prefix, "--records",
                            "--work", OUT / "dependent-fields"], env, ROOT, timeout=1200)
    print(aggregate_fields.stdout, end="", flush=True)
    receipt['native_dependent_fields'] = json.loads((OUT / 'dependent-fields/receipt.json').read_text())
    cleanup_state = run(["python3", ROOT / "scripts/check-qt612-state-cleanup.py",
                         "--qt-root", args.qt_prefix,
                         "--work", OUT / "state-cleanup"], env, ROOT, timeout=1200)
    print(cleanup_state.stdout, end="", flush=True)
    receipt['native_converter_cleanup'] = json.loads((OUT / 'state-cleanup/receipt.json').read_text())
    for name, script, directory in (
        ('native_output_and_array_conversions', 'check-qt-next-conversions-native.py', 'next-conversions-check'),
        ('native_rhi_buffer_access', 'check-qt-next-rhi-buffers.py', 'next-rhi-buffers'),
    ):
        checked = run(['python3', ROOT / 'scripts' / script, '--qt-root', args.qt_prefix],
                      env, ROOT, timeout=1800)
        print(checked.stdout, end='', flush=True)
        receipt[name] = json.loads((ROOT / 'build/qt612' / directory / 'receipt.json').read_text())
    # The paired-array proofs read the wrappers the conversion check generated.
    paired_arrays = run(['python3', ROOT / 'scripts/check-qt-next-conversion-proofs.py'],
                        env, ROOT, timeout=600)
    print(paired_arrays.stdout, end='', flush=True)
    receipt['paired_array_proofs'] = json.loads(
        (ROOT / 'build/qt612/next-conversion-proofs/receipt.json').read_text())
    return receipt


def callbacks(c):
    """Callback guards for every feature."""
    native_callbacks = run(["python3", ROOT / "scripts/check-qt-callbacks.py",
                            "--qt-root", c.args.qt_prefix, "--jobs", str(c.args.jobs), "--all-features"],
                           c.env, ROOT, timeout=14400)
    print(native_callbacks.stdout, end="", flush=True)
    return {"native_callback_guards": json.loads((ROOT / "build/qt612/callbacks/receipt.json").read_text())}


def signals(c):
    """Authored custom signals."""
    custom_signals = run(['python3', ROOT / 'scripts/check-qt-custom-signals.py', '--qt-root', c.args.qt_prefix],
                         c.env, ROOT, timeout=14400)
    print(custom_signals.stdout, end='', flush=True)
    return {'custom_signals': json.loads(
        (ROOT / 'build/qt612/custom-signals-check/custom-signals-receipt.json').read_text())}


def extension(c):
    """Automatic extraction of a module added to a profile."""
    return {"extension": extension_check(c.env, c.args.qt_prefix, c.args.extractor)}


def regeneration(c):
    """Regenerating from the same inputs must reproduce the package and its name lock."""
    args = c.args
    before = generation_digest(c.package)
    regenerate = ["python3", ROOT / "generator/generate.py", "--qt-prefix", args.qt_prefix, "--extractor", args.extractor]
    if args.runtime_manifest:
        regenerate += ['--runtime-manifest', args.runtime_manifest]
    run(regenerate, c.env, ROOT, timeout=14400)
    changed = differences(before, generation_digest(c.package))
    if changed:
        raise RuntimeError("Generation was not deterministic: " + ', '.join(changed))
    return {"deterministic_regeneration": True}


PART_CHECKS = dict(consumers=consumers, runtime=runtime, native=native, conversions=conversions,
                   callbacks=callbacks, signals=signals, regeneration=regeneration, extension=extension)
assert tuple(PART_CHECKS) == PARTS


def finish(receipt):
    receipt["public_hub_publication"] = False
    receipt['verification_complete'] = True
    (OUT / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print("PASS clean Hub imports, native builds, Action/scoped cleanup, lifetime checks and old/missing Qt rejection")


def combine(args, package, required):
    """Merge part receipts recorded for this generation, checker and options.

    A separately produced generation of the same inputs may stand in for the
    regeneration part, provided its digest matches this package exactly."""
    generation = generation_digest(package)
    expected = dict(generation=digest_id(generation), checker=checker_id(), options=part_options(args))
    receipt, combined = {}, []
    for name in required:
        if name == 'regeneration' and args.independent_generation:
            continue
        path = OUT / 'parts' / f'{name}.json'
        if not path.is_file():
            raise RuntimeError('A required part was not recorded: ' + name)
        part = json.loads(path.read_text())
        mismatched = [key for key, value in expected.items() if part.get(key) != value]
        if part.get('part') != name or part.get('passed') is not True or mismatched:
            raise RuntimeError(f'Part {name} was not recorded for this generation, checker and options: '
                               + ', '.join(mismatched or ['passed']))
        receipt.update(part['receipt'])
        combined.append(name)
    if args.independent_generation:
        for path in args.independent_generation:
            changed = differences(generation, json.loads(path.read_text()))
            if changed:
                raise RuntimeError("Generation was not deterministic: " + ', '.join(changed))
        receipt['deterministic_regeneration'] = True
        receipt['independent_generations'] = len(args.independent_generation)
    receipt['combined_parts'] = combined
    finish(receipt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qt-root", action="append", type=Path)
    parser.add_argument("--reject-qt-root", action="append", type=Path, default=[])
    parser.add_argument("--reject-system-qt", action="store_true")
    parser.add_argument("--generator-checks", action="store_true")
    parser.add_argument("--example", action="append", choices=tuple(EXAMPLES),
                        help="Run only these native examples; defaults to all")
    parser.add_argument('--jobs', type=int, default=2, help='Parallel fixture processes or standalone consumer builds')
    parser.add_argument('--bundle', action='store_true',
                        help='Build examples together, run each in a fresh process, then build standalone smoke cases')
    parser.add_argument("--qt-prefix", type=Path, default=Path.home() / ".cache/bend-qt-generator/Qt/6.12.0/gcc_64")
    parser.add_argument("--extractor", type=Path, default=Path.home() / ".cache/bend-qt-generator/build/bend-qt-extract")
    parser.add_argument('--runtime-manifest', type=Path, help='Release inputs for deterministic bundled regeneration')
    parser.add_argument('--part', action='append', choices=PARTS,
                        help='Run only these parts, recording each in check/parts for --combine')
    parser.add_argument('--combine', action='store_true',
                        help='Merge the recorded parts of this generation into the complete receipt')
    parser.add_argument('--independent-generation', action='append', type=Path, default=[],
                        help='With --combine, the generation digest from a separate run, in place of the regeneration part')
    args = parser.parse_args()
    required = list(PARTS if args.generator_checks else PARTS[:1])
    selected = [name for name in required if name in (args.part or required)]
    if args.part and len(selected) < len(set(args.part)):
        parser.error('Only the consumers part runs without --generator-checks')
    if args.combine and args.part:
        parser.error('--combine merges recorded parts and runs none')
    if args.independent_generation and not (args.combine and args.generator_checks):
        parser.error('--independent-generation stands in for the regeneration part of a --combine')
    runtimes = args.qt_root or [Path.home() / ".cache/bend-qt-generator/Qt/6.12.0/gcc_64"]
    package = ROOT / "packages/qt612"
    OUT.mkdir(parents=True, exist_ok=True)
    if args.combine:
        combine(args, package, required)
        return
    # Parts record the sources they started with; checks may write build outputs.
    recorded = dict(checker=checker_id(), options=part_options(args)) if args.part else None
    if not args.part:
        (OUT / 'receipt.json').write_text(json.dumps({'verification_complete': False,
            'stage': 'proofs and module checking'}, indent=2) + '\n')
    env = dict(os.environ, BENDRTS="", QT_QPA_PLATFORM="offscreen")
    for name in ("CC", "LD_LIBRARY_PATH", "LD_PRELOAD", "BEND_QT_LIBRARY", "BEND_QT_RUNTIME", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"):
        env.pop(name, None)
    if run([BEND, "version"], env, ROOT).stdout.strip() != "bend 2.0.40":
        raise RuntimeError("These native effects require Bend 2.0.40")
    coverage = json.loads((package / 'coverage.json').read_text())
    bundled_runtime = bool(coverage.get('bundled_runtime'))
    if bundled_runtime and 'regeneration' in selected and args.runtime_manifest is None:
        metadata = json.loads((ROOT / 'build/qt612/generation.json').read_text())
        if not metadata.get('runtime_release_manifest'):
            raise ValueError('Bundled regeneration needs its verified --runtime-manifest')
        args.runtime_manifest = Path(metadata['runtime_release_manifest'])
    context = SimpleNamespace(args=args, env=env, package=package, runtimes=runtimes, bundled_runtime=bundled_runtime)
    generation = digest_id(generation_digest(package))
    receipt = {}
    for index, name in enumerate(selected):
        if args.part:
            (OUT / 'parts' / f'{name}.json').unlink(missing_ok=True)
        record = PART_CHECKS[name](context)
        receipt.update(record)
        if args.part:
            (OUT / 'parts').mkdir(exist_ok=True)
            (OUT / 'parts' / f'{name}.json').write_text(json.dumps(dict(part=name, passed=True,
                generation=generation, **recorded, receipt=record), indent=2) + '\n')
            print(f'PASS part {name}: {PART_CHECKS[name].__doc__.splitlines()[0]}', flush=True)
        else:
            (OUT / 'receipt.json').write_text(json.dumps(dict(receipt, verification_complete=False,
                completed_parts=selected[:index + 1]), indent=2) + '\n')
    if not args.part:
        finish(receipt)


if __name__ == "__main__":
    main()
