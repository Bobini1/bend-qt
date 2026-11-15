"""Checked byte views over Qt storage with an observable owner and extent.

Views retain the owner, revalidate its current storage before every access, and
never expose an integer address to Bend. Native mappings without a non-mutating
liveness check require a separate adapter.
"""
from pathlib import Path


def install(classes, selected):
    classes['MemoryView'] = dict(name='MemoryView', object=False, value=True,
        qobject=False, public_destructor=True, abstract=False, copyable=True,
        namespace=False, generate=False, template=False, bases=[], functions=[],
        enums=[], adapter=True)
    if 'MemoryView' not in selected:
        selected.append('MemoryView')


def restores_method(function):
    return (function['declaring_class'] == 'QRhiBuffer' and function['name'] == 'beginFullDynamicBufferUpdateForCurrentFrame' or
            function['declaring_class'] == 'QByteArray' and function['name'] in ('constData', 'operator const char*', 'operator const void*'))


def adapt(g, f):
    owner, name = f['declaring_class'], f['name']
    t = f['return']
    if t['pointers'] != 1:
        return None
    if owner == 'QFileDevice' and name == 'map':
        return dict(kind='value', name='MemoryView', cpp='MemoryView', bend='MemoryView',
                    raw='U32', file_mapping=True)
    if owner == 'QOpenGLBuffer' and name in ('map', 'mapRange'):
        return dict(kind='value', name='MemoryView', cpp='MemoryView', bend='MemoryView',
                    raw='U32', gl_mapping=True)
    if owner == 'QRhiBuffer' and name == 'beginFullDynamicBufferUpdateForCurrentFrame':
        return dict(kind='value', name='MemoryView', cpp='MemoryView', bend='MemoryView', raw='U32', rhi_mapping=True)
    policy = None
    if owner == 'QSGMaterialShader::RenderState' and name == 'uniformData':
        policy = dict(owner=owner, plane=False, render=True,
                      size='source->uniformData() ? source->uniformData()->size() : 0',
                      read='source->uniformData() ? source->uniformData()->constData() : nullptr',
                      write='source->uniformData() ? source->uniformData()->data() : nullptr',
                      valid='source->uniformData() != nullptr',
                      pointer_expression='({value}) ? ({value})->data() : nullptr')
    if owner == 'QByteArray' and name in ('data', 'constData', 'operator const char*', 'operator const void*'):
        policy = dict(owner=owner, plane=False, size='source->size()',
                      read='source->constData()', write='source->data()', valid='true')
    elif owner == 'QPicture' and name == 'data':
        policy = dict(owner=owner, plane=False, size='source->size()',
                      read='source->data()', write='source->data()', valid='true')
    elif owner == 'QBitArray' and name == 'bits':
        policy = dict(owner=owner, plane=False, size='source->size() / 8 + (source->size() % 8 != 0)',
                      read='source->bits()', write='source->bits()', valid='true')
    elif owner == 'QResource' and name == 'data':
        policy = dict(owner=owner, plane=False, size='source->size()',
                      read='source->data()', write='source->data()', valid='source->isValid()')
    elif owner == 'QQmlFile' and name == 'data':
        policy = dict(owner=owner, plane=False, size='source->size()',
                      read='source->data()', write='source->data()', valid='source->isReady()')
    elif owner == 'QSharedMemory' and name in ('data', 'constData'):
        policy = dict(owner=owner, plane=False, size='source->size()',
                      read='source->constData()', write='source->data()', valid='source->isAttached()',
                      writable='entry(view.owner)->shared_memory_writable')
    elif owner == 'QImage' and name in ('bits', 'constBits', 'scanLine', 'constScanLine'):
        plane = name in ('scanLine', 'constScanLine')
        policy = dict(owner=owner, plane=plane, size='source->bytesPerLine()' if plane else 'source->sizeInBytes()',
                      read='source->constScanLine(view.auxiliary)' if plane else 'source->constBits()',
                      write='source->scanLine(view.auxiliary)' if plane else 'source->bits()',
                      valid='view.auxiliary >= 0 && view.auxiliary < source->height()' if plane else 'true')
    elif owner == 'QVideoFrame' and name == 'bits':
        policy = dict(owner=owner, plane=True, size='source->mappedBytes(view.auxiliary)',
                      read='static_cast<const QVideoFrame *>(source)->bits(view.auxiliary)',
                      write='source->bits(view.auxiliary)',
                      valid='source->isMapped() && view.auxiliary >= 0 && view.auxiliary < source->planeCount()',
                      writable='source->isWritable()')
    elif owner == 'QSGGeometry' and (name.startswith('vertexData') or name.startswith('indexData')):
        vertex = name.startswith('vertexData')
        count, size = ('vertexCount()', 'sizeOfVertex()') if vertex else ('indexCount()', 'sizeOfIndex()')
        member = 'vertexData()' if vertex else 'indexData()'
        policy = dict(owner=owner, plane=False, render=True,
                      size=f'qsizetype(source->{count}) * qsizetype(source->{size})',
                      read=f'static_cast<const QSGGeometry *>(source)->{member}',
                      write=f'source->{member}', valid='true')
    if policy is None:
        return None
    policy['readonly'] = bool(t['const'] or f['const'] or name.startswith('const'))
    return dict(kind='value', name='MemoryView', cpp='MemoryView', bend='MemoryView',
                raw='U32', memory_view=policy)


