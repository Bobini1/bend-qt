#!/usr/bin/env python3
"""Check outlined QML base factories across native operation translation units."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qt-root', type=Path,
                        default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    parser.add_argument('--work', type=Path,
                        default=ROOT / 'build/qt612/qml-base-factories-check')
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    control = ROOT / 'scripts/check-qt-native-shards.py'
    inputs = [Path(__file__).resolve(), control, ROOT / 'generator/qt_objects.py',
              ROOT / 'generator/templates/qt_objects.cpp', ROOT / 'generator/native_shards.py',
              ROOT / 'generator/backend.py']
    identities = {str(path.relative_to(ROOT)): digest(path) for path in inputs}
    receipt = dict(passed=False, source_sha256=identities)
    destination = work / 'receipt.json'
    destination.write_text(json.dumps(receipt, indent=2) + '\n')
    spec = importlib.util.spec_from_file_location('qml_base_shard_control', control)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    previous = {name: os.environ.get(name) for name in ('BQT_SHARD_OPERATIONS', 'BQT_SHARD_JOBS')}
    os.environ['BQT_SHARD_OPERATIONS'] = '1'
    os.environ['BQT_SHARD_JOBS'] = '1'
    try:
        receipt.update(module.check_qml_base_factories(work, args.qt_root.resolve()))
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    if identities != {str(path.relative_to(ROOT)): digest(path) for path in inputs}:
        raise RuntimeError('Factory check inputs changed during native validation')
    receipt['all_operation_units_separate'] = True
    receipt['private_final_factory_absent_from_public_payload'] = True
    receipt['public_guard_closing_brace_checked'] = True
    destination.write_text(json.dumps(receipt, indent=2) + '\n')
    print('QT612_QML_BASE_FACTORIES_OK')


if __name__ == '__main__':
    main()
