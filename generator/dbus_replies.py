"""Restore typed Qt DBus replies erased by PySide's Python helper type.

Every mapping is checked against decltype(the actual Qt call) in generated C++.
The public value is an optional typed payload plus a copied structured error.
No borrowed QDBusError or Python helper object escapes the call.
"""


def scalar(name, **fields):
    return dict(name=name, cpp=name, const=False, pointers=0, reference=0,
                container=False, enum=False, flags=False, instantiations=[], **fields)


def adapt(g, f):
    if (f['declaring_class'], f['name']) == ('QDBusConnection', 'interface'):
        return dict(g.type(f['return'], result=True), dbus_interface_lease=True)
    if f['return']['name'] not in ('QtDBusHelper::QDBusReply', 'QDBusReply'):
        return None
    if f['declaring_class'] != 'QDBusConnectionInterface':
        raise ValueError('Unknown native DBus helper return needs its typed reply restored')
    types = {
        'activatableServiceNames': 'QStringList', 'registeredServiceNames': 'QStringList',
        'isServiceRegistered': 'bool', 'unregisterService': 'bool',
        'serviceOwner': 'QString', 'servicePid': 'uint', 'serviceUid': 'uint',
        'registerService': 'QDBusConnectionInterface::RegisterServiceReply',
        'startService': 'void',
        'serviceCredentials': 'QVariantMap',
    }
    name = types.get(f['name'])
    if name is None:
        raise ValueError('Unknown native DBus helper return needs its typed reply restored')
    if name == 'QStringList':
        source = dict(scalar('QList'), cpp='QStringList', container=True,
                      instantiations=[scalar('QString')])
    elif name == 'QVariantMap':
        source = dict(scalar('QMap'), cpp='QVariantMap', container=True,
                      instantiations=[scalar('QString'), scalar('QVariant')])
    else:
        source = scalar(name)
        source['enum'] = name.endswith('::RegisterServiceReply')
    value = g.type(source, result=True)
    if value['kind'] == 'void':
        value.pop('cpp', None)  # Unit has no C++ value codec.
    value = g.conversions.register(value)
    optional = g.conversions.register(dict(kind='optional', children=[value],
        bend=f'Maybe<&2, {value["bend"]}>', raw='Wire', codec='Optional_' + value['codec']))
    error_fields = [g.conversions.register(g.type(scalar(n), result=True))
                    for n in ('uint', 'QString', 'QString')]
    error = g.conversions.register(dict(kind='record', children=error_fields,
        bend='DBusError', raw='Wire', codec='Convert_DBusError'))
    label = 'DBusReply_' + value['codec'].removeprefix('Convert_')
    reply = g.conversions.register(dict(kind='record', children=[optional, error],
        bend=label, raw='Wire', codec='Convert_' + label))
    return dict(reply, result_conversion='dbus_reply', dbus_value=value,
                dbus_native='QDBusReply<' + name + '>')


def store(g, t, expression):
    if t.get('dbus_interface_lease'):
        return [f'r->result.word = make_dbus_interface_lease(r, *self, {expression});',
                'r->result.owned_handle = r->result.word;']
    if t.get('result_conversion') != 'dbus_reply':
        return None
    value = t['dbus_value']
    lines = [f'static_assert(std::is_same_v<std::remove_cv_t<std::remove_reference_t<decltype({expression})>>, {t["dbus_native"]}>);',
             'r->result = sequence_value(2);',
             f'r->result.items[0] = sequence_value(({expression}).isValid() ? 1 : 0);']
    if value['kind'] != 'void':
        lines += [f'if (({expression}).isValid()) r->result.items[0].items[0] = write_{value["native_codec"]}(r, ({expression}).value());']
    lines += ['if (!r->error) {', '    r->result.items[1] = sequence_value(3);',
              f'    const auto &dbus_error = ({expression}).error();',
              '    r->result.items[1].items[0].word = uint32_t(dbus_error.type());',
              '    r->result.items[1].items[1] = string_value(dbus_error.name());',
              '    r->result.items[1].items[2] = string_value(dbus_error.message());', '}']
    return lines


def safe_receiver(f):
    # QDBusConnectionInterface typed methods all call the explicitly threadsafe
    # callWithArgumentList/asyncCallWithArgumentList. The daemon interface is
    # immutable after connection construction. Other QObject APIs keep their
    # ordinary affinity check. QObject::connect itself is threadsafe.
    return ((f['declaring_class'] == 'QDBusConnectionInterface' and
             (f['return']['name'] in ('QtDBusHelper::QDBusReply', 'QDBusReply') or f['signal'])) or
            (f['declaring_class'] == 'QDBusAbstractInterface' and f['name'] in
             ('callWithArgumentList', 'asyncCallWithArgumentList')))


