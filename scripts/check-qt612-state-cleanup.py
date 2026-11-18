#!/usr/bin/env python3
"""Verify native converter cleanup through fresh Hub imports and stock Bend."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
from backend import command, compile_backend, validate_backend
from generate import Generator
from lifetime import cpp_tables, evaluate_tables
from upstream import prepare
import aggregate_fields
import callbacks
import native_objects
import representations
import public_records

FIXTURE = """
static bool cleanup_test_fail;
static unsigned cleanup_test_hits, cleanup_foreign_hits, cleanup_holder_count;
static void cleanup_foreign(QStringConverterBase::State *) noexcept { ++cleanup_foreign_hits; }
"""

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    cache = Path.home() / '.cache/bend-qt-generator'
    parser.add_argument('--qt-root', type=Path, default=cache / 'Qt/6.12.0/gcc_64')
    parser.add_argument('--work', type=Path, default=ROOT / 'build/state-cleanup')
    parser.add_argument('--model-work', type=Path, default=ROOT / 'build/qt612',
                        help='Maintainer extraction directory containing api.json and its saved native traits')
    parser.add_argument('--runtime-only', action='store_true')
    parser.add_argument('--syntax-only', action='store_true')
    parser.add_argument('--emit-only', action='store_true')
    parser.add_argument('--records', action='store_true')
    parser.add_argument('--only', action='append')
    parser.add_argument('--trace', action='store_true')
    args = parser.parse_args()
    work = args.work; work.mkdir(parents=True, exist_ok=True)
    programs = [('state-cleanup', (ROOT / 'scripts/fixtures/state-cleanup.bend').read_text(), 'QT612_STATE_CLEANUP_OK')]
    if not args.runtime_only:
        profile = json.loads((ROOT / 'generator/qt612-core/profile.json').read_text())
        profile['qt_modules'] = ['QtCore', 'QtGui', 'QtWidgets']
        headers, system, modules, env, _ = prepare(cache / 'pyside-setup', args.qt_root, profile['qt_modules'], work)
        profile['qt_modules'] = modules
        api = json.loads((args.model_work / 'api.json').read_text())
        api['classes'] = [c for c in api['classes'] if c.get('package', '').removeprefix('PySide6.') in modules and '/rhi/' not in c.get('source_file', '')]
        # Namespace-level enums belong to modules too; keep only the selected ones.
        api['enums'] = [e for e in api.get('enums', []) if e.get('package', '').removeprefix('PySide6.') in modules]
        api['global_functions'] = []
        traits = native_objects.saved_traits(args.model_work)
        for c in api['classes']:
            if c['name'] in traits:
                c.update(traits[c['name']]); c['native_copyable'] = traits[c['name']]['copyable']; c['native_movable'] = traits[c['name']]['movable']
            c['generate'] = c['generate'] and c.get('package', '').removeprefix('PySide6.') in modules
        g = Generator(api, profile); g.collect()
        needed = set(re.findall(r'Qt\.([A-Za-z0-9_.]+)', '\n'.join(source for _, source, _ in programs)))
        (work / 'methods.json').write_text(json.dumps([m['bend_name'] for m in g.methods],indent=2))
        g.methods = [m for m in g.methods if m['bend_name'] in needed or m['function']['declaring_class'] == 'QStringConverterBase::State']
        callbacks.prepare(g)
        g.callback_classes, g.callback_methods, g.callback_qml = [], {}, False
        g.callback_functions = []
        state=dict(kind='object',name='QStringConverterBase::State',bend='QStringConverterBase.State',raw='U32')
        unit=dict(kind='void',bend='Unit',raw='Unit'); word=dict(kind='u32',bend='U32',raw='U32')
        sid=g.ids['QStringConverterBase::State']
        for public, params, ret, body in [
            ('Fixture.hit', [], unit, '++cleanup_test_hits;'),
            ('Fixture.hits', [], word, 'r->result.word=cleanup_test_hits;'),
            ('Fixture.holders', [], word, 'r->result.word=cleanup_holder_count;'),
            ('Fixture.foreignHits', [], word, 'r->result.word=cleanup_foreign_hits;'),
            ('Fixture.failNext', [], unit, 'cleanup_test_fail=true;'),
            ('Fixture.nonempty', [('state',state)], unit,
             f'NativeCallScope scope; auto *state=get<QStringConverterBase::State>(r,r->arguments[0].word,{sid},false,true); if(r->error)return true; state->state_data[0]=23;'),
            ('Fixture.foreign', [('state',state)], unit,
             f'NativeCallScope scope; auto *state=get<QStringConverterBase::State>(r,r->arguments[0].word,{sid},false,true); if(r->error)return true; state->clearFn=cleanup_foreign;'),
            # Qt clears the state on another thread while the main thread
            # runs an event loop, so the handler can run there.
            ('Fixture.clearOnOtherThread', [('state',state)], unit,
             f'NativeCallScope scope; auto *state=get<QStringConverterBase::State>(r,r->arguments[0].word,{sid},false,true); if(r->error)return true; '
             'std::atomic<bool> done{false}; QEventLoop loop; QTimer timer; '
             'QObject::connect(&timer,&QTimer::timeout,&loop,[&]{if(done.load())loop.quit();}); timer.start(1); '
             'std::thread other([&]{state->clear();done.store(true);}); loop.exec();other.join();')]:
            op=g.next_id;g.next_id+=1
            g.emit_effect(public,params,ret,op)
            g.cases.append(f'case {op}: {{\n {body} return true;\n}}')
        bend,effects,dispatch=g.emit()
        holder='~ConverterCleanupHolder() { callback_release_handler(handler); }'
        if dispatch.count(holder)!=1: raise RuntimeError('Cleanup holder destructor changed')
        dispatch=dispatch.replace(holder,'ConverterCleanupHolder(){++cleanup_holder_count;} ~ConverterCleanupHolder() { --cleanup_holder_count; callback_release_handler(handler); }')
        site='auto next=std::make_unique<ConverterCleanupHolder>();'
        if dispatch.count(site)!=1: raise RuntimeError('Cleanup allocation fault site changed')
        dispatch=dispatch.replace(site,'if(cleanup_test_fail){cleanup_test_fail=false;throw std::bad_alloc();} '+site)
        abi = (ROOT / 'generator/templates/abi.h').read_text().replace('@ARGUMENT_CAPACITY@', str(g.argument_capacity))
        aliases = ''.join(f'using {name} = {native};\n' for name, native in api['typedefs'].items() if name in g.ids) + representations.aliases(g)
        prefix, suffix = callbacks.qml_sources(g, args.qt_root, work)
        source_cpp = headers.read_text() + aliases + prefix + FIXTURE + (ROOT / 'generator/templates/runtime.cpp').read_text() + suffix
        for key, value in [('ABI', abi), ('LIFETIME', cpp_tables(evaluate_tables(work))),
                           ('NATIVE_OBJECTS', native_objects.traits(g)), ('DISPATCH', dispatch)]:
            source_cpp = source_cpp.replace('// @' + key + '@', value)
        native = work / 'wrappers.cpp'; native.write_text(source_cpp)
        (work / 'qt.bend').write_text(bend)
        (work / 'cleanup-inventory.json').write_text(json.dumps(__import__('converter_cleanup').inventory(g),indent=2))
        if args.emit_only: print('QT612_STATE_CLEANUP_EMIT_OK'); return
        validate_backend(native, args.qt_root, work, 'clang++-19', modules)
        if args.syntax_only: print('QT612_STATE_CLEANUP_SYNTAX_OK'); return
        assembly, imports, backend = compile_backend(native, args.qt_root, work, 'clang++-19', modules)
        extra = [m for m in modules if m not in ('QtCore', 'QtGui', 'QtWidgets')]
        libraries = [f'    void *libraries[{len(extra) + 1}] = {{lib}};']
        for i, module in enumerate(extra, 1):
            libraries += [f'    libraries[{i}] = dlopen("libQt6{module[2:]}.so.6", RTLD_NOW | RTLD_LOCAL);',
                          f'    if (!libraries[{i}]) return dlerror();']
        effect = (ROOT / 'generator/templates/effects.c').read_text()
        for key, value in [('ABI', abi), ('ASSEMBLY', assembly), ('IMPORTS', imports),
                           ('LIBRARIES', '\n'.join(libraries)), ('EFFECTS', effects)]:
            effect = effect.replace('// @' + key + '@', value)
        (work / 'qt.c').write_text(effect)
    spec = importlib.util.spec_from_file_location('checks', ROOT / 'scripts/check-qt612.py')
    checks = importlib.util.module_from_spec(spec); spec.loader.exec_module(checks)
    if args.only: programs = [item for item in programs if item[0] in args.only]
    receipt = checks.check_package(work, programs, os.environ.copy(), [args.qt_root], work / 'consumer')
    receipt['native_integration_only'] = True
    (work / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')

if __name__ == '__main__': main()
