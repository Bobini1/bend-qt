"""Restore typed std::function callbacks from upstream signatures and snippets.

Only the native callable signature is reused. Python glue is never executed or
vendored. The handler stays registered while the Qt object stores the function.
"""
import copy
import re
import effect_transport
from callbacks import _conversion, _record, _decode, native, signature_id, bend_ident, ident


FUNCTION = re.compile(r'std::function\s*<\s*([^()<>]+)\(([^()]*)\)\s*>')
# This typedef is not retained by ApiExtractor. Its Qt public declaration is
# verified by compilation; the two QStringView inputs are copied immediately.
ALIASES = {'QRemoteObjectHostBase::RemoteObjectNameFilter': 'std::function<bool(QStringView, QStringView)>'}


def _surface(f):
    """Public callable glue whose native lifetime contract needs an adapter."""
    owner, name = f['declaring_class'], f['name']
    if not any(a['type']['name'] in ('PyCallable', 'PyObject') for a in f['arguments']):
        return None
    if owner == 'QCoreApplication' and name == 'requestPermission':
        return dict(signature=('void', ['const QPermission &']), context=True)
    if owner in ('QCanvasPainterWidget', 'QCanvasRhiPaintDriver') and name == 'grabCanvas':
        # Qt 6.11 takes only canvas + callback; Qt 6.12 adds a context.
        # Without an explicit context, track the callable against its owner.
        return dict(signature=('void', ['const QImage &']),
                    context=any(a['type']['name'] == 'QObject' for a in f['arguments']))
    if owner == 'QHttpServer' and name == 'route':
        return dict(signature=('QString', ['const QHttpServerRequest &']), route=True)
    if owner == 'QHttpServer' and name == 'addAfterRequestHandler':
        return dict(signature=('void', ['const QHttpServerRequest &', 'QHttpServerResponse &']), context=True)
    if owner == 'QRestAccessManager' and name in ('deleteResource', 'get', 'head', 'patch', 'post', 'put', 'sendCustomRequest'):
        return dict(signature=('void', ['QRestReply &']), context=True, reply=True)
    if owner == 'QAbstractOAuth' and name == 'setModifyParametersFunction':
        return dict(signature=('void', ['QAbstractOAuth::Stage', 'QMultiMap<QString, QVariant> *']), output_map=1)
    if owner == 'QTimer' and name == 'singleShot':
        return dict(signature=('void', []), static=True,
                    context=any(a['type']['name'] == 'QObject' for a in f['arguments']))
    if owner == 'QHostInfo' and name == 'lookupHost':
        return dict(signature=('void', ['const QHostInfo &']), static=True, lookup=True)
    return None


def _type(cpp):
    cpp = cpp.strip()
    return dict(cpp=cpp, name=cpp.removeprefix('const ').replace('&', '').replace('*', '').strip(),
                const=cpp.startswith('const '), pointers=cpp.count('*'), reference=2 if '&&' in cpp else int('&' in cpp),
                enum=False, flags=False, container=False, instantiations=[])


def _signature(f):
    text = '\n'.join(f.get('source_signatures', []) + f.get('snippets', []))
    for alias, value in ALIASES.items():
        text = text.replace(alias, value)
    found = FUNCTION.search(text)
    if found:
        return found[1].strip(), [x.strip() for x in found[2].split(',') if x.strip()]
    # Some upstream conversion snippets use a named, void lambda instead.
    if any(a['type']['name'] == 'PyCallable' for a in f['arguments']):
        found = re.search(r'auto\s+callback\s*=\s*\[[^]]*\]\s*\(([^()]*)\)\s*\{', text)
        if found:
            return 'void', [re.sub(r'([&*]|\s)\s*[A-Za-z_]\w*\s*$', r'\1', x).strip()
                            for x in found[1].split(',') if x.strip()]
    return None


