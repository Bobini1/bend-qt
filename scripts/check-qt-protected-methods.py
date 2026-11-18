#!/usr/bin/env python3
"""Exercise protected assignments, ref-qualified calls and Qt overload markers."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
import protected_members
from native_objects import saved_traits


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-work', type=Path, default=ROOT / 'build/qt612')
    parser.add_argument('--work', type=Path, default=ROOT / 'build/protected-methods')
    parser.add_argument('--qt-root', type=Path, default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    api = json.loads((args.source_work / 'api.json').read_text())
    traits = saved_traits(args.source_work)
    classes = {c['name']: dict(c, **traits.get(c['name'], {})) for c in api['classes']}
    targets = {'QEvent': 'operator=', 'QCanvasGradient': 'operator=',
               'QStringConverterBase': 'operator=', 'QSqlResult': 'boundValues',
               'QValue3DAxisFormatter': 'gridPositions'}
    functions = [f for name, method in targets.items() for f in classes[name]['functions']
                 if f['name'] == method and f['protected'] and not f.get('removed')]
    generator = SimpleNamespace(classes=classes, ids={name: i for i, name in enumerate(targets, 1)},
                                methods=[dict(function=f) for f in functions], enums={})
    def call(owner, name, arguments, receiver, const=False):
        f = next(f for f in functions if f['declaring_class'] == owner and f['name'] == name
                 and f['const'] == const)
        return protected_members.expression(generator, f, arguments, receiver)
    assign = call('QEvent', 'operator=', ['other'], '&event')
    grid = call('QValue3DAxisFormatter', 'gridPositions', [], '&formatter', const=True)
    bound = call('QSqlResult', 'boundValues', [], 'result')
    source = args.work / 'main.cpp'
    source.write_text('''#include <QtCore/QtCore>
#include <QtCanvasPainter/QCanvasGradient>
#include <QtGraphs/QValue3DAxisFormatter>
#include <QtSql/QtSql>
#include <QtSql/QSqlResult>
#include <cassert>
''' + protected_members.declarations(generator) + f'''
int main(int argc, char **argv) {{
    QCoreApplication app(argc, argv);
    QEvent event(QEvent::User), other(QEvent::User);
    event.ignore();
    {assign};
    assert(event.isAccepted());
    QValue3DAxisFormatter formatter;
    const auto &positions = {grid};
    assert(positions.isEmpty());
    auto database = QSqlDatabase::addDatabase("QSQLITE");
    database.setDatabaseName(":memory:");
    assert(database.open());
    QSqlQuery query(database);
    assert(query.prepare("select ?"));
    query.bindValue(0, 7);
    auto *result = const_cast<QSqlResult *>(query.result());
    auto &values = {bound};
    assert(values.size() == 1 && values[0].toInt() == 7);
    values[0] = 23;
    assert(query.exec() && query.next() && query.value(0).toInt() == 23);
    puts("QT612_PROTECTED_METHODS_OK assignment=1 ref_qualified=1 hidden_marker=1 sql_mutation=1");
}}
''')
    qt = args.qt_root
    executable = args.work / 'native'
    command = ['clang++-19', '-std=c++17', '-fPIC', str(source), '-I' + str(qt / 'include')]
    command += ['-I' + str(qt / 'include' / module) for module in ('QtCore', 'QtCanvasPainter', 'QtGraphs', 'QtSql')]
    command += ['-L' + str(qt / 'lib'), '-Wl,-rpath,' + str(qt / 'lib'),
                '-lQt6CanvasPainter', '-lQt6Graphs', '-lQt6Sql', '-lQt6Core', '-o', str(executable)]
    built = subprocess.run(command, text=True, capture_output=True)
    (args.work / 'compile.log').write_text(built.stdout + built.stderr)
    built.check_returncode()
    checked = subprocess.run([str(executable)], text=True, capture_output=True,
        env=dict(os.environ, LD_LIBRARY_PATH=str(qt / 'lib'), QT_PLUGIN_PATH=str(qt / 'plugins')))
    (args.work / 'runtime.log').write_text(checked.stdout + checked.stderr)
    checked.check_returncode()
    assert 'QT612_PROTECTED_METHODS_OK' in checked.stdout
    (args.work / 'receipt.json').write_text(json.dumps(dict(verification_complete=True,
        native_methods=len(functions), output=checked.stdout.strip(),
        generator_sha256=hashlib.sha256((ROOT / 'generator/protected_members.py').read_bytes()).hexdigest(),
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest()), indent=2) + '\n')
    print(checked.stdout, end='')


if __name__ == '__main__':
    main()
