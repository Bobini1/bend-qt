"""Checked non-QObject views returned by documented native owner getters.

These are method lifetime contracts, not class selection. Every dereference
rechecks the originating getter after validating its physical owner. Indexed
model views retain a persistent index, and pointer lists recheck membership.
"""

GETTERS = {
    'QFileDialog': {'iconProvider'},
    'QFileSystemModel': {'iconProvider'},
    'QDesignerCustomWidgetCollectionInterface': {'customWidgets'},
    'QDesignerFormWindowInterface': {'cursor'},
    'QFormBuilder': {'customWidgets'},
    'QHelpContentItem': {'child', 'parent'},
    'QHelpContentModel': {'contentItemAt'},
    'QHttpServer': {'router'},
    'QItemDelegate': {'itemEditorFactory'},
    'QItemEditorFactory': {'defaultFactory'},
    'QStyledItemDelegate': {'itemEditorFactory'},
    'QNetworkAccessManager': {'proxyFactory'},
    'QQmlEngine': {'urlInterceptor', 'urlInterceptors', 'incubationController', 'networkAccessManagerFactory'},
    'QQuickWindow': {'incubationController'},
    'QScxmlCompiler': {'loader'},
    'QScxmlStateMachine': {'loader', 'tableData'},
    'QSensor': {'filters'},
    'QSqlQuery': {'result'},
    'QWebEngineProfile': {'clientCertificateStore', 'scripts', 'settings'},
    'QWebEnginePage': {'scripts', 'settings'},
    'QWebEngineView': {'settings'},
    'QQuickWebEngineProfile': {'clientCertificateStore'},
    'QWebView': {'settings'},
    'QXmlStreamReader': {'entityResolver'},
    'QTextBlock': {'layout', 'userData'},
    'QSyntaxHighlighter': {'currentBlockUserData'},
    'QFutureInterfaceBase': {'mutex'},
    'QStateMachine::WrappedEvent': {'event'},
    'Qt3DAnimation::QCallbackMapping': {'callback'},
    'QLayoutItem': {'spacerItem'},
}


def adapt(g, function):
    owner, method = function['declaring_class'], function['name']
    candidates = GETTERS.get(owner, ())
    if owner == 'QAccessibleInterface':
        import accessible_facets
        candidates = {getter for native, getter, kind in accessible_facets.interfaces(g)}
    if method not in candidates:
        return None
    source = function['return']
    result = g.type(source, result=True)
    element = result['children'][0] if result['kind'] == 'list' else result
    reference = bool(source.get('reference') == 1 and result['kind'] == 'object')
    if element['kind'] != 'object' or not (element.get('pointer') or reference) or g.classes[element['name']].get('qobject'):
        return None
    if function['arguments'] and (owner, method) not in {
            ('QHelpContentItem', 'child'), ('QHelpContentModel', 'contentItemAt')}:
        return None
    return dict(result, native_result_view=dict(owner=owner, method=method,
        static=bool(function['static']), virtual=bool(function.get('virtual')), reference=reference,
        element=element, function=function))


def _provider(g, view, *, list_member=False):
    owner, method = view['owner'], view['method']
    capture, setup, arguments = [], [], ''
    if (owner, method) == ('QHelpContentModel', 'contentItemAt'):
        capture += ['root = !a0->isValid()', 'index = QPersistentModelIndex(*a0)',
                    'epoch = std::make_shared<NativeResultModelEpoch>(self)']
        setup += ['if (epoch->changed || (!root && !index.isValid())) return nullptr;']
        arguments = 'root ? QModelIndex() : QModelIndex(index)'
        g.retention_accessors['native_result_model_epoch'] = '''
struct NativeResultModelEpoch {
    bool changed = false;
    QMetaObject::Connection reset;
    explicit NativeResultModelEpoch(QAbstractItemModel *model) {
        reset = QObject::connect(model, &QAbstractItemModel::modelAboutToBeReset,
            model, [this] { changed = true; });
    }
    ~NativeResultModelEpoch() { QObject::disconnect(reset); }
};
'''
    elif (owner, method) == ('QHelpContentItem', 'child'):
        capture += ['row = int32_t(r->arguments[0].word)']
        setup += ['if (row < 0 || row >= value->childCount()) return nullptr;']
        arguments = 'row'
    import protected_members
    call = protected_members.expression(g, view['function'], [arguments] if arguments else [], 'value')
    if call is None:
        call = f'value->{method}({arguments})' if view['virtual'] else f'value->{owner}::{method}({arguments})'
    if view['reference']:
        call = f'std::addressof({call})'
    if list_member:
        capture += ['pointer']
        result = f'return {call}.contains(pointer) ? pointer : nullptr;'
    else:
        result = 'return ' + call + ';'
    lines = [f'[{", ".join(capture)}](BqtRequest *request, uint32_t id) -> const void * {{',
        f'    auto *value = protected_fields_owner<{owner}>(request, id, {g.ids[owner]});',
        '    if (!value) return nullptr;', *['    ' + line for line in setup], '    ' + result, '}']
    return '\n'.join(lines)


