"""Access to the protected data members exposed by the pinned PySide model.

Addressable fields use legal derived member pointers on the real base object.
Bitfield references use a mask calibrated on a genuine probe object, then read
and write the base object's unsigned-char representation without a downcast.
"""
import re
from pathlib import Path

import protected_members

HERE = Path(__file__).resolve().parent


def permitted(g, field, owner=None):
    owner = field.get('declaring_class') or owner
    return bool(field.get('protected') and not field.get('private') and not field.get('removed')
                and (field.get('getter') or field.get('setter'))
                and owner and protected_members.can_derive(g, owner))


def helper(owner):
    return 'BqtProtectedFields_' + re.sub(r'[^A-Za-z0-9_]', '_', owner)


def expression(g, field, receiver='self'):
    source = field.get('source', field)
    owner = field.get('declaring_class') or source.get('declaring_class')
    if not permitted(g, source, owner):
        return None
    field_name = field.get('field', source['name'])
    function = helper(owner) + '::access_' + field_name
    return function + ('()' if source.get('static') else '(' + receiver + ')')


def native_pointer(g, owner, source):
    if source.get('pointers') != 1 or source.get('array') or source.get('name') not in g.ids:
        return False
    cls = g.classes.get(source['name'], {})
    if cls.get('qobject') or not cls.get('native_object'):
        return False
    import rhi_lifetimes
    return not rhi_lifetimes.resource(g, source['name'])


def setter_uses_owner_view(g, field):
    source = field['source']
    return bool(field['setter'] and permitted(g, source, field['declaring_class'])
                and source['type'].get('pointers') == 1
                and source['type'].get('name') in g.ids)


def field_type(g, owner, field, setter):
    if not permitted(g, field, owner):
        return None
    source = field['type']
    if native_pointer(g, owner, source):
        return g.conversions.register(dict(g.type(source, result=False), protected_field_view=True, nullable=True))
    cls = g.classes.get(source.get('name'), {})
    if not source.get('pointers') and not source.get('reference') and cls.get('native_object') and not cls.get('native_copyable', cls.get('copyable')):
        if setter and not cls.get('native_copy_assignable'):
            raise ValueError('Native member has no copy assignment; its mutable member view exposes in-place operations')
        borrowed = dict(source, reference=1, cpp=source['name'] + ' &')
        return g.conversions.register(dict(g.type(borrowed, result=False), protected_member_view=True))
    return None


def field_access(g, field, target, argument=None):
    source = field['source']
    if not permitted(g, source, field['declaring_class']) or field['setter']:
        return None
    member = field['type'].get('protected_member_view')
    if not member and not native_pointer(g, field['class'], source['type']):
        return None
    owner = field['declaring_class']
    name = field['field']
    receiver = helper(owner) + '::access_' + name + '(value)'
    pointer = '&(' + target + ')' if member else target
    current = '&(' + receiver + ')' if member else receiver
    readonly = 'entry(r->self)->read_only' if member else str(bool(source['type'].get('const'))).lower()
    return [
        f'auto current_field = +[](BqtRequest *request, uint32_t id) -> const void * {{',
        f'    auto *value = protected_fields_owner<{owner}>(request, id, {g.ids[owner]});',
        '    if (!value) return nullptr;',
        f'    return {current};', '};',
        f'r->result.word = protected_fields_borrow(r, {pointer}, {g.ids[field["type"]["name"]]}, r->self, current_field, {readonly});',
        'r->result.borrowed_handle = r->result.word;']


