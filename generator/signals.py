"""Direct typed signal connectors, sharing internal handler decoders.

`QPushButton.connect_clicked(~S, ~f, button, state)` connects the Bend handler
`f`, which Qt then calls like a slot: at once, on Qt's own stack, when the
signal is emitted on the main thread, and through Qt's queued delivery when it
is emitted on another thread. Arguments are valid during the call, and a
handler may change a mutable reference argument by returning its new value.

`QObject.destroyed` passes the identity of the destroyed object: its handle
is already invalid when Qt emits the signal.
"""
import re

from callbacks import _conversion, _record, _decode_output, native
import effect_transport
import volume_data

UNIT = dict(kind='void', bend='Unit', raw='Unit')
CONNECTION = dict(kind='connection', bend='Connection', raw='U32')


def c_ident(name):
    return re.sub(r'[^a-zA-Z0-9_]', '_', name)


def describe(g, f, overloaded):
    """The public entry of signal `f`: its arguments and its payload shape."""
    terminal = f['declaring_class'] == 'QObject' and f['name'] == 'destroyed'
    if overloaded and any('QPrivateSignal' in s for s in f['source_signatures']):
        raise ValueError('Overloaded private-marker signal needs a signature adapter')
    args, outputs = [], []
    if terminal:
        g.types['ObjectIdentity'] = 'scalar'
        args = [g.conversions.register(dict(kind='u32', bend='ObjectIdentity', raw='U32'))]
    elif volume_data.signal_arguments(g, f) is not None:
        args = volume_data.signal_arguments(g, f)
    else:
        for i, a in enumerate(f['arguments']):
            if a.get('removed') or a.get('array'):
                raise ValueError('Signal array or removed argument needs an explicit converter')
            source = a['type']
            value = g.classes.get(source['name'])
            pointer_copy = source['pointers'] == 1 and value and value.get('value') and value.get('copyable')
            t = _conversion(g, dict(source, pointers=0, reference=0, const=False, cpp=source['name']) if pointer_copy else source)
            t['callback_pointer_copy'] = bool(pointer_copy)
            args.append(t)
            if not source['const'] and (source['reference'] == 1 or pointer_copy) and t['kind'] != 'object':
                outputs.append((i, t))
    payload = _record(g, args, 'SignalArgs_')
    reply = _record(g, [t for _, t in outputs], 'SignalReply_') if outputs else UNIT
    name = 'SignalHandler_' + ('_'.join(c_ident(t['bend']) for t in args) or 'Unit')
    if outputs:
        name += '_Reply_' + '_'.join(str(i) for i, _ in outputs)
    kind = g.signal_kinds.get(name)
    if kind is None:
        kind = g.signal_kinds[name] = dict(name=name, payload=payload, reply=reply,
                                           arguments=[t['bend'] for t in args], mutable=bool(outputs))
    elif (kind['payload']['bend'], kind['reply']['bend']) != (payload['bend'], reply['bend']):
        raise ValueError('Two signal payload shapes share the name ' + name)
    return dict(args=args, outputs=outputs, kind=kind, terminal=terminal, overloaded=overloaded,
                private_marker=any('QPrivateSignal' in s for s in f.get('source_signatures', [])),
                result=CONNECTION)


def handler_type(arguments, result):
    return ' -> '.join(['S', *arguments, f'Action({result})'])


def invoke(g, public, arguments, payload, result, scope=None):
    """The closed wrapper Qt's request reaches: decode it, call `~f`, answer.

    A handler whose Qt call returns nothing gives no answer; it may even wait.
    Any other handler answers from inside the scope that owns its result, so
    Qt copies or adopts the value before that scope ends.
    """
    function = handler_type(arguments, result['bend'])
    fields = ', '.join(f'a{i}' for i in range(len(arguments)))
    call = 'f(' + ', '.join(['state', *[f'a{i}' for i in range(len(arguments))]]) + ')'
    if result['kind'] == 'void':
        body = call
    else:
        scope = scope or result['codec']
        body = f'{scope}.with(Unit, {call}, value => Handler.answer(call, {result["codec"]}.encode(value)))'
    g.bend += [
        f'def {public}.apply(~S: Data, ~f: {function}, state: S, call: U32, arguments: Maybe<&2, {payload["bend"]}>) -> Action(Unit):',
        '  match arguments:',
        '    case None{}: Handler.malformed(Unit)',
        f'    case Some{{{payload["bend"]}{{{fields}}}}}: {body}', '',
        f'def {public}.run(~S: Data, ~f: {function}, state: S, request: Maybe<&2, HandlerRequest>) -> Action(Unit):',
        '  match request:',
        '    case None{}: Handler.malformed(Unit)',
        f'    case Some{{HandlerRequest{{call, arguments}}}}: {public}.apply(~S, ~f, state, call, {payload["codec"]}.decode(arguments))', '',
        f'def {public}.invoke(~S: Data, ~f: {function}, pair: S & Wire) -> Action(Unit):',
        '  match pair:',
        f'    case (state, wire): {public}.run(~S, ~f, state, HandlerRequest.decode(wire))', '']
    return function


