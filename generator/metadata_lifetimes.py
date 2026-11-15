"""Observed QObject/type origins for Qt metaobjects and descriptor copies."""
from pathlib import Path

import abi_cohorts

VALUES = {'QMetaMethod', 'QMetaProperty', 'QMetaEnum', 'QMetaClassInfo'}


def adapt(g, f):
    t = f['return']
    if t['name'] == 'QMetaObject' and t['pointers'] == 1 and t['const']:
        return dict(g.type(t, result=True), metadata_pointer=True,
                    metatype_origin=f['declaring_class'] == 'QMetaType', metadata_static=f['static'])
    return None


def before_call(g, m):
    f = m['function']
    if f['declaring_class'] in VALUES and m['args'] and (f['constructor'] or f['name'] == 'operator='):
        if m['args'][0].get('name') in VALUES:
            return ['call_scope.value_origin = r->arguments[0].word;']
    return []


def after_call(g, m):
    if m['function']['declaring_class'] in VALUES and m['function']['name'] == 'operator=':
        return ['if (!finish_metadata_ownership(r, r->self)) return true;']
    return []


def store(g, t, value):
    if not t.get('metadata_pointer'):
        return None
    if t.get('metatype_origin'):
        origin = 'QMetaType(int32_t(r->arguments[0].word))' if t.get('metadata_static') else '*self'
        return [f'r->result.word = borrow_metatype_metadata(r, {origin}, {value});',
                'r->result.owned_handle = r->result.word;']
    return [f'r->result.word = borrow_metadata(r, {value}, r->self);']


def emit(g):
    if 'QMetaObject::SuperData' in g.ids:
        public = 'QMetaObject.SuperData.get'
        if any(method['bend_name'] == public for method in g.methods):
            raise ValueError('Native method conflicts with metadata arrow adapter: ' + public)
        operation = g.next_id
        g.next_id += 1
        g.cases.append(f'''case {operation}: {{
    NativeCallScope scope;
    auto *self = get<QMetaObject::SuperData>(r, r->self, {g.ids['QMetaObject::SuperData']}, false, false);
    if (r->error) return true;
    r->result = observe_metadata_field(r, self->operator->());
    return true;
}}''')
        g.emit_effect(public,
                      [('self', dict(kind='value', name='QMetaObject::SuperData', bend='QMetaObject.SuperData', raw='U32'))],
                      dict(kind='object', name='QMetaObject', bend='QMetaObject', raw='U32'), operation, has_self=True)
        for excluded in g.excluded:
            if excluded['class'] == 'QMetaObject::SuperData' and excluded['signature'] == 'operator->()const':
                excluded.setdefault('alternatives', []).append(dict(
                    bend_name=public, contract='guarded_metadata_arrow',
                    reason='Invokes the exact native operator and preserves the observed metadata origin'))
    if 'QMetaType' not in g.ids or any(m['bend_name'] == 'QMetaType.metaObject' for m in g.methods):
        return
    handle = dict(kind='value', name='QMetaType', bend='QMetaType', raw='U32')
    metadata = dict(kind='object', name='QMetaObject', bend='QMetaObject', raw='U32', pointer=True, readonly=True)
    operation = g.next_id
    g.next_id += 1
    g.cases.append(f'''case {operation}: {{
        NativeCallScope scope;
        auto *self = get<QMetaType>(r, r->self, {g.ids['QMetaType']}, false, false);
        if (r->error) return true;
        r->result.word = borrow_metatype_metadata(r, *self, self->metaObject());
        r->result.owned_handle = r->result.word;
        return true;
}}''')
    g.emit_effect('QMetaType.metaObject', [('self', handle)], metadata, operation, has_self=True)


