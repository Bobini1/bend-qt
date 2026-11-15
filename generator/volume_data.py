"""Owning list snapshots and checked image planes for QCustom3DVolume."""


def handles(f):
    if f['declaring_class'] != 'QCustom3DVolume':
        return False
    return (f['name'] in ('textureData', 'createTextureData', 'textureDataChanged') or
            (f['constructor'] and len(f['arguments']) > 1) or
            f['name'] == 'setSubTextureData' or
            (f['name'] == 'setTextureData' and any(a['type']['pointers'] for a in f['arguments'])))


def byte_list(g):
    child = g.conversions.register(dict(kind='u32', bend='U32', raw='U32', cpp='uchar'))
    return g.conversions.register(dict(kind='list', name='QList', cpp='QList<uchar>',
        children=[child], bend='List<&2, U32>', raw='Wire', codec='List_U32'))


def adapt(g, f):
    if handles(f) and f['name'] in ('textureData', 'createTextureData'):
        return byte_list(g)
    return None


def parameters(g, f):
    if not handles(f):
        return None
    args = []
    for a in f['arguments']:
        t = a['type']
        if t['name'] in ('QList', 'QVector') and t['pointers']:
            value = dict(byte_list(g), native_copy_adoption=True,
                         pointer_container_snapshot=f['signal'], pointer_snapshot_provenance='QCustom3DVolume::textureDataChanged copied on emission')
        elif f['name'] == 'createTextureData':
            image = g.conversions.register(dict(kind='value', name='QImage', cpp='QImage', bend='QImage', raw='U32'))
            value = g.conversions.register(dict(kind='list', name='QList', cpp='QList<QImage>',
                children=[image], bend='List<&2, QImage>', raw='Wire', codec='List_QImage'))
        elif t['pointers'] and t['name'] in ('uchar', 'unsigned char'):
            value = dict(kind='value', name='QByteArray', cpp='QByteArray', bend='QByteArray', raw='U32', pointer=False)
        else:
            value = g.type(t)
        args.append(value)
    return args, [dict(type=t, source=i, input=i, output=False, mutable=False) for i, t in enumerate(args)], []


def method_case(g, m):
    f = m['function']
    if not handles(f):
        return None
    if f['signal']:
        return None  # signals.connect_case, with signal_arguments below.
    lines = ['NativeCallScope scope;']
    if not f['constructor']:
        lines += [f'auto *self = get<QCustom3DVolume>(r, r->self, {g.ids["QCustom3DVolume"]}, false, {str(not f["const"]).lower()});']
    arguments = []
    for i, t in enumerate(m['args']):
        before, value = g.argument(t, i)
        lines += before
        arguments.append(value)
        if t.get('native_copy_adoption'):
            lines += [f'for (size_t i = 0; i < r->arguments[{i}].count; ++i)',
                      f'    if (r->arguments[{i}].items[i].word > 255) return fail(r, ERANGE, "Volume byte list has an out-of-range value");']
    lines += ['if (r->error) return true;']
    if f['constructor']:
        for expression in m.get('omitted_defaults', []):
            arguments.append(expression)
        data = arguments[6]
        lines += [f'if (!volume_data_extent(r, {arguments[3]}, {arguments[4]}, {arguments[5]}, {arguments[7]}, ({data}).size())) return true;',
                  f'auto data = std::make_unique<QList<uchar>>({data});']
        arguments[6] = 'nullptr'
        lines += [f'auto value = std::make_unique<QCustom3DVolume>(' + ', '.join(arguments) + ');',
                  'value->setTextureData(data.release());',
                  f'r->result.word = own(r, value.release(), {g.ids["QCustom3DVolume"]});',
                  'r->result.owned_handle = r->result.word;']
    elif f['name'] == 'setTextureData':
        lines += [f'if (!volume_data_extent(r, self->textureWidth(), self->textureHeight(), self->textureDepth(), self->textureFormat(), ({arguments[0]}).size())) return true;',
                  f'auto data = std::make_unique<QList<uchar>>({arguments[0]});',
                  'self->setTextureData(data.release());']
    elif f['name'] == 'setSubTextureData':
        if m['args'][2]['name'] == 'QImage':
            lines += [f'auto axis = {arguments[0]};',
                      'const auto size = axis == Qt::XAxis ? QSize(self->textureDepth(), self->textureHeight()) :',
                      '    axis == Qt::YAxis ? QSize(self->textureWidth(), self->textureDepth()) : QSize(self->textureWidth(), self->textureHeight());',
                      'if (a2->isNull() || a2->size() != size || (self->textureFormat() == QImage::Format_Indexed8 && a2->format() != QImage::Format_Indexed8))',
                      '    return fail(r, EINVAL, "Volume slice image has incompatible dimensions or format");',
                      'auto image = a2->convertToFormat(self->textureFormat());',
                      'if (image.isNull()) return fail(r, ENOMEM, "Volume slice image conversion failed");',
                      f'if (!volume_slice_extent(r, self, axis, {arguments[1]}, image.sizeInBytes())) return true;',
                      f'self->setSubTextureData(axis, {arguments[1]}, image);']
        else:
            lines += [f'if (!volume_slice_extent(r, self, {arguments[0]}, {arguments[1]}, a2->size())) return true;',
                      f'self->setSubTextureData({arguments[0]}, {arguments[1]}, reinterpret_cast<const uchar *>(a2->constData()));']
    elif f['name'] == 'createTextureData':
        lines += ['QList<QImage *> images;', 'images.reserve(a0->size());',
                  'if (a0->size() > INT_MAX) return fail(r, ERANGE, "Volume has too many image planes");',
                  'const auto size = a0->isEmpty() ? QSize(0, 0) : a0->first().size();',
                  'for (auto &image : *a0) {',
                  '    if (image.size() != size || image.isNull()) return fail(r, EINVAL, "Volume image planes must have identical nonempty dimensions");',
                  '    image = image.copy();',
                  '    if (image.isNull()) return fail(r, ENOMEM, "Volume image copy allocation failed");',
                  '    images.append(&image);', '}',
                  'if (!volume_data_extent(r, size.width(), size.height(), int(images.size()), QImage::Format_ARGB32, std::numeric_limits<qsizetype>::max())) return true;',
                  'const auto *data = self->createTextureData(images);',
                  f'r->result = write_{byte_list(g)["native_codec"]}(r, data ? *data : QList<uchar>{{}});']
    else:
        lines += ['const auto *data = self->textureData();',
                  f'r->result = write_{byte_list(g)["native_codec"]}(r, data ? *data : QList<uchar>{{}});']
    return lines + ['return true;']


