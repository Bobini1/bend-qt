"""Context-retained storage for OpenGL feedback and selection output arrays."""
from pathlib import Path

NAMES = {'glFeedbackBuffer': 'GLFeedbackBuffer', 'glSelectBuffer': 'GLSelectionBuffer'}


def handles(f):
    return f['declaring_class'].startswith(('QOpenGLFunctions', 'QOpenGLExtraFunctions')) and f['name'] in NAMES


def install(classes, selected):
    if not any(handles(f) or (f['declaring_class'].startswith(('QOpenGLFunctions', 'QOpenGLExtraFunctions'))
                            and f['name'] in ('glGetPointerv', 'glGetVertexAttribPointerv'))
               for c in classes.values() for f in c['functions']):
        return
    for name in NAMES.values():
        classes[name] = dict(name=name, object=False, value=True, qobject=False, copyable=False,
            public_destructor=True, abstract=False, namespace=False, generate=False, template=False,
            bases=[], functions=[], enums=[], adapter=True)
        selected.append(name)


def aliases(g, inside):
    names = [name for name in NAMES.values() if name in g.ids]
    if inside:
        return '\n'.join(f'struct Native{name}; struct {name} {{ std::shared_ptr<Native{name}> state; }};' for name in names) + '\n'
    return 'namespace bendqt { ' + ' '.join(f'struct {name};' for name in names) + ' }\n'


def handle(name):
    return dict(kind='value', name=name, cpp=name, bend=name, raw='U32')


def adapt(g, f):
    return handle(NAMES[f['name']]) if handles(f) else None


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
    name = NAMES[f['name']]
    receiver = g.receiver_class(m)
    lines = ['NativeCallScope scope;', f'auto *self = get<{receiver}>(r, r->self, {g.ids[receiver]});',
             'if (r->error || !initialize_gl_functions(r, self)) return true;',
             'auto size = int32_t(r->arguments[0].word);',
             'if (size < 0) return fail(r, ERANGE, "Negative OpenGL retained buffer size");',
             'GLint mode = 0; QOpenGLContext::currentContext()->functions()->glGetIntegerv(GL_RENDER_MODE, &mode);',
             f'if (mode == {"GL_FEEDBACK" if name == "GLFeedbackBuffer" else "GL_SELECT"}) return fail(r, EBUSY, "Leave the active OpenGL output mode before replacing its storage");']
    if name == 'GLFeedbackBuffer':
        lines += ['auto type = GLenum(r->arguments[1].word);',
                  'if (type < GL_2D || type > GL_4D_COLOR_TEXTURE) return fail(r, EINVAL, "Unknown OpenGL feedback format");']
    lines += [f'auto state = std::make_shared<Native{name}>(size);',
              '// Reserve context storage before Qt/GL begins retaining the address.',
              'auto &slot = retained_gl_output_slot(state->context.data());',
              f'const auto id = own(r, new {name}{{state}}, {g.ids[name]});',
              'if (r->error) return true;',
              f'self->{f["name"]}(size, ' + ('type, ' if name == 'GLFeedbackBuffer' else '') + 'state->values.data());',
              f'if (slot.{"feedback" if name == "GLFeedbackBuffer" else "selection"}) slot.{"feedback" if name == "GLFeedbackBuffer" else "selection"}->installed = false;',
              f'slot.{"feedback" if name == "GLFeedbackBuffer" else "selection"} = state;',
              'state->installed = true;', 'r->result.word = id;', 'r->result.owned_handle = id;', 'return true;']
    return lines


def results(g):
    found = []
    for name, native, scalar in [('GLFeedbackBuffer', 'float', dict(kind='real', cpp='float', bend='F64', raw='U32 & U32')),
                                  ('GLSelectionBuffer', 'unsigned int', dict(kind='u32', cpp='unsigned int', bend='U32', raw='U32'))]:
        if name not in g.ids:
            continue
        if scalar['kind'] == 'real':
            g.types['F64'] = 'wide'
        child = g.conversions.register(scalar)
        result = g.conversions.register(dict(kind='list', name='QList', cpp=f'QList<{native}>',
            children=[child], bend=f'List<&2, {scalar["bend"]}>', raw='Wire', codec='List_' + scalar['bend']))
        found.append((name, native, result))
    return found


def prepare(g):
    results(g)


def emit(g):
    for name, native, result in results(g):
        operation = g.next_id
        g.next_id += 1
        body = ['NativeCallScope scope;', f'auto *value = get<{name}>(r, r->self, {g.ids[name]}, false, false);',
                'if (r->error) return true;', 'auto count = r->arguments[0].word;',
                'if (size_t(count) > value->state->values.size()) return fail(r, ERANGE, "OpenGL retained output exceeds its storage");',
                'if (!retained_gl_output_readable(r, *value->state)) return true;',
                f'QList<{native}> copied(value->state->values.begin(), value->state->values.begin() + count);',
                f'r->result = write_{result["native_codec"]}(r, copied);', 'return true;']
        g.cases.append(f'case {operation}: {{\n' + '\n'.join('    ' + line for line in body) + '\n}')
        g.emit_effect(name + '.read', [('self', handle(name)), ('count', dict(kind='u32', bend='U32', raw='U32', cpp='uint'))], result, operation, has_self=True)


def cpp(g):
    if 'GLFeedbackBuffer' not in g.ids:
        return ''
    return Path(__file__).with_name('templates').joinpath('gl_retained.cpp').read_text()
