"""Scoped native interop capabilities; no untyped pointer-to-Qt constructors."""
from pathlib import Path


def install(classes, selected):
    import render_resources
    render_resources.install(classes, selected)
    import native_platform
    native_platform.install(classes, selected)
    names = []
    if any(t['name'] == 'QFunctionPointer' for c in classes.values() for f in c['functions']
           for t in [f['return'], *(a['type'] for a in f['arguments'])]):
        names.append('NativeFunction')
    for source, name in [('QSslKey', 'NativeSslKey'), ('QSslCertificate', 'NativeSslCertificate')]:
        if source in selected:
            names.append(name)
    for name in names:
        classes[name] = dict(name=name, object=False, value=True, qobject=False, copyable=False,
            public_destructor=True, abstract=False, namespace=False, generate=False, template=False,
            bases=[], functions=[], enums=[], adapter=True, native_interop=True)
        selected.append(name)


def aliases(g, inside):
    import render_resources
    import native_platform
    definitions = {
        'NativeFunction': 'struct NativeFunction { QFunctionPointer value; uint32_t owner; };',
        'NativeSslKey': 'struct NativeSslKey { QSslKey value; };',
        'NativeSslCertificate': 'struct NativeSslCertificate { QSslCertificate value; };',
    }
    names = [name for name in definitions if name in g.ids]
    if inside:
        return render_resources.aliases(g, inside) + native_platform.aliases(g, inside) + '\n'.join(definitions[name] for name in names) + '\n'
    return render_resources.aliases(g, inside) + native_platform.aliases(g, inside) + 'namespace bendqt { ' + ' '.join(f'struct {name};' for name in names) + ' }\n'


def handle(name, conversion=None):
    value = dict(kind='value', name=name, bend=name, cpp=name, raw='U32')
    if conversion:
        value['result_conversion'] = conversion
    return value


def restores_method(f):
    return f['return']['name'] == 'QFunctionPointer' and f['declaring_class'] in ('QLibrary', 'QGuiApplication', 'QOpenGLContext')


def adapt(g, f):
    import render_resources
    render = render_resources.adapt(g, f)
    if render:
        return render
    import native_platform
    platform = native_platform.adapt(g, f)
    if platform:
        return platform
    if restores_method(f) and 'NativeFunction' in g.ids:
        return handle('NativeFunction', 'native_function')
    if f['name'] == 'handle' and f['declaring_class'] in ('QSslKey', 'QSslCertificate'):
        name = 'NativeSslKey' if f['declaring_class'] == 'QSslKey' else 'NativeSslCertificate'
        if name in g.ids:
            return handle(name, 'native_ssl')
    return None


def is_key_constructor(f):
    return (f['declaring_class'] == 'QSslKey' and f['constructor'] and f['arguments']
            and f['arguments'][0]['type']['name'] == 'Qt::HANDLE')


def parameters(g, f):
    import render_resources
    render = render_resources.parameters(g, f)
    if render:
        return render
    if not is_key_constructor(f):
        return None
    args = [handle('NativeSslKey'), *(g.type(a['type']) for a in f['arguments'][1:])]
    return args, [dict(type=t, source=i, input=i, output=False, mutable=False) for i, t in enumerate(args)], []


def before_call(g, m):
    owner, method = m['function']['declaring_class'], m['function']['name']
    if owner == 'QLibrary' and method in ('unload', 'setFileName', 'setFileNameAndVersion'):
        return ['if (!native_function_owner_mutable(r, r->self)) return true;']
    if owner == 'QOpenGLContext' and method == 'getProcAddress':
        return ['if (QOpenGLContext::currentContext() != self) return fail(r, EXDEV, "OpenGL procedure lookup requires this context to be current");']
    return []


def method_case(g, m):
    import render_resources
    render = render_resources.method_case(g, m)
    if render:
        return render
    if not is_key_constructor(m['function']):
        return None
    key_type = 'static_cast<QSsl::KeyType>(r->arguments[1].word)' if len(m['args']) > 1 else 'QSsl::PrivateKey'
    return ['NativeCallScope call_scope;',
            f'auto *source = get<NativeSslKey>(r, r->arguments[0].word, {g.ids["NativeSslKey"]}, false, false);',
            'if (r->error) return true;',
            f'auto type = {key_type};',
            'if (type != source->value.type()) return fail(r, EINVAL, "Native key copy requires the original public/private KeyType");',
            '// The carrier owns a Qt shared key reference. Never adopt its borrowed native handle.',
            f'r->result.word = own(r, new QSslKey(source->value), {g.ids["QSslKey"]});',
            'r->result.owned_handle = r->result.word;', 'return true;']


def store(g, t, expression):
    import native_platform
    platform = native_platform.store(g, t, expression)
    if platform is not None:
        return platform
    conversion = t.get('result_conversion')
    if conversion == 'native_function':
        return [f'r->result.word = own_native_function(r, {expression});', 'r->result.owned_handle = r->result.word;']
    if conversion == 'native_ssl':
        source = 'QSslKey' if t['name'] == 'NativeSslKey' else 'QSslCertificate'
        return [f'auto *source = get<{source}>(r, r->self, {g.ids[source]}, false, false);',
                'if (r->error) return true;',
                f'r->result.word = own(r, new {t["name"]}{{*source}}, {g.ids[t["name"]]});',
                'r->result.owned_handle = r->result.word;']
    return None


def emit(g):
    import render_resources
    render_resources.emit(g)
    import native_platform
    native_platform.emit(g)
    wide = dict(kind='u64', bend='UInt64', cpp='quint64', raw='U32 & U32')
    g.types['UInt64'] = 'wide'
    boolean = dict(kind='bool', bend='Bool', raw='U32')
    for name in ('NativeFunction', 'NativeSslKey', 'NativeSslCertificate'):
        if name not in g.ids:
            continue
        for method, result in [('address', wide), ('isNull', boolean)]:
            op = g.next_id
            g.next_id += 1
            lines = ['NativeCallScope call_scope;',
                     f'auto *value = get<{name}>(r, r->arguments[0].word, {g.ids[name]}, false, false);',
                     'if (r->error) return true;']
            if name == 'NativeFunction':
                lines += ['if (!native_function_ready(r, *value)) return true;']
                pointer = 'value->value'
            else:
                pointer = 'value->value.handle()'
            lines += [f'r->result = wide_value(uint64_t(reinterpret_cast<uintptr_t>({pointer})));'
                      if method == 'address' else f'r->result.word = !{pointer};', 'return true;']
            g.cases.append(f'case {op}: {{\n' + '\n'.join('    ' + line for line in lines) + '\n}')
            g.emit_effect(name + '.' + method, [('value', handle(name))], result, op)


def cpp(g):
    import render_resources
    import native_platform
    if 'NativeFunction' not in g.ids:
        return render_resources.cpp(g) + native_platform.cpp(g)
    return render_resources.cpp(g) + native_platform.cpp(g) + (Path(__file__).with_name('templates').joinpath('native_interop.cpp').read_text()
            .replace('@FUNCTION_TYPE@', str(g.ids['NativeFunction']))
            .replace('@OBJECT_TYPE@', str(g.ids['QObject'])))
