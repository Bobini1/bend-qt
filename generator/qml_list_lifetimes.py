"""QQmlListReference membership leases attached to the native list owner."""
from pathlib import Path


def method_case(g, m):
    f = m['function']
    if f['declaring_class'] != 'QQmlListReference' or f['name'] not in ('append', 'replace', 'at', 'clear', 'removeLast'):
        return None
    name = f['name']
    lines = ['NativeCallScope call_scope;',
             f'auto *self = get<QQmlListReference>(r, r->self, {g.ids["QQmlListReference"]}, false, false);']
    arguments = []
    for i, arg in enumerate(m['args']):
        declaration, expression = g.argument(arg, i)
        lines += declaration
        arguments.append(expression)
    lines += ['if (r->error) return true;',
              'auto *lease = qml_list_lease(r, *self, true);',
              'if (r->error) return true;',
              'QmlListCall list_call(r, *self, lease);',
              'if (r->error) return true;']
    if name in ('at', 'replace'):
        lines += [f'auto index = {arguments[0]};',
                  'if (!self->canCount() || !self->canAt()) return fail(r, ENOTSUP, "Indexed QML list access requires observable bounds");',
                  'if (index < 0 || index >= self->count()) return fail(r, ERANGE, "QML list index is outside its native extent");',
                  'if (!self->isValid()) return fail(r, ESTALE, "QML list owner expired during a callback");']
    if name in ('append', 'replace'):
        i = 0 if name == 'append' else 1
        lines += [f'if (!retain_qml_list_member(r, lease, r->arguments[{i}].word)) return true;']
    if name == 'removeLast':
        lines += ['if (!self->canCount()) return fail(r, ENOTSUP, "Removing a QML list tail requires observable bounds");',
                  'if (self->count() <= 0) return fail(r, ERANGE, "QML list is empty");']
    call = f'self->{name}(' + ', '.join(arguments) + ')'
    lines += ['auto result = ' + call + ';', 'reconcile_parents();']
    if name == 'clear':
        lines += ['if (result && lease && (!self->canCount() || !self->canAt())) clear_qml_list_members(lease->id);']
    lines += g.store_result(m['return'], 'result')
    return lines + ['return true;']


def before_call(g, m):
    f = m['function']
    if f['declaring_class'] == 'QQmlListReference' and not f['constructor'] and not f['static']:
        return ['QmlListCall list_call(r, *self, qml_list_lease(r, *self, false));', 'if (r->error) return true;']
    return []


def cpp(g):
    if 'QQmlListReference' not in g.ids:
        return 'static void prune_qml_list_leases() {}\n'
    return (Path(__file__).parent / 'templates/qml_list_lifetimes.cpp').read_text().replace('@QOBJECT_TYPE@', str(g.ids['QObject']))
