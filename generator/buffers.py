"""Audited synchronous C-pointer conversions.

An array annotation alone is not a size contract. These policies describe
native memory use, independently of class discovery. Byte outputs mutate an
explicit caller-sized QByteArray. Counts stay explicit even where PySide
derives them; each call checks its native extent before exposing any pointer.
"""
import re
import gl_buffers
import allocated_buffers
import native_interop
import gl_raw_mappings


COPY_BYTES = {
    'QBuffer': {'setData'},
    'QByteArray': {'QByteArray', 'append', 'prepend', 'insert', 'replace'},
    'QByteArrayMatcher': {'QByteArrayMatcher', 'indexIn'},
    'QCryptographicHash': {'addData'},
    'QMessageAuthenticationCode': {'addData'},
    'QDataStream': {'readRawData', 'writeRawData', 'writeBytes'},
    'QIODevice': {'read', 'readLine', 'peek', 'write', 'readData', 'readLineData', 'writeData'},
    'QCborStreamWriter': {'append', 'appendByteString', 'appendTextString'},
    'QCborStreamReader': {'addData', 'readStringChunk'},
    'QCborValue': {'fromCbor'},
    'QPicture': {'setData'},
    'QPixmap': {'loadFromData'},
    'QImage': {'fromData', 'loadFromData'},
    'QUdpSocket': {'readDatagram', 'writeDatagram'},
    'QTest': {'toPrettyCString', 'toHexRepresentation'},
    '': {'qCompress', 'qUncompress', 'qChecksum'},
}

# These native calls consume/copy their C strings synchronously. In particular,
# retained QLoggingCategory/QMessageLogger pointers and printf varargs are not
# covered by this policy. String inputs reject embedded NUL instead of silently
# truncating them. Null defaults remain available through generated defaults.
C_STRINGS = {
    'QLibrary': {'resolve'},
    'QOpenGLContext': {'getProcAddress'},
    'QApplication': {'font', 'palette', 'setFont', 'setPalette'},
    'QBitmap': {'QBitmap'},
    'QByteArray': {'append', 'prepend', 'push_back', 'push_front', 'insert', 'operator+', 'operator=', 'operator+=', 'operator==', 'operator!=',
                  'operator<', 'operator<=', 'operator>', 'operator>='},
    'QCborValue': {'QCborValue'},
    'QColor': {'QColor'},
    'QCoreApplication': {'translate'},
    'QColorDialog': {'open'},
    'QDBusAbstractInterface': {'callWithCallback', 'QDBusAbstractInterface'},
    'QDBusConnection': {'callWithCallback', 'connect', 'disconnect'},
    'QDBusObjectPath': {'QDBusObjectPath'},
    'QDBusSignature': {'QDBusSignature'},
    'QDataStream': {'operator<<'},
    'QDesktopServices': {'setUrlHandler'},
    'QFile': {'decodeName'},
    'QFileDialog': {'open'},
    'QFontDialog': {'open'},
    'QHostInfo': {'lookupHost'},
    'QHttpServerResponse': {'QHttpServerResponse'},
    'QImage': {'QImage', 'fromData', 'load', 'loadFromData', 'save'},
    'QJSValue': {'QJSValue'},
    'QJsonValue': {'QJsonValue'},
    'QInputDialog': {'open'},
    'QMessageBox': {'open'},
    'QMessageLogger': {'critical', 'debug', 'fatal', 'info', 'noDebug', 'warning'},
    'QMetaEnum': {'keyToValue', 'keysToValue'},
    'QMetaObject': {'checkConnectArgs', 'indexOfClassInfo', 'indexOfConstructor',
                    'indexOfEnumerator', 'indexOfMethod', 'indexOfProperty',
                    'indexOfSignal', 'indexOfSlot', 'normalizedSignature', 'normalizedType', 'invokeMethod'},
    'QMetaType': {'type'},
    'QObject': {'inherits', 'property', 'setProperty', 'connect', 'disconnect', 'receivers'},
    'QWidget': {'addAction'},
    'QMenu': {'addAction'},
    'QToolBar': {'addAction'},
    'QIODevice': {'write'},
    'QOpenGLShader': {'compileSourceCode'},
    'QOpenGLExtraFunctions': {'glGetFragDataLocation', 'glGetProgramResourceIndex',
                            'glGetProgramResourceLocation', 'glGetUniformBlockIndex'},
    'QOpenGLShaderProgram': {'addCacheableShaderFromSourceCode', 'addShaderFromSourceCode',
        'attributeLocation', 'uniformLocation', 'bindAttributeLocation',
        'enableAttributeArray', 'disableAttributeArray', 'setAttributeArray', 'setAttributeBuffer',
        'setAttributeValue', 'setUniformValue', 'setUniformValue1f', 'setUniformValue1i', 'setUniformValueArray'},
    'QPixmap': {'QPixmap', 'load', 'loadFromData', 'save'},
    'QPageSetupDialog': {'open'},
    'QPrintDialog': {'open'},
    'QPrintPreviewDialog': {'open'},
    'QProgressDialog': {'open'},
    'QQmlFile': {'connectDownloadProgress', 'connectFinished'},
    'QQmlListReference': {'QQmlListReference'},
    'QQmlProperty': {'connectNotifySignal'},
    'QRawFont': {'fontTable'},
    'QScxmlStateMachine': {'connectToEvent', 'connectToState'},
    'QShortcut': {'QShortcut'},
    'QSignalSpy': {'QSignalSpy'},
    'QSignalTransition': {'QSignalTransition'},
    'QState': {'assignProperty', 'addTransition'},
    'QTextStream': {'operator<<'},
    'QTest': {'compare_string_helper', 'compare_ptr_helper', 'failOnWarning', 'ignoreMessage',
              'qCaught', 'qExpectFail', 'qFindTestData', 'qSkip', 'setMainSourcePath'},
    'QTimer': {'singleShot'},
    'QTranslator': {'translate'},
    'QWizard': {'setDefaultProperty'},
    '': {'qtTrId', 'qmlProtectModule', 'qmlRegisterModule', 'qmlRegisterType',
         'qmlRegisterSingletonType', 'qmlRegisterUncreatableMetaObject', 'qmlTypeId'},
}