def method_case(g, method):
    f = method['function']
    key = f['declaring_class'], f['name']
    if (f['name'] == 'rendererInterface' and not method['args']
            and method['return'].get('name') == 'QSGRendererInterface'):
        owner = f['declaring_class']
        interface = g.ids['QSGRendererInterface']
        # Render loops can implement this interface through a process-wide
        # QObject. The getter returns a view owned by its supplying window,
        # never a handle owning or observing that hidden implementation.
        return ['NativeCallScope scope;',
            f'auto *self = get<{owner}>(r, r->self, {g.ids[owner]}, false, false);',
            'if (r->error) return true;',
            'auto *pointer = self->rendererInterface();',
            'if (!pointer) return true;',
            f'const auto id = insert(r, pointer, nullptr, {interface}, release_static_native_view, false, NativeTraits<QSGRendererInterface>::cast);',
            'if (!id) return true;',
            'try {',
            '    static_native_views[id & 65535u] = StaticNativeView{id, pointer,',
            '        [owner = r->self](BqtRequest *request) -> const void * {',
            f'            auto *source = get<{owner}>(request, owner, {g.ids[owner]}, false, false);',
            '            return source ? source->rendererInterface() : nullptr;',
            '        }};',
            '    auto *record = entry(id);',
            '    // A new borrowed view records a lifetime boundary, not a Qt ownership transfer.',
            '    record->native_owner = r->self;',
            '    record->validate = validate_static_native_view;',
            '    record->native_observed = true;',
            '    record->render_only = false;',
            '    record->scope_owner = scope_track(r, id, 0);',
            '    native_pointer_publish(id);',
            '} catch (...) { invalidate(id); throw; }',
            'r->result.word = id; r->result.borrowed_handle = id;',
            'return true;']
    if key == ('QSqlDriver', 'createResult') and not method['args']:
        import protected_members
        getter = next(f for f in g.classes['QSqlResult']['functions'] if f['name'] == 'driver' and not f['arguments'])
        actual_driver = protected_members.expression(g, getter, [], 'result') or 'result->driver()'
        slot = g.retention_slots.setdefault('QSqlResult.nativeDriver', len(g.retention_slots) + 1)
        return ['NativeCallScope scope;',
            f'auto *self = get<QSqlDriver>(r, r->self, {g.ids["QSqlDriver"]}, false, false);',
            'if (r->error) return true;',
            f'r->result.word = own(r, self->createResult(), {g.ids["QSqlResult"]});',
            'r->result.owned_handle = r->result.word;',
            'if (r->error || !r->result.word) return true;',
            f'auto *result = get<QSqlResult>(r, r->result.word, {g.ids["QSqlResult"]}, false, false);',
            'if (r->error) return true;',
            f'const auto driver = borrow_const(r, {actual_driver}, {g.ids["QSqlDriver"]});',
            'if (r->error) return true;',
            'BqtRequest claim{}; claim.self = r->result.word;',
            f'int edge = prepare_retention(&claim, {slot}, 0, driver);',
            'if (claim.error) return fail(r, claim.error, claim.message);',
            f'commit_retention(edge, r->result.word, {slot}, 0, driver, nullptr);',
            'return true;']
    if (f['declaring_class'] == 'QSqlQuery' and f['constructor'] and len(method['args']) == 1
            and method['args'][0].get('name') == 'QSqlResult'):
        return ['NativeCallScope scope;',
            'const auto source = r->arguments[0].word;',
            f'auto *result = get<QSqlResult>(r, source, {g.ids["QSqlResult"]}, true, true);',
            'if (r->error) return true;',
            'if (source) {',
            '    if (!can_transfer_handle(r, source)) return true;',
            '    auto *record = entry(source);',
            '    if (!record->owned) return fail(r, EPERM, "QSqlQuery requires ownership of its result");',
            '    if (record->active_calls > 1 || retained(source)) return fail(r, EBUSY, "The SQL result is already in use");',
            '}',
            'auto *query = new QSqlQuery(result);',
            'if (source) set_owned(source, false);',
            'try {',
            f'    r->result.word = own(r, query, {g.ids["QSqlQuery"]});',
            '} catch (...) { if (source && entry(source)) invalidate(source); throw; }',
            'r->result.owned_handle = r->result.word;',
            'if (r->error || !r->result.word) { if (source && entry(source)) invalidate(source); return true; }',
            'if (source) {',
            '    if (!set_native_owner(r, source, r->result.word)) return true;',
            f'    protected_fields_watch(source, result, r->result.word, [](BqtRequest *request, uint32_t id) -> const void * {{',
            f'        auto *value = protected_fields_owner<QSqlQuery>(request, id, {g.ids["QSqlQuery"]});',
            '        return value ? value->result() : nullptr;',
            '    });',
            '}',
            'return true;']
    return None


