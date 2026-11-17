"""Bend-specific representations and safety policies, independent of class discovery.

PySide's injected Python/C API code is never compiled into this package.
The small converter inventory below describes representations, not Qt API coverage.
"""


def application_initializers(modules):
    """Qt requires these module initializers before the host application."""
    return [namespace + '::initialize();' for module, namespace in (
        ('QtWebEngineQuick', 'QtWebEngineQuick'), ('QtWebView', 'QtWebView')) if module in modules]


def initialized_application_call(g, method):
    function = method['function']
    if function['name'] == 'initialize' and function['declaring_class'] in ('QtWebEngineQuick', 'QtWebView'):
        if function['declaring_class'] in g.profile['qt_modules']:
            return ['// Host startup already ran this module before QApplication.', 'if (application) return true;']
    return []


def runtime_type_dependencies(selected=()):
    """Registry carriers required by the common lifetime/metadata policies.

    These are additive implementation dependencies. The complete owning
    module API is discovered independently from the pinned PySide model.
    """
    import generic_arguments
    import boundary_finders
    import metadata_lifetimes
    import model_indices
    import value_lifetimes
    owners = {
        'QStandardItem': {'QStandardItemModel', 'QAbstractItemModel'},
        'QTreeWidgetItem': {'QTreeWidget', 'QAbstractItemModel'},
        'QListWidgetItem': {'QListWidget', 'QAbstractItemModel'},
        'QTableWidgetItem': {'QTableWidget', 'QAbstractItemModel'},
        'QGraphicsItem': {'QGraphicsScene', 'QGraphicsObject'},
        'QLayoutItem': {'QLayout'},
        # Role spans check their origin against a single QModelRoleData.
        'QModelRoleDataSpan': {'QModelRoleData'},
        # An engine enables the QML callback bridge and its list views.
        'QQmlEngine': {'QQmlListReference'},
        'QRhi': {'QRhiResource', 'QRhiResourceUpdateBatch', 'QRhiCommandBuffer',
                 'QRhiReadbackResult', 'QRhiBuffer'},
    }
    observed = set().union(*(value for name, value in owners.items() if name in selected))
    return (observed | generic_arguments.TYPES | boundary_finders.ORIGIN_TYPES | metadata_lifetimes.VALUES | model_indices.TYPES
            | value_lifetimes.TYPES | {'QMetaType', 'QMetaObject', 'QAbstractItemModel',
                'QPersistentModelIndex', 'QTextDocument', 'QTreeWidget', 'QTreeWidgetItem',
                'QPointerEvent', 'QEventPoint', 'QLoggingCategory', 'QOpenGLContext'})

# These pointers are borrowed only for the duration of the documented native
# operation. They initialize or mutate the supplied value; none stores its
# address. The contracts apply to declarations, including inherited receivers.
# Element types remain discovered from the pinned upstream model.
VALUE_POINTER_CALLS = {
    ('QAbstractItemView', 'initViewItemOption'): {0: ('QStyleOptionViewItem', False)},
    ('QStyledItemDelegate', 'initStyleOption'): {0: ('QStyleOptionViewItem', False)},
    ('QGraphicsEffect', 'sourcePixmap'): {1: ('QPoint', True)},
    ('QHttpServerRouterRule', 'matches'): {1: ('QRegularExpressionMatch', False)},
    ('QModbusClient', 'processResponse'): {1: ('QModbusDataUnit', False)},
    ('QModbusClient', 'processPrivateResponse'): {1: ('QModbusDataUnit', False)},
    ('QModbusServer', 'readData'): {0: ('QModbusDataUnit', True)},
    ('QOAuth1', 'setup'): {0: ('QNetworkRequest', False)},
    ('QPaintDevice', 'redirected'): {0: ('QPoint', True)},
    ('QQuickItem', 'updatePaintNode'): {1: ('QQuickItem::UpdatePaintNodeData', False)},
    ('QTextToSpeech', 'allVoices'): {0: ('QLocale', True)},
}


