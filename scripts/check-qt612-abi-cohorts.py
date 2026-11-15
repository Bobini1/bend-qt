#!/usr/bin/env python3
"""Exercise the complete pinned RHI payload and reject other Qt versions."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
from abi_cohorts import compile_payloads, forbidden_imports, inventory, register_exact
from backend import command

NATIVE = r'''
#include <rhi/qshader.h>
#include <QtCanvasPainter/qcanvaspainteritemrenderer.h>
#ifndef BQT_HAS_RHI
#define BQT_HAS_RHI 1
#endif
@ABI@
struct PublicRenderer final : QCanvasPainterItemRenderer {
    ~PublicRenderer() override = default;
};
static int selected() {
    PublicRenderer renderer;
#if BQT_HAS_RHI
    QShader shader = QShader::fromSerialized(QByteArray());
    return shader.isValid() ? -1 : 51;
#else
    return 17;
#endif
}
extern "C" __attribute__((visibility("default"))) void bqt_abi_call(BqtRequest *r) { r->result.word = selected(); }
extern "C" __attribute__((visibility("default"))) const char *bqt_abi_start(const BqtHost *) { return nullptr; }
extern "C" __attribute__((visibility("default"))) int bqt_abi_stop(void) { return selected(); }
'''

CONSUMER = r'''
#define _GNU_SOURCE
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <dlfcn.h>
@ABI@
@PAYLOAD@
static const char *selected_version;
static const char *version(void) { return selected_version; }
static const char *load(void) {
    const char *error = bqt_check_qt_version(version());
    if (error) return error;
@LOAD@
    return NULL;
}
int main(int argc, char **argv) {
    if (argc != 3) return 2;
    selected_version = argv[1];
    const char *error = load();
    if (error) { puts(error); return 125; }
    BqtRequest request = {0};
    bqt_abi_call(&request);
    if (bqt_abi_start(NULL) || request.result.word != (unsigned)atoi(argv[2]) || bqt_abi_stop() != atoi(argv[2])) return 3;
    puts("QT612_ABI_COHORT_OK");
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qt-root', type=Path, default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    parser.add_argument('--work', type=Path, default=ROOT / 'build/qt612/abi-cohort-test')
    args = parser.parse_args()
    qt, work = args.qt_root, args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    shader_header = qt / 'include/QtGui/6.12.0/QtGui/rhi/qshader.h'
    g = SimpleNamespace(profile={'limited_abi': True}, classes={
        'QShader': {'source_file': str(shader_header), 'bases': []},
        'QRhiCommandBuffer': {'source_file': str(shader_header.with_name('qrhi.h')), 'bases': []}})
    if inventory(g)['limited_abi_types'] != ['QRhiCommandBuffer', 'QShader']:
        raise RuntimeError('Pinned RHI header guarantee was not discovered')
    register_exact(g, 'test_private_', 'Audit negative control', ['QTestTable::'])
    candidates = ['Public::render(QRhiCommandBuffer*)', 'Public::render(const QRhiCommandBuffer*)',
                  'Public::render(QShader)', 'Public::render(QShader const&)',
                  'QRhiCommandBuffer::render(QRhiCommandBuffer*)', 'Public::render(QShader::Variant)',
                  'QTestTable::insert(QRhiCommandBuffer*)', 'Public::render(QRhiCommandBuffer**)']
    mangled = [str(index) for index in range(len(candidates))]
    rejected, accepted = forbidden_imports(g, mangled, candidates, set(mangled))
    if accepted != candidates[:2] or rejected != candidates[2:]:
        raise RuntimeError('Opaque pointer audit accepted a version-bound signature')
    if forbidden_imports(g, mangled[:1], candidates[:1], set())[0] != candidates[:1]:
        raise RuntimeError('Opaque pointer import was accepted without a public Qt_6 symbol version')
    modules = ['QtCore', 'QtGui', 'QtNetwork', 'QtQml', 'QtQuick', 'QtOpenGL', 'QtCanvasPainter']
    abi = (ROOT / 'generator/templates/abi.h').read_text().replace('@ARGUMENT_CAPACITY@', '8')
    source = work / 'native.cpp'; source.write_text(NATIVE.replace('@ABI@', abi))
    payload, loader, metadata = compile_payloads(g, source, qt, work, 'clang++-19', modules)
    if 'public_abi_fallback' in metadata:
        raise RuntimeError('A version-pinned package compiled a reduced fallback')
    consumer = work / 'consumer.c'
    consumer.write_text(CONSUMER.replace('@ABI@', abi).replace('@PAYLOAD@', payload).replace('@LOAD@', loader))
    binary = work / 'consumer'
    command(['clang', consumer, '-o', binary, '-ldl'])
    dependencies = command(['ldd', binary]).stdout
    if any(name in dependencies for name in ('libQt', 'libstdc++', 'libz.so')):
        raise RuntimeError('Consumer gained an external native link dependency')
    env = dict(os.environ, LD_LIBRARY_PATH=str(qt / 'lib'))
    if 'QT612_ABI_COHORT_OK' not in command([binary, '6.12.0', 51], env=env).stdout:
        raise RuntimeError('Matching Qt runtime did not retain RHI support')
    rejected = ['6.12.1', '6.13.0', '6.11.0', '7.0.0', '6.12.0-beta', 'invalid']
    for version in rejected:
        result = subprocess.run([str(binary), version, '51'], env=env, capture_output=True, text=True)
        if result.returncode != 125 or "does not match this package's Qt 6.12.0" not in result.stdout:
            raise RuntimeError('Mismatched Qt runtime was not rejected: ' + version)
    receipt = dict(matching_runtime_keeps_rhi=True, rejected_version_strings=rejected,
        version_strings_are_loader_tests_only=True, actual_qt_runtime='6.12.0',
        symbol_audit_negative_cases=7, consumer_dependencies=dependencies,
        full_payload=metadata['payload'], public_abi_fallback=False)
    (work / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('PASS pinned Qt payload: real QShader, matching runtime, mismatch rejection, one complete build')


if __name__ == '__main__':
    main()