def before_call(g, method):
    f = method['function']
    if f['declaring_class'] == 'QFutureInterfaceBase' and f['name'] in ('operator=', 'swap'):
        import native_lifetimes
        native_lifetimes.prepare(g)
        lines = ['if (!native_children_idle(r, r->self) || !protected_fields_children_mutable(r, r->self)) return true;']
        if f['name'] == 'swap' and method['args']:
            lines += ['if (!native_children_idle(r, r->arguments[0].word) || !protected_fields_children_mutable(r, r->arguments[0].word)) return true;']
        lines += ['protected_fields_expire_children(r->self);']
        if f['name'] == 'swap' and method['args']:
            lines += ['protected_fields_expire_children(r->arguments[0].word);']
        return lines
    if f['declaring_class'] != 'QSqlQuery' or f['constructor'] or f['static']:
        return []
    if f['name'] not in ('exec', 'prepare', 'clear', 'operator=', 'swap'):
        return []
    import native_lifetimes
    native_lifetimes.prepare(g)
    lines = ['if (!native_children_idle(r, r->self) || !protected_fields_children_mutable(r, r->self)) return true;',
             'protected_fields_expire_children(r->self);']
    if f['name'] == 'swap' and method['args']:
        lines += ['if (!native_children_idle(r, r->arguments[0].word) || !protected_fields_children_mutable(r, r->arguments[0].word)) return true;',
                  'protected_fields_expire_children(r->arguments[0].word);']
    return lines


def store(g, result, expression):
    view = result.get('native_result_view')
    if not view:
        return None
    element = view['element']
    type_id = g.ids[element['name']]
    readonly = str(bool(element.get('readonly') or element.get('native_const'))).lower()
    if view['static']:
        # Static storage needs a scoped descriptor, not an immortal registry
        # QObject anchor. Replacing Qt's default factory expires old views.
        owner, method = view['owner'], view['method']
        return [f'r->result.word = borrow_static_native_view(r, {expression}, {type_id},',
            f'    [](BqtRequest *) -> const void * {{ return {owner}::{method}(); }}, {readonly});',
            'r->result.borrowed_handle = r->result.word;']
    if result['kind'] == 'list':
        provider = _provider(g, view, list_member=True)
        return [f'const auto &native_results = {expression};',
            'r->result = sequence_value(size_t(native_results.size()));',
            'for (qsizetype i = 0; i < native_results.size() && !r->error; ++i) {',
            '    auto *pointer = native_results[i];',
            f'    r->result.items[i].word = protected_fields_borrow(r, pointer, {type_id}, r->self, {provider}, {readonly});',
            '    r->result.items[i].borrowed_handle = r->result.items[i].word;', '}']
    return [f'r->result.word = protected_fields_borrow(r, {expression}, {type_id}, r->self, {_provider(g, view)}, {readonly});',
            'r->result.borrowed_handle = r->result.word;']


def annotate(method):
    view = method.get('native_return', method['return']).get('native_result_view')
    if view:
        method['native_result_lifetime'] = dict(policy='checked native owner getter',
            owner=view['owner'], getter=view['method'],
            invalidation='owner destruction, native storage replacement or list removal',
            arguments='persistent model index' if view['method'] == 'contentItemAt' else 'copied native index' if view['method'] == 'child' else None)
