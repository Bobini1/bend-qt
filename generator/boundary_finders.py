"""Owned text and optional working storage for QTextBoundaryFinder views."""

ORIGIN_TYPES = {'QTextBoundaryFinder'}


def handles(f):
    return (f['declaring_class'] == 'QTextBoundaryFinder' and f['constructor']
            and ((len(f['arguments']) == 4 and f['arguments'][1]['type']['name'] == 'QStringView')
                 or (len(f['arguments']) == 5 and f['arguments'][1]['type']['name'] == 'QChar'
                     and f['arguments'][1]['type']['pointers'] == 1)))


def parameters(g, f):
    if not handles(f):
        return None
    args = [g.type(f['arguments'][0]['type']), dict(kind='string', bend='String', raw='String')]
    if len(f['arguments']) == 5:
        args.append(g.type(f['arguments'][2]['type']))
    args.append(dict(kind='u64', bend='UInt64', raw='U32 & U32'))
    return args, [dict(type=t, source=i, input=i, output=False, mutable=False) for i, t in enumerate(args)], []


def method_case(g, m):
    if not handles(m['function']):
        return None
    raw = len(m['function']['arguments']) == 5
    size_index = 3 if raw else 2
    size = f'wide_bits(r->arguments[{size_index}])' if len(m['args']) > size_index else '0'
    lines = ['NativeCallScope scope;', f'uint64_t size = {size};',
        'if (size > uint64_t(PTRDIFF_MAX) - 7) return fail(r, EOVERFLOW, "Boundary working storage exceeds native limits");',
        'auto backing = std::make_shared<BoundaryFinderBacking>();',
        'backing->text = QString::fromUtf8(r->arguments[1].text, qsizetype(r->arguments[1].size));']
    if raw:
        lines += ['const int64_t length = int64_t(wide_bits(r->arguments[2]));',
                  'if (!lifetime_paired_array[(unsigned(length >= 0) * 2 + unsigned(uint64_t(length) <= uint64_t(backing->text.size()))) * 2 + 1])',
                  '    return fail(r, ERANGE, "Boundary text length exceeds its UTF-16 storage");']
    text = 'backing->text.constData(), qsizetype(length)' if raw else 'QStringView(backing->text)'
    return lines + ['backing->scratch.resize((size_t(size) + 7) / 8);',
        'auto hold = std::make_unique<BoundaryFinderBackingPtr>(backing);',
        f'auto finder = std::make_unique<QTextBoundaryFinder>(QTextBoundaryFinder::BoundaryType(r->arguments[0].word), {text}, reinterpret_cast<uchar *>(backing->scratch.data()), qsizetype(size));',
        f'r->result.word = own(r, finder.release(), {g.ids["QTextBoundaryFinder"]});',
        'r->result.owned_handle = r->result.word;',
        'if (r->result.word) boundary_finder_backings[r->result.word & 65535u] = hold.release();', 'return true;']


def before_call(g, m):
    f = m['function']
    if f['declaring_class'] == 'QTextBoundaryFinder' and m['args'] and m['args'][0].get('name') == 'QTextBoundaryFinder':
        if f['constructor'] or f['name'] == 'operator=':
            lines = ['call_scope.value_origin = r->arguments[0].word;']
            if f['name'] == 'operator=':
                lines += ['auto boundary_backing_update = copy_boundary_backing(r->arguments[0].word);']
            return lines
    return []


def after_native(g, m):
    f = m['function']
    if f['declaring_class'] != 'QTextBoundaryFinder':
        return []
    if f['name'] == 'swap':
        return ['std::swap(boundary_finder_backings[r->self & 65535u], boundary_finder_backings[r->arguments[0].word & 65535u]);',
                'swap_variant_origins(r->self, r->arguments[0].word);']
    if f['name'] == 'operator=' and m['args'] and m['args'][0].get('name') == 'QTextBoundaryFinder':
        return ['boundary_finder_forget(r->self);',
                'boundary_finder_backings[r->self & 65535u] = boundary_backing_update.release();',
                'clear_variant_origin(r->self);',
                'if (!preserve_variant_origin(r, r->self, r->arguments[0].word)) {',
                '    auto *e = entry(r->self); auto *value = e->value; auto destroy = e->destroy;',
                '    invalidate(r->self); destroy(value); return true;', '}']
    return []


def cpp(g):
    return f'''
struct BoundaryFinderBacking {{ QString text; std::vector<uint64_t> scratch; }};
using BoundaryFinderBackingPtr = std::shared_ptr<BoundaryFinderBacking>;
static SlotTable<BoundaryFinderBackingPtr *> boundary_finder_backings;
static bool has_boundary_backing(uint32_t id) {{
    return entry(id) && boundary_finder_backings[id & 65535u];
}}
static void boundary_finder_forget(uint32_t id) {{
    auto *backing = boundary_finder_backings[id & 65535u];
    boundary_finder_backings[id & 65535u] = nullptr;
    delete backing;
}}
static std::unique_ptr<BoundaryFinderBackingPtr> copy_boundary_backing(uint32_t source) {{
    source = variant_source_origin(source);
    auto *backing = entry(source) ? boundary_finder_backings[source & 65535u] : nullptr;
    return backing ? std::make_unique<BoundaryFinderBackingPtr>(*backing) : nullptr;
}}
static uint32_t finish_boundary_finder_ownership(BqtRequest *r, uint32_t id) {{
    auto *value = entry(id);
    if (!value || value->type != {g.ids['QTextBoundaryFinder']}) return id;
    uint32_t source = native_call_scope && native_call_scope->value_origin ? native_call_scope->value_origin : r->self;
    if (source != id) boundary_finder_backings[id & 65535u] = copy_boundary_backing(source).release();
    return id;
}}
'''
