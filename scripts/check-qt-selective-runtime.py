#!/usr/bin/env python3
"""Verify module-owned runtime assets are retained by ordinary Bend reachability."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
from runtime_bundle import embed


def run(command, work, env):
    result = subprocess.run([str(item) for item in command], cwd=work, env=env,
                            capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=ROOT / 'build/selective-runtime-check')
    parser.add_argument('--native-work', type=Path,
                        default=Path.home() / '.cache/bend-qt-generator/selective-runtime-check')
    args = parser.parse_args()
    report = args.work.resolve(); report.mkdir(parents=True, exist_ok=True)
    work = args.native_work.resolve(); work.mkdir(parents=True, exist_ok=True)
    (report / 'receipt.json').write_text('{"verification_complete":false}\n')
    files, owners = {}, {}
    for name, modules in [('base', ['base']), ('shared', ['base', 'Graphs']), ('graphs', ['Graphs']),
                          ('charts', ['Charts']), ('shared-optional', ['Graphs', 'Charts'])]:
        source = work / (name + '.source')
        source.write_bytes(hashlib.shake_256(name.encode()).digest(65537))
        files['lib/' + name] = source; owners['lib/' + name] = modules
    bundle = embed(files, aliases={'lib/graph-alias': 'lib/graphs'}, owners=owners,
                   block_size=16384, piece_size=32768)
    assert bundle == embed(files, aliases={'lib/graph-alias': 'lib/graphs'}, owners=owners,
                           block_size=16384, piece_size=32768)
    (work / 'qt.c').write_text(bundle['c'] + '''
static Term bqt_selective_test_run(Env e, Term *f, IoWork *w) {
    const char *error=bqt_bundle_materialize();
    return error?io_fail(e,EIO,error):io_done(e,io_str(e,bqt_bundle_root,strlen(bqt_bundle_root)));
}
static void __attribute__((constructor)) bqt_selective_test_register(void) {
    io_eff(CID(prepare),bqt_selective_test_run);
}
''')
    library = 'import Base\n' + bundle['bend'] + '''
def prepare() -> IO(Result<&1, &1, U32 & String, String>):
  import "./qt.c"
'''
    (work / 'qt.bend').write_text(library)
    for name, source in bundle['assets'].items():
        (work / name).write_text(source)
    env = dict(os.environ, BEND_NO_TELEMETRY='1', XDG_CACHE_HOME=str(work / 'cache'))
    env.pop('BEND_QT_RUNTIME', None)
    runs = []
    for label, modules in [('core', []), ('graphs', ['Graphs']), ('both', ['Charts', 'Graphs'])]:
        source = 'import Base\nimport ./qt.bend as Qt\ndef main() -> IO(Unit):\n  do IO<Unit>:\n'
        source += ''.join('    Qt.' + bundle['module_effects'][module] + '()\n' for module in modules)
        source += '    path: String <- IO.try(String, Qt.prepare())\n    IO.print(path)\n'
        (work / 'main.bend').write_text(source)
        run([Path.home() / '.bend/bin/bend', 'main.bend', '-o', label], work, env)
        runtime = Path(run([work / label], work, env))
        selected = {'base', *modules}
        expected = {name for name, modules in owners.items() if selected.intersection(modules)}
        actual = {path.relative_to(runtime).as_posix() for path in runtime.rglob('*') if path.is_file()}
        assert actual == expected | {'.lock'} | ({'lib/graph-alias'} if 'Graphs' in selected else set()), actual
        for name in expected:
            assert (runtime / name).read_bytes() == files[name].read_bytes()
        executable = (work / label).read_bytes()
        retained = []
        for asset, text in bundle['assets'].items():
            if asset.startswith('qt-runtime-module-'):
                continue
            # Use each first compressed block, which remains a contiguous
            # C string even when the piece contains multiple blocks.
            first = text.partition('static const char ')[2].partition(';')[0]
            first = ''.join(re.findall(r'"([A-Za-z0-9+/=]+)"', first)).encode()
            present = first in executable
            effect = 'native_Runtime_piece_' + str(int(asset.removeprefix('qt-runtime-').removesuffix('.c')))
            needed = any('FID(' + effect + ')' in bundle['assets']['qt-runtime-module-' + module + '.c']
                         for module in selected)
            assert present == needed, (label, asset, present, needed)
            if present:
                retained.append(asset)
        runs.append(dict(consumer=label, modules=sorted(selected), runtime=str(runtime),
                         files=sorted(actual), retained_pieces=retained))
    assert len({row['runtime'] for row in runs}) == 3, 'Module selections shared a cache identity'
    (report / 'receipt.json').write_text(json.dumps(dict(verification_complete=True,
        ordinary_bend_compile=True, runs=runs,
        boundary='Exact synthetic runtime asset retention/extraction; real Qt native integration is a separate gate'), indent=2) + '\n')
    print('QT_SELECTIVE_RUNTIME_OK core=1 graphs=1 both=1 exact_retention=1')


if __name__ == '__main__':
    main()
