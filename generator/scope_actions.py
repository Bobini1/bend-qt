"""Explicit resource contexts for Action; no ambient Bend task state."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORD = dict(kind='u32', bend='U32', raw='U32')
UNIT = dict(kind='void', bend='Unit', raw='Unit')


def emit(g):
    operations = dict(zip(('open', 'close', 'keep'), range(g.next_id, g.next_id + 3)))
    g.next_id += 3
    g.scope_operations = operations
    g.emit_effect('Scope.open', [('parent', WORD)], WORD, operations['open'])
    g.emit_effect('Scope.close', [('scope', WORD)], UNIT, operations['close'])
    g.emit_effect('Scope.keep_raw', [('kind', WORD), ('handle', WORD)], WORD, operations['keep'])
    for key, function in [('open', 'scope_open'), ('close', 'scope_close'), ('keep', 'scope_keep')]:
        g.cases.append(f'case {operations[key]}: {{\n    return {function}(r);\n}}')
    g.bend += [(HERE / 'templates/scopes.bend').read_text()]


def keep(g, name, kind=0):
    g.bend += [f'def {name}.keep(value: {name}) -> Action({name}):',
               f'  do Action.Raw<Result<&1, &1, U32 & String, {name}>>:',
               f'    result: Result<&1, &1, U32 & String, U32> <- Scope.keep_raw({kind}, {name}.word(value))',
               f'    return {name}.wrap(result)', '']


def cpp(g):
    return (HERE / 'templates/scopes.cpp').read_text().replace(
        '@QML_HANDLER_RELEASE@', 'callback_qml_release(&cleanup);' if g.callback_qml else
        'fail(&cleanup, ENOTSUP, "QML is unavailable");')


def inventory(g):
    return dict(operations=g.scope_operations, context='Explicit Action argument on each native request',
                order='Reverse acquisition; all cleanup attempted; original body errors take precedence',
                ownership='Borrowed results remain borrowed; Qt ownership and retention are respected',
                escape='Type.keep promotes ownership to the parent scope; root promotion is explicit unmanaged ownership')
