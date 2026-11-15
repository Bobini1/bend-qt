"""QCoreApplication destructor callbacks, using the real qAddPostRoutine list."""
from pathlib import Path

import effect_transport

HERE = Path(__file__).resolve().parent


def emit(g):
    name = 'PostRoutine'
    handle = dict(kind='object', bend=name, raw='U32')
    unit = dict(kind='void', bend='Unit', raw='Unit')
    g.types[name] = 'handle'
    g.bend += [
        'def Internal.PostRoutine.apply(~S: Data, ~f: S -> Action(Unit), state: S, call: U32) -> Action(Unit):',
        '  do Action<Unit>:',
        '    f(state)',
        '    Handler.answer(call, WireScalar{0, 0})', '',
        'def Internal.PostRoutine.run(~S: Data, ~f: S -> Action(Unit), state: S, request: Maybe<&2, HandlerRequest>) -> Action(Unit):',
        '  match request:',
        '    case None{}: Handler.malformed(Unit)',
        '    case Some{HandlerRequest{call, arguments}}: Internal.PostRoutine.apply(~S, ~f, state, call)', '',
        'def Internal.PostRoutine.invoke(~S: Data, ~f: S -> Action(Unit), pair: S & Wire) -> Action(Unit):',
        '  match pair:',
        '    case (state, wire): Internal.PostRoutine.run(~S, ~f, state, HandlerRequest.decode(wire))', '']
    operations = {}
    for public, params, result, function, has_self in [
        ('PostRoutine.add', [('state', effect_transport.handler('S -> Action(Unit)', 'Internal.PostRoutine.invoke'))], handle, 'add', False),
        ('PostRoutine.remove', [('self', handle)], unit, 'remove', True),
        ('PostRoutine.release', [('self', handle)], unit, 'remove', True),
    ]:
        operation = g.next_id
        g.next_id += 1
        operations[public] = operation
        g.cases.append(f'case {operation}: {{\n    return PostRoutines::{function}(r);\n}}')
        g.emit_effect(public, params, result, operation, has_self=has_self)
    g.emit_scope(name, 'release')
    import scope_actions
    scope_actions.keep(g, name)
    g.post_routine_operations = operations
    for row in g.excluded:
        if row['signature'].startswith(('qAddPostRoutine(', 'qRemovePostRoutine(')):
            row.setdefault('alternatives', []).append(dict(
                bend_name='PostRoutine.add / PostRoutine.remove', contract='application_destructor_callback',
                reason='Real Qt cleanup list, reverse order; scoped registrations can be removed early'))


def cpp(g):
    return (HERE / 'templates/post_routines.cpp').read_text()
