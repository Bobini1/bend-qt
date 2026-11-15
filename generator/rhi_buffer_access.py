"""Counted vertex bindings and scoped write-only dynamic buffer mappings."""
from pathlib import Path


def method_case(g, m):
    f = m['function']
    if f['declaring_class'] != 'QRhiBuffer' or f['name'] not in (
            'beginFullDynamicBufferUpdateForCurrentFrame', 'endFullDynamicBufferUpdateForCurrentFrame'):
        return None
    lines = ['NativeCallScope scope;', f'auto *self = get<QRhiBuffer>(r, r->self, {g.ids["QRhiBuffer"]});',
             'if (r->error) return true;']
    if f['name'].startswith('end'):
        return lines + ['return rhi_end_buffer_mapping(r, r->self);']
    return lines + ['auto mapping = rhi_begin_buffer_mapping(r, r->self, self);',
        'if (r->error) return true;',
        'MemoryView view{r->self, mapping->address, mapping->size, 0, false, observe_rhi_mapping};',
        'view.readable = false; view.rhi_mapping = mapping;',
        f'r->result.word = register_memory_view(r, view, {g.ids["MemoryView"]});',
        'r->result.owned_handle = r->result.word;', 'return true;']


def before_call(g, m):
    f = m['function']; owner, name = f['declaring_class'], f['name']
    lines = []
    if ((owner == 'QRhi' and name in ('endFrame', 'endOffscreenFrame', 'finish')) or
            (owner == 'QRhiCommandBuffer' and name in ('beginPass', 'beginComputePass', 'beginExternal'))):
        lines += ['if (!rhi_mappings_closed(r, r->self)) return true;']
    if owner != 'QRhiCommandBuffer' or name != 'setVertexInput' or len(m['args']) < 3 or not m['args'][2].get('buffer'):
        return lines
    lines += ['if (int32_t(r->arguments[0].word) < 0 || int32_t(r->arguments[1].word) < 0 ||',
              '    uint64_t(r->arguments[0].word) + uint64_t(r->arguments[1].word) > uint64_t(std::numeric_limits<int>::max()))',
              '    return fail(r, ERANGE, "Vertex binding range is outside the native integer range");',
              '// RHI resources already defer release while their native frame is recording.',
              '// A command-buffer -> resource -> root edge would cycle through the root-owned command buffer.',
              'for (size_t i = 0; i < size_t(r->arguments[1].word); ++i) {',
              '    auto &binding = (*a2)[i];',
              '    const auto id = r->arguments[2].items[i].items[0].word;',
              '    if (!binding.first || !(binding.first->usage() & QRhiBuffer::VertexBuffer)) return fail(r, EINVAL, "Vertex binding requires a vertex buffer");',
              '    if (binding.second > binding.first->size()) return fail(r, ERANGE, "Vertex offset exceeds its buffer");',
              '    if (!rhi_same_domain(r, r->self, id)) return true;',
              '}']
    if len(m['args']) > 3:
        lines += ['if (a3) {',
                  '    if (!(a3->usage() & QRhiBuffer::IndexBuffer)) return fail(r, EINVAL, "Index binding requires an index buffer");',
                  '    if (!rhi_same_domain(r, r->self, r->arguments[3].word)) return true;',
                  '}']
        if len(m['args']) > 4:
            lines += ['if (a3 && r->arguments[4].word > a3->size()) return fail(r, ERANGE, "Index offset exceeds its buffer");']
    return lines


def after_call(g, m):
    return []


def cpp(g):
    source = (Path(__file__).parent / 'templates/rhi_buffer_access.cpp').read_text()
    return source.replace('@QRHIBUFFER_ID@', str(g.ids['QRhiBuffer']))
