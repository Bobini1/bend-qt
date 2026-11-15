#!/usr/bin/env python3
"""Compile actual value codecs/snapshots for Qt's explicit-copy value type."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
from conversions import Conversions
from generate import Generator


class CodecGenerator:
    classes = {'QWebSocketCorsAuthenticator': dict(object=True, copyable=True)}
    ids = {'QWebSocketCorsAuthenticator': 1}
    argument = Generator.argument
    store_result = Generator.store_result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=ROOT / 'build/explicit-copies')
    parser.add_argument('--qt-root', type=Path, default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    generator = CodecGenerator()
    generator.conversions = Conversions(generator)
    value = generator.conversions.register(dict(kind='value', name='QWebSocketCorsAuthenticator',
        cpp='QWebSocketCorsAuthenticator', bend='QWebSocketCorsAuthenticator', raw='U32', pointer=False))
    declarations, argument = generator.argument(value, 0)
    native = generator.conversions.cpp_code()
    source = '''#include <QtCore/QtCore>
#include <QtWebSockets/QWebSocketCorsAuthenticator>
#include <optional>
#include <array>
#include <memory>
#include <vector>
#include <utility>
#include <cassert>
#include <iostream>
struct BqtValue { uint32_t word = 0, high = 0, tag = 0, owned_handle = 0; };
struct BqtRequest { int error = 0; BqtValue arguments[1], result; };
static std::vector<QWebSocketCorsAuthenticator *> objects(1);
static void discard_value(BqtValue &) {}
static bool wire_shape(BqtRequest *, const BqtValue &value, int shape) { return value.tag == uint32_t(shape); }
template<class T> static T *get(BqtRequest *, uint32_t word, uint16_t, bool = false, bool writable = true) {
    assert(!writable);
    return static_cast<T *>(objects.at(word));
}
template<class T> static uint32_t own(BqtRequest *, T *value, uint16_t) {
    objects.push_back(value); return uint32_t(objects.size() - 1);
}
''' + native + (ROOT / 'generator/templates/native_snapshots.cpp').read_text() + '''
QVariant native_owned_variant_snapshot(const QVariant &value, unsigned) { return value; }
static bool by_value(QWebSocketCorsAuthenticator value) { value.setAllowed(true); return value.allowed(); }
static bool converted_argument(BqtRequest *r) {
''' + '\n'.join('    ' + line for line in declarations) + '\n    return by_value(' + argument + ''');
}
int main() {
    static_assert(std::is_copy_constructible_v<QWebSocketCorsAuthenticator>);
    static_assert(!std::is_convertible_v<const QWebSocketCorsAuthenticator &, QWebSocketCorsAuthenticator>);
    QWebSocketCorsAuthenticator original(QStringLiteral("https://bend.example"));
    original.setAllowed(false); objects.push_back(&original);
    BqtRequest request{}; request.arguments[0].word = 1;
    auto copy = read_''' + value['native_codec'] + '''(&request, request.arguments[0]);
    assert(copy && copy->origin() == original.origin() && !copy->allowed());
    copy->setAllowed(true); assert(!original.allowed());
    BqtValue result = write_''' + value['native_codec'] + '''(&request, original);
    assert(result.word == 2 && objects[2]->origin() == original.origin());
    assert(converted_argument(&request) && !original.allowed());
    auto snapshot = native_owned_snapshot(original);
    assert(snapshot.origin() == original.origin() && !snapshot.allowed());
    std::optional<QWebSocketCorsAuthenticator> optional(std::in_place, original);
    auto optional_snapshot = native_owned_snapshot(optional);
    assert(optional_snapshot && optional_snapshot->origin() == original.origin());
    std::pair<QWebSocketCorsAuthenticator, int> pair(original, 7);
    auto pair_snapshot = native_owned_snapshot(pair);
    assert(pair_snapshot.first.origin() == original.origin() && pair_snapshot.second == 7);
    delete objects[2];
    std::cout << "QT612_EXPLICIT_COPIES_OK codec=1 argument=1 snapshot=1 optional=1 pair=1\\n";
}
'''
    path = args.work / 'explicit-copies.cpp'; path.write_text(source)
    binary = args.work / 'explicit-copies'
    command = ['clang++-19', '-std=c++17', '-O1', '-fPIC', str(path),
        '-I' + str(args.qt_root / 'include'), '-I' + str(args.qt_root / 'include/QtCore'),
        '-L' + str(args.qt_root / 'lib'), '-Wl,-rpath,' + str(args.qt_root / 'lib'),
        '-lQt6Core', '-lQt6WebSockets', '-o', str(binary)]
    compiled = subprocess.run(command, text=True, capture_output=True)
    (args.work / 'compile.log').write_text(compiled.stdout + compiled.stderr)
    if compiled.returncode: raise RuntimeError('Explicit-copy codec compilation failed; see ' + str(args.work / 'compile.log'))
    result = subprocess.run([str(binary)], text=True, capture_output=True)
    (args.work / 'native.log').write_text(result.stdout + result.stderr)
    if result.returncode: raise RuntimeError('Explicit-copy codec native test failed; see ' + str(args.work / 'native.log'))
    receipt = dict(passed=True, qt='6.12.0', output=result.stdout,
        source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        generator_sha256={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in
            ('generator/conversions.py', 'generator/generate.py', 'generator/templates/native_snapshots.cpp')})
    (args.work / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(result.stdout, end='')


if __name__ == '__main__': main()
