"""Generate the bundled runtime's absolute-path ELF loader.

Only linked Qt dependencies are preloaded. Optional FFmpeg/OpenSSL backends
keep Qt's normal lazy resolver behavior. Qt libraries already loaded from a
different installation are rejected before their symbols can be mixed.
"""
import json
from pathlib import Path

from runtime_bundle import relative_path


def module_paths(selection, modules):
    files, aliases = selection['files'], selection['aliases']
    libraries = []
    for module in modules:
        alias = 'lib/lib' + module.replace('Qt', 'Qt6', 1) + '.so.6'
        target = aliases.get(alias, alias)
        if target not in files:
            raise ValueError('The runtime does not contain the selected module: ' + module)
        libraries.append(target)
    return libraries


def linked_preloads(selection, modules):
    """Preload retained binding modules and their actual bundled dependencies.

    Platform helpers and other installed libraries remain available for Qt's
    normal plugin loading without imposing their host dependencies at startup.
    """
    needed, pending = set(), module_paths(selection, modules)
    while pending:
        name = pending.pop()
        if name in needed:
            continue
        if name not in selection['dependencies']:
            raise ValueError('Missing runtime dependency inventory: ' + name)
        needed.add(name)
        pending.extend(selection['dependencies'][name])
    return [name for name in selection['preload_order'] if name in needed]


def loader(selection, modules, *, preload_modules=None):
    libraries = module_paths(selection, modules)
    order = linked_preloads(selection, modules if preload_modules is None else preload_modules)
    for name in [*order, *libraries]:
        relative_path(name)
    paths = '\n'.join('    ' + json.dumps(name) + ',' for name in order)
    linked = '\n'.join('    ' + json.dumps(name) + ',' for name in libraries)
    template = Path(__file__).with_name('templates').joinpath('runtime_deployment.c').read_text()
    return template.replace('// @PRELOAD@', paths).replace('// @MODULES@', linked)
