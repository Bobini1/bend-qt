#!/usr/bin/env python3
"""Check shared function handlers using pinned extractor data and C++ headers.

The class subset is a bounded fixture, not a production class-selection policy.
"""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
from backend import compiler_flags
import callbacks
from generate import Generator
from overload_names import NameLock
from qt_targets import installed_version


def check(api, version):
    generator = Generator(api, dict(minimum_qt=version,
        qt_modules=['QtCore', 'QtGui', 'QtWidgets', 'QtWebEngineCore'], exclude_methods={}), NameLock())
    generator.collect()
    callbacks.prepare(generator)
    items = [item for item in generator.callback_functions
             if item['owner'] == 'QWebEnginePage' and item['function']['name'] == 'runJavaScript']
    assert len(items) == 2, [item['function']['minimal_signature'] for item in items]
    assert len({item['method']['method_id'] for item in items}) == 1
    assert len({item['public'] for item in items}) == 2
    assert all(item['method']['public'] == 'QWebEnginePage.Handler.runJavaScript' for item in items)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qt-root', type=Path, default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    parser.add_argument('--work', type=Path, default=ROOT / 'build/callback-spellings')
    args = parser.parse_args()
    version = installed_version(args.qt_root)
    short = ''.join(version.split('.')[:2])
    api = json.loads((ROOT / ('build/qt' + short) / 'api.json').read_text())
    api['classes'] = [copy.deepcopy(cls) for cls in api['classes']
                      if cls['name'] in {'QObject', 'QVariant', 'QWebEnginePage'}]
    for cls in api['classes']:
        cls['functions'] = [function for function in cls['functions']
                            if cls['name'] == 'QWebEnginePage' and function['name'] == 'runJavaScript']
    api['global_functions'] = []
    check(copy.deepcopy(api), version)
    # Both spellings occur in upstream declarations/snippets. Force the pair
    # even on SDKs whose extractor happens to emit consistent whitespace.
    page = next(cls for cls in api['classes'] if cls['name'] == 'QWebEnginePage')
    for index, function in enumerate(page['functions']):
        argument = 'const QVariant&' if index % 2 else 'const QVariant &'
        function['source_signatures'] = ['runJavaScript(QString,std::function<void(' + argument + ')>)']
        function['snippets'] = []
    check(api, version)
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    source = work / 'overloads.cpp'
    source.write_text('''#include <QtWebEngineCore/QWebEnginePage>
#include <type_traits>
using Compact = std::function<void(const QVariant&)>;
using Spaced = std::function<void(const QVariant &)>;
static_assert(std::is_same_v<Compact, Spaced>);
void attach(QWebEnginePage &page, const Compact &callback) {
    page.runJavaScript(QString(), callback);
    page.runJavaScript(QString(), 0, callback);
}
''')
    flags = compiler_flags(args.qt_root, 'clang++-19', ['QtCore', 'QtGui', 'QtWidgets', 'QtWebEngineCore'])
    subprocess.run([*flags, '-fsyntax-only', str(source)], check=True)
    (work / 'receipt.json').write_text(json.dumps(dict(passed=True, qt=version,
        actual_extractor_overloads=2, shared_handler=1, distinct_call_adapters=2,
        forced_cpp_whitespace_variants=True, actual_cpp_overload_declarations=True,
        boundary='Generator metadata and pinned C++ declarations; callback execution/lifetimes require integration tests'), indent=2) + '\n')
    print('QT_CALLBACK_SPELLINGS_OK qt=' + version + ' overloads=2 shared_handler=1 actual_cpp=1')


if __name__ == '__main__':
    main()