# These public factories return fresh allocations to their native caller.
# Their reverse calls transfer those allocations to Qt's renderer. Borrowed
# renderer getters and updatePaintNode's existing-node alias are separate.
RENDER_CALLER_OWNED_RETURNS = {
    ('QQuickWindow', 'createImageNode'), ('QQuickWindow', 'createNinePatchNode'),
    ('QQuickWindow', 'createRectangleNode'), ('QQuickWindow', 'createTextNode'),
    ('QSGMaterial', 'createShader'), ('QOpenGLTexture', 'createTextureView'),
    ('QQuickFramebufferObject::Renderer', 'createFramebufferObject'),
    ('QQuickRhiItem', 'createRenderer'),
    ('QCanvasPainterItem', 'createItemRenderer'), ('QCanvasPainterItem', 'createRenderer'),
}


def render_caller_owned_result(f):
    return ((f['declaring_class'], f['name']) in RENDER_CALLER_OWNED_RETURNS or
            (f['name'] == 'createShader' and f['return']['name'] == 'QSGMaterialShader'
             and f['return']['pointers'] == 1))


def install_carriers(classes, selected):
    import accessible_facets
    accessible_facets.install(classes, selected)
    from memory_views import install
    install(classes, selected)
    # Upstream treats QVariant as a primitive with a Python converter. Bend uses
    # a checked, owning value handle, so it needs a registry type as well.
    for name in ('QVariant', 'QJsonObject'):
        if name in selected:
            continue
        classes[name] = {'name': name, 'object': False, 'value': True,
            'qobject': False, 'public_destructor': True, 'abstract': False,
            'copyable': True, 'qt_metatype_defined': True,
            'bases': [], 'functions': [], 'enums': [], 'adapter': True,
            'native_namespace': '::'}
        selected.append(name)
    # PySide classifies QCollator as an object for Python wrapper behavior,
    # although its public Qt API is an independently copyable native value.
    collator = classes.get('QCollator')
    if collator and collator.get('public_destructor') and collator.get('copyable'):
        collator.update(object=False, value=True)
        if 'QCollator' not in selected:
            selected.append('QCollator')
    from representations import install_shared
    install_shared(classes, selected)
    import gl_sync
    gl_sync.install(classes, selected)
    import native_interop
    native_interop.install(classes, selected)
    import gl_retained
    gl_retained.install(classes, selected)
    import byte_iterators
    byte_iterators.install(classes, selected)
    import meta_storage
    meta_storage.install(classes, selected)
    import borrowed_values
    borrowed_values.install(classes, selected)
    import role_data
    role_data.install(classes, selected)
    import model_data
    model_data.install(classes, selected)
    import native_events
    native_events.install(classes, selected)
    import image_buffers
    image_buffers.install(classes, selected)
    import incubation
    incubation.install(classes, selected)
    import typed_views
    typed_views.install(classes, selected)
    selected.sort()


def excluded_internal_api(f):
    if (f['name'] == 'sharedPainter' and not f['arguments']
            and f['return']['name'] == 'QPainter' and f['return']['pointers'] == 1):
        return 'Qt-internal painter-sharing hook excluded from the public API'
    return None


def native_member_parameters(function, owner):
    """Select an exact overload when a temporary makes a direct call ambiguous."""
    if function['static'] or function['operator']:
        return None
    if owner == 'QScatterDataProxy' and function['name'] in ('addItem', 'addItems') and len(function['arguments']) == 1:
        # Qt 6.12 Graphs declares both value and && overloads, but exports only
        # the value forms. Select those for both API declarations: an owning
        # Bend value already supplies an independent copy to the native call.
        return function['arguments'][0]['type']['cpp'].replace('&&', '').strip()
    if function.get('rvalue_reference'):
        return ', '.join(argument['type']['cpp'] for argument in function['arguments'])
    return None


