"""Caller-owned QFormLayout row items, including copied aggregate lifetimes."""
from pathlib import Path

TYPE = 'QFormLayout::TakeRowResult'


def before_call(g, m):
    f = m['function']
    if f['declaring_class'] == 'QFormLayout' and f['name'] == 'takeRow':
        import native_lifetimes
        native_lifetimes.prepare(g)
        return ['if (!native_children_idle(r, r->self)) return true;',
                'NativeTakeScope taken_row_scope(r->self);']
    if f['declaring_class'] == TYPE and m['args'] and m['args'][0].get('name') == TYPE:
        if f['constructor'] or f['name'] == 'operator=':
            return ['call_scope.value_origin = r->arguments[0].word;']
    return []


def after_call(g, m):
    if m['function']['declaring_class'] == TYPE and m['function']['name'] == 'operator=':
        return ['if (!finish_take_row_ownership(r, r->self)) return true;']
    return []


def adapt(g, f):
    if f['return']['name'] != TYPE:
        return None
    return dict(g.type(f['return'], result=True), take_row_result=(
        f['declaring_class'] == 'QFormLayout' and f['name'] == 'takeRow'))


def store(g, t, expression):
    if t.get('name') != TYPE or t['kind'] != 'value':
        return None
    return [f'r->result.word = store_taken_row(r, {expression}, {str(t.get("take_row_result", False)).lower()});',
            'r->result.owned_handle = r->result.word;']


def field_type(g, name, field, setter):
    if name != TYPE or field['name'] not in ('labelItem', 'fieldItem'):
        return None
    return dict(g.type(field['type'], result=not setter), taken_row_field=True)


def field_access(g, field, expression, argument=None):
    if not field['type'].get('taken_row_field'):
        return None
    index = int(field['field'] == 'fieldItem')
    if field['setter']:
        return [f'if (!set_taken_row_field(r, r->self, {index}, r->arguments[0].word)) return true;']
    return [f'r->result.word = taken_row_field(r, r->self, {index});',
            'r->result.borrowed_handle = r->result.word;']


def emit(g):
    if TYPE not in g.ids:
        return
    import native_lifetimes
    native_lifetimes.prepare(g)
    for index, suffix in enumerate(('LabelItem', 'FieldItem')):
        operation = g.next_id; g.next_id += 1
        g.cases.append(f'''case {operation}: {{
    NativeCallScope scope;
    get<{TYPE}>(r, r->self, {g.ids[TYPE]}, false, true);
    if (r->error) return true;
    r->result.word = take_row_item(r, r->self, {index});
    r->result.owned_handle = r->result.word;
    return true;
}}''')
        g.emit_effect('QFormLayout.TakeRowResult.take' + suffix,
            [('self', dict(bend='QFormLayout.TakeRowResult', raw='U32'))],
            dict(kind='object', name='QLayoutItem', bend='QLayoutItem', raw='U32'), operation, has_self=True)


def declarations(g):
    return ('static uint32_t store_taken_row(BqtRequest *, const QFormLayout::TakeRowResult &, bool);\n'
            if TYPE in g.ids else '')


def cpp(g):
    if TYPE not in g.ids:
        return ('static uint32_t finish_take_row_ownership(BqtRequest *, uint32_t id) { return id; }\n'
                'static void take_row_native_deleted(uint32_t) {}\n')
    source = (Path(__file__).parent / 'templates/form_rows.cpp').read_text()
    for name, marker in ((TYPE, 'ROW'), ('QLayoutItem', 'ITEM'), ('QWidget', 'WIDGET')):
        source = source.replace('@' + marker + '_TYPE@', str(g.ids[name]))
    return source