def signal_arguments(g, f):
    """textureDataChanged passes a pointer Qt owns: the handler gets a copy."""
    if not (handles(f) and f['signal']):
        return None
    return [dict(byte_list(g), signal_expression='{a} ? *{a} : QList<uchar>{{}}')]


def override_before(g, f, inputs, expressions):
    """Prepare native-owned storage without handing it to a throwing constructor."""
    if f['declaring_class'] != 'QCustom3DVolume' or not f['constructor'] or len(inputs) <= 6:
        return []
    source = expressions[6]
    lines = ['for (size_t i = 0; i < r->arguments[7].count; ++i)',
             '    if (r->arguments[7].items[i].word > 255) return fail(r, ERANGE, "Volume byte list has an out-of-range value");',
             f'if (!volume_data_extent(r, {expressions[3]}, {expressions[4]}, {expressions[5]}, {expressions[7]}, ({source}).size())) return true;',
             f'auto copied_volume_data = std::make_unique<QList<uchar>>({source});']
    expressions[6] = 'nullptr'
    return lines


def override_after(f, inputs):
    if f['declaring_class'] == 'QCustom3DVolume' and f['constructor'] and len(inputs) > 6:
        return ['value->setTextureData(copied_volume_data.release());']
    return []


def cpp(g):
    if 'QCustom3DVolume' not in g.ids:
        return ''
    return '''
static bool volume_data_extent(BqtRequest *r, int width, int height, int depth, QImage::Format format, qsizetype count) {
    if (width < 0 || height < 0 || depth < 0 || (format != QImage::Format_ARGB32 && format != QImage::Format_Indexed8))
        return fail(r, EINVAL, "Invalid volume dimensions or texture format"), false;
    const uint64_t bytes = format == QImage::Format_Indexed8 ? 1 : 4;
    const uint64_t row = (uint64_t(width) * bytes + 3) & ~uint64_t(3);
    // Qt's slice implementation multiplies these dimensions using signed int.
    if (row > INT_MAX || (height && row > uint64_t(INT_MAX) / uint64_t(height)) ||
        (depth && row * uint64_t(height) > uint64_t(INT_MAX) / uint64_t(depth)))
        return fail(r, ERANGE, "Volume dimensions exceed native slice arithmetic"), false;
    if (count < 0 || row * uint64_t(height) * uint64_t(depth) > uint64_t(count))
        return fail(r, ERANGE, "Volume texture data is smaller than its dimensions"), false;
    return true;
}
static bool volume_slice_extent(BqtRequest *r, QCustom3DVolume *value, Qt::Axis axis, int index, qsizetype count) {
    const auto *data = value->textureData();
    const int width = value->textureWidth(), height = value->textureHeight(), depth = value->textureDepth();
    if (!data || !volume_data_extent(r, width, height, depth, value->textureFormat(), data->size())) {
        if (!r->error) fail(r, EINVAL, "Volume has no texture storage");
        return false;
    }
    if (axis != Qt::XAxis && axis != Qt::YAxis && axis != Qt::ZAxis)
        return fail(r, EINVAL, "Invalid volume slice axis"), false;
    const int bound = axis == Qt::XAxis ? width : axis == Qt::YAxis ? height : depth;
    if (index < 0 || index >= bound) return fail(r, ERANGE, "Volume slice index exceeds its axis"), false;
    const uint64_t pixel = value->textureFormat() == QImage::Format_Indexed8 ? 1 : 4;
    const uint64_t row = (uint64_t(width) * pixel + 3) & ~uint64_t(3);
    const uint64_t required = axis == Qt::XAxis ? uint64_t(depth) * uint64_t(height) * pixel :
        row * uint64_t(axis == Qt::YAxis ? depth : height);
    if (count < 0 || required > uint64_t(count)) return fail(r, ERANGE, "Volume slice data is truncated"), false;
    return true;
}
'''