def method_policy(name, f, bases):
    internal = excluded_internal_api(f)
    if internal:
        return internal
    if f['declaring_class'] == 'QVideoFrame' and (f['name'] == 'videoBuffer' or (f['constructor'] and f['arguments'] and f['arguments'][0]['type']['name'] == 'QAbstractVideoBuffer')):
        return 'Qt 6.12 marks the raw buffer constructor and getter internal and deprecated; use QVideoFrame.fromVideoBuffer consuming the public unique_ptr constructor'
    if f['declaring_class'] == 'QProcess' and f['name'] in ('setChildProcessModifier', 'failChildProcessModifier'):
        return 'Post-fork child-only API cannot enter the Bend/Qt scheduler; use declarative UnixProcessParameters for native child setup'
    if name == 'QMetaObject' and f['constructor']:
        return 'Metaobjects require a native QObject or type origin; use QObject.metaObject or QMetaType.metaObject'
    if f['declaring_class'] == 'QSGRenderNode' and f['name'] == 'projectionMatrix' and f['arguments']:
        return 'Qt-internal indexed projection getter has no public extent; use the documented zero-argument snapshot getter'
    audited_parent_rules = {
        ('QGraphicsScene', 'createItemGroup'), ('QListWidget', 'setItemWidget'),
        ('QTreeWidget', 'addTopLevelItem'),
    }
    if name.startswith('QFuture') and f['name'] in (
            'result', 'results', 'resultAt', 'takeResult'):
        return 'Potentially blocking future access requires the nonblocking Future_T.resultAt/await adapter on the main thread'
    if f['constructor'] and (name == 'QCoreApplication' or 'QCoreApplication' in bases):
        return 'The package owns the single Qt application'
    for policy in f['policies']:
        if policy['index'] > 0 and policy['parent_action'] and not (policy['parent_action'] in (1, 2) and policy['parent_index'] == -1) and (f['declaring_class'], f['name']) not in audited_parent_rules:
            return 'Retained argument/ownership-transfer adapter required'
        if policy['index'] == -1 and (policy['parent_action'] or policy['reference_count']) and f['name'] != 'setParent':
            # QDrag's source is its native QObject parent. The registry observes
            # that parent at construction; no separate wrapper pin is required.
            if f['constructor'] and f['declaring_class'] in ('QDrag', 'QRubberBand', 'QGraphicsProxyWidget'):
                continue
            if f['constructor'] and any(base in (name, *bases) for base in ('QGraphicsItem', 'QTreeWidgetItem', 'QListWidgetItem', 'QTableWidgetItem')):
                continue
            if f['constructor']:
                # Generic constructor dependency pins are installed from pointer
                # inputs; actual QObject parents are excluded after construction.
                continue
            if (f['declaring_class'], f['name']) in {
                    ('QCompleter', 'setWidget'), ('QQuickItem', 'setParentItem'),
                    ('QLayout', 'parentWidget'), ('QSyntaxHighlighter', 'document'),
                    ('QGraphicsItem', 'setParentItem'), ('QGraphicsItem', 'parentItem'),
                    ('QGraphicsItem', 'parentWidget'), ('QGraphicsItem', 'scene'),
                    ('QGraphicsLayoutItem', 'parentLayoutItem'),
                    ('QAbstractState', 'machine'),
                    ('QWizardPage', 'wizard'),
                    ('Qt3DCore::QEntity', 'addComponent'), ('Qt3DCore::QJoint', 'addChildJoint'),
                    ('Qt3DCore::QAspectEngine', 'registerAspect')}:
                continue
            return 'Receiver retention requires a Bend lifetime adapter'
    return None


def transfers_argument(f, policy):
    # This PySide virtual-factory rule keeps the editor's parent wrapper alive.
    # Calling the native factory does not transfer the parent QWidget to Qt.
    if (f['name'] == 'createEditor' and f['declaring_class'] in
            ('QAbstractItemDelegate', 'QItemDelegate', 'QStyledItemDelegate') and policy['index'] == 1):
        return False
    return policy['index'] > 0 and policy['target_ownership'] in (2, 3)


