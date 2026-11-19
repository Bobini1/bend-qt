"""Link, validate and embed native code; no C++ tools are used by consumers."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import tempfile
import time
import zlib

from backend import toolchain_flags

# Start Qt, run one operation, tear Qt down.
EXPORTS = ('bqt_abi_call', 'bqt_abi_start', 'bqt_abi_stop')


def _digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def _dependency(path):
    path = Path(path).absolute()
    return dict(resolved=str(path.resolve()), sha256=_digest(path))


def _search_directories(cxx, qt, command):
    text = command([cxx, *toolchain_flags(), '-print-search-dirs']).stdout
    libraries = next((line.partition('=')[2] for line in text.splitlines() if line.startswith('libraries:')), '')
    directories = [qt / 'lib', *[Path(value) for value in libraries.split(os.pathsep) if value]]
    result = {}
    for directory in directories:
        path = directory.absolute()
        result[str(path)] = (sorted([entry.name, os.readlink(entry) if entry.is_symlink() else '']
                                    for entry in path.iterdir()) if path.is_dir() else None)
    return result


def _link_dependencies(path):
    # LLD emits one continued dependency rule followed by empty phony rules.
    rule = path.read_text().replace('\\\n', ' ').splitlines()[0]
    fields = re.split(r'(?<!\\):', rule, maxsplit=1)
    if len(fields) != 2:
        raise RuntimeError('Invalid native linker dependency rule: ' + str(path))
    return [value.replace('$$', '$') for value in shlex.split(fields[1])]


def qt_library_closure(qt, modules, command):
    """Link only selected Qt libraries and their actual Qt ELF dependencies.

    Inline public helpers can call a transitive dependency directly. Listing
    that dependency is necessary with -z defs and --no-copy-dt-needed-entries;
    an installed but unrelated Qt module must never enter this closure.
    """
    root = (qt / 'lib').resolve()
    pending = ['libQt6' + module[2:] + '.so.6' for module in modules]
    libraries, seen = [], set()
    while pending:
        name = pending.pop(0)
        if name in seen:
            continue
        if Path(name).name != name:
            raise ValueError('A Qt dependency is not a library basename: ' + name)
        path = root / name
        if not path.is_file() or not path.resolve().is_relative_to(root):
            raise ValueError('A Qt dependency is missing from the selected installation: ' + str(path))
        seen.add(name); libraries.append(name)
        dynamic = command(['readelf', '-d', path]).stdout
        pending.extend(value for value in re.findall(r'\(NEEDED\).*\[(.*?)\]', dynamic)
                       if value.startswith('libQt6'))
    return libraries


def package(obj, qt, work, cxx, modules, command, objects=None):
    """Reuse a validated payload only while every link input remains identical.

    objects, when given, are the relocatable inputs that obj combines; linking
    them directly keeps their address-significance tables for --icf=safe.
    """
    started = time.monotonic()
    from native_linker import select
    linker = select(cxx)
    inputs = [Path(path) for path in objects] if objects else [obj]
    dependency_file = work / 'native-link.d'
    has_dependencies = '--dependency-file' in command([linker['identity']['path'], '--help']).stdout
    payload_file, stamp = work / 'native-payload.c', work / 'native-package-cache.json'
    native = work / 'native.so'
    libraries = qt_library_closure(qt, modules, command)
    key = dict(object=_digest(obj), object_path=str(obj.resolve()), qt=str(qt.resolve()), modules=list(modules),
               link_inputs=[str(path.resolve()) for path in inputs],
               compiler=command([cxx, '--version']).stdout, linker=linker['identity'], qt_libraries=libraries,
               packager=_digest(Path(__file__)), loader=_digest(Path(__file__).parent / 'templates/embedded_elf.c'),
               cache=_digest(Path(__file__).parent / 'templates/native_cache.c'),
               tools={tool: command([tool, '--version']).stdout
                      for tool in ('llvm-strip-19', 'readelf', 'nm', 'llvm-readobj-19')},
               search_directories=_search_directories(cxx, qt, command),
               environment={name: os.environ.get(name) for name in
                            ('LIBRARY_PATH', 'COMPILER_PATH', 'GCC_EXEC_PREFIX', 'LDEMULATION', 'LD_RUN_PATH', 'SOURCE_DATE_EPOCH')})
    if has_dependencies:
        try:
            saved = json.loads(stamp.read_text())
            if (saved['key'] == key and saved['native'] == _digest(native)
                    and saved['payload'] == _digest(payload_file)
                    and saved['dependencies']
                    and all(_dependency(path) == value for path, value in saved['dependencies'].items())):
                (work / 'native-package-resources.json').write_text(json.dumps(dict(
                    cache_hit=True, elapsed_seconds=time.monotonic() - started, linker=linker['identity']), indent=2) + '\n')
                return payload_file.read_text(), saved['loader'], saved['metadata']
        except (OSError, KeyError, TypeError, ValueError):
            pass
    payload, loader, metadata = _build_package(inputs, qt, work, cxx, modules, command, linker,
                                               dependency_file if has_dependencies else None, libraries)
    if has_dependencies:
        paths = _link_dependencies(dependency_file)
        paths += [str(obj), str(work / 'native.exports')]
        dependencies = {str(Path(path).absolute()): _dependency(path) for path in paths}
        payload_file.write_text(payload)
        stamp.write_text(json.dumps(dict(key=key, native=_digest(native), payload=_digest(payload_file),
            dependencies=dependencies, loader=loader, metadata=metadata), indent=2) + '\n')
    (work / 'native-package-resources.json').write_text(json.dumps(dict(
        cache_hit=False, elapsed_seconds=time.monotonic() - started, dependency_tracking=has_dependencies,
        linker=linker['identity']), indent=2) + '\n')
    return payload, loader, metadata


def _build_package(inputs, qt, work, cxx, modules, command, linker, dependency_file, libraries):
    exports = work / 'native.exports'
    exports.write_text('{ global: ' + ' '.join(name + ';' for name in EXPORTS) + ' local: *; };\n')
    native = work / 'native.so'
    # Safe folding merges only functions whose address is never taken, so
    # deleter and callback identities stay distinct; section GC drops inline
    # functions nothing references. Exports and static constructors are GC
    # roots. Other linkers keep the previous layout.
    folding = ['-Wl,--icf=safe,--gc-sections'] if 'LLD' in linker['identity']['version'] else []
    result = command([cxx, *toolchain_flags(), *linker['flags'], '-shared', *inputs, '-o', native, '-L' + str(qt / 'lib'),
        *folding,
        *(['-Wl,--dependency-file=' + str(dependency_file)] if dependency_file else []),
        '-Wl,--as-needed,-z,defs,-z,now,-z,relro,-z,noexecstack',
        '-Wl,--version-script=' + str(exports),
        *[qt / 'lib' / name for name in libraries]])
    (work / 'native-link.log').write_text(result.stdout + result.stderr)
    with tempfile.TemporaryDirectory(prefix='bend-qt-strip-') as directory:
        stripped = Path(directory) / 'native.so'
        command(['llvm-strip-19', '--strip-unneeded', '-o', stripped, native])
        native.write_bytes(stripped.read_bytes())
    dynamic = command(['readelf', '-d', native]).stdout
    if re.search(r'\((?:TEXTREL|RPATH|RUNPATH)\)', dynamic):
        raise RuntimeError('Native payload has text relocations or a maintainer library path')
    needed = re.findall(r'\(NEEDED\).*\[(.*?)\]', dynamic)
    allowed = {'libstdc++.so.6', 'libgcc_s.so.1', 'libc.so.6', 'libm.so.6', 'ld-linux-x86-64.so.2'}
    allowed.update(libraries)
    if set(needed) - allowed:
        raise RuntimeError('Unplanned native dependencies: ' + repr(set(needed) - allowed))
    names = {line.split()[-1] for line in command(['nm', '-D', '--defined-only', native]).stdout.splitlines()}
    if names != set(EXPORTS):
        raise RuntimeError('Native payload exports differ from its ABI: ' + repr(names))
    # Relocations are performed by Linux's ELF loader, not by the consumer
    # compiler. Still reject an unrecognized architecture or relocation family.
    metadata = json.loads(command(['llvm-readobj-19', '--elf-output-style=JSON',
        '--relocations', native]).stdout)[0]
    if metadata['FileSummary']['Format'] != 'elf64-x86-64':
        raise RuntimeError('Only Linux x86-64 ELF payloads are supported')
    relocations = sorted({item['Relocation']['Type']['Name']
        for section in metadata['Relocations'] for item in section['Relocs']})
    supported = {'R_X86_64_64', 'R_X86_64_RELATIVE', 'R_X86_64_GLOB_DAT',
        'R_X86_64_JUMP_SLOT', 'R_X86_64_DTPMOD64', 'R_X86_64_DTPOFF64',
        'R_X86_64_TPOFF64', 'R_X86_64_IRELATIVE', 'R_X86_64_NONE'}
    if set(relocations) - supported:
        raise RuntimeError('Unsupported native ELF relocations: ' + repr(set(relocations) - supported))
    raw = native.read_bytes()
    compressed = zlib.compress(raw, level=9)
    encoded = base64.b64encode(compressed).decode('ascii')
    templates = Path(__file__).parent / 'templates'
    # Programs cache the decoded module in a directory named by its content.
    cache_entry = hashlib.sha256(b'bend-qt native module\0' + raw).hexdigest()
    template = (templates / 'embedded_elf.c').read_text()
    template = template.replace('// @CACHE@', (templates / 'native_cache.c').read_text())
    template = template.replace('// @PAYLOAD@', '\n'.join(json.dumps(encoded[i:i+120])
        for i in range(0, len(encoded), 120)))
    template = (template.replace('@COMPRESSED_SIZE@', str(len(compressed))).replace('@ELF_SIZE@', str(len(raw)))
                .replace('@CACHE_ID@', cache_entry))
    return template, '    const char *payload_error = bqt_load_payload();\n    if (payload_error) return payload_error;', {
        'format': 'embedded-zlib-elf64-x86-64', 'elf_bytes': len(raw),
        'compressed_bytes': len(compressed), 'embedded_c_bytes': len(template.encode()),
        'elf_sha256': hashlib.sha256(raw).hexdigest(), 'dependencies': needed,
        'relocations': relocations, 'cache_entry': cache_entry,
        'consumer_cpp_toolchain': False}
