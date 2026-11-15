"""QIODevice reverse byte-buffer contracts, independent of Python glue.

Qt owns native buffers. Bend receives copied write bytes and a read capacity;
read replies contain an explicit count and owned bytes, checked before memcpy.
https://doc.qt.io/qt-6/qiodevice.html#readData
https://doc.qt.io/qt-6/qiodevice.html#writeData
"""
from callbacks import _conversion, _record, signature_id, bend_ident, ident, thread_branch


def prepare_method(g, name, f):
    if 'QIODevice' not in [name] + g.all_bases(name) or f['name'] not in ('readData', 'readLineData', 'writeData'):
        return None
    arguments = f['arguments']
    if (len(arguments) != 2 or arguments[0]['type']['name'] != 'char' or
            arguments[0]['type']['pointers'] != 1 or arguments[1]['type']['name'] != 'qint64' or
            f['return']['name'] != 'qint64'):
        raise ValueError('Unknown QIODevice virtual byte-buffer contract')
    count = _conversion(g, f['return'])
    data = _conversion(g, dict(name='QByteArray', cpp='QByteArray', const=False, pointers=0,
                              reference=0, enum=False, flags=False, container=False, instantiations=[]))
    read = f['name'] != 'writeData'
    args = [count] if read else [data, count]
    result = _record(g, [count, data], 'CallbackReply_') if read else count
    method_id = signature_id(f['declaring_class'], f)
    return dict(function=f, args=args, payload=_record(g, args, 'CallbackArgs_'), result=result,
                native_result=count, outputs=[], method_id=method_id,
                public=bend_ident(f['declaring_class']) + '.Virtual.' + ident(f['name']) + '_' + str(method_id),
                device_io=True, device_read=read, device_data=data)


def cpp(g, name, method):
    f, count, data = method['function'], method['native_result'], method['device_data']
    read = method['device_read']
    parameters = ', '.join(a['type']['cpp'] + f' a{i}' for i, a in enumerate(f['arguments']))
    fallback = 'return -1;' if f['abstract'] else f'return {name}::{f["name"]}(a0, a1);'
    lines = [f'    qint64 {f["name"]}({parameters}) override {{',
             '        if (!bqt_receiver) ' + fallback,
             f'        uint32_t handler = bqt_handlers.find({method["method_id"]}u);']
    if f['abstract']:
        lines += ['        if (!handler) { callback_report_error(ENOSYS, "A pure virtual method has no Bend handler"); return -1; }']
    else:
        lines += ['        if (!handler) ' + fallback]
    lines += thread_branch(method, 'qint64', 'a0, a1', fallback, 'return -1;')
    lines += ['        try {',
              '            if (a1 < 0 || uint64_t(a1) > uint64_t(std::numeric_limits<qsizetype>::max()) || (a1 && !a0)) {',
              '                callback_report_error(EINVAL); return -1;', '            }',
              '            BqtRequest conversion{};',
              f'            CallbackOwnedArguments arguments{{sequence_value({1 if read else 2})}};']
    if read:
        lines += [f'            arguments.value.items[0] = write_{count["native_codec"]}(&conversion, a1);']
    else:
        lines += [f'            arguments.value.items[0] = write_{data["native_codec"]}(&conversion, QByteArray(a0, qsizetype(a1)));',
                  f'            arguments.value.items[1] = write_{count["native_codec"]}(&conversion, a1);']
    lines += ['            if (conversion.error) { callback_report_error(conversion.error); return -1; }',
              '            struct Reply { char *data; qint64 capacity; qint64 count = -1; };',
              f'            Reply reply{{{("a0" if read else "nullptr")}, a1}};',
              '            auto decode = [](BqtRequest *r, const BqtValue &wire, void *destination) {',
              '                auto *reply = static_cast<Reply *>(destination);']
    if read:
        lines += ['                if (!wire_shape(r, wire, 2, 2)) return false;',
                  f'                auto count = read_{count["native_codec"]}(r, wire.items[0]);',
                  f'                auto data = read_{data["native_codec"]}(r, wire.items[1]);',
                  '                if (!count || !data) return false;']
    else:
        lines += [f'                auto count = read_{count["native_codec"]}(r, wire);',
                  '                if (!count) return false;']
    lines += ['                if (*count < -1 || *count > reply->capacity) {',
              '                    fail(r, EINVAL, "QIODevice callback count exceeds native buffer capacity"); return false;', '                }']
    if read:
        lines += ['                if ((*count == -1 && !data->isEmpty()) || (*count >= 0 && *count != data->size())) {',
                  '                    fail(r, EINVAL, "QIODevice read count does not match the reply bytes"); return false;', '                }',
                  '                if (*count > 0) std::memcpy(reply->data, data->constData(), size_t(*count));']
    lines += ['                reply->count = *count;', '                return true;', '            };',
              f'            int error = callback_invoke(handler, bqt_receiver, arguments.take(), decode, &reply);',
              '            if (error' + ('' if f['abstract'] else ' && error != ENOSYS') + ') callback_report_error(error);',
              '            if (error) ' + ('return -1;' if f['abstract'] else '{ if (error == ENOSYS) ' + fallback + ' return -1; }'),
              '            return reply.count;',
              '        } catch (const std::bad_alloc &) { callback_report_error(ENOMEM); return -1; }',
              '          catch (...) { callback_report_error(EFAULT); return -1; }', '    }']
    return lines
