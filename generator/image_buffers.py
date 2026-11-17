"""Stable aligned buffers for QImage's retained native pixel constructors.

Qt owns a shared storage lease through its documented cleanup callback. Image
copies and detachment therefore preserve native alias semantics without a
registry callback from a foreign thread.
"""


def handles(f):
    return (f['declaring_class'] == 'QImage' and f['constructor'] and f['arguments']
            and f['arguments'][0]['type']['name'] in ('uchar', 'unsigned char')
            and f['arguments'][0]['type']['pointers'] == 1)


def public_name(f):
    if not handles(f):
        return None
    return ('fromReadOnlyBuffer' if f['arguments'][0]['type']['const'] else 'fromBuffer') + ('WithStride' if len(f['arguments']) == 7 else '')


def install(classes, selected):
    classes['ImageBuffer'] = dict(name='ImageBuffer', object=False, value=True, qobject=False,
        public_destructor=True, abstract=False, copyable=False, namespace=False,
        generate=False, template=False, bases=[], functions=[], enums=[], adapter=True)
    selected.append('ImageBuffer')


def parameters(g, f):
    if not handles(f):
        return None
    args = [dict(kind='value', name='ImageBuffer', cpp='ImageBuffer', bend='ImageBuffer', raw='U32')]
    args += [g.type(a['type']) for a in f['arguments'][1:-2]]
    return args, [dict(type=t, source=i, input=i, output=False, mutable=False) for i, t in enumerate(args)], []


def method_case(g, m):
    f = m['function']
    if not handles(f):
        return None
    stride = 'int64_t(wide_bits(r->arguments[3]))' if len(m['args']) == 5 else '0'
    readonly = str(f['arguments'][0]['type']['const']).lower()
    fmt = len(m['args']) - 1
    return ['NativeCallScope scope;',
        f'auto *buffer = get<ImageBuffer>(r, r->arguments[0].word, {g.ids["ImageBuffer"]}, false, false);',
        'if (r->error) return true;',
        f'auto image = image_from_buffer(r, *buffer, int32_t(r->arguments[1].word), int32_t(r->arguments[2].word), {stride}, int32_t(r->arguments[{fmt}].word), {readonly});',
        'if (r->error) return true;',
        f'r->result.word = own(r, new QImage(std::move(image)), {g.ids["QImage"]});',
        'r->result.owned_handle = r->result.word;', 'return true;']


def emit(g):
    handle = dict(kind='value', name='ImageBuffer', bend='ImageBuffer', raw='U32')
    bytes_type = dict(kind='value', name='QByteArray', bend='QByteArray', raw='U32')
    view_type = dict(kind='value', name='MemoryView', bend='MemoryView', raw='U32')
    size_type = dict(kind='u64', name='quint64', bend='UInt64', raw='U32 & U32')
    for name in ('new', 'fromBytes', 'bytes', 'size'):
        op = g.next_id; g.next_id += 1
        lines = ['NativeCallScope scope;']
        if name in ('new', 'fromBytes'):
            params = [('size', size_type)] if name == 'new' else [('bytes', bytes_type)]
            if name == 'new':
                lines += ['uint64_t count = wide_bits(r->arguments[0]);']
            else:
                lines += [f'auto *source = get<QByteArray>(r, r->arguments[0].word, {g.ids["QByteArray"]}, false, false);',
                          'if (r->error) return true;', 'uint64_t count = uint64_t(source->size());']
            lines += ['if (!count) return fail(r, EINVAL, "Image buffer must contain at least one byte");',
                      'if (count > uint64_t(PTRDIFF_MAX) - 7) return fail(r, EOVERFLOW, "Image buffer exceeds native addressable storage");',
                      'auto buffer = std::make_unique<ImageBuffer>();', 'buffer->size = size_t(count);',
                      'buffer->storage = std::make_shared<std::vector<uint64_t>>((size_t(count) + 7) / 8);']
            if name == 'fromBytes':
                lines += ['if (count) std::memcpy(buffer->storage->data(), source->constData(), size_t(count));']
            lines += [f'r->result.word = own(r, buffer.release(), {g.ids["ImageBuffer"]});',
                      'r->result.owned_handle = r->result.word;']
            result, has_self = handle, False
        else:
            params, has_self = [('self', handle)], True
            lines += [f'auto *self = get<ImageBuffer>(r, r->self, {g.ids["ImageBuffer"]}, false, false);',
                      'if (r->error) return true;']
            if name == 'size':
                result = size_type
                lines += ['r->result = wide_value(self->size);']
            else:
                result = view_type
                lines += ['MemoryView view{r->self, self->storage->data(), self->size, 0, false, nullptr};',
                          'view.observe = [](BqtRequest *check, const MemoryView &view, bool) {',
                          f'    auto *source = get<ImageBuffer>(check, view.owner, {g.ids["ImageBuffer"]}, false, false);',
                          '    return source && view.address == source->storage->data() && view.size == source->size;', '};',
                          f'r->result.word = register_memory_view(r, view, {g.ids["MemoryView"]});',
                          'r->result.owned_handle = r->result.word;']
        g.cases.append(f'case {op}: {{\n' + '\n'.join('    ' + line for line in lines + ['return true;']) + '\n}')
        g.emit_effect('ImageBuffer.' + name, params, result, op, has_self=has_self)