def prepare(g):
    g.callback_functions = []
    seen, native_seen = set(), set()
    handlers = {}
    for name in g.selected:
        if not g.classes[name]['qobject'] and not any(_surface(f) for f in g.classes[name]['functions']):
            continue
        for original in g.classes[name]['functions']:
            surface = _surface(original)
            if surface and surface.get('static'):
                original = dict(original, static=True)
            if not original['public'] or (original['static'] and not surface) or original['constructor']:
                continue
            signature = surface['signature'] if surface else _signature(original)
            if not signature:
                continue
            key = original['declaring_class'] + '::' + original['minimal_signature']
            if key in seen:
                continue
            seen.add(key)
            try:
                if original['declaring_class'] == 'QProcess' and original['name'] == 'setChildProcessModifier':
                    raise ValueError('Post-fork child modifiers cannot invoke Bend, Qt, locks or callback transport; use QProcess UnixProcessParameters for native child setup')
                positions = [i for i, a in enumerate(original['arguments']) if a['type']['name'] == 'PyCallable' or
                             (surface and a['type']['name'] == 'PyObject')]
                if len(positions) > 1:
                    raise ValueError('Multiple callable arguments need one handler each')
                position = positions[0] if positions else len(original['arguments'])
                forward = [g.type(a['type']) for i, a in enumerate(original['arguments']) if i != position]
                if not surface and any(t['kind'] == 'object' or t.get('children') for t in forward):
                    raise ValueError('Stored function arguments require an explicit ownership policy')
                callback_return, callback_args = signature
                native_key = (original['declaring_class'], original['name'], original['const'],
                              tuple(t['cpp'].replace(' ', '') for t in forward),
                              callback_return.replace(' ', ''), tuple(t.replace(' ', '') for t in callback_args))
                if native_key in native_seen:
                    continue
                args = []
                for callback_index, cpp in enumerate(callback_args):
                    source = _type(cpp)
                    if surface and surface.get('output_map') == callback_index:
                        source = dict(_type('QMultiMap<QString, QVariant>'), name='QMultiMap', container=True,
                                      instantiations=[_type('QString'), _type('QVariant')])
                        t = _conversion(g, source)
                        t['function_output_map'] = True
                        args.append(t)
                        continue
                    if source['name'] in g.enums:
                        source['enum'] = True
                    if source['reference'] and not source['const']:
                        if not surface or not g.classes.get(source['name'], {}).get('native_object'):
                            raise ValueError('Mutable function references require a combined reply contract')
                        # These native move-only objects are valid for this
                        # invocation. Their ordinary methods mutate Qt's object;
                        # a saved handle expires when the callback returns.
                        t = _conversion(g, _type(source['name'] + ' *'))
                        t['function_temporary'] = True
                        args.append(t)
                        continue
                    if source['name'] in ('QStringView', 'QAnyStringView', 'QLatin1StringView'):
                        t = _conversion(g, _type('QString'))
                        t['function_string_view'] = True
                    else:
                        t = _conversion(g, source)
                    if surface and original['declaring_class'] in ('QCanvasPainterWidget', 'QCanvasRhiPaintDriver') and source['name'] == 'QImage':
                        # Qt's image can point into a readback buffer that is
                        # removed immediately after the native callback.
                        t['function_deep_copy'] = True
                    args.append(t)
                result = args[surface['output_map']] if surface and 'output_map' in surface else _conversion(g, _type(callback_return), result=True)
                if result['kind'] not in ('void', 'bool', 'u32', 'i32', 'i64', 'u64', 'real', 'string', 'value') and not (surface and 'output_map' in surface):
                    raise ValueError('Function callback return needs an independently owned value')
                owner = original['declaring_class']
                f = copy.deepcopy(original)
                f['minimal_signature'] = f['name'] + ':std_function(' + ','.join(callback_args) + ')->' + callback_return
                method_id = signature_id(owner, f)
                # Upstream snippets and declarations can spell the same C++
                # callable differently (for example QVariant& / QVariant &).
                # Keep the first identity, sharing its codec across overloads.
                handler_key = (owner, f['name'], callback_return.replace(' ', ''),
                               tuple(arg.replace(' ', '') for arg in callback_args))
                if handler_key in handlers:
                    method = handlers[handler_key]
                elif method_id in g.callback_methods:
                    # Native overloads sharing the same result signature use the
                    # same response codec and method_id, deliberately.
                    method = g.callback_methods[method_id]
                else:
                    method = dict(function=f, args=args, result=result, native_result=result,
                                  outputs=[], payload=_record(g, args, 'CallbackArgs_'), method_id=method_id,
                                  public=bend_ident(owner) + '.Handler.' + ident(f['name']) + '_' + str(method_id))
                    g.callback_methods[method_id] = method
                handlers[handler_key] = method
                item = dict(method=method, function=original, owner=owner, callback_position=position,
                            forward=forward, return_=g.type(_type('int') if surface and surface.get('lookup') else original['return'], result=True),
                            native_return=callback_return, native_arguments=callback_args,
                            public=bend_ident(owner) + '.' + ident(original['name']) + 'WithHandler_' + str(signature_id(owner, original)),
                            surface=surface)
                if surface and surface.get('context'):
                    item['context_position'] = next(i for i, t in enumerate(forward) if t.get('name') == 'QObject')
                if surface and surface.get('reply'):
                    body = next((i for i, t in enumerate(forward) if t.get('name') in ('QIODevice', 'QHttpMultiPart')), None)
                    if body is not None:
                        import retention
                        item['retention'] = dict(input=body, slot=retention._slot(g, 'QNetworkReply.requestBody'))
                g.callback_functions.append(item)
                native_seen.add(native_key)
            except ValueError as error:
                g.callback_excluded.append(dict(class_name=name, signature=original['minimal_signature'], pure=False,
                                               reason='Function callback: ' + str(error)))


