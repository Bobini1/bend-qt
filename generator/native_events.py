"""Callback-scoped native platform messages, without guessing opaque extents."""


def handles(f):
    return (f['declaring_class'], f['name']) in {
        ('QAbstractNativeEventFilter', 'nativeEventFilter'),
        ('QAbstractEventDispatcher', 'filterNativeEvent'),
        ('QWidget', 'nativeEvent'), ('QWindow', 'nativeEvent')}


def install(classes, selected):
    classes['NativeEvent'] = dict(name='NativeEvent', object=True, value=False,
        qobject=False, copyable=False, public_destructor=True, abstract=False,
        namespace=False, generate=False, template=False, bases=[], functions=[], enums=[], adapter=True,
        native_object=True)
    selected.append('NativeEvent')


def handle():
    return dict(kind='object', name='NativeEvent', cpp='NativeEvent *', bend='NativeEvent',
                raw='U32', pointer=True, required_pointer=True)


def parameters(g, f):
    if not handles(f):
        return None
    event_type = g.type(f['arguments'][0]['type'])
    result = dict(f['arguments'][2]['type'], pointers=0, reference=0, cpp='qintptr')
    output = dict(type=g.conversions.register(g.type(result)), source=2, input=None, output=True, mutable=False)
    return [event_type, handle()], [
        dict(type=event_type, source=0, input=0, output=False, mutable=False),
        dict(type=handle(), source=1, input=1, output=False, mutable=False), output], [output]


def callback_argument(g, f, index):
    if not handles(f):
        return None
    if index == 1:
        return dict(handle(), callback_native_event=True)
    if index == 2:
        from callback_adapters import optional, source
        return dict(optional(g, source('qintptr')), callback_scalar_pointer=True,
                    callback_pointee='qintptr', callback_output_only=True)
    return None


def method_case(g, m):
    f = m['function']
    if not handles(f):
        return None
    owner = f['declaring_class']
    import protected_members
    arguments = ['*type', 'message->message', '&output']
    call = protected_members.expression(g, f, arguments) or f'self->{f["name"]}({", ".join(arguments)})'
    lines = ['NativeCallScope scope;',
             f'auto *self = get<{owner}>(r, r->self, {g.ids[owner]});',
             f'auto *type = get<QByteArray>(r, r->arguments[0].word, {g.ids["QByteArray"]}, false, false);',
             f'auto *message = get<NativeEvent>(r, r->arguments[1].word, {g.ids["NativeEvent"]}, false, false);',
             'if (r->error) return true;',
             'if (*type != message->type) return fail(r, EINVAL, "Native event type does not match its scoped message");',
             'qintptr output = 0;',
             f'bool filtered = {call};',
             'r->result = sequence_value(2);']
    for i, (t, value) in enumerate(zip(m['return']['children'], ('filtered', 'output'))):
        lines += [f'if (!r->error) r->result.items[{i}] = write_{t["native_codec"]}(r, {value});']
    return lines + ['return true;']


def emit(g):
    event = handle()
    specs = [
        ('eventType', dict(kind='value', name='QByteArray', bend='QByteArray', raw='U32'),
         f'r->result.word = own(r, new QByteArray(self->type), {g.ids["QByteArray"]}); r->result.owned_handle = r->result.word;'),
        ('isNull', dict(kind='bool', bend='Bool', raw='U32'), 'r->result.word = !self->message;'),
        ('unsafeAddress', dict(kind='u64', bend='UInt64', raw='U32 & U32'),
         'r->result = wide_value(uintptr_t(self->message));'),
        ('xcbHeader', dict(kind='value', name='QByteArray', bend='QByteArray', raw='U32'),
         'if (self->type != "xcb_generic_event_t") return fail(r, ENOTSUP, "Only the XCB wire header has a known snapshot extent");\n'
         'if (!self->message) return fail(r, ENODATA, "Native event message is null");\n'
         f'r->result.word = own(r, new QByteArray(static_cast<const char *>(self->message), 32), {g.ids["QByteArray"]}); r->result.owned_handle = r->result.word;'),
    ]
    for name, result, body in specs:
        operation = g.next_id; g.next_id += 1
        g.cases.append(f'''case {operation}: {{
    NativeCallScope scope;
    auto *self = get<NativeEvent>(r, r->self, {g.ids['NativeEvent']}, false, false);
    if (r->error) return true;
    {body}
    return true;
}}''')
        g.emit_effect('NativeEvent.' + name, [('self', event)], result, operation, has_self=True)