def cpp(g):
    if 'QImage' not in g.ids:
        return ''
    return '''
static void release_image_buffer(void *data) noexcept {
    delete static_cast<std::shared_ptr<std::vector<uint64_t>> *>(data);
}
static QImage image_from_buffer(BqtRequest *r, const ImageBuffer &source,
        int width, int height, int64_t stride, int format, bool readonly) {
    if (width <= 0 || height <= 0 || format <= QImage::Format_Invalid || format >= QImage::NImageFormats) {
        fail(r, EINVAL, "Image dimensions and format must describe a valid image"); return {};
    }
    const auto native_format = QImage::Format(format);
    const uint64_t depth = QImage::toPixelFormat(native_format).bitsPerPixel();
    if (!depth) { fail(r, EINVAL, "Image format has no public pixel extent"); return {}; }
    const uint64_t row = (uint64_t(width) * depth + 7) / 8;
    const uint64_t aligned = (row + 3) & ~uint64_t(3);
    if (stride < 0 || (stride && uint64_t(stride) < row)) {
        fail(r, ERANGE, "Image stride is smaller than one pixel row"); return {};
    }
    const uint64_t pitch = stride ? uint64_t(stride) : aligned;
    if (pitch > uint64_t(PTRDIFF_MAX) / uint64_t(height) || pitch * uint64_t(height) > source.size) {
        fail(r, ERANGE, "Image pixel extent exceeds its backing buffer"); return {};
    }
    // QImage may hand scanlines to 32/64-bit native pixel operations. Keep each
    // line aligned even when the explicit stride overload would accept less.
    const uint64_t alignment = depth >= 64 ? alignof(uint64_t) : alignof(uint32_t);
    if (pitch % alignment) { fail(r, EINVAL, "Image scanline stride is not naturally aligned"); return {}; }
    auto lease = std::make_unique<std::shared_ptr<std::vector<uint64_t>>>(source.storage);
    auto *data = reinterpret_cast<uchar *>(source.storage->data());
    QImage image = readonly
        ? QImage(static_cast<const uchar *>(data), width, height, qsizetype(pitch), native_format, release_image_buffer, lease.get())
        : QImage(data, width, height, qsizetype(pitch), native_format, release_image_buffer, lease.get());
    // On null construction Qt never installed the cleanup function.
    if (image.isNull()) { fail(r, ENOMEM, "Qt could not create the image buffer view"); return {}; }
    lease.release();
    return image;
}
'''
