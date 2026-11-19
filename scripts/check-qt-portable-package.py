#!/usr/bin/env python3
"""Check that a generated package names no build-machine directory.

Packages built on different machines must be identical, and must not reveal
where they were built. This checks the path rewriting itself, then searches
every package file for this machine's Qt, workspace and home directories:
the generated text, each decoded native module and each bundled runtime file.
"""
import argparse
import base64
from pathlib import Path
import re
import sys
import tempfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
from portable_paths import portable, require_portable

ARRAY = re.compile(r'static const char (bqt_\w*payload|bqt_bundle_data_(\d+))\[\] =')


def rejected(action, label):
    try:
        action()
    except ValueError:
        return
    raise AssertionError('Accepted ' + label)


def check_rewriting():
    with tempfile.TemporaryDirectory(prefix='bend-portable-') as directory:
        qt = Path(directory) / 'Qt/6.12.0/gcc_64'
        (qt / 'include').mkdir(parents=True)
        link = Path(directory) / 'qt-link'
        link.symlink_to(qt)
        value = {str(qt / 'sbom/qtbase-6.12.0.spdx.json'): 'digest',
                 'evidence': [str(qt / 'include/QtCore/qobject.h'), str(link / 'include/QtGui/qimage.h')],
                 'detail': 'declared in ' + str(ROOT / 'build/qt612/headers.h') + ':4',
                 'root': str(ROOT), 'qt': str(qt), 'count': 3}
        assert portable(value, link) == {'<QT>/sbom/qtbase-6.12.0.spdx.json': 'digest',
            'evidence': ['<QT>/include/QtCore/qobject.h', '<QT>/include/QtGui/qimage.h'],
            'detail': 'declared in build/qt612/headers.h:4', 'root': '.', 'qt': '<QT>', 'count': 3}
        rejected(lambda: portable({str(qt / 'a'): 1, '<QT>/a': 2}, qt), 'two paths with one portable name')
        home = Path.home()
        if len(home.parts) > 1 and not qt.is_relative_to(home):
            rejected(lambda: portable({'path': str(home / 'unrelated/file')}, qt), 'a home directory path')
        rejected(lambda: require_portable('see ' + str(qt) + ')', qt, 'text'), 'an unterminated Qt path')


def decode(text, start):
    body = text[start:text.index(';', start)]
    return zlib.decompress(base64.b64decode(''.join(re.findall(r'"([A-Za-z0-9+/=]+)"', body))))


def check_package(package, qt):
    checked = dict(text_files=0, native_modules=0, runtime_blocks=0, runtime_bytes=0)
    blocks = {}
    for path in sorted(package.iterdir()):
        if not path.is_file():
            continue
        text = path.read_text()
        require_portable(text, qt, path.name)
        checked['text_files'] += 1
        for match in ARRAY.finditer(text):
            if match[2] is None:
                require_portable(decode(text, match.end()).decode('latin-1'), qt, path.name + ' native module')
                checked['native_modules'] += 1
            else:
                blocks[int(match[2])] = (path, match.end())
    # Bundled files are stored as consecutive blocks. Search them in order,
    # keeping a tail, so a path split between two blocks is still found.
    tail, current, text = '', None, ''
    for number in sorted(blocks):
        source, start = blocks[number]
        if source != current:
            current, text = source, source.read_text()
        data = decode(text, start).decode('latin-1')
        require_portable(tail + data, qt, 'bundled runtime block %d' % number)
        tail = data[-4096:]
        checked['runtime_blocks'] += 1
        checked['runtime_bytes'] += len(data)
    if not checked['native_modules']:
        raise AssertionError('The package has no native module to check')
    return checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, default=ROOT / 'packages/qt612')
    parser.add_argument('--qt-root', type=Path, default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    args = parser.parse_args()
    check_rewriting()
    checked = check_package(args.package, args.qt_root)
    print('PASS portable package: no build-machine directory in %(text_files)d files, '
          '%(native_modules)d native modules or %(runtime_blocks)d runtime blocks '
          '(%(runtime_bytes)d bytes)' % checked)


if __name__ == '__main__':
    main()
