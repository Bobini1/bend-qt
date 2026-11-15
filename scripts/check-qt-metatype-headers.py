#!/usr/bin/env python3
"""Check hidden metatype helpers against the installed baseline libraries."""
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
from adapters import native_header_support


def main():
    qt = Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64'
    work = ROOT / 'build/metatype-header-check'
    work.mkdir(parents=True, exist_ok=True)
    source = work / 'check.cpp'
    prefix = '#include <QtRemoteObjects/qtremoteobjectglobal.h>\n#include <QtCore/QVariant>\n'
    body = '''
extern "C" __attribute__((visibility("default"))) int check() {
    QIntHash original{{1, QByteArray("one")}, {2, QByteArray("two")}};
    QVariant value = QVariant::fromValue(original);
    auto copy = value.value<QIntHash>();
    return copy == original && value.metaType() == QMetaType::fromType<QIntHash>();
}
'''
    source.write_text(prefix + native_header_support(['QtRemoteObjects']) + body)
    library = work / 'check.so'
    flags = ['clang++-19', '-std=c++17', '-O1', '-fPIC', '-fvisibility=hidden', '-shared',
             '-I' + str(qt / 'include'), '-L' + str(qt / 'lib'), '-lQt6RemoteObjects', '-lQt6Core']
    subprocess.run([*flags, source, '-o', library], check=True)
    imports = subprocess.run(['llvm-nm-19', '-u', library], check=True, capture_output=True, text=True).stdout
    assert 'qRegisterNormalizedMetaType_QIntHash' not in imports
    tested = subprocess.run([sys.executable, '-c', 'import ctypes,sys; assert ctypes.CDLL(sys.argv[1]).check() == 1', str(library)],
        env=dict(os.environ, LD_LIBRARY_PATH=str(qt / 'lib')), capture_output=True, text=True, check=True)
    # The unadapted Qt header really does leave the helper undefined.
    source.write_text(prefix + body)
    negative = work / 'unadapted.so'
    subprocess.run([*flags, source, '-o', negative], check=True)
    missing = subprocess.run(['llvm-nm-19', '-u', negative], check=True, capture_output=True, text=True).stdout
    assert 'qRegisterNormalizedMetaType_QIntHash' in missing
    (work / 'receipt.json').write_text(json.dumps(dict(passed=True, map_roundtrip=True,
        no_private_import=True, unadapted_header_negative=True), indent=2) + '\n')
    print('QT612_METATYPE_HEADERS_OK map_roundtrip=1 private_import=0 negative=1')


if __name__ == '__main__':
    main()
