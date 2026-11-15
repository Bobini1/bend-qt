"""Legal access to the protected API exposed by Shiboken wrappers.

Member pointers are obtained inside a derived access class and applied to the
real base object. No object is cast to that access class. Protected enum aliases
change only C++ spelling; metadata and the Bend API retain their native names.
"""
import hashlib
import re


def access_name(owner):
    return 'BqtProtected_' + re.sub(r'[^A-Za-z0-9_]', '_', owner)


def can_derive(g, owner):
    cls = g.classes.get(owner, {})
    return (owner in g.ids and not cls.get('final_cpp')
            and (cls.get('derived_destructible') or cls.get('public_destructor'))
            and not any(f.get('destructor') and f.get('final_cpp') for f in cls.get('functions', [])))


def permitted(g, f):
    return bool(f.get('protected') and not f.get('private')
                and can_derive(g, f['declaring_class']))


def callable_contract(g, receiver, current):
    if not current.get('private') or not current.get('virtual'):
        return current
    import native_operators
    identity = native_operators.identity(current)
    pending, seen = list(g.classes[receiver]['bases']), set()
    while pending:
        owner = pending.pop(0)
        if owner in seen or owner not in g.classes:
            continue
        seen.add(owner)
        for base in g.inherited(owner):
            if (native_operators.identity(base) == identity and not base.get('private')
                    and (base.get('public') or permitted(g, base))):
                # Only the ordinary call uses the accessible base contract.
                # Proxy generation must retain the actual private/final
                # override and must not invent a callable pure-base fallback.
                return dict(base, private_override_contract=dict(owner=current['declaring_class'],
                                                                 signature=current['minimal_signature']))
        pending.extend(g.classes[owner]['bases'])
    return current


def enum_accessible(g, name):
    enum = g.enums.get(name, {})
    return bool(enum.get('protected') and not enum.get('private')
                and can_derive(g, name.rpartition('::')[0]))


def pointer_name(f):
    identity = f['declaring_class'] + '::' + f['minimal_signature']
    return 'member_' + hashlib.sha256(identity.encode()).hexdigest()[:16]


def member(g, f):
    if f.get('protected') and permitted(g, f):
        if not hasattr(g, 'protected_accessor_methods'):
            g.protected_accessor_methods = {}
        g.protected_accessor_methods[pointer_name(f)] = dict(function=f)
        return access_name(f['declaring_class']) + '::' + pointer_name(f) + '()'
    return None


def expression(g, f, arguments, receiver='self'):
    pointer = member(g, f)
    if not pointer:
        return None
    call = pointer if f['static'] else '(' + receiver + '->*' + pointer + ')'
    return call + '(' + ', '.join([*arguments, *native_defaults(f)]) + ')'


def native_defaults(f):
    # Function pointers have no default arguments. ApiExtractor omits Qt's
    # disambiguation marker from the target signature, while retaining it in
    # the original native declaration.
    from native_operators import parameters
    for source in f.get('source_signatures', []):
        args = parameters(source, f['name'])
        if (args and len(args) == len(f['arguments']) + 1
                and args[-1].replace(' ', '') == 'Qt::Disambiguated_t'):
            return ['Qt::Disambiguated']
    return []


