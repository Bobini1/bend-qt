#!/usr/bin/env python3
"""Load actual bundled QtCore with a conflicting system Qt search path.

This is a focused deployment control, not the generated Qt package gate.
The ICU notice is an explicit maintainer input, never a consumer download.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
from qt_licenses import Inventory
from runtime_bundle import embed
from runtime_selection import elf_dependencies


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qt-root', type=Path, default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    parser.add_argument('--icu-notice', type=Path, required=True)
    parser.add_argument('--work', type=Path, default=ROOT / 'build/bundled-core-check')
    parser.add_argument('--native-work', type=Path, default=Path.home() / '.cache/bend-qt-generator/bundled-core-check')
    args = parser.parse_args()
    qt = args.qt_root.resolve(); work = args.native_work.resolve(); work.mkdir(parents=True, exist_ok=True)
    report = args.work.resolve(); report.mkdir(parents=True, exist_ok=True)
    inventory = Inventory(qt); files, aliases, order, visited = {}, {}, [], set()

    def visit(path):
        real = path.resolve()
        if real in visited:
            return
        visited.add(real)
        relative = real.relative_to(qt).as_posix()
        if real.name.startswith('libQt6'):
            inventory.binary(path, 'lgpl')
        else:
            assert re.fullmatch(r'libicu(?:data|i18n|uc)\.so\.73\.2', real.name), real
        for needed in elf_dependencies(real):
            if (qt / 'lib' / needed).is_file():
                visit(qt / 'lib' / needed)
        files[relative] = real; order.append(relative)

    visit(qt / 'lib/libQt6Core.so.6')
    for path in (qt / 'lib').glob('*.so*'):
        if path.is_symlink() and path.resolve() in visited:
            aliases[path.relative_to(qt).as_posix()] = path.resolve().relative_to(qt).as_posix()
    assert args.icu_notice.is_file() and args.icu_notice.stat().st_size > 1000
    files['notices/ICU-LICENSE'] = args.icu_notice
    core_sbom = Path(inventory.modules['QtCore']['evidence'])
    files['notices/qtbase.spdx.json'] = core_sbom
    bundle = embed(files, aliases=aliases, context=dict(test='actual QtCore deployment', qt='6.12.0'))
    preload = '\n'.join('    if (snprintf(path,sizeof path,"%s/' + name
        + '",bqt_bundle_root)>=(int)sizeof path) return "Bundled library path is too long";\n'
        + '    library=dlopen(path,RTLD_NOW|RTLD_LOCAL);if(!library)return dlerror();' for name in order)
    c = '#define _GNU_SOURCE\n' + bundle['c'] + '''
static const char *test_load(void) {
    const char *error=bqt_bundle_materialize();if(error)return error;
    char path[PATH_MAX];void *library=NULL;
''' + preload + '''
    const char *(*version)(void);void *symbol=dlsym(library,"qVersion");
    if(!symbol)return "Missing qVersion";memcpy(&version,&symbol,sizeof symbol);
    if(strcmp(version(),"6.12.0"))return "Loaded a different Qt runtime";
    Dl_info info;if(!dladdr(symbol,&info)||!info.dli_fname)return "Missing Qt library origin";
    if(!realpath(info.dli_fname,path))return "Cannot resolve Qt library origin";
    size_t n=strlen(bqt_bundle_root);
    if(strncmp(path,bqt_bundle_root,n)||path[n]!='/')return "Qt escaped the selected runtime";
    return NULL;
}
static Term bundled_core_run(Env e, Term *f, IoWork *w) {
    const char *error=test_load();
    return error ? io_fail(e,ELIBACC,error) : io_done(e,io_str(e,bqt_bundle_root,strlen(bqt_bundle_root)));
}
static void __attribute__((constructor)) bundled_core_register(void) { io_eff(CID(bundled_core),bundled_core_run); }
'''
    bend = 'import Base\n' + bundle['bend'] + '''
def bundled_core() -> IO(Result<&1, &1, U32 & String, String>):
  import "./qt.c"
def main() -> IO(Unit):
  do IO<Unit>:
    root: String <- IO.try(String, bundled_core())
    IO.print(root)
'''
    (work / 'main.bend').write_text(bend); (work / 'qt.c').write_text(c)
    for name, text in bundle['assets'].items():
        (work / name).write_text(text)
    env = dict(os.environ, BEND_NO_TELEMETRY='1'); env.pop('BEND_QT_RUNTIME', None)
    bend = Path.home() / '.bend/bin/bend'
    compiled = subprocess.run([str(bend), 'main.bend', '-o', 'app'], cwd=work, env=env,
                              text=True, capture_output=True)
    (report / 'compile.log').write_text(compiled.stdout + compiled.stderr)
    if compiled.returncode:
        raise RuntimeError('Stock Bend compile failed; see ' + str(report / 'compile.log'))
    env.update(XDG_CACHE_HOME=str(work / 'runtime-cache'), LD_LIBRARY_PATH='/usr/lib/x86_64-linux-gnu',
               QT_PLUGIN_PATH='/usr/lib/x86_64-linux-gnu/qt6/plugins',
               QML_IMPORT_PATH='/usr/lib/x86_64-linux-gnu/qt6/qml')
    runs = []
    for index in range(2):
        tested = subprocess.run([str(work / 'app')], cwd=work, env=env, text=True, capture_output=True)
        (report / f'run-{index}.log').write_text(tested.stdout + tested.stderr)
        if tested.returncode:
            raise RuntimeError(tested.stdout + tested.stderr)
        runtime = Path(tested.stdout.strip())
        assert runtime.name == bundle['manifest']['sha256']
        runs.append(dict(runtime=str(runtime), warm_cache=bool(index)))
    receipt = dict(passed=True, qt='6.12.0', bundled_files=bundle['manifest'], runs=runs,
                   ordinary_bend_compile=True, system_qt_search_path_ignored=True,
                   native_root=str(work), preload_order=order,
                   boundary='Actual bundled QtCore/ICU; GUI/QML/plugins, licensing/source release artifacts and the full generated package remain separate checks')
    (report / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('QT_BUNDLED_CORE_OK qt=6.12.0 stock_bend=1 foreign_system_qt=1 cold_and_warm=1')


if __name__ == '__main__':
    main()
