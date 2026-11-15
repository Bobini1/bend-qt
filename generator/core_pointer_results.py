"""Audited ownership and scoped views of core native pointer results."""
from pathlib import Path

HERE = Path(__file__).resolve().parent


def install(classes, selected):
    owner = 'Qt3DAnimation::QChannelComponent'
    if owner not in selected or 'Qt3DAnimation::QKeyFrame' not in selected:
        return
    from convenience_apis import _function, _list, _type
    frame = _type('Qt3DAnimation::QKeyFrame')
    classes[owner]['functions'] += [
        _function(owner, 'keyFrames', [], _list(frame), kind='keyframe_snapshot'),
        _function(owner, 'keyFrameAt', [('index', _type('int'))], frame, kind='keyframe_at'),
    ]


def adapt(g, function):
    import adapters
    if adapters.raw_keyframe_iterator(function):
        raise ValueError('Raw key-frame pointer iterators use keyFrames or keyFrameAt snapshots')
    if adapters.static_native_result(function):
        return dict(g.type(function['return'], result=True), static_native_view=True)
    return None


def store(g, value, expression):
    if not value.get('static_native_view'):
        return None
    readonly = str(bool(value.get('readonly') or value.get('native_const'))).lower()
    return [f'r->result.word = borrow_static_native_view(r, {expression}, {g.ids[value["name"]]}, {{}}, {readonly});',
            'r->result.borrowed_handle = r->result.word;']


def after_call(g, method):
    function = method['function']
    if function['name'] == 'clone' and function['declaring_class'] in ('QEvent', 'QIconEngine'):
        return ['if (!copy_cloned_native_dependencies(r, r->result.word, r->self)) return true;']
    return []


def before_call(g, method):
    function = method['function']
    if function['declaring_class'] in ('QRandomGenerator', 'QRandomGenerator64') and function['name'] in ('seed', 'operator='):
        return ['if (entry(r->self)->destroy == release_static_native_view) return fail(r, EPERM, "Qt process-wide random generators cannot be reseeded or assigned");']
    return []


def method_case(g, method):
    function = method['function']
    if (function['declaring_class'], function['name']) == ('QLoggingCategory', 'defaultCategory'):
        return ['NativeCallScope call_scope;',
                f'r->result.word = borrow_static_native_view(r, QLoggingCategory::defaultCategory(), {g.ids["QLoggingCategory"]});',
                'r->result.borrowed_handle = r->result.word;', 'return true;']
    kind = function.get('convenience')
    if kind in ('keyframe_snapshot', 'keyframe_at'):
        owner = function['declaring_class']
        lines = ['NativeCallScope call_scope;',
                 f'auto *self = get<{owner}>(r, r->self, {g.ids[owner]}, false, false);',
                 'if (r->error) return true;']
        if kind == 'keyframe_snapshot':
            lines += ['QList<Qt3DAnimation::QKeyFrame> returned;',
                      'returned.reserve(self->keyFrameCount());',
                      'for (auto iterator = self->cbegin(); iterator != self->cend(); ++iterator) returned.append(*iterator);']
        else:
            lines += ['const int index = int32_t(r->arguments[0].word);',
                      'if (index < 0 || index >= self->keyFrameCount()) return fail(r, ERANGE, "Key frame index is outside the component");',
                      'auto returned = self->cbegin()[index];']
        return lines + g.store_result(method['return'], 'returned') + ['return true;']
    if function['declaring_class'] not in ('QEvent', 'QIconEngine') or function['name'] != 'clone':
        return None
    receiver = g.receiver_class(method)
    value = method.get('native_return', method['return'])
    helper = 'observe_cloned_event' if function['declaring_class'] == 'QEvent' else 'observe_cloned_icon_engine'
    return ['NativeCallScope call_scope;',
            f'auto *self = get<{receiver}>(r, r->self, {g.ids[receiver]}, false, false);',
            'if (r->error) return true;', 'auto *returned = self->clone();',
            'if (returned == self) return fail(r, EINVAL, "A clone must be a new native object");',
            f'r->result.word = {helper}(r, returned, {g.ids[value["name"]]});',
            'r->result.owned_handle = r->result.word;',
            'if (!r->error && !copy_cloned_native_dependencies(r, r->result.word, r->self)) return true;',
            'return true;']


def annotate(g):
    for row in g.excluded:
        if row['class'] == 'Qt3DAnimation::QChannelComponent' and row['signature'].split('(', 1)[0] in ('begin', 'cbegin', 'end', 'cend'):
            row.setdefault('alternatives', []).extend([
                dict(bend_name='Qt3DAnimation.QChannelComponent.keyFrames', contract='owning_keyframe_sequence'),
                dict(bend_name='Qt3DAnimation.QChannelComponent.keyFrameAt', contract='checked_owning_keyframe_at'),
            ])


def cpp(g):
    events = []
    for name in g.selected:
        cls = g.classes[name]
        if name != 'QEvent' and 'QEvent' not in g.all_bases(name):
            continue
        if cls.get('abstract') or cls.get('final_cpp') or not cls.get('derived_destructible'):
            continue
        if not any(f.get('copy_constructor') and not f.get('private') and not f.get('removed')
                   for f in cls['functions']):
            continue
        events.append(f'''    if (typeid(*pointer) == typeid({name})) {{
        auto value = std::make_unique<NativeTracked<{name}>>(*static_cast<{name} *>(static_cast<QEvent *>(pointer)));
        original.reset();
        return own_derived<{name}>(r, value.release(), {g.ids[name]});
    }}''')
    icon = (HERE/'templates/icon_engine_observer.cpp').read_text() if 'QIconEngine' in g.ids else ''
    return (HERE/'templates/core_pointer_results.cpp').read_text().replace('@OBSERVED_EVENT_CLONES@', '\n'.join(events)) + icon
