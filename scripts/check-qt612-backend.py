#!/usr/bin/env python3
"""Maintainer checks for the embedded ELF and dependency-aware compile cache."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
from backend import compile_backend


def run(args, **kwargs):
    result = subprocess.run([str(a) for a in args], text=True, capture_output=True, **kwargs)
    if result.returncode:
        raise RuntimeError(f'{args}: {result.returncode}\n{result.stdout}\n{result.stderr}')
    return result.stdout


NATIVE = r'''
#include <string>
#include <stdexcept>
#include "cache-input.h"
struct BqtRequest { int result; };
struct BqtHost;
static std::string initialized = "native static initialization";
static thread_local int counter = 13;
extern "C" __attribute__((visibility("default"))) void bqt_abi_call(BqtRequest *r) {
    try { throw std::runtime_error(initialized); }
    catch (const std::exception &error) {
        if (!dynamic_cast<const std::runtime_error *>(&error)) r->result = -1;
        else if (std::string(error.what()) != initialized) r->result = -2;
        else r->result = ++counter;
    }
}
extern "C" __attribute__((visibility("default"))) const char *bqt_abi_start(const BqtHost *) {
    return initialized.size() == 28 ? nullptr : "static initialization did not run";
}
extern "C" __attribute__((visibility("default"))) int bqt_abi_stop(void) {
    return CACHE_VALUE;
}
'''

CONSUMER = r'''
#define _GNU_SOURCE
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <pthread.h>
#include <dlfcn.h>
typedef struct BqtRequest { int result; } BqtRequest;
typedef struct BqtHost BqtHost;
@PAYLOAD@
static int call(void) {
    BqtRequest request = {0};
    bqt_abi_call(&request);
    return request.result;
}
static void *other_thread(void *unused) {
    return (void *)(intptr_t)call();
}
int main(void) {
    const char *error = bqt_load_payload();
    if (error) { puts(error); return 125; }
    if (bqt_abi_start(NULL) || bqt_abi_stop() != @EXPECTED@) return 1;
    if (call() != 14 || call() != 15) return 2;
    pthread_t thread;
    if (pthread_create(&thread, NULL, other_thread, NULL)) return 3;
    void *result;
    if (pthread_join(thread, &result) || (intptr_t)result != 14) return 4;
    puts("QT612_EMBEDDED_ELF_OK constructors=1 exceptions=1 rtti=1 tls=1");
}
'''


def check_consumer(work, payload, expected):
    source = work / 'consumer.c'
    source.write_text(CONSUMER.replace('@PAYLOAD@', payload).replace('@EXPECTED@', str(expected)))
    binary = work / 'consumer'
    run(['clang', source, '-o', binary, '-ldl', '-pthread'])
    dependencies = run(['ldd', binary])
    if any(name in dependencies for name in ('libQt', 'libstdc++', 'libz.so')):
        raise RuntimeError('Consumer gained a native payload link dependency')
    output = run([binary])
    if 'QT612_EMBEDDED_ELF_OK' not in output:
        raise RuntimeError(output)
    return dependencies


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qt-root', type=Path, default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    parser.add_argument('--work', type=Path, default=ROOT / 'build/qt612/backend-test')
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    source = work / 'native.cpp'
    header = work / 'cache-input.h'
    source.write_text(NATIVE)
    header.write_text('#define CACHE_VALUE 19\n')
    first, _, first_receipt = compile_backend(source, args.qt_root, work, 'clang++-19', ['QtCore'])
    dependencies = check_consumer(work, first, 19)
    second, _, second_receipt = compile_backend(source, args.qt_root, work, 'clang++-19', ['QtCore'])
    if not second_receipt['compile_cache_hit'] or first != second:
        raise RuntimeError('An unchanged native input did not reproduce its cached payload')
    header.write_text('#define CACHE_VALUE 20\n')
    changed, _, changed_receipt = compile_backend(source, args.qt_root, work, 'clang++-19', ['QtCore'])
    if changed_receipt['compile_cache_hit'] or first == changed:
        raise RuntimeError('A changed transitive header reused stale native code')
    check_consumer(work, changed, 20)
    # The zlib checksum must reject corrupted package bytes before dlopen.
    corrupted = changed.replace('static const char bqt_payload[] =\n"', 'static const char bqt_payload[] =\n"A', 1)
    consumer = work / 'corrupt.c'
    consumer.write_text(CONSUMER.replace('@PAYLOAD@', corrupted).replace('@EXPECTED@', '20'))
    run(['clang', consumer, '-o', work / 'corrupt', '-ldl', '-pthread'])
    rejected = subprocess.run([str(work / 'corrupt')], text=True, capture_output=True)
    if rejected.returncode != 125 or 'payload' not in rejected.stdout:
        raise RuntimeError('Corrupt native payload was not rejected cleanly')
    missing = work / 'missing'
    missing.mkdir(exist_ok=True)
    missing_source = missing / 'native.cpp'
    missing_source.write_text('extern "C" int deliberately_missing_bqt_symbol();\n' + NATIVE.replace(
        '#include "cache-input.h"', '#define CACHE_VALUE deliberately_missing_bqt_symbol()'))
    try:
        compile_backend(missing_source, args.qt_root, missing, 'clang++-19', ['QtCore'])
    except RuntimeError as error:
        if 'deliberately_missing_bqt_symbol' not in str(error):
            raise
    else:
        raise RuntimeError('Native undefined symbol was not rejected')
    receipt = dict(first=first_receipt['payload'], consumer_dependencies=dependencies,
        unchanged_cache_hit=True, changed_header_invalidates=True,
        corruption_rejected=True, missing_symbol_rejected=True,
        constructors=True, exceptions=True, rtti=True, thread_local_storage=True)
    (work / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('PASS embedded ELF: static initialization, exceptions, RTTI, per-thread TLS, cache invalidation and negative controls')


if __name__ == '__main__':
    main()
