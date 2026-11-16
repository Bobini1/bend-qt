"""Typed native QMutexLocker helpers absent from ApiExtractor's class model."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORD = dict(kind='u32', bend='U32', raw='U32')
UNIT = dict(kind='void', bend='Unit', raw='Unit')
BOOL = dict(kind='bool', bend='Bool', raw='U32')


def emit(g):
    import scope_actions
    if not {'QMutex', 'QRecursiveMutex'}.issubset(g.ids):
        g.mutex_locker_operations = {}
        return
    slot = g.retention_slots.setdefault('QMutexLocker.mutex', len(g.retention_slots) + 1)
    g.mutex_locker_slot = slot
    operations = {}
    def handle(name): return dict(kind='object', bend=name, raw='U32')
    rows = []
    for kind, mutex, locker in [(0, 'QMutex', 'QMutexLocker'), (1, 'QRecursiveMutex', 'QRecursiveMutexLocker')]:
        g.types[locker] = 'handle'
        rows += [('QMutexLocker.new__' + mutex, [('mutex', handle(mutex))], handle(locker), f'create<{mutex}, {kind}>(r)', False)]
        rows += [(locker + '.' + name, [('self', handle(locker))], result, f'{call}(r, {kind})', True)
            for name, result, call in [('destroy', UNIT, 'destroy_strict'), ('release', UNIT, 'release'),
                ('isLocked', BOOL, 'locked'), ('unlock', UNIT, 'unlock'), ('relock', UNIT, 'relock'),
                ('mutex', handle(mutex), 'mutex')]]
        rows += [(locker + '.swap', [('self', handle(locker)), ('other', handle(locker))], UNIT, f'swap(r, {kind})', True)]
    for name, args, result, call, self_arg in rows:
        operation = g.next_id
        g.next_id += 1
        operations[name] = operation
        g.cases.append(f'case {operation}: {{\n    return NativeMutexLockers::{call};\n}}')
        g.emit_effect(name, args, result, operation, has_self=self_arg)
    for name in ('QMutexLocker', 'QRecursiveMutexLocker'):
        g.emit_scope(name, 'release')
        scope_actions.escapes(g, name)
    g.mutex_locker_operations = operations
    g.bend += [(HERE / 'templates/mutex_lockers.bend').read_text()]


def cpp(g):
    if not getattr(g, 'mutex_locker_operations', {}):
        return ''
    return ((HERE / 'templates/mutex_lockers.cpp').read_text()
        .replace('@QMutex@', str(g.ids['QMutex']))
        .replace('@QRecursiveMutex@', str(g.ids['QRecursiveMutex']))
        .replace('@RETENTION_SLOT@', str(g.mutex_locker_slot)))


def inventory(g):
    return dict(operations=getattr(g, 'mutex_locker_operations', {}),
        native='Real QMutexLocker<QMutex> and QMutexLocker<QRecursiveMutex>',
        lifetime='Source mutex identity and physical owner retained until locker destruction, including while unlocked',
        scope='Action scopes unlock on Done and Fail; body failures take precedence',
        thread='Construction, locking, unlocking and destruction use the normal Bend/Qt main thread')
