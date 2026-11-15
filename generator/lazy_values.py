"""Owned input views and live converter leases for Qt lazy conversion records."""
from pathlib import Path
import re


def prepare(g):
    if hasattr(g, 'lazy_values'): return
    g.lazy_values = {}
    for name in g.selected:
        native = g.api.get('typedefs', {}).get(name, '')
        match = re.fullmatch(r'(.+)::(?:EncodedData|DecodedData)<(QByteArrayView|QStringView)>', native)
        if not match or match[1] not in g.ids: continue
        fields = {f['name']: f for f in g.classes[name].get('fields', []) if f.get('public') and not f.get('removed')}
        pointers = [f for f in fields.values() if f['type'].get('pointers') == 1 and f['type']['name'] == match[1]]
        views = [f for f in fields.values() if not f['type'].get('pointers') and f['type']['name'] == match[2]]
        if len(pointers) == len(views) == 1:
            g.lazy_values[name] = dict(converter=match[1], pointer=pointers[0]['name'], data=views[0]['name'],
                view=match[2], backing='QByteArray' if match[2] == 'QByteArrayView' else 'QString',
                result='QString' if match[2] == 'QByteArrayView' else 'QByteArray')
    g.lazy_converter_types = {s['converter'] for s in g.lazy_values.values()}
    pending = list(g.lazy_converter_types)
    while pending:
        for base in g.classes.get(pending.pop(), {}).get('bases', []):
            if base not in g.lazy_converter_types:
                g.lazy_converter_types.add(base); pending.append(base)


def before_call(g, m):
    prepare(g)
    f = m['function']; name = f['declaring_class']
    if name in g.lazy_values and (f['constructor'] or f['name'] == 'operator=') and m['args'] and m['args'][0].get('name') == name:
        return ['call_scope.value_origin = r->arguments[0].word;']
    if name in g.lazy_converter_types and f['name'] in ('operator=', 'swap'):
        return ['if (retained(r->self)) return fail(r, EBUSY, "Converter is retained by a deferred conversion");']
    return []


def after_call(g, m):
    prepare(g)
    return ['if (!finish_lazy_value_ownership(r, r->self)) return true;'] if m['function']['declaring_class'] in g.lazy_values and m['function']['name'] == 'operator=' else []


def method_case(g, m):
    prepare(g)
    spec = g.lazy_values.get(m['return'].get('name'))
    f = m['function']
    if not spec or f['declaring_class'] != spec['converter'] or len(m['args']) != 1:
        return None
    declarations, argument = g.argument(m['args'][0], 0)
    # QStringView inputs normally refer to an expression-local QString. A lazy
    # result still refers to it after the call's full expression has ended.
    # Keep that owning conversion alive until the ownership hook snapshots it.
    lines = ['NativeCallScope scope;',
        f'auto *self = get<{spec["converter"]}>(r, r->self, {g.ids[spec["converter"]]}, false, true);']
    owned_input = f'({argument}).toString()' if spec['view'] == 'QStringView' else argument
    lines += declarations + ['if (r->error) return true;', f'auto lazy_input = {owned_input};',
        f'auto returned = self->{f["name"]}({spec["view"]}(lazy_input));']
    return lines + g.store_result(m['return'], 'returned') + ['return true;']


def field_type(g, name, field, setter):
    prepare(g)
    spec = g.lazy_values.get(name)
    if spec and field['name'] in (spec['pointer'], spec['data']):
        return g.conversions.register(dict(g.type(field['type'], result=not setter), lazy_field=True))
    return None


def field_access(g, field, expression, argument=None):
    if not field['type'].get('lazy_field'): return None
    name = field['class']; spec = g.lazy_values[name]
    if not field['setter']: return g.store_result(field['type'], expression)
    operation = 'converter' if field['field'] == spec['pointer'] else 'data'
    return [f'if (!set_lazy_{operation}<{name}>(r, r->self, {argument})) return true;']


def emit(g):
    prepare(g)
    for name, spec in g.lazy_values.items():
        result = g.type(dict(name=spec['result'], cpp=spec['result'], pointers=0, reference=0,
            const=False, container=False, enum=False, flags=False, instantiations=[]), result=True)
        op = g.next_id; g.next_id += 1
        lines = ['NativeCallScope scope;', f'auto *self = get<{name}>(r, r->self, {g.ids[name]}, false, false);',
            'if (r->error) return true;', f'if (!lazy_converter<{name}>(r, r->self, true)) return true;',
            f'auto result = static_cast<{spec["result"]}>(*self);'] + g.store_result(result, 'result') + ['return true;']
        g.cases.append(f'case {op}: {{\n' + '\n'.join(lines) + '\n}')
        g.emit_effect(name.replace('::','.')+'.value', [('self',dict(kind='value',name=name,bend=name.replace('::','.'),raw='U32'))], result, op, has_self=True)


def cpp(g):
    prepare(g)
    traits=[]; cases=[]
    for name, spec in g.lazy_values.items():
        c, view, backing = spec['converter'], spec['view'], spec['backing']
        traits += [f'template<> struct LazyValueTraits<{name}> {{',
            f'using Converter = {c}; using View = {view}; using Backing = {backing};',
            f'static constexpr uint16_t type = {g.ids[name]}, converter_type = {g.ids[c]};',
            f'static auto &converter({name} &value) {{ return value.{spec["pointer"]}; }}',
            f'static auto &data({name} &value) {{ return value.{spec["data"]}; }}', '};']
        cases += [f'case {g.ids[name]}: result = capture_lazy_value<{name}>(r, id); break;']
    return (Path(__file__).parent/'templates/lazy_values.cpp').read_text().replace('// @LAZY_TRAITS@','\n'.join(traits)).replace('// @LAZY_CASES@','\n'.join(cases))


def inventory(g):
    prepare(g)
    return dict(records=g.lazy_values, contract='Deferred conversion retains the actual mutable converter and owned input backing; copies share backing, setters replace it atomically.',
        conversion='Record.value performs the native implicit conversion at invocation time.',
        verification='Native lifetime and streaming behavior require integration tests.')
