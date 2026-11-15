"""Keyed QRhi cleanup handlers, run by Qt before its backend teardown."""
from pathlib import Path


def emit(g):
    if 'QRhi' not in g.ids:
        return
    import abi_cohorts
    import effect_transport
    import signals
    abi_cohorts.register_exact(g, 'rhi_add_cleanup(', 'QRhi native cleanup callback phase', [])
    abi_cohorts.register_exact(g, 'rhi_remove_cleanup(', 'QRhi native cleanup callback phase', [])
    g.bend += ['def QRhi.Cleanup.decodeKey(value: Wire) -> Maybe<&2, U32>:',
               '  match value:',
               '    case WireSequence{WireScalar{key, 0} <> Nil{}}: Some{key}',
               '    case _: None{}', '']
    function = signals.invoke_value(g, 'QRhi.Cleanup', 'U32', 'QRhi.Cleanup.decodeKey')
    handler = effect_transport.handler(function, 'QRhi.Cleanup.invoke')
    root = dict(bend='QRhi', raw='U32')
    key = dict(bend='U32', raw='U32')
    unit = dict(bend='Unit', raw='Unit')
    for name, params, body in [
        ('QRhi.addCleanupHandler', [('self', root), ('key', key), ('state', handler)],
         'return rhi_add_cleanup(r, r->arguments[0].word, r->arguments[1].word, true);'),
        ('QRhi.addCleanupHandlerUnkeyed', [('self', root), ('state', handler)],
         'return rhi_add_cleanup(r, 0, r->arguments[0].word, false);'),
        ('QRhi.removeCleanupHandler', [('self', root), ('key', key)],
         'return rhi_remove_cleanup(r, r->arguments[0].word);'),
    ]:
        operation = g.next_id; g.next_id += 1
        g.cases.append(f'case {operation}: {{\n    {body}\n}}')
        g.emit_effect(name, params, unit, operation, has_self=True)


def bend_helpers(g):
    pass


def cpp(g):
    if 'QRhi' not in g.ids:
        return ''
    source = (Path(__file__).parent / 'templates/rhi_cleanup.cpp').read_text()
    return '#if BQT_HAS_RHI\n' + source.replace('@QRHI@', str(g.ids['QRhi'])) + '\n#endif\n'


def annotate(g):
    if 'QRhi' not in g.ids:
        return
    for row in g.excluded:
        if row.get('class') != 'QRhi':
            continue
        for function in g.classes['QRhi']['functions']:
            if function['signature'] != row.get('signature'):
                continue
            if function['name'] == 'addCleanupCallback':
                public = 'QRhi.addCleanupHandler' if len(function['arguments']) == 2 else 'QRhi.addCleanupHandlerUnkeyed'
            elif function['name'] == 'removeCleanupCallback':
                public = 'QRhi.removeCleanupHandler'
            else:
                continue
            alternative = dict(bend_name=public, contract='synchronous_native_cleanup',
                reason='Real QRhi cleanup phase running a Bend handler; stable logical keys support replacement/removal; resources remain valid while the handler runs')
            if alternative not in row.setdefault('alternatives', []): row['alternatives'].append(alternative)
