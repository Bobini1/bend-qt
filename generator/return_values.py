"""Audited native return representations that need method-level semantics.

A char pointer alone does not establish text, length, termination or ownership.
These metadata/version APIs return borrowed, terminated text. Binary storage
and iterator APIs deliberately do not pass through this adapter.
"""


def adapt(g, function):
    import core_pointer_results
    core_pointer = core_pointer_results.adapt(g, function)
    if core_pointer is not None:
        return core_pointer
    import native_result_views
    native_view = native_result_views.adapt(g, function)
    if native_view is not None:
        return native_view
    import data_proxies
    data = data_proxies.adapt(g, function)
    if data:
        return data
    if (function['declaring_class'], function['name']) == ('QCborStreamReader', 'readStringChunk'):
        size = g.conversions.register(dict(kind='i64', bend='Int64', raw='U32 & U32', cpp='qsizetype'))
        status = g.conversions.register(dict(kind='enum', name='QCborStreamReader::StringResultCode',
            bend='QCborStreamReader.StringResultCode', raw='U32', cpp='QCborStreamReader::StringResultCode'))
        pair = g.conversions.register(dict(kind='pair', children=[size,status],
            bend='PairValue<Int64, QCborStreamReader.StringResultCode>', raw='Wire',
            cpp='std::pair<qsizetype, QCborStreamReader::StringResultCode>', codec='Pair_CborChunk'))
        return dict(pair, result_conversion='cbor_chunk')
    if (function['declaring_class'], function['name']) == ('QThread', 'currentThreadId'):
        # This is an opaque diagnostic identity, never an address accepted by a
        # pointer argument. It identifies the Qt host thread running the call.
        g.types['ThreadIdentity'] = 'wide'
        return dict(kind='u64', bend='ThreadIdentity', raw='U32 & U32', cpp='quintptr',
                    result_conversion='thread_identity')
    import form_rows
    row = form_rows.adapt(g, function)
    if row:
        return row
    import rhi_snapshots
    rhi_value = rhi_snapshots.adapt(g, function)
    if rhi_value:
        return rhi_value
    import qtest_values
    test_value = qtest_values.adapt(g, function)
    if test_value:
        return test_value
    import allocated_buffers
    text = allocated_buffers.adapt(g, function)
    if text:
        return text
    import model_data
    data = model_data.adapt(g, function)
    if data:
        return data
    import volume_data
    volume = volume_data.adapt(g, function)
    if volume:
        return volume
    import generic_arguments
    generic = generic_arguments.adapt(g, function)
    if generic:
        return generic
    import byte_iterators
    iterator = byte_iterators.adapt(g, function)
    if iterator:
        return iterator
    import gl_pointers
    pointer = gl_pointers.adapt(g, function)
    if pointer:
        return pointer
    import gl_retained
    retained = gl_retained.adapt(g, function)
    if retained:
        return retained
    import gl_raw_mappings
    raw_mapping = gl_raw_mappings.adapt(g, function)
    if raw_mapping:
        return raw_mapping
    import meta_storage
    storage = meta_storage.adapt(g, function)
    if storage:
        return storage
    import native_interop
    interop = native_interop.adapt(g, function)
    if interop:
        return interop
    import role_data
    role = role_data.adapt(g, function)
    if role:
        return role
    import metadata_lifetimes
    metadata = metadata_lifetimes.adapt(g, function)
    if metadata:
        return metadata
    import typed_views
    typed = typed_views.adapt(g, function)
    if typed:
        return typed
    import dbus_replies
    reply = dbus_replies.adapt(g, function)
    if reply:
        return reply
    import borrowed_values
    value = borrowed_values.adapt(g, function)
    if value:
        return value
    import memory_views
    view = memory_views.adapt(g, function)
    if view:
        return view
    source = function['return']
    owner, method = function['declaring_class'], function['name']
    if owner == 'QTest' and method in ('toPrettyCString', 'toHexRepresentation') and source['cpp'] == 'char *':
        return dict(kind='string', name='QString', bend='String', raw='String',
                    result_conversion='owned_terminated_text')
    if source['pointers'] != 1 or not source['const']:
        return None
    metadata = owner in ('QMetaClassInfo', 'QMetaEnum', 'QMetaMethod', 'QMetaObject',
                         'QMetaProperty', 'QMetaType', 'QGenericArgument')
    text = metadata or (owner.startswith(('QOpenGLFunctions', 'QOpenGLExtraFunctions'))
                        and method in ('glGetString', 'glGetStringi')) or (owner, method) in {
        ('QLibraryInfo', 'build'), ('QLoggingCategory', 'categoryName'),
        ('QQmlProperty', 'propertyTypeName'), ('QStringConverter', 'name'),
        ('QStringConverter', 'nameForEncoding'),
        ('QOpenGLFunctions', 'glGetString'), ('QOpenGLExtraFunctions', 'glGetStringi'),
        ('QTest', 'currentAppName'), ('QTest', 'currentDataTag'),
        ('QTest', 'currentGlobalDataTag'), ('QTest', 'currentTestFunction'),
        ('', 'qVersion'), ('', 'qWebEngineVersion'),
        ('', 'qWebEngineChromiumVersion'), ('', 'qWebEngineChromiumSecurityPatchVersion'),
        ('QRhi', 'backendName'),
    }
    if not text or source['name'] not in ('char', 'unsigned char', 'uchar'):
        return None
    string = dict(name='QString', cpp='QString', const=False, pointers=0, reference=0,
                  container=False, enum=False, flags=False, instantiations=[])
    converted = g.conversions.container(dict(string, name='std::optional',
        cpp='std::optional<QString>', instantiations=[string]), True)
    # Keep method-specific adaptation outside the shared optional codec.
    return dict(converted, result_conversion='terminated_text')


def expression(t, value):
    if t.get('result_conversion') == 'cbor_chunk':
        return f'std::make_pair(({value}).data, ({value}).status)'
    if t.get('result_conversion') == 'thread_identity':
        return f'reinterpret_cast<quintptr>({value})'
    if t.get('result_conversion') == 'rhi_descriptor_snapshot':
        return f'(*({value}))'
    import borrowed_values
    converted = borrowed_values.expression(t, value)
    if converted is not None:
        return converted
    if t.get('result_conversion') == 'terminated_text':
        return (f'(({value}) ? std::optional<QString>(QString::fromUtf8('
                f'reinterpret_cast<const char *>({value}))) : std::nullopt)')
    if t.get('result_conversion') == 'owned_terminated_text':
        return (f'([](char *text) {{ std::unique_ptr<char[]> owner(text); '
                f'return QString::fromUtf8(text); }})({value})')
    return value
