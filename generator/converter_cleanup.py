"""One-shot native State cleanup callbacks without raw function pointers."""
from pathlib import Path

STATE = 'QStringConverterBase::State'
PUBLIC = 'QStringConverterBase.State.Cleanup'


def before_call(g, m):
    if STATE not in g.ids: return []
    f=m['function']; lines=[]
    if f['declaring_class'] == STATE and not f['constructor'] and not f['const']:
        allowed = f['name'] in ('clear', 'reset', 'operator=')
        lines += [f'if (!converter_cleanup_access(r, self, {str(allowed).lower()})) return true;']
    for index,t in enumerate(m['args']):
        if t.get('name') != STATE: continue
        # A consuming native move carries the cleanup holder along with the state.
        if not (f['declaring_class'] == STATE and t.get('consume')):
            lines += [f'if (!converter_cleanup_argument(r, r->arguments[{index}].word)) return true;']
    return lines


def after_native(g,m):
    return []


def field_guard(g, field, argument):
    if field['class'] != STATE or not field['setter']: return []
    name=field['field']
    lines=['if (!converter_cleanup_access(r, self, true)) return true;']
    if name == 'flags':
        lines += [f'if (self->clearFn == converter_cleanup_native && ({argument}).testFlag(QStringConverterBase::Flag::UsesIcu)) return fail(r, EINVAL, "A Bend cleanup holder is not ICU codec storage");']
    elif name not in ('internalState','remainingChars','invalidChars'):
        lines += ['if (self->clearFn == converter_cleanup_native) return fail(r, EBUSY, "Native cleanup storage is reserved until cleanup or removal");']
    return lines


def emit(g):
    if STATE not in g.ids: return
    import effect_transport
    state=dict(bend=STATE.replace('::','.'),raw='U32')
    unit=dict(kind='void',bend='Unit',raw='Unit')
    for name,params,result,body in [
        ('install',[('self',state),('state',effect_transport.handler(g.converter_cleanup_handler, PUBLIC+'.invoke'))],unit,'return converter_cleanup_install(r);'),
        ('remove',[('self',state)],unit,'return converter_cleanup_remove(r);'),
        ('installed',[('self',state)],dict(kind='bool',bend='Bool',raw='U32'),'return converter_cleanup_installed(r);'),
    ]:
        op=g.next_id; g.next_id+=1
        g.cases.append(f'case {op}: {{\n {body}\n}}')
        g.emit_effect(PUBLIC+'.'+name,params,result,op,has_self=True)


def bend_helpers(g):
    """Declared before emit(): the handler wrapper the install def names."""
    if STATE not in g.ids: return
    import signals
    snapshot = 'QStringConverterBase.State.CleanupSnapshot'
    g.bend += [
        f'type {snapshot} is Data:',
        f'  {snapshot}{{flags: Flags_QStringConverterBase__Flag, internalState: Int32, remainingChars: Int64, invalidChars: Int64}}', '',
        f'def {PUBLIC}.decode(value: Wire) -> Maybe<&2, {snapshot}>:',
        '  match value:',
        '    case WireSequence{WireScalar{flags, 0} <> WireScalar{internal, 0} <> WireScalar{remaining_lo, remaining_hi} <> WireScalar{invalid_lo, invalid_hi} <> Nil{}}:',
        f'      Some{{{snapshot}{{Flags_QStringConverterBase__Flag{{flags}}, Int32{{internal}}, Int64{{remaining_lo, remaining_hi}}, Int64{{invalid_lo, invalid_hi}}}}}}',
        '    case _: None{}', '']
    g.converter_cleanup_handler = signals.invoke_value(g, PUBLIC, snapshot, PUBLIC + '.decode')


def cpp(g):
    if STATE not in g.ids: return ''
    return (Path(__file__).parent/'templates/converter_cleanup.cpp').read_text().replace('@STATE@',str(g.ids[STATE]))


def inventory(g):
    if STATE not in g.ids: return {}
    methods=[f['minimal_signature'] for f in g.classes[STATE]['functions'] if f['public'] and not f.get('removed')]
    fields=[dict(name=f['name'],cpp=f['type']['cpp']) for f in g.classes[STATE]['fields'] if f['public'] and not f.get('removed')]
    return dict(native_methods=methods, native_fields=fields, native_field=STATE+'.clearFn', APIs=[PUBLIC+'.install',PUBLIC+'.remove',PUBLIC+'.installed'],
        contract='One-shot actual native cleanup callback running a Bend handler; scalar snapshot; holder follows native consuming moves; opaque foreign cleanup/storage is never replaced.',
        limits=['No arbitrary C function pointers or raw union storage.', 'Native custom codec Interface construction remains protected.', 'A cleanup on another thread runs its handler on the main thread; native noexcept callback failures are reported through the Qt operation in progress.'])


def annotate(g):
    for row in getattr(g,'excluded_fields',[]):
        if row.get('class') == STATE and row.get('field') == 'clearFn':
            row['alternatives']=[dict(bend_name=PUBLIC+'.installed' if row['operation']=='get' else PUBLIC+'.install',
                contract='one_shot_native_cleanup', reason='Actual noexcept native callback with copied scalar state, checked storage ownership and move transfer; arbitrary function pointers remain unsupported.')]
