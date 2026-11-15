#!/usr/bin/env python3
"""Compile the production RCC validator with ASan/UBSan and hostile inputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def run(args, **kwargs):
    result = subprocess.run([str(x) for x in args], text=True, capture_output=True, **kwargs)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--qt-root', type=Path, default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    parser.add_argument('--work', type=Path, default=ROOT / 'build/qt612/check/resource-bounds')
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    production = (ROOT / 'generator/templates/persistent_storage.cpp').read_text()
    validator = production[production.index('static uint32_t rcc_u32'):production.index('// File-backed roots')]
    source = r'''
#include <QtCore/QByteArray>
#include <QtCore/QFile>
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>
#include <cassert>
''' + validator + r'''
static void be32(QByteArray &data, qsizetype at, uint32_t value) {
    for (int i = 0; i < 4; ++i) data[at + i] = char(value >> (24 - i * 8));
}
int main(int argc, char **argv) {
    unsigned rejected = 0;
    for (int argument = 1; argument < argc; ++argument) {
        QFile file(QString::fromUtf8(argv[argument])); assert(file.open(QIODevice::ReadOnly));
        const QByteArray good = file.readAll(); assert(valid_rcc_snapshot(good));
        for (qsizetype size = 0; size < good.size(); ++size) {
            assert(!valid_rcc_snapshot(good.first(size))); ++rejected;
        }
        const auto *data = reinterpret_cast<const uchar *>(good.constData());
        uint32_t tree = rcc_u32(data + 8), payload = rcc_u32(data + 12);
        auto invalid_word = [&](qsizetype at, uint32_t value) {
            QByteArray bad = good; be32(bad, at, value); assert(!valid_rcc_snapshot(bad)); ++rejected;
        };
        for (int field : {8, 12, 16}) {
            invalid_word(field, 0); invalid_word(field, 0x80000000u); invalid_word(field, uint32_t(good.size()));
        }
        invalid_word(4, 0); invalid_word(4, 4);
        invalid_word(tree + 6, 0x7fffffffu); // unbounded directory children
        invalid_word(tree + 10, 0); // root cycle
        invalid_word(payload, 0x7fffffffu); // unbounded file payload
        const unsigned width = rcc_u32(data + 4) >= 2 ? 22 : 14;
        invalid_word(tree + width, 0x7fffffffu); // unbounded child name
    }
    uint32_t random = 0x53474956u;
    auto next = [&] { random ^= random << 13; random ^= random >> 17; random ^= random << 5; return random; };
    // Random RCC-looking headers exercise checked integer arithmetic and all
    // short-buffer paths under native sanitizers; they need not all be invalid.
    for (unsigned trial = 0; trial < 20000; ++trial) {
        QByteArray data(qsizetype(next() % 1024), char(0));
        for (auto &byte : data) byte = char(next());
        if (data.size() >= 24) {
            std::memcpy(data.data(), "qres", 4); be32(data, 4, 1 + next() % 3);
            for (int at : {8, 12, 16}) be32(data, at, next() % uint32_t(data.size()));
            be32(data, 20, next() & 5);
        }
        (void)valid_rcc_snapshot(data);
    }
    std::printf("QT612_RESOURCE_BOUNDS_OK formats=%d corruptions=%u random=20000 asan=1 ubsan=1\n", argc - 1, rejected);
}
'''
    cpp = args.work / 'resource-bounds.cpp'
    cpp.write_text(source)
    files = []
    for version in (1, 2, 3):
        binary = args.work / f'fixture-v{version}.rcc'
        run([args.qt_root / 'libexec/rcc', '--binary', '--format-version', version,
             ROOT / 'scripts/fixtures/persistent-resource.qrc', '-o', binary])
        files.append(binary)
    program = args.work / 'resource-bounds'
    run(['g++', '-std=c++17', '-O1', '-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
         '-I' + str(args.qt_root / 'include'), '-I' + str(args.qt_root / 'include/QtCore'),
         cpp, '-L' + str(args.qt_root / 'lib'), '-Wl,-rpath,' + str(args.qt_root / 'lib'), '-lQt6Core', '-o', program])
    result = run([program, *files], env=dict(os.environ, ASAN_OPTIONS='detect_leaks=1:halt_on_error=1', UBSAN_OPTIONS='halt_on_error=1'))
    if 'QT612_RESOURCE_BOUNDS_OK' not in result.stdout:
        raise RuntimeError(result.stdout + result.stderr)
    receipt = dict(validator_sha256=hashlib.sha256(validator.encode()).hexdigest(), stdout=result.stdout.strip(),
                   formats=[1, 2, 3], sanitizers=['address', 'undefined'], random_cases=20000,
                   boundary='Native checks of production RCC bounds validation; not a Bend proof')
    (args.work / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(result.stdout, end='')


if __name__ == '__main__':
    main()
