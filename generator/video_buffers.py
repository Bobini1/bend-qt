"""Stable plane storage, mapping epochs and consuming custom video buffers."""
from pathlib import Path

MAP = 'QAbstractVideoBuffer::MapData'
BUFFER = 'QAbstractVideoBuffer'


def available(g):
    return all(n in g.ids for n in (MAP, BUFFER, 'QVideoFrame', 'QVideoFrameFormat'))


def planes_type(g, setter):
    name = 'ImageBuffer' if setter else 'MemoryView'
    child = g.conversions.register(dict(kind='value', name=name, cpp=name, bend=name, raw='U32'))
    optional = g.conversions.register(dict(kind='optional', name='std::optional',
        children=[child], cpp=f'std::optional<{name}>', bend=f'Maybe<&2, {name}>', raw='Wire'))
    return g.conversions.register(dict(kind='list', name='QList', children=[optional],
        cpp=f'QList<std::optional<{name}>>', bend=f'List<&2, Maybe<&2, {name}>>', raw='Wire'))


def field_type(g, name, field, setter):
    if name == MAP and field['name'] == 'data': return planes_type(g, setter)
    return None


def field_access(g, field, expression, argument=None):
    if field['class'] != MAP: return None
    if field['field'] == 'data':
        if field['setter']:
            return [f'if (!set_video_planes(r, r->self, {argument})) return true;']
        return ['r->result = video_planes(r, r->self);']
    if field['setter']:
        key = field['field']
        if key == 'planeCount':
            return [f'if (!set_video_plane_count(r, r->self, {argument})) return true;']
        if key in ('dataSize', 'bytesPerLine'):
            return [f'if (!set_video_plane_sizes(r, r->self, {argument}, {str(key == "bytesPerLine").lower()})) return true;']
    return None


def before_call(g, m):
    f = m['function']; owner, name = f['declaring_class'], f['name']
    if owner == MAP:
        if not (f['constructor'] or f['static'] or f['const']):
            result = ['if (!video_record_mutable(r, r->self)) return true;']
        else: result = []
        if m['args'] and m['args'][0].get('name') == MAP:
            result += ['call_scope.value_origin = r->arguments[0].word;']
        return result
    if owner == BUFFER and name in ('map', 'unmap'):
        return ['if (!video_buffer_observed(r, r->self)) return true;',
                'if (!entry(r->self)->owned) return fail(r, EPERM, "Map and unmap an adopted custom buffer through its QVideoFrame");',
                'if (video_mapping_in_progress(r->self)) return fail(r, EBUSY, "Custom video map callback is active");',
                'call_scope.value_origin = r->self;']
    if owner == 'QVideoFrame' and name in ('map', 'unmap', 'toImage', 'paint'):
        return ['if (video_map_invocation) return fail(r, EBUSY, "Reentrant frame mapping during a custom map callback can lock the shared native frame");']
    return []


def after_call(g, m):
    f=m['function']
    if f['declaring_class'] == MAP and not (f['constructor'] or f['static'] or f['const']):
        return ['if (!finish_video_ownership(r, r->self)) return true;']
    return []


def callback_entry(f):
    if f['declaring_class'] != BUFFER: return []
    if f['name'] == 'unmap': return [
        '        if (video_mapping_in_progress(bqt_receiver)) { callback_report_error(EBUSY); return; }',
        '        retire_video_mapping(bqt_receiver);']
    return []


def proxy_members(c):
    if any(m['function']['declaring_class'] == BUFFER for m in c['virtuals']):
        return ['    std::shared_ptr<std::atomic<uint64_t>> bqt_video_epoch = std::make_shared<std::atomic<uint64_t>>(0);']
    return []


def callback_before_thread(f):
    if f['declaring_class'] == BUFFER and f['name'] == 'unmap':
        return ['        if (QThread::currentThread() != main_thread)',
                '            video_unmap_from_thread(bqt_receiver, bqt_video_epoch);']
    return []


def callback_setup(f, fallback):
    if f['declaring_class'] == BUFFER and f['name'] == 'map':
        return ['        VideoMapInvocation video_mapping(&conversion, bqt_receiver, a0, bqt_video_epoch);',
                '        if (conversion.error) { callback_report_error(conversion.error); ' + fallback + ' }']
    return []


def callback_decode(f):
    if f['declaring_class'] != BUFFER: return []
    if f['name'] == 'map':
        return ['            if (!publish_video_mapping(r, wire.word, *value)) return false;']
    if f['name'] == 'format':
        return ['            if (!remember_video_format(r, *value)) return false;']
    return []


def emit(g):
    if not available(g): return
    op=g.next_id; g.next_id+=1
    buffer=dict(kind='object',name=BUFFER,bend=BUFFER,raw='U32')
    frame=dict(kind='value',name='QVideoFrame',bend='QVideoFrame',raw='U32')
    lines=['NativeCallScope call_scope;',
        f'auto *source = get<QAbstractVideoBuffer>(r, r->arguments[0].word, {g.ids[BUFFER]}, false, true);',
        'if (r->error) return true;',
        'r->result = consume_video_buffer(r, r->arguments[0].word, source);', 'return true;']
    g.cases.append(f'case {op}: {{\n'+'\n'.join(lines)+'\n}')
    g.emit_effect('QVideoFrame.fromVideoBuffer',[('buffer',buffer)],frame,op)


def cpp(g):
    if not available(g):
        return 'static void video_buffers_forget(uint32_t) {}\nstatic uint32_t finish_video_ownership(BqtRequest *, uint32_t id) { return id; }\n'
    text=(Path(__file__).parent/'templates/video_buffers.cpp').read_text()
    for tag,name in [('MAP',MAP),('BUFFER',BUFFER),('FRAME','QVideoFrame'),('VIEW','MemoryView')]:
        text=text.replace('@'+tag+'@',str(g.ids[name]))
    return text


def inventory(g):
    if not available(g): return {}
    return dict(factory=dict(bend_name='QVideoFrame.fromVideoBuffer',
        native_signature='QVideoFrame(std::unique_ptr<QAbstractVideoBuffer>)',
        source=dict(qt_version='6.12.0', path='qtmultimedia/src/multimedia/video/qvideoframe.h', line=55,
            url='https://raw.githubusercontent.com/qt/qtmultimedia/v6.12.0/src/multimedia/video/qvideoframe.h'),
        ownership='Consumes an exclusively owned observed custom buffer; Qt shared frame copies release it after the last native owner'),
        plane_fields=dict(getter='QAbstractVideoBuffer.MapData.Fields.data',
            setter='QAbstractVideoBuffer.MapData.Fields.set_data', count=4,
            input='List<Maybe<ImageBuffer>> with independently shared stable backing',
            output='List<Maybe<MemoryView>> with native mode and mapping-epoch checks'),
        copy_policy='Owning MapData copies share stable backing and mapping expiry; unmap or actual native buffer destruction expires every mapped copy',
        direct_mapping='Only observed independently owned custom buffers; adopted buffers map through QVideoFrame to preserve its native mapped state',
        limits=['Unobserved native MapData pointers require an established mapping origin and are rejected',
                'CPU plane storage cannot represent opaque GPU sampler formats; ordinary mapped RGB/YUV and compressed JPEG storage remain available'],
        native_integration_required=True)
