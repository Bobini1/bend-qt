"""Consuming moves for noncopyable native values, with token invalidation."""
from pathlib import Path


def convert(g, t):
    c = g.classes.get(t['name'])
    if not c or c.get('copyable') or c.get('qobject') or t['const'] or t['pointers']:
        return None
    return dict(kind='object', name=t['name'], bend=t['name'].replace('::', '.'), raw='U32',
                cpp=t['cpp'], pointer=False, native_const=False, consume=True)


def argument(g, t, index):
    name = t['name']
    lines = [f'auto *a{index} = get<{name}>(r, r->arguments[{index}].word, {g.ids[name]}, false, true);',
             'if (r->error) return true;',
             f'if (!prepare_consuming_move(r, r->arguments[{index}].word)) return true;',
             f'MoveInput move{index}(r->arguments[{index}].word);']
    return lines, f'std::move(*a{index})'


def before_call(g, m):
    indices = [i for i, t in enumerate(m['args']) if t.get('consume')]
    if not indices:
        return []
    f = m['function']
    if not (f['constructor'] or f['name'] == 'operator=') or len(indices) != 1:
        raise ValueError('Consuming move needs one explicit constructor or assignment destination')
    i = indices[0]
    lines = []
    if f['name'] == 'operator=':
        lines += [f'if (!prepare_move_assignment(r, r->arguments[{i}].word)) return true;',
                  f'if constexpr (!std::is_nothrow_move_assignable_v<{m["args"][i]["name"]}>) {{',
                  '    if (!prepare_consuming_move(r, r->self)) return true;',
                  f'    move{i}.exception_destination = r->self;', '}']
    return lines + [f'move{i}.armed = true;']


def after_native(g, m):
    indices = [i for i, t in enumerate(m['args']) if t.get('consume')]
    if not indices:
        return []
    assignment = m['function']['name'] == 'operator='
    destination = 'r->self' if assignment else 'r->result.word'
    # Run immediately after the native operation, before conversion or any
    # postcondition can fail. An assignment has already changed its receiver.
    return [f'move{indices[0]}.complete({destination}, {str(assignment).lower()});']


def cpp(g):
    return (Path(__file__).parent / 'templates/moves.cpp').read_text()
