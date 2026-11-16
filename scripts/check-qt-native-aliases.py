#!/usr/bin/env python3
"""Check lazy Qt metatype registration before installing native aliases."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
from custom_signals import native_meta_type_body


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qt-root', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--mutation-checks', action='store_true')
    args = parser.parse_args()
    qt, work = args.qt_root.resolve(), args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    body = '\n'.join(native_meta_type_body('QJSValue'))
    partition = (ROOT / 'generator/templates/partition_metatypes.cpp').read_text()
    prefix = '''#include <QtCore/QCoreApplication>
#include <QtCore/QVariant>
#include <QtQml/QJSEngine>
#include <map>
#include <memory>
#include <cstring>
#include <stdexcept>
struct AliasProbe { int value = 42; };
Q_DECLARE_METATYPE(AliasProbe)
'''
    suffix = '''
int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    const auto js = registered_js();
    if (js.id() < QMetaType::User || QMetaType::fromName("QJSValue").id() != js.id()) return 1;
    const auto isolated = BendQualifiedTypes::plain(QMetaType::fromType<AliasProbe>(), "Probe.Module.AliasProbe");
    if (isolated.id() < QMetaType::User || QMetaType::fromName("Probe.Module.AliasProbe").id() != isolated.id()) return 2;
    QJSEngine engine;
    const auto map = engine.evaluate("({answer:42})").toVariant().toMap();
    return map.value("answer").toInt() == 42 ? 0 : 3;
}
'''
    variants = [('valid', body, partition, 0)]
    if args.mutation_checks:
        variants += [
            ('unregistered_native_alias', body.replace('    (void)meta.id(); // Allocate the ID before installing aliases.\n', ''), partition, 1),
        ]
    results = {}
    for name, current_body, current_partition, expected in variants:
        source = work / (name + '.cpp')
        source.write_text(prefix + current_partition + '\nstatic QMetaType registered_js() {\n' + current_body + '\n}\n' + suffix)
        executable = work / name
        subprocess.run(['clang++-19', '-std=c++17', '-fPIC', '-I' + str(qt / 'include'),
                        '-I' + str(qt / 'include/QtCore'), '-I' + str(qt / 'include/QtQml'),
                        source, '-L' + str(qt / 'lib'), '-Wl,-rpath,' + str(qt / 'lib'),
                        '-lQt6Qml', '-lQt6Core', '-o', executable], check=True)
        checked = subprocess.run([executable], env=dict(os.environ, LD_LIBRARY_PATH=str(qt / 'lib')))
        if checked.returncode != expected:
            raise RuntimeError(f'{name}: expected exit {expected}, observed {checked.returncode}')
        results[name] = checked.returncode
    receipt = dict(verification_complete=True, cases=results,
                   native_body_sha256=hashlib.sha256(body.encode()).hexdigest(),
                   partition_template_sha256=hashlib.sha256(partition.encode()).hexdigest())
    (work / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('PASS native Qt aliases: registered IDs and QML object conversion' +
          ('; registration-order regression rejected' if args.mutation_checks else ''))


if __name__ == '__main__':
    main()
