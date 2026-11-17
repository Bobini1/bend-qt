"""Allocation and observed-alias contracts for public rendering factories."""
from pathlib import Path
from adapters import RENDER_CALLER_OWNED_RETURNS, render_caller_owned_result
import protected_members

CANVAS_DEPENDENCY_SLOT = 0xffa10001


def cpp(g):
    # A group that only refers to QQuickWindow, such as QuickWidgets, has no
    # scene-graph factories.
    if 'QQuickWindow' not in g.ids or 'QSGNode' not in g.ids:
        return '''static void render_factory_mark(uint32_t) {}
static bool render_factory_consumable(uint32_t) { return false; }
static uint32_t render_factory_retention_owner(uint32_t id) { return id; }
static bool render_factory_handoff(BqtRequest *r, uint32_t, uint32_t, bool) { fail(r, ENOTSUP, "Rendering is unavailable"); return false; }
static void render_factory_replaced(uint32_t, const void *, const void *) {}
static void render_factory_replacing(uint32_t, const void *, const void *) {}
static void render_factory_replacing_allocation(uint32_t) {}
static void render_factory_replaced_allocation(uint32_t) {}
static void render_factory_end_scope(uint64_t) {}
static uint32_t render_factory_restore(BqtRequest *, const void *, uint16_t, uint32_t) { return 0; }
static bool render_factory_sync_owner(BqtRequest *r, uint32_t id, uint32_t owner) { return set_native_owner(r, id, owner); }
'''
    return (Path(__file__).resolve().parent / 'templates/render_factory_domains.cpp').read_text().replace(
        '@QSG_NODE_ID@', str(g.ids['QSGNode'])).replace('@QQUICK_WINDOW_ID@', str(g.ids['QQuickWindow'])).replace(
        '@VARIANT_ID@', str(g.ids['QVariant']))


def before_call(g, m):
    f = m['function']
    key = f['declaring_class'], f['name']
    if key == ('QCanvasPainterFactory', 'create'):
        return ['if (!a0) return fail(r, EINVAL, "A Canvas painter needs a live QRhi");',
                'bool canvas_was_valid = self->isValid();',
                f'int canvas_dependency = canvas_was_valid || entry_inside(r->self, r->arguments[0].word) ? -1 : prepare_retention(r, {CANVAS_DEPENDENCY_SLOT}u, 0, r->arguments[0].word);',
                'if (r->error) return true;',
                f'RetentionReservation canvas_reservation(canvas_dependency, r->self, {CANVAS_DEPENDENCY_SLOT}u, 0);']
    if key == ('QCanvasPainterFactory', 'destroy'):
        return ['if (!protected_fields_children_mutable(r, r->self)) return true;',
                'if (!native_children_idle(r, r->self)) return true;',
                'protected_fields_expire_children(r->self);', 'invalidate_native_children(r->self);']
    if key == ('QQuickFramebufferObject::Renderer', 'invalidateFramebufferObject'):
        return ['if (!gui_render_depth) return fail(r, EPERM, "Framebuffer access requires an active GUI render callback");',
                'if (!protected_fields_children_mutable(r, r->self)) return true;',
                'if (!native_children_idle(r, r->self)) return true;',
                'protected_fields_expire_children(r->self);']
    return []


def _observed(g, m, getter=None, frame=False):
    f = m['function']
    owner = f['declaring_class']
    result = m.get('native_return', m['return'])
    helper = 'render_alias_' + owner.replace('::', '_') + '_' + f['name']
    if getter is None:
        getter = protected_members.expression(g, f, [], 'value') or ('value->' + f['name'] + '()')
    g.retention_accessors[helper] = f'''static const void *{helper}(BqtRequest *r, uint32_t id) {{
    auto *value = protected_fields_owner<{owner}>(r, id, {g.ids[owner]});
    return value ? {getter} : nullptr;
}}
'''
    observer = helper
    lines = []
    if frame:
        lines += ['if (!active_gui_render_scope) return fail(r, EPERM, "This native rendering view needs a live GUI render callback");',
                  'const auto render_view_epoch = active_gui_render_scope->identity;']
        observer = ('[render_view_epoch](BqtRequest *request, uint32_t id) -> const void * {'
            ' if (!active_gui_render_scope || active_gui_render_scope->identity != render_view_epoch) {'
            ' fail(request, ESTALE, "The rendering view belongs to a completed callback"); return nullptr; }'
            f' return {helper}(request, id); }}')
    return lines + [f'if (returned) protected_fields_borrow(r, returned, {g.ids[result["name"]]}, r->self, {observer}, false);',
                    'if (r->error) return true;']


