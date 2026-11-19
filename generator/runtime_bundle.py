"""Embed runtime files through ordinary Bend foreign C imports.

The binary data is split into separately imported C files. A FID reference
keeps each import reachable without adding an IO step to every Qt operation.
No consumer compiler flags, download, SDK or external extraction tool is used.
License selection and source delivery are checked before calling this packer.
"""
import base64
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
import zlib


HERE = Path(__file__).resolve().parent


def relative_path(value):
    path = PurePosixPath(value)
    if (not value or path.is_absolute() or '..' in path.parts or '\\' in value
            or '\x00' in value or path.as_posix() != value or value == '.'):
        raise ValueError('Invalid bundled runtime path: ' + repr(value))
    return value


def embed(files, *, aliases=None, context=None, block_size=512 * 1024,
          piece_size=4 * 1024 * 1024, owners=None, base_module='base'):
    """Return generated loader C, internal Bend defs and C assets.

    `files` maps normalized installation-relative paths to source paths.
    Aliases become hard links inside the private extracted runtime.
    The cache identity includes every file byte, mode, alias and build context.
    """
    if block_size <= 0 or piece_size <= 0:
        raise ValueError('Runtime bundle block sizes must be positive')
    selective = owners is not None
    owners = ({name: tuple(sorted(set(value))) for name, value in owners.items()}
              if selective else {name: (base_module,) for name in files})
    if set(owners) != set(files) or any(not value for value in owners.values()):
        raise ValueError('Every runtime file needs an owning module')
    modules = sorted({module for values in owners.values() for module in values})
    if (base_module not in modules or len(modules) > 128
            or any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', module) for module in modules)):
        raise ValueError('Invalid runtime module inventory')
    module_ids = {name: i for i, name in enumerate(modules)}
    aliases = dict(sorted((relative_path(k), relative_path(v))
                          for k, v in (aliases or {}).items()))
    rows, blocks = [], []
    for name, source in sorted(files.items()):
        relative_path(name)
        source = Path(source)
        if not source.is_file():
            raise ValueError('Missing runtime input: ' + str(source))
        raw = source.read_bytes()
        # Libraries and helper processes are ELF files; everything else is
        # data. The source file's mode depends on the build machine's
        # filesystem, such as a Windows drive mounted with every bit set.
        row = dict(path=name, size=len(raw), mode=0o700 if raw[:4] == b'\x7fELF' else 0o600,
                   sha256=hashlib.sha256(raw).hexdigest(), first=len(blocks), count=0)
        if selective:
            row['modules'] = owners[name]
        for offset in range(0, len(raw), block_size):
            plain = raw[offset:offset + block_size]
            packed = zlib.compress(plain, 9)
            blocks.append(dict(plain=len(plain), packed=len(packed),
                               data=base64.b64encode(packed).decode('ascii'), modules=owners[name]))
            row['count'] += 1
        rows.append(row)
    if not rows:
        raise ValueError('A runtime bundle must contain files')
    names = {r['path'] for r in rows}
    for alias, target in aliases.items():
        if alias in names or target not in names:
            raise ValueError('A runtime alias needs a distinct real file: ' + alias)
    all_names = names | aliases.keys()
    if any(any(str(parent) in all_names for parent in PurePosixPath(name).parents) for name in all_names):
        raise ValueError('A bundled file is also a directory')
    manifest = dict(schema=1, files=rows, aliases=aliases, context=context or {})
    if selective:
        manifest.update(modules=modules, base_module=base_module)
    identity = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    declarations = (HERE / 'templates/runtime_bundle_types.h').read_text()
    pieces, current, size = [], [], 0
    for i, block in sorted(enumerate(blocks), key=lambda item: (item[1]['modules'], item[0])):
        if current and (size + len(block['data']) > piece_size or current[0][1]['modules'] != block['modules']):
            pieces.append(current); current, size = [], 0
        current.append((i, block)); size += len(block['data'])
    if current:
        pieces.append(current)
    assets, bend, references = {}, [], []
    module_references = {name: [] for name in modules}
    for index, group in enumerate(pieces):
        effect = f'native_Runtime_piece_{index}'
        filename = f'qt-runtime-{index:04d}.c'
        lines = [declarations]
        for i, block in group:
            lines += [f'static const char bqt_bundle_data_{i}[] =',
                      *[json.dumps(block['data'][j:j + 120]) for j in range(0, len(block['data']), 120)], ';',
                      f'static const BqtBundleBlock bqt_bundle_block_{i} = '
                      + '{' + f'{block["plain"]}, {block["packed"]}, bqt_bundle_data_{i}' + '};']
        lines += [f'static Term bqt_bundle_piece_{index}_run(Env e, Term *f, IoWork *w) '
                  + '{ return term_pak(CID(Unit), 0); }',
                  f'static void __attribute__((constructor)) bqt_bundle_piece_{index}_register(void) {{',
                  *[f'    bqt_bundle_add({i}, &bqt_bundle_block_{i});' for i, _ in group],
                  f'    io_eff(CID({effect}), bqt_bundle_piece_{index}_run);', '}']
        assets[filename] = '\n'.join(lines) + '\n'
        bend += [f'def {effect}() -> IO(Unit):', f'  import "./{filename}"', '']
        reference = f'    (void)FID({effect});'
        references.append(reference)
        for module in group[0][1]['modules']:
            module_references[module].append(reference)
    if selective:
        for module in modules:
            effect = 'native_Runtime_assets_' + module
            filename = 'qt-runtime-module-' + module + '.c'
            assets[filename] = declarations + '\n' + '\n'.join([
                f'static Term bqt_bundle_module_{module}_run(Env e, Term *f, IoWork *w) '
                + '{ return term_pak(CID(Unit), 0); }',
                f'static void __attribute__((constructor)) bqt_bundle_module_{module}_register(void) {{',
                '    (void)FID(native_Runtime_bundleHost);',
                *module_references[module], f'    bqt_bundle_enable({module_ids[module]});',
                f'    io_eff(CID({effect}), bqt_bundle_module_{module}_run);', '}', ''])
            bend += [f'def {effect}() -> IO(Unit):', f'  import "./{filename}"', '']
        references = [f'    (void)FID(native_Runtime_assets_{base_module});']
    bend += ['def native_Runtime_bundleHost() -> IO(Unit):', '  import "./qt.c"', '']
    # An empty input file needs no compressed blocks, and still gets extracted.
    def mask(names):
        words = [sum(1 << (module_ids[name] % 64) for name in names if module_ids[name] // 64 == word)
                 for word in range(2)]
        return '{' + ', '.join('UINT64_C(' + str(word) + ')' for word in words) + '}'
    file_table = '\n'.join('    {' + ', '.join((json.dumps(r['path']), str(r['size']),
        str(r['mode']), json.dumps(r['sha256']), str(r['first']), str(r['count']), mask(owners[r['path']]))) + '},' for r in rows)
    indices = {r['path']: i for i, r in enumerate(rows)}
    alias_table = '\n'.join('    {' + json.dumps(alias) + ', ' + str(indices[target]) + '},'
                            for alias, target in aliases.items()) or '    {NULL, 0},'
    loader = (HERE / 'templates/runtime_bundle.c').read_text()
    for key, value in dict(TYPES=declarations, CACHE=(HERE / 'templates/native_cache.c').read_text(),
                           ID=identity, FILES=file_table, ALIASES=alias_table,
                           FILE_COUNT=str(len(rows)), ALIAS_COUNT=str(len(aliases)),
                           BLOCK_COUNT=str(len(blocks)), REFERENCES='\n'.join(references),
                           MODULE_COUNT=str(len(modules)), MODULE_NAMES=', '.join(map(json.dumps, modules)),
                           ACTIVE_MODULES='{0, 0}' if selective else mask((base_module,)),
                           SELECTIVE=str(int(selective))).items():
        loader = loader.replace('// @' + key + '@', value).replace('@' + key + '@', value)
    return dict(c=loader, bend='\n'.join(bend), assets=assets,
                module_effects={module: 'native_Runtime_assets_' + module for module in modules} if selective else {},
                manifest=dict(manifest, sha256=identity, pieces=len(pieces),
                              compressed_bytes=sum(b['packed'] for b in blocks)))
