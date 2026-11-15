"""Opaque renderer pointers that expire with their originating render callback.

No ownership or pointee representation is inferred from a backend resource key.
The explicitly unsafe address escape retains Qt's native platform obligations.
"""


def handles(f):
    return (f['declaring_class'], f['name']) in {
        ('QSGRendererInterface', 'getResource'), ('QSGRenderNode::RenderState', 'get')}


def install(classes, selected):
    if not any(name in classes for name in ('QSGRendererInterface', 'QSGRenderNode::RenderState')):
        return
    name = 'NativeRenderResource'
    classes[name] = dict(name=name, object=False, value=True, qobject=False, copyable=False,
        public_destructor=True, abstract=False, namespace=False, generate=False, template=False,
        bases=[], functions=[], enums=[], adapter=True)
    selected.append(name)


def aliases(g, inside):
    if 'NativeRenderResource' not in g.ids:
        return ''
    if inside:
        return 'struct NativeRenderResource { uintptr_t pointer; uint32_t owner, window; uint64_t scope; };\n'
    return 'namespace bendqt { struct NativeRenderResource; }\n'


def handle():
    return dict(kind='value', name='NativeRenderResource', bend='NativeRenderResource',
                cpp='NativeRenderResource', raw='U32', pointer=False)


def adapt(g, f):
    return dict(handle(), result_conversion='render_resource') if handles(f) else None


def parameters(g, f):
    if not handles(f):
        return None
    args = [dict(kind='string', name='QString', bend='String', raw='String')
            if a['type']['name'] == 'char' else g.type(a['type']) for a in f['arguments']]
    return args, [dict(type=t, source=i, input=i, output=False, mutable=False)
                  for i, t in enumerate(args)], []


def method_case(g, m):
    f = m['function']
    if not handles(f):
        return None
    owner = f['declaring_class']
    lines = ['NativeCallScope scope;',
             'if (!active_gui_render_scope) return fail(r, EPERM, "Native renderer resources require an active GUI render callback");',
             f'auto *self = get<{owner}>(r, r->self, {g.ids[owner]}, false, false);']
    if owner == 'QSGRendererInterface':
        lines += [f'auto *window = get<QQuickWindow>(r, r->arguments[0].word, {g.ids["QQuickWindow"]}, false, false);',
                  'if (r->error) return true;',
                  'if (gui_render_window != r->arguments[0].word) return fail(r, EXDEV, "Renderer resource window differs from the active render callback");',
                  'if (window->rendererInterface() != self) return fail(r, ESTALE, "Renderer interface no longer belongs to this window");']
        index, arguments, origin = 1, 'window, ', 'r->arguments[0].word'
    else:
        lines += ['if (r->error) return true;']
        index, arguments, origin = 0, '', 'r->self'
    if m['args'][index]['kind'] == 'string':
        lines += [f'if (std::memchr(r->arguments[{index}].text, 0, r->arguments[{index}].size)) return fail(r, EINVAL, "Renderer resource key contains an embedded NUL");',
                  f'QByteArray key(r->arguments[{index}].text, qsizetype(r->arguments[{index}].size));']
        arguments += 'key.constData()'
    else:
        arguments += f'static_cast<QSGRendererInterface::Resource>(r->arguments[{index}].word)'
    lines += [f'auto *pointer = self->{f["name"]}({arguments});',
              f'r->result.word = own(r, new NativeRenderResource{{reinterpret_cast<uintptr_t>(pointer), {origin}, gui_render_window, active_gui_render_scope->identity}}, {g.ids["NativeRenderResource"]});',
              'r->result.owned_handle = r->result.word;', 'return true;']
    return lines


def emit(g):
    if 'NativeRenderResource' not in g.ids:
        return
    g.types['UInt64'] = 'wide'
    for method in ('isValid', 'isNull', 'unsafeAddress'):
        result = (dict(kind='u64', bend='UInt64', raw='U32 & U32') if method == 'unsafeAddress'
                  else dict(kind='bool', bend='Bool', raw='U32'))
        operation = g.next_id; g.next_id += 1
        lines = ['NativeCallScope scope;',
                 f'auto *value = get<NativeRenderResource>(r, r->self, {g.ids["NativeRenderResource"]}, false, false);',
                 'if (r->error) return true;',
                 'bool valid = native_render_resource_valid(*value);']
        if method == 'isValid':
            lines += ['r->result.word = valid;']
        else:
            lines += ['if (!valid) return fail(r, ESTALE, "Native renderer resource has left its originating render callback");',
                      'r->result = wide_value(value->pointer);' if method == 'unsafeAddress'
                      else 'r->result.word = !value->pointer;']
        lines += ['return true;']
        g.cases.append(f'case {operation}: {{\n' + '\n'.join('    ' + line for line in lines) + '\n}')
        g.emit_effect('NativeRenderResource.' + method, [('self', handle())], result, operation, has_self=True)


def cpp(g):
    if 'NativeRenderResource' not in g.ids:
        return ''
    return '''
static bool native_render_resource_valid(const NativeRenderResource &value)
{
    if (!entry(value.owner) || (value.window && (!entry(value.window) || gui_render_window != value.window))) return false;
    for (auto *scope = active_gui_render_scope; scope; scope = scope->previous)
        if (scope->identity == value.scope) return true;
    return false;
}
'''