# These arguments address one native value for the duration of the call.
# They are not retained pointers or arrays. Output-only values start with the
# native default constructor and are returned in the ordinary output record.
VALUE_OUTPUTS = {
    ('QAccessibleTextInterface', 'attributes'): {'int'},
    ('QAccessibleTextInterface', 'selection'): {'int'},
    ('QAccessibleTextInterface', 'textBeforeOffset'): {'int'},
    ('QAccessibleTextInterface', 'textAtOffset'): {'int'},
    ('QAccessibleTextInterface', 'textAfterOffset'): {'int'},
    ('QBitArray', 'toUInt32'): {'bool'},
    ('QHostAddress', 'toIPv4Address'): {'bool'},
    ('QCanBusFactory', 'availableDevices'): {'QString'},
    ('QCanBusFactory', 'createDevice'): {'QString'},
    ('QDesignerFormWindowInterface', 'activateResourceFilePaths'): {'int', 'QString'},
    ('QDesignerFormWindowInterface', 'layoutDefault'): {'int'},
    ('QDesignerFormWindowInterface', 'layoutFunction'): {'QString'},
    ('QDesignerFormWindowInterface', 'setContents'): {'QString'},
    ('QDomDocument', 'setContent'): {'QString', 'int'},
    ('QFile', 'moveToTrash'): {'QString'},
    ('QGeoServiceProviderFactory', 'createGeocodingManagerEngine'): {'QGeoServiceProvider::Error', 'QString'},
    ('QGeoServiceProviderFactory', 'createPlaceManagerEngine'): {'QGeoServiceProvider::Error', 'QString'},
    ('QGeoServiceProviderFactory', 'createRoutingManagerEngine'): {'QGeoServiceProvider::Error', 'QString'},
    ('QJSEngine', 'evaluate'): {'QStringList', 'QList'},
    ('QModbusServer', 'data'): {'quint16'},
    ('QProcess', 'startDetached'): {'qint64'},
    ('QQmlEngine', 'importPlugin'): {'QList'},
    ('QScxmlCompiler::Loader', 'load'): {'QStringList', 'QList'},
    ('QScxmlDataModel', 'evaluateAssignment'): {'bool'},
    ('QScxmlDataModel', 'evaluateForeach'): {'bool'},
    ('QScxmlDataModel', 'evaluateInitialization'): {'bool'},
    ('QScxmlDataModel', 'evaluateToVoid'): {'bool'},
    ('QScxmlDataModel::ForeachLoopBody', 'run'): {'bool'},
    ('QCborValue', 'fromCbor'): {'QCborParserError'},
    ('QJsonDocument', 'fromJson'): {'QJsonParseError'},
    ('QJsonValue', 'fromJson'): {'QJsonParseError'},
    ('QImageIOHandler', 'allocateImage'): {'QImage'},
    ('QImageIOHandler', 'read'): {'QImage'},
    ('QImageReader', 'read'): {'QImage'},
    ('QItemSelection', 'split'): {'QItemSelection'},
    ('QPixmap', 'scroll'): {'QRegion'},
    ('QPixmapCache', 'find'): {'QPixmap'},
    ('QQuaternion', 'getAxes'): {'QVector3D'},
    ('QQuaternion', 'getAxisAndAngle'): {'QVector3D', 'float'},
    ('QTransform', 'map'): {'int'},
    **{('QLocale', method): {'bool'} for method in
       ('toDouble', 'toFloat', 'toInt', 'toLong', 'toLongLong', 'toShort', 'toUInt', 'toULongLong', 'toUShort')},
    ('QQuickImageProvider', 'requestImage'): {'QSize'},
    ('QQuickImageProvider', 'requestPixmap'): {'QSize'},
    ('QQuickImageProvider', 'requestTexture'): {'QSize'},
    ('QQuick3DInstancing', 'instanceBuffer'): {'int'},
    ('QQuickRenderControl', 'renderWindow'): {'QPoint'},
    ('QQuickRenderControl', 'renderWindowFor'): {'QPoint'},
    ('QSslCertificate', 'importPkcs12'): {'QSslKey', 'QSslCertificate', 'QList'},
    ('QWidget', 'redirected'): {'QPoint'},
}

VALUE_INPUTS = {
    ('QSGMaterialShader', 'updateGraphicsPipelineState'): {'QSGMaterialShader::GraphicsPipelineState'},
    ('QSGBasicGeometryNode', 'setRendererMatrix'): {'QMatrix4x4'},
    ('QAbstractOAuth', 'prepareRequest'): {'QNetworkRequest'},
    ('QGraphicsTransform', 'applyTo'): {'QMatrix4x4'},
    ('QQuickTransform', 'applyTo'): {'QMatrix4x4'},
    ('QModbusServer', 'data'): {'QModbusDataUnit'},
    ('QTextDocument', 'redo'): {'QTextCursor'},
    ('QTextDocument', 'undo'): {'QTextCursor'},
    ('QVideoFrameFormat', 'updateUniformData'): {'QByteArray'},
}


def index_bounds(f):
    owner = f['declaring_class']
    if (owner == 'QSGMaterialShader::RenderState' and f['name'] in ('combinedMatrix', 'projectionMatrix')
            and f['arguments']):
        return {0: 'self->projectionMatrixCount()'}
    if f['name'] == 'operator[]':
        if owner in ('QByteArray', 'QBitArray', 'QPolygon', 'QPolygonF', 'QXmlStreamAttributes', 'QJsonArray', 'QCborArray',
                     'QBluetoothServiceInfo::Alternative', 'QBluetoothServiceInfo::Sequence', 'QItemSelection', 'QNdefMessage',
                     'QModelRoleDataSpan'):
            return {0: 'self->size()'}
        if owner in ('QBarSet', 'QDir'):
            return {0: 'self->count()'}
        if owner == 'QIPv6Address':
            return {0: '16'}
        if owner == 'QKeySequence':
            return {0: '4'}
        if owner in ('QCborMap', 'QCborValue', 'QJsonDocument', 'QJsonValue'):
            # These are integer keys or documented undefined-on-miss lookups.
            # Negative keys are meaningful for CBOR and must not be rejected
            # by the ordinal-index validation used for native arrays.
            return {0: None}
        vector = re.fullmatch(r'QVector([234])D', owner)
        if vector:
            return {0: vector[1]}
    if f['name'] == 'operator()':
        matrix = re.fullmatch(r'QMatrix([234])x([234])', owner)
        if matrix:
            return {0: matrix[2], 1: matrix[1]}
    return {}


