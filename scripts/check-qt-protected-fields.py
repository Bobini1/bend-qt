#!/usr/bin/env python3
"""Check generated protected-field access against actual foreign Qt objects.

Maintainer-only C++ validation. Consumers use the ordinary generated package.
"""
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
import protected_fields
from native_objects import saved_traits


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-work', type=Path, default=ROOT / 'build/qt612')
    parser.add_argument('--work', type=Path, default=ROOT / 'build/qt612/protected-fields')
    parser.add_argument('--qt-root', type=Path, default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    parser.add_argument('--sanitize', action='store_true')
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    api_path = args.source_work / 'api.json'
    api = json.loads(api_path.read_text())
    classes = {c['name']: c for c in api['classes']}
    try:
        traits = saved_traits(args.source_work)
    except FileNotFoundError:
        traits = {}
    for name, flags in traits.items():
        if name in classes: classes[name].update(flags)
    # Test cases, not a production class allowlist. These include every pinned
    # bitfield owner and representative addressable/member-view contracts.
    selected = ['QPaintDevice', 'QPaintEngine', 'QPaintEngineState', 'QLayoutItem',
                'QWidgetItem', 'QSGOpaqueTextureMaterial', 'QStringConverter']

    def inherited(name):
        methods = {}
        for base in classes[name]['bases']:
            if base in classes:
                for f in inherited(base): methods[f['minimal_signature']] = f
        for f in classes[name]['functions']: methods[f['minimal_signature']] = f
        return list(methods.values())

    generator = SimpleNamespace(classes=classes, selected=selected,
        ids={name: i + 1 for i, name in enumerate(classes)}, inherited=inherited)
    source = protected_fields.declarations(generator, include_views=False)
    (args.work / 'protected-fields-helpers.h').write_text(source)
    native = ROOT / 'examples/qt612/protected-fields-native.cpp'
    executable = args.work / 'native'
    flags = ['g++' if args.sanitize else 'clang++-19', '-std=c++17', f'-I{args.qt_root}/include',
             f'-I{args.work.resolve()}', *[f'-I{args.qt_root}/include/{module}'
                 for module in ('QtCore', 'QtGui', 'QtWidgets', 'QtQml', 'QtQuick')]]
    if args.sanitize: flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    compiled = subprocess.run([*flags, str(native), f'-L{args.qt_root}/lib', f'-Wl,-rpath,{args.qt_root}/lib',
        '-lQt6Quick', '-lQt6Widgets', '-lQt6Gui', '-lQt6Core', '-o', str(executable)], text=True, capture_output=True)
    (args.work / 'compile.log').write_text(compiled.stdout + compiled.stderr)
    compiled.check_returncode()
    checked = subprocess.run([str(executable)], env=dict(os.environ, QT_QPA_PLATFORM='offscreen',
        ASAN_OPTIONS='detect_leaks=0'), text=True, capture_output=True)
    (args.work / 'native.log').write_text(checked.stdout + checked.stderr)
    checked.check_returncode()
    if 'PROTECTED_FIELDS_NATIVE_OK' not in checked.stdout:
        raise RuntimeError('Native protected field validation did not finish')
    # The alias guard must validate replaced ancestor storage before reading a
    # descendant's current getter. ASan catches the old parent-first UAF.
    views = ROOT / 'generator/templates/protected_field_views.cpp'
    (args.work / 'protected-field-views.h').write_text(views.read_text())
    aliases = ROOT / 'examples/qt612/native-aliases-native.cpp'
    alias_executable = args.work / 'aliases-native'
    alias_compile = subprocess.run([*flags, str(aliases), f'-L{args.qt_root}/lib', f'-Wl,-rpath,{args.qt_root}/lib',
        '-lQt6Core', '-o', str(alias_executable)], text=True, capture_output=True)
    (args.work / 'aliases-compile.log').write_text(alias_compile.stdout + alias_compile.stderr)
    alias_compile.check_returncode()
    alias_check = subprocess.run([str(alias_executable)], env=dict(os.environ,
        ASAN_OPTIONS='detect_leaks=0'), text=True, capture_output=True)
    (args.work / 'aliases-native.log').write_text(alias_check.stdout + alias_check.stderr)
    alias_check.check_returncode()
    if 'NATIVE_ALIASES_OK' not in alias_check.stdout:
        raise RuntimeError('Native alias validation did not finish')
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    receipt = dict(verification_complete=True, native_foreign_objects=True, bitfields=9,
        addressable_fields=True, borrowed_member_state=True, sanitizers=args.sanitize,
        api_sha256=digest(api_path), generator_sha256=digest(ROOT / 'generator/protected_fields.py'),
        template_sha256=digest(ROOT / 'generator/templates/protected_fields.cpp'),
        fixture_sha256=digest(native))
    receipt.update(nested_native_aliases=True, retained_native_consumer_barrier=True,
        alias_guard_sha256=digest(views), alias_fixture_sha256=digest(aliases))
    (args.work / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(checked.stdout, end='', flush=True)
    print(alias_check.stdout, end='', flush=True)


if __name__ == '__main__':
    main()
