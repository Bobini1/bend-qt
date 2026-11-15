"""Origin-checked opaque native platform capabilities.

unsafeAddress is deliberately a native interop escape, not an ownership lease.
Qt may remove a Wayland device asynchronously after the address is returned.
External native callers retain their platform lifetime and thread obligations.
"""
import re


def carrier(t):
    return 'NativePlatform_' + re.sub(r'[^A-Za-z0-9_]', '_', t['name'])


def handles(f):
    return (not f['arguments'] and f['return']['pointers'] == 1
            and (f['declaring_class'].startswith('QNativeInterface::')
                 or (f['declaring_class'], f['name']) == ('QSurface', 'surfaceHandle')))


def install(classes, selected):
    discovered = {}
    for name, cls in list(classes.items()):
        if name not in selected and not ((name.startswith('QNativeInterface::') or name == 'QSurface') and cls.get('generate')):
            continue
        for f in cls['functions']:
            if handles(f) and f['public']:
                discovered[carrier(f['return'])] = f['return']['cpp']
    for name, native in sorted(discovered.items()):
        classes[name] = dict(name=name, object=False, value=True, qobject=False, copyable=False,
            public_destructor=True, abstract=False, namespace=False, generate=False, template=False,
            bases=[], functions=[], enums=[], adapter=True, native_platform_pointer=native)
        selected.append(name)


def names(g):
    return [name for name in g.selected if g.classes[name].get('native_platform_pointer')]


def aliases(g, inside):
    if not names(g):
        return ''
    if not inside:
        return 'namespace bendqt { ' + ' '.join(f'struct {name};' for name in names(g)) + ' }\n'
    return ('struct NativePlatformIdentity { uintptr_t pointer; uint32_t owner; '
            'std::function<uintptr_t(BqtRequest *)> current; bool invalidated = false; };\n'
            + ''.join(f'struct {name} : NativePlatformIdentity {{}};\n' for name in names(g)))


def handle(name):
    return dict(kind='value', name=name, bend=name, cpp=name, raw='U32', pointer=False)


def adapt(g, f):
    if not handles(f) or carrier(f['return']) not in g.ids:
        return None
    return dict(handle(carrier(f['return'])), result_conversion='native_platform',
                native_platform_owner=f['declaring_class'], native_platform_method=f['name'])


def store(g, t, expression):
    if t.get('result_conversion') != 'native_platform':
        return None
    owner, method = t['native_platform_owner'], t['native_platform_method']
    return [f'r->result.word = own_platform_identity<{t["name"]}>(r, reinterpret_cast<uintptr_t>({expression}), r->self, {g.ids[t["name"]]},',
            '    [origin = r->self](BqtRequest *request) -> uintptr_t {',
            f'        auto *source = get<{owner}>(request, origin, {g.ids[owner]}, false, false);',
            f'        return source ? reinterpret_cast<uintptr_t>(source->{method}()) : 0;', '    });',
            'r->result.owned_handle = r->result.word;']


def emit(g):
    wide = dict(kind='u64', bend='UInt64', cpp='quint64', raw='U32 & U32')
    boolean = dict(kind='bool', bend='Bool', raw='U32')
    if not names(g):
        return
    g.types['UInt64'] = 'wide'
    for name in names(g):
        for method, result in [('isValid', boolean), ('isNull', boolean), ('unsafeAddress', wide), ('sameIdentity', boolean)]:
            operation = g.next_id; g.next_id += 1
            params = [('value', handle(name))]
            lines = ['NativeCallScope call_scope;',
                     f'auto *value = get<{name}>(r, r->arguments[0].word, {g.ids[name]}, false, false);',
                     'if (r->error) return true;']
            if method == 'sameIdentity':
                params.append(('other', handle(name)))
                lines += [f'auto *other = get<{name}>(r, r->arguments[1].word, {g.ids[name]}, false, false);',
                          'if (r->error) return true;',
                          'r->result.word = value->owner == other->owner && value->pointer == other->pointer;']
            elif method == 'isValid':
                lines += ['r->result.word = platform_identity_valid(*value);']
            else:
                lines += ['if (!platform_identity_valid(*value)) return fail(r, ESTALE, "Native platform capability no longer matches its Qt origin");']
                if method == 'unsafeAddress':
                    lines += ['// External callers must obey the native platform lifetime/thread contract.',
                              'r->result = wide_value(value->pointer);']
                else:
                    lines += ['r->result.word = !value->pointer;']
            lines += ['return true;']
            g.cases.append(f'case {operation}: {{\n' + '\n'.join('    ' + line for line in lines) + '\n}')
            g.emit_effect(name + '.' + method, params, result, operation)
    # The template's revision check is performed by Qt itself. On a different
    # platform (or an incompatible future interface revision), this returns null.
    if 'QGuiApplication' in g.ids:
        app = dict(kind='object', name='QGuiApplication', cpp='QGuiApplication *', bend='QGuiApplication', raw='U32')
        for interface in g.selected:
            if not interface.startswith('QNativeInterface::') or not g.classes[interface].get('native_object'):
                continue
            operation = g.next_id; g.next_id += 1
            result = dict(kind='object', name=interface, cpp=interface + ' *', bend=interface.replace('::', '.'), raw='U32')
            lines = ['NativeCallScope call_scope;',
                     f'auto *value = get<QGuiApplication>(r, r->arguments[0].word, {g.ids["QGuiApplication"]}, false, false);',
                     'if (r->error) return true;',
                     f'auto *native = platform_application_interface<{interface}>(value);',
                     f'r->result.word = register_native_borrow(r, native, {g.ids[interface]}, r->arguments[0].word);',
                     'return true;']
            g.cases.append(f'case {operation}: {{\n' + '\n'.join('    ' + line for line in lines) + '\n}')
            g.emit_effect('QGuiApplication.nativeInterface_' + interface.replace('::', '_'), [('application', app)], result, operation)


def cpp(g):
    if not names(g):
        return ''
    return '''
static constexpr uint32_t native_platform_slot = 0xffffffe2u;
static bool platform_identity_valid(NativePlatformIdentity &value)
{
    if (value.invalidated || !entry(value.owner)) { value.invalidated = true; return false; }
    BqtRequest request{};
    const auto current = value.current(&request);
    if (request.error || current != value.pointer) value.invalidated = true;
    return !value.invalidated;
}
template<class T> static uint32_t own_platform_identity(BqtRequest *r, uintptr_t pointer,
    uint32_t owner, uint16_t type, std::function<uintptr_t(BqtRequest *)> current)
{
    if (!entry(owner)) { fail(r, ESTALE, "Native platform capability has no Qt origin"); return 0; }
    const auto id = own(r, new T{{pointer, owner, std::move(current)}}, type);
    if (!id) return 0;
    BqtRequest relationship{}; relationship.self = id;
    const auto index = prepare_retention(&relationship, native_platform_slot, 0, owner);
    if (relationship.error) {
        auto *value = static_cast<T *>(entry(id)->value);
        invalidate(id); delete value;
        fail(r, relationship.error, relationship.message); return 0;
    }
    commit_retention(index, id, native_platform_slot, 0, owner, nullptr);
    return id;
}
template<class T> static T *platform_application_interface(QGuiApplication *application)
{
    if constexpr (QNativeInterface::Private::TypeInfo<T>::template isCompatibleWith<QGuiApplication>)
        return application->nativeInterface<T>();
    else return nullptr;
}
'''
