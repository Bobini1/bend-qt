"""Bend declarations for owning Qt/QML record values."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
WIRE = dict(kind='wire', bend='Wire', raw='Wire', codec='WireIdentity')
WORD = dict(kind='u32', bend='U32', raw='U32')
TEXT = dict(kind='string', bend='String', raw='String')


def emit(g):
    if not hasattr(g, 'generic_variant_operations'):
        return
    g.value_type_operations = {}
    for name, parameters, result in [
        ('create', [('schema', WIRE), ('values', WIRE), ('mode', WORD)], WORD),
        ('get', [('schema', WIRE), ('self', WORD), ('field', WIRE)], WIRE),
        ('updated', [('schema', WIRE), ('self', WORD), ('field', WIRE), ('value', WIRE)], WORD),
        ('register', [('schema', WIRE), ('uri', TEXT), ('major', WORD), ('minor', WORD), ('name', TEXT)], WORD),
    ]:
        operation = g.next_id; g.next_id += 1
        g.value_type_operations[name] = operation
        g.cases.append(f'case {operation}: {{\n    return RuntimeValueTypes::{name if name != "register" else "register_qml"}(r);\n}}')
        g.emit_effect('Internal.ValueType.' + name, parameters, result, operation)
    g.bend.append((HERE / 'templates/value_types.bend').read_text())


def cpp(g):
    if not hasattr(g, 'value_type_operations'):
        return ''
    source = (HERE / 'templates/value_type_api.cpp').read_text().replace(
        '@VARIANT_ID@', str(g.ids['QVariant'])).replace('@HAS_QML@', '1' if 'QtQml' in g.profile['qt_modules'] else '0')
    import re
    import runtime_dispatch
    names = ('ensure', 'argument_type', 'meta_type', 'store', 'read_value', 'write_value',
             'assign_value', 'create', 'field_index', 'get', 'updated', 'register_qml')
    # Explicit free functions are separate native units. Changes to a property
    # operation no longer force every native signal codec to rebuild its body.
    # Match balanced braces; signatures and names are fixed maintainer inputs.
    for name in names:
        match = re.search(r'^static [^\n]+\b' + name + r'\([^\n]+\) \{\n', source, re.M)
        if not match:
            raise ValueError('Value operation signature changed: ' + name)
        begin = match.start(); opening = match.end() - 2; depth = 0; end = None
        tokens = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*.*?\*/|[{}]', re.S)
        for token in tokens.finditer(source, opening):
            if token[0] == '{': depth += 1
            elif token[0] == '}':
                depth -= 1
                if not depth: end = token.end(); break
        if end is None:
            raise ValueError('Unterminated value operation: ' + name)
        source = source[:begin] + '// BQT_RUNTIME_BODY_BEGIN ' + name + '\n' + source[begin:end] + '\n// BQT_RUNTIME_BODY_END ' + name + '\n' + source[end + 1:]
    return runtime_dispatch.cpp(source, hubs={name: ('value_type_runtime', index, 'RuntimeValueTypes')
                                            for index, name in enumerate(names)})


def declarations():
    return '''namespace RuntimeValueTypes {
extern __attribute__((visibility("hidden"))) int argument_type(BqtRequest *, const QByteArray &, const BqtValue *);
static bool is_code(int);
extern __attribute__((visibility("hidden"))) QMetaType meta_type(int);
extern __attribute__((visibility("hidden"))) QVariant read_value(BqtRequest *, int, const BqtValue &);
extern __attribute__((visibility("hidden"))) BqtValue write_value(BqtRequest *, int, const void *);
extern __attribute__((visibility("hidden"))) bool assign_value(BqtRequest *, int, void *, const void *);
}
'''


def inventory(g):
    return dict(available=hasattr(g, 'value_type_operations'), operations=getattr(g, 'value_type_operations', {}),
                storage='Owning reflected gadgets and distinct per-schema typed sequences',
                boundary='Declared fields; default-constructible, copyable native field types; no gadget inheritance or arbitrary member functions')