def policies(f):
    """Return source-indexed pointer policies and restored removed arguments."""
    owner, method = f['declaring_class'], f['name']
    result, restored = {}, set()
    arguments = f['arguments']
    if (owner, method) == ('QGraphicsView', 'drawItems'):
        # Both native arrays have the same explicit numItems extent. The item
        # identities are borrowed; style options are independent value copies.
        result[2] = dict(count_source=1, graphics_items=True)
        result[3] = dict(count_source=1)
    if owner == 'QGraphicsItem' and method == 'isBlockedByModalPanel':
        result[0] = {'output_object': True}
    for i, a in enumerate(arguments):
        t = a['type']
        if t['name'] == 'char' and t['pointers'] == 1 and t['const'] and (owner, method) in {
                ('QQmlExtensionInterface', 'initializeEngine'),
                ('QQmlTypesExtensionInterface', 'registerTypes'),
                ('QGeoAreaMonitorSource', 'requestUpdate')}:
            # Plugin implementations may retain names after this call. Intern
            # immutable bytes for the native host lifetime, including QML names
            # whose registration may outlive the plugin instance.
            result[i] = {'stable_cstring': True}
            continue
        if t['name'] == 'void' and t['pointers'] == 1 and (owner, method) in {
                ('QTextStream', 'operator<<'), ('QHelpGlobal', 'uniquifyConnectionName'),
                ('QTest', 'compare_ptr_helper')}:
            # These APIs compare or format an address, never read its pointee.
            result[i] = {'pointer_identity': True}
            continue
        if owner in ('QImage', 'QPixmap') and f['constructor'] and re.sub(r'\s+', '', t['cpp']) == 'constchar*const[]':
            result[i] = {'xpm_strings': True}
            continue
        matrix = re.fullmatch(r'const (?:GLfloat|float)\s*\[([234])\]\[([234])\]', t['cpp'])
        if owner == 'QOpenGLShaderProgram' and method == 'setUniformValue' and matrix:
            rows, columns = map(int, matrix.groups())
            result[i] = {'exact_size': rows * columns, 'matrix_shape': (rows, columns)}
            continue
        if owner == 'QRhi' and method == 'beginOffscreenFrame' and t['name'] == 'QRhiCommandBuffer' and t['pointers'] == 2:
            result[i] = {'output_object': True}
            continue
        const_pointer_reference = t['const'] and t['reference'] == 1 and bool(re.search(r'\*\s*const\s*&', t['cpp']))
        if t['pointers'] != 1 or (t['reference'] and not const_pointer_reference):
            continue
        if owner == 'QRhiCommandBuffer' and method == 'setVertexInput' and i == 2 and t['name'] == 'std::pair' and t['const']:
            result[i] = {'count_source': 1}
            continue
        if owner == 'QHostAddress' and method in ('QHostAddress', 'setAddress') and t['name'] == 'quint8' and t['const']:
            result[i] = {'exact_size': 16}
            continue
        if owner == 'QPolygon' and f['constructor'] and t['name'] == 'int' and t['const']:
            result[i] = {'count_source': 0, 'multiplier': 2}
            continue
        if owner == 'QRawFont' and method == 'advancesForGlyphIndexes' and t['name'] in ('quint32', 'QPointF'):
            result[i] = {'count_source': 2, 'writable_array': not t['const']}
            continue
        if owner == 'QRawFont' and method == 'glyphIndexesForChars':
            result[i] = ({'count_source': 1} if i == 0 else
                         {'count_source': 3, 'writable_array': True} if i == 2 else
                         {'inout_pointer': True})
            continue
        if owner == 'QOpenGLTexture' and method == 'borderColor' and not t['const']:
            result[i] = {'exact_size': 4, 'writable_array': True}
            continue
        if owner == 'QTextLine' and method == 'cursorToX' and t['name'] == 'int' and not t['const']:
            result[i] = {'inout_pointer': True}
            continue
        if owner in ('QRandomGenerator', 'QRandomGenerator64') and method == 'generate' and t['name'] == 'quint32':
            result[i] = ({'range_begin': True, 'writable_array': True, 'preserve_empty_range': True}
                         if i == 0 else {'range_source': 0})
            continue
        if owner in ('QRandomGenerator', 'QRandomGenerator64') and f['constructor'] and t['name'] == 'quint32' and t['const']:
            if i == 0:
                if len(arguments) == 2 and arguments[1]['type']['pointers']:
                    result[i] = {'range_begin': True}
                elif len(arguments) == 2:
                    result[i] = {'count_source': 1, 'range_begin': True}
            elif i == 1 and arguments[0]['type']['pointers']:
                result[i] = {'range_source': 0}
            continue
        if owner == 'QUuid' and method == 'fromBytes' and t['name'] == 'void' and t['const']:
            result[i] = {'bytes': True, 'minimum_size': 16}
            continue
        if owner == 'QAudioFormat' and method == 'normalizedSampleValue' and t['name'] == 'void' and t['const']:
            result[i] = {'bytes': True, 'audio_sample': True}
            continue
        if owner == 'QBitmap' and method == 'fromData' and t['name'] in ('uchar', 'unsigned char'):
            result[i] = {'bytes': True, 'bitmap_size_source': 0, 'bitmap_format_source': 2}
            continue
        if owner == 'QCollator' and method == 'compare' and t['name'] == 'QChar' and t['const']:
            result[i] = {'count_source': i + 1}
            continue
        if not t['const'] and t['name'] in VALUE_OUTPUTS.get((owner, method), ()):
            result[i] = {'output_pointer': True}
            continue
        if t['name'] in VALUE_INPUTS.get((owner, method), ()):
            result[i] = {'value_pointer': True, 'nullable': a.get('native_default') == 'nullptr'}
            continue
        if (owner == 'QFileDialog' and method in ('getOpenFileName', 'getOpenFileNames', 'getOpenFileUrl',
                'getOpenFileUrls', 'getSaveFileName', 'getSaveFileUrl') and t['name'] == 'QString' and not t['const']):
            # The selected filter is both an initial selection and an output.
            result[i] = {'inout_pointer': True}
            continue
        if owner == 'QDesignerFormWindowInterface' and method == 'simplifySelection' and t['name'] == 'QList':
            # Designer removes descendants whose ancestors are also selected.
            # The list is mutated synchronously; widget identities stay borrowed.
            result[i] = {'inout_pointer': True}
            continue
        if (not owner and t['name'] == 'QBrush' and t['const'] and method in
                ('qDrawPlainRect', 'qDrawPlainRoundedRect', 'qDrawShadePanel', 'qDrawShadeRect', 'qDrawWinButton', 'qDrawWinPanel')):
            result[i] = {'value_pointer': True, 'nullable': True}
            continue
        if owner.startswith(('QOpenGLFunctions', 'QOpenGLExtraFunctions')):
            if method in ('glDebugMessageInsert', 'glObjectLabel', 'glPushDebugGroup') and t['name'] == 'char' and t['const']:
                result[i] = {'bytes': True, 'count_source': i - 1, 'negative_terminated': True}
                continue
            uniform = re.fullmatch(r'gl(?:Program)?Uniform([1234])(?:f|i|ui)v', method)
            matrix = re.fullmatch(r'gl(?:Program)?UniformMatrix([234])(?:x([234]))?fv', method)
            fixed = re.fullmatch(r'glVertexAttrib([1234])fv', method)
            if t['const'] and uniform:
                result[i] = {'count_source': i - 1, 'multiplier': int(uniform[1])}
                continue
            if t['const'] and matrix:
                result[i] = {'count_source': i - 2, 'multiplier': int(matrix[1]) * int(matrix[2] or matrix[1])}
                continue
            if t['const'] and fixed:
                result[i] = {'exact_size': int(fixed[1])}
                continue
            if method in ('glDeleteBuffers', 'glDeleteFramebuffers', 'glDeleteRenderbuffers', 'glDeleteTextures',
                          'glDeleteQueries', 'glDeleteSamplers', 'glDeleteVertexArrays', 'glDeleteTransformFeedbacks',
                          'glDrawBuffers') and t['const']:
                result[i] = {'count_source': i - 1}
                continue
            if method in ('glGenBuffers', 'glGenFramebuffers', 'glGenRenderbuffers', 'glGenTextures',
                          'glGenQueries', 'glGenSamplers', 'glGenVertexArrays', 'glGenTransformFeedbacks') and not t['const']:
                result[i] = {'count_source': i - 1, 'writable_array': True}
                continue
            if method in ('glBufferData', 'glBufferSubData', 'glGetBufferSubData') and t['name'] == 'void':
                result[i] = {'bytes': True, 'count_source': i - 1, 'writable': not t['const']}
                continue
            if method in ('glBindAttribLocation', 'glGetAttribLocation', 'glGetUniformLocation',
                          'glBindFragDataLocation', 'glGetFragDataLocation', 'glGetUniformBlockIndex',
                          'glBindFragDataLocationIndexed', 'glGetFragDataIndex', 'glGetSubroutineIndex',
                          'glGetSubroutineUniformLocation', 'glGetProgramResourceIndex',
                          'glGetProgramResourceLocation', 'glGetProgramResourceLocationIndex') and t['name'] == 'char' and t['const']:
                result[i] = {'cstring': True}
                continue
        if (owner, method, t['name']) == ('QIODevice', 'readLineInto', 'QByteArray') and not t['const']:
            result[i] = {'value_pointer': True}
            continue
        if (owner in ('QDataStream', 'QTextStream', 'QBuffer', 'QCborStreamWriter', 'QXmlStreamWriter') and t['name'] == 'QByteArray'
                and not t['const'] and (f['constructor'] or method == 'setBuffer')):
            # retention.py provides the owner->backing dependency for these
            # persistent pointers. They are not temporary byte-buffer views.
            result[i] = {'value_pointer': True, 'nullable': owner not in ('QCborStreamWriter', 'QXmlStreamWriter')}
            continue
        if (owner, method, t['name']) == ('QTextStream', 'readLineInto', 'QString') and not t['const']:
            result[i] = {'output_pointer': True}
            continue
        if (owner, method, t['name']) == ('QLocale', 'toULong', 'bool') and not t['const']:
            result[i] = {'output_pointer': True}
            continue
        byte = t['name'] in ('char', 'uchar', 'unsigned char', 'quint8')
        next_scalar = (i + 1 < len(arguments) and arguments[i + 1]['type']['name']
                       in ('int', 'uint', 'unsigned int', 'qint64', 'qsizetype')
                       and not arguments[i + 1]['type']['pointers'])
        if owner == 'QBitArray' and method == 'fromBits' and byte and t['const'] and next_scalar:
            result[i] = {'bytes': True, 'count_source': i + 1, 'count_divisor': 8}
        elif byte and next_scalar and method in COPY_BYTES.get(owner, ()):
            if not t['const'] and (owner, method) not in (('QCborStreamReader', 'readStringChunk'), ('QDataStream', 'readRawData'), ('QUdpSocket', 'readDatagram'),
                                                        ('QIODevice', 'read'), ('QIODevice', 'readLine'), ('QIODevice', 'peek'),
                                                        ('QIODevice', 'readData'), ('QIODevice', 'readLineData')):
                continue
            result[i] = {'bytes': True, 'count_source': i + 1, 'writable': not t['const']}
            restored.update((i, i + 1))
        elif owner == 'QOpenGLBuffer' and method in ('allocate', 'write', 'read') and t['name'] == 'void' and next_scalar:
            result[i] = {'bytes': True, 'count_source': i + 1, 'writable': not t['const']}
        elif (owner == 'QOpenGLShaderProgram' and method == 'setUniformValueArray' and t['const'] and next_scalar):
            result[i] = {'count_source': i + 1}
            if i + 2 < len(arguments) and arguments[i + 2]['name'] == 'tupleSize':
                result[i]['tuple_source'] = i + 2
        elif (owner == 'QOpenGLShaderProgram' and method == 'setAttributeValue' and t['name'] == 'float'
              and t['const'] and next_scalar and i + 2 < len(arguments)):
            result[i] = {'count_source': i + 1, 'tuple_source': i + 2}
        elif (owner in ('QPainter', 'QPaintEngine') and method in ('drawLines', 'drawPoints', 'drawRects', 'drawPixmapFragments',
                                               'drawPolygon', 'drawPolyline', 'drawConvexPolygon')
              and t['const'] and next_scalar and t['name'] in
              ('QLine', 'QLineF', 'QPoint', 'QPointF', 'QRect', 'QRectF', 'QPainter::PixmapFragment')):
            multiplier = 2 if method == 'drawLines' and t['name'] in ('QPoint', 'QPointF') else 1
            result[i] = {'count_source': i + 1, 'multiplier': multiplier}
        elif owner == 'QRegion' and method == 'setRects' and t['name'] == 'QRect' and t['const'] and next_scalar:
            result[i] = {'count_source': i + 1}
        elif owner == 'QMatrix4x4' and f['constructor'] and t['name'] == 'float' and t['const']:
            result[i] = {'exact_size': 16}
        elif method == 'copyDataTo' and not t['const'] and t['name'] == 'float' and re.fullmatch(r'QMatrix[234]x[234]', owner):
            result[i] = {'exact_size': int(owner[7]) * int(owner[9]), 'writable_array': True}
        elif (owner in ('QFontMetrics', 'QFontMetricsF') and method in ('size', 'boundingRect')
              and t['name'] == 'int' and a.get('array')
              and 'sequenceToIntArray' in '\n'.join(f.get('snippets', []))):
            result[i] = {'sentinel': True}
        elif t['name'] == 'char' and t['const'] and method in C_STRINGS.get(owner, ()):
            result[i] = {'cstring': True}
    for source, policy in gl_buffers.policies(f).items():
        result.setdefault(source, policy)
    for source, policy in result.items():
        restored.add(source)
        for extent in ('count_source', 'tuple_source', 'pname_source', 'range_source', 'bitmap_size_source', 'bitmap_format_source',
                       'width_source', 'height_source', 'depth_source', 'format_source', 'pixel_type_source',
                       'index_count_source', 'index_type_source', 'options_source', 'mip_source', 'layer_count_source',
                       'program_source', 'block_source', 'stage_source', 'list_type_source', 'lengths_source', 'target_source', 'query_source',
                       'ustride_source', 'uorder_source', 'vstride_source', 'vorder_source', 'draw_count_source', 'draw_stride_source', 'counts_source'):
            if extent in policy:
                restored.add(policy[extent])
    return result, restored


