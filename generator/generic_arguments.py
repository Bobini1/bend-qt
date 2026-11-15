"""Typed, retained storage for Qt's legacy generic meta-call arguments."""
from pathlib import Path

TYPES = {'QGenericArgument', 'QGenericReturnArgument'}


def constructor(f):
    return f['declaring_class'] in TYPES and f['constructor'] and any(a['type']['name'] == 'void' for a in f['arguments'])


def parameters(g, f):
    if not constructor(f) and not (f['declaring_class'] == 'QMetaMethod' and f['name'] == 'invokeOnGadget'):
        return None
    args = []
    for a in f['arguments']:
        t = a['type']
        if t['name'] == 'void' and t['pointers']:
            converted = dict(kind='value', name='MetaStorage', cpp='MetaStorage', bend='MetaStorage', raw='U32', pointer=False)
        elif t['name'] == 'char' and t['pointers']:
            converted = dict(kind='string', cpp='QString', bend='String', raw='String')
        else:
            converted = g.type(t)
        args.append(converted)
    return args, [dict(type=t, source=i, input=i, output=False, mutable=False) for i, t in enumerate(args)], []


def adapt(g, f):
    if f['declaring_class'] in TYPES and f['name'] == 'data':
        return dict(kind='value', name='MetaStorage', cpp='MetaStorage', bend='MetaStorage', raw='U32', generic_data=True)
    return None


def method_case(g, m):
    f = m['function']
    if constructor(f):
        name = 'QString::fromUtf8(r->arguments[0].text, qsizetype(r->arguments[0].size))' if m['args'] else 'QString()'
        source = 'r->arguments[1].word' if len(m['args']) > 1 else '0'
        native = f['declaring_class']
        return ['NativeCallScope scope;',
                f'r->result.word = new_generic_argument<{native}>(r, {g.ids[native]}, {name}, {str(bool(m["args"])).lower()}, {source});',
                'r->result.owned_handle = r->result.word;', 'return true;']
    if f['declaring_class'] in TYPES and f['name'] == 'data':
        return ['NativeCallScope scope;',
                f'get<{m["class"]}>(r, r->self, {g.ids[m["class"]]}, false, false);',
                'if (r->error) return true;', 'r->result.word = generic_argument_storage(r, r->self);',
                'r->result.owned_handle = r->result.word;', 'return true;']
    if f['declaring_class'] == 'QMetaMethod' and f['name'] == 'invokeOnGadget':
        lines = ['NativeCallScope call_scope;',
                 f'auto *self = get<QMetaMethod>(r, r->self, {g.ids["QMetaMethod"]}, false, false);']
        arguments = []
        for i, t in enumerate(m['args']):
            declaration, expression = ([f'auto *a0 = get<MetaStorage>(r, r->arguments[0].word, {g.ids["MetaStorage"]}, false, false);'], 'a0->data') if i == 0 else g.argument(t, i)
            lines += declaration
            arguments.append('a0->data' if i == 0 else expression)
        lines += ['if (r->error) return true;',
                  'if (!meta_storage_ready(r, a0, a0->type, true, !self->isConst(), r->arguments[0].word)) return true;',
                  'auto *origin = a0->type.metaObject();',
                  'if (!origin || !a0->type.flags().testFlag(QMetaType::IsGadget) || !self->isValid() || !origin->inherits(self->enclosingMetaObject())) return fail(r, EINVAL, "Method does not belong to the stored gadget");']
        lines += invocation(g, m)
        lines += [f'bool returned = self->invokeOnGadget(' + ', '.join(arguments) + ');',
                  'if (!generic_call.finish(returned)) return true;', 'r->result.word = returned;', 'return true;']
        return lines
    return None


def before_call(g, m):
    f = m['function']
    if f['declaring_class'] in TYPES and m['args'] and m['args'][0].get('name') in TYPES:
        return ['call_scope.value_origin = r->arguments[0].word;']
    return invocation(g, m)


def after_call(g, m):
    f = m['function']
    if f['declaring_class'] in TYPES and f['name'] == 'operator=':
        return ['if (!finish_generic_argument_ownership(r, r->self)) return true;']
    if is_invocation(m['function']):
        return ['if (!generic_call.finish(bool(returned))) return true;']
    return []


def is_invocation(f):
    return (f['declaring_class'] == 'QMetaMethod' and f['name'] in ('invoke', 'invokeOnGadget')) or (f['declaring_class'] == 'QMetaObject' and f['name'] in ('invokeMethod', 'newInstance'))


def invocation(g, m):
    f = m['function']
    if not is_invocation(f):
        return []
    arguments = [(i, t) for i, t in enumerate(m['args']) if t.get('name') in TYPES]
    if any(t.get('name', '').startswith('QtCoreHelper::') for t in m['args']):
        return []
    ids = '{' + ', '.join('{r->arguments[' + str(i) + '].word, ' + str(t['name'] == 'QGenericReturnArgument').lower() + '}' for i, t in arguments) + '}'
    conn = next((g.argument(t, i)[1] for i, t in enumerate(m['args']) if t.get('name') == 'Qt::ConnectionType'), 'Qt::AutoConnection')
    receiver = 'r->arguments[0].word' if f['name'] in ('invoke', 'invokeMethod') else '0'
    if f['declaring_class'] == 'QMetaMethod':
        method = '*self'
    elif f['name'] == 'newInstance':
        method = f'find_generic_method(self, QByteArray(), {ids}, true)'
    else:
        method = f'find_generic_method(a0->metaObject(), QByteArray(r->arguments[1].text, qsizetype(r->arguments[1].size)), {ids}, false)'
    return [f'GenericMetaCall generic_call(r, {method}, {receiver}, {conn}, {ids});',
            'if (r->error || generic_call.handled) return true;']


def emit(g):
    if not (TYPES | {'MetaStorage'}) <= set(g.ids):
        return
    storage = dict(kind='value', name='MetaStorage', cpp='MetaStorage', bend='MetaStorage', raw='U32')
    for name in sorted(TYPES):
        operation = g.next_id; g.next_id += 1
        result = dict(kind='value', name=name, cpp=name, bend=name, raw='U32')
        g.cases.append(f'''case {operation}: {{
    NativeCallScope scope;
    auto *storage = get<MetaStorage>(r, r->arguments[0].word, {g.ids['MetaStorage']}, false, false);
    if (r->error) return true;
    r->result.word = new_generic_argument<{name}>(r, {g.ids[name]}, QString::fromUtf8(storage->type.name()), true, r->arguments[0].word);
    r->result.owned_handle = r->result.word;
    return true;
}}''')
        g.emit_effect(name + '.fromStorage', [('value', storage)], result, operation)


def cpp(g):
    if not (TYPES | {'MetaStorage'}) <= set(g.ids):
        return '''static uint32_t finish_generic_argument_ownership(BqtRequest *, uint32_t id) { return id; }
static void generic_argument_forget(uint32_t) {}
'''
    source = (Path(__file__).parent / 'templates/generic_arguments.cpp').read_text()
    for name in (*sorted(TYPES), 'MetaStorage'):
        source = source.replace('@' + name + '@', str(g.ids[name]))
    return source