def owns_result(f):
    if render_caller_owned_result(f):
        return True
    # Qt's clone contract allocates a new independently owned native object.
    if f['name'] == 'clone' and f['declaring_class'] in ('QEvent', 'QIconEngine'):
        return True
    # These are borrowed getters. PySide's wrapper ownership annotation does
    # not mean QDrag gives its source/target QObject to the native caller.
    if f['declaring_class'] == 'QDrag' and f['name'] in ('source', 'target'):
        return False
    if (f['declaring_class'], f['name']) in {('QLayout', 'parentWidget'), ('QSyntaxHighlighter', 'document'),
            ('QWizardPage', 'wizard'), ('QTextDocument', 'createObject'),
            ('QGraphicsItem', 'parentItem'), ('QGraphicsItem', 'parentWidget'), ('QGraphicsItem', 'scene'),
            ('QGraphicsLayoutItem', 'parentLayoutItem'),
            ('QAbstractState', 'machine'), ('QAbstractTransition', 'targetState'), ('QAbstractTransition', 'targetStates')}:
        return False
    # The native create()/beginCreate() contract transfers the QML root to its
    # caller. PySide attaches this rule to a synthetic Python convenience method.
    return (f['constructor'] or
            (f['declaring_class'] == 'QMetaObject' and f['name'] == 'newInstance') or
            (f['declaring_class'] == 'QQmlComponent' and f['name'] in ('create', 'beginCreate')) or
            (f['declaring_class'] == 'QQmlIncubator' and f['name'] == 'object') or
            (f['declaring_class'] == 'QTemporaryFile' and f['name'] == 'createNativeFile') or
            (f['declaring_class'] == 'QQuickTextureFactory' and f['name'] == 'textureFactoryForImage') or
            (f['declaring_class'] == 'QSqlDriver' and f['name'] == 'createResult') or
            (f['declaring_class'], f['name']) in (('QItemEditorFactory', 'createEditor'), ('QItemEditorCreatorBase', 'createWidget')) or
            (f['declaring_class'], f['name']) in (('QMainWindow', 'takeCentralWidget'), ('QScrollArea', 'takeWidget')) or
            (f['declaring_class'] in ('QAbstractItemDelegate', 'QItemDelegate', 'QStyledItemDelegate') and f['name'] == 'createEditor') or
            any(p['index'] == 0 and (p['target_ownership'] == 2 or p['parent_action'] == 2) for p in f['policies']))


def raw_keyframe_iterator(f):
    return f['declaring_class'] == 'Qt3DAnimation::QChannelComponent' and f['name'] in ('begin', 'cbegin', 'end', 'cend')


def static_native_result(f):
    # These accessors return process-wide native services, never new objects.
    return (f['declaring_class'], f['name']) in {
        ('QRandomGenerator', 'global'), ('QRandomGenerator', 'system'),
        ('QRandomGenerator64', 'global'), ('QRandomGenerator64', 'system'),
        ('QLoggingCategory', 'defaultCategory'),
        ('QtROClientFactory', 'instance'), ('QtROServerFactory', 'instance'),
    }


def reverse_transfers_result(f):
    if f['name'] == 'clone' and f['declaring_class'] in ('QEvent', 'QIconEngine'):
        return True
    if render_caller_owned_result(f):
        return True
    # Upstream QtQuick XML leaves these unannotated. Qt owns the image factory:
    # https://doc.qt.io/qt-6/qquickimageresponse.html#textureFactory
    # Qt 6.12 qquickpixmapcache.cpp stores requestTexture's return in
    # QQuickPixmapData; its destructor deletes textureFactory (lines 364-366,
    # 1590-1595). textureFactoryForImage returns a fresh factory in
    # qquickimageprovider.cpp:76-83, hence the matching forward policy above.
    return (any(p['index'] == 0 and p['native_ownership'] == 3 for p in f['policies']) or
            (f['declaring_class'], f['name']) in {
                ('QQuickImageProvider', 'requestTexture'), ('QQuickImageResponse', 'textureFactory'),
                ('QSqlDriver', 'createResult'),
                ('QItemEditorCreatorBase', 'createWidget'), ('QItemEditorFactory', 'createEditor'),
                # https://doc.qt.io/qt-6/qcanbusfactory.html#createDevice
                ('QCanBusFactory', 'createDevice')})


def byte_list(g):
    byte = g.conversions.register({'kind': 'u32', 'bend': 'U32', 'raw': 'U32', 'cpp': 'quint8'})
    return g.conversions.register({'kind': 'list', 'name': 'QList', 'children': [byte],
        'bend': 'List<&2, U32>', 'raw': 'Wire', 'cpp': 'QList<quint8>', 'codec': 'List_U32'})