def before_result(g, m):
    f = m['function']
    key = f['declaring_class'], f['name']
    if key == ('QQuickFramebufferObject', 'createRenderer'):
        # Renderer has a protected destructor. Only an existing generated
        # proxy carries an accessible, exact native deleter to reclaim.
        return ['uint32_t reclaimed_renderer = 0;',
                'if (returned) {',
                '    for (uint32_t i = 1; i < capacity; ++i) {',
                '        auto &record = entries[i];',
                f'        if (!record.value || !record.cast || record.cast(record.value, {g.ids["QQuickFramebufferObject::Renderer"]}) != returned) continue;',
                '        if (!record.native_observed || !record.proxy || !record.destroy || record.native_owner)',
                '            return fail(r, EPERM, "This renderer is already owned by native Qt");',
                '        reclaimed_renderer = token(i, record.generation);',
                '        if (!can_transfer_handle(r, reclaimed_renderer)) return true;',
                '        record.read_only = false; record.pending_release = false;',
                '        set_owned(reclaimed_renderer, true);',
                '        break;', '    }',
                '    if (!reclaimed_renderer) return fail(r, ENOTSUP, "A private Qt renderer has no public owning destructor");',
                '}']
    if key == ('QOpenGLVersionFunctionsFactory', 'get'):
        context = 'a1' if len(m['args']) >= 2 else 'nullptr'
        profile = 'QOpenGLVersionProfile(*a0)' if m['args'] else 'QOpenGLVersionProfile{}'
        return [f'if (returned) {{ auto *context = {context} ? {context} : QOpenGLContext::currentContext();',
                '    if (!context) return fail(r, ENODEV, "OpenGL functions need their owning context");',
                f'    uint32_t owner = borrow(r, context, {g.ids["QOpenGLContext"]});',
                f'    const auto native_profile = {profile};',
                f'    auto id = protected_fields_borrow(r, returned, {g.ids["QAbstractOpenGLFunctions"]}, owner,',
                f'        [native_profile](BqtRequest *request, uint32_t id) -> const void * {{ auto *value = protected_fields_owner<QOpenGLContext>(request, id, {g.ids["QOpenGLContext"]});',
                '            return value ? QOpenGLVersionFunctionsFactory::get(native_profile, value) : nullptr; }, false);',
                '    if (auto *record = entry(id)) record->graphics_context = owner;',
                '}', 'if (r->error) return true;']
    if key == ('QCanvasPainterFactory', 'sharedInstance'):
        return [f'if (returned) register_native_borrow(r, returned, {g.ids["QCanvasPainterFactory"]}, r->arguments[0].word);',
                'if (r->error) return true;']
    if key == ('QCanvasPainterFactory', 'create'):
        return _observed(g, m, 'value->painter()')
    if key in {('QCanvasPainterFactory', 'painter'), ('QCanvasPainterFactory', 'paintDriver')} or (
            f['name'] == 'type' and f['return']['name'] == 'QSGMaterialType' and f['return']['pointers'] == 1):
        return _observed(g, m)
    if key in {('QCanvasPainterItemRenderer', 'painter'),
               ('QQuickFramebufferObject::Renderer', 'framebufferObject')}:
        return _observed(g, m, frame=True)
    return []


def after_call(g, m):
    f = m['function']
    key = f['declaring_class'], f['name']
    if key == ('QQuickFramebufferObject', 'createRenderer'):
        return ['if (reclaimed_renderer && !r->error) { r->result.owned_handle = reclaimed_renderer; r->result.borrowed_handle = 0; }']
    if key == ('QCanvasPainterFactory', 'create'):
        return [f'if (canvas_dependency >= 0 && returned && !r->error) commit_retention(canvas_dependency, r->self, {CANVAS_DEPENDENCY_SLOT}u, 0, r->arguments[0].word, nullptr);']
    if key == ('QCanvasPainterFactory', 'destroy'):
        return [f'for (auto &edge : retentions) if (edge.owner == r->self && edge.slot == {CANVAS_DEPENDENCY_SLOT}u) edge = {{}};',
                'schedule_collection();']
    if render_caller_owned_result(f):
        return ['if (r->result.word && !r->error) render_factory_mark(r->result.word);']
    return []


def inventory(g):
    return dict(caller_owned_factories=sorted('::'.join(key) for key in RENDER_CALLER_OWNED_RETURNS),
                borrowed='Context, QRhi, factory or current getter observation; replacement expires the generation',
                frame_views=['QQuickFramebufferObject::Renderer::framebufferObject', 'QCanvasPainterItemRenderer::painter'],
                canvas='Manual factories retain QRhi until destroy; shared factories follow QRhi destruction',
                transfers='Committed consumption retires factory tokens; per-allocation anchors preserve dependency slots and observed proxy children',
                protected_destructors={'QQuickFramebufferObject::createRenderer':
                    'Reclaims an existing Bend proxy through its exact deleter; private native renderers stay Qt-owned'})