def restores_method(function):
    """A documented public C++ overload can replace an upstream Python omission."""
    import gl_retained
    import gl_pointers
    import byte_iterators
    import volume_data
    import typed_views
    return typed_views.restores_method(function) or volume_data.handles(function) or byte_iterators.handles(function) or gl_pointers.handles(function) or gl_retained.handles(function) or allocated_buffers.handles(function) or gl_raw_mappings.handles(function) or native_interop.restores_method(function) or bool(policies(function)[0])


def convert(g, t, policy):
    if policy.get('stable_cstring'):
        return dict(kind='cstring', bend='String', raw='String', cpp=t['cpp'], buffer=policy)
    if policy.get('gpu_indices_array'):
        g.types['GLBufferOffset'] = 'wide'
        element = g.conversions.register(dict(kind='u64', bend='GLBufferOffset', raw='U32 & U32', cpp='quintptr'))
        sequence = g.conversions.register(dict(kind='list', name='QList', cpp='QList<quintptr>',
            children=[element], bend='List<&2, GLBufferOffset>', raw='Wire', codec='List_GLBufferOffset'))
        return dict(sequence, buffer=policy)
    if policy.get('string_array'):
        string = g.conversions.register(dict(kind='string', cpp='QString', bend='String', raw='String'))
        sequence = g.conversions.register(dict(kind='list', name='QList', cpp='QList<QString>',
            children=[string], bend='List<&2, String>', raw='Wire', codec='List_String'))
        return dict(sequence, buffer=policy)
    if policy.get('gl_sync'):
        if 'QOpenGLSync' not in g.ids:
            raise ValueError('OpenGL sync pointer requires the additive native extractor inventory')
        return dict(kind='gl_sync', name='QOpenGLSync', cpp=t['cpp'], bend='QOpenGLSync', raw='U32')
    if policy.get('gpu_offset'):
        g.types['GLBufferOffset'] = 'wide'
        return dict(kind='gpu_offset', bend='GLBufferOffset', raw='U32 & U32', cpp=t['cpp'], buffer=policy)
    if policy.get('pointer_identity'):
        g.types['NativeAddress'] = 'wide'
        return dict(kind='pointer_identity', bend='NativeAddress', raw='U32 & U32', cpp=t['cpp'], buffer=policy)
    if 'range_source' in policy:
        g.types['Int64'] = 'wide'
        return dict(kind='buffer_end', bend='Int64', raw='U32 & U32', cpp=t['cpp'], buffer=policy)
    if policy.get('value_pointer'):
        return dict(kind='value', name=t['name'], bend=t['name'].replace('::', '.'),
                    raw='U32', cpp=t['cpp'], pointer=True, native_const=t['const'],
                    required_pointer=not policy.get('nullable', True))
    if policy.get('cstring'):
        return dict(kind='cstring', bend='String', raw='String', cpp=t['cpp'])
    if policy.get('bytes'):
        return dict(kind='buffer', bend='QByteArray', raw='U32', name='QByteArray',
                    cpp=t['cpp'], buffer=policy)
    if policy.get('xpm_strings'):
        element = g.conversions.register(dict(kind='string', bend='String', raw='String', cpp='QString'))
        sequence = g.conversions.register(dict(kind='list', name='QList', children=[element],
            bend='List<&2, String>', raw='Wire', cpp='QList<QString>', codec='List_String'))
        return dict(sequence, buffer=policy)
    # Remove only the outer pointer. Nested pointer elements (for example a
    # vertex-input pair containing QRhiBuffer*) retain their native identity.
    if t.get('array') and t.get('array_element'):
        scalar = dict(t['array_element'], reference=0, const=False,
                      cpp=t['array_element']['cpp'].removeprefix('const ').strip())
    else:
        scalar = dict(t, pointers=max(0, t['pointers'] - 1), reference=0, const=False,
                      cpp=t['cpp'].removeprefix('const ').rstrip().removesuffix('*').strip())
    if policy.get('matrix_shape'):
        scalar.update(name='float', cpp='float')
    element = g.type(scalar)
    element = g.conversions.register(element)
    native = element['cpp']
    sequence = g.conversions.register({'kind': 'list', 'name': 'QList', 'children': [element],
        'bend': 'List<&2, ' + element['bend'] + '>', 'raw': 'Wire',
        'cpp': 'QList<' + native + '>', 'codec': 'List_' + element['codec'].removeprefix('Convert_')})
    # This is an input-only use of the normal list wire codec. Retain its native
    # list spelling; the pointer spelling belongs only to the call expression.
    return dict(sequence, buffer=dict(policy, pointer_cpp=t['cpp']))


