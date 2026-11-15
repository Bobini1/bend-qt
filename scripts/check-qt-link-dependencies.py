#!/usr/bin/env python3
"""Verify exact transitive Qt linking without importing unrelated modules."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'generator'))
from backend import command
from embedded_elf import package, qt_library_closure
from native_linker import select


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,default=ROOT/'build/qt-link-dependencies')
    parser.add_argument('--qt-root',type=Path,help='Accepted for the common gate interface; this control builds a tiny ELF dependency kit')
    args=parser.parse_args()
    work=args.work.resolve();work.mkdir(parents=True,exist_ok=True)
    qt=work/'dependency kit';lib=qt/'lib';lib.mkdir(parents=True,exist_ok=True)
    linker=select('clang++-19')
    def library(name,body,dependencies=()):
        source=work/(name+'.cpp');source.write_text(body)
        command(['clang++-19',*linker['flags'],'-shared','-fPIC',source,
            '-Wl,-soname,libQt6'+name+'.so.6','-L'+str(lib),
            *['-l:libQt6'+value+'.so.6' for value in dependencies],
            '-o',lib/('libQt6'+name+'.so.6')])
    library('Provider','extern "C" int provided() { return 42; }\n')
    library('Direct','extern "C" int provided(); extern "C" int direct() { return provided(); }\n',['Provider'])
    library('Unrelated','extern "C" int unrelated() { return 99; }\n')
    expected=['libQt6Direct.so.6','libQt6Provider.so.6']
    assert qt_library_closure(qt,['QtDirect'],command)==expected
    source=work/'native.cpp'
    source.write_text('''extern "C" int direct(); extern "C" int provided();
struct BqtRequest { int value; }; struct BqtHost;
extern "C" void bqt_abi_call(BqtRequest *r) { r->value=direct()+provided(); }
extern "C" const char *bqt_abi_start(const BqtHost *) { return nullptr; }
extern "C" int bqt_abi_stop() { return 0; }
''')
    obj=work/'native.o';command(['clang++-19','-fPIC','-c',source,'-o',obj])
    old=subprocess.run(['clang++-19',*linker['flags'],'-shared',obj,'-Wl,-z,defs',
        '-L'+str(lib),'-l:libQt6Direct.so.6','-o',work/'missing-direct.so'],capture_output=True,text=True)
    if not old.returncode or 'provided' not in old.stderr:
        raise RuntimeError('The transitive-symbol negative control did not fail as expected')
    folder=work/'package';folder.mkdir(exist_ok=True)
    _,_,metadata=package(obj,qt,folder,'clang++-19',['QtDirect'],command)
    assert set(metadata['dependencies'])==set(expected),metadata['dependencies']
    consumer=work/'main.cpp'
    consumer.write_text('''#include <dlfcn.h>
#include <cassert>
struct Request { int value; };
int main(int argc,char **argv) {
    auto *library=dlopen(argv[1],RTLD_NOW|RTLD_LOCAL); assert(library);
    auto call=reinterpret_cast<void(*)(Request*)>(dlsym(library,"bqt_abi_call")); assert(call);
    Request request{};call(&request);assert(request.value==84);
}
''')
    command(['clang++-19',consumer,'-ldl','-o',work/'main'])
    subprocess.run([str(work/'main'),str(folder/'native.so')],
        env=dict(os.environ,LD_LIBRARY_PATH=str(lib)),check=True)
    provider=lib/'libQt6Provider.so.6'
    backup=lib/'provider.saved'
    provider.rename(backup)
    try:
        try: qt_library_closure(qt,['QtDirect'],command)
        except ValueError: pass
        else: raise RuntimeError('Missing Qt dependency was accepted')
    finally:
        backup.rename(provider)
    outside=work/'outside-provider.so';outside.write_bytes(provider.read_bytes())
    provider.rename(backup);provider.symlink_to(outside)
    try:
        try: qt_library_closure(qt,['QtDirect'],command)
        except ValueError: pass
        else: raise RuntimeError('Qt dependency outside the selected installation was accepted')
    finally:
        provider.unlink();backup.rename(provider)
    receipt=dict(passed=True,direct_transitive_symbol_resolved=True,actual_elf_execution=True,
        unrelated_installed_module_excluded=True,missing_dependency_rejected=True,
        outside_installation_rejected=True,dependencies=expected,
        boundary='Tiny real ELF dependency kit and production packager; full Qt module consumers remain a separate gate')
    (work/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print('QT_LINK_DEPENDENCIES_OK transitive=1 unrelated=0 missing_rejected=1 outside_rejected=1')


if __name__=='__main__': main()
