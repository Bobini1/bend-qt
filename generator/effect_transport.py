"""Share foreign effects by wire layout and validate their dynamic operation.

Bend's publisher reads an imported C file for every foreign definition. Keeping
the native operation out of the foreign signature avoids thousands of identical
file reads without changing the public typed functions.

A `Handler` argument passes a Bend function Qt will call. The public def is a
template: its `~f` is wrapped by a closed function that decodes Qt's request,
and the Data `state` travels with it. See `templates/handlers.bend`.
"""
KINDS = {'U32': 'w', 'U32 & U32': 'd', 'String': 's', 'Wire': 'v', 'Handler': 'h'}
PACKERS = {'U32': 'word', 'U32 & U32': 'wide', 'String': 'string', 'Wire': 'wire', 'Unit': 'unit'}
HANDLER_CALL = '(S{n} & Wire) -> IO(Result<&1, &1, U32 & String, Unit>)'


def result_type(name):
    return 'Result<&1, &1, U32 & String, ' + name + '>'


def handler(function, invoke):
    """An argument for a handler of Bend type `function`, run through `invoke`.

    `invoke` is a template `(~S: Data, ~f: function, pair: S & Wire) ->
    Action(Unit)` declared above the public def.
    """
    return dict(kind='handler', bend='Handler', raw='Handler', function=function, invoke=invoke)


def layout(g, native, ret):
    """The shared foreign effect for these native arguments and result."""
    if not hasattr(g, 'raw_effect_layouts'):
        g.raw_effect_layouts, g.raw_effect_operations = {}, {}
    raw_args = tuple(t['raw'] for _, t in native)
    raw_ret = ret['raw']
    if any(t not in KINDS for t in raw_args) or raw_ret not in PACKERS:
        raise ValueError('Unsupported raw effect shape')
    handlers = sum(t == 'Handler' for t in raw_args)
    if handlers > 1:
        raise ValueError('One call registers one handler')
    module = getattr(g, 'foreign_effect_module', None)
    key = (module, raw_args, raw_ret) if module else (raw_args, raw_ret)
    found = g.raw_effect_layouts.get(key)
    if found is not None:
        return found
    signature = ''.join(KINDS[t] for t in raw_args) or 'none'
    name = 'raw_Qt_' + (module + '_' if module else '') + signature + '_to_' + PACKERS[raw_ret]
    found = dict(id=len(g.raw_effect_layouts) + 1, name=name, args=raw_args, result=raw_ret)
    g.raw_effect_layouts[key] = found
    raw_params = ['-S0: Data'] if handlers else []
    raw_params += ['operation: U32', 'self: U32']
    for i, kind in enumerate(raw_args):
        if kind == 'U32 & U32':
            raw_params += [f'arg{i}_lo: U32', f'arg{i}_hi: U32']
        elif kind == 'Handler':
            raw_params += [f'arg{i}_call: ' + HANDLER_CALL.format(n=0), f'arg{i}_state: S0']
        else:
            raw_params += [f'arg{i}: {kind}']
    native_name = 'native_' + name
    native_params = raw_params[:1] + ['scope: U32'] + raw_params[1:] if handlers else ['scope: U32'] + raw_params
    arguments = (['S0'] if handlers else []) + ['scope'] + [p.split(':', 1)[0] for p in raw_params if not p.startswith('-')]
    g.bend += [f'def {native_name}({", ".join(native_params)}) -> IO({result_type(raw_ret)}):',
               '  import "' + getattr(g, 'foreign_effect_file', './qt.c') + '"', '',
               f'def {name}({", ".join(raw_params)}) -> Action.Raw({result_type(raw_ret)}):',
               f'  scope => {native_name}({", ".join(arguments)})', '']
    lines = [f'#ifdef CID({native_name})', f'static Term {name}_run(Env e, Term *f, IoWork *w) {{',
             '    BqtRequest request = {0};',
             '    request.scope = (uint32_t)f[0];',
             '    request.operation = (uint32_t)f[1];', '    request.self = (uint32_t)f[2];',
             '    bool valid = true;']
    if handlers:
        lines += ['    uint32_t handler = 0;']
    source = 3
    for i, kind in enumerate(raw_args):
        if kind == 'Wire':
            lines += [f'    valid = bqt_unpack_wire(e, f[{source}], &request.arguments[{i}], 0) && valid;']
        elif kind == 'String':
            lines += [f'    u64 size_{i};',
                      f'    request.arguments[{i}].text = io_cstr(e, f[{source}], &size_{i});',
                      f'    request.arguments[{i}].size = size_{i};',
                      f'    request.arguments[{i}].tag = 1;']
        elif kind == 'Handler':
            # Qt owns the handler once the call succeeds.
            lines += [f'    handler = bqt_handler_new(e, f[{source}], f[{source + 1}]);',
                      f'    request.arguments[{i}].word = handler;', '    valid = handler && valid;']
            source += 1
        else:
            lines += [f'    request.arguments[{i}].word = (uint32_t)f[{source}];']
            if kind == 'U32 & U32':
                source += 1
                lines += [f'    request.arguments[{i}].high = (uint32_t)f[{source}];']
        source += 1
    lines += [f'    if (!valid || !bqt_validate_layout(&request, {found["id"]})) {{',
              '        bqt_free_request(&request);']
    if handlers:
        lines += ['        bqt_host_release(handler);']
    lines += ['        return io_fail(e, EINVAL, "Qt operation and raw argument/result layout do not match");',
              '    }']
    if handlers:
        lines += ['    bool failed = false;',
                  f'    Term answer = bqt_call(e, &request, bqt_pack_{PACKERS[raw_ret]}, &failed);',
                  '    if (failed) bqt_host_release(handler);', '    return answer;']
    else:
        lines += [f'    return bqt_call(e, &request, bqt_pack_{PACKERS[raw_ret]}, NULL);']
    lines += ['}', f'static void __attribute__((constructor)) {name}_register(void) {{',
              f'    io_eff(CID({native_name}), {name}_run);', '}', '#endif', '']
    g.effects += lines
    return found


