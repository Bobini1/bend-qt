"""QFuture adapters, discovered from concrete template signatures.

`await` waits like Qt's own waiting operations: it runs a Qt event loop until
the future finishes, so the application stays responsive and Bend's other
computations keep running meanwhile.
"""


def prepare(g):
    futures = [c for c in g.classes.values() if c.get('future_cpp')]
    if not futures:
        return
    for c in futures:
        try:
            payload = g.type(c['future_element'], result=True)
            if payload['kind'] == 'void':
                continue
            c['future_take_payload'] = payload
            if payload['kind'] == 'value' and not g.classes[payload['name']].get('copyable'):
                g.excluded.append({'class': c['name'], 'signature': 'resultAt(int)',
                    'reason': 'The native resultAt template requires a copyable payload',
                    'alternatives': [dict(bend_name=c['name'] + '.takeResult', contract='consuming_future_result',
                        reason='Moves the first finished result and invalidates every alias of the shared future; remaining results are discarded')]})
                continue
            c['future_payload'] = g.conversions.register(payload)
            c['future_take_payload'] = c['future_payload']
        except ValueError as error:
            g.excluded.append({'class': c['name'], 'signature': 'resultAt(int)', 'reason': str(error)})


def emit(g):
    void = {'kind': 'void', 'bend': 'Unit', 'raw': 'Unit'}
    boolean = {'kind': 'bool', 'bend': 'Bool', 'raw': 'U32'}
    integer = {'kind': 'i32', 'bend': 'Int32', 'raw': 'U32'}
    string = {'kind': 'string', 'bend': 'String', 'raw': 'String'}

    def handle(name):
        return {'kind': 'value', 'name': name, 'bend': name.replace('::', '.'), 'raw': 'U32'}

    def effect(name, parameters, result, lines, *, has_self=False):
        operation = g.next_id
        g.next_id += 1
        g.cases.append(f'case {operation}: {{\n    NativeCallScope scope;\n' + '\n'.join('    ' + line for line in lines) + '\n    return true;\n}')
        g.emit_effect(name.replace('::', '.'), parameters, result, operation, has_self=has_self)

    for name in g.selected:
        c = g.classes[name]
        if not c.get('future_cpp'):
            continue
        from module_partitions import exports_class
        if not exports_class(g, name):
            continue
        watcher = c['future_watcher']
        future, watch = handle(name), handle(watcher)
        get = [f'auto *value = get<{name}>(r, r->arguments[0].word, {g.ids[name]}, false, false);',
               'if (r->error) return true;']
        effect(name + '.new', [], future, [f'r->result.word = own(r, new {name}(), {g.ids[name]});'])
        element = c['future_element']['cpp']
        effect(name + '.fromError', [('message', string)], future,
               ['auto error = std::make_exception_ptr(std::runtime_error(std::string(r->arguments[0].text ? r->arguments[0].text : "", r->arguments[0].size)));',
                f'r->result.word = own(r, new {name}(QtFuture::makeExceptionalFuture<{element}>(error)), {g.ids[name]});'])
        effect(name + '.clone', [('value', future)], future,
               get + [f'r->result.word = own(r, new {name}(*value), {g.ids[name]});'])
        for method in ('isValid', 'isStarted', 'isFinished', 'isCanceled', 'isRunning', 'isSuspended', 'isSuspending'):
            effect(name + '.' + method, [('value', future)], boolean, get + [f'r->result.word = value->{method}();'])
        for method in ('cancel', 'suspend', 'resume'):
            effect(name + '.' + method, [('value', future)], void, get + [f'value->{method}();'])
        for method in ('resultCount', 'progressMinimum', 'progressMaximum', 'progressValue'):
            effect(name + '.' + method, [('value', future)], integer, get + [f'r->result.word = uint32_t(value->{method}());'])
        effect(name + '.isResultReadyAt', [('value', future), ('index', integer)], boolean,
               get + ['int index = int32_t(r->arguments[1].word);',
                      'if (index < 0) return fail(r, ERANGE, "Future result index is negative");',
                      'r->result.word = value->isValid() && value->isResultReadyAt(index);'])
        # Finished is monotonic for this shared state. The native wait performs
        # no work or blocking here; it only rethrows a stored Qt future failure.
        effect(name + '.checkFinished', [('value', future)], void,
               get + ['if (!value->isFinished()) return fail(r, EAGAIN, "Future has not finished");',
                      'value->waitForFinished();',
                      'if (!value->isValid()) return fail(r, ENODATA, "Future has no consumable state");'])
        payload = c.get('future_payload')
        if payload:
            effect(name + '.resultAt', [('value', future), ('index', integer)], payload,
                   get + ['int index = int32_t(r->arguments[1].word);',
                          'if (index < 0) return fail(r, ERANGE, "Future result index is negative");',
                          'if (value->isFinished()) value->waitForFinished();',
                          'if (!value->isValid()) return fail(r, ENODATA, "Future has no consumable result");',
                          'if (!value->isResultReadyAt(index)) return fail(r, value->isFinished() ? ENODATA : EAGAIN, "Future result is not ready");',
                          'auto returned = value->resultAt(index);'] + g.store_result(payload, 'returned'))
            declarations, expression = g.argument(payload, 0)
            effect(name + '.fromResult', [('value', payload)], future,
                   declarations + ['if (r->error) return true;',
                                   f'r->result.word = own(r, new {name}(QtFuture::makeReadyValueFuture({element}({expression}))), {g.ids[name]});'])
        taken = c.get('future_take_payload')
        if taken:
            effect(name + '.takeResult', [('value', future)], taken,
                   [f'auto *value = get<{name}>(r, r->arguments[0].word, {g.ids[name]}, false, true);',
                    'if (r->error) return true;',
                    'bool valid = value->isValid(), finished = value->isFinished();',
                    # Qt takeResult waits for all producer results, even if the
                    # first one is already available. Never enter that wait on
                    # the main thread before completion. Exceptions precede the
                    # empty-result check, as they do for ordinary resultAt.
                    'if (valid && finished) value->waitForFinished();',
                    'bool ready = valid && finished && value->isResultReadyAt(0);',
                    'auto decision = lifetime_future_take[unsigned(valid) * 4 + unsigned(finished) * 2 + unsigned(ready)];',
                    'if (decision) return fail(r, decision, decision == EAGAIN ? "Future has not finished; await it before taking its result" : "Future has no consumable first result");',
                    'auto returned = value->takeResult();'] + g.store_result(taken, 'returned'))
        effect(watcher + '.new', [], watch,
               [f'r->result.word = own(r, new {watcher}(), {g.ids[watcher]});'])
        effect(watcher + '.setFuture', [('self', watch), ('future', future)], void,
               [f'auto *self = get<{watcher}>(r, r->self, {g.ids[watcher]});',
                f'auto *value = get<{name}>(r, r->arguments[0].word, {g.ids[name]}, false, false);',
                'if (r->error) return true;',
                'if (!value->isValid()) return fail(r, ENODATA, "Cannot watch a future without consumable state");',
                'self->setFuture(*value);'], has_self=True)
        effect(watcher + '.future', [('self', watch)], future,
               [f'auto *self = get<{watcher}>(r, r->self, {g.ids[watcher]}, false, false);',
                'if (r->error) return true;',
                f'r->result.word = own(r, new {name}(self->future()), {g.ids[name]});',
                'r->result.owned_handle = r->result.word;'], has_self=True)
        effect(name + '.await', [('value', future)], void,
               get + ['if (!value->isValid()) return fail(r, ENODATA, "Future has no consumable state");',
                      'wait_until(r, [value] { return value->isFinished(); }, QDeadlineTimer(QDeadlineTimer::Forever));',
                      'if (r->error) return true;',
                      'r->result.word = 0;',
                      # Rethrows a stored failure; the future has finished.
                      'value->waitForFinished();'])
