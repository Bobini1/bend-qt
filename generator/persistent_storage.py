"""Owned backing for Qt APIs retaining strings, translation bytes and RCC data."""
from pathlib import Path


def kind(f):
    owner, name = f['declaring_class'], f['name']
    args = f['arguments']
    if owner in ('QMessageLogContext', 'QMessageLogger') and f['constructor']:
        return 'message_context'
    if owner == 'QLoggingCategory' and f['constructor'] and args and args[0]['type']['name'] == 'char':
        return 'logging'
    if owner == 'QLoggingCategory' and name == 'defaultCategory':
        return 'logging_default'
    if args and args[0]['type']['pointers'] == 1 and args[0]['type']['name'] in ('uchar', 'unsigned char'):
        if owner == 'QResource' and name in ('registerResource', 'unregisterResource'):
            return 'resource'
        if owner == 'QTranslator' and name == 'load':
            return 'translation'
    return None


def parameters(g, f):
    adapted = kind(f)
    if not adapted or adapted == 'logging_default':
        return None
    if adapted == 'message_context':
        args = [dict(kind='string', bend='String', raw='String', cpp='QString')
                if a['type']['name'] == 'char' and a['type']['pointers'] else g.type(a['type']) for a in f['arguments']]
        return args, [dict(type=t, source=i, input=i, output=False, mutable=False) for i, t in enumerate(args)], []
    args = [dict(kind='string', bend='String', raw='String', cpp='QString') if adapted == 'logging' else
            dict(kind='value', name='QByteArray', bend='QByteArray', raw='U32', cpp='QByteArray')]
    args += [g.type(a['type']) for a in f['arguments'][1:]]
    return args, [dict(type=t, source=i, input=i, output=False, mutable=False) for i, t in enumerate(args)], []


def method_case(g, m):
    f = m['function']
    adapted = kind(f)
    if not adapted:
        return None
    lines = ['NativeCallScope call_scope;']
    if adapted == 'message_context':
        owner = f['declaring_class']
        strings = [i for i, t in enumerate(m['args']) if t['kind'] == 'string']
        lines += [f'if (std::memchr(r->arguments[{i}].text, 0, r->arguments[{i}].size)) return fail(r, EINVAL, "Logging context contains an embedded NUL");' for i in strings]
        arguments = [f'QByteArray(r->arguments[{i}].text, qsizetype(r->arguments[{i}].size))' if t['kind'] == 'string' else g.argument(t, i)[1] for i, t in enumerate(m['args'])]
        if len(arguments) == 3:
            arguments.append('QByteArray("default")')
        holder = 'StableMessageLogContext' if owner == 'QMessageLogContext' else 'StableMessageLogger'
        return lines + [f'auto value = std::make_unique<{holder}>(' + ', '.join(arguments) + ');',
            f'r->result.word = insert(r, value.release(), nullptr, {g.ids[owner]}, destroy_message_context<{holder}>, true, cast_message_context<{holder}, {g.ids[owner]}>);',
            'r->result.owned_handle = r->result.word;', 'return true;']
    if adapted == 'logging_default':
        return lines + [f'auto *category = QLoggingCategory::defaultCategory();',
            f'r->result.word = insert(r, category, nullptr, {g.ids["QLoggingCategory"]}, nullptr, false, NativeTraits<QLoggingCategory>::cast);', 'return true;']
    if adapted == 'logging':
        level = g.argument(m['args'][1], 1)[1] if len(m['args']) > 1 else 'QtDebugMsg'
        return lines + ['if (std::memchr(r->arguments[0].text, 0, r->arguments[0].size)) return fail(r, EINVAL, "Logging category contains an embedded NUL");',
            f'auto category = std::make_unique<StableLoggingCategory>(QByteArray(r->arguments[0].text, qsizetype(r->arguments[0].size)), {level});',
            f'r->result.word = insert(r, category.release(), nullptr, {g.ids["QLoggingCategory"]}, destroy_logging_category, true, cast_logging_category);',
            'r->result.owned_handle = r->result.word;', 'return true;']
    lines += [f'auto *source = get<QByteArray>(r, r->arguments[0].word, {g.ids["QByteArray"]}, false, false);',
              'if (r->error) return true;']
    if adapted == 'resource':
        root = g.argument(m['args'][1], 1)[1] if len(m['args']) > 1 else 'QString()'
        operation = 'register_resource_snapshot' if f['name'] == 'registerResource' else 'unregister_resource_snapshot'
        return lines + [f'r->result.word = {operation}(r, r->arguments[0].word, *source, {root});', 'return true;']
    directory = g.argument(m['args'][2], 2)[1] if len(m['args']) > 2 else 'QString()'
    return lines + [f'auto *self = get<QTranslator>(r, r->self, {g.ids["QTranslator"]});',
        'if (r->error) return true;', 'auto count = int32_t(r->arguments[1].word);',
        'if (count < 0 || count > source->size()) return fail(r, ERANGE, "Translation snapshot exceeds the source extent");',
        f'r->result.word = load_translation_snapshot(r, self, *source, count, {directory});', 'return true;']


def cpp(g):
    source = (Path(__file__).parent / 'templates/persistent_storage.cpp').read_text()
    return source.replace('@LOGGING_TYPE@', str(g.ids['QLoggingCategory']))


def field_type(g, name, field, setter):
    if name != 'QMessageLogContext' or field['name'] not in ('file', 'function', 'category'):
        return None
    string = dict(name='QString', cpp='QString', const=False, pointers=0, reference=0,
                  container=False, enum=False, flags=False, instantiations=[])
    converted = g.conversions.container(dict(string, name='std::optional',
        cpp='std::optional<QString>', instantiations=[string]), not setter)
    return dict(converted, logging_field=True)


def field_access(g, field, expression, argument=None):
    if not field['type'].get('logging_field'):
        return None
    if field['setter']:
        return [f'if (!set_message_context_field(r, {expression}, &StableMessageLogContext::{field["field"]}, {argument})) return true;']
    return g.store_result(field['type'], f'({expression} ? std::optional<QString>(QString::fromUtf8({expression})) : std::nullopt)')