def before_call(g, method):
    function = method['function']
    if function['declaring_class'] == 'QOpenGLBuffer' and function['name'] in ('allocate', 'write', 'read', 'native_destroy', 'destroy', 'operator=', 'swap'):
        lines = ['if (!guard_gl_mapping_mutation(r, self)) return true;']
        if function['name'] == 'swap' and method['args']:
            lines += ['if (!guard_gl_mapping_mutation(r, a0)) return true;']
        return lines
    if function['declaring_class'] == 'QSharedMemory' and function['name'] in ('detach', 'setKey', 'setNativeKey'):
        return shared_mutation_guard(g)
    if (not function['static'] and not function['constructor'] and
            function['name'] in ('open', 'resize', 'setFileName', 'rename', 'remove', 'commit', 'cancelWriting') and
            function['declaring_class'] in ('QFile', 'QFileDevice', 'QTemporaryFile', 'QSaveFile', 'QIODevice')):
        return ['if (entry(r->self)->file_mappings) return fail(r, EBUSY, "Release file mappings before changing the file storage");']
    t = method.get('native_return', method['return'])
    policy = t.get('memory_view')
    if not policy:
        return []
    lines = []
    if policy['plane']:
        bound = 'self->height()' if policy['owner'] == 'QImage' else 'self->planeCount()'
        lines += [f'if (int32_t(r->arguments[0].word) < 0 || int32_t(r->arguments[0].word) >= {bound})',
                  '    return fail(r, ERANGE, "Qt storage plane or scanline is outside its bounds");']
    if policy['owner'] == 'QVideoFrame':
        lines += ['if (!self->isMapped()) return fail(r, EPERM, "Map the video frame before accessing its bytes");']
    return lines


def parameters(g, function):
    if function['declaring_class'] == 'QFileDevice' and function['name'] == 'unmap':
        t = dict(kind='value', name='MemoryView', cpp='MemoryView', bend='MemoryView', raw='U32')
        return [t], [dict(type=t, source=0, input=0, output=False, mutable=False)], []
    return None


