"""Raw GL buffer mappings backed by scoped, revalidated MemoryView capabilities."""
from pathlib import Path

MAPS = {'glMapBuffer', 'glMapBufferRange', 'glMapNamedBuffer', 'glMapNamedBufferRange'}
GETTERS = {'glGetBufferPointerv', 'glGetNamedBufferPointerv'}


def enabled(g):
    # The function wrappers belong to QtGui; QOpenGLBuffer belongs to the
    # optional QtOpenGL module and is not required for raw GL buffer mappings.
    return 'QOpenGLBuffer' in g.ids or any(name.startswith(('QOpenGLFunctions', 'QOpenGLExtraFunctions')) for name in g.ids)


def handles(f):
    return f['declaring_class'].startswith(('QOpenGLFunctions', 'QOpenGLExtraFunctions')) and f['name'] in MAPS | GETTERS


def adapt(g, f):
    if handles(f):
        return dict(kind='value', name='MemoryView', cpp='MemoryView', bend='MemoryView', raw='U32', raw_gl_mapping=True)
    return None


def parameters(g, f):
    if not handles(f) or f['name'] not in GETTERS:
        return None
    args = [g.type(a['type']) for a in f['arguments'][:2]]
    plan = [dict(type=t, source=i, input=i, output=False, mutable=False) for i, t in enumerate(args)]
    plan.append(dict(type=dict(kind='void', bend='Unit', raw='Unit'), source=2, input=None, output=False, mutable=False, ignored=True))
    return args, plan, []


def method_case(g, m):
    f = m['function']
    if not handles(f):
        return None
    name = f['name']
    receiver = g.receiver_class(m)
    named = str('Named' in name).lower()
    mode = 0 if name in GETTERS else 2 if name.endswith('Range') else 1
    args = [g.argument(t, i)[1] for i, t in enumerate(m['args'])]
    offset, length, access = ('0', '0', args[1]) if mode != 2 else (args[1], args[2], args[3])
    return ['NativeCallScope call_scope;', f'auto *self = get<{receiver}>(r, r->self, {g.ids[receiver]});',
            'if (r->error || !initialize_gl_functions(r, self)) return true;',
            f'return raw_gl_mapping_request(r, {args[0]}, {named}, {mode}, {offset}, {length}, {access});']


def before_call(g, m):
    f = m['function']
    if not f['declaring_class'].startswith(('QOpenGLFunctions', 'QOpenGLExtraFunctions')):
        return []
    name = f['name']
    if name == 'glDeleteBuffers':
        return ['for (int n = 0; n < int32_t(r->arguments[0].word); ++n)',
                '    if (!guard_raw_gl_mapping_mutation(r, a1->at(n))) return true;']
    if name in ('glUnmapBuffer', 'glUnmapNamedBuffer'):
        return [f'auto raw_buffer = raw_gl_buffer_id(r, r->arguments[0].word, {str("Named" in name).lower()});',
                'if (r->error) return true;', 'retire_gl_mappings(raw_buffer);']
    if name in ('glBufferData', 'glBufferStorage', 'glBufferSubData', 'glClearBufferData', 'glClearBufferSubData',
                'glNamedBufferData', 'glNamedBufferStorage', 'glNamedBufferSubData', 'glClearNamedBufferData', 'glClearNamedBufferSubData'):
        return [f'auto raw_buffer = raw_gl_buffer_id(r, r->arguments[0].word, {str("Named" in name).lower()});',
                'if (r->error || !guard_raw_gl_mapping_mutation(r, raw_buffer)) return true;']
    return []


def declarations(g):
    if not enabled(g):
        return ''
    return '''static void flush_raw_gl_mapping(const MemoryView &, size_t, size_t);
static void retire_raw_gl_mappings(GLuint);
static bool guard_raw_gl_mapping_mutation(BqtRequest *, GLuint);
'''


def cpp(g):
    if not enabled(g):
        return ''
    source = Path(__file__).with_name('templates').joinpath('gl_raw_mappings.cpp').read_text()
    qt_buffer_guard = '''        if (view.gl_mapping && view.gl_mapping->buffer.bufferId() == buffer && view.gl_mapping->compatible() && view.gl_mapping->live())
            return fail(r, EBUSY, "Release or unmap Qt OpenGL mappings before replacing buffer storage"), false;
'''
    qt_buffer_live = 'view.gl_mapping && view.gl_mapping->buffer.bufferId() == buffer && view.gl_mapping->live()'
    return (source.replace('@MEMORY_VIEW@', str(g.ids['MemoryView']))
            .replace('@QT_BUFFER_MUTATION_GUARD@\n', qt_buffer_guard if 'QOpenGLBuffer' in g.ids else '')
            .replace('@QT_BUFFER_LIVE@', qt_buffer_live if 'QOpenGLBuffer' in g.ids else 'false'))


def raw_only_memory_cpp(g):
    if not enabled(g):
        return 'static void flush_memory_mapping(const MemoryView &, size_t, size_t) {}\n'
    # Keep the same current-context/version precondition for both mapping
    # families, without emitting the optional QOpenGLBuffer implementation.
    source = Path(__file__).with_name('templates').joinpath('gl_mappings.cpp').read_text()
    common, separator, _ = source.partition('struct GLBufferBinding {')
    if not separator:
        raise ValueError('OpenGL mapping template no longer exposes its common context precondition')
    return common + '''static void flush_memory_mapping(const MemoryView &view, size_t offset, size_t count) {
    flush_raw_gl_mapping(view, offset, count);
}
static void retire_gl_mappings(GLuint buffer) {
    retire_raw_gl_mappings(buffer);
}
'''
