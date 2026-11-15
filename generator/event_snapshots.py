"""Transfer independently owned SCXML event snapshots to native queues."""


def handles(f):
    return ((f['declaring_class'], f['name']) in {
            ('QScxmlStateMachine', 'submitEvent'), ('QScxmlInvokableService', 'postEvent')}
            and len(f['arguments']) == 1 and f['arguments'][0]['type']['name'] == 'QScxmlEvent'
            and f['arguments'][0]['type']['pointers'] == 1)


def parameters(g, f):
    if not handles(f):
        return None
    t = g.type(dict(f['arguments'][0]['type'], cpp='QScxmlEvent', pointers=0, reference=0, const=False))
    t['native_copy_adoption'] = True  # The custom call transfers its independent heap snapshot.
    return [t], [dict(type=t, source=0, input=0, output=False, mutable=False)], []


def method_case(g, m):
    f = m['function']
    if not handles(f):
        return None
    owner = f['declaring_class']
    lines = ['NativeCallScope call_scope;', f'auto *self = get<{owner}>(r, r->self, {g.ids[owner]});',
             f'auto *event = get<QScxmlEvent>(r, r->arguments[0].word, {g.ids["QScxmlEvent"]}, false, false);',
             'if (r->error) return true;']
    if owner == 'QScxmlStateMachine':
        lines += ['if (event->delay() > 0 && event->eventType() != QScxmlEvent::ExternalEvent)',
                  '    return fail(r, EINVAL, "Delayed SCXML events must have ExternalEvent type");']
    return lines + ['auto snapshot = std::make_unique<QScxmlEvent>(*event);',
                    f'self->{f["name"]}(snapshot.release());', 'return true;']