def method_case(g, method):
    f = method['function']
    import rhi_buffer_access
    adapted = rhi_buffer_access.method_case(g, method)
    if adapted is not None:
        return adapted
    if f['declaring_class'] == 'QOpenGLBuffer' and f['name'] in ('map', 'mapRange', 'unmap'):
        return gl_method_case(g, method)
    if f['declaring_class'] == 'QSharedMemory' and f['name'] in ('create', 'attach'):
        lines = ['NativeCallScope scope;',
                 f'auto *self = get<QSharedMemory>(r, r->self, {g.ids["QSharedMemory"]});',
                 'if (r->error) return true;'] + shared_mutation_guard(g)
        arguments = []
        for i, t in enumerate(method['args']):
            declarations, expression = g.argument(t, i)
            lines += declarations
            arguments.append(expression)
        mode = arguments[-1] if len(arguments) == len(f['arguments']) else 'QSharedMemory::ReadWrite'
        lines += ['if (r->error) return true;', f'bool success = self->{f["name"]}({", ".join(arguments)});',
                  f'if (success) entry(r->self)->shared_memory_writable = ({mode}) == QSharedMemory::ReadWrite;',
                  'r->result.word = success;', 'return true;']
        return lines
    if f['declaring_class'] != 'QFileDevice' or f['name'] not in ('map', 'unmap'):
        return None
    lines = ['NativeCallScope scope;',
             f'auto *self = get<QFileDevice>(r, r->self, {g.ids["QFileDevice"]});',
             'if (r->error) return true;']
    if f['name'] == 'unmap':
        return lines + [f'auto *view = get<MemoryView>(r, r->arguments[0].word, {g.ids["MemoryView"]});',
            'if (r->error) return true;',
            'if (!view->mapping || view->owner != r->self) return fail(r, EINVAL, "This view is not a mapping of this file");',
            'if (!view->mapping->active) return fail(r, ESTALE, "File mapping has already been unmapped");',
            'bool unmapped = self->unmap(view->mapping->address);',
            'if (unmapped) view->mapping->active = false;', 'r->result.word = unmapped;', 'return true;']
    # Allocate cleanup before mapping. Allocation or registry failure cannot
    # leak a mapping, and any copied views share exactly one cleanup record.
    flags = 'QFileDevice::MemoryMapFlags(int(r->arguments[2].word))' if len(method['args']) > 2 else 'QFileDevice::NoOptions'
    return lines + [
        'qint64 offset = int64_t(wide_bits(r->arguments[0]));',
        'qint64 size = int64_t(wide_bits(r->arguments[1]));',
        f'auto flags = {flags};',
        'qint64 extent = self->size();',
        'if (offset < 0 || size <= 0 || offset > extent || size > extent - offset) return fail(r, ERANGE, "File mapping exceeds file size");',
        'if (!self->isReadable()) return fail(r, EPERM, "File mapping requires a readable open file");',
        'auto state = std::make_shared<NativeFileMapping>(r->self, self, offset);',
        'state->address = self->map(offset, size, flags);', 'state->active = state->address != nullptr;',
        'MemoryView view{r->self, state->address, size_t(size), 0,',
        '    !self->isWritable() && !(flags & QFileDevice::MapPrivateOption), nullptr, state};',
        'view.observe = [](BqtRequest *check, const MemoryView &view, bool) {',
        f'    auto *file = get<QFileDevice>(check, view.owner, {g.ids["QFileDevice"]}, false, false);',
        '    if (check->error) return false;',
        '    if (!view.mapping->active || !view.mapping->file || view.mapping->file != file) {',
        '        fail(check, ESTALE, "File mapping is no longer available"); return false;', '    }',
        '    auto extent = file->size();',
        '    if (extent < view.mapping->offset || uint64_t(extent - view.mapping->offset) < view.size) {',
        '        fail(check, ESTALE, "Mapped file was truncated"); return false;', '    }',
        '    return true;', '};',
        f'r->result.word = register_memory_view(r, view, {g.ids["MemoryView"]});',
        'r->result.owned_handle = r->result.word;', 'return true;']


def shared_mutation_guard(g):
    return ['for (const auto &candidate : entries)',
            f'    if (candidate.value && candidate.type == {g.ids["MemoryView"]} && static_cast<const MemoryView *>(candidate.value)->owner == r->self)',
            '        return fail(r, EBUSY, "Release shared-memory views before changing the attachment");']


