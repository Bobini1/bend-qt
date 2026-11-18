#!/usr/bin/env python3
"""Maintainer checks for the embedded ELF and dependency-aware compile cache."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
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


def cached(cache):
    """The environment of a program whose module cache is the given directory."""
    return dict(os.environ, XDG_CACHE_HOME=str(cache))


# The cache must be private, which a mounted Windows workspace cannot express.
CACHES = Path.home() / '.cache/bend-qt-generator/backend-test'


def check_consumer(work, payload, expected):
    source = work / 'consumer.c'
    source.write_text(CONSUMER.replace('@PAYLOAD@', payload).replace('@EXPECTED@', str(expected)))
    binary = work / 'consumer'
    run(['clang', source, '-o', binary, '-ldl', '-pthread'])
    dependencies = run(['ldd', binary])
    if any(name in dependencies for name in ('libQt', 'libstdc++', 'libz.so')):
        raise RuntimeError('Consumer gained a native payload link dependency')
    cache = CACHES / 'cache'
    shutil.rmtree(cache, ignore_errors=True)
    CACHES.mkdir(parents=True, exist_ok=True)
    output = run([binary], env=cached(cache))
    if 'QT612_EMBEDDED_ELF_OK' not in output:
        raise RuntimeError(output)
    return binary, cache, dependencies


def check_module_cache(binary, cache):
    """The decoded module is cached once, trusted by stat stamp and repaired by rewriting."""
    [entry] = [path for path in (cache / 'bend-qt').iterdir() if not path.name.startswith('.')]
    module, stamp = entry / 'native.so', entry / '.ready'
    assert module.stat().st_mode & 0o777 == 0o500 and (entry / '.use').stat().st_size
    before = module.stat(), stamp.stat()
    run([binary], env=cached(cache))
    after = module.stat(), stamp.stat()
    assert [(s.st_ino, s.st_mtime_ns) for s in before] == [(s.st_ino, s.st_mtime_ns) for s in after], (
        'A warm start rewrote the cached module')
    # A changed module, a changed mode and a substituted link are each rewritten.
    module.chmod(0o700); module.write_bytes(bytes(module.stat().st_size)); module.chmod(0o500)
    run([binary], env=cached(cache))
    assert module.stat().st_ino != before[0].st_ino and stamp.stat().st_ino != before[1].st_ino
    module.chmod(0o700)
    run([binary], env=cached(cache))
    assert module.stat().st_mode & 0o777 == 0o500
    module.unlink(); module.symlink_to('/etc/passwd')
    run([binary], env=cached(cache))
    assert module.is_file() and not module.is_symlink()
    # Concurrent first starts decode the module once and share it.
    fresh = cache.parent / 'concurrent-cache'
    shutil.rmtree(fresh, ignore_errors=True)
    outputs = list(ThreadPoolExecutor(max_workers=8).map(lambda _: run([binary], env=cached(fresh)), range(16)))
    assert all('QT612_EMBEDDED_ELF_OK' in output for output in outputs)
    names = sorted(path.name for path in (fresh / 'bend-qt' / entry.name).iterdir())
    assert names == ['.lock', '.ready', '.use', 'native.so'], names
    shutil.rmtree(fresh)
    # The cache needs a home; it does not fall back to the working directory.
    homeless = {key: value for key, value in os.environ.items() if key not in ('HOME', 'XDG_CACHE_HOME')}
    result = subprocess.run([str(binary)], env=homeless, text=True, capture_output=True)
    assert result.returncode == 125 and 'HOME' in result.stdout, result.stdout


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
    binary, cache, dependencies = check_consumer(work, first, 19)
    check_module_cache(binary, cache)
    second, _, second_receipt = compile_backend(source, args.qt_root, work, 'clang++-19', ['QtCore'])
    if not second_receipt['compile_cache_hit'] or first != second:
        raise RuntimeError('An unchanged native input did not reproduce its cached payload')
    header.write_text('#define CACHE_VALUE 20\n')
    changed, _, changed_receipt = compile_backend(source, args.qt_root, work, 'clang++-19', ['QtCore'])
    if changed_receipt['compile_cache_hit'] or first == changed:
        raise RuntimeError('A changed transitive header reused stale native code')
    check_consumer(work, changed, 20)
    # The zlib checksum must reject corrupted package bytes before dlopen.
    # The module is decoded only when its cache entry is absent.
    corrupted = changed.replace('static const char bqt_payload[] =\n"', 'static const char bqt_payload[] =\n"A', 1)
    consumer = work / 'corrupt.c'
    consumer.write_text(CONSUMER.replace('@PAYLOAD@', corrupted).replace('@EXPECTED@', '20'))
    run(['clang', consumer, '-o', work / 'corrupt', '-ldl', '-pthread'])
    shutil.rmtree(cache)
    rejected = subprocess.run([str(work / 'corrupt')], env=cached(cache), text=True, capture_output=True)
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
    if any((path / 'native.so').exists() for path in (cache / 'bend-qt').iterdir()):
        raise RuntimeError('A corrupt payload left a cached module')
    shutil.rmtree(CACHES)
    receipt = dict(first=first_receipt['payload'], consumer_dependencies=dependencies,
        unchanged_cache_hit=True, changed_header_invalidates=True, module_cache=dict(
            stat_stamp=True, rewritten=['content', 'mode', 'symlink'], concurrent_first_starts=16, needs_home=True),
        corruption_rejected=True, missing_symbol_rejected=True,
        constructors=True, exceptions=True, rtti=True, thread_local_storage=True)
    (work / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('PASS embedded ELF: static initialization, exceptions, RTTI, per-thread TLS, cache invalidation, '
          'module cache and negative controls')


if __name__ == '__main__':
    main()
