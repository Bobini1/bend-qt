#!/usr/bin/env python3
"""Validate the actual native locker helper without the full package backend."""
from pathlib import Path
from types import SimpleNamespace
import argparse
import hashlib
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
import mutex_lockers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=ROOT / 'build/qt612/mutex-lockers-native')
    parser.add_argument('--qt-root', type=Path, default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--cursor-guards', action='store_true')
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'examples/qt612' / ('cursor-guards-native.cpp' if args.cursor_guards else 'mutex-lockers-native.cpp')
    runtime = ROOT / 'generator/templates/mutex_lockers.cpp'
    generated = mutex_lockers.cpp(SimpleNamespace(ids={'QMutex': 1, 'QRecursiveMutex': 2},
        mutex_locker_slot=1, mutex_locker_operations={'test': 1}))
    (args.work / 'mutex-lockers-runtime.h').write_text(generated)
    if args.cursor_guards:
        cursor_runtime = ROOT / 'generator/templates/cursor_guards.cpp'
        (args.work / 'cursor-guards-runtime.h').write_text(cursor_runtime.read_text().replace('@QCursor@', '3'))
    executable = args.work / 'native'
    flags = ['g++' if args.sanitize else 'clang++-19', '-std=c++17', '-pthread',
        f'-I{args.work.resolve()}', f'-I{args.qt_root}/include', f'-I{args.qt_root}/include/QtCore']
    if args.sanitize: flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    if args.cursor_guards: flags += [f'-I{args.qt_root}/include/QtGui']
    built = subprocess.run([*flags, str(source), f'-L{args.qt_root}/lib',
        f'-Wl,-rpath,{args.qt_root}/lib', *(['-lQt6Gui'] if args.cursor_guards else []),
        '-lQt6Core', '-o', str(executable)], text=True, capture_output=True)
    (args.work / 'compile.log').write_text(built.stdout + built.stderr)
    built.check_returncode()
    checked = subprocess.run([str(executable)], env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0', QT_QPA_PLATFORM='offscreen'),
        text=True, capture_output=True)
    (args.work / 'native.log').write_text(checked.stdout + checked.stderr)
    checked.check_returncode()
    assert ('CURSOR_GUARDS_NATIVE_OK' if args.cursor_guards else 'MUTEX_LOCKERS_NATIVE_OK') in checked.stdout
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    receipt = dict(verification_complete=True,
        boundary='Native helper and registry contract; complete Bend effect/scopes require integration tests',
        native_real_mutexes=not args.cursor_guards, native_gui_cursor_stack=args.cursor_guards,
        sanitizers=args.sanitize, helper_sha256=digest(runtime),
        generator_sha256=digest(ROOT / 'generator/mutex_lockers.py'), fixture_sha256=digest(source))
    if args.cursor_guards: receipt.update(cursor_guard_sha256=digest(cursor_runtime),
        registry_fixture_sha256=digest(ROOT / 'examples/qt612/mutex-lockers-native.cpp'))
    (args.work / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(checked.stdout, end='')


if __name__ == '__main__':
    main()
