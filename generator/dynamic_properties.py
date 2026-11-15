"""Preserve dependent QVariant origins in QObject's native dynamic properties."""
from pathlib import Path

HERE = Path(__file__).resolve().parent


def method_case(g, method):
    function = method['function']
    if function['declaring_class'] != 'QObject' or function['name'] not in ('setProperty', 'property'):
        return None
    writing = function['name'] == 'setProperty'
    lines = ['NativeCallScope scope;',
             f'auto *self = get<QObject>(r, r->self, {g.ids["QObject"]}, false, {str(writing).lower()});']
    arguments = []
    for index, argument in enumerate(method['args']):
        declarations, value = g.argument(argument, index)
        lines += declarations
        arguments.append(value)
    lines += ['if (r->error) return true;',
              f'return DynamicProperties::{"write" if writing else "read"}(r, self, {", ".join(arguments)});']
    return lines


def cpp(g):
    if not {'QObject', 'QVariant'}.issubset(g.ids):
        return ('static void dynamic_properties_event(QObject *, QEvent *) {}\n'
                'static void dynamic_properties_forget(uint32_t) {}\n')
    return (HERE / 'templates/dynamic_properties.cpp').read_text().replace('@QVARIANT_ID@', str(g.ids['QVariant']))
