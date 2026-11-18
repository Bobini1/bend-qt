#!/usr/bin/env python3
"""Exercise the embedded file loader through stock Bend native compilation."""
import argparse
import fcntl
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
from runtime_bundle import embed


def run(command, **kw):
    result = subprocess.run([str(x) for x in command], text=True, capture_output=True, **kw)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=ROOT / 'build/runtime-bundle-check')
    parser.add_argument('--native-work', type=Path,
                        default=Path.home() / '.cache/bend-qt-generator/runtime-bundle-check')
    parser.add_argument('--bend', default=str(Path.home() / '.bend/bin/bend'))
    args = parser.parse_args()
    report = args.work.resolve(); report.mkdir(parents=True, exist_ok=True)
    work = args.native_work.resolve(); work.mkdir(parents=True, exist_ok=True)
    source = work / 'source'; source.mkdir(exist_ok=True)
    files = {}
    rng = random.Random(4391)
    for n in (0, 1, 55, 56, 63, 64, 65, 131072, 600001):
        path = source / f'file-{n}'
        path.write_bytes(rng.randbytes(n)); path.chmod(0o700 if n == 65 else 0o600)
        files[f'lib/nested/file-{n}'] = path
    files['NOTICE'] = source / 'notice'
    files['NOTICE'].write_text('Qt test data, not a redistributable Qt runtime.\n')
    aliases = {'lib/alias': 'lib/nested/file-600001'}
    bundle = embed(files, aliases=aliases, block_size=65536, piece_size=131072)
    second = embed(files, aliases=aliases, block_size=65536, piece_size=131072)
    assert bundle == second, 'Non-deterministic bundle'
    for bad in ('../escape', '/absolute', 'a/../b', './x', 'a//b', 'a\\b', 'x\x00y'):
        try:
            embed({bad: files['NOTICE']})
        except ValueError:
            pass
        else:
            raise AssertionError('Accepted invalid path: ' + repr(bad))
    try:
        embed({'a': files['NOTICE'], 'a/b/c': files['NOTICE']})
    except ValueError:
        pass
    else:
        raise AssertionError('A bundled file can shadow an ancestor directory')
    c = bundle['c'] + '''
static Term bundle_test_run(Env e, Term *f, IoWork *w) {
    const char *error = bqt_bundle_materialize();
    return error ? io_fail(e, EIO, error) : io_done(e, io_str(e, bqt_bundle_root, strlen(bqt_bundle_root)));
}
static void __attribute__((constructor)) bundle_test_register(void) {
    io_eff(CID(bundle_test), bundle_test_run);
}
'''
    library = 'import Base\n' + bundle['bend'] + '''
def bundle_test() -> IO(Result<&1, &1, U32 & String, String>):
  import "./qt.c"
'''
    bend = '''import Base
import ./qt.bend as Qt
def main() -> IO(Unit):
  do IO<Unit>:
    path: String <- IO.try(String, Qt.bundle_test())
    IO.print(path)
'''
    (work / 'main.bend').write_text(bend); (work / 'qt.bend').write_text(library); (work / 'qt.c').write_text(c)
    for name, text in bundle['assets'].items():
        (work / name).write_text(text)
    # The concurrent starts below are first extractions into an empty cache.
    shutil.rmtree(work / 'cache', ignore_errors=True)
    env = dict(os.environ, BEND_NO_TELEMETRY='1', XDG_CACHE_HOME=str(work / 'cache'))
    env.pop('BEND_QT_RUNTIME', None)
    run([args.bend, 'main.bend', '-o', 'app'], cwd=work, env=env)

    def execute():
        return Path(run([work / 'app'], cwd=work, env=env))

    paths = list(ThreadPoolExecutor(max_workers=8).map(lambda _: execute(), range(16)))
    assert len(set(paths)) == 1
    path = paths[0]
    assert path.name == bundle['manifest']['sha256']

    def verify():
        for name, original in files.items():
            current = path / name
            assert current.read_bytes() == original.read_bytes(), name
            assert current.stat().st_mode & 0o777 == (0o700 if original.stat().st_mode & 0o111 else 0o600)
        assert (path / 'lib/alias').stat().st_ino == (path / aliases['lib/alias']).stat().st_ino

    verify()
    # A verified directory is stamped; a later start trusts unchanged stats and
    # neither hashes nor rewrites anything.
    stamp = path / '.ready'
    assert stamp.read_text().strip() and (path / '.use').stat().st_size
    before = stamp.stat()
    assert execute() == path
    assert stamp.stat().st_ino == before.st_ino and stamp.stat().st_mtime_ns == before.st_mtime_ns
    # Collection removes runtime directories unused for a week and leftovers
    # from an interrupted collection; it keeps recent, held and foreign ones.
    cache = path.parent
    week = 8 * 24 * 3600
    def runtime(name, age, use=True):
        directory = cache / name; directory.mkdir(mode=0o700)
        (directory / 'lib').mkdir(); (directory / 'lib/file').write_bytes(b'x')
        if use:
            (directory / '.use').write_text('\n')
            os.utime(directory / '.use', (time.time() - age,) * 2)
        os.utime(directory, (time.time() - age,) * 2)
        return directory
    unused, held, recent = runtime('a' * 64, week), runtime('b' * 64, week), runtime('c' * 64, 3600)
    unstamped = runtime('d' * 64, week, use=False)
    foreign = cache / 'kept-by-someone-else'; foreign.mkdir()
    trash = cache / ('.trash-' + 'e' * 20 + '-1'); (trash / 'deep/er').mkdir(parents=True); (trash / 'deep/er/f').write_bytes(b'x')
    (cache / '.collected').unlink(missing_ok=True)
    with open(held / '.use') as holder:
        fcntl.flock(holder, fcntl.LOCK_SH)
        assert execute() == path
    assert not unused.exists() and not unstamped.exists() and not trash.exists()
    assert held.exists() and recent.exists() and foreign.exists() and path.exists()
    assert not [p for p in cache.iterdir() if p.name.startswith('.trash-')]
    # Collection runs at most once a day.
    stale = runtime('f' * 64, week)
    assert execute() == path and stale.exists()
    os.utime(cache / '.collected', (time.time() - 2 * 24 * 3600,) * 2)
    # The released directory is now as unused as any other.
    assert execute() == path and not stale.exists() and not held.exists() and recent.exists()
    shutil.rmtree(recent); foreign.rmdir()
    # Cached data is verified, including same-sized changes and mode changes.
    (path / 'lib/nested/file-131072').write_bytes(b'x' * 131072)
    (path / 'lib/nested/file-65').chmod(0o600)
    (path / 'lib/alias').unlink()
    (path / 'lib/alias').symlink_to('/etc/passwd')
    assert execute() == path; verify()
    assert stamp.stat().st_ino != before.st_ino, 'A repaired directory kept its old stamp'
    (path / 'NOTICE').unlink()
    (path / 'NOTICE').symlink_to('/etc/passwd')
    assert execute() == path; verify()
    # A hostile directory link is rejected without traversing it.
    outside = work / 'outside'; outside.mkdir(exist_ok=True)
    nested = path / 'lib/nested'; moved = path / 'lib/saved'
    nested.rename(moved); nested.symlink_to(outside, target_is_directory=True)
    rejected = subprocess.run([str(work / 'app')], env=env, text=True, capture_output=True)
    assert rejected.returncode and 'file directory' in rejected.stderr + rejected.stdout
    assert not list(outside.iterdir())
    nested.unlink(); moved.rename(nested); assert execute() == path
    override = work / 'replacement'; override.mkdir(exist_ok=True)
    assert Path(run([work / 'app'], env=dict(env, BEND_QT_RUNTIME=str(override)))) == override
    # A fresh Hub-format consumer must fetch every C asset through the standard
    # compiler. No local package paths, extraction command or SDK are available.
    spec = importlib.util.spec_from_file_location('qt_package_check', ROOT / 'scripts/check-qt612.py')
    checker = importlib.util.module_from_spec(spec); spec.loader.exec_module(checker)
    consumer = '''import Base
import ../../packages/qt612/qt.bend as Qt
def main() -> IO(Unit):
  do IO<Unit>:
    path: String <- IO.try(String, Qt.bundle_test())
    IO.print("QT_RUNTIME_BUNDLE_HUB_OK")
'''
    hub = checker.check_package(work, [('runtime-assets', consumer, 'QT_RUNTIME_BUNDLE_HUB_OK')],
                                env, [Path('/usr')], report / 'hub')
    fetched = {Path(p).name for p in hub['fetches']}
    assert set(bundle['assets']) <= fetched, 'Hub consumer omitted runtime C assets'
    receipt = dict(passed=True, verification_complete=True, manifest=bundle['manifest'], native_work=str(work),
        foreign_c_pieces=len(bundle['assets']), ordinary_bend_compile=True, fid_import_retention=True,
        concurrent_extraction=16, cache_hashes=True, stale_cache_repaired=True,
        symlink_parent_rejected=True, explicit_runtime_override=True, fresh_hub=hub,
        boundary='Embedded file transport and extraction; full Qt dependency selection, notices, runtime preloading and package integration are separate checks')
    (report / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('QT_RUNTIME_BUNDLE_OK stock_bend=1 concurrent=16 stat_stamp=1 hash_repair=1 collection=1 symlink_guard=1')


if __name__ == '__main__':
    main()