def invoke_value(g, public, value, decode):
    """The wrapper for a handler of one decoded value that answers nothing.

    `decode` is a def `Wire -> Maybe<&2, value>`. Answers the handler's type.
    """
    function = f'S -> {value} -> Action(Unit)'
    g.bend += [
        f'def {public}.apply(~S: Data, ~f: {function}, state: S, arguments: Maybe<&2, {value}>) -> Action(Unit):',
        '  match arguments:',
        '    case None{}: Handler.malformed(Unit)',
        '    case Some{value}: f(state, value)', '',
        f'def {public}.run(~S: Data, ~f: {function}, state: S, request: Maybe<&2, HandlerRequest>) -> Action(Unit):',
        '  match request:',
        '    case None{}: Handler.malformed(Unit)',
        f'    case Some{{HandlerRequest{{call, arguments}}}}: {public}.apply(~S, ~f, state, {decode}(arguments))', '',
        f'def {public}.invoke(~S: Data, ~f: {function}, pair: S & Wire) -> Action(Unit):',
        '  match pair:',
        f'    case (state, wire): {public}.run(~S, ~f, state, HandlerRequest.decode(wire))', '']
    return function


def emit(g):
    """Connection scope and shared internal handler functions."""
    g.signal_connection_method_names = {method['bend_name'] for method in g.methods}
    g.types['Connection'] = 'handle'
    g.emit_effect('Connection.disconnect', [('self', CONNECTION)], UNIT, 2, has_self=True)
    g.emit_scope('Connection', 'disconnect')
    import scope_actions
    scope_actions.keep(g, 'Connection', 1)
    for name, kind in sorted(g.signal_kinds.items()):
        invoke(g, name, kind['arguments'], kind['payload'], kind['reply'])


def entry(g, m, operation, doc=None):
    """Connect a checked Bend handler to signal `m` of one object."""
    owner = m['class'].replace('::', '.')
    kind = m['signal']['kind']
    function = handler_type(kind['arguments'], kind['reply']['bend'])
    g.emit_effect(m['bend_name'], [('self', dict(bend=owner, raw='U32')),
                  ('state', effect_transport.handler(function, kind['name'] + '.invoke'))],
                  CONNECTION, operation, has_self=True, doc=doc)
    public = m['connection_type_name']
    if public in g.signal_connection_method_names:
        raise ValueError('Native method conflicts with a connection-type helper: ' + public)
    variants = getattr(g, 'signal_connection_type_operations', None)
    if variants is None:
        variants = g.signal_connection_type_operations = {}
    with_operation = variants.get(operation)
    if with_operation is None:
        with_operation = g.next_id
        g.next_id += 1
        variants[operation] = with_operation
        g.method_case(dict(m, signal_connection_type=True), with_operation)
    g.emit_effect(public, [('self', dict(bend=owner, raw='U32')),
                  ('connectionType', dict(bend='Qt.ConnectionType', raw='U32')),
                  ('state', effect_transport.handler(function, kind['name'] + '.invoke'))],
                  CONNECTION, with_operation, has_self=True, doc=doc)