def method_case(g, m):
    f = m['function']
    if (f['declaring_class'], f['name']) != ('QDBusAbstractInterface', 'connection'):
        return None
    return ['NativeCallScope call_scope;',
            'if (auto *lease = dbus_interface_lease(r->self)) {',
            '    call_scope.pin(r, r->self); if (r->error) return true;',
            f'    r->result.word = own(r, new QDBusConnection(lease->connection), {g.ids["QDBusConnection"]});',
            '} else {',
            f'    auto *self = get<QDBusAbstractInterface>(r, r->self, {g.ids["QDBusAbstractInterface"]}, false, false);',
            '    if (r->error) return true;',
            f'    r->result.word = own(r, new QDBusConnection(self->connection()), {g.ids["QDBusConnection"]});',
            '}', 'r->result.owned_handle = r->result.word;', 'return true;']


def cpp(g):
    if 'QDBusConnectionInterface' not in g.ids:
        return 'static bool dbus_cleanup_precheck(BqtRequest *, uint32_t, uint16_t) { return false; }\n'
    types = ', '.join(str(g.ids[n]) for n in ('QObject', 'QDBusAbstractInterfaceBase', 'QDBusAbstractInterface', 'QDBusConnectionInterface') if n in g.ids)
    return f'''
// A daemon interface lives in Qt's DBus thread. The registry owns a connection
// lease, never that foreign QObject, so ordinary QObject operations cannot
// accidentally bypass affinity or run its destructor on the main thread.
struct DBusInterfaceLease {{
    QDBusConnection connection;
    QDBusConnectionInterface *daemon;
}};
static void destroy_dbus_interface_lease(void *value) {{ delete static_cast<DBusInterfaceLease *>(value); }}
static DBusInterfaceLease *dbus_interface_lease(uint32_t id) {{
    auto *e = entry(id);
    return e && e->destroy == destroy_dbus_interface_lease ? static_cast<DBusInterfaceLease *>(e->value) : nullptr;
}}
static bool deny_foreign_dbus_operation(BqtRequest *r, uint32_t) {{
    fail(r, EXDEV, "Foreign DBus interfaces expose only audited thread-safe calls and signals"); return false;
}}
static uint32_t make_dbus_interface_lease(BqtRequest *r, const QDBusConnection &connection, QDBusConnectionInterface *daemon) {{
    if (!daemon) return 0;
    auto lease = std::make_unique<DBusInterfaceLease>(DBusInterfaceLease{{connection, daemon}});
    uint32_t id = insert(r, lease.release(), nullptr, {g.ids['QDBusConnectionInterface']}, destroy_dbus_interface_lease, true);
    if (!id) return 0;
    entry(id)->validate = deny_foreign_dbus_operation;
    return id;
}}
template<class T> static T *get_dbus_receiver(BqtRequest *r, uint32_t id, uint16_t type, bool writable) {{
    if (auto *lease = dbus_interface_lease(id)) {{
        // The owned QDBusConnection reference keeps its daemon interface alive
        // even after disconnectFromBus removes the public connection name.
        if (lease->connection.interface() != lease->daemon) {{
            fail(r, ESTALE, "DBus daemon interface was replaced"); return nullptr;
        }}
        if (native_call_scope) native_call_scope->pin(r, id);
        if (r->error) return nullptr;
        return static_cast<T *>(lease->daemon);
    }}
    return get<T>(r, id, type, false, writable);
}}
static bool dbus_cleanup_precheck(BqtRequest *r, uint32_t id, uint16_t type) {{
    if (!dbus_interface_lease(id)) return false;
    for (uint16_t compatible : {{{types}}}) if (type == compatible) return true;
    fail(r, EINVAL, "DBus interface lease has the wrong cleanup type"); return true;
}}
'''


def bend(g):
    replies = {m['return']['bend']: m['return'] for m in g.methods
               if m['return'].get('result_conversion') == 'dbus_reply'}
    if not replies:
        return ''
    lines = ['def DBusError.code(value: DBusError) -> U32:', '  DBusError.arg0(value)', '',
             'def DBusError.name(value: DBusError) -> String:', '  DBusError.arg1(value)', '',
             'def DBusError.message(value: DBusError) -> String:', '  DBusError.arg2(value)', '']
    for typ, t in sorted(replies.items()):
        value = t['dbus_value']['bend']
        lines += [f'def {typ}.value(reply: {typ}) -> Maybe<&2, {value}>:', f'  {typ}.arg0(reply)', '',
                  f'def {typ}.error(reply: {typ}) -> DBusError:', f'  {typ}.arg1(reply)', '',
                  f'def {typ}.isValid(reply: {typ}) -> Bool:',
                  f'  Codec.optional_valid(~{value}, {typ}.arg0(reply))', '']
    return '\n'.join(lines)
