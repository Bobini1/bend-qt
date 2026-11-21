"""Thread-confined RHI ownership, pooled batches, and frame validity."""
from pathlib import Path
import re
import zlib
import rhi_buffer_access


def field_type(g, name, field, setter):
    """Pointer members in backend parameter records keep their actual objects."""
    source = field['type']
    if (not name.startswith('QRhi') or source.get('pointers') != 1 or source['name'] not in g.classes):
        return None
    native = source['name']
    if native not in ('QSurface', 'QObject') and 'QObject' not in g.all_bases(native) and not resource(g, native):
        return None
    return dict(g.type(source, result=False), rhi_parameter_pointer=True, nullable=True)


def field_access(g, field, expression, argument=None):
    if not field['type'].get('rhi_parameter_pointer'):
        return None
    native = field['type']['name']
    if argument is None:
        return [f'r->result.word = borrow(r, {expression}, {g.ids[native]});']
    slot = 0xb2000000 | (zlib.crc32((field['class'] + '.' + field['field']).encode()) & 0xffffff)
    return [f'const uint32_t slot = {slot}u;',
            'auto retention = prepare_retention(r, slot, 0, r->arguments[0].word);',
            'if (r->error) return true;',
            f'{expression} = a0;',
            'commit_retention(retention, r->self, slot, 0, r->arguments[0].word, nullptr);']


def restore_methods(g):
    headers = {}
    for name, cls in g.classes.items():
        if not name.startswith('QRhi') or not cls.get('source_file'):
            continue
        path = cls['source_file']
        if path not in headers:
            headers[path] = Path(path).read_text(errors='replace') if Path(path).is_file() else ''
        for f in cls['functions']:
            if not f.get('user_added') or f['constructor'] or len(f['arguments']) != 1:
                continue
            source = f['arguments'][0]['type']
            if source['name'] != 'QList' or len(source.get('instantiations', [])) != 1:
                continue
            element = source['instantiations'][0]['name']
            initializer = r'void\s+' + re.escape(f['name']) + r'\s*\(\s*std::initializer_list\s*<\s*' + re.escape(element) + r'\s*>\s+\w+\s*\)'
            iterator = r'void\s+' + re.escape(f['name']) + r'\s*\(\s*InputIterator\s+first\s*,\s*InputIterator\s+last\s*\)'
            if re.search(initializer, headers[path]) and re.search(iterator, headers[path]):
                f['rhi_range_adapter'] = True


def dependencies(g, m):
    f, result = m['function'], m.get('native_return', m['return'])
    if not f['declaring_class'].startswith('QRhi') or f['declaring_class'] in ('QRhiResourceUpdateBatch', 'QRhiCommandBuffer'):
        return None
    produced = bool(result.get('name', '').startswith('QRhi') and result.get('kind') in ('value', 'object')
                    and (result.get('kind') == 'value' or result.get('owned') or f['constructor']) and not m.get('outputs'))
    mutation = not f['static'] and not f['const'] and (f['name'].startswith(('set', 'append', 'operator=')) or
                resource(g, f['declaring_class']) and f['name'] == 'createFrom')
    if not (produced or mutation):
        return None
    targets = []
    def visit(t, expression, depth=0):
        if t.get('kind') in ('object', 'value') and t.get('name', '').startswith('QRhi'):
            targets.append((expression + '.word', t['kind'] == 'value'))
        elif t.get('kind') in ('list', 'array') and t.get('children'):
            before = len(targets)
            visit(t['children'][0], f'rhi_wire_{depth}', depth + 1)
            if len(targets) > before:
                inner = targets[before:]; del targets[before:]
                targets.append(('loop', expression, f'rhi_wire_{depth}', inner))
    for index, t in enumerate(m['args']):
        visit(t, f'r->arguments[{index}]')
    if produced and not f['static'] and not f['constructor']:
        targets.append(('r->self', True))
    return dict(produced=produced, mutation=mutation, targets=targets) if targets else None