def connect_case(g, m):
    """Native code connecting a handler to signal `m`; `self` is checked."""
    f, signal = m['function'], m['signal']
    args, outputs = signal['args'], signal['outputs']
    object_references = {i for i, t in enumerate(args)
                         if t['kind'] == 'object' and not t.get('pointer')
                         and g.classes[t['name']]['qobject']}
    # Qt queues pointer values, not temporary pointees. Snapshot inputs on
    # emission; mutable replies instead keep that emitting thread waiting.
    snapshot = not outputs and any(t.get('signal_expression') or t.get('callback_pointer_copy') for t in args)
    with_type = m.get('signal_connection_type', False)
    # Capture while the emitter still owns raw text/byte storage. Qt's queued
    # argument copy can otherwise retain a fromRawData alias until too late.
    forwarded = True
    owner = f['declaring_class']
    parameters = ', '.join(a['type']['cpp'] + f' a{i}' for i, a in enumerate(f['arguments']))
    types = ', '.join(a['type']['cpp'] for a in f['arguments'])
    member = f'&{owner}::{f["name"]}'
    # Inherited overloads can be absent from the declaring class's extracted
    # function list. Always select the exact member type unless Qt
    # deliberately hides QPrivateSignal.
    if not signal['private_marker']:
        qualifier = ' const' if f['const'] else ''
        member = f'static_cast<void ({owner}::*)({types}){qualifier}>({member})'
    import protected_members
    member = protected_members.member(g, f) or member
    lines = [f'uint32_t handler = r->arguments[{1 if with_type else 0}].word;',
             f'uint32_t requested_type = {"r->arguments[0].word" if with_type else "0"};',
             'if (!callback_connection_type(r, requested_type)) return true;',
             'CallbackConnectionGuard guard;',
             'guard.id = new_connection(r, handler);',
             'if (r->error) return true;',
             'uint32_t id = guard.id, sender = r->self;',
             # The context object lives on the main thread, so Qt delivers
             # there: directly for an emission on the main thread, queued
             # otherwise.
             'connection(id)->context = new QObject;']
    if outputs:
        lines.insert(3, 'if ((requested_type & 3u) == Qt::QueuedConnection) return fail(r, ENOTSUP, "A mutable signal reply cannot be delivered asynchronously");')
    if signal['terminal']:
        # The registry forgets a destroyed sender, and closes its connections,
        # before Qt reaches this slot. This one outlives that step and closes
        # itself after its single delivery.
        lines += ['connection(id)->sender = 0;',
                  f'auto made = QObject::connect(self, {member}, connection(id)->context, [handler, id, sender, requested_type]({parameters}) {{',
                  '    auto deliver = [handler, id, sender] {',
                  '    try {',
                  '        CallbackOwnedArguments arguments{sequence_value(1)};',
                  '        arguments.value.items[0].word = sender;',
                  '        int error = callback_invoke(handler, 0, arguments.take(), callback_decode_unit, nullptr);',
                  '        if (error) callback_report_error(error);',
                  '    } catch (const std::bad_alloc &) { callback_report_error(ENOMEM); }',
                  '      catch (...) { callback_report_error(EFAULT); }',
                  '    if (auto *c = connection(id)) close_connection(*c);',
                  '    };',
                  '    if (!callback_signal_call_with_type(id, std::move(deliver), requested_type, false)) callback_signal_error(id, EPIPE);',
                  '}, Qt::DirectConnection);']
    else:
        captures = 'handler, sender, id, requested_type' if forwarded else 'handler, sender'
        lines += [f'auto made = QObject::connect(self, {member}, connection(id)->context, [{captures}]({parameters}) {{']
        if forwarded:
            lines += ['    try {']
            captures = ['handler', 'sender']
            if not outputs:
                lines += ['    BendSignalApi::Snapshot snapshots;']
            for i, t in enumerate(args):
                expression = f'a{i}'
                if snapshot and t.get('signal_expression'):
                    expression = t['signal_expression'].format(a=f'a{i}')
                elif snapshot and t.get('callback_pointer_copy'):
                    expression = f'a{i} ? std::make_optional(*a{i}) : std::nullopt'
                if not outputs:
                    # QObject references preserve the object's identity. They
                    # cannot be copied, even when the slot returns no reply.
                    if i in object_references:
                        expression = f'&a{i}'
                    lines += [f'    auto copied{i} = native_owned_snapshot({expression});',
                              f'    snapshots.guard(QVariant::fromValue(copied{i}), 0, BendSignalApi::synchronous_native_arguments(requested_type));']
                    expression = f'std::move(copied{i})'
                captures.append(f'a{i} = {expression}')
            if not outputs:
                lines += ['    BqtRequest capture{};',
                          '    if (!snapshots.capture_origins(&capture, sender)) { callback_signal_error(id, capture.error); return; }']
                captures.append('snapshots = std::move(snapshots)')
            capture = '&' if outputs else ', '.join(captures)
            lines += [f'    auto deliver = [{capture}]() mutable {{']
            if not outputs:
                lines += ['    if (!snapshots.live()) { callback_report_error(ESTALE, "A signal argument QObject was destroyed before delivery"); return; }']
        lines += ['    try {', '        BqtRequest conversion{};', '        NativeCallScope native_scope;', '        CallbackNativeArguments native_arguments;',
                  f'        CallbackOwnedArguments arguments{{sequence_value({len(args)})}};',
                  '        { NativeAggregateInputScope native_fields(&conversion);']
        if not outputs:
            lines += ['        if (!snapshots.stage_native_arguments(&conversion, native_arguments, sender)) { callback_report_error(conversion.error, conversion.message); return; }',
                      '        if (!snapshots.capture_origins(&conversion, sender)) { callback_report_error(conversion.error, conversion.message); return; }']
        for i, t in enumerate(args):
            if t.get('signal_expression'):
                expression = f'a{i}' if snapshot else t['signal_expression'].format(a=f'a{i}')
                lines += [f'        arguments.value.items[{i}] = write_{t["native_codec"]}(&conversion, {expression});']
            elif t.get('callback_pointer_copy'):
                lines += [f'        if (a{i}) arguments.value.items[{i}] = write_{t["native_codec"]}(&conversion, *a{i});']
            elif t['kind'] == 'object' and not g.classes[t['name']]['qobject']:
                value = f'a{i}' if t.get('pointer') else f'&a{i}'
                lines += [f'        arguments.value.items[{i}] = native_arguments.borrow_argument(&conversion, {value}, {g.ids[t["name"]]}, sender);']
            elif t.get('callback_enum'):
                expression = f'a{i}.toInt()' if t['kind'].startswith('flags') else f'a{i}'
                lines += [f'        arguments.value.items[{i}] = wide_value(uint64_t({expression}));']
            else:
                captured_pointer = forwarded and not outputs and i in object_references
                value = f'&a{i}' if t['kind'] == 'object' and not t.get('pointer') and not captured_pointer else f'a{i}'
                lines += [f'        arguments.value.items[{i}] = write_{t["native_codec"]}(&conversion, {value});']
        if not outputs:
            lines += ['        if (!conversion.error) snapshots.finish_output(&conversion, arguments.value);']
        lines += ['        }', '        if (conversion.error) { callback_report_error(conversion.error, conversion.message); return; }']
        if outputs:
            lines += ['        struct Reply {', *[f'            {native(t)} *out{i};' for i, t in outputs], '        };',
                      '        Reply result{' + ', '.join(f'a{i}' if t.get('callback_pointer_copy') else f'&a{i}' for i, t in outputs) + '};',
                      '        auto decode = [](BqtRequest *r, const BqtValue &wire, void *destination) {',
                      f'            if (!wire_shape(r, wire, 2, {len(outputs)})) return false;',
                      '            auto *target = static_cast<Reply *>(destination);']
            for n, (i, t) in enumerate(outputs):
                lines += ['            ' + line for line in _decode_output(i, t, f'wire.items[{n}]')]
            lines += [f'            if (target->out{i}) *target->out{i} = std::move(*out{i});' for i, t in outputs]
            lines += ['            return true;', '        };',
                      '        int error = callback_invoke(handler, sender, arguments.take(), decode, &result);']
        else:
            lines += ['        int error = callback_invoke(handler, sender, arguments.take(), callback_decode_unit, nullptr);']
        lines += ['        if (error) callback_report_error(error);',
                  '    } catch (const std::bad_alloc &) { callback_report_error(ENOMEM); }',
                  '      catch (const std::system_error &error) { callback_report_error(error.code().value()); }',
                  '      catch (...) { callback_report_error(EFAULT); }']
        if forwarded:
            lines += ['    };',
                      f'    if (!callback_signal_call_with_type(id, std::move(deliver), requested_type, {str(bool(outputs)).lower()})) callback_signal_error(id, EPIPE);',
                      '    } catch (const std::bad_alloc &) { callback_signal_error(id, ENOMEM); }',
                      '      catch (const std::system_error &error) { callback_signal_error(id, error.code().value()); }',
                      '      catch (...) { callback_signal_error(id, EFAULT); }',
                      '}, Qt::ConnectionType(uint32_t(Qt::DirectConnection) | (requested_type & uint32_t(Qt::SingleShotConnection))));']
        else:
            lines += ['});']
    lines += ['if (!made) return fail(r, EINVAL, "Qt signal connection failed");',
              'if (auto *value = connection(id)) value->connection = new QMetaObject::Connection(made);',
              'guard.keep = true;', 'r->result.word = id;']
    return lines


def inventory(g):
    return [dict(handler=name, arguments=kind['arguments'], payload=kind['payload']['bend'],
                 reply=kind['reply']['bend'], mutable_reply=kind['mutable'])
            for name, kind in sorted(g.signal_kinds.items())]
