"""Snapshots of documented, process-lived native C-string constants.

Neither a char pointer nor a fixed array alone establishes NUL termination.
The sensor identifier and ALPN constants below have that native contract.
Class discovery remains the upstream type system's responsibility.
"""


def field_type(g, name, field, setter):
    owner = field.get('declaring_class') or name
    sensor_identifier = (field['name'] == 'sensorType'
                         and (owner == 'QSensor' or 'QSensor' in g.all_bases(owner)))
    protocol = owner == 'QSslConfiguration' and field['name'] in (
        'ALPNProtocolHTTP2', 'NextProtocolHttp1_1')
    if not (sensor_identifier or protocol) or not field.get('static'):
        return None
    source = field['type']
    if source['name'] != 'char' or not source.get('const'):
        return None
    if setter:
        raise ValueError('Native string constants are read-only')
    return dict(kind='string', name='QString', cpp='QString', bend='String',
                raw='String', constant_cstring=True)


def field_access(g, field, expression, argument=None):
    if not field['type'].get('constant_cstring'):
        return None
    return g.store_result(field['type'], f'QString::fromUtf8({expression})')
