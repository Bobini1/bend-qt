"""Descriptor-based QVariant boxing with the existing origin lease machinery."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
WIRE = dict(kind='wire', bend='Wire', raw='Wire', codec='WireIdentity')
VARIANT = dict(kind='value', name='QVariant', bend='QVariant', raw='U32')
BOOL = dict(kind='bool', bend='Bool', raw='U32')
WORD = dict(kind='u32', bend='U32', raw='U32')
UNIT = dict(kind='void', bend='Unit', raw='Unit')


def emit(g):
    if not hasattr(g, 'custom_signal_arguments') or 'QVariant' not in g.ids:
        return
    g.generic_variant_operations = {}
    for public, parameters, result, native, receiver in [
        ('from_value_raw', [('argument', WIRE), ('value', WIRE)], VARIANT, 'box', False),
        ('to_value_raw', [('self', VARIANT), ('argument', WIRE)], WIRE, 'unbox', True),
        ('conversion_raw', [('self', VARIANT), ('argument', WIRE), ('mode', WORD)], BOOL, 'conversion', True),
        ('new', [], VARIANT, 'create', False),
        ('isValid', [('self', VARIANT)], BOOL, 'is_valid', True),
        ('isNull', [('self', VARIANT)], BOOL, 'is_null', True),
        ('clear', [('self', VARIANT)], UNIT, 'clear', True),
        ('metaType', [('self', VARIANT)], dict(kind='value', name='QMetaType', bend='QMetaType', raw='U32'), 'meta_type', True),
    ]:
        operation = g.next_id; g.next_id += 1
        g.generic_variant_operations[public] = operation
        g.cases.append(f'case {operation}: {{\n    return GenericVariants::{native}(r);\n}}')
        name = 'QVariant.' + public
        if any(m['bend_name'] == name for m in g.methods):
            raise ValueError('Native QVariant method conflicts with descriptor adapter: ' + name)
        g.emit_effect(name, parameters, result, operation, has_self=receiver)
    g.bend.append((HERE / 'templates/generic_variants.bend').read_text())


def cpp(g):
    if not hasattr(g, 'custom_signal_arguments') or 'QVariant' not in g.ids:
        return ''
    import metadata_lifetimes
    metadata_cases = ' '.join(f'case {g.ids[name]}:' for name in sorted(metadata_lifetimes.VALUES) if name in g.ids)
    return (HERE / 'templates/generic_variants.cpp').read_text().replace(
        '@VARIANT_ID@', str(g.ids['QVariant'])).replace('@QOBJECT_ID@', str(g.ids['QObject'])).replace(
        '@METADATA_CASES@', metadata_cases).replace('@METATYPE_ID@', str(g.ids['QMetaType']))


def inventory(g):
    return dict(available=hasattr(g, 'generic_variant_operations'),
                operations=getattr(g, 'generic_variant_operations', {}),
                types='The same native and opaque Bend descriptors used by signals, properties and methods',
                unboxing='Exact native metatype and closed Bend witness; QVariant descriptor copies the whole carrier',
                conversion='Explicit Qt canConvert/convert; failed conversion follows Qt and invalidates the QVariant',
                lifetime='Immutable VariantOrigin leases preserve value, metadata, QObject and observed native-pointer dependencies across copy, assign and swap')
