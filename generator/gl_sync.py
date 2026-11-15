"""Context-owned OpenGL synchronization handles and nonblocking client waits."""
from pathlib import Path


def install(classes, selected):
    if not any(t['name'] == 'GLsync' for c in classes.values() for f in c['functions']
               for t in [f['return'], *(a['type'] for a in f['arguments'])]):
        return
    name = 'QOpenGLSync'
    classes[name] = dict(name=name, object=False, value=True, qobject=False, copyable=False,
        public_destructor=True, abstract=False, namespace=False, generate=False, template=False,
        bases=[], functions=[], enums=[], adapter=True, gl_sync=True)
    selected.append(name)


def aliases(g, inside):
    if 'QOpenGLSync' not in g.ids:
        return ''
    if not inside:
        return 'namespace bendqt { struct QOpenGLSync; }\n'
    return '''struct QOpenGLSync {
    GLsync value;
    QPointer<QOpenGLContextGroup> group;
    QOpenGLSync(GLsync native, QOpenGLContextGroup *owner) : value(native), group(owner) {}
    QOpenGLSync(const QOpenGLSync &) = delete;
    ~QOpenGLSync() {
        auto *context = QOpenGLContext::currentContext();
        if (value && group && context && context->shareGroup() == group)
            context->extraFunctions()->glDeleteSync(value);
    }
};
'''


def type(g, t):
    if t['name'] == 'GLsync' and not t['pointers'] and 'QOpenGLSync' in g.ids:
        return dict(kind='gl_sync', name='QOpenGLSync', cpp=t['cpp'], bend='QOpenGLSync', raw='U32', owned=True)
    return None


def argument(g, t, index):
    if t['kind'] != 'gl_sync':
        return None
    return [f'auto gl_sync_{index} = checked_gl_sync(r, r->arguments[{index}].word);',
            'if (r->error) return true;'], f'gl_sync_{index}'


def store(g, t, expression):
    if t['kind'] != 'gl_sync':
        return None
    return [f'r->result.word = own_gl_sync(r, {expression});', 'r->result.owned_handle = r->result.word;']


def method_case(g, m):
    f = m['function']
    if not f['declaring_class'].startswith('QOpenGL') or f['name'] not in ('glDeleteSync', 'glClientWaitSync'):
        return None
    owner = g.receiver_class(m)
    lines = ['NativeCallScope call_scope;', f'auto *self = get<{owner}>(r, r->self, {g.ids[owner]});',
             'if (r->error) return true;', 'if (!initialize_gl_functions(r, self)) return true;']
    if f['name'] == 'glDeleteSync':
        return lines + ['return delete_gl_sync(r, r->arguments[0].word);']
    return lines + ['return wait_gl_sync(r, r->arguments[0].word, r->arguments[1].word, wide_bits(r->arguments[2]));']


def cpp(g):
    if 'QOpenGLSync' not in g.ids:
        return ''
    source = Path(__file__).with_name('templates').joinpath('gl_sync.cpp').read_text()
    return (source.replace('@SYNC_TYPE@', str(g.ids['QOpenGLSync'])).replace('@CONTEXT_TYPE@', str(g.ids['QOpenGLContext']))
            .replace('@OBJECT_TYPE@', str(g.ids['QObject'])))
