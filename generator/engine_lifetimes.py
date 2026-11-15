"""Observed aliases for Qt-owned paint and print engines.

Engine identities are borrowed, never adopted. A native getter checks the
current pointer before a view is used; replacement expires the old generation.
"""
import protected_members

BORROWED_GETTERS = {
    ('QPainter', 'device'), ('QPaintEngine', 'paintDevice'),
    ('QPaintEngine', 'painter'), ('QPaintEngineState', 'painter'),
    ('QPaintDevice', 'redirected'),
    ('QBackingStore', 'paintDevice'), ('QAbstractTextDocumentLayout', 'paintDevice'),
    ('QAbstractPrintDialog', 'printer'), ('QPageSetupDialog', 'printer'),
    ('QPrintPreviewDialog', 'printer'),
    ('QWidget', 'backingStore'),
}


def _getter(g, method):
    function = method['function']
    result = method.get('native_return', method['return'])
    engine = not function['arguments'] and function['name'] in ('paintEngine', 'printEngine')
    audited = (function['declaring_class'], function['name']) in BORROWED_GETTERS
    return bool(not function['static'] and not function['constructor'] and (engine or audited)
                and result['kind'] == 'object' and result.get('pointer') and not result.get('owned')
                and not g.classes[result['name']].get('qobject'))


def before_result(g, method):
    if not _getter(g, method):
        return []
    function = method['function']
    owner = function['declaring_class']
    name = function['name']
    key = owner + '.' + name
    helper = 'observed_engine_' + owner.replace('::', '_') + '_' + name
    # Preserve native derived dispatch, including a QWidget view of a GL widget.
    # Known Bend-owned results are reused before an observer is attached.
    arguments = ['&offset'] if name == 'redirected' else []
    access = protected_members.expression(g, function, arguments, 'value')
    if access is None:
        access = ('value->' + name if function.get('virtual') else f'value->{owner}::{name}')
        access += '(' + ', '.join(arguments) + ')'
    g.retention_accessors['engine_alias_' + key] = f'''
static const void *{helper}(BqtRequest *request, uint32_t id) {{
    auto *value = protected_fields_owner<{owner}>(request, id, {g.ids[owner]});
    if (!value) return nullptr;
    {'QPoint offset;' if name == 'redirected' else ''}
    return {access};
}}
'''
    result = method.get('native_return', method['return'])
    return [f'if (returned) protected_fields_borrow(r, returned, {g.ids[result["name"]]}, r->self, {helper}, false);',
            'if (r->error) return true;']


def _replacement_condition(g, method):
    function = method['function']
    if function['constructor'] or function['static'] or function['const'] or function['signal']:
        return None
    owner, name = function['declaring_class'], function['name']
    if owner == 'QPrinter':
        if name == 'setOutputFormat':
            argument = g.argument(method['args'][0], 0)[1]
            return f'self->outputFormat() != {argument}'
        elif name == 'setPdfVersion':
            argument = g.argument(method['args'][0], 0)[1]
            return f'self->pdfVersion() != {argument} && self->outputFormat() == QPrinter::PdfFormat'
        elif name in ('setEngines', 'setPrinterName', 'setOutputFileName'):
            return 'true'
    elif owner in ('QImage', 'QPixmap', 'QBitmap', 'QPicture', 'QBackingStore'):
        return 'true'
    elif owner == 'QPainter' and name in ('begin', 'end'):
        return 'true'
    elif owner == 'QWidget' and name in ('setParent', 'setWindowFlags', 'setWindowFlag', 'create', 'destroy'):
        return 'true'
    return None


def before_call(g, method):
    condition = _replacement_condition(g, method)
    if condition is None:
        return []
    import native_lifetimes
    native_lifetimes.prepare(g)
    return [f'if ({condition}) {{',
            '    if (!native_children_idle(r, r->self)) return true;',
            '    if (!protected_fields_children_mutable(r, r->self)) return true;', '}']


def before_native(g, method):
    # Wait until argument, parenting and retention preflight have all passed.
    # Revocation precedes Qt's potentially same-address allocation replacement.
    condition = _replacement_condition(g, method)
    return [f'if ({condition}) protected_fields_expire_children(r->self);'] if condition is not None else []
