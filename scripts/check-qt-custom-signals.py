#!/usr/bin/env python3
"""Custom signals and QObject/QML schemas in the complete native payload."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))

BASELINE = '''import Base
import ./qt.bend as Qt

def finished() -> Qt.Signal:
  Qt.Signal.define("finished", [])

def require(ok: Bool) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, "Custom signal availability failed")

def noop(state: Unit) -> Qt.Action(Unit):
  Qt.Action.pure(Unit, Unit{})

def object_cases(+object: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    connected: Qt.Connection <- Qt.Signal.connect(~finished(), ~Unit, ~noop, object, Unit{})
    Qt.Signal.emit(~finished(), object)

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    available: Bool <- Qt.Runtime.hasCustomSignals()
    require(available)
    Qt.scoped(Unit, Qt.QObject.with(Unit, Qt.QObject.newWithSignals("PublicSignals", [finished()]), object => object_cases(object)))
    connections: U32 <- Qt.Runtime.liveConnections()
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(connections, 0) && U32.is_eq(objects, 0))
    Qt.Action.lift(Unit, IO.print("QT612_CUSTOM_SIGNALS_AVAILABLE_OK available=1 create=1 connect=1 emit=1 cleanup=1"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, Qt.QApplication.with(Unit, Qt.QApplication.new(), application => checks())))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qt-root', type=Path, default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    parser.add_argument('--work', type=Path, default=ROOT / 'build/qt612/custom-signals-check')
    parser.add_argument('--skip-focused', action='store_true')
    args = parser.parse_args()
    work, qt = args.work.resolve(), args.qt_root.resolve()
    work.mkdir(parents=True, exist_ok=True)
    if not args.skip_focused:
        subprocess.run(['python3', str(ROOT / 'scripts/check-qt-callbacks.py'), '--only', 'custom-signals', '--only', 'native-signal-arguments',
                        '--only', 'opaque-data', '--only', 'qt-objects', '--only', 'qml-created-objects',
                        '--only', 'qml-extension-inheritance', '--only', 'qml-factory-failures',
                        '--only', 'qt-object-worker',
                        '--only', 'qml-registration-modes', '--only', 'native-argument-types',
                        '--only', 'qml-constructors',
                        '--only', 'signal-connection-modes',
                        '--only', 'native-pointer-arguments',
                        '--only', 'method-metadata',
                        '--only', 'runtime-enums',
                        '--only', 'generic-variants',
                        '--only', 'metadata-arguments', '--only', 'metadata-signal-arguments',
                        '--only', 'convenience-apis', '--only', 'audio-buffer-bytes', '--only', 'quick-test-runner', '--only', 'qml-script-singletons',
                        '--only', 'qml-list-properties', '--only', 'post-routines', '--only', 'child-lookup-options',
                        '--only', 'callback-surfaces',
                        '--only', 'http-server-callbacks', '--module', 'QtHttpServer',
                        '--only', 'oauth-parameter-callbacks', '--module', 'QtNetworkAuth',
                        '--only', 'canvas-grab-callbacks', '--module', 'QtCanvasPainter', '--rhi',
                        '--module', 'QtMultimedia', '--module', 'QtQuickTest', '--only', 'function-pointer-callbacks',
                        '--only', 'data-stream-values', '--only', 'metadata-arrow',
                        '--only', 'native-value-forms',
                        '--only', 'explicit-copy-values', '--module', 'QtWebSockets',
                        '--only', 'value-pointer-calls', '--module', 'QtPositioning', '--module', 'QtSerialBus', '--module', 'QtTextToSpeech',
                        '--only', 'protected-members',
                        '--only', 'protected-lifetimes', '--module', 'QtPrintSupport',
                        '--only', 'protected-fields',
                        '--only', 'native-result-views', '--module', 'QtSql',
                        '--only', 'core-pointer-results',
                        '--only', 'core-keyframes', '--module', 'Qt3DAnimation',
                        '--only', 'qobject-interface-helpers', '--module', 'QtDesigner', '--module', 'QtSql',
                        '--only', 'mutex-lockers', '--only', 'render-factory-results',
                        '--only', 'cursor-guards',
                        '--only', 'io-pipe', '--only', 'touch-sequences', '--module', 'QtTest',
                        '--only', 'dynamic-properties',
                        '--only', 'transition-constructors', '--module', 'QtStateMachine',
                        '--only', 'reverse-pointer-callbacks', '--module', 'QtLocation', '--module', 'QtWebEngineCore',
                        '--only', 'model-source-index',
                        '--only', 'event-dispatcher-transfer',
                        '--only', 'nondefault-properties',
                        '--only', 'property-bindings', '--only', 'qml-singleton-extensions',
                        '--only', 'property-map-subclasses',
                        '--only', 'property-attributes',
                        '--only', 'typed-connection-modes', '--only', 'unicode-metadata',
                        '--only', 'error-messages',
                        '--only', 'properties',
                        '--qt-root', str(qt), '--work', str(work)], cwd=ROOT, check=True)
    focused = json.loads((work / 'receipt.json').read_text())
    if not focused['verification_complete'] or 'custom_signal_types' not in focused:
        raise RuntimeError('The custom signal fixture and type controls must pass first')
    metadata = json.loads((work / 'backend.json').read_text())
    symbols = subprocess.run(['c++filt'], input='\n'.join(metadata['undefined_symbols']) + '\n',
                             text=True, capture_output=True, check=True).stdout
    if any(name in symbols for name in ('QMetaObjectBuilder', 'QMetaMethodBuilder',
                                       'QObjectPrivate::connect', 'QMetaObjectPrivate::signalIndex')):
        raise RuntimeError('The native payload imported private signal metadata/capture APIs')
    selected = {'custom-signals', 'native-signal-arguments', 'opaque-data', 'qt-objects', 'qml-created-objects',
                'qml-extension-inheritance', 'qml-factory-failures', 'qt-object-worker', 'properties',
                'qml-registration-modes', 'qml-constructors', 'native-argument-types', 'signal-connection-modes', 'method-metadata',
                'property-bindings', 'qml-singleton-extensions', 'property-attributes', 'runtime-enums', 'property-map-subclasses', 'generic-variants', 'native-pointer-arguments',
                'typed-connection-modes', 'unicode-metadata', 'error-messages',
                'metadata-arguments', 'metadata-signal-arguments', 'nondefault-properties',
                'convenience-apis', 'audio-buffer-bytes', 'quick-test-runner', 'qml-script-singletons', 'qml-list-properties', 'post-routines', 'child-lookup-options', 'callback-surfaces', 'http-server-callbacks', 'oauth-parameter-callbacks', 'canvas-grab-callbacks', 'function-pointer-callbacks', 'data-stream-values', 'metadata-arrow', 'native-value-forms', 'explicit-copy-values', 'event-dispatcher-transfer', 'protected-members', 'protected-lifetimes', 'model-source-index', 'value-pointer-calls'}
    selected.update({'protected-fields', 'reverse-pointer-callbacks', 'native-result-views', 'core-pointer-results', 'core-keyframes'})
    selected.update({'qobject-interface-helpers', 'mutex-lockers', 'render-factory-results'})
    selected.update({'io-pipe', 'touch-sequences'})
    selected.update({'cursor-guards'})
    selected.update({'dynamic-properties'})
    selected.update({'transition-constructors'})
    if not selected.issubset(set(focused['expected_programs'])):
        raise RuntimeError('The focused package must include the signal, payload and QObject/QML schema fixtures')
    if not focused.get('post_routine_controls'):
        raise RuntimeError('The focused receipt must include post-routine controls')
    # Reuse the complete native payload already exercised by every selected
    # consumer. A disabled-RHI rebuild would test a package we no longer ship.
    consumer = work / 'signal-availability'
    consumer.mkdir(exist_ok=True)
    for name in ('qt.bend', 'qt.c'):
        (consumer / name).write_bytes((work / name).read_bytes())
    (consumer / 'main.bend').write_text(BASELINE)
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen', LD_LIBRARY_PATH=str(qt / 'lib'))
    executable = consumer / 'app'
    subprocess.run([str(Path.home() / '.bend/bin/bend'), str(consumer / 'main.bend'), '-o', str(executable)],
                   cwd=ROOT, env=env, check=True)
    tested = subprocess.run([str(executable)], cwd=ROOT, env=env, text=True, capture_output=True, check=True)
    (consumer / 'run.log').write_text(tested.stdout + tested.stderr)
    if 'QT612_CUSTOM_SIGNALS_AVAILABLE_OK' not in tested.stdout:
        raise RuntimeError(tested.stdout + tested.stderr)
    receipt = dict(verification_complete=True, focused=focused,
                   native_metadata=dict(private_builder_imports=False, marker=tested.stdout.strip()),
                   complete_payload_reused=True, public_abi_fallback=False,
                   native_source_sha256=hashlib.sha256((work / 'wrappers.cpp').read_bytes()).hexdigest())
    (work / 'custom-signals-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('PASS complete-payload metadata: focused signals, QObject/QML schemas, typed consumers and cleanup')


if __name__ == '__main__':
    main()
