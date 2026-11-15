"""Outline nine explicit runtime dispatch hubs, retaining their typed callees."""
import re


HUBS = {
    'native_owned_variant_snapshot': ('signal_dispatch', 0, ''),
    'meta_type': ('signal_dispatch', 1, 'BendSignalApi'),
    'read_value': ('signal_dispatch', 2, 'BendSignalApi'),
    'write_value': ('signal_dispatch', 3, 'BendSignalApi'),
    'can_assign': ('signal_dispatch', 4, 'BendSignalApi'),
    'assign_value': ('signal_dispatch', 5, 'BendSignalApi'),
    'argument_type': ('signal_dispatch', 6, 'BendSignalApi'),
    'binding_storage': ('qt_object_dispatch', 0, 'RuntimeQtObjects'),
    'bound_native_name': ('qt_object_dispatch', 1, 'RuntimeQtObjects'),
}


def cpp(source, *, hubs=None):
    """Render annotated definitions; this does not discover or rewrite C++ ASTs."""
    hubs = HUBS if hubs is None else hubs
    pattern = re.compile(r'^// BQT_RUNTIME_BODY_BEGIN ([a-z_]+)\n(.*?)'
                         r'^// BQT_RUNTIME_BODY_END \1\n', re.M | re.S)
    seen = set()
    def outline(match):
        name, original = match[1], match[2]
        if name not in hubs or name in seen:
            raise ValueError('Unknown or repeated runtime dispatch hub: ' + name)
        seen.add(name)
        signature, opening, body = original.partition('{\n')
        # These nine explicit signatures have ordinary return types, no default
        # arguments and no constexpr semantics. Reject an accidental expansion.
        if (not opening or not signature.startswith('static ') or '=' in signature
                or re.search(r'\b(?:auto|constexpr|consteval)\b', signature)
                or signature.count(name + '(') != 1 or not body.endswith('}\n')):
            raise ValueError('Runtime hub needs an explicit ordinary signature: ' + name)
        family, identifier, scope = hubs[name]
        declaration = signature.replace('static ', 'extern __attribute__((visibility("hidden"))) ', 1).rstrip() + ';\n'
        qualified = (scope + '::' if scope else '') + name
        definition = signature.removeprefix('static ').replace(
            name + '(', '__attribute__((noinline, visibility("hidden"))) ' + qualified + '(', 1)
        implementation = (f'// BQT_AUXILIARY_BEGIN {family} {identifier}\n' + definition + '{\n' + body
                          + f'// BQT_AUXILIARY_END {family} {identifier}\n')
        return declaration + ('}\n' if scope else '') + implementation + ('namespace ' + scope + ' {\n' if scope else '')
    result = pattern.sub(outline, source)
    if 'BQT_RUNTIME_BODY_' in result:
        raise ValueError('Malformed explicit runtime dispatch boundary')
    return result