def matrix_list(g):
    real = g.conversions.register({'kind': 'real', 'bend': 'F64', 'raw': 'U32 & U32', 'cpp': 'float'})
    return g.conversions.register({'kind': 'list', 'name': 'QList', 'children': [real],
        'bend': 'List<&2, F64>', 'raw': 'Wire', 'cpp': 'QList<float>', 'codec': 'List_F64'})


def matrix_shape(name):
    import re
    match = re.fullmatch(r'QMatrix([234])x([234])', name)
    return tuple(map(int, match.groups())) if match else None


def optional_uint64(g):
    scalar = dict(name='quint64', cpp='quint64', const=False, pointers=0, reference=0,
                  container=False, enum=False, flags=False, instantiations=[])
    return g.conversions.container(dict(scalar, name='std::optional', cpp='std::optional<quint64>',
                                       instantiations=[scalar]), True)


def prepare_adapters(g):
    import gl_retained
    gl_retained.prepare(g)
    # Bend checks definitions in order. Register helper codecs before the codec
    # definitions, then emit the effect wrappers only after those definitions.
    if 'QByteArray' in g.ids:
        byte_list(g)
    if any(matrix_shape(name) for name in g.selected):
        matrix_list(g)
    if 'QMetaEnum' in g.ids:
        optional_uint64(g)
    import futures
    futures.prepare(g)


