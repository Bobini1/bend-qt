"""Scoped override-cursor restoration, corresponding to PySide's helper."""
from pathlib import Path

HERE = Path(__file__).resolve().parent


def emit(g):
    import scope_actions
    g.cursor_guard_operations = {}
    if not {'QCursor', 'QGuiApplication'}.issubset(g.ids):
        return
    name = 'QOverrideCursorGuard'
    g.types[name] = 'handle'
    handle = dict(kind='object', bend=name, raw='U32')
    unit = dict(kind='void', bend='Unit', raw='Unit')
    rows = [
        ('new', [('cursor', dict(kind='object', bend='QCursor', raw='U32'))], handle, 'create(r)', False),
        ('restoreOverrideCursor', [('self', handle)], unit, 'restore(r)', True),
        ('isActive', [('self', handle)], dict(kind='bool', bend='Bool', raw='U32'), 'active(r)', True),
        ('destroy', [('self', handle)], unit, 'destroy(r, false)', True),
        ('release', [('self', handle)], unit, 'destroy(r, true)', True),
    ]
    for suffix, args, result, call, self_arg in rows:
        operation = g.next_id
        g.next_id += 1
        g.cursor_guard_operations[suffix] = operation
        g.cases.append(f'case {operation}: {{\n    return NativeCursorGuards::{call};\n}}')
        g.emit_effect(name + '.' + suffix, args, result, operation, has_self=self_arg)
    g.emit_scope(name, 'release')
    scope_actions.keep(g, name)
    g.bend += ['def QOverrideCursorGuard.restore(self: QOverrideCursorGuard) -> Action(Unit):',
               '  QOverrideCursorGuard.restoreOverrideCursor(self)', '']


def cpp(g):
    if not getattr(g, 'cursor_guard_operations', {}):
        return ('static bool cursor_guard_cleanup_ready(BqtRequest *, uint32_t) { return true; }\n'
                'static bool cursor_guard_defer_release(BqtRequest *, uint32_t) { return false; }\n')
    return (HERE / 'templates/cursor_guards.cpp').read_text().replace('@QCursor@', str(g.ids['QCursor']))


def inventory(g):
    return dict(operations=getattr(g, 'cursor_guard_operations', {}),
        native='QGuiApplication override cursor stack',
        cleanup='One idempotent restore on explicit restore or scope cleanup; active native cursor-view calls defer cleanup',
        nesting='Each active guard restores one native stack entry; use normal reverse acquisition order')
