"""QObject.moveToThread hands an object tree to another thread.

Bend calls Qt only on the main thread, so a moved object is unavailable to
Bend afterwards (EXDEV). The move is refused while the binding itself still
relies on the tree from the main thread: see object_move_allowed in
templates/runtime.cpp.
"""


def before_call(g, m):
    f = m['function']
    if f['declaring_class'] == 'QObject' and f['name'] == 'moveToThread':
        return ['if (!object_move_allowed(r, r->self)) return true;']
    return []


def handles(f):
    return (f['declaring_class'], f['name']) == ('QThread', 'setEventDispatcher')


def method_case(g, m):
    if not handles(m['function']):
        return None
    return [
        'NativeCallScope scope;',
        f'auto *self = get<QThread>(r, r->self, {g.ids["QThread"]});',
        f'auto *dispatcher = get<QAbstractEventDispatcher>(r, r->arguments[0].word, {g.ids["QAbstractEventDispatcher"]}, true);',
        'if (r->error) return true;',
        'if (!dispatcher) return fail(r, EINVAL, "An event dispatcher must not be null");',
        'if (self->eventDispatcher()) return fail(r, EEXIST, "The thread already has an event dispatcher");',
        'if (dispatcher->parent()) return fail(r, EINVAL, "An event dispatcher must have no QObject parent");',
        'if (dispatcher == QAbstractEventDispatcher::instance(main_thread)) return fail(r, EBUSY, "The main event dispatcher is already in use");',
        'const uint32_t id = r->arguments[0].word;',
        'if (!can_transfer_handle(r, id) || !object_move_allowed(r, id)) return true;',
        'if (reaches_token(id, r->self)) return fail(r, ELOOP, "Event dispatcher ownership would create a cycle");',
        'QPointer<QAbstractEventDispatcher> guard(dispatcher);',
        'self->setEventDispatcher(dispatcher);',
        'if (!guard || !entry(id) || !entry(r->self)) return fail(r, ESTALE, "A thread or dispatcher was destroyed during transfer");',
        'if (self->eventDispatcher() != dispatcher || dispatcher->thread() != self) return fail(r, EINVAL, "Qt rejected the event dispatcher transfer");',
        'set_native_owner(r, id, r->self);',
        'return true;',
    ]
