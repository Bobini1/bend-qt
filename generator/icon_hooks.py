"""Typed QIconEngine ABI hooks, including their original in/out payloads.

Only Qt's documented IsNullHook and ScaledPixmapHook have payload contracts.
Unknown native hook IDs keep their base fallback; Bend never supplies void*.
"""
import copy


def matches(f):
    return f['declaring_class'] == 'QIconEngine' and f['name'] == 'virtual_hook'


def prepare_methods(g, f):
    from callbacks import _conversion, _record, signature_id
    if f['minimal_signature'] != 'virtual_hook(int,void*)':
        raise ValueError('Unknown QIconEngine ABI hook signature')
    methods = []
    for suffix, cpp, hook in [('IsNull', 'bool', 'IsNullHook'),
                              ('ScaledPixmap', 'QIconEngine::ScaledPixmapArgument', 'ScaledPixmapHook')]:
        source = dict(name=cpp, cpp=cpp, const=False, pointers=0, reference=0,
                      container=False, enum=False, flags=False, instantiations=[])
        arg = _conversion(g, source)
        ret = _conversion(g, source, result=True)
        typed = copy.deepcopy(f)
        typed.update(name='bqt_hook_' + suffix, return_type=cpp,
                     minimal_signature='virtual_hook' + suffix + '(' + cpp + ')',
                     arguments=[dict(name='data', type=source, removed=False, array=False)],
                     abstract=False, removed=False, const=False, noexcept=False)
        typed['return'] = source
        method_id = signature_id('QIconEngine', typed)
        methods.append(dict(function=typed, args=[arg], result=ret, native_result=ret, outputs=[],
                            payload=_record(g, [arg], 'CallbackArgs_'), method_id=method_id,
                            public='QIconEngine.Virtual.virtual_hook' + suffix + '_' + str(method_id),
                            icon_hook=hook, icon_suffix=suffix, native_signature=f['minimal_signature'],
                            render_update=False, render_scope=False))
    return methods


def configuration_cpp(g, c):
    methods = [m for m in c['virtuals'] if m.get('icon_hook')]
    if not methods:
        return []
    name = c['name']
    lines = []
    for m in methods:
        cpp = m['function']['return']['cpp']
        helper = m['function']['name']
        lines += [f'    {cpp} {helper}_base({cpp} data) {{',
                  f'        {name}::virtual_hook(QIconEngine::{m["icon_hook"]}, &data); return data;', '    }']
    lines += ['    void virtual_hook(int id, void *data) override {',
              '        switch (id) {']
    for m in methods:
        cpp = m['function']['return']['cpp']
        lines += [f'        case QIconEngine::{m["icon_hook"]}:',
                  '            if (!data) { callback_report_error(EINVAL); return; }',
                  f'            *static_cast<{cpp} *>(data) = {m["function"]["name"]}(*static_cast<{cpp} *>(data)); return;']
    lines += [f'        default: {name}::virtual_hook(id, data); return;', '        }', '    }']
    return lines


def emit(g):
    for method in g.callback_methods.values():
        if not method.get('icon_hook'):
            continue
        arg, ret = method['args'][0], method['result']
        operation = g.next_id; g.next_id += 1
        declarations, expression = g.argument(arg, 0)
        lines = ['NativeCallScope scope;',
                 f'auto *self = get<QIconEngine>(r, r->self, {g.ids["QIconEngine"]});',
                 *declarations, 'if (r->error) return true;',
                 f'auto data = {expression};',
                 f'self->virtual_hook(QIconEngine::{method["icon_hook"]}, &data);',
                 'if (r->error) return true;',
                 f'r->result = write_{ret["native_codec"]}(r, data);', 'return true;']
        g.cases.append(f'case {operation}: {{\n' + '\n'.join('    ' + line for line in lines) + '\n}')
        g.emit_effect('QIconEngine.virtual_hook' + method['icon_suffix'],
                      [('self', dict(kind='object', bend='QIconEngine', raw='U32')), ('data', arg)],
                      ret, operation, has_self=True)


def annotate(g):
    methods = [m for m in getattr(g, 'callback_methods', {}).values() if m.get('icon_hook')]
    for row in g.excluded:
        if row['class'] == 'QIconEngine' and row['signature'].startswith('virtual_hook('):
            for m in methods:
                for public in ('QIconEngine.virtual_hook' + m['icon_suffix'], m['public'] + '.handle'):
                    alternative = dict(bend_name=public, contract='typed_icon_hook',
                        reason='The documented hook ID selects an owning in/out payload; arbitrary extension IDs have no public payload contract')
                    if alternative not in row.setdefault('alternatives', []):
                        row['alternatives'].append(alternative)
