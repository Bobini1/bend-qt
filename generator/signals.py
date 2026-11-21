"""Native Qt signals as Signal declarations, and shared handler decoders.

As in PySide, a native signal and one declared in Bend are the same kind of
value. `QSlider.rangeChanged()` declares the native signal of QSlider, and
`Signal.connect`, `Signal.connectWith`, `Signal.emit` and the signal
destinations find it by name and argument types in the object's meta-object.
The declaration carries the sender's class, so
`Signal.connect(~Qt.QSlider.rangeChanged(), ~S, ~f, slider, state)` takes a
QSlider and `f: S -> Int32 -> Int32 -> Action(Unit)`.

Arguments are copied, except a value class passed by non-const reference or
pointer, such as the QAuthenticator of authenticationRequired. The handler then
gets a borrowed handle to Qt's own object, valid during the call, as PySide
passes it, and such an argument is delivered only synchronously. A QObject
passed by reference arrives as its usual handle. `QObject.destroyed()` passes
the identity of the destroyed object, whose handle is already invalid.

Signal.emit uses QMetaObject::activate, as PySide does, so it also reaches
signals Qt declares with QPrivateSignal. The runtime refuses to emit the
signals in RESERVED_EMISSIONS, which it observes itself.
"""
import re

from conversions import native as native_type

UNIT = dict(kind='void', bend='Unit', raw='Unit')
CONNECTION = dict(kind='connection', bend='Connection', raw='U32')
SIGNAL = dict(kind='signal', bend='Signal', raw='Unit')
# The runtime's descriptor name for the identity QObject.destroyed passes.
IDENTITY = 'BendObjectIdentity'

# The runtime observes these signals to release native resources or to run
# Bend's scheduler. An emission from Bend would free resources that are still
# in use or re-enter the scheduler, so Signal.emit refuses them.
RESERVED_EMISSIONS = {
    'QObject::destroyed': 'The runtime releases handles and retained values when this signal reports destruction',
    'QQuickWindow::beforeSynchronizing': 'The runtime collects released scene graph resources on this render-thread signal',
    'QQuickWindow::afterSynchronizing': 'The runtime finishes render factory work on this render-thread signal',
    'QQuickWindow::sceneGraphInvalidated': 'The runtime releases scene graph resources when this signal reports invalidation',
    'QOpenGLContext::aboutToBeDestroyed': 'The runtime releases GL resources when this signal reports context destruction',
    'QAbstractEventDispatcher::aboutToBlock': "The runtime runs Bend's scheduler from this signal",
    'QAbstractEventDispatcher::awake': "The runtime runs Bend's scheduler from this signal",
}


def ident(name):
    return name.replace('::', '.')


def normalized(cpp):
    """A C++ type spelling as Qt normalizes it, such as `QAction*`."""
    return re.sub(r'\s*([*&,<>])\s*', r'\1', cpp.strip())


def argument(g, a):
    """The runtime descriptor name and Bend conversion of one signal argument."""
    if a.get('removed') or a.get('array'):
        raise ValueError('Signal array or removed argument needs an explicit converter')
    source = a['type']
    if source['reference'] == 2:
        raise ValueError('A signal cannot pass an rvalue reference')
    cls = g.classes.get(source['name'])
    identity = cls and (cls['qobject'] or cls.get('native_object'))
    borrowed = cls and not identity and cls.get('value') and source['name'] in g.ids
    if source['pointers'] or (source['reference'] and (identity or (borrowed and not source['const']))):
        if source['pointers'] > 1 or not (identity or borrowed):
            raise ValueError('A signal pointer argument needs an explicit lifetime policy')
        if identity:
            t = g.type(dict(source, pointers=1, reference=0, cpp=source['name'] + ' *'))
        else:
            # Qt's own value, borrowed for the call (see the module doc).
            const = 'const ' if source['const'] else ''
            t = dict(kind='object', name=source['name'], bend=ident(source['name']), raw='U32',
                     cpp=const + source['name'] + ' *', pointer=True, native_const=bool(source['const']))
        g.conversions.register(t)
        name = normalized(native_type(t))
        return (name.removesuffix('*') + '&' if source['reference'] else name), t
    if source['reference'] and not source['const']:
        raise ValueError('A mutable signal argument of this type needs a reply policy')
    t = g.type(source)
    if t['kind'] == 'void' or g.conversions.contains(t, ('string_view', 'byte_view', 'latin1_view', 'std_string')):
        raise ValueError('Signal arguments require owning representations')
    if t['kind'] == 'value' and not g.classes[t['name']].get('copyable', False):
        raise ValueError('Signal value arguments must be copyable')
    enum = g.enums.get(t['name'][7:-1] if t['kind'].startswith('flags') else t.get('name'))
    if t['kind'].startswith(('enum', 'flags')) and enum and not enum.get('public', True):
        raise ValueError('A protected enum signal argument has no public native metatype name')
    g.conversions.register(t)
    return normalized(native_type(t)), t


def describe(g, f):
    """The arguments of native signal `f`: (descriptor name, conversion) pairs."""
    if f['declaring_class'] == 'QObject' and f['name'] == 'destroyed':
        g.types['ObjectIdentity'] = 'scalar'
        return dict(args=[(IDENTITY, dict(kind='identity', bend='ObjectIdentity', raw='U32'))])
    return dict(args=[argument(g, a) for a in f['arguments']])


def descriptor(g, m, doc):
    """The Bend declaration of native signal `m` for its receiver class."""
    from module_partitions import schema_dependency
    owner = ident(m['class'])
    arguments = []
    flags = 2 if any(borrowed(g, t) for _, t in m['signal']['args']) else 0
    for name, t in m['signal']['args']:
        if name == IDENTITY:
            arguments.append('ObjectIdentity.arg()')
        else:
            arguments.append(f'TypeDescriptor{{{t["bend"]}, "{name}", value => {t["codec"]}.encode(value), '
                             f'wire => {t["codec"]}.decode(wire), {schema_dependency(g)}}}')
    g.bend += [doc, f'def {m["bend_name"]}() -> Signal:',
               f'  Internal.Signal.native("{m["function"]["name"]}", [{", ".join(arguments)}], {flags}, '
               f'SignalSender{{{owner}, value => {owner}.word(value)}})', '']


def borrowed(g, t):
    """Whether the argument is Qt's own value, borrowed for the call."""
    return t['kind'] == 'object' and not g.classes[t['name']]['qobject'] and not g.classes[t['name']].get('native_object')


def reserved_cpp():
    return ', '.join('{"' + owner + '", "' + name + '"}'
                     for owner, name in (key.split('::') for key in sorted(RESERVED_EMISSIONS)))


def inventory(g):
    excluded = {}
    for e in g.excluded:
        if e.get('signal'):
            excluded[e['reason']] = excluded.get(e['reason'], 0) + 1
    return dict(declarations=sum('signal' in m for m in g.methods), excluded=dict(sorted(excluded.items())),
                reserved_emissions=RESERVED_EMISSIONS,
                borrowed_arguments=sorted({name for m in g.methods if 'signal' in m
                                           for name, t in m['signal']['args'] if borrowed(g, t)}))


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
    """The Connection handle and its scope."""
    g.types['Connection'] = 'handle'
    g.emit_effect('Connection.disconnect', [('self', CONNECTION)], UNIT, 2, has_self=True)
    g.emit_scope('Connection', 'disconnect')
    import scope_actions
    scope_actions.escapes(g, 'Connection', 1)
