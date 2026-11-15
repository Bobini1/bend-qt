"""Checked native RHI records and bounded direct dynamic-buffer updates."""
from pathlib import Path


def full_update(f):
    return f['declaring_class'] == 'QRhiBuffer' and f['name'] == 'fullDynamicBufferUpdateForCurrentFrame'


def parameters(g, f):
    if not full_update(f):
        return None
    byte = dict(kind='value', name='QByteArray', cpp='QByteArray', bend='QByteArray', raw='U32', pointer=False)
    args = [byte, g.type(f['arguments'][1]['type'])]
    return args, [dict(type=t, source=i, input=i, output=False, mutable=False) for i, t in enumerate(args)], []


def method_case(g, m):
    if not full_update(m['function']):
        return None
    return ['NativeCallScope scope;', f'auto *self = get<QRhiBuffer>(r, r->self, {g.ids["QRhiBuffer"]});',
        f'auto *bytes = get<QByteArray>(r, r->arguments[0].word, {g.ids["QByteArray"]}, false, false);',
        'if (r->error) return true;', 'return rhi_full_buffer_update(r, self, *bytes, r->arguments[1].word);']


def before_call(g, m):
    f = m['function']
    if f['name'] in ('create', 'destroy') and m['class'].startswith('QRhi'):
        lines = ['if (rhi_record_borrowed(r->self)) return fail(r, EBUSY, "A native RHI record retains this resource allocation");']
        if f['name'] == 'destroy':
            lines += ['rhi_buffer_clear(r->self);']
        return lines
    if m['function']['declaring_class'] == 'QRhiResourceUpdateBatch' and m['function']['name'] in ('updateDynamicBuffer', 'uploadStaticBuffer'):
        return ['if (!rhi_buffer_batch_access(r, r->arguments[0].word)) return true;']
    return []


def after_call(g, m):
    f = m['function']
    if f['declaring_class'] != 'QRhiBuffer':
        return []
    if f['name'] == 'create':
        return ['rhi_buffer_allocation(r->self, self, returned);']
    if f['name'] == 'destroy':
        return ['rhi_buffer_allocation(r->self, self, false);']
    return []


def backends(g):
    for name in g.selected:
        if name != 'QRhiInitParams' and 'QRhiInitParams' in g.all_bases(name):
            backend = name.removeprefix('QRhi').removesuffix('InitParams')
            enum = 'OpenGLES2' if backend == 'Gles2' else backend
            if enum in ('Null', 'OpenGLES2', 'D3D11', 'D3D12', 'Metal'):
                yield name, backend, enum


def enumerate_lines(g, expression):
    child = g.rhi_adapter_list['children'][0]
    return [f'auto native_adapters = {expression};',
        'auto adapter_cleanup = qScopeGuard([&] { qDeleteAll(native_adapters); });',
        'r->result = sequence_value(size_t(native_adapters.size()));',
        'for (qsizetype i = 0; i < native_adapters.size() && !r->error; ++i) {',
        '    auto *adapter = native_adapters[i]; native_adapters[i] = nullptr;',
        f'    r->result.items[i] = write_{child["native_codec"]}(r, adapter);', '}']


