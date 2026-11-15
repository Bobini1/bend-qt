"""Public names of callback families, without method id hashes.

Native code identifies each virtual method by a numeric id; the Bend
namespaces carry none. Families are named by `overload_names.assign_family`
and pinned in the same name lock as ordinary entries:

* `Owner.Virtual.method` for virtual overrides (`.handle` installs a Bend
  handler), including device, sampled-image and icon-hook adapters;
* `Owner.Handler.method` for the function a method stores;
* `Owner.methodWithHandler` for methods taking such a function;
* `Owner.newOverride` for proxy constructors. The zero-argument form is the
  default constructor (or the first constructor whose arguments all have
  native defaults); the others are named by their Bend arguments.
"""
import re

import overload_names
import native_operators
from callbacks import bend_ident, ident

FAMILY_PATTERN = re.compile(r'(.+)\.(Virtual|Handler)\.(\w+?)_(\d+)')
FAMILY_KEYS = {'Virtual': 'virtual', 'Handler': 'handler'}


def _owner(method, bend_owner):
    f = method['function']
    for candidate in (method.get('owner'), f.get('declaring_class'), 'QIconEngine' if method.get('icon_hook') else None):
        if candidate and bend_ident(candidate) == bend_owner:
            return candidate
    raise ValueError(f'Cannot identify the C++ owner of callback {method["public"]}')


def _method_entries(g):
    entries = {}
    for method in g.callback_methods.values():
        match = FAMILY_PATTERN.fullmatch(method['public'])
        if not match:
            if re.search(r'_\d{5,}(\.|$)', method['public']):
                raise ValueError(f'Unrecognized hashed callback name: {method["public"]}')
            continue
        bend_owner, family, base, _ = match.groups()
        f = method['function']
        entries[method['public']] = dict(
            owner=_owner(method, bend_owner), base=family + '.' + base,
            key=FAMILY_KEYS[family] + ' ' + f['minimal_signature'],
            inputs=tuple(t['bend'] for t in method['args']), result=method['result']['bend'],
            # Function callbacks rewrite their signature; native parameter
            # spelling is not a stable disambiguator for them.
            cpp=None if family == 'Handler' else [a['type'] for a in f['arguments']])
    return entries


def _function_entries(g):
    entries = []
    for item in getattr(g, 'callback_functions', []):
        original = item['function']
        position = item['callback_position']
        entries.append((item, dict(
            owner=item['owner'], base=ident(original['name']) + 'WithHandler',
            key='with-handler ' + original['minimal_signature'],
            inputs=tuple(t['bend'] for t in item['forward']), result=item['return_']['bend'],
            cpp=[a['type'] for i, a in enumerate(original['arguments']) if i != position])))
    return entries


def _override_entries(g):
    entries = []
    for c in g.callback_classes:
        name = c['name']
        constructors = c['constructors']
        # One zero-argument factory: an actual default constructor if there
        # is one, otherwise the first constructor with only native defaults.
        default = next((x for x in constructors if not x['args']), None) or next((x for x in constructors if x['default']), None)
        for constructor in constructors:
            constructor['override_variants'] = []
            f = constructor['function']
            if constructor is default:
                entries.append((constructor, [], dict(owner=name, base='newOverride', key='override /0',
                                inputs=(), result=bend_ident(name), cpp=[])))
            if constructor['args'] or constructor is not default:
                entries.append((constructor, constructor['args'], dict(
                    owner=name, base='newOverride', key='override ' + f['minimal_signature'],
                    inputs=tuple(t['bend'] for t in constructor['args']), result=bend_ident(name),
                    cpp=[a['type'] for a in f['arguments']])))
    return entries


def assign(g):
    """Rename callback families after callbacks.prepare built them."""
    methods = _method_entries(g)
    functions = _function_entries(g)
    overrides = _override_entries(g)
    signal_types = [(method, dict(owner=method['class'],
                     base='connect_' + ident(method['function']['name']) + 'With',
                     key='signal-with-type ' + native_operators.identity(method['function']),
                     inputs=tuple(t['bend'] for t in method['signal']['args']), result='Connection',
                     cpp=[a['type'] for a in method['function']['arguments']]))
                    for method in g.methods if method['function']['signal']]
    import qt_objects
    eligible = {c['name'] for c in g.callback_classes if qt_objects.eligible(g, c)}
    schemas = [(constructor, entry, dict(entry, base='newAs',
                key=entry['key'].replace('override ', 'schema-constructor ', 1),
                result='QtObject.Instance(schema)'))
               for constructor, _, entry in overrides if entry['owner'] in eligible]
    overload_names.assign_family(g, g.name_lock, list(methods.values()) + [e for _, e in functions]
                                + [e for _, _, e in overrides] + [e for _, _, e in schemas] + [e for _, e in signal_types])
    for method, entry in signal_types:
        method['connection_type_name'] = entry['name']
    rename = {old: e['name'] for old, e in methods.items()}
    rename.update({item['public']: e['name'] for item, e in functions})
    for constructor, inputs, e in overrides:
        constructor['override_variants'].append((inputs, e['name'][len(bend_ident(e['owner'])):]))
    for constructor, original, schema in schemas:
        constructor.setdefault('schema_names', {})[original['name']] = schema['name']

    def update(d):
        if isinstance(d, dict) and d.get('public') in rename:
            d['public'] = rename[d['public']]
    for method in g.callback_methods.values():
        update(method)
    for c in g.callback_classes:
        for method in c['virtuals']:
            update(method)
    for item in getattr(g, 'callback_functions', []):
        update(item)
        update(item['method'])
    g.callback_renames = rename
