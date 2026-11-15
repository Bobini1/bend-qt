#!/usr/bin/env python3
"""Run the production dynamic-property adapter against real Qt metadata."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=ROOT / 'build/qt612/dynamic-properties-native')
    parser.add_argument('--qt-root', type=Path, default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    parser.add_argument('--sanitize', action='store_true')
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    helper = ROOT / 'generator/templates/dynamic_properties.cpp'
    fixture = ROOT / 'examples/qt612/dynamic-properties-native.cpp'
    (args.work / 'dynamic-properties-runtime.h').write_text(helper.read_text().replace('@QVARIANT_ID@', '1'))
    executable = args.work / 'native'
    flags = ['g++' if args.sanitize else 'clang++-19', '-std=c++17', '-pthread',
             f'-I{args.work.resolve()}', f'-I{args.qt_root}/include',
             f'-I{args.qt_root}/include/QtCore', f'-I{args.qt_root}/include/QtQml']
    if args.sanitize:
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    compiled = subprocess.run([*flags, str(fixture), f'-L{args.qt_root}/lib',
        f'-Wl,-rpath,{args.qt_root}/lib', '-lQt6Qml', '-lQt6Core', '-o', str(executable)],
        text=True, capture_output=True)
    (args.work / 'compile.log').write_text(compiled.stdout + compiled.stderr)
    compiled.check_returncode()
    checked = subprocess.run([str(executable)], text=True, capture_output=True,
        env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0'))
    (args.work / 'native.log').write_text(checked.stdout + checked.stderr)
    checked.check_returncode()
    assert 'DYNAMIC_PROPERTIES_NATIVE_OK' in checked.stdout
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    receipt = dict(verification_complete=True, sanitizers=args.sanitize,
        boundary='Production dynamic-property adapter, real Qt objects/metadata and minimal origin registry; complete generic codecs/Bend ABI require the consumer fixture',
        helper_sha256=digest(helper), fixture_sha256=digest(fixture),
        metadata_lifetime=True, native_raw_mutations=True, outgoing_snapshots=True,
        borrowed_qobjects=True, reentrant_events=True, preflight_failure=True,
        repeated_removal_cleanup=True)
    (args.work / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(checked.stdout, end='')


if __name__ == '__main__':
    main()
