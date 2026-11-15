"""Owning carrier types discovered from extracted Qt template signatures."""
import re


def shared_name(t):
    return 'Shared_' + re.sub(r'[^A-Za-z0-9_]', '_', t['cpp'].removeprefix('const ').replace('&', '').strip()[len('QSharedPointer<'):-1])


def future_name(t):
    return 'Future_' + re.sub(r'[^A-Za-z0-9_]', '_', t['cpp'].removeprefix('const ').replace('&', '').strip()[len('QFuture<'):-1])


def install_shared(classes, selected):
    found = {}

    def package(t):
        packages = set()
        if value := classes.get(t.get('name'), {}).get('package'):
            packages.add(value)
        for child in t.get('instantiations', []):
            if value := package(child):
                packages.add(value)
        return next(iter(packages)) if len(packages) == 1 else None

    def visit(t):
        if t.get('name') == 'QSharedPointer' and not t['pointers'] and len(t.get('instantiations', [])) == 1:
            native = t['cpp'].removeprefix('const ').replace('&', '').strip()
            public = shared_name(t)
            found[public] = {'name': public, 'object': False, 'value': True,
                'qobject': False, 'public_destructor': True, 'abstract': False,
                'copyable': True, 'namespace': False, 'generate': False, 'template': False,
                'bases': [], 'functions': [], 'enums': [], 'adapter': True,
                'shared_cpp': native, 'shared_target': t['instantiations'][0]['name'],
                'package': package(t['instantiations'][0])}
        if (t.get('name') == 'QFuture' and not t['pointers'] and len(t.get('instantiations', [])) == 1
                and t['instantiations'][0]['name'] not in ('T', 'U')):
            native = t['cpp'].removeprefix('const ').replace('&', '').strip()
            public = future_name(t)
            watcher = public.replace('Future_', 'FutureWatcher_', 1)
            common = {'public_destructor': True, 'abstract': False, 'namespace': False,
                'generate': False, 'template': False, 'functions': [], 'enums': [], 'adapter': True,
                'final_cpp': True, 'package': package(t['instantiations'][0])}
            found[public] = dict(common, name=public, object=False, value=True, qobject=False,
                copyable=True, bases=[], future_cpp=native, future_element=t['instantiations'][0],
                future_watcher=watcher)
            found[watcher] = dict(common, name=watcher, object=True, value=False, qobject=True,
                copyable=False, bases=['QObject'], future_watcher_cpp=native.replace('QFuture<', 'QFutureWatcher<', 1))
        for child in t.get('instantiations', []):
            visit(child)
        if t.get('array_element'):
            visit(t['array_element'])

    for c in list(classes.values()):
        for field in c.get('fields', []):
            visit(field['type'])
        for f in c['functions']:
            visit(f['return'])
            for argument in f['arguments']:
                visit(argument['type'])
    classes.update(found)
    selected.extend(name for name in found if name not in selected)
    selected.sort()


def aliases(g, inside=False):
    import qtest_values
    import typed_views
    import gl_sync
    import native_interop
    import gl_retained
    import byte_iterators
    import meta_storage
    import touch_sequences
    def alias(name, native):
        namespace, _, local = name.rpartition('::')
        return (f'namespace {namespace} {{ using {local} = {native}; }}\n' if namespace
                else f'using {name} = {native};\n')
    return ('' if inside else qtest_values.includes(g) + touch_sequences.includes(g)) + byte_iterators.aliases(g, inside) + gl_retained.aliases(g, inside) + meta_storage.aliases(g, inside) + typed_views.aliases(g, inside) + gl_sync.aliases(g, inside) + native_interop.aliases(g, inside) + ''.join(alias(name, native)
                   for name in g.selected
                   for native in [g.classes[name].get('shared_cpp') or g.classes[name].get('future_cpp')
                                  or g.classes[name].get('future_watcher_cpp')]
                   if native)