def store(g, t, value):
    p = t.get('memory_view')
    if not p:
        return None
    readonly = str(p['readonly']).lower()
    writable = p.get('writable', 'true')
    initial_writable = writable.replace('view.owner', 'r->self')
    auxiliary = 'int32_t(r->arguments[0].word)' if p['plane'] else '0'
    prefix = ['if (!gui_render_depth) { fail(check, EPERM, "Scene graph storage requires a render callback"); return false; }'] if p.get('render') else []
    value = p.get('pointer_expression', '{value}').replace('{value}', value)
    return [
        f'auto *source = self;',
        f'MemoryView view{{r->self, const_cast<void *>(static_cast<const void *>({value})), 0, {auxiliary}, {readonly} || !({initial_writable}), nullptr}};',
        f'auto extent = {p["size"]};',
        'if (extent < 0) return fail(r, ERANGE, "Qt storage reports a negative extent");',
        'view.size = size_t(extent);',
        'view.observe = [](BqtRequest *check, const MemoryView &view, bool writing) {',
        *['    ' + line for line in prefix],
        f'    auto *source = get<{p["owner"]}>(check, view.owner, {g.ids[p["owner"]]}, false, writing);',
        '    if (check->error) return false;',
        f'    if (!({p["valid"]})) {{ fail(check, ESTALE, "Qt storage is no longer available"); return false; }}',
        f'    if (writing && !({writable})) {{ fail(check, EPERM, "Qt storage is read only"); return false; }}',
        f'    const void *current = writing ? static_cast<const void *>({p["write"]}) : static_cast<const void *>({p["read"]});',
        f'    auto extent = {p["size"]};',
        '    if (extent < 0 || current != view.address || size_t(extent) != view.size) {',
        '        fail(check, ESTALE, "Qt storage changed since this view was acquired"); return false;',
        '    }',
        '    return true;',
        '};',
        f'r->result.word = register_memory_view(r, view, {g.ids["MemoryView"]});',
        'r->result.owned_handle = r->result.word;',
    ]


def emit(g):
    unit = dict(kind='void', bend='Unit', raw='Unit')
    wide = dict(kind='u64', bend='UInt64', raw='U32 & U32')
    boolean = dict(kind='bool', bend='Bool', raw='U32')
    handle = dict(kind='value', name='MemoryView', bend='MemoryView', raw='U32')
    array = dict(kind='value', name='QByteArray', bend='QByteArray', raw='U32')

    def effect(name, args, result, body):
        operation = g.next_id
        g.next_id += 1
        lines = ['NativeCallScope scope;',
                 f'auto *view = get<MemoryView>(r, r->self, {g.ids["MemoryView"]}, false, false);',
                 'if (r->error) return true;'] + body + ['return true;']
        g.cases.append(f'case {operation}: {{\n' + '\n'.join('    ' + line for line in lines) + '\n}')
        g.emit_effect('MemoryView.' + name, [('self', handle)] + args, result, operation, has_self=True)

    effect('size', [], wide, ['if (!view->observe(r, *view, false)) return true;', 'r->result = wide_value(view->size);'])
    effect('isReadOnly', [], boolean, ['r->result.word = view->readonly;'])
    effect('read', [('offset', wide), ('count', wide)], array,
           ['if (!view->readable) return fail(r, EPERM, "Memory view is write only");',
            'if (!view->observe(r, *view, false)) return true;',
            'auto offset = wide_bits(r->arguments[0]), count = wide_bits(r->arguments[1]);',
            'if (offset > view->size || count > view->size - offset || count > uint64_t(std::numeric_limits<qsizetype>::max()))',
            '    return fail(r, ERANGE, "Memory view read exceeds its extent");',
            'auto *start = count ? static_cast<const char *>(view->address) + size_t(offset) : nullptr;',
            f'r->result.word = own(r, new QByteArray(start, qsizetype(count)), {g.ids["QByteArray"]});'])
    effect('write', [('offset', wide), ('bytes', array)], unit,
           ['if (view->readonly) return fail(r, EPERM, "Memory view is read only");',
            'if (!view->observe(r, *view, true)) return true;',
            f'auto *bytes = get<QByteArray>(r, r->arguments[1].word, {g.ids["QByteArray"]}, false, false);',
            'if (r->error) return true;',
            'auto offset = wide_bits(r->arguments[0]);',
            'if (offset > view->size || size_t(bytes->size()) > view->size - offset)',
            '    return fail(r, ERANGE, "Memory view write exceeds its extent");',
            'if (!bytes->isEmpty()) std::memmove(static_cast<char *>(view->address) + size_t(offset), bytes->constData(), size_t(bytes->size()));',
            'flush_memory_mapping(*view, offset, size_t(bytes->size()));'])


