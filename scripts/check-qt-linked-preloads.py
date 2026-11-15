#!/usr/bin/env python3
"""Check the production loader with real QtCore and optional ELF dependencies."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
from runtime_deployment import loader, linked_preloads
from runtime_selection import elf_dependencies
from qt_targets import installed_version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qt-root', type=Path, default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    parser.add_argument('--work', type=Path, default=ROOT / 'build/linked-preloads')
    args = parser.parse_args()
    qt, work = args.qt_root.resolve(), args.work.resolve()
    prefix = work / 'runtime'
    lib = prefix / 'lib'
    lib.mkdir(parents=True, exist_ok=True)
    files, aliases, dependencies, order = {}, {}, {}, []

    def visit(path):
        real = path.resolve()
        name = real.relative_to(qt).as_posix()
        if name in files:
            return
        files[name] = True
        dependencies[name] = []
        for needed in elf_dependencies(real):
            target = qt / 'lib' / needed
            if target.is_file():
                dependencies[name].append(target.resolve().relative_to(qt).as_posix())
                visit(target)
        shutil.copyfile(real, prefix / name)
        order.append(name)

    visit(qt / 'lib/libQt6Core.so.6')
    for path in (qt / 'lib').glob('*.so*'):
        target = path.resolve().relative_to(qt).as_posix()
        if path.is_symlink() and target in files:
            name = path.relative_to(qt).as_posix()
            aliases[name] = target
            link = prefix / name
            if not link.is_symlink():
                link.symlink_to(Path(target).name)

    def library(name, source, extra=()):
        path = work / (name + '.c')
        path.write_text(source)
        destination = lib / ('lib' + name + '.so.6')
        subprocess.run(['cc', '-shared', '-fPIC', str(path), '-Wl,-soname,' + destination.name,
                        *extra, '-o', str(destination)], check=True)
        return destination

    helper = library('Qt6FixtureHelper', 'int fixture_helper(void) { return 23; }')
    root = library('Qt6FixtureRoot', 'extern int fixture_helper(void); int fixture_root(void) { return fixture_helper(); }', [str(helper)])
    missing = library('BendFixtureMissing', 'int fixture_missing(void) { return 1; }')
    poison = library('Qt6Unused', 'extern int fixture_missing(void); int fixture_poison(void) { return fixture_missing(); }', [str(missing)])
    missing.unlink()
    for path, deps in ((helper, []), (root, ['lib/' + helper.name]), (poison, [])):
        name = 'lib/' + path.name
        files[name] = True
        dependencies[name] = deps
        order.append(name)
    selection = dict(files=files, aliases=aliases, dependencies=dependencies, preload_order=order)
    roots = ['QtCore', 'QtFixtureRoot']
    wanted = linked_preloads(selection, roots)
    assert 'lib/' + helper.name in wanted
    assert 'lib/' + poison.name not in wanted

    preamble = '''#define _GNU_SOURCE
#include <dlfcn.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static const char *bqt_bundle_root = @PREFIX@;
static const char *bqt_bundle_materialize(void) { return NULL; }
static int bqt_bundle_contains(const char *name) {
    return !getenv("EXCLUDE_OPTIONAL") || strcmp(name, "lib/libQt6Unused.so.6");
}
'''.replace('@PREFIX@', json.dumps(str(prefix)))
    main_source = '''
int main(void) {
    const char *error = bqt_runtime_prepare();
    void *libraries[2];
    if (!error) error = bqt_runtime_load_modules(libraries);
    if (error) { fprintf(stderr, "%s\\n", error); return 79; }
    const char *(*version)(void) = dlsym(libraries[0], "qVersion");
    int (*value)(void) = dlsym(libraries[1], "fixture_root");
    if (!version || strcmp(version(), @VERSION@) || !value || value() != 23) return 1;
    if (dlopen("libQt6Unused.so.6", RTLD_NOW | RTLD_NOLOAD)) return 2;
    puts("QT_LINKED_PRELOADS_OK real_qt=1 transitive_dependency=1 unused_library_omitted=1");
}
'''.replace('@VERSION@', json.dumps(installed_version(qt)))
    env = dict(os.environ, LD_LIBRARY_PATH='/usr/lib/x86_64-linux-gnu')
    for key in ('BEND_QT_LIBRARY', 'BEND_QT_RUNTIME', 'LD_PRELOAD', 'EXCLUDE_OPTIONAL'):
        env.pop(key, None)
    runs = []
    for optional in (False, True):
        path = work / ('optional.c' if optional else 'linked.c')
        path.write_text(preamble + loader(selection, roots, preload_modules=roots + (['QtUnused'] if optional else [])) + main_source)
        executable = path.with_suffix('')
        subprocess.run(['cc', str(path), '-ldl', '-o', str(executable)], check=True)
        cases = [(False, 0)] if not optional else [(True, 0), (False, 79)]
        for excluded, expected in cases:
            environment = dict(env, EXCLUDE_OPTIONAL='1') if excluded else env
            result = subprocess.run([str(executable)], env=environment, text=True, capture_output=True)
            assert result.returncode == expected, result.stdout + result.stderr
            if expected:
                assert missing.name in result.stderr, result.stderr
            else:
                assert 'QT_LINKED_PRELOADS_OK' in result.stdout
            runs.append(dict(optional_root=optional, optional_excluded=excluded, exit_code=result.returncode))
    (work / 'receipt.json').write_text(json.dumps(dict(passed=True, qt=installed_version(qt),
        actual_qtcore_and_icu=True, actual_transitive_elf_dependency=True,
        unused_library_with_missing_host_dependency=True, retained_optional_failure_is_strict=True,
        runs=runs), indent=2) + '\n')
    print('QT_LINKED_PRELOADS_OK real_qt=1 transitive_dependency=1 optional_retention=1 strict_missing_dependency=1')


if __name__ == '__main__':
    main()
