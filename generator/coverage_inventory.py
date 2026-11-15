"""Separate native binding gaps from inherited duplicates and Python additions."""
from collections import Counter, defaultdict
import converter_cleanup
import native_operators
import glyph_arrays


def source_classification(f):
    """Classify declarations using audited Qt 6.12 source, never their names alone."""
    owner, name = f['declaring_class'], f['name']
    from adapters import excluded_internal_api
    if excluded_internal_api(f):
        return dict(category='qt_internal_api_excluded', supported=False,
                    source_evidence=dict(qt_version='6.12.0',
                        path='qtbase/src/gui/painting/qpaintdevice.cpp', line=65,
                        url='https://github.com/qt/qtbase/blob/v6.12.0/src/gui/painting/qpaintdevice.cpp#L65-L71',
                        reason='Explicitly marked internal by Qt. Public forwarding methods and overrides are intentionally excluded at the user\'s request.'))
    if owner == 'QMetaObject' and f['constructor'] and not f['arguments']:
        return dict(category='native_origin_alternative', supported=False,
                    source_evidence=dict(qt_version='6.12.0', path='qtbase/src/corelib/kernel/qobjectdefs.h', line=234,
                        reason='A default QMetaObject has no generated metadata tables. Pinned PySide constructs it, but className() and propertyCount() each crash with SIGSEGV. Obtain usable native metadata from a QObject or QMetaType instead.'),
                    runtime_evidence='docs/api-coverage-audit.md#native-metadata-and-process-setup',
                    alternatives=[dict(bend_name='QObject.metaObject', contract='observed_native_metadata'),
                                  dict(bend_name='QMetaType.metaObject', contract='observed_native_metadata')])
    if owner == 'QProcess' and name == 'failChildProcessModifier':
        return dict(category='upstream_unusable_callback_entry', supported=False,
                    source_evidence=dict(qt_version='6.12.0', path='qtbase/src/corelib/io/qprocess.cpp', line=1824,
                        url='https://doc.qt.io/qt-6/qprocess.html#failChildProcessModifier',
                        reason='Qt defines use outside the matching child-process modifier as undefined behavior. Pinned PySide exposes this error function but has no setChildProcessModifier callback entry. The extracted setter has an unmatched std::function argument.'),
                    runtime_evidence='docs/api-coverage-audit.md#native-metadata-and-process-setup')
    evidence = None
    if owner == 'QDBusAbstractInterface' and name in ('internalPropGet', 'internalPropSet'):
        evidence = ('qtbase/src/dbus/qdbusabstractinterface.cpp', 619 if name == 'internalPropGet' else 631,
                    'Explicitly marked internal for generated DBus proxies. The implementations forward directly to QObject.property/setProperty, which remain available.')
    elif owner == 'QBasicReadWriteLock' and name in ('contendedTryLockForRead', 'contendedTryLockForWrite', 'contendedUnlock', 'describeLockInternal'):
        evidence = ('qtbase/src/corelib/thread/qreadwritelock.cpp', 16,
                    'Implementation-state hooks for QReadWriteLock. The void pointer is a tagged QReadWriteLockPrivate state read from d_ptr by the public lock operations; it is not caller-owned data. These helpers have no public QDoc contract. Public read/write lock operations remain available.')
    elif name == 'resolveInterface' and len(f['arguments']) == 2 and f['return']['name'] == 'void' and f['return']['pointers']:
        evidence = ('qtbase/src/corelib/global/qnativeinterface.h', 114,
                    'Generated protected plumbing of QT_DECLARE_NATIVE_INTERFACE_ACCESSOR. Its Q_QDOC branch exposes nativeInterface<T>; the implementation passes private type-name/revision metadata to this raw resolver. Typed native-interface accessors remain available.')
    elif owner == 'QVideoFrame' and (name == 'videoBuffer' or (f['constructor'] and f['arguments'] and f['arguments'][0]['type']['name'] == 'QAbstractVideoBuffer')):
        evidence = ('qtmultimedia/src/multimedia/video/qvideoframe.cpp', 82 if f['constructor'] else 92,
                    'Explicitly documented as internal and deprecated since 6.8 in qvideoframe.h:131-135; the checked QVideoFrame.fromVideoBuffer uses the public unique_ptr constructor.')
    elif owner == 'QSGRenderNode' and name == 'projectionMatrix' and f['arguments']:
        evidence = ('qtdeclarative/src/quick/scenegraph/coreapi/qsgrendernode.cpp', 328,
                    'The indexed overload is documented as internal; only the zero-argument overload is public API.')
    elif owner == 'QScxmlTableData' and name in ('instructions', 'stateMachineTable'):
        evidence = ('qtscxml/src/scxml/qscxmltabledata.cpp', 20,
                    'The class is reserved for internal use and SCXML compiler-generated state machines; these methods expose opaque executable/state tables.')
    elif owner == 'QDBusConnection' and name == 'internalPointer':
        evidence = ('qtbase/src/dbus/qdbusconnection.cpp', 794,
                    'Explicitly internal and implementation-defined; the returned libdbus pointer does not increment its native reference count.')
    elif owner == 'QAccessibleInterface' and name == 'virtual_hook':
        evidence = ('qtbase/src/gui/accessible/qaccessible.cpp', 1941,
                    'Reserved ABI extension hook; Qt explicitly documents it as internal and currently unused.')
    elif owner == 'QRhiBuffer' and name == 'fullDynamicBufferUpdateForCurrentFrame':
        evidence = ('qtbase/src/gui/rhi/qrhi.cpp', 4173,
                    'Qt-internal convenience implementation; public dynamic updates use bounded QByteArray through QRhiResourceUpdateBatch.')
    elif owner == 'QMetaMethod' and name == 'attributes':
        evidence = ('qtbase/src/corelib/kernel/qmetaobject.cpp', 2414,
                    'Explicitly internal metadata flag representation, not a documented public attribute API.')
    elif owner == 'QMetaMethod' and name == 'getParameterTypes':
        evidence = ('qtbase/src/corelib/kernel/qmetaobject.cpp', 2308,
                    'Qt 6.12.0 explicitly marks this raw array helper internal; public parameterType, parameterMetaType and parameterTypes remain available.')
    elif owner == 'QMetaObject' and name == 'connect' and len(f['arguments']) == 6 and f['arguments'][-1]['type']['pointers']:
        evidence = ('qtbase/src/corelib/kernel/qobject.cpp', 3747,
                    'Qt 6.12.0 marks the indexed connect overload and its zero-terminated internal metatype vector as internal; use typed signals or public QObject connections.')
    elif owner == 'QMenu' and name == 'setNoReplayFor':
        evidence = ('qtbase/src/widgets/widgets/qmenu.cpp', 3750,
                    'Explicitly internal mouse-event replay suppression hook.')
    elif owner == 'QPaintEngine' and name == 'setPaintDevice':
        evidence = ('qtbase/src/gui/painting/qpaintengine.cpp', 875,
                    'Explicitly internal paint-device assignment hook; public drawing starts through QPainter.begin.')
    elif owner == 'QPainter' and name == 'drawText' and len(f['arguments']) == 4 and f['arguments'][0]['type']['name'] == 'QPointF':
        evidence = ('qtbase/src/gui/painting/qpainter.cpp', 5669,
                    'The point/string/flags/justification overload is explicitly internal; documented public drawText overloads remain available.')
    if evidence:
        path, line, reason = evidence
        result = dict(category='qt_internal_native_gap', source_evidence=dict(
            qt_version='6.12.0', path=path, line=line, reason=reason),
            supported=False)
        if owner == 'QVideoFrame':
            result['source_evidence']['url'] = 'https://raw.githubusercontent.com/qt/qtmultimedia/v6.12.0/src/multimedia/video/qvideoframe.cpp'
        return result
    return None


