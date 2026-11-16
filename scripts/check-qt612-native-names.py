#!/usr/bin/env python3
"""Native pointer identities and stable QML/plugin/area-monitor names."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
from backend import command, compile_backend
from generate import Generator
from lifetime import cpp_tables, evaluate_tables
from upstream import prepare
import callbacks
import native_objects
import representations
import qobject_interfaces
import qio_pipe
import effect_transport

PROGRAM = '''import Base
import ../../packages/qt612/qt.bend as Qt

def finished(ok: Bool) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.lift(Unit, IO.print("QT612_NATIVE_NAMES_OK address=1 plugins=1 retained=1 nul=1 monitor=1 cleanup=1"))
    case False{}: Qt.Action.fail(Unit, 1, "Native-name fixture leaked handles")

def demo() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Fixture.check()
    objects: U32 <- Qt.Runtime.liveObjects()
    finished(U32.is_eq(objects, 0))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, demo()))
'''


def add_fixture(g, bend, effects, dispatch):
    def selected(owner, method, contains=None):
        candidates = [m for m in g.methods if m['class'] == owner and m['function']['name'] == method
                      and (contains is None or contains in m['function']['minimal_signature'])]
        assert len(candidates) == 1, [(m['bend_name'], m['function']['minimal_signature']) for m in candidates]
        return 'bqt_op_' + str(candidates[0]['operation'])
    
    ops = {
        'STREAM': selected('QTextStream', 'operator<<', 'const void*'),
        'HELP': selected('QHelpGlobal', 'uniquifyConnectionName'),
        'COMPARE': selected('QTest', 'compare_ptr_helper', 'const volatile void*,const volatile void*'),
        'REGISTER': selected('QQmlTypesExtensionInterface', 'registerTypes'),
        'ENGINE': selected('QQmlExtensionInterface', 'initializeEngine'),
        'MONITOR': selected('QGeoAreaMonitorSource', 'requestUpdate'),
    }
    body = (ROOT / 'scripts/fixtures/native-names.inc').read_text()
    for key, value in {**ops, **g.ids}.items():
        body = body.replace('@' + key + '@', str(value))
    old_dispatch = g.dispatch()
    operation = g.next_id; g.next_id += 1
    g.cases.append(f'case {operation}: {{\n' + body + '\n}')
    g.emit_effect('Fixture.check', [], dict(kind='void', bend='Unit', raw='Unit'), operation)
    dispatch = dispatch.removesuffix(old_dispatch) + g.dispatch()
    bend = g.prelude() + '\n'.join(g.bend) + '\n'
    effects = effect_transport.effects(g)
    return bend, effects, dispatch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    cache = Path.home() / '.cache/bend-qt-generator'
    parser.add_argument('--qt-root', type=Path, default=cache / 'Qt/6.12.0/gcc_64')
    parser.add_argument('--extractor', type=Path, default=cache / 'build/bend-qt-extract')
    args = parser.parse_args()
    qt = args.qt_root
    work = ROOT / 'build/qt612/check/native-names'; work.mkdir(parents=True, exist_ok=True)
    profile = json.loads((ROOT / 'generator/qt612-core/profile.json').read_text())
    profile['qt_modules'] += ['QtHelp', 'QtPositioning', 'QtTest']
    headers, system, modules, env, _ = prepare(cache / 'pyside-setup', qt, profile['qt_modules'], work)
    profile['qt_modules'] = modules
    logs = work / 'extractor'; logs.mkdir(exist_ok=True)
    extracted = command([args.extractor, headers, system, work / 'api.json', logs,
                         qt / 'include', qt / 'mkspecs/linux-g++', *[qt / 'include' / m for m in modules]], env=env)
    (work / 'extraction.log').write_text(extracted.stdout + extracted.stderr)
    api = json.loads((work / 'api.json').read_text())
    qobject_interfaces.restore(api, work)
    qio_pipe.restore(api, work)
    native_objects.refine_traits(api, qt, modules, work, 'clang++-19')
    g = Generator(api, profile); g.collect()
    pairs = {('QTextStream', 'operator<<'), ('QHelpGlobal', 'uniquifyConnectionName'),
             ('QTest', 'compare_ptr_helper'), ('QQmlExtensionInterface', 'initializeEngine'),
             ('QQmlTypesExtensionInterface', 'registerTypes'), ('QGeoAreaMonitorSource', 'requestUpdate')}
    g.methods = [m for m in g.methods if (m['class'], m['function']['name']) in pairs]
    callbacks.prepare(g)
    g.callback_classes = []; g.callback_methods = {}; g.callback_functions = []; g.callback_qml = False
    bend, effects, dispatch = g.emit()
    bend, effects, dispatch = add_fixture(g, bend, effects, dispatch)
    abi = (ROOT / 'generator/templates/abi.h').read_text().replace('@ARGUMENT_CAPACITY@', str(g.argument_capacity))
    aliases = ''.join(f'using {name} = {native};\n' for name, native in api['typedefs'].items() if name in g.ids) + representations.aliases(g)
    prefix, suffix = callbacks.qml_sources(g, qt, work)
    source = headers.read_text() + aliases + prefix + (ROOT / 'generator/templates/runtime.cpp').read_text() + suffix
    source = source.replace('// @ABI@', abi).replace('// @LIFETIME@', cpp_tables(evaluate_tables(work)))
    source = source.replace('// @NATIVE_OBJECTS@', native_objects.traits(g)).replace('// @DISPATCH@', dispatch)
    native = work / 'wrappers.cpp'; native.write_text(source)
    payload, loader, metadata = compile_backend(native, qt, work, 'clang++-19', modules)
    extra = [m for m in modules if m not in ('QtCore', 'QtGui', 'QtWidgets')]
    libraries = [f'    void *libraries[{len(extra) + 1}] = {{lib}};']
    for i, module in enumerate(extra, 1):
        libraries += [f'    libraries[{i}] = dlopen("libQt6{module[2:]}.so.6", RTLD_NOW | RTLD_LOCAL);', f'    if (!libraries[{i}]) return dlerror();']
    c = (ROOT / 'generator/templates/effects.c').read_text()
    for key, value in [('ABI', abi), ('ASSEMBLY', payload), ('IMPORTS', loader), ('LIBRARIES', '\n'.join(libraries)), ('EFFECTS', effects)]:
        c = c.replace('// @' + key + '@', value)
    (work / 'qt.bend').write_text(bend); (work / 'qt.c').write_text(c)
    spec = importlib.util.spec_from_file_location('checks', ROOT / 'scripts/check-qt612.py')
    checks = importlib.util.module_from_spec(spec); spec.loader.exec_module(checks)
    receipt = checks.check_package(work, [('native-names', PROGRAM, 'QT612_NATIVE_NAMES_OK')], os.environ.copy(), [qt], work / 'consumer', jobs=1)
    receipt['native_payload'] = metadata['payload']
    (work / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    main()
