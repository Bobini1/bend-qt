"""Typed specialized accessibility interfaces for the native interface_cast hook."""
from pathlib import Path
import re


def install(classes, selected):
    classes['AccessibleFacet'] = dict(name='AccessibleFacet', object=False, value=True, qobject=False,
        public_destructor=True, abstract=False, copyable=True, namespace=False, generate=False,
        template=False, bases=[], functions=[], enums=[], adapter=True)
    selected.append('AccessibleFacet')


def interfaces(g):
    cls = g.classes.get('QAccessibleInterface', {})
    path = Path(cls.get('source_file', ''))
    if not path.is_file():
        return []
    text = path.read_text(errors='replace')
    pattern = r'inline\s+(QAccessible\w+Interface)\s*\*\s*(\w+Interface)\(\)\s*\{[^{}]*interface_cast\(QAccessible::(\w+)\)'
    return [(native, getter, kind) for native, getter, kind in re.findall(pattern, text) if native in g.ids]


def result(g, f):
    if (f['declaring_class'], f['name']) != ('QAccessibleInterface', 'interface_cast'):
        return None
    if not interfaces(g):
        raise ValueError('Accessible specialization mapping requires native inline getter declarations')
    return dict(name='AccessibleFacet', cpp='AccessibleFacet', const=False, pointers=0,
                reference=0, enum=False, flags=False, container=False, instantiations=[])


def emit(g):
    result_type = dict(kind='value', name='AccessibleFacet', bend='AccessibleFacet', raw='U32')
    for native, getter, kind in interfaces(g):
        operation = g.next_id; g.next_id += 1
        g.cases.append(f'''case {operation}: {{
    NativeCallScope scope;
    auto *target = get<{native}>(r, r->arguments[0].word, {g.ids[native]}, false, false);
    if (r->error) return true;
    RetentionBatch retained;
    if (!retained.add(r, 0, 0xb3000001u, r->arguments[0].word, nullptr, false, true)) return true;
    r->result.word = own(r, new AccessibleFacet{{QAccessible::{kind}, r->arguments[0].word, target}}, {g.ids['AccessibleFacet']});
    r->result.owned_handle = r->result.word;
    if (!r->error && !retained.finish(r, r->result.word, true)) return true;
    return true;
}}''')
        g.emit_effect('AccessibleFacet.from' + kind, [('interface', dict(kind='object', name=native, bend=native, raw='U32'))], result_type, operation)
    operation = g.next_id; g.next_id += 1
    g.cases.append(f'''case {operation}: {{
    r->result.word = own(r, new AccessibleFacet{{-1, 0, nullptr}}, {g.ids['AccessibleFacet']});
    r->result.owned_handle = r->result.word;
    return true;
}}''')
    g.emit_effect('AccessibleFacet.none', [], result_type, operation)


def decode(g):
    return ['        struct Reply { int kind; void *pointer = nullptr; };',
            '        Reply result{int(a0)};',
            '        auto decode = [](BqtRequest *r, const BqtValue &wire, void *destination) {',
            '            if (!wire_shape(r, wire, 0)) return false;',
            f'            auto *facet = bendqt::get<::bendqt::AccessibleFacet>(r, wire.word, {g.ids["AccessibleFacet"]}, false, false);',
            '            if (r->error) return false;',
            '            auto *reply = static_cast<Reply *>(destination);',
            '            if (facet->kind == -1 && !facet->target) return true;',
            '            if (facet->kind != reply->kind) { fail(r, EINVAL, "Accessible facet does not match the requested native interface"); return false; }',
            '            RetentionBatch retained;',
            '            if (!callback_prepare_retained(r, facet->target, retained) || !retained.finish(r)) return false;',
            '            reply->pointer = facet->pointer;',
            '            return true;', '        };']


def annotate(g):
    mapping = interfaces(g)
    for item in g.excluded:
        if not item['class'].startswith('QAccessible') or not item['signature'].startswith('interface_cast('):
            continue
        alternatives = item.setdefault('alternatives', [])
        for native, getter, kind in mapping:
            for method in g.methods:
                if method['class'] == item['class'] and method['function']['name'] == getter:
                    value = dict(bend_name=method['bend_name'], contract='typed_accessible_interface_getter',
                                 reason='Native inline getter invokes interface_cast for ' + kind)
                    if value not in alternatives: alternatives.append(value)
        for method in getattr(g, 'callback_methods', {}).values():
            if method['function']['declaring_class'] == 'QAccessibleInterface' and method['function']['name'] == 'interface_cast':
                value = dict(bend_name=method['public'] + '.handle', contract='typed_accessible_facet_override',
                    reason='Returns an AccessibleFacet validated against the requested kind, with specialized interface lifetime retained by the proxy')
                if value not in alternatives: alternatives.append(value)