def declarations(g, include_views=True):
    groups = {}
    for name in g.selected:
        for field in g.classes[name].get('fields', []):
            if permitted(g, field, name):
                owner = field.get('declaring_class') or name
                groups.setdefault(owner, {})[field['name']] = field
    if not groups:
        g.protected_field_inventory = dict(owners=0, fields=0)
        return (HERE / 'templates/protected_field_views.cpp').read_text() if include_views else ''
    lines = [(HERE / 'templates/protected_fields.cpp').read_text()]
    for owner, fields in sorted(groups.items()):
        access = helper(owner)
        lines += [f'struct {access} : {owner} {{']
        # This makes a genuinely constructed probe concrete when a protected
        # bitfield belongs to an abstract class. No probe is made for ordinary
        # fields, including classes whose default construction is unavailable.
        seen = set()
        for function in g.inherited(owner):
            if not function.get('abstract') or function.get('destructor'):
                continue
            key = function['minimal_signature']
            if key in seen:
                continue
            seen.add(key)
            arguments = ', '.join(a['type']['cpp'] + f' argument{i}' for i, a in enumerate(function['arguments']))
            qualifiers = (' const' if function.get('const') else '') + (' noexcept' if function.get('noexcept') else '')
            lines += [f'    {function["return"]["cpp"]} {function["name"]}({arguments}){qualifiers} override {{',
                      '        throw std::logic_error("A native bitfield probe invoked a pure virtual method");', '    }']
        for name, field in sorted(fields.items()):
            if field.get('static'):
                lines += [f'    static decltype(auto) access_{name}() {{ return ({access}::{name}); }}']
                continue
            lines += [f'    template<class A, class = void> struct Addressable_{name} : std::false_type {{}};',
                      f'    template<class A> struct Addressable_{name}<A, std::void_t<decltype(&A::{name})>> : std::true_type {{}};',
                      f'    template<class A = {access}> static decltype(auto) access_{name}({owner} *object) {{',
                      f'        if constexpr (Addressable_{name}<A>::value) return (object->*(&A::{name}));',
                      f'        else return ProtectedFieldBits::Reference<decltype(std::declval<A &>().{name})>{{object, mask_{name}<A>()}};',
                      '    }',
                      f'    template<class A> static const ProtectedFieldBits::Mask &mask_{name}() {{',
                      '        static const auto result = [] {',
                      '            if constexpr (!std::is_default_constructible_v<A>) {',
                      '                throw std::logic_error("A native bitfield has no usable probe constructor");',
                      '                return ProtectedFieldBits::Mask{};',
                      '            } else {',
                      '                A probe;',
                      f'                using Value = decltype(probe.{name});',
                      f'                const Value original = probe.{name};',
                      f'                auto *base = static_cast<{owner} *>(&probe);',
                      f'                std::array<unsigned char, sizeof({owner})> zero{{}}, ones{{}}, check{{}};',
                      f'                probe.{name} = static_cast<Value>(0);',
                      '                std::memcpy(zero.data(), static_cast<const void *>(base), zero.size());',
                      '                Value allValues = static_cast<Value>(~uint64_t(0));',
                      f'                probe.{name} = allValues;',
                      '                std::memcpy(ones.data(), static_cast<const void *>(base), ones.size());',
                      f'                const auto maximum = static_cast<uint64_t>(probe.{name});',
                      f'                probe.{name} = original;',
                      '                auto mask = ProtectedFieldBits::calibrate(zero, ones);',
                      '                bool valid = mask.width <= sizeof(Value) * CHAR_BIT',
                      '                    && maximum == mask.template decodedMaximum<Value>();',
                      '                for (unsigned bit = 0; valid && bit < mask.width; ++bit) {',
                      '                    const uint64_t value = uint64_t(1) << bit;',
                      f'                    probe.{name} = static_cast<Value>(value);',
                      '                    std::memcpy(check.data(), static_cast<const void *>(base), check.size());',
                      '                    valid = mask.matches(zero.data(), check.data(), check.size(), value);',
                      '                }',
                      f'                probe.{name} = original;',
                      '                if (!valid) throw std::logic_error("The native bitfield layout failed calibration");',
                      '                return mask;',
                      '            }',
                      '        }();',
                      '        return result;', '    }']
        lines += ['};']
    g.protected_field_inventory = dict(owners=len(groups), fields=sum(len(fields) for fields in groups.values()),
        access='Legal member pointers for ordinary fields; verified unsigned-char bit masks calibrated on genuine derived probes for bitfields')
    return '\n'.join(lines) + '\n' + ((HERE / 'templates/protected_field_views.cpp').read_text() if include_views else '')