def reserve(g, public, params, ret, operation, *, has_self=False):
    """Binds `operation` to its layout. Answers that layout.

    For an operation whose public def the caller writes itself, such as a
    connect that takes the operation number from a signal value.
    """
    native = params[1:] if has_self else params
    if has_self and (not params or params[0][1]['raw'] != 'U32'):
        raise ValueError('Native self must be one handle word: ' + public)
    # The ABI reserves operations below ten for process-wide destruction,
    # connections and counters. Secondary modules use the root transport for
    # these operations instead of retaining themselves for shared cleanup.
    if getattr(g, 'partition_secondary', False) and int(operation) < 10:
        previous = g.raw_effect_operations.get(int(operation))
        if previous is not None:
            found = next(row for row in g.raw_effect_layouts.values() if row['id'] == previous[0])
            if (previous[1] != bool(has_self) or found['args'] != tuple(t['raw'] for _, t in native)
                    or found['result'] != ret['raw']):
                raise ValueError('Conflicting shared runtime layout: ' + public)
            return found
    try:
        found = layout(g, native, ret)
    except ValueError as error:
        raise ValueError(f'{error}: {public}')
    operation_key = int(operation)
    contract = found['id'], bool(has_self)
    previous = g.raw_effect_operations.setdefault(operation_key, contract)
    if previous != contract:
        raise ValueError(f'Conflicting raw layouts for operation {operation_key}: {public}')
    g.argument_capacity = max(g.argument_capacity, len(native))
    return found


