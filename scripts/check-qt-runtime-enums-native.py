#!/usr/bin/env python3
"""Verify QML enum lookup against an ordinary moc-generated Qt class."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qt-root', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    qt, work = args.qt_root.resolve(), args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'examples/qt612/runtime-enums-native.cpp'
    subprocess.run([qt / 'libexec/moc', source, '-o', work / 'runtime-enums-native.moc'], check=True)
    executable = work / 'runtime-enums-native'
    subprocess.run(['clang++-19', '-std=c++17', '-fPIC', '-I' + str(work),
                    '-I' + str(qt / 'include'), '-I' + str(qt / 'include/QtCore'),
                    '-I' + str(qt / 'include/QtQml'), source, '-L' + str(qt / 'lib'),
                    '-Wl,-rpath,' + str(qt / 'lib'), '-lQt6Qml', '-lQt6Core', '-o', executable], check=True)
    result = subprocess.run([executable], text=True, capture_output=True, check=True,
                            env=dict(os.environ, LD_LIBRARY_PATH=str(qt / 'lib'), QML_IMPORT_PATH=str(qt / 'qml')))
    if result.stdout.strip() != 'native=4294967297 qml=1':
        raise RuntimeError('Unexpected Qt enum control: ' + result.stdout + result.stderr)
    receipt = dict(verification_complete=True, native_enum=4294967297, qml_lookup=1,
                   source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    (work / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('PASS native Qt enum control: 64-bit metadata preserved; QML constant lookup uses 32 bits')


if __name__ == '__main__':
    main()
