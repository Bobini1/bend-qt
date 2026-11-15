"""Authored QQmlListProperty views with typed elements and native callbacks."""
from pathlib import Path
from module_partitions import argument_entries
import abi_cohorts
import effect_transport

HERE = Path(__file__).resolve().parent
WIRE = dict(kind='wire', bend='Wire', raw='Wire', codec='WireIdentity')
WORD = dict(kind='u32', bend='U32', raw='U32')
UNIT = dict(kind='void', bend='Unit', raw='Unit')
OBJECT = dict(kind='object', name='QObject', bend='QObject', raw='U32')


def emit(g):
    if not g.callback_qml or not hasattr(g, 'custom_signal_arguments'):
        return
    g.qml_list_property_operations = {}
    operation = g.next_id; g.next_id += 1
    g.qml_list_property_operations['operate'] = operation
    g.cases.append(f'case {operation}: {{\n    return BendQmlLists::operation(r);\n}}')
    g.emit_effect('Internal.ListProperty.operate', [('self', OBJECT), ('property', WIRE),
        ('kind', WORD), ('storage', WORD), ('index', WIRE), ('value', WIRE)], WIRE, operation, has_self=True)
    operation = g.next_id; g.next_id += 1
    g.qml_list_property_operations['install'] = operation
    handler = effect_transport.handler('', '')
    raw = effect_transport.reserve(g, 'Internal.ListProperty.install', [('self', OBJECT),
        ('property', WIRE), ('kind', WORD), ('handler', handler)], UNIT, operation, has_self=True)
    g.cases.append(f'case {operation}: {{\n    return BendQmlLists::install(r);\n}}')
    for public, kind in [('Append', 0), ('Count', 1), ('At', 2), ('Clear', 3), ('Replace', 4), ('RemoveLast', 5)]:
        method = 'ListProperty.' + public[:1].lower() + public[1:] + 'Method(property)'
        g.bend += [f'def ListProperty.handle{public}(~property: Property, ~S: Data, ~f: S -> Method.Handler(~{method}), self: QObject, state: S) -> Action(Unit):',
            '  do Action<Unit>:', '    schema: Wire <- Property.schema(property)',
            f'    {raw["name"]}(S, {operation}, QObject.word(self), schema, {kind}, pair => run(Unit, Method.invoke(~{method}, ~S, ~f, pair)), state)', '']
    operation = g.next_id; g.next_id += 1
    g.qml_list_property_operations['reference'] = operation
    reference = dict(kind='value', bend='QQmlListReference', name='QQmlListReference', raw='U32')
    g.cases.append(f'case {operation}: {{\n    return BendQmlLists::reference(r);\n}}')
    g.emit_effect('Internal.QmlListView.reference', [('value', WORD)], reference, operation)
    g.bend.append((HERE / 'templates/qml_list_properties.bend').read_text())


def cpp(g):
    if not g.callback_qml:
        return '''namespace BendQmlLists {
struct Context;
struct Capture {};
static std::optional<Capture> capture(const QVariant &) { return {}; }
static bool live(const Capture &) { return true; }
static bool pin(BqtRequest *, const Capture &) { return true; }
static uint32_t owner(BqtRequest *, const Capture &) { return 0; }
static int argument_type(BqtRequest *, const QByteArray &, const BqtValue *) { return INT_MIN; }
static bool is_code(int) { return false; }
}
'''
    declarations, definitions, cases = [], [], []
    for index, _, cpp_name, t in argument_entries(g):
        if t['kind'] != 'object' or not g.classes.get(t.get('name'), {}).get('qobject'):
            continue
        name = t['name']
        factory = f'bqt_qml_list_factory_{index}'
        signature = f'BendQmlLists::Type *{factory}()'
        declarations.append('extern ' + signature + ';')
        body = signature.replace(factory, '__attribute__((noinline)) ' + factory) + ' {\n' + \
            f'    return BendQmlLists::native_type<{name}>({index});\n}}\n'
        line = f'case {index}: return {factory}();'
        if abi_cohorts.required(g, name):
            body = '#if BQT_HAS_RHI\n' + body + '#endif\n'
            line = '#if BQT_HAS_RHI\n' + line + '\n#endif'
        definitions.append(f'// BQT_AUXILIARY_BEGIN qml_lists {index}\n' + body + f'// BQT_AUXILIARY_END qml_lists {index}\n')
        cases.append(line)
    source = (HERE / 'templates/qml_list_properties.cpp').read_text()
    source = source.replace('@NATIVE_FACTORY_DECLARATIONS@', '\n'.join(declarations)).replace(
        '@NATIVE_FACTORY_CASES@', '\n'.join(cases)).replace('@VARIANT_ID@', str(g.ids['QVariant'])).replace(
        '@QOBJECT_ID@', str(g.ids['QObject'])).replace('@LIST_REFERENCE_ID@', str(g.ids['QQmlListReference']))
    return (HERE / 'templates/property_bindings.cpp').read_text() + '\n' + source + '\n' + ''.join(definitions)


def runtime_cpp(g):
    if not g.callback_qml:
        return ''
    return (HERE / 'templates/qml_list_runtime.cpp').read_text().replace(
        '@QOBJECT_ID@', str(g.ids['QObject'])).replace('@VARIANT_ID@', str(g.ids['QVariant'])).replace(
        '@LIST_REFERENCE_ID@', str(g.ids['QQmlListReference'])).replace('@INT64_CODE@', str(next(
            i for i, _, native, _ in argument_entries(g) if native == 'qint64')))


def inventory(g):
    return dict(available=bool(g.callback_qml), define='Property.qmlList(name, elementDescriptor)',
        descriptor='qmlList(elementDescriptor)',
        native_elements={cpp: t['bend'] for _, cpp, t in getattr(g, 'custom_signal_arguments', [])
            if t['kind'] == 'object' and g.classes.get(t.get('name'), {}).get('qobject')},
        element_policy='Exact native QObject list metatypes; Bend class list metatypes retain the declared element metadata',
        operations=['append', 'count', 'at', 'clear', 'replace', 'removeLast'],
        storage_operations=['appendStorage', 'countStorage', 'atStorage', 'clearStorage', 'replaceStorage', 'removeLastStorage'],
        callbacks=['handleAppend', 'handleCount', 'handleAt', 'handleClear', 'handleReplace', 'handleRemoveLast'],
        capabilities=['withAppend', 'withCount', 'withAt', 'withClear', 'withReplace', 'withRemoveLast'],
        native_operations=getattr(g, 'qml_list_property_operations', {}),
        backing='Per-instance native storage, current-element leases, generational non-QObject contexts',
        views='Typed scoped QVariant-backed QmlListView; copied views preserve owner provenance')