def inventory(g):
    import protected_members
    import lazy_values
    import video_buffers
    import rhi_lifetimes
    import accessible_facets
    import callback_functions
    callback_functions.annotate(g)
    import callback_sampled_images
    callback_sampled_images.annotate(g)
    import icon_hooks
    icon_hooks.annotate(g)
    import rhi_cleanup
    rhi_cleanup.annotate(g)
    rhi_lifetimes.annotate(g)
    import rhi_native_handles
    rhi_native_handles.annotate(g)
    accessible_facets.annotate(g)
    entries = {}
    functions = {}
    unmatched = []
    for excluded in g.excluded:
        receiver = excluded['class']
        if receiver not in functions:
            grouped = defaultdict(list)
            for f in g.inherited(receiver):
                grouped[f['signature']].append(f)
            functions[receiver] = grouped
        candidates = functions[receiver].get(excluded['signature'], [])
        if not candidates:
            unmatched.append(dict(excluded))
        for f in candidates:
            f = protected_members.callable_contract(g, receiver, f)
            classified = source_classification(f)
            if not f['public'] and not protected_members.permitted(g, f):
                category = 'inaccessible_native_member'
            elif f['user_added']:
                category = 'python_only_addition'
            elif f['destructor']:
                category = 'checked_destroy_alternative'
            elif f['constructor'] and g.classes[receiver]['abstract']:
                category = 'abstract_constructor'
            elif excluded.get('alternatives'):
                category = 'explicit_alternative'
            elif classified:
                category = classified['category']
            elif f['removed'] and excluded['reason'] == 'Removed by the type system':
                category = 'upstream_removed_native_member'
            elif f['name'].startswith('qt_'):
                category = 'qt_internal_marker'
            elif excluded['reason'] == 'The package owns the single Qt application':
                category = 'binding_owned_application'
            else:
                category = 'binding_gap'
            owner = f['declaring_class'] or 'Global'
            signature = native_operators.identity(f)
            key = (category, owner, signature, excluded['reason'])
            item = entries.setdefault(key, dict(category=category, owner=owner, signature=signature,
                source_signatures=f['source_signatures'], reason=excluded['reason'], receivers=[], alternatives=[]))
            if f.get('source_file'):
                item['declaration'] = dict(path=f['source_file'], line=f.get('source_line'))
            if classified and category == classified['category']:
                item.update(classified)
            for alternative in excluded.get('alternatives', []):
                if alternative not in item['alternatives']:
                    item['alternatives'].append(alternative)
            item['receivers'].append(receiver)
    values = sorted(entries.values(), key=lambda v: (v['category'], v['owner'], v['signature'], v['reason']))
    for value in values:
        value['receivers'] = sorted(set(value['receivers']))
        if not value['alternatives']:
            del value['alternatives']
    partial = {}
    function_alternatives = defaultdict(list)
    for callback in getattr(g, 'callback_functions', []):
        f = callback['function']
        key = (f['declaring_class'], native_operators.identity(f))
        function_alternatives[key].append(dict(
            bend_name=callback['public'], contract='typed_function_handler',
            reason='Supplies a Bend handler as the native callback; arguments are copied, and Qt owns the stored function until it destroys it'))
    for m in g.methods:
        f = m['function']
        if f.get('omitted_native_callback'):
            key = (f['declaring_class'], native_operators.identity(f))
            partial[key] = dict(owner=key[0], signature=key[1],
                omitted_callback=f['omitted_native_callback'], behavior='native default callback only')
            if function_alternatives[key]:
                partial[key]['alternatives'] = function_alternatives[key]
                partial[key]['callback_available'] = True
    return dict(unique_exclusions_by_category=dict(Counter(v['category'] for v in values)),
                converter_state_cleanup=converter_cleanup.inventory(g),
                custom_video_buffers=video_buffers.inventory(g),
                deferred_conversion_values=lazy_values.inventory(g),
                unique_exclusions=values, partial_native_signatures=list(partial.values()) + rhi_native_handles.limitations(g) + glyph_arrays.limitations(g),
                unselected_classes=g.excluded_classes,
                unmatched_exclusions=unmatched,
                full_coverage=False,
                full_coverage_blockers=['Native binding gaps and partial signatures in this inventory',
                    'Upstream-removed declarations and Qt-internal gaps remain explicitly unbound',
                    'Unselected classes and extraction_omissions must be audited independently',
                    'Explicit alternatives have their declared semantics; they do not imply identical native signatures'],
                scope='Extracted public native members; extractor omissions and class exclusions remain separate and prevent a full-coverage claim.')


def conversion_policy(t):
    keys = ('kind', 'result_conversion', 'memory_view', 'value_view', 'consume', 'readonly',
            'native_const', 'owned', 'buffer', 'retained_bytes_snapshot', 'gl_mapping', 'file_mapping',
            'static_native_view', 'native_result_view')
    result = {key: t[key] for key in keys if key in t}
    if 'children' in t:
        result['children'] = [conversion_policy(child) for child in t['children']]
    return result