def emit(g):
    cleared = set()
    for item in g.callback_functions:
        f, owner, args = item['function'], item['owner'], item['forward']
        method = item['method']
        operation = g.next_id
        g.next_id += 1
        lines = ['NativeCallScope scope;']
        if not f['static']:
            lines += [f'auto *self = get<{owner}>(r, r->self, {g.ids[owner]});']
        lines += [f'uint32_t handler = r->arguments[{len(args)}].word;',
                 'if (r->error) return true;']
        expressions = []
        for i, t in enumerate(args):
            declarations, expression = g.argument(t, i)
            lines += declarations
            expressions.append(expression)
        receiver = (f'(r->arguments[{item["context_position"]}].word ? r->arguments[{item["context_position"]}].word : r->self)'
                    if 'context_position' in item else 'r->self')
        expressions.insert(item['callback_position'], f'callback_function_{method["method_id"]}(handler, {receiver})')
        lines += ['if (r->error) return true;']
        retained = item.get('retention')
        if retained:
            lines += ['RetentionBatch retention_batch;',
                      f'if (!retention_batch.add(r, 0, {retained["slot"]}, r->arguments[{retained["input"]}].word, nullptr, false, true, 0)) return true;']
        expression = (owner + '::' if f['static'] else 'self->') + f['name'] + '(' + ', '.join(expressions) + ')'
        if (item.get('surface') or {}).get('route'):
            expression = '(' + expression + ' != nullptr)'
        lines += g.store_result(item['return_'], expression)
        if retained:
            lines += ['if (!retention_batch.finish(r, r->result.word, true)) return true;']
        lines += ['return true;']
        g.cases.append(f'case {operation}: {{\n' + '\n'.join('    ' + line for line in lines) + '\n}')
        g.emit_effect(item['public'], ([] if f['static'] else [('self', dict(bend=bend_ident(owner), raw='U32'))]) +
                      [(f'arg{i}', t) for i, t in enumerate(args)] +
                      [('state', effect_transport.handler(method['handler'], method['public'] + '.invoke'))],
                      item['return_'], operation, has_self=not f['static'])
        if 'output_map' in (item.get('surface') or {}) and owner not in cleared:
            cleared.add(owner)
            operation = g.next_id
            g.next_id += 1
            g.cases.append(f'case {operation}: {{\n    NativeCallScope scope;\n'
                           f'    auto *self = get<{owner}>(r, r->self, {g.ids[owner]});\n'
                           '    if (r->error) return true;\n    self->setModifyParametersFunction({});\n    return true;\n}')
            g.emit_effect(bend_ident(owner) + '.clearModifyParametersFunction',
                          [('self', dict(bend=bend_ident(owner), raw='U32'))], dict(kind='void', bend='Unit', raw='Unit'), operation, has_self=True)


def annotate(g):
    """Link removed/stripped native declarations to emitted callable adapters."""
    by_signature = {}
    for item in getattr(g, 'callback_functions', []):
        f = item['function']
        by_signature.setdefault(f['signature'], []).append(item)
    for excluded in g.excluded:
        for item in by_signature.get(excluded.get('signature'), []):
            owner = item['owner']
            if excluded['class'] != owner and owner not in g.all_bases(excluded['class']):
                continue
            alternative = dict(bend_name=item['public'],
                               contract='typed_function_handler', native_signature=item['function']['minimal_signature'],
                               reason=('Passes a typed Bend handler as the native callable; ordinary values are copied and mutable move-only native arguments are callback-scoped views; the Qt context cancels delivery and destroying the callable releases the handler'
                                       if item.get('surface') else
                                       'Passes a Bend handler as the native callable, with copied arguments; Qt owns the stored function and destroying it releases the handler'))
            if alternative not in excluded.setdefault('alternatives', []):
                excluded['alternatives'].append(alternative)


