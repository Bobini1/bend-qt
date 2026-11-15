"""Typed adapters for Qt's raw easing and accessibility function pointers.

Easing functions have application lifetime: native QEasingCurve copies contain
only a code pointer, so Qt offers no last-copy notification. Function views
are scoped independently. Accessibility registrations have explicit removal.
"""
from pathlib import Path

import effect_transport

HERE = Path(__file__).resolve().parent
WORD = dict(kind='u32', bend='U32', raw='U32')
UNIT = dict(kind='void', bend='Unit', raw='Unit')
BOOL = dict(kind='bool', bend='Bool', raw='U32')


def prepare(g):
    from callbacks import _conversion, _record
    def source(name, pointers=0):
        return dict(name=name, cpp=name + '*' * pointers, pointers=pointers,
                    reference=0, const=False, container=False, enum=False,
                    flags=False, instantiations=[])
    g.native_function_callbacks = {}
    if 'QEasingCurve' in g.ids:
        real = _conversion(g, source('double'))
        g.native_function_callbacks['easing'] = dict(
            real=real, payload=_record(g, [real], 'EasingArguments_'))
    if {'QAccessible', 'QAccessibleInterface', 'QObject'}.issubset(g.ids):
        text = _conversion(g, source('QString'))
        obj = _conversion(g, source('QObject', 1))
        result = _conversion(g, source('QAccessibleInterface', 1), result=True, transfer=True)
        g.native_function_callbacks['accessible'] = dict(
            result=result, payload=_record(g, [text, obj], 'AccessibilityFactoryArguments_'))


def emit(g):
    import signals
    features = g.native_function_callbacks
    operations = {}
    def operation(public, params, result, function, has_self=False):
        value = g.next_id
        g.next_id += 1
        operations[function] = value
        g.cases.append(f'case {value}: {{\n    return NativeFunctionCallbacks::{function}(r);\n}}')
        g.emit_effect(public, params, result, value, has_self=has_self)
    if 'easing' in features:
        item = features['easing']
        name = 'QEasingCurve.EasingFunction'
        g.types[name] = 'handle'
        handle = dict(kind='object', bend=name, raw='U32')
        curve = dict(kind='object', bend='QEasingCurve', raw='U32')
        function = signals.invoke(g, 'Internal.EasingFunction', ['F64'], item['payload'], item['real'])
        operation(name + '.new', [('state', effect_transport.handler(function, 'Internal.EasingFunction.invoke'))], handle, 'easing_new')
        operation(name + '.release', [('self', handle)], UNIT, 'easing_release', True)
        operation(name + '.call', [('self', handle), ('progress', item['real'])], item['real'], 'easing_call', True)
        operation(name + '.isSame', [('self', handle), ('other', handle)], BOOL, 'easing_same', True)
        operation('QEasingCurve.setCustomType', [('self', curve), ('function', handle)], UNIT, 'easing_set', True)
        operation('Internal.QEasingCurve.customType', [('self', curve)], WORD, 'easing_get', True)
        g.emit_scope(name, 'release')
        g.bend += [
            f'def {name}.fromResult(result: Result<&1, &1, U32 & String, U32>) -> Result<&1, &1, U32 & String, Maybe<&2, {name}>>:',
            '  match result:',
            '    case Fail{error}: Fail{error}',
            '    case Done{0}: Done{None{}}',
            f'    case Done{{value}}: Done{{Some{{{name}{{value}}}}}}', '',
            f'def QEasingCurve.customType(self: QEasingCurve) -> Action(Maybe<&2, {name}>):',
            f'  do Action.Raw<Result<&1, &1, U32 & String, Maybe<&2, {name}>>>:',
            '    result: Result<&1, &1, U32 & String, U32> <- Internal.QEasingCurve.customType(self)',
            f'    return {name}.fromResult(result)', '',
            'def QEasingCurve.setCustomHandler(~S: Data, ~f: S -> F64 -> Action(F64), self: QEasingCurve, state: S) -> Action(Unit):',
            f'  {name}.with(Unit, {name}.new(~S, ~f, state), function => QEasingCurve.setCustomType(self, function))', '']
    if 'accessible' in features:
        item = features['accessible']
        name = 'QAccessible.InterfaceFactory'
        g.types[name] = 'handle'
        handle = dict(kind='object', bend=name, raw='U32')
        function = signals.invoke(g, 'Internal.AccessibleFactory', ['String', 'QObject'],
                                  item['payload'], item['result'], scope='QAccessibleInterface')
        operation('QAccessible.installFactory', [('state', effect_transport.handler(function, 'Internal.AccessibleFactory.invoke'))], handle, 'accessible_install')
        operation('QAccessible.removeFactory', [('self', handle)], UNIT, 'accessible_remove', True)
        operation(name + '.release', [('self', handle)], UNIT, 'accessible_remove', True)
        g.emit_scope(name, 'release')
    g.native_function_callback_operations = operations


def cpp(g):
    features = g.native_function_callbacks
    # Imported interface returns need the cache/lifetime helpers even when the
    # partition does not expose QAccessible's public factory API.
    accessible = {'QAccessibleInterface', 'QObject'}.issubset(g.ids)
    return (HERE / 'templates/native_function_callbacks.cpp').read_text().replace(
        '@HAS_EASING@', '1' if 'easing' in features else '0').replace(
        '@HAS_ACCESSIBLE@', '1' if accessible else '0').replace(
        '@EASING_ID@', str(g.ids.get('QEasingCurve', 0))).replace(
        '@QOBJECT_ID@', str(g.ids.get('QObject', 0))).replace(
        '@ACCESSIBLE_ID@', str(g.ids.get('QAccessibleInterface', 0)))


def store(g, t, expression):
    if t.get('name') == 'QAccessibleInterface' and t.get('kind') == 'object' and not t.get('owned'):
        return [f'r->result.word = NativeFunctionCallbacks::accessible_borrow(r, {expression});',
                'r->result.borrowed_handle = r->result.word;']
    return None


def method_case(g, m):
    f = m['function']
    if f['declaring_class'] == 'QAccessible' and f['name'] == 'deleteAccessibleInterface':
        return ['return NativeFunctionCallbacks::accessible_delete(r);']
    if f['declaring_class'] == 'QAccessible' and f['name'] in ('uniqueId', 'registerAccessibleInterface'):
        return ['return NativeFunctionCallbacks::accessible_register(r);']
    return None


def annotate(g):
    names = {name for name in g.native_function_callback_operations}
    for excluded in g.excluded:
        cls = excluded.get('class')
        signature = excluded.get('signature', '')
        public = None
        if cls == 'QEasingCurve' and 'setCustomType(' in signature and 'easing_set' in names:
            public = 'QEasingCurve.setCustomType'
        elif cls == 'QEasingCurve' and 'customType(' in signature and 'easing_get' in names:
            public = 'QEasingCurve.customType'
        elif cls == 'QAccessible' and 'installFactory(' in signature and 'accessible_install' in names:
            public = 'QAccessible.installFactory'
        elif cls == 'QAccessible' and 'removeFactory(' in signature and 'accessible_remove' in names:
            public = 'QAccessible.removeFactory'
        if public:
            excluded.setdefault('alternatives', []).append(dict(bend_name=public,
                contract='typed_native_function_pointer', native_signature=signature,
                reason='Typed Bend callbacks with checked function identities and explicit Qt lifetime policy'))