def emit(g, public, params, ret, operation, *, has_self=False, alias=None, doc=None):
    found = reserve(g, public, params, ret, operation, has_self=has_self)
    native = params[1:] if has_self else params
    raw_ret = ret['raw']
    handlers = [t for _, t in native if t['raw'] == 'Handler']
    values = [str(operation), f'{params[0][1]["bend"]}.word({params[0][0]})' if has_self and params[0][1]['bend'] != 'U32'
              else params[0][0] if has_self else '0']
    if handlers:
        values.insert(0, 'S')
    for name, t in native:
        # A constant is fixed by the generated def, not passed by its caller.
        if 'constant' in t: values.append(str(t['constant']))
        elif t['raw'] == 'Wire': values.append(f'{t["codec"]}.encode({name})')
        elif t['raw'] == 'Handler': values += [f'pair => run(Unit, {t["invoke"]}(~S, ~f, pair))', name]
        elif t['raw'] == 'U32 & U32': values += [f'{t["bend"]}.lo({name})', f'{t["bend"]}.hi({name})']
        elif t['bend'] in ('U32', 'String'): values.append(name)
        elif t['bend'] == 'Bool': values.append(f'bool_word({name})')
        else: values.append(f'{t["bend"]}.word({name})')
    call = f'{found["name"]}({", ".join(values)})'
    public_params = [f'~S: Data, ~f: {handlers[0]["function"]}'] if handlers else []
    public_params += [('+' if t['raw'] == 'U32 & U32' else '') + n + ': ' + ('S' if t['raw'] == 'Handler' else t['bend'])
                      for n, t in params if 'constant' not in t]
    if doc:
        g.bend.append(doc)
    g.bend += [f'def {public}({", ".join(public_params)}) -> Action({ret["bend"]}):']
    if ret['bend'] in ('U32', 'String', 'Unit'):
        g.bend += ['  ' + call, '']
    else:
        wrap = ret['codec'] + '.wrap' if raw_ret == 'Wire' else 'bool_wrap' if ret['bend'] == 'Bool' else ret['bend'] + '.wrap'
        g.bend += [f'  do Action.Raw<{result_type(ret["bend"])}>:',
                   f'    result: {result_type(raw_ret)} <- {call}', f'    return {wrap}(result)', '']


def effects(g):
    layouts = sorted(getattr(g, 'raw_effect_layouts', {}).values(), key=lambda row: row['id'])
    operations = getattr(g, 'raw_effect_operations', {})
    if not layouts:
        return '\n'.join(g.effects)
    lines = ['// Includes the return packer, not only the argument count.',
             'typedef struct { uint32_t operation, layout; bool self; } BqtOperationLayout;',
             'static const BqtOperationLayout bqt_operation_layouts[] = {']
    lines += [f'    {{{operation}, {layout}, {str(self).lower()}}},'
              for operation, (layout, self) in sorted(operations.items())]
    lines += ['};', 'static const char *const bqt_argument_layouts[] = { "",']
    lines += ['    "' + ''.join(KINDS[t] for t in row['args']) + '",' for row in layouts]
    lines += ['};', '''
static bool bqt_valid_wire(const BqtValue *value, unsigned depth) {
    if (depth > 128) return false;
    if (value->tag == 0) return !value->text && !value->items && !value->count;
    if (value->tag == 1) return (value->text || !value->size) && !value->items && !value->count;
    if (value->tag == 3) return !value->text && !value->items && !value->count && !value->high && bqt_data_exists(value->word);
    if (value->tag != 2 || value->text || (value->count && !value->items)) return false;
    for (size_t i = 0; i < value->count; ++i)
        if (!bqt_valid_wire(&value->items[i], depth + 1)) return false;
    return true;
}
static bool bqt_validate_layout(const BqtRequest *request, uint32_t layout) {
    size_t low = 0, high = sizeof bqt_operation_layouts / sizeof *bqt_operation_layouts;
    while (low < high) {
        size_t mid = low + (high - low) / 2;
        const BqtOperationLayout *row = &bqt_operation_layouts[mid];
        if (row->operation < request->operation) low = mid + 1;
        else high = mid;
    }
    if (low == sizeof bqt_operation_layouts / sizeof *bqt_operation_layouts) return false;
    const BqtOperationLayout *row = &bqt_operation_layouts[low];
    if (row->operation != request->operation || row->layout != layout || (!row->self && request->self)) return false;
    const char *kinds = bqt_argument_layouts[layout];
    for (size_t i = 0; kinds[i]; ++i) {
        const BqtValue *value = &request->arguments[i];
        if (!bqt_valid_wire(value, 0)) return false;
        if ((kinds[i] == 'w' || kinds[i] == 'd' || kinds[i] == 'h') && value->tag != 0) return false;
        if (kinds[i] == 's' && value->tag != 1) return false;
        if ((kinds[i] == 'w' || kinds[i] == 'h') && value->high) return false;
    }
    return true;
}
''']
    return '\n'.join(lines + g.effects)


def inventory(g):
    return dict(raw_foreign_effects=len(getattr(g, 'raw_effect_layouts', {})),
                operation_layouts=len(getattr(g, 'raw_effect_operations', {})),
                validation='Operation, receiver mode, argument shape and result packer checked before the native call')