def dependency_before(g, m):
    plan = dependencies(g, m)
    if not plan:
        return []
    lines = ['RetentionBatch rhi_dependencies;']
    owner = '0' if plan['produced'] else 'r->self'
    fresh = 'true' if plan['produced'] else 'false'
    def add(targets, indent=''):
        nonlocal lines
        for target in targets:
            if target[0] == 'loop':
                _, expression, variable, children = target
                lines.append(indent + f'for (size_t {variable}_index = 0; {variable}_index < {expression}.count; ++{variable}_index) {{')
                lines.append(indent + f'    const auto &{variable} = {expression}.items[{variable}_index];')
                add(children, indent + '    ')
                lines.append(indent + '}')
            else:
                identifier, copied = target
                if copied:
                    lines.append(indent + f'for (const auto &edge : retentions) if (edge.owner == {identifier} && edge.target) {{')
                    identifier, suffix = 'edge.target', '    '
                else:
                    suffix = ''
                slot = '(edge.slot == 0xb1000004u ? 0xb1000004u : 0xb1000003u)' if copied else ('0xb1000004u' if m['function']['name'] == 'createFrom' else '0xb1000003u')
                lines += [indent + suffix + f'if ({identifier} && {identifier} != {owner}) {{',
                          indent + suffix + f'    if (!rhi_dependency_domain(r, r->self, {identifier})) return true;',
                          indent + suffix + f'    if (!rhi_dependencies.add(r, {owner}, {slot}, {identifier}, nullptr, false, {fresh}, {identifier})) return true;']
                if plan['produced'] and plan['mutation']:
                    lines += [indent + suffix + f'    if ({identifier} != r->self && !rhi_dependencies.add(r, r->self, {slot}, {identifier}, nullptr, false, false, {identifier})) return true;']
                lines += [indent + suffix + '}']
                if copied: lines.append(indent + '}')
    add(plan['targets'])
    return lines


def resource(g, name):
    return name == 'QRhiResource' or name in g.classes and 'QRhiResource' in g.all_bases(name)


def prepare(g):
    if 'QRhiReadbackResult' not in g.ids:
        return
    payload = dict(kind='value', name='QRhiReadbackResult', bend='QRhiReadbackResult', raw='U32',
                   cpp='QRhiReadbackResult', pointer=False)
    g.rhi_readback_payload = g.conversions.register(payload)
    g.types['QRhi.Flag'] = 'scalar'
    g.flag_types.add('QRhi.Flag')
    if 'QRhiAdapter' in g.ids:
        child = dict(name='QRhiAdapter', cpp='QRhiAdapter *', const=False, pointers=1, reference=0,
                     enum=False, flags=False, container=False, instantiations=[])
        sequence = dict(child, name='QList', cpp='QList<QRhiAdapter *>', pointers=0,
                        container=True, instantiations=[child])
        g.rhi_adapter_list = g.conversions.owned_objects(g.type(sequence, result=True))


def parameters(g, f):
    owner, name = f['declaring_class'], f['name']
    if ((owner, name) not in {('QRhiCommandBuffer', 'setShaderResources'),
                              ('QRhiShaderResourceBinding', 'sampledTextures'),
                              ('QRhiShaderResourceBinding', 'textures')} or len(f['arguments']) < 3):
        return None
    first = len(f['arguments']) - 2
    source = f['arguments'][-1]['type']
    element = dict(source, pointers=source['pointers'] - 1, const=False, reference=0,
                   cpp=source['cpp'].removeprefix('const ').rstrip().removesuffix('*').strip())
    sequence = dict(name='QList', cpp='QList<' + element['cpp'] + '>', pointers=0,
                    reference=0, const=False, enum=False, flags=False, container=True, instantiations=[element])
    arguments = [g.type(a['type']) for a in f['arguments'][:first]] + [g.conversions.register(g.type(sequence))]
    f['rhi_pointer_array'] = True
    return arguments, [dict(type=t, source=i, input=i, output=False, mutable=False) for i, t in enumerate(arguments)], []


def owns_result(g, f):
    if f['declaring_class'] == 'QRhiGles2InitParams' and f['name'] == 'newFallbackSurface':
        return True
    if f['declaring_class'] == 'QRhi' and f['name'] == 'enumerateAdapters':
        return True  # The public API requires the caller to destroy every adapter.
    result = f['return']
    if result['pointers'] != 1:
        return False
    return ((f['declaring_class'] == 'QRhi' and f['name'] == 'create' and result['name'] == 'QRhi') or
            (resource(g, result['name']) and (f['declaring_class'] == 'QRhi' and f['name'].startswith('new') or
                                             f['name'] == 'newCompatibleRenderPassDescriptor')))


