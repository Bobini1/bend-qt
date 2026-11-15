"""Typed opaque Bend values carried by owning Qt metatype values."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORD = dict(kind='u32', bend='U32', raw='U32')
UNIT = dict(kind='void', bend='Unit', raw='Unit')
WIRE = dict(kind='wire', bend='Wire', raw='Wire', codec='WireIdentity')


def emit(g):
    if not hasattr(g, 'custom_signal_arguments'):
        return
    g.bend_data_operations = {}
    for name, params, result, function, self in [
        ('Internal.Data.adopt_raw', [('token', WORD)], WIRE, 'adopt', False),
        ('Internal.Data.release_raw', [('token', WORD)], UNIT, 'release_lease', False),
        ('Internal.Data.variant_raw', [('value', WIRE)], dict(kind='value', name='QVariant', bend='QVariant', raw='U32'), 'variant', False),
        ('Internal.Data.from_variant_raw', [('self', dict(kind='value', name='QVariant', bend='QVariant', raw='U32'))], WIRE, 'from_variant', True),
        ('Runtime.liveData', [], WORD, 'count', False),
    ]:
        if function in ('variant', 'from_variant') and 'QVariant' not in g.ids:
            continue
        operation = g.next_id; g.next_id += 1
        g.bend_data_operations[function] = operation
        g.cases.append(f'case {operation}: {{\n    return OpaqueData::{function}(r);\n}}')
        g.emit_effect(name, params, result, operation, has_self=self)
    g.bend += [(HERE / 'templates/bend_data.bend').read_text().split('# @PUBLIC@')[0]]
    if not getattr(g, 'partition_secondary', False):
        g.effects += [effects(g)]


def public(g):
    source = (HERE / 'templates/bend_data.bend').read_text().split('# @PUBLIC@')[1]
    if 'QVariant' not in g.ids:
        source = source.split('# @VARIANT@')[0]
    return source


def cpp(g):
    return (HERE / 'templates/bend_data.cpp').read_text().replace('@VARIANT_ID@', str(g.ids.get('QVariant', 0))).replace(
        '@HAS_VARIANT@', '1' if 'QVariant' in g.ids else '0')


def effects(g):
    operation = g.bend_data_operations['adopt']
    return f'''
static void __attribute__((constructor)) bqt_data_operations_register(void) {{
    bqt_data_adopt_operation = {operation};
}}

#ifdef CID(Internal.Data.capture_raw)
static Term bqt_data_capture_run(Env e, Term *f, IoWork *w) {{
    Term witness = f[1], value = f[2];
    if (!term_triv(witness) || term_tag(witness) != TAG_CLO) {{
        term_drop(e, witness); term_drop(e, value);
        return io_fail(e, EINVAL, "An opaque Bend type needs a closed type witness");
    }}
    uint32_t token = bqt_data_new(e, (uint32_t)term_aux(witness), value);
    if (!token) return io_fail(e, ENOSPC, "Opaque Bend value capacity exhausted");
    BqtRequest request = {{0}};
    request.scope = (uint32_t)f[0]; request.operation = {operation};
    request.arguments[0].word = token;
    bool failed = false;
    Term result = bqt_call(e, &request, bqt_pack_wire, &failed);
    if (failed) bqt_data_release(token);
    return result;
}}
static void __attribute__((constructor)) bqt_data_capture_register(void) {{
    io_eff(CID(Internal.Data.capture_raw), bqt_data_capture_run);
}}
#endif

#ifdef CID(Internal.Data.extract_raw)
static Term bqt_data_extract_run(Env e, Term *f, IoWork *w) {{
    bqt_env = e;
    Term witness = f[0], wire = f[1];
    if (!term_triv(witness) || term_tag(witness) != TAG_CLO || term_aux(wire) != CID(WireData)) {{
        term_drop(e, witness); term_drop(e, wire);
        return io_fail(e, EINVAL, "Expected an opaque Bend value");
    }}
    Term fields[1];
    if (term_tag(wire) == TAG_PAK) fields[0] = term_loc(wire);
    else spare_free(e, cls_fit(1), ctr_take(e, wire, 1, fields));
    BqtData *row = bqt_data_find((uint32_t)fields[0]);
    if (!row) return io_fail(e, ESTALE, "Opaque Bend value has expired");
    if (row->witness != (uint32_t)term_aux(witness))
        return io_fail(e, EINVAL, "Opaque Bend value has a different declared type");
    return io_done(e, bqt_state_copy(e, &row->value));
}}
static void __attribute__((constructor)) bqt_data_extract_register(void) {{
    io_eff(CID(Internal.Data.extract_raw), bqt_data_extract_run);
}}
#endif
'''
