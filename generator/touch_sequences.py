"""Owning QtTest touch sequences using Qt's public native test support."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORD = dict(kind='u32', bend='U32', raw='U32')
UNIT = dict(kind='void', bend='Unit', raw='Unit')
BOOL = dict(kind='bool', bend='Bool', raw='U32')
INT = dict(kind='i32', bend='Int32', raw='U32')


def emit(g):
    g.touch_sequence_operations = {}
    if 'QtTest' not in g.profile['qt_modules'] or not {'QWindow', 'QWidget', 'QPointingDevice', 'QPoint'}.issubset(g.ids):
        return
    def handle(name):
        return dict(kind='object', name=name, bend=name, raw='U32')
    g.touch_sequence_slot = g.retention_slots.setdefault('QTest.QTouchEventSequence.sources', len(g.retention_slots) + 1)
    operations = [
        ('createDevice', [('deviceType', WORD), ('capabilities', WORD)], handle('QPointingDevice'), 'create_device(r)', False),
        ('newWindow', [('window', handle('QWindow')), ('device', handle('QPointingDevice')), ('autoCommit', BOOL)], WORD, 'create(r, false)', False),
        ('newWidget', [('widget', handle('QWidget')), ('device', handle('QPointingDevice')), ('autoCommit', BOOL)], WORD, 'create(r, true)', False),
        ('destroy', [('self', WORD)], UNIT, 'destroy(r, false)', True),
        ('releaseHandle', [('self', WORD)], UNIT, 'destroy(r, true)', True),
        ('commit', [('self', WORD), ('processEvents', BOOL)], BOOL, 'commit(r)', True),
        ('stationary', [('self', WORD), ('touchId', INT)], UNIT, 'stationary(r)', True),
    ]
    for name, state in [('press', 'Pressed'), ('move', 'Updated'), ('release', 'Released')]:
        for suffix, mapping, kind in [('', [], 0), ('Window', [('window', handle('QWindow'))], 1), ('Widget', [('widget', handle('QWidget'))], 2)]:
            operations.append((name + suffix, [('self', WORD), ('touchId', INT), ('point', handle('QPoint')), *mapping],
                               UNIT, f'update(r, QEventPoint::{state}, {kind})', True))
    for name, args, result, call, self_arg in operations:
        operation = g.next_id
        g.next_id += 1
        g.touch_sequence_operations[name] = operation
        g.cases.append(f'case {operation}: {{\n    return NativeTouchSequences::{call};\n}}')
        g.emit_effect('Internal.TouchSequence.' + name, args, result, operation, has_self=self_arg)
    g.bend += [(HERE / 'templates/touch_sequences.bend').read_text()]


def cpp(g):
    if not getattr(g, 'touch_sequence_operations', {}):
        return ''
    result = (HERE / 'templates/touch_sequences.cpp').read_text()
    for name in ('QWindow', 'QWidget', 'QPointingDevice', 'QPoint'):
        result = result.replace('@' + name + '@', str(g.ids[name]))
    return result.replace('@RETENTION_SLOT@', str(g.touch_sequence_slot))


def public_adapter(g, method):
    # Newer extraction snapshots include the native zero-default overload.
    # The public helper already supplies its defaults through createDevice,
    # which also scopes the observed view of Qt's application-owned device.
    if (getattr(g, 'touch_sequence_operations', {}) and
            method['bend_name'] == 'QTest.createTouchDevice' and not method['args']):
        method['operation'] = g.touch_sequence_operations['createDevice']
        return True
    return False


def includes(g):
    return '#include <QtGui/qtestsupport_gui.h>\n' if 'QtTest' in g.profile['qt_modules'] else ''


def inventory(g):
    return dict(operations=getattr(g, 'touch_sequence_operations', {}),
        native='Public Qt QTest::QTouchEventSequence with native Qt event dispatch',
        lifetime='Owning scoped sequence retains its QObject target and pointing device; native deletion is checked before commit',
        coordinates='Default target, explicit QWindow and explicit QWidget coordinate spaces',
        cleanup='Auto-commit defaults to true, explicit commit clears pending points; Done and Fail both release the sequence')