def before_call(g, m):
    f = m['function']
    owner, method = f['declaring_class'], f['name']
    if 'QRhi' not in g.ids:
        return []
    lines = dependency_before(g, m) + rhi_buffer_access.before_call(g, m)
    if owner == 'QRhi' and method in ('create', 'probe'):
        if len(m['args']) >= 2:
            variants = [('Null', 'QRhiNullInitParams'), ('OpenGLES2', 'QRhiGles2InitParams'),
                        ('D3D11', 'QRhiD3D11InitParams'),
                        ('D3D12', 'QRhiD3D12InitParams'), ('Metal', 'QRhiMetalInitParams')]
            lines += ['switch (static_cast<QRhi::Implementation>(r->arguments[0].word)) {']
            for enum, typ in variants:
                if typ in g.ids:
                    lines += [f'case QRhi::{enum}: if (!entry(r->arguments[1].word) || entry(r->arguments[1].word)->type != {g.ids[typ]}) return fail(r, EINVAL, "RHI backend and initialization parameter type differ"); break;']
            lines += ['default: return fail(r, ENOTSUP, "This RHI backend has no typed initialization adapter in this package");', '}']
    if owner == 'QRhi' and method in ('beginFrame', 'beginOffscreenFrame'):
        lines += ['if (!rhi_begin_frame_ready(r, r->self)) return true;']
        swapchain = 'a0' if method == 'beginFrame' else 'nullptr'
        lines += [f'RhiFrameStartGuard rhi_frame_start(r, self, {swapchain});']
    if owner == 'QRhi' and method in ('endFrame', 'endOffscreenFrame'):
        arguments = 'false, a0' if method == 'endFrame' else 'true'
        lines += [f'if (!rhi_end_frame_ready(r, r->self, {arguments})) return true;']
    if owner == 'QRhi' and method == 'finish':
        lines += ['if (!rhi_finish_frame_ready(r, r->self)) return true;']
    if owner == 'QRhiCommandBuffer':
        lines += ['if (!rhi_command_ready(r, r->self)) return true;']
        required = {'resourceUpdate': 0, 'beginPass': 0, 'endPass': 1,
                    'beginComputePass': 0, 'endComputePass': 2,
                    'setGraphicsPipeline': 1, 'draw': 1, 'drawIndexed': 1,
                    'drawIndirect': 1, 'drawIndexedIndirect': 1, 'setVertexInput': 1,
                    'setViewport': 1, 'setScissor': 1, 'setBlendConstants': 1,
                    'setStencilRef': 1, 'setComputePipeline': 2, 'dispatch': 2}
        required['setShaderResources'] = -1
        if method in required:
            lines += [f'if (!rhi_pass_required(r, r->self, {required[method]})) return true;']
    if owner == 'QRhi' and method in ('finish', 'endFrame', 'endOffscreenFrame'):
        lines += ['if (!rhi_pass_required(r, r->self, 0)) return true;']
    if owner != 'QRhiCommandBuffer' and resource(g, owner) and not f['const'] and not f['static']:
        lines += ['if (!rhi_mutation_ready(r, r->self)) return true;']
    if owner == 'QRhiResourceUpdateBatch':
        lines += ['if (!rhi_batch_ready(r, r->self)) return true;']
        if method in ('uploadStaticBuffer', 'updateDynamicBuffer') and m['args'] and m['args'][-1].get('name') == 'QByteArray':
            data = 'a' + str(len(m['args']) - 1)
            offset = 'uint32_t(r->arguments[1].word)' if len(m['args']) == 3 else '0u'
            lines += [f'if ({offset} > a0->size() || quint64({data}->size()) > a0->size() - {offset}) return fail(r, ERANGE, "RHI update exceeds its native buffer extent");',
                      'if (' + ('a0->type() != QRhiBuffer::Dynamic' if method == 'updateDynamicBuffer' else 'a0->type() == QRhiBuffer::Dynamic') + ') return fail(r, EINVAL, "RHI update does not match the native buffer usage");']
    for i, t in enumerate(m['args']):
        if t.get('name') == 'QRhiResourceUpdateBatch' and owner == 'QRhiCommandBuffer':
            lines += [f'if (!rhi_batch_ready(r, r->arguments[{i}].word, true)) return true;',
                      f'if (!rhi_same_domain(r, r->self, r->arguments[{i}].word)) return true;']
        elif resource(g, t.get('name', '')) and owner in ('QRhi', 'QRhiCommandBuffer', 'QRhiResourceUpdateBatch'):
            lines += [f'if (!rhi_same_domain(r, r->self, r->arguments[{i}].word)) return true;']
        if owner == 'QRhiResourceUpdateBatch' and t.get('raw') == 'U32' and t.get('kind') in ('object', 'value'):
            if method == 'merge':
                lines += [f'if (!rhi_merge_dependencies(r, r->self, r->arguments[{i}].word)) return true;']
            else:
                lines += [f'if (!rhi_retain_argument(r, r->self, r->arguments[{i}].word)) return true;']
    if ((owner == 'QRhi' and method == 'finish') or
            (owner == 'QRhiCommandBuffer' and method in ('beginPass', 'endPass', 'beginComputePass',
                                                       'endComputePass', 'beginExternal', 'endExternal'))):
        lines += ['rhi_native_records_changed(r->self);']
    return lines


