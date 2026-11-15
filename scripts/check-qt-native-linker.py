#!/usr/bin/env python3
"""Exercise linker selection and dependency-checked embedded payload reuse."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'generator'))
from backend import command, compile_backend
import embedded_elf
import native_linker


def load(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,default=ROOT/'build/native-linker-test')
    parser.add_argument('--qt-root',type=Path,default=Path.home()/'.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    args=parser.parse_args(); work=args.work.resolve(); work.mkdir(parents=True,exist_ok=True)
    os.environ['BQT_NATIVE_WORKSPACE']='off'
    os.environ['BQT_LINKER']='lld'
    selected=native_linker.select('clang++-19')
    assert selected['flags'] and 'LLD' in selected['identity']['version']
    qt=work/'dependency-kit'; (qt/'lib').mkdir(parents=True,exist_ok=True)
    for link in ('libQt6Core.so','libQt6Core.so.6'):
        (qt/'lib'/link).unlink(missing_ok=True)
        (qt/'lib'/link).symlink_to('libcore1.so')
    def library(name, value, *, exported=True):
        source=work/(name+'.cpp')
        source.write_text('extern "C" int '+('cache_value' if exported else 'removed_value')+'() { return '+str(value)+'; }\n')
        command(['clang++-19',*selected['flags'],'-shared','-fPIC',source,
                 '-Wl,-soname,libQt6Core.so.6','-o',qt/'lib'/name])
    library('libcore1.so',41); library('libcore2.so',55)
    source=work/'native.cpp'
    source.write_text('''extern "C" int cache_value();
struct BqtRequest { int value; }; struct BqtHost;
extern "C" void bqt_abi_call(BqtRequest *r) { r->value=cache_value(); }
extern "C" const char *bqt_abi_start(const BqtHost *) { return nullptr; }
extern "C" int bqt_abi_stop() { return 0; }
''')
    obj=work/'input.o'; command(['clang++-19','-fPIC','-c',source,'-o',obj])
    folder=work/'package'; folder.mkdir(exist_ok=True)
    def package(module=embedded_elf):
        value=module.package(obj,qt,folder,'clang++-19',['QtCore'],command)
        hit=json.loads((folder/'native-package-resources.json').read_text())['cache_hit']
        return value,hit
    def consumer(payload,value):
        code='''#define _GNU_SOURCE
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <dlfcn.h>
typedef struct { int value; } BqtRequest;
typedef struct BqtHost BqtHost;
'''+payload+'''
int main(int argc,char **argv) {
    const char *error=bqt_load_payload();
    if(error) { puts(error); return 1; }
    if(bqt_abi_start(NULL)) return 2;
    BqtRequest r={0}; bqt_abi_call(&r);
    return r.value==atoi(argv[1]) ? bqt_abi_stop() : 3;
}
'''
        path=work/'consumer.c'; path.write_text(code)
        binary=work/'consumer'; command(['clang',path,'-ldl','-o',binary])
        command([binary,str(value)],env=dict(os.environ,LD_LIBRARY_PATH=str(qt/'lib')))
    first,hit=package(); consumer(first[0],41)
    second,hit=package(); assert hit and second==first
    before=json.loads((folder/'native-package-cache.json').read_text())
    library('libcore1.so',43)
    changed,hit=package(); assert not hit; consumer(changed[0],43)
    assert json.loads((folder/'native-package-cache.json').read_text())['key']==before['key']
    for link in ('libQt6Core.so','libQt6Core.so.6'):
        (qt/'lib'/link).unlink(); (qt/'lib'/link).symlink_to('libcore2.so')
    changed,hit=package(); assert not hit; consumer(changed[0],55)
    clone=work/'private-packager'; (clone/'templates').mkdir(parents=True,exist_ok=True)
    shutil.copyfile(ROOT/'generator/embedded_elf.py',clone/'embedded_elf.py')
    template=clone/'templates/embedded_elf.c'
    template.write_text((ROOT/'generator/templates/embedded_elf.c').read_text()+'\n// loader-cache-control\n')
    cloned=load('private_embedded_elf',clone/'embedded_elf.py')
    changed,hit=package(cloned); assert not hit and 'loader-cache-control' in changed[0]
    consumer(changed[0],55)
    same,hit=package(cloned); assert hit and same==changed
    (folder/'native-payload.c').write_text('corrupted cached payload')
    repaired,hit=package(cloned); assert not hit; consumer(repaired[0],55)
    (folder/'native.so').write_bytes(b'invalid ELF')
    repaired,hit=package(cloned); assert not hit; consumer(repaired[0],55)
    stamp=(folder/'native-package-cache.json').read_bytes()
    encoded=(folder/'native-payload.c').read_bytes()
    library('libcore2.so',55,exported=False)
    try: package(cloned)
    except subprocess.CalledProcessError: pass
    else: raise RuntimeError('Missing dependency symbol was packaged')
    assert (folder/'native-package-cache.json').read_bytes()==stamp
    assert (folder/'native-payload.c').read_bytes()==encoded
    library('libcore2.so',55)
    repaired,hit=package(cloned); consumer(repaired[0],55)
    rule=work/'spaces.d'; rule.write_text('target: a\\ b \\\n c\n\na\\ b:\n')
    assert embedded_elf._link_dependencies(rule)==['a b','c']
    control=load('native_linker_shards',ROOT/'scripts/check-qt-native-shards.py')
    shards=work/'switch'; shards.mkdir(exist_ok=True)
    native=shards/'wrappers.cpp'; native.write_text(control.NATIVE)
    (shards/'shared-input.h').write_text('#define INPUT_VALUE 47\n')
    os.environ['BQT_SHARD_OPERATIONS']='1'; os.environ['BQT_SHARD_JOBS']='1'
    compile_backend(native,args.qt_root,shards,'clang++-19',['QtCore'])
    os.environ['BQT_LINKER']='system'
    compile_backend(native,args.qt_root,shards,'clang++-19',['QtCore'])
    resources=json.loads((shards/'native-resources.json').read_text())
    assert {r['name'] for r in resources['shards']}=={'combined'}, resources
    assert len(resources['cached'])==6, resources
    old=json.loads(command(['llvm-readobj-19','--elf-output-style=JSON','--symbols',shards/'wrappers.o']).stdout)[0]
    old_names=sorted(row['Symbol']['Name']['Name'] for row in old['Symbols']
                     if row['Symbol']['Section']['Name']=='Undefined' and row['Symbol']['Name']['Name'])
    new_names=sorted(command(['llvm-nm-19','--undefined-only','--format=just-symbols',shards/'wrappers.o']).stdout.splitlines())
    assert old_names==new_names
    assert (shards/'proxy-traits.bin').read_bytes()==bytes([1,0,1])
    receipt=dict(passed=True,lld_selected=True,embedded_consumers_passed=True,
        unchanged_payload_reused=True,library_content_invalidates=True,symlink_target_invalidates=True,
        loader_invalidates=True,corrupt_artifacts_rebuilt=True,failed_link_preserves_checked_cache=True,
        phony_and_escaped_dependency_rules=True,linker_switch_preserves_compilation=True,
        compact_object_inventory_matches_symbol_dump=True,
        boundary='Real ELF link/dependency and embedded consumer controls; a tiny test library uses an allowed Qt SONAME. Actual Qt behavior is covered by the native integration gates.')
    (work/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print('QT612_NATIVE_LINKER_OK lld=1 cache=1 dependencies=1 symlinks=1 loader=1 failures=1 compile_reused=1')


if __name__=='__main__':
    main()