def declarations(g):
    owners = {}
    for name, enum in sorted(g.enums.items()):
        if enum_accessible(g, name):
            owner, _, local = name.rpartition('::')
            owners.setdefault(owner, dict(enums={}, methods={} ))['enums'][local] = enum
    for method in [*getattr(g, 'protected_accessor_methods', {}).values(), *g.methods]:
        f = method['function']
        if not f.get('constructor') and permitted(g, f):
            owners.setdefault(f['declaring_class'], dict(enums={}, methods={} ))['methods'][pointer_name(f)] = method
    lines = ['template<int N> struct ProtectedMemberPriority : ProtectedMemberPriority<N - 1> {};',
             'template<> struct ProtectedMemberPriority<0> {};']
    replacements = {}
    for owner, members in sorted(owners.items()):
        helper = access_name(owner)
        lines.append(f'struct {helper} : {owner} {{')
        if any(m['function']['name'] == 'operator=' for m in members['methods'].values()):
            # The helper's implicit assignment operators hide the base ones.
            lines.append(f'    using {owner}::operator=;')
        for local, enum in sorted(members['enums'].items()):
            lines.append(f'    using {owner}::{local};')
            replacements[owner + '::' + local] = helper + '::' + local
            flags = enum.get('flags')
            if flags and flags.startswith(owner + '::'):
                flag_name = flags.rpartition('::')[2]
                lines.append(f'    using {owner}::{flag_name};')
                replacements[flags] = helper + '::' + flag_name
        for name, method in sorted(members['methods'].items()):
            f = method['function']
            if method.get('signal', {}).get('private_marker'):
                lines += [f'    static constexpr auto {name}() {{',
                          f'        return &{helper}::{f["name"]};', '    }']
            else:
                types = [a['type']['cpp'] for a in f['arguments']]
                if native_defaults(f):
                    types.append('Qt::Disambiguated_t')
                args = ', '.join(types)
                pointer = '(*)' if f['static'] else f'({owner}::*)'
                qualifier = ' const' if f['const'] and not f['static'] else ''
                candidates = [(1, f['return']['cpp'], qualifier)] if f['static'] else [
                    (1, f['return']['cpp'], qualifier), (0, f['return']['cpp'], qualifier + ' &')]
                if not f['static'] and not f['const'] and not f['return']['reference']:
                    # Older ApiExtractor versions expose an && getter as an
                    # ordinary non-const value getter. Calling it on Bend's
                    # lvalue must select its const-reference sibling, just as
                    # a direct C++ call does, without moving from the object.
                    sibling = next((other for other in g.classes[owner]['functions']
                        if other['name'] == f['name'] and other['const']
                        and other['return']['reference'] == 1 and other['return']['const']
                        and other['return']['cpp'] == 'const ' + f['return']['cpp'] + ' &'
                        and [a['type']['cpp'] for a in other['arguments']] == types), None)
                    if sibling:
                        candidates = [(3, f['return']['cpp'], qualifier),
                                      (2, f['return']['cpp'], qualifier + ' &'),
                                      (1, sibling['return']['cpp'], ' const'),
                                      (0, sibling['return']['cpp'], ' const &')]
                for priority, result, qualifiers in candidates:
                    member_type = f'{result} {pointer}({args}){qualifiers}'
                    lines += [f'    template<class D = {helper}>',
                              f'    static constexpr auto {name}(ProtectedMemberPriority<{priority}>)',
                              f'        -> decltype(static_cast<{member_type}>(&D::{f["name"]})) {{',
                              f'        return static_cast<{member_type}>(&D::{f["name"]});', '    }']
                lines += [f'    static constexpr auto {name}() {{',
                          f'        return {name}<>(ProtectedMemberPriority<{candidates[0][0]}>{{}});', '    }']
        lines.append('};')
    g.protected_cpp_replacements = replacements
    g.protected_member_inventory = dict(
        method_entries=sum(bool(m['function'].get('protected')) for m in g.methods),
        native_methods=sum(len(value['methods']) for value in owners.values()),
        constructor_entries=sum(bool(m['function'].get('constructor') and m['function'].get('protected')) for m in g.methods),
        enum_types=sorted(name for name in g.enums if enum_accessible(g, name)),
        access='Derived member-pointer access applied to the actual base object; protected construction uses an exact derived deleter')
    return '\n'.join(lines) + '\n'


# Keep metadata type names, arbitrary user strings, comments and raw strings
# untouched. Alias substitutions apply only to actual C++ identifier tokens.
_quoted = re.compile(r'//[^\n]*|/\*[\s\S]*?\*/|R"(?P<delimiter>[^ ()\\\t\r\n]{0,16})\([\s\S]*?\)(?P=delimiter)"|"(?:\\.|[^"\\\n])*"|(?<![A-Za-z0-9_])(?:u8|[uUL])?\'(?:\\.|[^\'\\\n])+\'')


def rewrite_cpp(g, source):
    replacements = getattr(g, 'protected_cpp_replacements', {})
    if not replacements:
        return source
    symbols = re.compile(r'(?<![A-Za-z0-9_])(?:' + '|'.join(
        re.escape(name) for name in sorted(replacements, key=len, reverse=True)) + r')(?![A-Za-z0-9_])')
    def replace(part):
        return symbols.sub(lambda match: replacements[match[0]], part)
    output, previous = [], 0
    for match in _quoted.finditer(source):
        output.extend((replace(source[previous:match.start()]), match[0]))
        previous = match.end()
    output.append(replace(source[previous:]))
    return ''.join(output)
