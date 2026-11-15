"""The process-global Qt message handler, as a Bend handler.

`MessageHandler.install(~S, ~f, state)` replaces Qt's message handler by `f`,
which receives each `LogMessage` logged on the main thread. Messages logged on
other threads, or while `f` itself runs, go to the handler that was installed
before. A failing `f` does not fail the Qt operation that logged: the message
goes to the previous handler and `MessageHandler.lastError` keeps the code.
"""
from pathlib import Path

import effect_transport

FUNCTION = 'S -> LogMessage -> Action(Unit)'


def prepare(g):
    from callbacks import _conversion
    def source(name, **extra):
        return dict(name=name, cpp=name, pointers=0, reference=0, const=False,
                    container=False, enum=False, flags=False, **extra)
    text = _conversion(g, source('QString'))
    optional = dict(source('std::optional'), container=True, cpp='std::optional<QString>', instantiations=[source('QString')])
    nullable = _conversion(g, optional)
    kind = _conversion(g, dict(source('QtMsgType'), enum=True))
    signed = _conversion(g, source('int'))
    children = [dict(t) for t in (kind, text, nullable, nullable, signed, nullable, signed)]
    for t in children:
        if t.get('callback_enum'): t.pop('cpp', None)
    g.conversions.register(dict(kind='record', children=children, bend='LogMessage', raw='Wire', codec='LogMessage'))


def emit(g):
    unit = dict(bend='Unit', raw='Unit')
    import signals
    signals.invoke_value(g, 'MessageHandler', 'LogMessage', 'LogMessage.decode')
    for public, params, result, function in [
        ('MessageHandler.install', [('state', effect_transport.handler(FUNCTION, 'MessageHandler.invoke'))], unit, 'message_handler_install'),
        ('MessageHandler.restore', [], unit, 'message_handler_restore'),
        ('MessageHandler.lastError', [], dict(bend='U32', raw='U32'), 'message_handler_status'),
        ('MessageHandler.format', [('message', dict(bend='LogMessage', raw='Wire', codec='LogMessage'))], dict(bend='String', raw='String'), 'message_handler_format')]:
        operation = g.next_id
        g.next_id += 1
        g.callback_operations[function] = operation
        g.cases.append(f'case {operation}: {{\n    return {function}(r);\n}}')
        g.emit_effect(public, params, result, operation)


def cpp(g):
    return (Path(__file__).parent / 'templates/message_handlers.cpp').read_text()
