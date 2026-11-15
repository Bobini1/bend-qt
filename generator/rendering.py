"""Public Qt render-loop selection and checked graphics operations."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTEXT_INDEPENDENT = {'QOpenGLContext', 'QOpenGLContextGroup', 'QOpenGLFramebufferObjectFormat',
                       'QOpenGLVersionProfile', 'QOpenGLPixelTransferOptions', 'QOpenGLDebugMessage',
                       'QOpenGLWidget', 'QOpenGLWindow'}


def emit(g):
    if 'QQuickWindow' not in g.ids:
        return
    operation = g.next_id
    g.next_id += 1
    g.cases.append(f'case {operation}: {{\n    return use_gui_render_loop(r);\n}}')
    g.emit_effect('Render.useGuiThread', [], {'kind': 'void', 'bend': 'Unit', 'raw': 'Unit'}, operation)


def before_call(g, m):
    owner = m['function']['declaring_class']
    if owner == 'QSGRendererInterface':
        return []  # Resource queries have their own render guard; API queries are always available.
    if owner.startswith('QSG') or owner in ('QQuickFramebufferObject::Renderer', 'QQuickRhiItemRenderer', 'QCanvasPainterItemRenderer'):
        return ['if (!gui_render_depth) return fail(r, EPERM, "Scene graph operations require an active GUI render callback");']
    if owner.startswith('QOpenGL') and owner not in CONTEXT_INDEPENDENT:
        return ['if (!check_graphics_context(r)) return true;']
    if owner == 'QOpenGLContext' and m['function']['name'] in ('functions', 'extraFunctions'):
        return ['if (!check_graphics_context(r)) return true;',
                'if (QOpenGLContext::currentContext() != self) return fail(r, EXDEV, "OpenGL function access requires this context to be current");']
    if owner == 'QQuickWindow' and m['function']['name'] in ('createTextureFromImage', 'createTextureFromRhiTexture',
            'createImageNode', 'createRectangleNode', 'createNinePatchNode', 'createTextNode'):
        return ['if (!gui_render_depth) return fail(r, EPERM, "Scene graph factories require an active GUI render callback");']
    return []


def cpp(g):
    types = ', '.join('case ' + str(g.ids[n]) + ':' for n in g.selected
                      if n.startswith('QSG') or n in ('QQuickFramebufferObject::Renderer', 'QQuickRhiItemRenderer') or
                      'QQuickRhiItemRenderer' in g.all_bases(n))
    prefix = 'static bool render_type(uint16_t type) { switch (type) { ' + types.replace(', ', ' ') + ' return true; default: return false; } }\n'
    graphics = ' '.join('case ' + str(g.ids[n]) + ':' for n in g.selected
                        if n.startswith('QOpenGL') and n not in CONTEXT_INDEPENDENT)
    prefix += 'static bool graphics_type(uint16_t type) { switch (type) { ' + graphics + ' return true; default: return false; } }\n'
    # OpenGL container/query state is context-local even within a share group.
    # Only these resource categories have a documented shared object namespace.
    shareable = ' '.join('case ' + str(g.ids[n]) + ':' for n in
                        ('QOpenGLBuffer', 'QOpenGLTexture', 'QOpenGLShader', 'QOpenGLShaderProgram', 'MemoryView')
                        if n in g.ids)
    prefix += 'static bool graphics_shareable(uint16_t type) { switch (type) { ' + shareable + ' return true; default: return false; } }\n'
    prefix += '''static bool graphics_context_ready(uint32_t id) {
    auto *e = entry(id);
    @SYNC_READY@
    if (!e || !e->graphics_context) return true;
    auto *owner = entry(e->graphics_context);
    auto *context = owner && owner->object ? qobject_cast<QOpenGLContext *>(owner->object) : nullptr;
    auto *current = QOpenGLContext::currentContext();
    return context && current && (context == current ||
        (graphics_shareable(e->type) && QOpenGLContext::areSharing(context, current)));
}
static bool attach_graphics_context(BqtRequest *r, uint32_t id) {
    auto *e = entry(id);
    if (!e || !graphics_type(e->type)) return true;
    auto *context = QOpenGLContext::currentContext();
    if (!context) { fail(r, ENODEV, "OpenGL resource registration requires a current context"); return false; }
    auto owner = borrow(r, context, @CONTEXT_TYPE@);
    if (!owner) return false;
    e->graphics_context = owner;
    return true;
}
'''.replace('@CONTEXT_TYPE@', str(g.ids['QOpenGLContext'])).replace('@SYNC_READY@',
    f'''if (e && e->type == {g.ids['QOpenGLSync']}) {{
        auto *value = static_cast<QOpenGLSync *>(e->value);
        auto *current = QOpenGLContext::currentContext();
        return value->group && current && current->shareGroup() == value->group;
    }}''' if 'QOpenGLSync' in g.ids else '')
    prefix += '''static bool check_graphics_context(BqtRequest *r) {
    auto *current = QOpenGLContext::currentContext();
    if (!current) { fail(r, ENODEV, "OpenGL operation requires a current context on the Qt thread"); return false; }
    if (!graphics_context_ready(r->self)) { fail(r, EXDEV, "OpenGL resource belongs to a different context"); return false; }
    for (uint32_t depth = 0, id = r->self; id && depth < capacity; ++depth) {
        auto *e = entry(id);
        if (!e) break;
        auto *owner = e->object ? qobject_cast<QOpenGLContext *>(e->object) : nullptr;
        if (owner && owner != current && !QOpenGLContext::areSharing(owner, current)) {
            fail(r, EXDEV, "OpenGL handle belongs to a different context"); return false;
        }
        id = e->native_owner;
    }
    return true;
}
'''
    if 'QQuickWindow' not in g.ids:
        return prefix + 'static void schedule_render_collection(uint32_t) {}\nstatic void prepare_render_shutdown() {}\n'
    return prefix + (HERE / 'templates/rendering.cpp').read_text().replace('@QQUICK_WINDOW_TYPE@', str(g.ids['QQuickWindow']))