def after_call(g, m):
    f = m['function']
    owner, method = f['declaring_class'], f['name']
    if 'QRhi' not in g.ids:
        return []
    lines = rhi_buffer_access.after_call(g, m)
    plan = dependencies(g, m)
    if plan:
        lines += [f'if (!rhi_dependencies.finish(r, {"r->result.word" if plan["produced"] else "0"}, true)) return true;']
    if owner == 'QRhi' and method == 'nextResourceUpdateBatch':
        lines += ['if (r->result.word && !r->error) rhi_register_batch(r, r->result.word, r->self);']
    if owner == 'QRhi' and method in ('endFrame', 'endOffscreenFrame'):
        lines += ['rhi_frame_finished(r->self);', 'schedule_collection();']
    if owner == 'QRhi' and method in ('beginFrame', 'beginOffscreenFrame'):
        swap = 'a0' if method == 'beginFrame' else 'nullptr'
        lines += [f'if (returned == QRhi::FrameOpSuccess && !r->error) {{ rhi_frame_started(r->self, {swap}); rhi_frame_start.committed = true; }}']
    if owner == 'QRhiCommandBuffer':
        for i, t in enumerate(m['args']):
            if t.get('name') == 'QRhiResourceUpdateBatch':
                lines += [f'if (r->arguments[{i}].word) {{ rhi_batch_submitted(r->arguments[{i}].word); invalidate(r->arguments[{i}].word); }}']
        if method in ('beginPass', 'beginComputePass', 'endPass', 'endComputePass'):
            phase = 1 if method == 'beginPass' else 2 if method == 'beginComputePass' else 0
            lines += [f'rhi_pass_changed(r->self, {phase});']
    if owner == 'QRhiResourceUpdateBatch' and method == 'merge':
        lines += ['rhi_batch_merged(r->arguments[0].word); rhi_readbacks_merged(r->self, r->arguments[0].word);']
    return lines


def method_case(g, m):
    f = m['function']
    if f.get('rhi_pointer_array') and len(m['args']) == len(f['arguments']) - 1:
        lines = ['NativeCallScope scope;']
        if not f['static']:
            lines += [f'auto *self = get<{f["declaring_class"]}>(r, r->self, {g.ids[f["declaring_class"]]});']
        args = []
        for index, t in enumerate(m['args']):
            declarations, expression = g.argument(t, index)
            lines += declarations; args.append(expression)
        lines += ['if (r->error) return true;'] + before_call(g, m)
        if f['declaring_class'] == 'QRhiShaderResourceBinding':
            lines += [f'if (({args[-1]}).size() < 1 || ({args[-1]}).size() > 16) return fail(r, ERANGE, "RHI texture arrays require between 1 and 16 elements");']
        data = 'constData' if f['arguments'][-1]['type']['const'] else 'data'
        values = args[:-1] + [f'int(({args[-1]}).size())', f'({args[-1]}).{data}()']
        owner = f['declaring_class'] + '::' if f['static'] else 'self->'
        lines += g.store_result(m['return'], owner + f['name'] + '(' + ', '.join(values) + ')')
        lines += after_call(g, m) + ['return true;']
        return lines
    if f['declaring_class'] == 'QRhiResource' and f['name'] == 'deleteLater':
        return ['// QRhiResource lifetime adapter', 'return rhi_delete_later(r);']
    if f['declaring_class'] == 'QRhiResourceUpdateBatch' and f['name'] == 'release':
        return ['// QRhiResourceUpdateBatch pool adapter', 'return rhi_release_batch(r);']
    return None


