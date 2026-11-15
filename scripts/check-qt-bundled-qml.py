#!/usr/bin/env python3
"""Render QML through the bundled loader using ordinary stock Bend.

This focused test deliberately inventories only its fixture's dependencies.
It does not replace the release's complete license/source deployment audit.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
from qt_licenses import Inventory
from runtime_bundle import embed
from runtime_deployment import loader
from runtime_selection import elf_dependencies


def run(command, **kwargs):
    result = subprocess.run([str(x) for x in command], text=True, capture_output=True, **kwargs)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qt-root', type=Path, default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    parser.add_argument('--icu-notice', type=Path, required=True)
    parser.add_argument('--bindings-work', type=Path, help='Also package a freshly generated value-types fixture and run its Hub consumer')
    parser.add_argument('--work', type=Path, default=ROOT / 'build/bundled-qml-check')
    parser.add_argument('--native-work', type=Path, default=Path.home() / '.cache/bend-qt-generator/bundled-qml-check')
    args = parser.parse_args()
    qt, report, work = args.qt_root.resolve(), args.work.resolve(), args.native_work.resolve()
    report.mkdir(parents=True, exist_ok=True); work.mkdir(parents=True, exist_ok=True)
    (report / 'receipt.json').write_text(json.dumps(dict(passed=False, stage='bundled Qt/QML deployment')) + '\n')
    inventory = Inventory(qt); files, aliases, order, visited = {}, {}, [], set()
    dependencies = {}

    def visit(path):
        real = path.resolve()
        if real in visited:
            return
        visited.add(real)
        relative = real.relative_to(qt).as_posix()
        if real.name.startswith('libicu'):
            assert real.name in {'libicudata.so.73.2', 'libicui18n.so.73.2', 'libicuuc.so.73.2'}, real
        else:
            inventory.binary(path, 'lgpl')
        dependencies[relative] = []
        for needed in elf_dependencies(real):
            if (qt / 'lib' / needed).is_file():
                dependencies[relative].append((qt / 'lib' / needed).resolve().relative_to(qt).as_posix())
                visit(qt / 'lib' / needed)
        files[relative] = real
        if relative.startswith('lib/'):
            order.append(relative)

    modules = ['QtWidgets', 'QtQuick', 'QtQml']
    for module in modules:
        visit(qt / 'lib' / ('lib' + module.replace('Qt', 'Qt6', 1) + '.so.6'))
    visit(qt / 'plugins/platforms/libqoffscreen.so')
    qml_files = [*(qt / 'qml/QtQml').rglob('*'), *(qt / 'qml/QtQuick/Window').rglob('*'),
                 *(qt / 'qml/QtQuick').glob('*')]
    for path in qml_files:
        if path.is_file():
            if path.suffix == '.so':
                visit(path)
            else:
                files[path.relative_to(qt).as_posix()] = path
    for path in (qt / 'lib').glob('*.so*'):
        if path.is_symlink() and path.resolve() in visited:
            aliases[path.relative_to(qt).as_posix()] = path.resolve().relative_to(qt).as_posix()
    files['notices/ICU-LICENSE'] = args.icu_notice
    files['notices/qtbase.spdx.json'] = Path(inventory.modules['QtCore']['evidence'])
    bundle = embed(files, aliases=aliases, context=dict(test='actual QML deployment', qt='6.12.0'))
    selection = dict(files=files, aliases=aliases, preload_order=order, dependencies=dependencies)
    deployment = loader(selection, modules)
    probe = (ROOT / 'generator/templates/runtime_paths.cpp').read_text() + r'''
#include <QtWidgets/QApplication>
#include <QtQml/QQmlEngine>
#include <QtQml/QQmlComponent>
#include <QtQuick/QQuickWindow>
#include <QtCore/QLibraryInfo>
#include <QtCore/QDir>
#include <QtGui/QImage>
#include <thread>
extern "C" const char *probe(const char *root) {
    if (const auto *error=RuntimePaths::configure(root)) return error;
    int argc=1; char arg[]="bend-bundled-qml"; char *argv[]={arg,nullptr};
    QApplication app(argc,argv);
    if (QString::fromUtf8(root)!=QLibraryInfo::path(QLibraryInfo::PrefixPath)) return "Qt prefix escaped the bundle";
    QCoreApplication::setLibraryPaths({QString::fromUtf8(root)+"/plugins"});
    QQmlEngine engine;
    for (const auto &path : engine.importPathList())
        if (path.startsWith("/home/bobini/.cache/bend-qt-generator/Qt/") || path.startsWith("/usr/lib"))
            return "QML default imports escaped the selected runtime";
    QQmlComponent component(&engine);
    component.setData("import QtQuick\nimport QtQuick.Window\nWindow { width: 40; height: 32; visible: true; color: '#123456'; Rectangle { x: 4; y: 4; width: 12; height: 12; color: '#eedd22' } }",QUrl());
    auto object=std::unique_ptr<QObject>(component.create());
    if (!object) { qWarning()<<component.errors(); return "Cannot create the bundled QML window"; }
    auto *window=qobject_cast<QQuickWindow *>(object.get());
    if (!window) return "QML did not create a window";
    for (int i=0;i<40;++i) { app.processEvents(); std::this_thread::sleep_for(std::chrono::milliseconds(5)); }
    auto image=window->grabWindow();
    if (image.isNull()) return "Cannot grab the bundled Qt Quick frame";
    if (image.pixelColor(2,2)!=QColor("#123456") || image.pixelColor(8,8)!=QColor("#eedd22")) return "Bundled Qt Quick rendered the wrong pixels";
    return nullptr;
}
'''
    (work / 'probe.cpp').write_text(probe)
    needed = ['QtWidgets', 'QtQuick', 'QtQml', 'QtQmlMeta', 'QtCore', 'QtGui']
    command = ['clang++-19', '-std=c++17', '-shared', '-fPIC', '-O1', work / 'probe.cpp', '-o', work / 'probe.so',
               '-I' + str(qt / 'include'), '-L' + str(qt / 'lib')]
    command += ['-l' + module.replace('Qt', 'Qt6', 1) for module in needed]
    (report / 'native.log').write_text(run(command))
    c = bundle['c'] + deployment + '\n' + r'''
static Term bundled_qml_run(Env e, Term *f, IoWork *w) {
    const char *error=bqt_runtime_prepare();
    void *libraries[sizeof bqt_runtime_modules / sizeof *bqt_runtime_modules];
    if(!error)error=bqt_runtime_load_modules(libraries);
    if(!error) {
        void *lib=dlopen("@PROBE@",RTLD_NOW|RTLD_LOCAL);
        if(!lib)error=dlerror();
        else {
            const char *(*probe)(const char *);void *symbol=dlsym(lib,"probe");
            memcpy(&probe,&symbol,sizeof symbol);
            error=probe?probe(bqt_bundle_root):"Missing deployment probe";
            if(!error&&dl_iterate_phdr(bqt_runtime_check_loaded,NULL))error=bqt_runtime_error;
        }
    }
    return error?io_fail(e,ELIBACC,error):io_done(e,io_str(e,bqt_bundle_root,strlen(bqt_bundle_root)));
}
static void __attribute__((constructor)) bundled_qml_register(void) { io_eff(CID(bundled_qml),bundled_qml_run); }
'''.replace('@PROBE@', str(work / 'probe.so'))
    bend = 'import Base\n' + bundle['bend'] + '''
def bundled_qml() -> IO(Result<&1, &1, U32 & String, String>):
  import "./qt.c"
def main() -> IO(Unit):
  do IO<Unit>:
    root: String <- IO.try(String, bundled_qml())
    IO.print(root)
'''
    (work / 'main.bend').write_text(bend); (work / 'qt.c').write_text(c)
    for name, content in bundle['assets'].items():
        (work / name).write_text(content)
    env = dict(os.environ, BEND_NO_TELEMETRY='1', XDG_CACHE_HOME=str(work / 'cache'),
               LD_LIBRARY_PATH='/usr/lib/x86_64-linux-gnu', QT_QPA_PLATFORM='offscreen',
               QT_QUICK_BACKEND='software', QSG_RENDER_LOOP='basic',
               QT_PLUGIN_PATH='/usr/lib/x86_64-linux-gnu/qt6/plugins',
               QML_IMPORT_PATH='/usr/lib/x86_64-linux-gnu/qt6/qml')
    env.pop('BEND_QT_RUNTIME', None); env.pop('BEND_QT_LIBRARY', None)
    cached = work / 'cache/bend-qt' / bundle['manifest']['sha256']
    if cached.exists():
        if not cached.resolve().is_relative_to(work) or cached.is_symlink():
            raise ValueError('The focused test cache escapes its native work directory')
        shutil.rmtree(cached)
    (report / 'compile.log').write_text(run([Path.home() / '.bend/bin/bend', 'main.bend', '-o', 'app'], cwd=work, env=env))
    roots = []
    for index in range(2):
        result = run([work / 'app'], cwd=work, env=env)
        (report / f'run-{index}.log').write_text(result); roots.append(result.strip())
    assert roots[0] == roots[1] and Path(roots[0]).name == bundle['manifest']['sha256']
    replacement = work / 'replacement Qt, custom'
    replacement.mkdir(exist_ok=True)
    shutil.copytree(roots[0], replacement, dirs_exist_ok=True)
    (replacement / 'notices/ICU-LICENSE').write_text('User-managed replacement: bundled-byte hashes are deliberately not enforced.\n')
    modified = work / 'replacement-note.txt'; modified.write_text('User-modified Qt library, with compatible ABI.\n')
    core = replacement / aliases['lib/libQt6Core.so.6']
    before_core = core.read_bytes()
    run(['objcopy', '--add-section', '.bend_qt_replacement=' + str(modified), core])
    assert core.read_bytes() != before_core
    result = run([work / 'app'], cwd=work, env=dict(env, BEND_QT_RUNTIME=str(replacement)))
    assert result.strip() == str(replacement)
    (report / 'replacement.log').write_text(result)
    empty = work / 'incomplete'; empty.mkdir(exist_ok=True)
    negative = subprocess.run([work / 'app'], cwd=work, env=dict(env, BEND_QT_RUNTIME=str(empty)), text=True, capture_output=True)
    assert negative.returncode and 'cannot open shared object' in negative.stderr, negative
    (report / 'incomplete.log').write_text(negative.stdout + negative.stderr)
    system = Path('/usr/lib/x86_64-linux-gnu/libQt6Core.so.6')
    assert system.is_file()
    negative = subprocess.run([work / 'app'], cwd=work, env=dict(env, LD_PRELOAD=str(system)), text=True, capture_output=True)
    assert negative.returncode and 'already loaded' in negative.stderr, negative
    (report / 'foreign-preload.log').write_text(negative.stdout + negative.stderr)
    negative = subprocess.run([work / 'app'], cwd=work, env=dict(env, BEND_QT_LIBRARY=str(system)), text=True, capture_output=True)
    assert negative.returncode and 'BEND_QT_LIBRARY cannot replace' in negative.stderr, negative
    (report / 'single-library-override.log').write_text(negative.stdout + negative.stderr)
    binding_receipt = None
    if args.bindings_work:
        generated = args.bindings_work.resolve()
        inputs = json.loads((generated / 'suite-inputs.json').read_text())
        if inputs['expected_programs'] != ['value-types']:
            raise ValueError('The bundled binding control requires the value-types fixture snapshot')
        if '#define BQT_BUNDLED_RUNTIME_NATIVE 1' not in (generated / 'wrappers.cpp').read_text():
            raise ValueError('Regenerate the native fixture with the runtime path startup')
        fixture_package = work / 'binding-package'; fixture_package.mkdir(exist_ok=True)
        c = (generated / 'qt.c').read_text()
        if c.count('// @RUNTIME@') != 1:
            raise ValueError('The generated fixture is missing its runtime transport insertion point')
        runtime = '#define BQT_BUNDLED_RUNTIME 1\n' + bundle['c'] + loader(selection, inputs['qt_modules'])
        (fixture_package / 'qt.c').write_text(c.replace('// @RUNTIME@', runtime))
        (fixture_package / 'qt.bend').write_text((generated / 'qt.bend').read_text() + '\n' + bundle['bend'])
        for name, content in bundle['assets'].items():
            (fixture_package / name).write_text(content)
        (fixture_package / 'coverage.json').write_text(json.dumps(dict(bundled_runtime=bundle['manifest'],
            boundary='Narrow native deployment fixture, not production coverage')))
        spec = importlib.util.spec_from_file_location('qt_package_check', ROOT / 'scripts/check-qt612.py')
        checker = importlib.util.module_from_spec(spec); spec.loader.exec_module(checker)
        source = (ROOT / 'scripts/fixtures/value-types.bend').read_text()
        binding_receipt = checker.check_package(fixture_package, [('value-types', source, 'QT612_VALUE_TYPES_OK')],
            env, [qt, replacement], report / 'bindings-hub', jobs=1)
        (report / 'bindings-hub-receipt.json').write_text(json.dumps(binding_receipt, indent=2) + '\n')
    (report / 'receipt.json').write_text(json.dumps(dict(passed=True, qt='6.12.0', stock_bend=True,
        rendered_pixel_check=True, qml_plugins=True, cold_and_warm=True, conflicting_system_search_paths=True,
        complete_replacement=True, modified_qt_binary_accepted=True,
        incomplete_replacement_rejected=True, foreign_qt_preload_rejected=True,
        bundle=bundle['manifest'], generated_binding_hub=binding_receipt,
        boundary='Focused Qt Quick deployment; complete release licensing, all modules and generated package validation remain separate'), indent=2) + '\n')
    print('QT_BUNDLED_QML_OK rendered_pixels=1 isolated_paths=1 replacement=1 foreign_qt_rejected=1')


if __name__ == '__main__':
    main()
