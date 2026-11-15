#!/usr/bin/env python3
"""Type-check custom signal declarations and reject incompatible handlers/emissions."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BEND = Path.home() / '.bend/bin/bend'


def check(package, output, native_class='QPushButton'):
    output.mkdir(parents=True, exist_ok=True)
    template = ROOT / 'generator/templates/custom_signals.bend'
    if template.read_text() not in (package / 'qt.bend').read_text():
        raise RuntimeError('The package does not contain the current custom signal source')
    imported = os.path.relpath(package / 'qt.bend', output).replace(os.sep, '/')
    prefix = f'''import Base
import {imported} as Qt

def changed() -> Qt.Signal:
  Qt.Signal.define("changed", [Qt.int32(), Qt.string()])

def finished() -> Qt.Signal:
  Qt.Signal.define("finished", [])

def buttonReady() -> Qt.Signal:
  Qt.Signal.define("buttonReady", [Qt.QPushButton.arg()])

'''
    valid_handler = '''def handler(state: Unit, value: Qt.Int32, title: String) -> Qt.Action(Unit):
  Qt.Action.pure(Unit, Unit{})

'''
    valid_connect = '''def connect(object: Qt.QObject) -> Qt.Action(Qt.Connection):
  Qt.Signal.connect(~changed(), ~Unit, ~handler, object, Unit{})
'''
    valid_emit = '''def emit(object: Qt.QObject) -> Qt.Action(Unit):
  Qt.Signal.emit(~changed(), object, Qt.Int32{42}, "Loading")
'''
    native_handler = '''def ready(state: Unit, button: Qt.QPushButton) -> Qt.Action(Unit):
  Qt.Action.pure(Unit, Unit{})

def connect_button(object: Qt.QObject) -> Qt.Action(Qt.Connection):
  Qt.Signal.connect(~buttonReady(), ~Unit, ~ready, object, Unit{})
'''
    native_emit = '''def emit_button(object: Qt.QObject, button: Qt.QPushButton) -> Qt.Action(Unit):
  Qt.Signal.emit(~buttonReady(), object, button)
'''
    cases = {
        'valid': (valid_handler + valid_connect + '\n' + valid_emit + '''
def emit_empty(object: Qt.QObject) -> Qt.Action(Unit):
  Qt.Signal.emit(~finished(), object)
''', True),
        'wrong_handler_argument': (valid_handler.replace('value: Qt.Int32', 'value: String') + valid_connect, False),
        'wrong_handler_result': (valid_handler.replace('Qt.Action(Unit)', 'Qt.Action(Bool)')
                                  .replace('Qt.Action.pure(Unit, Unit{})', 'Qt.Action.pure(Bool, True{})') + valid_connect, False),
        'wrong_emitted_argument': (valid_emit.replace('Qt.Int32{42}', '"wrong"'), False),
        'wrong_emitted_arity': (valid_emit.replace(', "Loading"', ''), False),
        'valid_native_class': (native_handler + '\n' + native_emit, True),
        'wrong_native_handler_class': (native_handler.replace('button: Qt.QPushButton', 'button: Qt.QObject'), False),
        'wrong_native_emitted_class': (native_emit.replace('button: Qt.QPushButton', 'button: Qt.QObject'), False),
    }
    results = {}
    for name, (body, valid) in cases.items():
        source = output / (name + '.bend')
        source.write_text((prefix + body).replace('Qt.QPushButton', 'Qt.' + native_class))
        result = subprocess.run([str(BEND), str(source), '--check-only'], cwd=ROOT,
                                text=True, capture_output=True, timeout=180)
        diagnostic = (result.stdout + result.stderr).strip()
        (output / (name + '.log')).write_text(diagnostic + '\n')
        if valid:
            expected = bool(re.fullmatch(
                r'SOME PROOFS FAIL\nError: \d+ defs rely on unsafe or foreign code:\n'
                r'defs that depend on foreign effects: [A-Za-z0-9_./, \n]+', diagnostic))
        else:
            expected = '- expected :' in diagnostic and '- observed :' in diagnostic
        if result.returncode != 1 or not expected:
            raise RuntimeError(f'Unexpected type-check result for {name}: {diagnostic[:2000]}')
        results[name] = 'typed' if valid else 'rejected'
    receipt = dict(cases=results, source_sha256=hashlib.sha256(template.read_bytes()).hexdigest(),
                   source_identity=True, native_runtime_proved=False)
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('PASS custom signal declarations: typed handlers and emitters; six incompatible programs rejected')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--native-class', default='QPushButton', help='Concrete QObject class present in the tested profile')
    args = parser.parse_args()
    package = args.package.resolve()
    check(package, args.output or package / 'custom-signal-types', args.native_class)
