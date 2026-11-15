"""Select a maintainer linker without changing C++ compilation flags."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def select(cxx):
    mode = os.environ.get('BQT_LINKER', 'auto')
    if mode not in ('auto', 'lld', 'system') and not Path(mode).is_absolute():
        raise ValueError('BQT_LINKER must be auto, lld, system or an absolute linker path')
    cache = Path(os.environ.get('BEND_QT_GENERATOR_CACHE', Path.home()/'.cache/bend-qt-generator'))
    flags = []
    path = None
    if mode != 'system':
        candidates = ([mode] if Path(mode).is_absolute() else
                      [shutil.which('ld.lld-19'), cache/'tools/lld-19/usr/bin/ld.lld-19', shutil.which('ld.lld')])
        # LLD is a multicall binary: preserve ld.lld's argv[0] symlink name.
        path = next((Path(value).absolute() for value in candidates if value and Path(value).is_file()
                     and os.access(value, os.X_OK)), None)
        if path is None and mode != 'auto':
            raise RuntimeError('Requested linker is unavailable; run bash scripts/setup-qt-linker.sh')
        if path is not None:
            flags = ['--ld-path=' + str(path)]
    if path is None:
        named = subprocess.run([cxx, '-print-prog-name=ld'], text=True, capture_output=True, check=True).stdout.strip()
        found = named if Path(named).is_absolute() else shutil.which(named)
        if not found:
            raise RuntimeError('Compiler default linker is unavailable: ' + named)
        path = Path(found).absolute()
    version = subprocess.run([str(path), '--version'], text=True, capture_output=True, check=True)
    return dict(flags=flags, identity=dict(path=str(path),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        version=version.stdout.strip(), flags=flags))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cxx', default='clang++-19')
    print(json.dumps(select(parser.parse_args().cxx), indent=2))