def cpp(g):
    lines, seen = [], set()
    for item in g.callback_functions:
        method = item['method']
        method_id, ret, args = method['method_id'], method['result'], method['args']
        if method_id in seen:
            continue
        seen.add(method_id)
        result_type = item['native_return']
        fallback = 'return;' if result_type == 'void' else 'return {};'
        parameters = ', '.join(cpp + f' a{i}' for i, cpp in enumerate(item['native_arguments']))
        # Qt owns the function object. Destroying it gives the handler back.
        lines += [f'static auto callback_function_{method_id}(uint32_t handler, uint32_t receiver) {{',
                  '    auto holder = std::make_shared<CallbackFunctionHandler>(handler);',
                  '    auto alive = callback_source_alive(receiver);',
                  f'    return [holder, receiver, alive]({parameters}) -> {result_type} {{',
                  f'        auto invoke = [&]() -> {result_type} {{', '            try {',
                  '            NativeCallScope scope;', '            CallbackNativeArguments native_arguments;',
                  '            BqtRequest conversion{};', f'            CallbackOwnedArguments arguments{{sequence_value({len(args)})}};']
        for i, t in enumerate(args):
            value = f'a{i}.toString()' if t.get('function_string_view') else f'a{i}'
            if t.get('function_deep_copy'):
                value = f'a{i}.copy()'
            if t.get('function_output_map'):
                lines += [f'            if (!a{i}) {{ callback_report_error(EINVAL, "The native parameter map is null"); {fallback} }}']
                value = '*a' + str(i)
            if t.get('function_temporary'):
                lines += [f'            arguments.value.items[{i}] = native_arguments.borrow_argument(&conversion, &a{i}, {g.ids[t["name"]]}, receiver);']
            elif t['kind'] == 'object' and not g.classes[t['name']]['qobject']:
                pointer = f'a{i}' if t.get('pointer') else f'&a{i}'
                lines += [f'            arguments.value.items[{i}] = native_arguments.borrow_argument(&conversion, {pointer}, {g.ids[t["name"]]}, receiver);']
            elif t.get('callback_enum'):
                expression = f'a{i}.toInt()' if t['kind'].startswith('flags') else f'a{i}'
                lines += [f'            arguments.value.items[{i}] = wide_value(uint64_t({expression}));']
            else:
                if t['kind'] == 'object' and not t.get('pointer'):
                    value = '&a' + str(i)
                lines += [f'            arguments.value.items[{i}] = write_{t["native_codec"]}(&conversion, {value});']
        lines += ['            if (conversion.error) { callback_report_error(conversion.error, conversion.message); ' + fallback + ' }']
        if ret['kind'] == 'void':
            lines += ['            int error = callback_invoke(holder->handler, receiver, arguments.take(), callback_decode_unit, nullptr);',
                      '            if (error) callback_report_error(error);']
        else:
            lines += [f'            std::optional<{native(ret)}> result;',
                      '            auto decode = [](BqtRequest *r, const BqtValue &wire, void *destination) {',
                      *['                ' + line for line in _decode(ret, 'wire', 'value')],
                      f'                *static_cast<std::optional<{native(ret)}> *>(destination) = std::move(value);',
                      '                return true;', '            };',
                      '            int error = callback_invoke(holder->handler, receiver, arguments.take(), decode, &result);',
                      '            if (error) callback_report_error(error);',
                      '            if (error || !result) ' + fallback]
            if (item.get('surface') or {}).get('output_map') is not None:
                lines += [f'            *a{item["surface"]["output_map"]} = std::move(*result);', '            return;']
            else:
                lines += ['            return std::move(*result);']
        lines += ['            } catch (const std::bad_alloc &) { callback_report_error(ENOMEM); ' + fallback + ' }',
                  '              catch (...) { callback_report_error(EFAULT); ' + fallback + ' }', '        };',
                  '        if (QThread::currentThread() == main_thread) return invoke();',
                  f'        return callback_from_thread<{result_type}>(alive, invoke, [&]() -> {result_type} {{ {fallback} }});',
                  '    };', '}', '']
    return '\n'.join(lines)