def count_expression(g, policy):
    index, t = policy['count_input'], policy['count_type']
    return g.argument(t, index)[1]


def argument(g, t, index):
    policy = t['buffer']
    if policy.get('stable_cstring'):
        value = f'r->arguments[{index}]'
        return [f'if ({value}.size && std::memchr({value}.text, 0, {value}.size)) return fail(r, EINVAL, "Native name contains an embedded NUL");'], f'intern_native_name({value}.text, {value}.size)'
    if policy.get('pointer_identity'):
        return [], f'reinterpret_cast<{t["cpp"]}>(uintptr_t(wide_bits(r->arguments[{index}])))'
    if policy.get('gpu_pixel_offset'):
        import gl_pixel_offsets
        return gl_pixel_offsets.argument(g, t, index)
    if policy.get('gpu_indices_array'):
        count = count_expression(g, policy)
        counts = policy['counts_type']
        element_type = g.argument(policy['index_type_type'], policy['index_type_input'])[1]
        lines = [f'auto offsets_{index} = read_{t["native_codec"]}(r, r->arguments[{index}]);',
                 f'auto counts_{index} = read_{counts["native_codec"]}(r, r->arguments[{policy["counts_input"]}]);',
                 'if (r->error) return true;', f'const auto count_{index} = {count};',
                 f'if (count_{index} < 0 || uint64_t(count_{index}) > uint64_t(offsets_{index}->size()) || uint64_t(count_{index}) > uint64_t(counts_{index}->size()))',
                 '    return fail(r, ERANGE, "Multi-draw array count exceeds available elements");',
                 f'const auto index_type_{index} = {element_type};',
                 f'if (index_type_{index} != GL_UNSIGNED_BYTE && index_type_{index} != GL_UNSIGNED_SHORT && index_type_{index} != GL_UNSIGNED_INT)',
                 '    return fail(r, EINVAL, "Multi-draw index type must be unsigned byte, short, or int");',
                 f'std::vector<const void *> indices_{index};', f'indices_{index}.reserve(size_t(count_{index}));',
                 f'for (qsizetype n = 0; n < count_{index}; ++n) {{',
                 f'    if (counts_{index}->at(n) < 0) return fail(r, ERANGE, "Multi-draw element count is negative");',
                 f'    const auto extent = uint64_t(counts_{index}->at(n)) * gl_component_bytes(index_type_{index});',
                 f'    auto *pointer = gl_checked_offset(r, GL_ELEMENT_ARRAY_BUFFER, GL_ELEMENT_ARRAY_BUFFER_BINDING, offsets_{index}->at(n), extent, 1);',
                 '    if (r->error) return true;', f'    indices_{index}.push_back(pointer);', '}']
        return lines, f'indices_{index}.data()'
    if policy.get('string_array'):
        count = count_expression(g, policy)
        lines = [f'auto strings_{index} = read_{t["native_codec"]}(r, r->arguments[{index}]);',
                 'if (r->error) return true;', f'const auto string_count_{index} = {count};',
                 f'if (string_count_{index} < 0 || uint64_t(string_count_{index}) > uint64_t(strings_{index}->size()))',
                 '    return fail(r, ERANGE, "Native string count exceeds available strings");',
                 f'std::vector<QByteArray> string_bytes_{index};',
                 f'std::vector<const char *> string_pointers_{index};',
                 f'string_bytes_{index}.reserve(size_t(string_count_{index}));',
                 f'string_pointers_{index}.reserve(size_t(string_count_{index}));']
        if 'lengths_input' in policy:
            lengths = policy['lengths_type']
            lines += [f'auto string_lengths_{index} = read_{lengths["native_codec"]}(r, r->arguments[{policy["lengths_input"]}]);',
                      'if (r->error) return true;',
                      f'if (string_lengths_{index}->size() < string_count_{index}) return fail(r, ERANGE, "Shader source length array is too short");']
        lines += [f'for (qsizetype n = 0; n < string_count_{index}; ++n) {{',
                  f'    auto bytes = strings_{index}->at(n).toUtf8();']
        if 'lengths_input' in policy:
            lines += [f'    const auto length = string_lengths_{index}->at(n);',
                      '    if (length >= 0 && length > bytes.size()) return fail(r, ERANGE, "Shader source byte length exceeds available UTF-8 bytes");',
                      '    if (length < 0 && bytes.contains(char(0))) return fail(r, EINVAL, "Terminated shader source contains an embedded NUL");']
        else:
            lines += ['    if (bytes.contains(char(0))) return fail(r, EINVAL, "Native terminated name contains an embedded NUL");']
        lines += [f'    string_bytes_{index}.push_back(std::move(bytes));', '}',
                  f'for (const auto &bytes : string_bytes_{index}) string_pointers_{index}.push_back(bytes.constData());']
        return lines, f'string_pointers_{index}.data()'
    if policy.get('gpu_offset'):
        lines, extent = [], str(policy['gpu_extent'])
        if 'draw_count_input' in policy:
            count = g.argument(policy['draw_count_type'], policy['draw_count_input'])[1]
            stride = g.argument(policy['draw_stride_type'], policy['draw_stride_input'])[1]
            lines += [f'const auto draw_count_{index} = {count};', f'const auto draw_stride_{index} = {stride};',
                      f'if (draw_count_{index} < 0 || draw_stride_{index} < 0 || draw_stride_{index} % 4)',
                      '    return fail(r, ERANGE, "Indirect draw count or stride is invalid");',
                      f'const uint64_t draw_extent_{index} = !draw_count_{index} ? 0 : {policy["gpu_extent"]} +',
                      f'    uint64_t(draw_count_{index} - 1) * uint64_t(draw_stride_{index} ? draw_stride_{index} : {policy["gpu_extent"]});']
            extent = f'draw_extent_{index}'
        return lines + [f'auto gpu_pointer_{index} = gl_checked_offset(r, {policy["gpu_target"]}, {policy["gpu_binding"]},',
                f'    wide_bits(r->arguments[{index}]), {extent}, {policy["gpu_alignment"]});',
                'if (r->error) return true;'], f'reinterpret_cast<{t["cpp"]}>(gpu_pointer_{index})'
    if 'range_source' in policy:
        first = policy['range_input']
        accessor = 'constData' if t['cpp'].lstrip().startswith('const ') else 'data'
        return [f'const auto range_count_{index} = int64_t(wide_bits(r->arguments[{index}]));',
                f'if (range_count_{index} < 0 || uint64_t(range_count_{index}) > uint64_t(buffer_length_{first}))',
                '    return fail(r, ERANGE, "Native pointer range exceeds available elements");',
                f'auto *range_end_{index} = a{first}->{accessor}() + range_count_{index};'], f'range_end_{index}'
    if policy.get('bytes'):
        writable = str(bool(policy.get('writable'))).lower()
        nullable = str(bool(policy.get('nullable'))).lower()
        lines = [f'auto *a{index} = get<QByteArray>(r, r->arguments[{index}].word, {g.ids["QByteArray"]}, {nullable}, {writable});']
        storage = f'a{index}'
    else:
        lines = [f'auto a{index} = read_{t["native_codec"]}(r, r->arguments[{index}]);']
        storage = f'a{index}'
    lines += ['if (r->error) return true;']
    if policy.get('graphics_items'):
        lines += ['if (!a0 || !a0->isActive()) return fail(r, EINVAL, "Drawing items requires an active painter");',
                  f'for (auto *item : *{storage}) if (!item) return fail(r, EINVAL, "A graphics item array contains a null item");']
    if policy.get('range_begin'):
        lines += [f'const auto buffer_length_{index} = {storage}->size();']
    if policy.get('audio_sample'):
        lines += [f'quint8 audio_u8_{index}{{}}; qint16 audio_i16_{index}{{}};',
                  f'qint32 audio_i32_{index}{{}}; float audio_float_{index}{{}};',
                  f'void *audio_pointer_{index} = &audio_u8_{index}; size_t audio_size_{index} = 0;',
                  'switch (self->sampleFormat()) {',
                  f'case QAudioFormat::UInt8: audio_size_{index} = sizeof(audio_u8_{index}); break;',
                  f'case QAudioFormat::Int16: audio_pointer_{index} = &audio_i16_{index}; audio_size_{index} = sizeof(audio_i16_{index}); break;',
                  f'case QAudioFormat::Int32: audio_pointer_{index} = &audio_i32_{index}; audio_size_{index} = sizeof(audio_i32_{index}); break;',
                  f'case QAudioFormat::Float: audio_pointer_{index} = &audio_float_{index}; audio_size_{index} = sizeof(audio_float_{index}); break;',
                  'default: break;', '}',
                  f'if (uint64_t({storage}->size()) < audio_size_{index}) return fail(r, ERANGE, "Audio sample exceeds its byte storage");',
                  f'if (audio_size_{index}) std::memcpy(audio_pointer_{index}, {storage}->constData(), audio_size_{index});']
        return lines, f'audio_pointer_{index}'
    if 'bitmap_size_source' in policy:
        size = g.argument(policy['bitmap_size_type'], policy['bitmap_size_input'])[1]
        format = g.argument(policy['bitmap_format_type'], policy['bitmap_format_input'])[1]
        lines += [f'const auto &bitmap_size_{index} = {size};',
                  f'const auto bitmap_format_{index} = {format};',
                  f'if (bitmap_format_{index} != QImage::Format_Mono && bitmap_format_{index} != QImage::Format_MonoLSB)',
                  '    return fail(r, EINVAL, "Bitmap data needs a monochrome image format");',
                  f'if (bitmap_size_{index}.width() < 0 || bitmap_size_{index}.height() < 0 || bitmap_size_{index}.width() > INT_MAX - 7)',
                  '    return fail(r, ERANGE, "Bitmap size is outside the native range");',
                  f'const auto bitmap_row_{index} = uint64_t(bitmap_size_{index}.width() + 7) / 8;',
                  f'const auto bitmap_bytes_{index} = bitmap_row_{index} * uint64_t(bitmap_size_{index}.height());',
                  f'if (bitmap_bytes_{index} > INT_MAX || bitmap_bytes_{index} > uint64_t({storage}->size()))',
                  '    return fail(r, ERANGE, "Bitmap dimensions exceed available byte storage");']
    if policy.get('pixel_buffer'):
        binding = 'GL_PIXEL_PACK_BUFFER_BINDING' if policy['pixel_buffer'] == 'pack' else 'GL_PIXEL_UNPACK_BUFFER_BINDING'
        lines += ['if (auto *context = QOpenGLContext::currentContext()) {',
                  '    const auto version = context->format().version();',
                  '    const bool pixel_buffers = context->isOpenGLES() ? version.first >= 3',
                  '        : (version.first > 2 || (version.first == 2 && version.second >= 1));',
                  '    if (pixel_buffers || context->hasExtension(QByteArrayLiteral("GL_NV_pixel_buffer_object"))',
                  '            || context->hasExtension(QByteArrayLiteral("GL_EXT_pixel_buffer_object"))',
                  '            || context->hasExtension(QByteArrayLiteral("GL_ARB_pixel_buffer_object"))) {', '        GLint bound = 0;',
                  f'        context->functions()->glGetIntegerv({binding}, &bound);',
                  '        if (bound) return fail(r, EBUSY, "Host byte conversion requires the pixel buffer binding to be zero");',
                  '    }', '}']
    if policy.get('nullable'):
        lines += [f'QByteArray buffer_copy_{index};', f'if ({storage}) {{']
    if policy.get('compressed_layout'):
        if policy.get('texture_compressed'):
            lines += ['if (!self->isCreated()) return fail(r, EINVAL, "Texture upload requires a created texture");']
        else:
            def compressed_dimension(role):
                return g.argument(policy[role + '_type'], policy[role + '_input'])[1] if role + '_input' in policy else '1'
            lines += [f'auto compressed_bytes_{index} = gl_compressed_extent(r, true, {policy["compressed_dimensions"]},',
                      f'    {compressed_dimension("width")}, {compressed_dimension("height")}, {compressed_dimension("depth")}, {count_expression(g, policy)});',
                      'if (r->error) return true;',
                      f'if (compressed_bytes_{index} > uint64_t({storage}->size())) return fail(r, ERANGE, "Compressed pixel layout exceeds available byte storage");']
        if 'mip_input' in policy:
            mip = g.argument(policy['mip_type'], policy['mip_input'])[1]
            lines += [f'if ({mip} < 0 || {mip} >= 31) return fail(r, ERANGE, "Texture mip level is outside the native shift range");']
    if policy.get('texture_layout') or policy.get('texture_compressed'):
        def texture_extent(role, default='1'):
            return g.argument(policy[role + '_type'], policy[role + '_input'])[1] if role + '_input' in policy else default
        options = policy['options_input']
        lines += [f'auto *pixel_options_{index} = get<QOpenGLPixelTransferOptions>(r, r->arguments[{options}].word, {g.ids["QOpenGLPixelTransferOptions"]}, true, false);',
                  'if (r->error) return true;', f'GlPixelLayout pixel_layout_{index}{{}};',
                  f'if (pixel_options_{index}) pixel_layout_{index} = {{pixel_options_{index}->alignment(), pixel_options_{index}->rowLength(),',
                  f'    pixel_options_{index}->skipRows(), pixel_options_{index}->skipPixels(), pixel_options_{index}->imageHeight(), pixel_options_{index}->skipImages()}};',
                  f'const auto texture_bytes_{index} = gl_texture_pixel_extent(r, self, {str("width_input" in policy).lower()},',
                  f'    {texture_extent("width")}, {texture_extent("height")}, {texture_extent("depth")}, {texture_extent("mip", "0")}, {texture_extent("layer_count")},',
                  f'    {texture_extent("format")}, {texture_extent("pixel_type")}, pixel_options_{index} ? &pixel_layout_{index} : nullptr, '
                  + (count_expression(g, policy) if policy.get('texture_compressed') else '-1') + ');',
                  'if (r->error) return true;',
                  f'if (texture_bytes_{index} > uint64_t({storage}->size())) return fail(r, ERANGE, "Texture pixel layout exceeds available bytes");']
    if policy.get('pixel_layout'):
        def extent(role, default='1'):
            return g.argument(policy[role + '_type'], policy[role + '_input'])[1] if role + '_input' in policy else policy.get(role + '_fixed', default)
        unpack = str(policy.get('pixel_buffer') == 'unpack').lower()
        volume = str('depth_input' in policy).lower()
        provided = ''
        if policy.get('unit_pixel'):
            lines += [f'const GlPixelLayout unit_pixel_{index}{{1, 0, 0, 0, 0, 0}};']
            provided = f', &unit_pixel_{index}'
        lines += [f'const auto pixel_bytes_{index} = gl_pixel_extent(r, {unpack}, {volume}, {extent("width")}, {extent("height")},',
                  f'    {extent("depth")}, {extent("format")}, {extent("pixel_type")}{provided});',
                  'if (r->error) return true;',
                  f'if (pixel_bytes_{index} > uint64_t({storage}->size())) return fail(r, ERANGE, "Pixel storage layout exceeds available bytes");']
    if policy.get('texture_readback'):
        def readback(role, default='0'):
            return g.argument(policy[role + '_type'], policy[role + '_input'])[1] if role + '_input' in policy else default
        lines += [f'const auto readback_bytes_{index} = gl_texture_readback_extent(r, {readback("target")}, {readback("mip")},',
                  f'    {readback("format")}, {readback("pixel_type")}, {str(policy.get("compressed_readback", False)).lower()});',
                  'if (r->error) return true;',
                  f'if (readback_bytes_{index} > uint64_t({storage}->size())) return fail(r, ERANGE, "Texture readback exceeds available byte storage");']
    if 'legacy_readback' in policy:
        def readback(role):
            return g.argument(policy[role + '_type'], policy[role + '_input'])[1]
        lines += [f'const auto readback_bytes_{index} = gl_legacy_readback_extent(r, {policy["legacy_readback"]}, {readback("target")},',
                  f'    {readback("format")}, {readback("pixel_type")}, {policy.get("readback_axis", 0)});',
                  'if (r->error) return true;',
                  f'if (readback_bytes_{index} > uint64_t({storage}->size())) return fail(r, ERANGE, "OpenGL imaging readback exceeds available byte storage");']
    if policy.get('gl_evaluator_result') or policy.get('gl_evaluator_input'):
        def evaluator(role, default='0'):
            return g.argument(policy[role + '_type'], policy[role + '_input'])[1] if role + '_input' in policy else default
        if policy.get('gl_evaluator_result'):
            expression = f'gl_evaluator_result_extent(r, {evaluator("target")}, {evaluator("query")})'
        else:
            expression = f'gl_evaluator_input_extent(r, {evaluator("target")}, {evaluator("ustride")}, {evaluator("uorder")}, {evaluator("vstride")}, {evaluator("vorder", "1")})'
        lines += [f'const auto evaluator_count_{index} = {expression};', 'if (r->error) return true;',
                  f'if (evaluator_count_{index} > uint64_t({storage}->size())) return fail(r, ERANGE, "OpenGL evaluator exceeds available element storage");']
    if policy.get('client_indices'):
        count = g.argument(policy['index_count_type'], policy['index_count_input'])[1]
        typ = g.argument(policy['index_type_type'], policy['index_type_input'])[1]
        lines += [f'const auto index_bytes_{index} = gl_index_extent(r, {count}, {typ});',
                  'if (r->error) return true;',
                  f'if (index_bytes_{index} > uint64_t({storage}->size())) return fail(r, ERANGE, "Index count exceeds available bytes");']
    if policy.get('xpm_strings'):
        # Qt's array reader advances source[index++] without an array bound.
        # Validate its header-driven read extent before building C pointers.
        # Limits mirror Qt 6.12 qxpmhandler.cpp; native parsing still interprets
        # colors and pixels. Storage remains alive throughout the constructor.
        suffix = str(index)
        lines += [
            f'if ({storage}->isEmpty()) return fail(r, EINVAL, "XPM data has no header");',
            f'QList<QByteArray> xpm_storage_{suffix};',
            f'xpm_storage_{suffix}.reserve({storage}->size());',
            f'for (const auto &line : *{storage}) {{',
            '    auto bytes = line.toUtf8();',
            '    if (bytes.contains(char(0))) return fail(r, EINVAL, "XPM line contains an embedded NUL");',
            f'    xpm_storage_{suffix}.append(std::move(bytes));', '}',
            f'auto xpm_header_{suffix} = xpm_storage_{suffix}.first().simplified().split(char(32));',
            f'if (xpm_header_{suffix}.size() < 4) return fail(r, EINVAL, "XPM header requires four dimensions");',
            f'qlonglong xpm_dimensions_{suffix}[4]{{}};',
            f'for (int field = 0; field < 4; ++field) {{',
            '    bool valid = false;',
            f'    xpm_dimensions_{suffix}[field] = xpm_header_{suffix}[field].toLongLong(&valid);',
            '    if (!valid) return fail(r, EINVAL, "XPM dimension is not an integer");', '}',
            f'auto xpm_width_{suffix} = xpm_dimensions_{suffix}[0];',
            f'auto xpm_height_{suffix} = xpm_dimensions_{suffix}[1];',
            f'auto xpm_colors_{suffix} = xpm_dimensions_{suffix}[2];',
            f'auto xpm_characters_{suffix} = xpm_dimensions_{suffix}[3];',
            f'if (xpm_width_{suffix} <= 0 || xpm_width_{suffix} > 32767 || xpm_height_{suffix} <= 0 || xpm_height_{suffix} > 32767',
            f'        || xpm_colors_{suffix} <= 0 || xpm_colors_{suffix} > 16777216 || xpm_characters_{suffix} <= 0 || xpm_characters_{suffix} > 15)',
            '    return fail(r, ERANGE, "XPM dimensions exceed the Qt format limits");',
            f'if (xpm_storage_{suffix}.size() < 1 + xpm_colors_{suffix} + xpm_height_{suffix})',
            '    return fail(r, EINVAL, "XPM array is shorter than its declared image");',
            f'for (qlonglong color = 0; color < xpm_colors_{suffix}; ++color)',
            f'    if (xpm_storage_{suffix}[1 + color].size() < xpm_characters_{suffix})',
            '        return fail(r, EINVAL, "XPM color code is truncated");',
            f'for (qlonglong row = 0; row < xpm_height_{suffix}; ++row)',
            f'    if (xpm_storage_{suffix}[1 + xpm_colors_{suffix} + row].size() < xpm_width_{suffix} * xpm_characters_{suffix})',
            '        return fail(r, EINVAL, "XPM pixel row is truncated");',
            f'std::vector<const char *> xpm_pointers_{suffix};',
            f'xpm_pointers_{suffix}.reserve(size_t(xpm_storage_{suffix}.size()) + 1);',
            f'for (const auto &line : xpm_storage_{suffix}) xpm_pointers_{suffix}.push_back(line.constData());',
            f'xpm_pointers_{suffix}.push_back(nullptr);']
        return lines, f'xpm_pointers_{suffix}.data()'
    if 'count_input' in policy:
        count = count_expression(g, policy)
        multiplier = policy.get('multiplier', 1)
        if 'list_type_input' in policy:
            list_type = g.argument(policy['list_type_type'], policy['list_type_input'])[1]
            multiplier = f'buffer_list_width_{index}'
            lines += [f'uint32_t {multiplier} = 0;', f'switch ({list_type}) {{',
                      f'case GL_BYTE: case GL_UNSIGNED_BYTE: {multiplier} = 1; break;',
                      f'case GL_SHORT: case GL_UNSIGNED_SHORT: case GL_2_BYTES: {multiplier} = 2; break;',
                      f'case GL_3_BYTES: {multiplier} = 3; break;',
                      f'case GL_INT: case GL_UNSIGNED_INT: case GL_FLOAT: case GL_4_BYTES: {multiplier} = 4; break;',
                      'default: return fail(r, EINVAL, "Unsupported OpenGL display-list element type");', '}']
        if 'tuple_input' in policy:
            size = g.argument(policy['tuple_type'], policy['tuple_input'])[1]
            multiplier = f'buffer_tuple_{index}'
            lines += [f'auto {multiplier} = {size};',
                      f'if ({multiplier} < 1 || {multiplier} > 4) return fail(r, ERANGE, "Uniform tuple size must be between one and four");']
        # Divide capacity before comparison, so multiplication cannot overflow.
        invalid = (f'buffer_count_{index} >= 0 && uint64_t(buffer_count_{index}) > uint64_t({storage}->size()) / {multiplier}'
                   if policy.get('negative_terminated') else
                   f'buffer_count_{index} < 0 || uint64_t(buffer_count_{index}) > uint64_t({storage}->size()) / {multiplier}')
        if policy.get('count_divisor'):
            divisor = policy['count_divisor']
            invalid = (f'buffer_count_{index} < 0 || uint64_t(buffer_count_{index}) / {divisor}'
                       f' + (uint64_t(buffer_count_{index}) % {divisor} != 0) > uint64_t({storage}->size())')
        lines += [f'auto buffer_count_{index} = {count};',
                  f'if ({invalid})',
                  '    return fail(r, ERANGE, "Native buffer count exceeds available storage");']
    if 'exact_size' in policy:
        lines += [f'if ({storage}->size() != {policy["exact_size"]}) return fail(r, EINVAL, "Native array has the wrong number of elements");']
    if 'minimum_size' in policy:
        lines += [f'if ({storage}->size() < {policy["minimum_size"]}) return fail(r, ERANGE, "Native array needs storage for its largest return value");']
    if 'gl_extent' in policy:
        pname = g.argument(policy['pname_type'], policy['pname_input'])[1]
        extra = ''
        if 'program_input' in policy:
            program = g.argument(policy['program_type'], policy['program_input'])[1]
            block = g.argument(policy['block_type'], policy['block_input'])[1]
            extra = f', {program}, {block}'
            if 'stage_input' in policy:
                extra += ', ' + g.argument(policy['stage_type'], policy['stage_input'])[1]
        lines += [f'auto gl_count_{index} = gl_buffer_extent(r, {policy["gl_extent"]}, {pname}{extra});',
                  'if (r->error) return true;',
                  f'if ({storage}->size() < gl_count_{index}) return fail(r, ERANGE, "OpenGL state exceeds available buffer storage");']
    if policy.get('sentinel'):
        lines += [f'{storage}->append(0);']
    if policy.get('range_begin'):
        if policy.get('preserve_empty_range'):
            lines += [f'const auto range_original_size_{index} = {storage}->size();']
        lines += [f'if ({storage}->isEmpty()) {storage}->append({{}});']
    if policy.get('matrix_shape'):
        rows, columns = policy['matrix_shape']
        # A real array preserves the parameter's array type. Casting a flat
        # container pointer would not establish the native subarray objects.
        lines += [f'float buffer_matrix_{index}[{rows}][{columns}];',
                  f'for (int row = 0; row < {rows}; ++row)',
                  f'    for (int column = 0; column < {columns}; ++column)',
                  f'        buffer_matrix_{index}[row][column] = {storage}->at(row * {columns} + column);']
        return lines, f'buffer_matrix_{index}'
    pointer = policy.get('pointer_cpp', t['cpp'])
    if policy.get('bytes'):
        # A source may alias the receiver, or an output may alias a stream's
        # retained source buffer. Detached storage avoids both invalidation and
        # overlapping native memcpy; output commits after the call returns.
        lines += [f'buffer_copy_{index} = *{storage};' if policy.get('nullable') else f'QByteArray buffer_copy_{index}(*{storage});',
                  f'buffer_copy_{index}.detach();']
        expression = f'buffer_copy_{index}.' + ('data()' if policy.get('writable') else 'constData()')
    else:
        expression = f'{storage}->data()'
    if policy.get('bytes'):
        expression = f'reinterpret_cast<{pointer}>({expression})'
    if policy.get('nullable'):
        lines += ['}']
        expression = f'({storage} ? {expression} : nullptr)'
    return lines, expression


