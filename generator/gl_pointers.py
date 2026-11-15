"""Typed descriptions of native GL client pointers, never raw host addresses."""
from pathlib import Path


def handles(f):
    return f['declaring_class'].startswith(('QOpenGLFunctions', 'QOpenGLExtraFunctions')) and f['name'] in ('glGetPointerv', 'glGetVertexAttribPointerv')


def adapt(g, f):
    if not handles(f):
        return None
    scalar = g.conversions.register(dict(kind='u32', cpp='uint', bend='U32', raw='U32'))
    g.types['GLBufferOffset'] = 'wide'
    offset = g.conversions.register(dict(kind='u64', cpp='quintptr', bend='GLBufferOffset', raw='U32 & U32'))
    children = [scalar, scalar, offset]
    for name in ('GLFeedbackBuffer', 'GLSelectionBuffer'):
        value = g.conversions.register(dict(kind='value', name=name, cpp=name, bend=name, raw='U32'))
        children.append(g.conversions.register(dict(kind='optional', cpp=f'std::optional<{name}>',
            children=[value], bend=f'Maybe<&2, {name}>', raw='Wire')))
    return g.conversions.register(dict(kind='record', children=children, bend='GLClientPointer', raw='Wire', codec='GLClientPointer'))


def parameters(g, f):
    if not handles(f):
        return None
    args = [g.type(a['type']) for a in f['arguments'][:-1]]
    plan = [dict(type=t, source=i, input=i, output=False, mutable=False) for i, t in enumerate(args)]
    plan.append(dict(type=dict(kind='void', bend='Unit', raw='Unit'), source=len(args), input=None, output=False, mutable=False, ignored=True))
    return args, plan, []


def method_case(g, m):
    f = m['function']
    if not handles(f):
        return None
    receiver = g.receiver_class(m)
    attributes = f['name'] == 'glGetVertexAttribPointerv'
    arguments = [g.argument(t, i)[1] for i, t in enumerate(m['args'])]
    selector = arguments[1] if attributes else arguments[0]
    index = arguments[0] if attributes else '0'
    return ['NativeCallScope scope;', f'auto *self = get<{receiver}>(r, r->self, {g.ids[receiver]});',
            'if (r->error || !initialize_gl_functions(r, self)) return true;',
            f'if (!validate_gl_client_pointer_query(r, {selector}, {index}, {str(attributes).lower()})) return true;',
            'void *pointer = nullptr;', f'self->{f["name"]}(' + ', '.join(arguments + ['&pointer']) + ');',
            f'return gl_client_pointer_result(r, {selector}, {index}, {str(attributes).lower()}, pointer);']


def cpp(g):
    if not any(handles(m['function']) for m in g.methods):
        return ''
    source = Path(__file__).with_name('templates').joinpath('gl_pointers.cpp').read_text()
    for name in ('GLFeedbackBuffer', 'GLSelectionBuffer'):
        source = source.replace('@' + name + '@', str(g.ids[name]))
    return source
