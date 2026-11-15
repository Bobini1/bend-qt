"""Cooperative QML incubation controlled by an owned atomic flag."""


def install(classes, selected):
    if 'QQmlIncubationController' not in classes:
        return
    classes['IncubationFlag'] = dict(name='IncubationFlag', object=False, value=True, qobject=False,
        public_destructor=True, abstract=False, copyable=False, namespace=False,
        generate=False, template=False, bases=[], functions=[], enums=[], adapter=True)
    selected.append('IncubationFlag')


def handles(f):
    return f['declaring_class'] == 'QQmlIncubationController' and f['name'] == 'incubateWhile'


def parameters(g, f):
    if not handles(f):
        return None
    args = [dict(kind='value', name='IncubationFlag', cpp='IncubationFlag', bend='IncubationFlag', raw='U32')]
    args += [g.type(a['type']) for a in f['arguments'][1:]]
    return args, [dict(type=t, source=i, input=i, output=False, mutable=False) for i, t in enumerate(args)], []


def method_case(g, m):
    f = m['function']
    if f['declaring_class'] == 'QQmlIncubationController' and f['name'] == 'engine':
        return ['NativeCallScope scope;',
            f'auto *self = get<QQmlIncubationController>(r, r->self, {g.ids["QQmlIncubationController"]}, false, false);',
            'if (r->error) return true;',
            f'r->result.word = borrow(r, observable_incubation_engine(self), {g.ids["QQmlEngine"]});', 'return true;']
    if not handles(m['function']):
        return None
    timeout = 'int32_t(r->arguments[1].word)' if len(m['args']) > 1 else '0'
    return ['NativeCallScope call_scope;',
        f'auto *self = get<QQmlIncubationController>(r, r->self, {g.ids["QQmlIncubationController"]});',
        f'get<IncubationFlag>(r, r->arguments[0].word, {g.ids["IncubationFlag"]}, false, false);',
        'if (r->error) return true;',
        'if (entry(r->self)->active_calls > 1) return fail(r, EBUSY, "Controller already has an active incubation call");',
        'if (!self->incubatingObjectCount()) return true;',
        'auto *engine = observable_incubation_engine(self);',
        'if (!engine) return fail(r, ESTALE, "Incubation has no observable engine association");',
        f'uint32_t engine_id = borrow(r, engine, {g.ids["QQmlEngine"]});',
        'if (r->error) return true;',
        f'int msecs = {timeout};',
        'auto deadline = msecs == 0 ? QDeadlineTimer(QDeadlineTimer::Forever) : QDeadlineTimer(msecs);',
        'auto state = std::make_shared<IncubationWait>(r, r->self, r->arguments[0].word, engine_id, deadline);',
        'if (!state->pin()) return true;',
        'return wait_until(r, [state] { return state->poll(); }, deadline);']


def before_call(g, m):
    f = m['function']
    if f['declaring_class'] == 'QQmlEngine' and f['name'] == 'setIncubationController':
        return ['if (a0) {', '    auto *old = observable_incubation_engine(a0);',
                '    if (old && old != self) return fail(r, EBUSY, "Detach the controller from its previous QML engine first");', '}']
    return []


def emit(g):
    if 'IncubationFlag' not in g.ids:
        return
    handle = dict(kind='value', name='IncubationFlag', bend='IncubationFlag', raw='U32')
    boolean = dict(kind='bool', bend='Bool', raw='U32')
    unit = dict(kind='void', bend='Unit', raw='Unit')
    for method in ('new', 'load', 'store'):
        op = g.next_id; g.next_id += 1
        lines = ['NativeCallScope scope;']
        if method == 'new':
            params, result = [('initial', boolean)], handle
            lines += [f'r->result.word = own(r, new IncubationFlag(r->arguments[0].word != 0), {g.ids["IncubationFlag"]});',
                      'r->result.owned_handle = r->result.word;']
        else:
            params = [('self', handle)] + ([('value', boolean)] if method == 'store' else [])
            result = boolean if method == 'load' else unit
            lines += [f'auto *self = get<IncubationFlag>(r, r->self, {g.ids["IncubationFlag"]}, false, {str(method == "store").lower()});',
                      'if (r->error) return true;']
            lines += ['r->result.word = self->value.load(std::memory_order_acquire);' if method == 'load'
                      else 'self->value.store(r->arguments[0].word != 0, std::memory_order_release);']
        g.cases.append(f'case {op}: {{\n' + '\n'.join('    ' + line for line in lines + ['return true;']) + '\n}')
        g.emit_effect('IncubationFlag.' + method, params, result, op, has_self=method != 'new')


def cpp(g):
    if 'IncubationFlag' not in g.ids or 'QQmlIncubationController' not in g.ids:
        return ''
    return f'''
static QQmlEngine *observable_incubation_engine(QQmlIncubationController *controller) {{
    // Qt 6.12 engine() dereferences its private pointer even when detached.
    // The count getter is null-safe; a positive count proves attachment.
    if (controller->incubatingObjectCount() > 0) return controller->engine();
    for (const auto &value : entries) {{
        if (!value.value || !value.object || value.destroying ||
                (value.alive && !(*value.alive)->load(std::memory_order_acquire))) continue;
        if (value.object->thread() != main_thread) continue;
        if (auto *engine = qobject_cast<QQmlEngine *>(value.object); engine && engine->incubationController() == controller)
            return engine;
    }}
    return nullptr;
}}
struct IncubationWait {{
    BqtRequest *request;
    uint32_t controller, flag, engine;
    QDeadlineTimer deadline;
    bool flag_pinned = false, engine_pinned = false;
    IncubationWait(BqtRequest *r, uint32_t c, uint32_t f, uint32_t e, QDeadlineTimer d)
        : request(r), controller(c), flag(f), engine(e), deadline(d) {{}}
    ~IncubationWait() {{
        if (engine_pinned) callback_unpin(engine);
        if (flag_pinned) callback_unpin(flag);
    }}
    bool pin() {{
        if (!callback_pin(request, flag)) return false;
        flag_pinned = true;
        if (!callback_pin(request, engine)) return false;
        engine_pinned = true; return true;
    }}
    bool poll() {{
        NativeCallScope scope;
        auto *c = get<QQmlIncubationController>(request, controller, {g.ids['QQmlIncubationController']}, false, false);
        auto *f = get<IncubationFlag>(request, flag, {g.ids['IncubationFlag']}, false, false);
        auto *e = get<QQmlEngine>(request, engine, {g.ids['QQmlEngine']}, false, false);
        if (request->error) return true;
        auto decide = [&] {{
            const bool alive = e->incubationController() == c && observable_incubation_engine(c) == e;
            return lifetime_incubation[unsigned(alive) * 8 + unsigned(f->value.load(std::memory_order_acquire)) * 4 +
                unsigned(c->incubatingObjectCount() > 0) * 2 + unsigned(deadline.hasExpired())];
        }};
        auto decision = decide();
        if (!decision) {{
            c->incubateWhile(&f->value, 1);
            if (!entry(controller) || !entry(flag) || !entry(engine)) decision = 2;
            else decision = decide();
        }}
        if (decision == 2) fail(request, ESTALE, "QML engine changed its incubation controller during the wait");
        return decision != 0;
    }}
}};
'''