def emit(g):
    if 'QRhiNullInitParams' not in g.ids:
        return
    operation = g.next_id
    g.next_id += 1
    g.cases.append(f'''case {operation}: {{
    QRhiNullInitParams parameters;
    r->result.word = own(r, QRhi::create(QRhi::Null, &parameters), {g.ids['QRhi']});
    r->result.owned_handle = r->result.word;
    if (!r->result.word && !r->error) return fail(r, ENODEV, "Unable to initialize Qt RHI Null backend");
    return true;
}}''')
    g.emit_effect('QRhi.newNull', [], dict(kind='object', name='QRhi', bend='QRhi', raw='U32', owned=True), operation)
    emit_backend_creation(g)
    root = dict(kind='object', name='QRhi', bend='QRhi', raw='U32')
    import signals
    g.types['ObjectIdentity'] = 'scalar'
    g.bend += ['def ObjectIdentity.decode_word(value: Wire) -> Maybe<&2, ObjectIdentity>:',
               '  match value:', '    case WireSequence{WireScalar{word, 0} <> Nil{}}: Some{ObjectIdentity{word}}',
               '    case _: None{}', '']
    destroyed = signals.invoke_value(g, 'QRhi.Destroyed', 'ObjectIdentity', 'ObjectIdentity.decode_word')
    operation = g.next_id; g.next_id += 1
    g.cases.append(f'''case {operation}: {{
    get<QRhi>(r, r->self, {g.ids['QRhi']});
    if (r->error) return true;
    auto id = new_connection(r, r->arguments[0].word);
    if (r->error) return true;
    connection(id)->terminal = true;
    r->result.word = id;
    return true;
}}''')
    import effect_transport
    g.emit_effect('QRhi.onDestroyed', [('self', root), ('state', effect_transport.handler(destroyed, 'QRhi.Destroyed.invoke'))],
                  dict(kind='connection', bend='Connection', raw='U32'), operation, has_self=True)
    for name, result, body in [
        ('QRhi.beginOffscreen', dict(kind='object', name='QRhiCommandBuffer', bend='QRhiCommandBuffer', raw='U32'), f'''
    NativeCallScope scope;
    auto *self = get<QRhi>(r, r->self, {g.ids['QRhi']});
    if (r->error) return true;
    if (!rhi_begin_frame_ready(r, r->self)) return true;
    RhiFrameStartGuard rhi_frame_start(r, self, nullptr);
    QRhiCommandBuffer *commands = nullptr;
    auto result = self->beginOffscreenFrame(&commands);
    if (result != QRhi::FrameOpSuccess) return fail(r, EIO, "Qt RHI could not begin the offscreen frame");
    r->result.word = borrow(r, commands, {g.ids['QRhiCommandBuffer']});
    if (r->error || !r->result.word) {{
        if (!r->error) fail(r, EIO, "RHI returned no offscreen command buffer");
    }} else {{ rhi_frame_started(r->self, nullptr); rhi_frame_start.committed = true; }}
    return true;'''),
        ('QRhi.endOffscreen', dict(kind='void', bend='Unit', raw='Unit'), f'''
    NativeCallScope scope;
    auto *self = get<QRhi>(r, r->self, {g.ids['QRhi']});
    if (r->error) return true;
    auto *identity = rhi_identity(r->self);
    if (!rhi_end_frame_ready(r, r->self, true)) return true;
    rhi_end_active_pass(identity->domain);
    auto result = self->endOffscreenFrame();
    rhi_frame_finished(r->self); schedule_collection();
    if (result != QRhi::FrameOpSuccess) return fail(r, EIO, "Qt RHI could not submit the offscreen frame");
    return true;''')]:
        operation = g.next_id
        g.next_id += 1
        g.cases.append(f'case {operation}: {{\n{body}\n}}')
        g.emit_effect(name, [('self', root)], result, operation, has_self=True)
    g.bend += ['def QRhi.withOffscreenFrame(-A: Type, +self: QRhi, body: QRhiCommandBuffer -> Action(A)) -> Action(A):',
               '  Action.bind(QRhiCommandBuffer, A, QRhi.beginOffscreen(self),',
               '    commands => Action.finally(A, body(commands), QRhi.endOffscreen(self)))', '']
    if 'QRhiReadbackResult' in g.ids:
        batch = dict(kind='object', name='QRhiResourceUpdateBatch', bend='QRhiResourceUpdateBatch', raw='U32')
        import signals
        import effect_transport
        payload = g.rhi_readback_payload
        readback = signals.invoke_value(g, 'QRhiReadbackResult.Ready', payload['bend'], payload['codec'] + '.decode')
        ready = effect_transport.handler(readback, 'QRhiReadbackResult.Ready.invoke')
        for public, parameters, body in [
            ('QRhiResourceUpdateBatch.readBackBufferAsync', [('buffer', dict(bend='QRhiBuffer', raw='U32')),
                                                          ('offset', dict(bend='U32', raw='U32')), ('size', dict(bend='U32', raw='U32'))],
             f'''NativeCallScope scope;
    auto *batch = get<QRhiResourceUpdateBatch>(r, r->self, {g.ids['QRhiResourceUpdateBatch']});
    auto *buffer = get<QRhiBuffer>(r, r->arguments[0].word, {g.ids['QRhiBuffer']}, false, false);
    if (r->error || !rhi_batch_ready(r, r->self) || !rhi_same_domain(r, r->self, r->arguments[0].word)) return true;
    if (!rhi_buffer_batch_access(r, r->arguments[0].word)) return true;
    uint32_t offset = r->arguments[1].word, size = r->arguments[2].word;
    if (offset > buffer->size() || size > buffer->size() - offset) return fail(r, ERANGE, "RHI buffer readback exceeds its native extent");
    if (!rhi_retain_argument(r, r->self, r->arguments[0].word)) return true;
    auto state = rhi_new_readback(r, r->self);
    if (!state) return true;
    try {{ batch->readBackBuffer(buffer, offset, size, &state->result); }}
    catch (...) {{ rhi_cancel_readback(state); throw; }}
    return true;'''),
            ('QRhiResourceUpdateBatch.readBackTextureAsync', [('description', dict(bend='QRhiReadbackDescription', raw='U32'))],
             f'''NativeCallScope scope;
    auto *batch = get<QRhiResourceUpdateBatch>(r, r->self, {g.ids['QRhiResourceUpdateBatch']});
    auto *description = get<QRhiReadbackDescription>(r, r->arguments[0].word, {g.ids['QRhiReadbackDescription']}, false, false);
    if (r->error || !rhi_batch_ready(r, r->self)) return true;
    if (!rhi_retain_argument(r, r->self, r->arguments[0].word)) return true;
    auto state = rhi_new_readback(r, r->self);
    if (!state) return true;
    try {{ batch->readBackTexture(*description, &state->result); }}
    catch (...) {{ rhi_cancel_readback(state); throw; }}
    return true;''')]:
            operation = g.next_id
            g.next_id += 1
            g.cases.append(f'case {operation}: {{\n    {body}\n}}')
            handler_slot = len(parameters)
            body_lines = body.replace('rhi_new_readback(r, r->self)', f'rhi_new_readback(r, r->self, r->arguments[{handler_slot}].word)')
            g.cases[-1] = f'case {operation}: {{\n    {body_lines}\n}}'
            g.emit_effect(public, [('self', batch), *parameters, ('state', ready)],
                          dict(kind='void', bend='Unit', raw='Unit'), operation, has_self=True)