def emit_adapters(g):
    import variant_values
    variant_values.emit(g)
    import meta_storage
    meta_storage.emit(g)
    import native_interop
    native_interop.emit(g)
    import gl_retained
    gl_retained.emit(g)
    import byte_iterators
    byte_iterators.emit(g)
    import borrowed_values
    borrowed_values.emit(g)
    import futures
    futures.emit(g)
    import runnable_jobs
    runnable_jobs.emit(g)
    import memory_views
    memory_views.emit(g)
    string = {'kind': 'string', 'bend': 'String', 'raw': 'String'}
    boolean = {'kind': 'bool', 'bend': 'Bool', 'raw': 'U32'}
    real = {'kind': 'real', 'bend': 'F64', 'raw': 'U32 & U32'}
    def handle(name):
        return {'kind': 'value', 'name': name, 'bend': name.replace('::', '.'), 'raw': 'U32'}
    def emit(name, params, result, lines):
        op = g.next_id
        g.next_id += 1
        g.cases.append(f'case {op}: {{\n' + '\n'.join('    ' + s for s in lines) + '\n    return true;\n}')
        g.emit_effect(name.replace('::', '.'), params, result, op)
    for name in g.selected:
        c = g.classes[name]
        if not c.get('shared_cpp'):
            continue
        from module_partitions import exports_class
        if not exports_class(g, name):
            continue
        shared = handle(name)
        emit(name + '.new', [], shared,
             [f'r->result.word = own(r, new {name}(), {g.ids[name]});'])
        get = [f'auto *value = get<{name}>(r, r->arguments[0].word, {g.ids[name]});', 'if (r->error) return true;']
        emit(name + '.clone', [('value', shared)], shared,
             get + [f'r->result.word = own(r, new {name}(*value), {g.ids[name]});'])
        emit(name + '.isNull', [('value', shared)], boolean,
             get + ['r->result.word = value->isNull();'])
        target = c['shared_target']
        if target in g.ids:
            target_class = g.classes[target]
            if target_class.get('native_default_constructible'):
                # The Qt control block constructs and owns its pointee from the
                # start. No raw handle is consumed, even if allocation throws.
                emit(name + '.create', [], shared,
                     [f'r->result.word = own(r, new {name}({name}::create()), {g.ids[name]});'])
            emit(name + '.data', [('value', shared)], handle(target),
                 get + [f'r->result.word = borrow_shared(r, value->data(), {g.ids[target]}, r->arguments[0].word);'])
    if 'QMetaEnum' in g.ids:
        optional = optional_uint64(g)
        valid_name = ['if (r->arguments[0].size && std::memchr(r->arguments[0].text, 0, r->arguments[0].size)) return fail(r, EINVAL, "Enum name contains an embedded NUL");']
        emit('QMetaEnum.fromQtName', [('name', string)], handle('QMetaEnum'),
             valid_name + ['int index = Qt::staticMetaObject.indexOfEnumerator(r->arguments[0].text);',
                           'if (index < 0) return fail(r, ENOENT, "Qt namespace enum was not found");',
                           f'r->result.word = own(r, new QMetaEnum(Qt::staticMetaObject.enumerator(index)), {g.ids["QMetaEnum"]});'])
        get_enum = [f'auto *value = get<QMetaEnum>(r, r->arguments[0].word, {g.ids["QMetaEnum"]});', 'if (r->error) return true;']
        for method in ('keyToValue64', 'keysToValue64'):
            # Upstream PySide replaces these optional-returning entry points
            # with Python integer/bool convenience conversions. Preserve the
            # actual Qt 6.12 optional contract in the Bend adaptation layer.
            emit('QMetaEnum.' + method, [('value', handle('QMetaEnum')), ('key', string)], optional,
                 get_enum + ['if (r->arguments[1].size && std::memchr(r->arguments[1].text, 0, r->arguments[1].size)) return fail(r, EINVAL, "Enum key contains an embedded NUL");',
                             f'r->result = write_{optional["native_codec"]}(r, value->{method}(r->arguments[1].text));'])
        emit('QMetaEnum.value64', [('value', handle('QMetaEnum')), ('index', {'kind': 'i32', 'bend': 'Int32', 'raw': 'U32'})], optional,
             get_enum + [f'r->result = write_{optional["native_codec"]}(r, value->value64(int32_t(r->arguments[1].word)));'])
    text = 'QString::fromUtf8(r->arguments[0].text, qsizetype(r->arguments[0].size))'
    emit('F64.fromString', [('text', string)], real,
         ['bool ok = false;', f'double n = {text}.toDouble(&ok);',
          'if (!ok) return fail(r, EINVAL, "Invalid F64 decimal");', 'r->result = real_bits(n);'])
    emit('F64.toString', [('value', real)], string,
         ["r->result = string_value(QString::number(real_value(r->arguments[0]), 'g', 17));"])
    for name, operator in [('add', '+'), ('subtract', '-'), ('multiply', '*'), ('divide', '/')]:
        emit('F64.' + name, [('left', real), ('right', real)], real,
             [f'r->result = real_bits(real_value(r->arguments[0]) {operator} real_value(r->arguments[1]));'])
    emit('F64.equal', [('left', real), ('right', real)], boolean,
         ['r->result.word = real_value(r->arguments[0]) == real_value(r->arguments[1]);'])
    if 'QByteArray' in g.ids:
        bytes_type = byte_list(g)
        emit('QByteArray.allocate', [('size', {'kind': 'i64', 'bend': 'Int64', 'raw': 'U32 & U32'})], handle('QByteArray'),
             ['int64_t size = int64_t(wide_bits(r->arguments[0]));',
              'if (size < 0 || uint64_t(size) > uint64_t(std::numeric_limits<qsizetype>::max())) return fail(r, ERANGE, "Byte buffer size is outside Qt range");',
              f'r->result.word = own(r, new QByteArray(qsizetype(size), char(0)), {g.ids["QByteArray"]});'])
        emit('QByteArray.fromBytes', [('bytes', bytes_type)], handle('QByteArray'),
             [f'auto input = read_{bytes_type["native_codec"]}(r, r->arguments[0]);',
              'if (!input) return true;', 'QByteArray bytes;', 'bytes.reserve(input->size());',
              'for (quint8 byte : *input) bytes.append(static_cast<char>(byte));',
              f'r->result.word = own(r, new QByteArray(std::move(bytes)), {g.ids["QByteArray"]});'])
        emit('QByteArray.toBytes', [('value', handle('QByteArray'))], bytes_type,
             [f'auto *v = get<QByteArray>(r, r->arguments[0].word, {g.ids["QByteArray"]});',
              'if (r->error) return true;', 'r->result = sequence_value(size_t(v->size()));',
              'for (qsizetype i = 0; i < v->size(); ++i)',
              '    r->result.items[size_t(i)].word = static_cast<unsigned char>(v->at(i));'])
        emit('QByteArray.fromUtf8', [('text', string)], handle('QByteArray'),
             [f'r->result.word = own(r, new QByteArray(r->arguments[0].text, qsizetype(r->arguments[0].size)), {g.ids["QByteArray"]});'])
        emit('QByteArray.utf8', [('value', handle('QByteArray'))], string,
             [f'auto *v = get<QByteArray>(r, r->arguments[0].word, {g.ids["QByteArray"]});',
              'if (r->error) return true;', 'r->result = string_value(QString::fromUtf8(*v));'])
    for name in g.selected:
        shape = matrix_shape(name)
        if not shape:
            continue
        count = shape[0] * shape[1]
        values = matrix_list(g)
        emit(name + '.fromValues', [('values', values)], handle(name),
             [f'auto values = read_{values["native_codec"]}(r, r->arguments[0]);',
              'if (!values) return true;',
              f'if (values->size() != {count}) return fail(r, EINVAL, "Matrix requires exactly {count} row-major values");',
              f'r->result.word = own(r, new {name}(values->constData()), {g.ids[name]});'])
        emit(name + '.toValues', [('value', handle(name))], values,
             [f'auto *value = get<{name}>(r, r->arguments[0].word, {g.ids[name]});',
              'if (r->error) return true;', f'QList<float> values({count});',
              'value->copyDataTo(values.data());',
              f'r->result = write_{values["native_codec"]}(r, values);'])
    if 'QJsonObject' in g.ids and 'QJsonValue' in g.ids:
        emit('QJsonObject.new', [], handle('QJsonObject'),
             [f'r->result.word = own(r, new QJsonObject(), {g.ids["QJsonObject"]});'])
        obj = [f'auto *v = get<QJsonObject>(r, r->arguments[0].word, {g.ids["QJsonObject"]});',
               'if (r->error) return true;']
        emit('QJsonObject.isEmpty', [('value', handle('QJsonObject'))], boolean,
             obj + ['r->result.word = v->isEmpty();'])
        emit('QJsonObject.size', [('value', handle('QJsonObject'))], {'kind': 'u32', 'bend': 'U32', 'raw': 'U32'},
             obj + ['r->result.word = uint32_t(v->size());'])
        key = 'QString::fromUtf8(r->arguments[1].text, qsizetype(r->arguments[1].size))'
        emit('QJsonObject.contains', [('value', handle('QJsonObject')), ('key', string)], boolean,
             obj + [f'r->result.word = v->contains({key});'])
        emit('QJsonObject.value', [('value', handle('QJsonObject')), ('key', string)], handle('QJsonValue'),
             obj + [f'r->result.word = own(r, new QJsonValue(v->value({key})), {g.ids["QJsonValue"]});'])
        emit('QJsonObject.insert', [('value', handle('QJsonObject')), ('key', string), ('item', handle('QJsonValue'))], {'kind': 'void', 'bend': 'Unit', 'raw': 'Unit'},
             obj + [f'auto *item = get<QJsonValue>(r, r->arguments[2].word, {g.ids["QJsonValue"]});',
                    'if (r->error) return true;', f'v->insert({key}, *item);'])
        emit('QJsonObject.remove', [('value', handle('QJsonObject')), ('key', string)], {'kind': 'void', 'bend': 'Unit', 'raw': 'Unit'},
             obj + [f'v->remove({key});'])
        emit('QJsonObject.toJson', [('value', handle('QJsonObject'))], handle('QByteArray'),
             obj + [f'r->result.word = own(r, new QByteArray(QJsonDocument(*v).toJson(QJsonDocument::Compact)), {g.ids["QByteArray"]});'])
        emit('QJsonObject.fromJson', [('data', handle('QByteArray'))], handle('QJsonObject'),
             [f'auto *data = get<QByteArray>(r, r->arguments[0].word, {g.ids["QByteArray"]});',
              'if (r->error) return true;', 'QJsonParseError error;',
              'auto doc = QJsonDocument::fromJson(*data, &error);',
              'if (error.error != QJsonParseError::NoError || !doc.isObject()) return fail(r, EINVAL, "JSON input is not a valid object");',
              f'r->result.word = own(r, new QJsonObject(doc.object()), {g.ids["QJsonObject"]});'])
    for name, typ, value, meta, conversion in [
            ('F64', real, 'real_value(r->arguments[0])', 'Double', 'real_bits(v->toDouble())'),
            ('Float', real, 'float(real_value(r->arguments[0]))', 'Float', 'real_bits(v->toFloat())'),
            ('Int32', {'kind': 'i32', 'bend': 'Int32', 'raw': 'U32'}, 'int32_t(r->arguments[0].word)', 'Int', 'BqtValue{uint32_t(v->toInt()), nullptr, 0}'),
            ('UInt32', {'kind': 'u32', 'bend': 'U32', 'raw': 'U32'}, 'uint32_t(r->arguments[0].word)', 'UInt', 'BqtValue{v->toUInt(), nullptr, 0}'),
            ('Int64', {'kind': 'i64', 'bend': 'Int64', 'raw': 'U32 & U32'}, 'qlonglong(wide_bits(r->arguments[0]))', 'LongLong', 'wide_value(uint64_t(v->toLongLong()))'),
            ('UInt64', {'kind': 'u64', 'bend': 'UInt64', 'raw': 'U32 & U32'}, 'qulonglong(wide_bits(r->arguments[0]))', 'ULongLong', 'wide_value(v->toULongLong())'),
            ('String', string, text, 'QString', 'string_value(v->toString())'),
            ('Bool', boolean, 'bool(r->arguments[0].word)', 'Bool', 'BqtValue{uint32_t(v->toBool()), nullptr, 0}')]:
        emit('QVariant.from' + name, [('value', typ)], handle('QVariant'),
             [f'r->result.word = own(r, new QVariant({value}), {g.ids["QVariant"]});'])
        emit('QVariant.to' + name, [('value', handle('QVariant'))], typ,
             [f'auto *v = get<QVariant>(r, r->arguments[0].word, {g.ids["QVariant"]});',
              'if (r->error) return true;'] +
             ([] if name == 'String' else [f'if (v->typeId() != QMetaType::{meta}) return fail(r, EINVAL, "QVariant has a different type");']) +
             [
              f'r->result = {conversion};'])
    # Runtime-checked downcasts preserve identity and do not acquire ownership.
    for name in g.selected:
        if not g.classes[name]['qobject']:
            for base in g.all_bases(name):
                if g.classes[name]['object']:
                    continue  # Native identity upcasts are emitted by prelude().
                if g.classes[base]['object']:
                    emit(name.replace('::', '.') + '.as_' + base.replace('::', '_'),
                         [('value', handle(name))], handle(base),
                         [f'get<{base}>(r, r->arguments[0].word, {g.ids[base]});',
                          'if (r->error) return true;', 'r->result.word = r->arguments[0].word;'])
                    continue
                emit(name.replace('::', '.') + '.as_' + base.replace('::', '_'),
                     [('value', handle(name))], handle(base),
                     [f'auto *v = get<{name}>(r, r->arguments[0].word, {g.ids[name]});',
                      'if (r->error) return true;',
                      f'r->result.word = own(r, new {base}(static_cast<const {base} &>(*v)), {g.ids[base]});'])
            continue
        emit(name.replace('::', '.') + '.cast', [('value', handle('QObject'))], handle(name),
             [f'get<{name}>(r, r->arguments[0].word, {g.ids[name]});',
              'if (r->error) return true;', 'r->result.word = r->arguments[0].word;'])
def native_header_support(modules):
    # QtRemoteObjects declares QHash<int, QByteArray>'s metatype registration
    # helper without exporting its implementation. Other bindings instantiate
    # this public container too; provide Qt's header-defined implementation in
    # our hidden payload instead of importing the library's private symbol.
    if 'QtRemoteObjects' in modules:
        return '\ninline QT_IMPL_METATYPE_EXTERN(QIntHash)\n'
    return ''