def after_call(g, method):
    lines = [f'*a{i} = std::move(buffer_copy_{i});'
            for i, t in enumerate(method['args'])
            if t.get('buffer', {}).get('bytes') and t['buffer'].get('writable')]
    f = method['function']
    for item in method.get('parameters', []):
        if item['type'].get('buffer', {}).get('preserve_empty_range'):
            lines += [f'out{item["source"]}.resize(range_original_size_{item["input"]});']
    if f['declaring_class'] == 'QGraphicsItem' and f['name'] == 'isBlockedByModalPanel':
        lines += ['if (out0) native_observe_QGraphicsItem(r, out0);', 'if (r->error) return true;']
    return lines


def call_arguments(function, arguments):
    # QMessageLogger's public overloads are printf-like. The Bend parameter is
    # literal text, matching PySide's format-string adapter: never interpret
    # a caller's percent sequences as missing C varargs.
    if function['declaring_class'].startswith(('QOpenGLFunctions', 'QOpenGLExtraFunctions')) and function['name'] in ('glGetnSeparableFilter', 'glGetSeparableFilter'):
        return [*arguments, 'nullptr']
    if (function['declaring_class'] == 'QMessageLogger' and function['name'] in C_STRINGS['QMessageLogger']
            and function['arguments'] and function['arguments'][-1]['type']['name'] == 'char'
            and function['arguments'][-1]['type']['pointers'] == 1):
        return [*arguments[:-1], '"%s"', arguments[-1]]
    return arguments