def emit_backend_creation(g):
    """Discover parameter subclasses, preserving their dynamic native layout."""
    for name in g.selected:
        if name == 'QRhiInitParams' or 'QRhiInitParams' not in g.all_bases(name):
            continue
        backend = name.removeprefix('QRhi').removesuffix('InitParams')
        implementation = {'Gles2': 'OpenGLES2'}.get(backend, backend)
        if implementation not in ('Null', 'OpenGLES2', 'D3D11', 'D3D12', 'Metal'):
            continue
        parameters = dict(kind='value', name=name, bend=name, raw='U32')
        flags = dict(kind='flags', bend='QRhi.Flag', raw='U32')
        variants = [('createWith' + backend, [('parameters', parameters), ('flags', flags)], False, False, False),
                    ('probeWith' + backend, [('parameters', parameters)], True, False, False)]
        handles = 'QRhi' + backend + 'NativeHandles'
        if handles in g.ids:
            variants.append(('createWith' + backend + 'Imported', [('parameters', parameters), ('flags', flags),
                ('device', dict(kind='value', name=handles, bend=handles, raw='U32'))], False, True, False))
        if 'QRhiAdapter' in g.ids:
            variants.append(('createWith' + backend + 'Adapter', [('parameters', parameters), ('flags', flags),
                ('adapter', dict(kind='object', name='QRhiAdapter', bend='QRhiAdapter', raw='U32'))], False, False, True))
        for method, arguments, probe, imported, adapter in variants:
            lines = ['NativeCallScope scope;', f'auto *parameters = get<{name}>(r, r->arguments[0].word, {g.ids[name]}, false, false);',
                     'if (r->error) return true;']
            if backend == 'Gles2':
                lines += ['if (!parameters->fallbackSurface) return fail(r, EINVAL, "OpenGL RHI requires a live fallback surface");']
            if imported:
                lines += [f'auto *device = get<{handles}>(r, r->arguments[2].word, {g.ids[handles]}, false, false);',
                          'if (r->error) return true;']
                if backend == 'Gles2':
                    lines += ['if (!device->context || !device->context->isValid()) return fail(r, EINVAL, "Imported OpenGL RHI requires a valid context");']
            if adapter:
                lines += [f'auto *adapter = get<QRhiAdapter>(r, r->arguments[2].word, {g.ids["QRhiAdapter"]}, false, false);',
                          'if (r->error) return true;']
            if probe:
                lines += [f'r->result.word = QRhi::probe(QRhi::{implementation}, parameters);']
                result = dict(kind='bool', bend='Bool', raw='U32')
            else:
                lines += ['RetentionBatch dependencies;',
                          'for (const auto &edge : retentions) if (edge.target && (edge.owner == r->arguments[0].word' +
                          (' || edge.owner == r->arguments[2].word' if imported else '') + '))',
                          '    if (!dependencies.add(r, 0, 0xb1000003u, edge.target, nullptr, false, true, edge.target)) return true;']
                if adapter:
                    lines += ['if (!dependencies.add(r, 0, 0xb1000003u, r->arguments[2].word, nullptr, false, true, r->arguments[2].word)) return true;']
                lines += [f'auto *value = QRhi::create(QRhi::{implementation}, parameters, QRhi::Flags(r->arguments[1].word), ' +
                          ('device' if imported else 'nullptr') + (', adapter' if adapter else '') + ');',
                          'if (!value) return fail(r, ENODEV, "Qt could not initialize the requested RHI backend");',
                          f'r->result.word = own(r, value, {g.ids["QRhi"]});',
                          'r->result.owned_handle = r->result.word;',
                          'if (!r->error && !dependencies.finish(r, r->result.word, true)) return true;']
                result = dict(kind='object', name='QRhi', bend='QRhi', raw='U32', owned=True)
            operation = g.next_id; g.next_id += 1
            g.cases.append(f'case {operation}: {{\n' + '\n'.join('    ' + line for line in lines) + '\n    return true;\n}')
            g.emit_effect('QRhi.' + method, arguments, result, operation)
        if hasattr(g, 'rhi_adapter_list'):
            operation = g.next_id; g.next_id += 1
            lines = ['NativeCallScope scope;', f'auto *parameters = get<{name}>(r, r->arguments[0].word, {g.ids[name]}, false, false);',
                     'if (r->error) return true;']
            if backend == 'Gles2':
                lines += ['if (!parameters->fallbackSurface) return fail(r, EINVAL, "OpenGL RHI requires a fallback surface");']
            import rhi_native_handles
            lines += rhi_native_handles.enumerate_lines(g, f'QRhi::enumerateAdapters(QRhi::{implementation}, parameters)')
            g.cases.append(f'case {operation}: {{\n' + '\n'.join('    ' + line for line in lines) + '\n    return true;\n}')
            g.emit_effect('QRhi.enumerateWith' + backend, [('parameters', parameters)], g.rhi_adapter_list, operation)
        if handles in g.ids:
            operation = g.next_id; g.next_id += 1
            g.cases.append(f'''case {operation}: {{
    NativeCallScope scope;
    auto *self = get<QRhi>(r, r->self, {g.ids['QRhi']}, false, false);
    if (r->error) return true;
    if (self->backend() != QRhi::{implementation}) return fail(r, EINVAL, "RHI native handle type does not match the initialized backend");
    auto *native = static_cast<const {handles} *>(self->nativeHandles());
    if (!native) return fail(r, ENOTSUP, "This RHI backend exposes no native handle record");
    RetentionBatch dependencies;
    if (!dependencies.add(r, 0, 0xb1000003u, r->self, nullptr, false, true)) return true;
    {{ NativeAggregateInputScope native_fields(r); // Qt-owned objects such as the GL context.
    r->result.word = own(r, new {handles}(*native), {g.ids[handles]}); }}
    r->result.owned_handle = r->result.word;
    if (!r->error && !dependencies.finish(r, r->result.word, true)) return true;
    return true;
}}''')
            g.emit_effect('QRhi.native' + backend + 'Handles', [('self', dict(bend='QRhi', raw='U32'))],
                          dict(kind='value', name=handles, bend=handles, raw='U32'), operation, has_self=True)