def emit(g):
    if 'QRhi' not in g.ids:
        return
    g.rhi_native_alternatives = {}
    def emit_one(owner, name, arguments, result, lines, native_name=None):
        operation = g.next_id; g.next_id += 1
        g.cases.append(f'case {operation}: {{\n' + '\n'.join('    ' + line for line in lines) + '\n    return true;\n}')
        g.emit_effect(owner + '.' + name, arguments, result, operation, has_self=bool(arguments and arguments[0][0] == 'self'))
        if native_name:
            g.rhi_native_alternatives.setdefault((owner, native_name), []).append(owner + '.' + name)
    for params, backend, enum in backends(g):
        record = 'QRhi' + backend + 'NativeHandles'
        if record in g.ids and hasattr(g, 'rhi_adapter_list'):
            lines = ['NativeCallScope scope;',
                f'auto *parameters = get<{params}>(r, r->arguments[0].word, {g.ids[params]}, false, false);',
                f'auto *device = get<{record}>(r, r->arguments[1].word, {g.ids[record]}, false, false);',
                'if (r->error) return true;']
            if backend == 'Gles2':
                lines += ['if (!parameters->fallbackSurface) return fail(r, EINVAL, "OpenGL RHI requires a fallback surface");']
            lines += enumerate_lines(g, f'QRhi::enumerateAdapters(QRhi::{enum}, parameters, device)')
            emit_one('QRhi', 'enumerateWith' + backend + 'Imported',
                [('parameters', dict(bend=params, raw='U32')), ('device', dict(bend=record, raw='U32'))],
                g.rhi_adapter_list, lines, 'enumerateAdapters')
        for owner, suffix in (('QRhiCommandBuffer', 'CommandBufferNativeHandles'), ('QRhiRenderPassDescriptor', 'RenderPassNativeHandles')):
            record = 'QRhi' + backend + suffix
            if record not in g.ids:
                continue
            frame = owner == 'QRhiCommandBuffer'
            lines = ['NativeCallScope scope;', f'auto *self = get<{owner}>(r, r->self, {g.ids[owner]}, false, false);',
                'if (r->error) return true;',
                f'if (self->rhi()->backend() != QRhi::{enum}) return fail(r, EINVAL, "Native RHI record has the wrong backend");']
            if frame:
                lines += ['if (!rhi_command_ready(r, r->self)) return true;']
            lines += [f'auto *native = static_cast<const {record} *>(self->nativeHandles());',
                'if (!native) return fail(r, ENOTSUP, "This backend exposes no native record in the current state");',
                'RetentionBatch dependencies;', 'if (!dependencies.add(r, 0, 0xb1000004u, r->self, nullptr, false, true)) return true;',
                '{ NativeAggregateInputScope native_fields(r); // Qt-owned objects in the record.',
                f'r->result.word = own(r, new {record}(*native), {g.ids[record]}); }}',
                'r->result.owned_handle = r->result.word;',
                'if (!r->error && !dependencies.finish(r, r->result.word, true)) return true;',
                f'if (!r->error) rhi_record_origin(r, r->result.word, r->self, {str(frame).lower()});']
            emit_one(owner, 'native' + backend + 'Handles', [('self', dict(bend=owner, raw='U32'))],
                dict(kind='value', name=record, bend=record, raw='U32'), lines, 'nativeHandles')
    for owner in ('QRhi', 'QRhiCommandBuffer', 'QRhiRenderPassDescriptor'):
        if owner not in g.ids:
            continue
        lines = ['NativeCallScope scope;', f'auto *self = get<{owner}>(r, r->self, {g.ids[owner]}, false, false);', 'if (r->error) return true;']
        if owner == 'QRhiCommandBuffer':
            lines += ['if (!rhi_command_ready(r, r->self)) return true;']
        lines += ['r->result.word = self->nativeHandles() != nullptr;']
        emit_one(owner, 'hasNativeHandles', [('self', dict(bend=owner, raw='U32'))],
            dict(kind='bool', bend='Bool', raw='U32'), lines, 'nativeHandles')
    if 'QRhiNativeHandles' in g.ids:
        emit_one('QRhi', 'setQueueSubmitParams',
            [('self', dict(bend='QRhi', raw='U32')),
             ('parameters', dict(bend='QRhiNativeHandles', raw='U32'))],
            dict(kind='void', bend='Unit', raw='Unit'), [
                'NativeCallScope scope;',
                f'auto *self = get<QRhi>(r, r->self, {g.ids["QRhi"]});',
                f'auto *parameters = get<QRhiNativeHandles>(r, r->arguments[0].word, {g.ids["QRhiNativeHandles"]}, false, false);',
                'if (r->error) return true;',
                'if (parameters && self->backend() != QRhi::Null && self->backend() != QRhi::OpenGLES2)',
                '    return fail(r, ENOTSUP, "This backend requires a queue-submit parameter type outside the selected PySide binding scope");',
                # nullptr is a native no-op, including Vulkan. A generic
                # record cannot supply a backend semaphore structure.
                'self->setQueueSubmitParams(parameters);',
            ], 'setQueueSubmitParams')


def annotate(g):
    for excluded in g.excluded:
        owner = excluded['class']
        if not owner.startswith('QRhi'):
            continue
        for f in g.inherited(owner):
            if f['signature'] != excluded['signature']:
                continue
            names = list(getattr(g, 'rhi_native_alternatives', {}).get((owner, f['name']), []))
            if f['name'] == 'nativeHandles':
                names.append(owner + '.hasNativeHandles')
                for _, backend, _ in backends(g):
                    suffix = {'QRhi': 'NativeHandles', 'QRhiCommandBuffer': 'CommandBufferNativeHandles', 'QRhiRenderPassDescriptor': 'RenderPassNativeHandles'}.get(owner)
                    if suffix and 'QRhi' + backend + suffix in g.ids:
                        names.append(owner + '.native' + backend + 'Handles')
            for name in sorted(set(names)):
                item = dict(bend_name=name, contract='typed_native_record', reason='Availability is explicit; concrete records preserve backend layout and native origin lifetime.')
                if f['name'] == 'setQueueSubmitParams':
                    item.update(contract='checked_queue_submit_parameters',
                        reason='Null follows the native no-op; non-null base records are accepted for Null/OpenGLES2. Vulkan semaphore parameter records are outside the pinned PySide scope.')
                if item not in excluded.setdefault('alternatives', []): excluded['alternatives'].append(item)


def limitations(g):
    if 'QRhi' not in g.ids:
        return []
    return [dict(owner='QRhi', signature='setQueueSubmitParams(QRhiNativeHandles*)',
                 behavior='Null follows the native no-op; non-null records are supported for Null/OpenGLES2 only',
                 reason='The functional Vulkan semaphore payload QRhiVulkanQueueSubmitParams is not present in the pinned PySide type system; native Vulkan expansion is outside this package scope',
                 alternatives=[dict(bend_name='QRhi.setQueueSubmitParams', contract='checked_queue_submit_parameters')])]


def cpp(g):
    if 'QRhi' not in g.ids:
        return ''
    return '#if BQT_HAS_RHI\n' + (Path(__file__).parent / 'templates/rhi_native_handles.cpp').read_text() + '\n#endif\n'
