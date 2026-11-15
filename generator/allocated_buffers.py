"""Qt-allocated byte outputs with exact native lengths and exception-safe cleanup."""


def handles(f):
    if f['declaring_class'] == 'QScxmlTableData' and f['name'] == 'dataNames':
        return True
    if f['declaring_class'] in ('QStringDecoder', 'QStringEncoder') and f['name'] == 'appendToBuffer':
        return len(f['arguments']) == 2 and f['arguments'][0]['type']['pointers'] == 1
    if is_text_word(f):
        return True
    if f['declaring_class'] != 'QDataStream' or f['name'] not in ('readBytes', 'operator>>'):
        return False
    arguments = f['arguments']
    return bool(arguments and arguments[0]['type']['name'] == 'char'
                and arguments[0]['type']['pointers'] == 1 and arguments[0]['type']['reference'] == 1
                and (len(arguments) == 1 or arguments[1]['type']['name'] in ('qint64', 'uint')))


def is_text_word(f):
    return (f['declaring_class'] == 'QTextStream' and f['name'] == 'operator>>'
            and len(f['arguments']) == 1 and f['arguments'][0]['type']['name'] == 'char'
            and f['arguments'][0]['type']['pointers'] == 1 and not f['arguments'][0]['type']['reference'])


def adapt(g, f):
    if handles(f) and f['declaring_class'] == 'QScxmlTableData':
        scalar = dict(name='qint32', cpp='qint32', const=False, pointers=0, reference=0,
                      container=False, enum=False, flags=False, instantiations=[])
        return g.type(dict(scalar, name='QList', cpp='QList<qint32>', container=True, instantiations=[scalar]), result=True)
    if handles(f) and f['declaring_class'] in ('QStringDecoder', 'QStringEncoder'):
        if f['declaring_class'] == 'QStringDecoder':
            return dict(kind='string', cpp='QString', bend='String', raw='String')
        return dict(kind='value', name='QByteArray', cpp='QByteArray', bend='QByteArray', raw='U32')
    return None


def parameters(g, f):
    if not handles(f):
        return None
    if f['declaring_class'] == 'QScxmlTableData':
        return [], [], []
    if f['declaring_class'] in ('QStringDecoder', 'QStringEncoder'):
        item = g.type(f['arguments'][1]['type'])
        return [item], [dict(type=item, source=1, input=0, output=False, mutable=False)], []
    # The native length reference is output-only. The owned byte array keeps the
    # entire serialized extent, including embedded NULs and an explicitly stored
    # string terminator. It never includes readBytes' additional sentinel byte.
    byte_array = dict(kind='value', name='QByteArray', cpp='QByteArray', bend='QByteArray', raw='U32')
    output = [dict(type=g.conversions.register(byte_array), source=0, input=None, output=True, mutable=False)]
    if len(f['arguments']) == 2:
        native = dict(f['arguments'][1]['type'], reference=0,
                      cpp=f['arguments'][1]['type']['cpp'].replace('&', '').strip())
        output.append(dict(type=g.conversions.register(g.type(native)), source=1, input=None, output=True, mutable=False))
    return [], output, output


def method_case(g, m):
    f = m['function']
    if not handles(f):
        return None
    if f['declaring_class'] == 'QScxmlTableData':
        lines = ['NativeCallScope call_scope;',
                 f'auto *self = get<QScxmlTableData>(r, r->self, {g.ids["QScxmlTableData"]}, false, false);',
                 'if (r->error) return true;', 'int count = 0;', 'auto *names = self->dataNames(&count);',
                 'if (count < 0 || (count && !names)) return fail(r, EFAULT, "SCXML data names returned an invalid native extent");',
                 'QList<qint32> output; output.reserve(count);',
                 'for (int i = 0; i < count; ++i) output.append(names[i]);']
        return lines + g.store_result(m['return'], 'output') + ['return true;']
    if f['declaring_class'] in ('QStringDecoder', 'QStringEncoder'):
        owner = f['declaring_class']
        declarations, expression = g.argument(m['args'][0], 0)
        native = 'QString' if owner == 'QStringDecoder' else 'QByteArray'
        lines = ['NativeCallScope call_scope;', f'auto *self = get<{owner}>(r, r->self, {g.ids[owner]});',
                 'if (r->error) return true;', *declarations,
                 f'auto input = {expression};', 'const auto capacity = self->requiredSpace(input.size());',
                 'if (capacity < 0) return fail(r, ERANGE, "Text converter returned a negative output extent");',
                 f'{native} output(capacity, Qt::Uninitialized);',
                 'auto *start = output.data();', 'auto *end = self->appendToBuffer(start, input);',
                 'const auto begin_address = reinterpret_cast<uintptr_t>(start);',
                 'const auto end_address = reinterpret_cast<uintptr_t>(end);',
                 'if (end_address < begin_address || end_address - begin_address > uint64_t(capacity) * sizeof(*start)',
                 '    || (end_address - begin_address) % sizeof(*start))',
                 '    return fail(r, EFAULT, "Text converter returned an invalid output extent");',
                 'output.truncate(qsizetype((end_address - begin_address) / sizeof(*start)));']
        lines += g.store_result(m['return'], 'output')
        return lines + ['return true;']
    if is_text_word(f):
        lines = ['NativeCallScope call_scope;',
                 f'auto *self = get<QTextStream>(r, r->self, {g.ids["QTextStream"]});',
                 'if (r->error) return true;', 'QByteArray output_bytes;',
                 # Qt 6.12 explicitly documents this as the safe replacement
                 # for char*: both extract the same UTF-8 word and status.
                 '*self >> output_bytes;', f'r->result = sequence_value({len(m["return"]["children"])});']
        for i, (t, value) in enumerate(zip(m['return']['children'], ['self', 'output_bytes'])):
            lines.append(f'if (!r->error) r->result.items[{i}] = write_{t["native_codec"]}(r, {value});')
        return lines + ['return true;']
    lines = ['NativeCallScope call_scope;',
             f'auto *self = get<QDataStream>(r, r->self, {g.ids["QDataStream"]});',
             'if (r->error) return true;',
             'char *allocated_bytes = nullptr;', 'qint64 allocated_length = 0;',
             # Qt 6.12's char*& extraction operator delegates directly to this
             # overload, discarding only the length. Preserve it for safe copying.
             'self->readBytes(allocated_bytes, allocated_length);',
             'std::unique_ptr<char[]> allocated_guard(allocated_bytes);']
    if len(f['arguments']) == 2 and f['arguments'][1]['type']['name'] == 'uint':
        lines += ['if (allocated_length > std::numeric_limits<uint>::max()) {',
                  '    self->setStatus(QDataStream::SizeLimitExceeded);',
                  '    allocated_guard.reset(); allocated_bytes = nullptr; allocated_length = 0;', '}']
    lines += ['QByteArray output_bytes(allocated_bytes, qsizetype(allocated_length));',
              f'r->result = sequence_value({len(m["return"]["children"])});']
    values = ['self', 'output_bytes'] + (['allocated_length'] if len(f['arguments']) == 2 else [])
    for i, (t, value) in enumerate(zip(m['return']['children'], values)):
        lines.append(f'if (!r->error) r->result.items[{i}] = write_{t["native_codec"]}(r, {value});')
    lines.append('return true;')
    return lines