def annotate(g):
    methods = {(m['function']['declaring_class'], m['function']['name']): m['bend_name'] for m in g.methods
               if any(t.get('name') == 'QByteArray' for t in m['args'])}
    for excluded in g.excluded:
        if not excluded['class'].startswith('QRhi'):
            continue
        for f in g.inherited(excluded['class']):
            if f['signature'] != excluded['signature']:
                continue
            owner, name = f['declaring_class'], f['name']
            choices = []
            if owner == 'QRhi' and name in ('create', 'probe', 'enumerateAdapters'):
                for cls in g.selected:
                    if cls != 'QRhiInitParams' and 'QRhiInitParams' in g.all_bases(cls):
                        backend = cls.removeprefix('QRhi').removesuffix('InitParams')
                        if backend not in ('Null', 'Gles2', 'D3D11', 'D3D12', 'Metal'): continue
                        public = 'QRhi.' + ('enumerate' if name == 'enumerateAdapters' else name) + 'With' + backend
                        choices.append((public, 'Preserves the backend-specific native init structure; resources referenced by parameters remain retained'))
                        if name == 'create' and 'QRhi' + backend + 'NativeHandles' in g.ids:
                            choices.append((public + 'Imported', 'Typed native device import with retained backing objects'))
                        if name == 'create' and 'QRhiAdapter' in g.ids:
                            choices.append((public + 'Adapter', 'Typed init structure and retained native adapter; cannot combine adapter and imported device'))
            elif owner == 'QRhiResourceUpdateBatch' and name in ('readBackBuffer', 'readBackTexture'):
                choices.append((owner + '.' + name + 'Async', 'Returns a cancellable typed signal with an independent completed result snapshot; native callback storage survives submission'))
            elif owner.startswith('QRhi') and (owner, name) in methods:
                choices.append((methods[(owner, name)], 'Copies bounded QByteArray storage; byte count is inferred from its native extent'))
            for public, reason in choices:
                item = dict(bend_name=public, contract='typed_rhi_adapter', native_signature=f['minimal_signature'], reason=reason)
                if item not in excluded.setdefault('alternatives', []): excluded['alternatives'].append(item)


