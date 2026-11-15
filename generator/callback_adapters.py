"""Audited native reverse-call contracts absent from PySide's Python surface.

These select contracts, not classes. All discovery remains upstream-driven.
"""


def source(name, cpp=None):
    return dict(name=name, cpp=cpp or name, const=False, pointers=0, reference=0,
                enum=False, flags=False, container=False, instantiations=[])


def optional(g, child):
    return g.conversions.container(dict(source('std::optional', 'std::optional<' + child['cpp'] + '>'),
                                       container=True, instantiations=[child]), False)


def accessibility_output(function):
    return (function['declaring_class'] == 'QAccessibleTextInterface' and
            function['minimal_signature'] in ('attributes(int,int*,int*)const',
                                               'selection(int,int*,int*)const'))


def validate_reply(function):
    if (function['declaring_class'], function['name']) == ('QQuick3DInstancing', 'getInstanceBuffer'):
        return ['if (*out0 && (**out0 < 0 || size_t(**out0) > size_t(returned->size()) / sizeof(QQuick3DInstancing::InstanceTableEntry))) {',
                '    fail(r, EINVAL, "Instance count exceeds the returned native instance table"); return false;', '}']
    return []


def argument(g, function, index, argument):
    import callback_arrays
    array = callback_arrays.argument(g, function, index, argument)
    if array is not None:
        return array
    import value_pointer_inputs
    if value_pointer_inputs.nmea(function):
        if index == 0:
            native = argument['type']
            if native['name'] == 'QByteArrayView' or (native['name'] == 'char' and native['pointers'] == 1 and native['const']):
                value = g.conversions.register(g.type(source('QByteArray')))
                return dict(value, callback_owned_bytes=True,
                            callback_bytes_view=native['name'] == 'QByteArrayView', callback_bytes_count=1)
        if argument['type']['name'] == 'bool' and argument['type']['pointers'] == 1:
            return dict(optional(g, source('bool')), callback_scalar_pointer=True,
                        callback_pointee='bool', callback_output_only=True)
    import native_events
    event = native_events.callback_argument(g, function, index)
    if event:
        return event
    if accessibility_output(function) and index in (1, 2):
        if argument['type']['cpp'].replace(' ', '') != 'int*':
            raise ValueError('Unknown accessible text output contract')
        child = source('int')
        return dict(optional(g, child), callback_scalar_pointer=True,
                    callback_pointee='int', callback_output_only=True)
    output_contracts = {
        ('QCanBusFactory', 'availableDevices'): {0: 'QString'},
        ('QCanBusFactory', 'createDevice'): {1: 'QString'},
        ('QDesignerFormWindowInterface', 'layoutDefault'): {0: 'int', 1: 'int'},
        ('QDesignerFormWindowInterface', 'layoutFunction'): {0: 'QString', 1: 'QString'},
        ('QDesignerFormWindowInterface', 'setContents'): {1: 'QString'},
        ('QQuick3DInstancing', 'getInstanceBuffer'): {0: 'int'},
        ('QScxmlCompiler::Loader', 'load'): {2: 'QStringList'},
        ('QScxmlDataModel', 'evaluateAssignment'): {1: 'bool'},
        ('QScxmlDataModel', 'evaluateForeach'): {1: 'bool'},
        ('QScxmlDataModel', 'evaluateInitialization'): {1: 'bool'},
        ('QScxmlDataModel', 'evaluateToBool'): {1: 'bool'},
        ('QScxmlDataModel', 'evaluateToString'): {1: 'bool'},
        ('QScxmlDataModel', 'evaluateToVariant'): {1: 'bool'},
        ('QScxmlDataModel', 'evaluateToVoid'): {1: 'bool'},
        ('QScxmlDataModel::ForeachLoopBody', 'run'): {0: 'bool'},
        ('QGraphicsLayoutItem', 'getContentsMargins'): {0: 'qreal', 1: 'qreal', 2: 'qreal', 3: 'qreal'},
        ('QWebEnginePage', 'javaScriptPrompt'): {3: 'QString'},
        ('QGeoServiceProviderFactory', 'createGeocodingManagerEngine'): {1: 'QGeoServiceProvider::Error', 2: 'QString'},
        ('QGeoServiceProviderFactory', 'createPlaceManagerEngine'): {1: 'QGeoServiceProvider::Error', 2: 'QString'},
        ('QGeoServiceProviderFactory', 'createRoutingManagerEngine'): {1: 'QGeoServiceProvider::Error', 2: 'QString'},
    }
    output = output_contracts.get((function['declaring_class'], function['name']), {}).get(index)
    if output:
        if argument['type']['cpp'].replace(' ', '') != output + '*':
            raise ValueError('Unknown reverse output-pointer contract')
        child = dict(argument['type'], pointers=0, reference=0, const=False, cpp=output)
        return dict(optional(g, child), callback_scalar_pointer=True,
                    callback_pointee=output, callback_output_only=True)
    if (function['declaring_class'], function['name'], index) == ('QDesignerFormWindowInterface', 'simplifySelection', 0):
        pointee = dict(argument['type'], pointers=0, const=False,
                       cpp=argument['type']['cpp'].replace('*', '').strip())
        # Strip only the outer pointer; the element's QWidget* remains intact.
        pointee['cpp'] = 'QList<QWidget*>'
        return dict(optional(g, pointee), callback_scalar_pointer=True,
                    callback_pointee=pointee['cpp'], callback_output_only=False)
    if ((function['declaring_class'], function['name'], index) in
            (('QQmlExtensionInterface', 'initializeEngine', 1),
             ('QQmlTypesExtensionInterface', 'registerTypes', 0))):
        if argument['type']['cpp'].replace(' ', '') != 'constchar*':
            raise ValueError('Unknown QML extension URI contract')
        # An owned UTF-8 string copy, with nullptr distinct from an empty URI.
        return dict(optional(g, source('QString')), callback_cstring=True)
    if (function['declaring_class'], function['name'], index) == ('QGeoAreaMonitorSource', 'requestUpdate', 1):
        return dict(optional(g, source('QString')), callback_cstring=True)
    import buffers
    policies, _ = buffers.policies(function)
    policy = policies.get(index, {})
    if policy.get('cstring'):
        return dict(optional(g, source('QString')), callback_cstring=True)
    if policy.get('bytes') and not policy.get('writable') and 'count_source' in policy:
        value = g.conversions.register(g.type(source('QByteArray')))
        return dict(value, callback_owned_bytes=True, callback_bytes_view=False,
                    callback_bytes_count=policy['count_source'])
    if argument.get('removed'):
        for source_index, source_policy in policies.items():
            if (source_policy.get('bytes') and not source_policy.get('writable')
                    and source_policy.get('count_source') == index):
                return g.conversions.register(g.type(argument['type']))
    return None