def cpp(g):
    values = ' '.join(f'case {g.ids[n]}:' for n in sorted(VALUES) if n in g.ids)
    roots = '\n'.join(f'    case {g.ids[n]}: return static_cast<{n} *>(e->value)->enclosingMetaObject();'
                      for n in sorted(VALUES) if n in g.ids)
    if 'QMetaType' in g.ids:
        roots += f'\n    case {g.ids["QMetaType"]}: return static_cast<QMetaType *>(e->value)->metaObject();'
    if 'QQmlListReference' in g.ids:
        roots += f'\n    case {g.ids["QQmlListReference"]}: return static_cast<QQmlListReference *>(e->value)->listElementType();'
    source = f'''
struct MetadataOrigin {{
    uint32_t id = 0, root = 0;
    const QMetaObject *expected = nullptr;
    int properties = 0, methods = 0, enumerators = 0, infos = 0;
    bool immutable_root = false;
}};
static bool runtime_enum_metadata(const QMetaObject *);
static void native_metadata_publish(uint32_t);
static SlotTable<MetadataOrigin> metadata_origins;
static const QMetaObject *metadata_root_pointer(Entry *e) {{
    if (!e) return nullptr;
    auto index = uint32_t(e->slot_index);
    const auto &lease = metadata_origins[index];
    if (lease.immutable_root && lease.id == token(index, e->generation) && lease.root == lease.id)
        return lease.expected;
    if (e->object) return e->object->metaObject();
    switch (e->type) {{
{roots}
    default: return nullptr;
    }}
}}
static bool validate_metadata(BqtRequest *r, uint32_t id) {{
    auto origin = metadata_origins[id & 65535u];
    auto *root = origin.id == id ? entry(origin.root) : nullptr;
    auto *current = metadata_root_pointer(root);
    if (!root || !current || current != origin.expected || current->propertyCount() != origin.properties ||
            current->methodCount() != origin.methods || current->enumeratorCount() != origin.enumerators ||
            current->classInfoCount() != origin.infos) {{
        fail(r, ESTALE, "Qt dynamic metadata origin was destroyed or replaced"); return false;
    }}
    if (native_call_scope) native_call_scope->pin(r, origin.root);
    return !r->error;
}}
static MetadataOrigin metadata_source(uint32_t source) {{
    auto old = metadata_origins[source & 65535u];
    if (entry(source) && old.id == source) return old;
    if (auto *root = entry(source))
        if (auto *pointer = metadata_root_pointer(root)) return {{source, source, pointer,
            pointer->propertyCount(), pointer->methodCount(), pointer->enumeratorCount(), pointer->classInfoCount()}};
    return {{}};
}}
static uint32_t finish_metadata_ownership(BqtRequest *r, uint32_t id) {{
    auto *value = entry(id);
    if (!value) return id;
    switch (value->type) {{ {values} break; default: return id; }}
    uint32_t source = native_call_scope && native_call_scope->value_origin ? native_call_scope->value_origin : r->self;
    auto origin = metadata_source(source);
    // A default descriptor has no metadata; Qt exposes its native validity
    // predicates. Real descriptors obtained from a metaobject inherit origin.
    BqtRequest check{{}}; check.self = id;
    constexpr uint32_t slot = 0xffffffeau;
    int index = prepare_retention(&check, slot, 0, origin.root);
    if (check.error) {{
        auto *storage = value->value; auto destroy = value->destroy;
        invalidate(id); destroy(storage); if (!r->error) fail(r, check.error, check.message); return 0;
    }}
    commit_retention(index, id, slot, 0, origin.root, nullptr);
    origin.id = id;
    metadata_origins[id & 65535u] = origin;
    if (origin.root || value->validate == validate_metadata)
        value->validate = origin.root ? validate_metadata : nullptr;
    native_metadata_publish(id);
    return id;
}}
static uint32_t borrow_metadata(BqtRequest *r, const QMetaObject *value, uint32_t source) {{
    if (!value) return 0;
    auto origin = metadata_source(source);
    if (!origin.root) {{ fail(r, ENOTSUP, "Qt metadata needs an observed QObject or type origin"); return 0; }}
    auto id = register_native_borrow(r, value, {g.ids['QMetaObject']}, source);
    if (!id) return 0;
    // Shared static metaobjects may already have a valid origin. Keeping that
    // owner is conservative; never replace its validator with a weaker one.
    auto old = metadata_origins[id & 65535u];
    if (old.id != id) {{ origin.id = id; metadata_origins[id & 65535u] = origin; }}
    entry(id)->validate = validate_metadata;
    entry(id)->read_only = true;
    native_metadata_publish(id);
    return id;
}}
static uint32_t borrow_metatype_metadata(BqtRequest *r, const QMetaType &type, const QMetaObject *value, bool immutable = false) {{
    if (!value) return 0;
    immutable = immutable || runtime_enum_metadata(value);
    uint32_t source = own(r, new QMetaType(type), {g.ids['QMetaType']});
    if (!source) return 0;
    entry(source)->pending_release = true;
    if (immutable) {{
        // A scoped private value is the lease identity, including namespaces
        // whose metaType() is invalid. The pointer was checked against the
        // generated immutable native metadata inventory before this call.
        entry(source)->read_only = true;
        metadata_origins[source & 65535u] = {{source, source, value,
            value->propertyCount(), value->methodCount(), value->enumeratorCount(), value->classInfoCount(), true}};
    }}
    uint32_t id = create_value_view(r, const_cast<QMetaObject *>(value), {g.ids['QMetaObject']}, source, 0, nullptr);
    if (!id) {{ schedule_collection(); return 0; }}
    auto origin = metadata_source(source);
    origin.id = id;
    metadata_origins[id & 65535u] = origin;
    entry(id)->validate = validate_metadata;
    entry(id)->read_only = true;
    native_metadata_publish(id);
    return id;
}}
static bool immutable_metaobject(const QMetaObject *);
static BqtValue observe_metadata_field(BqtRequest *r, const QMetaObject *value) {{
    if (!value) return {{}};
    // Comparing against generated static objects needs no pointer dereference.
    // A private metatype lease makes each owning record copy independent.
    if (immutable_metaobject(value)) {{
        BqtValue result{{}};
        result.word = borrow_metatype_metadata(r, value->metaType(), value, true);
        result.owned_handle = result.word;
        return result;
    }}
    // Dynamic metadata must already have an observed QObject/type origin.
    for (uint32_t i=1; i<capacity; ++i) {{
        auto &candidate = entries[i];
        if (candidate.value != value || candidate.type != {g.ids['QMetaObject']}) continue;
        auto id = token(i, candidate.generation);
        get<QMetaObject>(r, id, {g.ids['QMetaObject']}, false, false);
        if (r->error) return {{}};
        BqtValue result{{}}; result.word = id; return result;
    }}
    fail(r, ENOTSUP, "Metadata field requires a compiled metatype or observed dynamic origin");
    return {{}};
}}
'''
    checks = []
    for name in g.selected:
        line = f'    if (native_metadata_static<{name}>(meta)) return true;'
        checks += ['#if BQT_HAS_RHI', line, '#endif'] if abi_cohorts.required(g, line) else [line]
    if g.callback_qml:
        checks.append('    if (meta == &CallbackQmlBridge::staticMetaObject) return true;')
    template = (Path(__file__).resolve().parent / 'templates/metadata_observations.cpp').read_text()
    return source + template.replace('@COMPILED_METADATA@', '\n'.join(checks)).replace(
        '@METADATA_LEASE_ID@', str(g.ids['QMetaClassInfo']))