def cpp(g):
    if 'QRhi' not in g.ids:
        return '''static bool attach_rhi_identity(BqtRequest *, uint32_t) { return true; }
static void rhi_forget(uint32_t) {}
static bool rhi_release_ready(uint32_t) { return true; }
static bool rhi_destroy_root(BqtRequest *) { return false; }
static bool rhi_cleanup_operation(BqtRequest *, uint32_t) { return true; }
static void rhi_shutdown() {}
static bool rhi_validate_dependencies(BqtRequest *, uint32_t) { return true; }
static bool borrow_rhi_identity(BqtRequest *, void *, uint16_t, void *(*)(void *, uint16_t), void (*)(void *), uint32_t *) { return false; }
'''
    source = (Path(__file__).parent / 'templates/rhi_lifetimes.cpp').read_text()
    source += rhi_buffer_access.cpp(g)
    source += (Path(__file__).parent / 'templates/rhi_readbacks.cpp').read_text()

    source = source.replace('@RHI_VALUE_TYPES@', ' '.join('case ' + str(g.ids[name]) + ':' for name in g.selected if name.startswith('QRhi')))
    for name in ('QRhi', 'QRhiResource', 'QRhiResourceUpdateBatch', 'QRhiCommandBuffer', 'QRhiReadbackResult'):
        source = source.replace('@' + name.upper() + '_ID@', str(g.ids[name]))
    return '#if BQT_HAS_RHI\n' + source + '\n#else\n' + cpp(type('Empty', (), {'ids': {}})()) + '#endif\n'