def gl_method_case(g, m):
    f = m['function']
    lines = ['NativeCallScope call_scope;',
             f'auto *self = get<QOpenGLBuffer>(r, r->self, {g.ids["QOpenGLBuffer"]});',
             'if (r->error || !check_gl_mapping_context(r)) return true;',
             'if (!self->isCreated()) return fail(r, EINVAL, "Create the OpenGL buffer before mapping it");',
             'GLBufferBinding binding(self->type(), self->bufferId());']
    if f['name'] == 'unmap':
        return lines + ['GLint mapped = 0;', 'binding.functions->glGetBufferParameteriv(binding.target, GL_BUFFER_MAPPED, &mapped);',
                        'if (!mapped) return fail(r, ESTALE, "OpenGL buffer is not mapped");',
                        'bool success = self->unmap();', 'retire_gl_mappings(self->bufferId());',
                        'r->result.word = success;', 'return true;']
    lines += ['GLint already_mapped = 0;',
              'binding.functions->glGetBufferParameteriv(binding.target, GL_BUFFER_MAPPED, &already_mapped);',
              'if (already_mapped) return fail(r, EBUSY, "OpenGL buffer is already mapped");',
              'retire_gl_mappings(self->bufferId());', 'int extent = self->size();']
    if f['name'] == 'map':
        access = g.argument(m['args'][0], 0)[1]
        lines += [f'auto access = {access};',
                  'if (access != QOpenGLBuffer::ReadOnly && access != QOpenGLBuffer::WriteOnly && access != QOpenGLBuffer::ReadWrite)',
                  '    return fail(r, EINVAL, "Invalid OpenGL mapping access");',
                  'int offset = 0, count = extent;',
                  'bool readable = access != QOpenGLBuffer::WriteOnly, writable = access != QOpenGLBuffer::ReadOnly;',
                  'bool explicit_flush = false;']
        expression = 'self->map(access)'
    else:
        args = [g.argument(t, i)[1] for i, t in enumerate(m['args'])]
        lines += [f'int offset = {args[0]}, count = {args[1]};', f'auto access = {args[2]};',
                  'unsigned flags = unsigned(access);',
                  'bool readable = flags & QOpenGLBuffer::RangeRead, writable = flags & QOpenGLBuffer::RangeWrite;',
                  'bool explicit_flush = flags & QOpenGLBuffer::RangeFlushExplicit;',
                  'if ((flags & ~63u) || !(readable || writable) || (explicit_flush && !writable) ||',
                  '        (readable && (flags & (QOpenGLBuffer::RangeInvalidate | QOpenGLBuffer::RangeInvalidateBuffer | QOpenGLBuffer::RangeUnsynchronized))))',
                  '    return fail(r, EINVAL, "Invalid OpenGL range mapping access");']
        expression = 'self->mapRange(offset, count, access)'
    lines += ['if (offset < 0 || count <= 0 || offset > extent || count > extent - offset)',
              '    return fail(r, ERANGE, "OpenGL mapping exceeds the buffer extent");',
              'auto state = std::make_shared<NativeGLMapping>(*self);',
              f'state->address = {expression};', 'state->active = state->address != nullptr;',
              'state->explicit_flush = explicit_flush;',
              'MemoryView view{r->self, state->address, size_t(count), 0, !writable, observe_gl_mapping, {}, state, readable};',
              f'r->result.word = register_memory_view(r, view, {g.ids["MemoryView"]});',
              'if (auto *registered = entry(r->result.word)) registered->graphics_context = entry(r->self)->graphics_context;',
              'r->result.owned_handle = r->result.word;', 'return true;']
    return lines


def cpp(g):
    if 'QOpenGLBuffer' not in g.ids:
        import gl_raw_mappings
        return gl_raw_mappings.raw_only_memory_cpp(g)
    return (Path(__file__).parent / 'templates/gl_mappings.cpp').read_text().replace('@MEMORY_VIEW@', str(g.ids['MemoryView']))
