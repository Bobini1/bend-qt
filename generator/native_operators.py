"""Normalize free/friend operators that Shiboken presents as class methods.

The source signature still contains both operands; the extracted argument list
omits its receiver. Retain that distinction instead of treating it as a lost
native parameter. Reverse operators and rvalue receiver overloads remain distinct.
"""
import re


def restores_method(function):
    # PySide replaces native arithmetic/stream overloads with Python protocol
    # methods (notably readInt32/writeInt32). Bend keeps the original typed
    # operator. Ordinary type, lifetime, source-signature and bounds validation
    # still apply; this does not restore a Python-only injected function.
    return function['operator'] and not function['user_added']


def conversion_name(function):
    if function['operator'] and function['name'].startswith('operator '):
        target = function['name'][len('operator '):]
        return 'op_to_' + re.sub(r'[^a-zA-Z0-9_]', '_', target)
    return None


def parameters(signature, name):
    position = signature.find(name)
    start = signature.find('(', position + len(name)) if position >= 0 else -1
    if start < 0:
        return None
    depth, begin, values = 0, start + 1, []
    for i in range(begin, len(signature)):
        char = signature[i]
        if char == ')' and depth == 0:
            tail = signature[begin:i].strip()
            if tail and tail != 'void':
                values.append(tail)
            return values
        if char == ',' and depth == 0:
            values.append(signature[begin:i].strip())
            begin = i + 1
        elif char in '<([':
            depth += 1
        elif char in '>)]':
            depth -= 1
    return None


def sources(function):
    if not function['operator'] or function['static']:
        return []
    count = len(function['arguments']) + 1
    return [(source, params) for source in function.get('source_signatures', [])
            for params in [parameters(source, function['name'])]
            if params is not None and len(params) == count]


def identity(function):
    free = function.get('free_operator')
    if free:
        return 'free:' + free['signature']
    found = sources(function)
    if found:
        # Original qualifiers are more precise than Shiboken's normalized
        # alternate signature; preserve rvalue/const overloads in this key.
        source, _ = max(found, key=lambda item: item[0].count('&') + item[0].count('const'))
        return 'free:' + source
    return function['minimal_signature']


def base_type(cpp, aliases):
    text = cpp.strip()
    text = re.sub(r'^(?:(?:const|volatile)\s+)+', '', text)
    text = re.sub(r'\s*&&?\s*$', '', text)
    # These primitive/container aliases have no class typedef entry in the
    # ApiExtractor JSON, but are already normalized by the Bend converters.
    aliases = dict({'QLatin1String': 'QLatin1StringView', 'QStringList': 'QList<QString>',
                    'QVariantList': 'QList<QVariant>', 'QVariantMap': 'QMap<QString,QVariant>',
                    'QVariantHash': 'QHash<QString,QVariant>'}, **aliases)
    visited = set()
    while text in aliases and text not in visited:
        visited.add(text)
        text = aliases[text]
    return re.sub(r'\s+', '', text)


def normalize(g, function):
    found = sources(function)
    if not found:
        return function
    owner = function['declaring_class']
    aliases = g.api.get('typedefs', {})
    receiver = base_type(owner, aliases)
    arguments = [a['type']['cpp'] for a in function['arguments']]
    candidates = []
    for source, params in found:
        for index, parameter in enumerate(params):
            if base_type(parameter, aliases).removesuffix('*') != receiver:
                continue
            others = params[:index] + params[index + 1:]
            if any(base_type(a, aliases) != base_type(b, aliases) for a, b in zip(others, arguments)):
                continue
            exact = sum(re.sub(r'\s+', '', a) == re.sub(r'\s+', '', b) for a, b in zip(others, arguments))
            detailed = source.count('&') + source.count('const')
            candidates.append((exact, detailed, -index, source, params, index))
    if not candidates:
        return dict(function, free_operator_error='Free operator receiver cannot be aligned with its original native signature')
    _, _, _, source, params, index = max(candidates, key=lambda item: item[:3])
    receiver_cpp = params[index]
    pointer = receiver_cpp.rstrip().endswith('*')
    copied = not pointer and ('&&' in receiver_cpp or '&' not in receiver_cpp)
    if copied and not g.classes[owner].get('copyable'):
        return dict(function, free_operator_error='Free operator receiver requires an explicit noncopyable transfer')
    read_only = copied or bool(re.match(r'^\s*const\b', receiver_cpp))
    return dict(function, const=read_only, free_operator={
        'signature': source, 'self_index': index, 'self_cpp': receiver_cpp,
        'self_copy': copied, 'self_pointer': pointer, 'reverse': index != 0, 'parameters': params})


def expression(function, arguments):
    free = function['free_operator']
    owner = function['declaring_class']
    if free.get('self_pointer'):
        receiver = f'static_cast<{"const " if function["const"] else ""}{owner} *>(self)'
    elif free['self_copy']:
        receiver = f'{owner}(*self)'
    else:
        receiver = f'static_cast<{"const " if function["const"] else ""}{owner} &>(*self)'
    values = []
    for argument, metadata in zip(arguments, function['arguments']):
        # The extractor's qualified type spelling is authoritative. This also
        # preserves mutable output references and explicit rvalue argument copies.
        values.append(f'static_cast<{metadata["type"]["cpp"]}>({argument})')
    values.insert(free['self_index'], receiver)
    if owner == 'Qt3DRender::QGraphicsApiFilter' and function['name'] in ('operator==', 'operator!='):
        # Qt 6.12 declares these with Q_AUTOTEST_EXPORT, so release libraries
        # do not export them. Their actual operation is directional capability
        # matching, not structural equality. Preserve the source contract using
        # exported public getters, including version/profile asymmetry.
        # https://github.com/qt/qt3d/blob/v6.12.0/src/render/materialsystem/qgraphicsapifilter.cpp
        body = '''[](const Qt3DRender::QGraphicsApiFilter &available, const Qt3DRender::QGraphicsApiFilter &required) {
            if (available.api() != required.api()) return false;
            if (available.majorVersion() < required.majorVersion()
                    || (available.majorVersion() == required.majorVersion() && available.minorVersion() < required.minorVersion())) return false;
            if (required.api() == Qt3DRender::QGraphicsApiFilter::OpenGL
                    && available.profile() == Qt3DRender::QGraphicsApiFilter::CoreProfile
                    && required.profile() != available.profile()) return false;
            const auto extensions = available.extensions();
            for (const auto &extension : required.extensions())
                if (!extensions.contains(extension)) return false;
            return required.vendor().isEmpty() || required.vendor() == available.vendor();
        }'''
        match = '(' + body + ')(' + ', '.join(values) + ')'
        return '!' + match if function['name'] == 'operator!=' else match
    # The unqualified function call enables ADL for Qt's hidden friend operators.
    return function['name'] + '(' + ', '.join(values) + ')'
