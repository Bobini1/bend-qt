#!/usr/bin/env python3
"""Generate a BendHub-ready Qt package using Shiboken's ApiExtractor.

This is maintainer tooling. Consumers compile only the emitted Bend/C files.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import output_files

from backend import command, compile_backend, validate_backend
from upstream import prepare, select_classes
import adapters
import application_objects
from adapters import install_carriers, prepare_adapters, emit_adapters, method_policy, owns_result, transfers_argument, native_member_parameters, native_header_support
from conversions import Conversions
from lifetime import evaluate_tables, cpp_tables
from retention import plan as retention_plan, native_parent_argument
from retention import before_call as retention_before_call, after_call as retention_after_call
import retention as retention_module
import callbacks
import signals
import custom_signals
import scope_actions
import qt_objects
import generic_variants
import value_types
import dynamic_properties
import bend_data
import child_lookup
import native_objects
import representations
import rendering
import rhi_lifetimes
import rhi_cleanup
import converter_cleanup
import buffers
import allocated_buffers
import qtest_values
import rhi_snapshots
import rhi_native_handles
import pyside_boundary
import native_interop
import gl_sync
import gl_raw_mappings
import gl_retained
import gl_pointers
import byte_iterators
import volume_data
import data_proxies
import public_fields
import form_rows
import value_provenance
import aggregate_fields
import pointer_fields
import video_buffers
import lazy_values
import durations
import public_records
import record_values
import native_operators
import overload_names
import return_values
import memory_views
import value_lifetimes
import moves
import borrowed_values
import dbus_replies
import meta_storage
import abi_cohorts
import variant_values
import url_handlers
import qml_registration
import native_events
import signature_restoration
import webview_runtime
import message_handlers
import coverage_inventory
import glyph_arrays
import raw_storage
import resource_swaps
import typed_views
import metadata_lifetimes
import role_data
import event_snapshots
import persistent_storage
import model_indices
import qml_list_lifetimes
import generic_arguments
import model_data
import image_buffers
import boundary_finders
import incubation
import effect_transport
import runnable_jobs
import event_loops
import thread_affinity
import data_streams
import native_function_callbacks
import qml_list_properties
import post_routines
import protected_members
import protected_fields
import engine_lifetimes
import core_pointer_results
import native_result_views
import render_result_lifetimes
import mutex_lockers
import cursor_guards
import touch_sequences
import qobject_interfaces
import qio_pipe
import value_pointer_inputs
import convenience_apis

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CACHE = Path.home() / ".cache/bend-qt-generator"
RESULT = "Result<&1, &1, U32 & String, {type}>"
OPERATORS = {'operator+': 'op_add', 'operator-': 'op_subtract', 'operator*': 'op_multiply',
             'operator/': 'op_divide', 'operator==': 'op_equal', 'operator!=': 'op_not_equal',
             'operator<': 'op_less', 'operator<=': 'op_less_equal', 'operator>': 'op_greater',
             'operator>=': 'op_greater_equal', 'operator=': 'op_assign',
             'operator+=': 'op_add_assign', 'operator-=': 'op_subtract_assign',
             'operator*=': 'op_multiply_assign', 'operator/=': 'op_divide_assign',
             'operator&': 'op_bit_and', 'operator|': 'op_bit_or', 'operator^': 'op_bit_xor',
             'operator&=': 'op_bit_and_assign', 'operator|=': 'op_bit_or_assign',
             'operator^=': 'op_bit_xor_assign', 'operator~': 'op_bit_not',
             'operator!': 'op_not', 'operator bool': 'op_bool', 'operator QVariant': 'op_variant',
             'operator%': 'op_remainder', 'operator%=': 'op_remainder_assign',
             'operator<<': 'op_shift_left', 'operator>>': 'op_shift_right',
             'operator++': 'op_increment', 'operator--': 'op_decrement',
             'operator[]': 'op_at', 'operator()': 'op_call',
             'operator int': 'op_int', 'operator unsigned int': 'op_unsigned_int',
             'operator double': 'op_double', 'operator qreal': 'op_qreal', 'operator QString': 'op_string'}


def result_type(name):
    return RESULT.format(type=name)


def ident(name):
    return name.replace("::", ".")


def c_ident(name):
    return re.sub(r"[^a-zA-Z0-9_]", "_", name)


def json_write(path, value):
    output_files.write_text(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def enum_fits_word(enum):
    return enum["used_bits"] <= 32 and enum["underlying_type"] not in (
        "qint64", "quint64", "long long", "unsigned long long", "long", "unsigned long")


def source_arity(signature):
    """Count parameters in Shiboken's original, unresolved C++ signature."""
    start = signature.index("(") + 1
    depth = 0
    count = 1
    for i in range(start, len(signature)):
        char = signature[i]
        if char == ")" and depth == 0:
            return 0 if signature[start:i].strip() in ("", "void") else count
        if char in "<([": depth += 1
        elif char in ">)]": depth -= 1
        elif char == "," and depth == 0: count += 1
        if depth < 0: break
    raise ValueError(f"Cannot interpret original parameter list: {signature}")


def source_parameters_match(function):
    if function.get('free_operator'):
        return True
    for signature in function["source_signatures"]:
        parameters = native_operators.parameters(signature, function['name'])
        arity = len(parameters) if parameters is not None else source_arity(signature)
        expected = len(function["arguments"])
        if signature_restoration.optional_tail(function, parameters):
            continue
        # Qt deliberately hides the trailing QPrivateSignal marker. connect()
        # deduces its real signature and permits a lambda with fewer arguments.
        if (function["signal"] and arity == expected + 1
                and re.search(r"(?:\(|,)\s*(?:\w+::)*QPrivateSignal\)\s*$", signature)):
            continue
        if arity != expected:
            return False
    return True


class Generator:
    def __init__(self, api, profile, name_lock=None):
        api = pyside_boundary.apply(api)
        self.api = api
        self.profile = profile
        # Focused fixture profiles read the package lock so their names match
        # the published package; only a full generation writes it.
        if name_lock is None:
            name_lock = overload_names.NameLock.load(HERE / 'qt612/names.lock.json')
            name_lock.path = None
        self.name_lock = name_lock
        self.unbound_overloads = Counter()
        self.excluded_identities = {}
        self.merged_overloads = []
        self.classes = {}
        for c in api['classes']:
            previous = self.classes.get(c['name'])
            if previous and c['namespace']:
                merged = dict(previous)
                for field, identity in (('functions', 'minimal_signature'), ('enums', 'name')):
                    merged[field] = list({x[identity]: x for x in previous[field] + c[field]}.values())
                merged['generate'] = previous['generate'] or c['generate']
                merged['packages'] = sorted({*previous.get('packages', [previous.get('package')]), c.get('package')} - {None})
                self.classes[c['name']] = merged
            else:
                self.classes[c['name']] = c
        self.selected, self.excluded_classes = select_classes(api)
        install_carriers(self.classes, self.selected)
        adapters.install_group_retention(self.classes)
        native_objects.install(self.classes, self.selected, self.excluded_classes)
        child_lookup.install(self.classes, self.selected)
        convenience_apis.install(self.classes, self.selected)
        core_pointer_results.install(self.classes, self.selected)
        self.excluded_classes = [c for c in self.excluded_classes if c['class'] not in self.selected]
        self.namespaces = sorted(c['name'] for c in self.classes.values() if c.get('namespace') and c.get('generate'))
        if api.get('global_functions'):
            self.classes['Global'] = {'name': 'Global', 'namespace': True, 'object': False,
                'qobject': False, 'public_destructor': True, 'abstract': False,
                'bases': [], 'functions': api['global_functions'], 'enums': []}
            self.namespaces.append('Global')
        self.ids = {name: i + 1 for i, name in enumerate(self.selected)}
        self.enums = {e["name"]: e for e in api["enums"]}
        for c in api["classes"]:
            self.enums.update({e["name"]: e for e in c["enums"]})
        self.types = {"Int32": "scalar"}
        self.types.update({name: "wide" for name in ("F64", "Int64", "UInt64")})
        self.types.update({ident(name): "handle" for name in self.selected})
        self.excluded = []
        for name, enum in self.enums.items():
            self.types[ident(name)] = 'scalar' if enum_fits_word(enum) else 'wide'
        self.methods = []
        self.signal_kinds = {}
        self.cases = []
        self.bend = []
        self.effects = []
        self.next_id = 10
        self.argument_capacity = 8
        self.conversions = Conversions(self)
        self.retention_slots = {}
        self.retention_accessors = {}

    def type(self, t, *, result=False):
        t = durations.normalize(t) or t
        name, pointers, reference = t["name"], t["pointers"], t["reference"]
        synchronization = gl_sync.type(self, t)
        if synchronization is not None:
            return synchronization
        # A registered upstream primitive may retain a template spelling while
        # omitting its instantiation metadata (Qt Multimedia uses optional<qreal>).
        optional = re.fullmatch(r'std::optional<(.+)>', name)
        if optional and not pointers and not t.get('instantiations'):
            element = optional[1].strip()
            child = dict(t, name=element, cpp=element, const=False, reference=0,
                         instantiations=[], container=False, enum=element in self.enums, flags=False)
            return self.conversions.container(dict(t, name='std::optional', instantiations=[child]), result)
        if pointers > 1:
            raise ValueError("Pointer-to-pointer conversion needs an explicit allocation policy")
        if reference == 2:
            consumed = moves.convert(self, t)
            if consumed is not None:
                return consumed
            converted = self.type(dict(t, reference=0, cpp=t['cpp'].replace('&&', '').strip()), result=result)
            if converted['kind'] == 'object' or (converted['kind'] == 'value' and not self.classes[converted['name']].get('copyable', True)):
                raise ValueError('Rvalue input requires a copyable value representation')
            return dict(converted, cpp=t['cpp'], rvalue=True)
        if pointers and reference:
            raise ValueError('Pointer-reference reassignment needs a lifetime adapter')
        if name == "void" and not pointers:
            return {"kind": "void", "bend": "Unit", "raw": "Unit", "cpp": t["cpp"]}
        if name == 'std::nullptr_t' and not pointers:
            return dict(kind='nullptr', bend='Unit', raw='Unit', cpp=t['cpp'], codec='Convert_Nullptr')
        if name == "QString" and not pointers:
            return {"kind": "string", "bend": "String", "raw": "String", "cpp": t["cpp"]}
        if name in ('QChar', 'QLatin1Char') and not pointers:
            return {'kind': 'character', 'bend': 'U32', 'raw': 'U32', 'name': name, 'cpp': t['cpp']}
        if name.startswith('std::chrono::') and not pointers:
            unit = name.removeprefix('std::chrono::')
            if unit in ('nanoseconds', 'microseconds', 'milliseconds', 'seconds', 'minutes', 'hours'):
                public = unit[:1].upper() + unit[1:]
                self.types[public] = 'wide'
                return {'kind': 'duration', 'bend': public, 'raw': 'U32 & U32', 'name': name, 'cpp': t['cpp']}
        if name in ('QLatin1String', 'QLatin1StringView', 'std::string', 'std::string_view') and not pointers:
            return {'kind': 'std_string' if name.startswith('std::') else 'latin1_view',
                    'bend': 'QByteArray', 'raw': 'U32', 'name': 'QByteArray', 'cpp': t['cpp'], 'pointer': False}
        if name in ("QAnyStringView", "QStringView") and not pointers:
            return {"kind": "string_view", "bend": "String", "raw": "String", "cpp": t["cpp"], "name": name}
        if name == 'QByteArrayView' and not pointers:
            # Bend owns the byte storage. Inputs borrow it only for the native
            # call; returned views are copied before their owner can change.
            return {'kind': 'byte_view', 'bend': 'QByteArray', 'raw': 'U32',
                    'cpp': t['cpp'], 'name': 'QByteArray', 'pointer': False}
        if name == 'QStringList' and not pointers:
            element = dict(t, name='QString', cpp='QString', const=False, reference=0, instantiations=[], container=False)
            return self.conversions.container(dict(t, name='QList', instantiations=[element]), result)
        if name in ('QSharedPointer', 'QFuture') and not pointers:
            from representations import shared_name, future_name
            public = shared_name(t) if name == 'QSharedPointer' else future_name(t)
            if public not in self.ids:
                raise ValueError('Owning template carrier was not discovered before generation')
            if reference == 1 and not t['const']:
                raise ValueError('Mutable template reference requires alias invalidation')
            return {'kind': 'value', 'bend': public, 'raw': 'U32', 'name': public,
                    'cpp': t['cpp'], 'pointer': False, 'native_const': bool(t['const'])}
        if (t.get('container') or name == 'std::optional' or (t.get('instantiations') and name in
                ('QList', 'QVector', 'QSet', 'QMap', 'QHash', 'QMultiMap', 'QMultiHash', 'std::pair', 'QPair', 'std::array'))) and not pointers:
            return self.conversions.container(t, result)
        matrix = re.fullmatch(r'QGenericMatrix<(\d+),(\d+),float>', t['cpp'].replace('const ', '').replace('&', '').replace(' ', ''))
        if matrix:
            alias = f'QMatrix{matrix[1]}x{matrix[2]}'
            if alias in self.ids:
                name = alias
        if name in self.ids:
            obj = self.classes[name]["object"]
            if self.classes[name].get('borrow_only') and not pointers and not reference:
                raise ValueError('Class with a non-public destructor supports borrowed identity only')
            if obj and not self.classes[name]['qobject'] and not pointers and not reference:
                if not self.classes[name].get('copyable') and not result:
                    raise ValueError('Noncopyable value input requires an explicit transfer operation')
                if self.classes[name].get('abstract'):
                    raise ValueError('Abstract object cannot be copied into a value')
                if result and not self.classes[name].get('native_movable', True):
                    raise ValueError('Native value return requires a public copy or move constructor')
                return {'kind': 'value', 'bend': ident(name), 'raw': 'U32', 'name': name,
                        'cpp': t['cpp'], 'pointer': False,
                        'move_result': True}
            if obj and not (pointers == 1 or reference == 1):
                raise ValueError("QObject values need a separate ownership policy")
            if not obj and pointers:
                raise ValueError("Pointers to value types need an explicit lifetime policy")
            return {"kind": "object" if obj else "value", "bend": ident(name), "raw": "U32",
                    "name": name, "cpp": t["cpp"], "pointer": bool(pointers),
                    'native_const': bool(t['const']), 'readonly': bool(obj and result and t['const'])}
        if pointers:
            raise ValueError("Raw pointer conversion is not implemented")
        if name in ("double", "qreal", "float"):
            return {"kind": "real", "bend": "F64", "raw": "U32 & U32", "cpp": t["cpp"]}
        if name in ("long long", "qint64", "qlonglong", "long", "qsizetype", "qintptr", 'ptrdiff_t', 'std::ptrdiff_t', 'int64_t', 'std::int64_t'):
            return {"kind": "i64", "bend": "Int64", "raw": "U32 & U32", "cpp": t["cpp"]}
        if name in ("unsigned long long", "quint64", "qulonglong", "unsigned long", "ulong", "size_t", "quintptr", 'WId', 'uint64_t', 'std::uint64_t'):
            return {"kind": "u64", "bend": "UInt64", "raw": "U32 & U32", "cpp": t["cpp"]}
        if t["enum"] or t["flags"] or name in self.enums:
            enum_name = name[7:-1] if t["flags"] else name
            enum = self.enums.get(enum_name)
            wide = enum and not enum_fits_word(enum)
            public = "Flags_" + c_ident(name[7:-1]) if t["flags"] else ident(name)
            self.types[public] = 'wide' if wide else 'scalar'
            return {"kind": ('flags' if t['flags'] else 'enum') + ('64' if wide else ''), "bend": public,
                    "raw": "U32 & U32" if wide else 'U32', "name": name, "cpp": t["cpp"]}
        mapping = {"bool": ("bool", "Bool"), "int": ("i32", "Int32"),
                   "unsigned int": ("u32", "U32"), "uint": ("u32", "U32"),
                   "short": ("i32", "Int32"), "unsigned short": ("u32", "U32"),
                   "char": ("i32", "Int32"), "signed char": ("i32", "Int32"), "unsigned char": ("u32", "U32")}
        mapping.update({n: ('i32', 'Int32') for n in ('qint8', 'qint16', 'qint32',
            'int8_t', 'int16_t', 'int32_t', 'std::int8_t', 'std::int16_t', 'std::int32_t')})
        mapping.update({n: ('u32', 'U32') for n in ('quint8', 'quint16', 'quint32', 'uchar', 'ushort',
            'uint8_t', 'uint16_t', 'uint32_t', 'std::uint8_t', 'std::uint16_t', 'std::uint32_t', 'char16_t', 'char32_t')})
        if name in mapping:
            kind, public = mapping[name]
            return {"kind": kind, "bend": public, "raw": "U32", "cpp": t["cpp"]}
        raise ValueError(f"No lossless conversion for {t['cpp']}")

    def parameters(self, f):
        mapped = glyph_arrays.parameters(self, f)
        if mapped is not None:
            return mapped
        mapped = rhi_native_handles.parameters(self, f)
        if mapped is not None:
            return mapped
        """Keep native positions separate from public inputs and returned outputs."""
        mapped = rhi_lifetimes.parameters(self, f)
        if mapped is not None:
            return mapped
        mapped = incubation.parameters(self, f)
        if mapped is not None:
            return mapped
        mapped = native_events.parameters(self, f)
        if mapped is not None:
            return mapped
        mapped = model_data.parameters(self, f)
        if mapped is not None:
            return mapped
        mapped = value_pointer_inputs.parameters(self, f)
        if mapped is not None:
            return mapped
        mapped = boundary_finders.parameters(self, f)
        if mapped is not None:
            return mapped
        mapped = image_buffers.parameters(self, f)
        if mapped is not None:
            return mapped
        mapped = volume_data.parameters(self, f)
        if mapped is not None:
            return mapped
        mapped = data_proxies.parameters(self, f)
        if mapped is not None:
            return mapped
        mapped = generic_arguments.parameters(self, f)
        if mapped is not None:
            return mapped
        mapped = byte_iterators.parameters(self, f)
        if mapped is not None:
            return mapped
        mapped = gl_pointers.parameters(self, f)
        if mapped is not None:
            return mapped
        mapped = gl_retained.parameters(self, f)
        if mapped is not None:
            return mapped
        mapped = meta_storage.parameters(self, f)
        if mapped is not None:
            return mapped
        mapped = gl_raw_mappings.parameters(self, f)
        if mapped is not None:
            return mapped
        mapped = qtest_values.parameters(self, f)
        if mapped is not None:
            return mapped
        mapped = allocated_buffers.parameters(self, f)
        if mapped is not None:
            return mapped
        mapped = native_interop.parameters(self, f)
        if mapped is not None:
            return mapped
        mapped = persistent_storage.parameters(self, f)
        if mapped is not None:
            return mapped
        mapped = record_values.parameters(self, f)
        if mapped is not None: return mapped
        mapped = event_snapshots.parameters(self, f)
        if mapped is not None:
            return mapped
        mapped = role_data.parameters(self, f)
        if mapped is not None:
            return mapped
        mapped = raw_storage.parameters(self, f)
        if mapped is not None:
            return mapped
        mapped = borrowed_values.parameters(self, f)
        if mapped is not None:
            return mapped
        mapped = memory_views.parameters(self, f)
        if mapped is not None:
            return mapped
        import buffers
        args, plan, outputs = [], [], []
        buffer_policies, restored = buffers.policies(f)
        snippets = '\n'.join(f.get('snippets', []))
        # These upstream templates allocate one scalar per removed pointer.
        # Other snippets (notably buffers) require a different adapter.
        scalar_outputs = bool(re.search(r'// TEMPLATE - fix_(?:bool\*(?:,arg)?|char\*|number\*(?:,number\*)+) - START', snippets))
        for i, a in enumerate(f['arguments']):
            t = a['type']
            if buffer_policies.get(i, {}).get('ignored'):
                plan.append(dict(type=dict(kind='void', bend='Unit', raw='Unit'), source=i, input=None,
                                 output=False, mutable=False, ignored=True))
                continue
            # A removed pointer is an output only when upstream passes the
            # address of an explicitly typed local, rather than an array/data
            # pointer. This also covers value outputs such as QRect/QPointF.
            local_type = re.escape(t['name'])
            address_output = (bool(re.search(r'%FUNCTION_NAME\([^;]*&[A-Za-z_]\w*', snippets))
                              and bool(re.search(r'\b' + local_type + r'\s+[A-Za-z_]\w*\s*[,;={]', snippets)))
            suffix_output = (f['declaring_class'], f['name'], i) == ('QVersionNumber', 'fromString', 1)
            out = (a.get('removed') and (scalar_outputs or address_output or suffix_output)
                   and not a.get('array') and t['pointers'] == 1 and not t['const'] and not t['reference'])
            out = out or buffer_policies.get(i, {}).get('output_pointer', False)
            object_output = buffer_policies.get(i, {}).get('output_object', False)
            out = out or object_output
            inout_pointer = buffer_policies.get(i, {}).get('inout_pointer', False)
            if out:
                t = dict(t, pointers=1 if object_output else 0, reference=0,
                         cpp=t['cpp'].rstrip().removesuffix('*').rstrip())
            elif inout_pointer:
                t = dict(t, pointers=0, reference=1, cpp=re.sub(r'\*\s*$', '&', t['cpp']))
            elif a.get('removed') and i not in restored:
                raise ValueError('Removed argument needs an audited native conversion')
            converted = buffers.convert(self, t, buffer_policies[i]) if i in buffer_policies and not (out or inout_pointer) else self.type(t)
            if out and converted['kind'] == 'object' and not object_output:
                raise ValueError('Output object pointer requires an explicit lifetime policy')
            mutable = (t['reference'] == 1 and not t['const']) or converted.get('buffer', {}).get('writable_array', False)
            if mutable and (converted['kind'] in ('string_view', 'byte_view', 'latin1_view') or 'std::string_view' in converted['cpp']):
                raise ValueError('Mutable view lifetime conversion is not implemented')
            item = {'type': converted, 'source': i, 'input': None if out else len(args), 'output': out,
                    'inout_pointer': inout_pointer,
                    'mutable': mutable and converted['kind'] not in ('object', 'value')}
            if not out: args.append(converted)
            if out or item['mutable']:
                self.conversions.register(converted)
                outputs.append(item)
            plan.append(item)
        for item in plan:
            buffer = item['type'].get('buffer')
            if buffer:
                for role in ('count', 'tuple', 'pname', 'range', 'bitmap_size', 'bitmap_format',
                             'width', 'height', 'depth', 'format', 'pixel_type', 'index_count', 'index_type',
                             'options', 'mip', 'layer_count', 'program', 'block', 'stage', 'list_type', 'lengths',
                             'target', 'query', 'ustride', 'uorder', 'vstride', 'vorder', 'draw_count', 'draw_stride', 'counts'):
                    if role + '_source' not in buffer:
                        continue
                    count = plan[buffer[role + '_source']]
                    if count['input'] is None:
                        raise ValueError('Buffer extent must be an explicit input')
                    buffer.update({role + '_input': count['input'], role + '_type': count['type']})
        bounds = buffers.index_bounds(f)
        if f['name'] in ('operator[]', 'operator()') or bounds:
            for i, converted in enumerate(args):
                if converted['kind'] in ('i32', 'u32', 'i64', 'u64'):
                    if i not in bounds:
                        raise ValueError('Numeric indexing requires an audited receiver bound')
                    if bounds[i] is not None:
                        converted['index_bound'] = bounds[i]
        return args, plan, outputs

    def inherited(self, name):
        methods = {native_operators.identity(f): native_operators.normalize(self, signature_restoration.normalize(f))
                   for f in self.classes[name]["functions"]}
        for base in self.classes[name]["bases"]:
            if base in self.ids:
                for f in self.inherited(base):
                    if not f["constructor"] and not f["destructor"]:
                        methods.setdefault(native_operators.identity(f), f)
        return sorted(methods.values(), key=lambda f: (f["name"], f["minimal_signature"]))

    def collect(self):
        rhi_lifetimes.restore_methods(self)
        for name in self.selected + self.namespaces:
            if name not in self.classes:
                raise ValueError(f"Selected class was not extracted: {name}")
            from module_partitions import exports_class
            # A group also emits members declared by its own modules for a
            # class owned elsewhere (module_partitions.member_assignments).
            from module_partitions import partition_assigned
            assigned = None if exports_class(self, name) else partition_assigned(self, name)
            if not exports_class(self, name) and not assigned:
                continue
            if name in ("QString", "QStringView", "QAnyStringView"):
                raise ValueError(f"{name} uses the String converter, not a handle class")
            if not self.classes[name]["public_destructor"] and not self.classes[name].get('borrow_only'):
                raise ValueError(f"A non-public destructor needs an explicit lifetime policy: {name}")
            methods = self.inherited(name)
            if assigned:
                methods = [f for f in methods if f['minimal_signature'] in assigned]
            elif getattr(self, 'partition_export_packages', None):
                methods = [f for f in methods if not f.get('partition_module')
                           or 'PySide6.' + f['partition_module'] in self.partition_export_packages]
            signal_counts = Counter(f["name"] for f in methods)
            for f in methods:
                f = protected_members.callable_contract(self, name, f)
                bindable = False
                try:
                    if not f["public"] and not protected_members.permitted(self, f):
                        raise ValueError("Not a public or accessible protected member")
                    if f["removed"] and not (buffers.restores_method(f) or native_operators.restores_method(f) or memory_views.restores_method(f) or borrowed_values.restores_method(f) or raw_storage.handles(f) or role_data.restores_method(f) or persistent_storage.kind(f) or image_buffers.handles(f)):
                        if not signature_restoration.restore_native(f):
                            raise ValueError("Removed by the type system")
                        f = dict(f, bend_restored_native=True)
                    if f["user_added"] and not role_data.restores_addition(f) and not f.get('rhi_range_adapter'): raise ValueError("Python-only addition requires a Bend adapter")
                    if f["destructor"]: raise ValueError("Use the checked destroy effect")
                    if f.get('free_operator_error'): raise ValueError(f['free_operator_error'])
                    if f["operator"] and f['name'] not in OPERATORS and not native_operators.conversion_name(f):
                        raise ValueError("Operator requires an explicit Bend naming/conversion policy")
                    if not source_parameters_match(f) and not f.get('rhi_range_adapter'):
                        raise ValueError("Shiboken stripped or changed parameters; register their types before generation")
                    if f["constructor"] and self.classes[name]["abstract"]:
                        raise ValueError("Abstract classes cannot be constructed")
                    if f['constructor'] and self.classes[name].get('borrow_only') and not self.classes[name].get('derived_constructor'):
                        raise ValueError('An inaccessible native destructor permits borrowed handles only')
                    if f["name"].startswith("qt_") or (f["name"] == "tr" and f.get('convenience') != 'translation'):
                        raise ValueError("Qt metaobject implementation entry point")
                    reason = self.profile["exclude_methods"].get(f["declaring_class"] + "::" + f["name"])
                    if reason: raise ValueError(reason)
                    reason = method_policy(name, f, self.all_bases(name))
                    if reason: raise ValueError(reason)
                    # Past every policy: a failure below is a missing conversion
                    # that a later release may add, so it keeps names suffixed.
                    bindable = True
                    if f['signal']:
                        signal = signals.describe(self, f, signal_counts[f['name']] > 1)
                        self.methods.append({'class': name, 'function': f, 'args': [], 'return': signal['result'],
                                             'signal': signal, 'signal_args': signal['args'],
                                             'default_constructor': False})
                        continue
                    args, plan, outputs = self.parameters(f)
                    retention = retention_plan(self, name, f, args, plan)
                    for policy in f['policies']:
                        if transfers_argument(f, policy):
                            p = plan[policy['index'] - 1]
                            if not p['type'].get('native_copy_adoption') and (p['type']['kind'] != 'object' or p['input'] is None):
                                raise ValueError('Ownership transfer requires a tracked QObject argument')
                    if f["constructor"]:
                        ret = {"kind": "object" if self.classes[name]["object"] else "value",
                               "bend": ident(name), "raw": "U32", "name": name}
                    else:
                        ret = return_values.adapt(self, f) or self.type(f["return"], result=True)
                    if ret['kind'] == 'object':
                        ret['owned'] = owns_result(f) or rhi_lifetimes.owns_result(self, f)
                    elif owns_result(f) or rhi_lifetimes.owns_result(self, f):
                        ret = self.conversions.owned_objects(ret)
                    def check_owned_result(t):
                        if t['kind'] == 'object' and t.get('owned') and self.classes[t['name']].get('borrow_only'):
                            if not (f['constructor'] and t['name'] == name and self.classes[name].get('derived_constructor')):
                                raise ValueError('A native factory result needs an accessible destruction policy')
                        for child in t.get('children', []): check_owned_result(child)
                    check_owned_result(ret)
                    native_return = ret
                    if outputs:
                        fields = ([] if ret['kind'] == 'void' else [ret]) + [p['type'] for p in outputs]
                        ret = self.conversions.record(fields, prefix='Outputs_')
                    self.methods.append({"class": name, "function": f, "args": args, "return": ret,
                                         'parameters': plan, 'outputs': outputs, 'native_return': native_return, 'retention': retention,
                                         "default_constructor": False})
                    if f["constructor"] and args and not outputs and all(a["default"] for a in f["arguments"]):
                        self.methods.append({"class": name, "function": f, "args": [], "return": ret,
                                             "default_constructor": True})
                except ValueError as error:
                    self.excluded.append({"class": name, "signature": f["signature"],
                                          "source_signatures": f["source_signatures"], "reason": str(error)})
                    self.excluded_identities[(name, native_operators.identity(f))] = str(error)
                    if bindable:
                        self.unbound_overloads[(name, self.base_name({'function': f}))] += 1
        # Default variants take N explicit arguments and supply the remaining
        # original C++ defaults. Python replacements of defaults are
        # deliberately not evaluated. Variants are named as ordinary overloads.
        for m in list(self.methods):
            f = m['function']
            if f['signal'] or m['default_constructor']:
                continue
            constructor_dependencies = (f['constructor'] and m.get('retention', {}).get('custom') == 'constructor_dependencies') if m.get('retention') else False
            handle_property = bool(m.get('retention') and m['retention'].get('custom') == 'handle_property')
            if m.get('outputs') or (m.get('retention') and not (constructor_dependencies or handle_property)) or any(a.get('buffer') for a in m['args']):
                continue  # Output-bearing methods keep every public input explicit.
            for count in reversed(range(len(m['args']))):
                if not f['arguments'][count].get('native_default'):
                    break
                if handle_property and (m['retention']['input'] >= count or
                        (m['retention'].get('key') is not None and m['retention']['key'] >= count)):
                    break  # The retained pointer and relationship key stay explicit.
                if constructor_dependencies and any(
                        item['input'] >= count and f['arguments'][item['input']]['native_default'] not in ('nullptr', '0', 'Q_NULLPTR')
                        for item in m['retention']['dependencies']):
                    break  # An omitted non-null dependency needs its own registered lifetime.
                if count == 0 and f['constructor'] and all(a['default'] for a in f['arguments']):
                    continue  # Existing .new() already covers this constructor.
                self.methods.append(dict(m, args=m['args'][:count],
                    omitted_defaults=[a['native_default'] for a in f['arguments'][count:]]))
        overload_names.assign(self, self.name_lock)
        import gl_pixel_offsets
        gl_pixel_offsets.expand(self)
        rhi_snapshots.alternatives(self)
        # Callback families are named in callbacks.prepare; main() then runs
        # overload_names.finalize over every public entry.

    @staticmethod
    def base_name(m):
        f = m["function"]
        if glyph_arrays.handles(f):
            return 'setRawDataSnapshot'
        if boundary_finders.handles(f):
            return 'withWorkingBuffer'
        if image_buffers.handles(f):
            return image_buffers.public_name(f)
        name = OPERATORS.get(f['name'], native_operators.conversion_name(f) or f['name'])
        if f.get('free_operator', {}).get('reverse') and name.startswith('op_'):
            name = 'op_reverse_' + name.removeprefix('op_')
        if name in ('destroy', 'release', 'with', 'word', 'wrap', 'cast'):
            name = 'native_' + name
        return "new" if f["constructor"] else ("connect_" if f["signal"] else "") + name

    def argument(self, t, index):
        synchronization = gl_sync.argument(self, t, index)
        if synchronization is not None:
            return synchronization
        adapted = borrowed_values.argument(self, t, index)
        if adapted is not None:
            return adapted
        value = f"r->arguments[{index}]"
        kind = t["kind"]
        if t.get('consume'):
            return moves.argument(self, t, index)
        if 'index_bound' in t:
            plain = dict(t)
            bound = plain.pop('index_bound')
            declarations, expression = self.argument(plain, index)
            return declarations + ['if (r->error) return true;',
                f'if ({expression} < 0 || uint64_t({expression}) >= uint64_t({bound})) return fail(r, ERANGE, "Qt index is outside its receiver bounds");'], expression
        if 'buffer' in t:
            import buffers
            return buffers.argument(self, t, index)
        if t.get('rvalue'):
            copied = dict(t, rvalue=False, cpp=t['cpp'].replace('&&', '').strip())
            declarations, expression = self.argument(copied, index)
            native = copied['cpp'].replace('const ', '').replace('&', '').strip()
            return declarations, f'{native}({expression})'
        if t['raw'] == 'Wire':
            return [f"auto a{index} = read_{t['native_codec']}(r, {value});"], f'*a{index}'
        if kind in ("object", "value", 'object_snapshot'):
            by_value = kind == 'value' and not t.get('pointer') and '&' not in t['cpp']
            writable = not (t.get('native_const') or t.get('readonly') or kind == 'object_snapshot' or by_value)
            decl = (f"auto *a{index} = get<{t['name']}>(r, {value}.word, {self.ids[t['name']]}, "
                    + ("true" if t.get("pointer", False) and not t.get('required_pointer') else "false")
                    + ', ' + str(writable).lower() + ");")
            expression = f"a{index}" if t.get("pointer", False) else f"{t['name']}(*a{index})" if by_value else f"*a{index}"
            return [decl], expression
        if kind == 'byte_view':
            return [f"auto *a{index} = get<QByteArray>(r, {value}.word, {self.ids['QByteArray']});"], f'QByteArrayView(*a{index})'
        if kind in ('latin1_view', 'std_string'):
            native = t['cpp'].replace('const ', '').replace('&', '').strip()
            declarations = [f"auto *a{index} = get<QByteArray>(r, {value}.word, {self.ids['QByteArray']});"]
            return declarations, f'{native}(a{index}->constData(), a{index}->size())'
        if kind == 'character':
            maximum = 255 if t['name'] == 'QLatin1Char' else 65535
            cast = 'char' if t['name'] == 'QLatin1Char' else 'char16_t'
            return [f'if ({value}.word > {maximum}) fail(r, ERANGE, "Character code unit is outside its Qt type range");'], f"{t['name']}(static_cast<{cast}>({value}.word))"
        if kind == 'duration':
            return [f"static_assert(std::numeric_limits<{t['name']}::rep>::is_signed && sizeof({t['name']}::rep) == 8);"], f"{t['name']}{{static_cast<{t['name']}::rep>(int64_t(wide_bits({value})))}}"
        if kind == "string":
            return [], f"QString::fromUtf8({value}.text, qsizetype({value}.size))"
        if kind == 'cstring':
            return [f'if ({value}.size && std::memchr({value}.text, 0, {value}.size)) fail(r, EINVAL, "C string contains an embedded NUL");'], f'{value}.text'
        if kind == "string_view":
            return [], f"{t['name']}(QString::fromUtf8({value}.text, qsizetype({value}.size)))"
        if kind == "bool": return [], f"({value}.word != 0)"
        if kind == 'nullptr':
            return [f'if ({value}.word || {value}.high) fail(r, EINVAL, "Null pointer payload must be Unit");'], 'nullptr'
        numeric = {"i32": f"int32_t({value}.word)", "u32": f"{value}.word",
                   "real": f"real_value({value})", "i64": f"int64_t(wide_bits({value}))",
                   "u64": f"wide_bits({value})"}
        if kind in numeric:
            native = t['cpp'].replace('const ', '').replace('&', '').strip()
            checks = []
            if kind in ('i32', 'u32'):
                checks = [f"if ({numeric[kind]} < std::numeric_limits<{native}>::min() || "
                          f"{numeric[kind]} > std::numeric_limits<{native}>::max()) "
                          'fail(r, ERANGE, "Integer argument is outside its Qt type range");']
            return checks, f"static_cast<{native}>({numeric[kind]})"
        if kind == "enum":
            return [f"static_assert(sizeof({t['name']}) <= 4);"], f"static_cast<{t['name']}>({value}.word)"
        if kind == "flags":
            return [f"static_assert(sizeof({t['name']}) <= 4);"], f"{t['name']}::fromInt({value}.word)"
        if kind == 'enum64':
            return [f"static_assert(sizeof({t['name']}) == 8);"], f"static_cast<{t['name']}>(wide_bits({value}))"
        if kind == 'flags64':
            return [f"static_assert(sizeof({t['name']}) == 8);"], f"{t['name']}::fromInt(wide_bits({value}))"
        raise ValueError(kind)

    def store_result(self, t, expression):
        core_pointer = core_pointer_results.store(self, t, expression)
        if core_pointer is not None:
            return core_pointer
        native_view = native_result_views.store(self, t, expression)
        if native_view is not None:
            return native_view
        function = native_function_callbacks.store(self, t, expression)
        if function is not None:
            return function
        row = form_rows.store(self, t, expression)
        if row is not None:
            return row
        data = model_data.store(self, t, expression)
        if data is not None:
            return data
        interop = native_interop.store(self, t, expression)
        if interop is not None:
            return interop
        synchronization = gl_sync.store(self, t, expression)
        if synchronization is not None:
            return synchronization
        metadata = metadata_lifetimes.store(self, t, expression)
        if metadata is not None:
            return metadata
        typed = typed_views.store(self, t, expression)
        if typed is not None:
            return typed
        reply = dbus_replies.store(self, t, expression)
        if reply is not None:
            return reply
        view = borrowed_values.store(self, t, expression)
        if view is not None:
            return view
        view = memory_views.store(self, t, expression)
        if view is not None:
            return view
        expression = return_values.expression(t, expression)
        kind = t["kind"]
        if t['raw'] == 'Wire':
            return [f"r->result = write_{t['native_codec']}(r, {expression});"]
        if kind == "void": return [expression + ";"]
        if kind == 'nullptr': return [f'(void)({expression});']
        if kind == "string": return [f"r->result = string_value({expression});"]
        if kind == "string_view": return [f"r->result = string_value(({expression}).toString());"]
        if kind == 'byte_view':
            return [f"r->result.word = own(r, new QByteArray(({expression}).toByteArray()), {self.ids['QByteArray']});", 'r->result.owned_handle = r->result.word;']
        if kind == 'latin1_view':
            return [f"r->result.word = own(r, new QByteArray(({expression}).data(), ({expression}).size()), {self.ids['QByteArray']});", 'r->result.owned_handle = r->result.word;']
        if kind == 'std_string':
            return [f"r->result.word = own(r, new QByteArray(({expression}).data(), qsizetype(({expression}).size())), {self.ids['QByteArray']});", 'r->result.owned_handle = r->result.word;']
        if kind == 'character':
            return [f"r->result.word = uint32_t(static_cast<unsigned char>(({expression}).toLatin1()));"] if t['name'] == 'QLatin1Char' else [f"r->result.word = uint32_t(({expression}).unicode());"]
        if kind == 'duration':
            return [f"r->result = wide_value(uint64_t(({expression}).count()));"]
        if kind == 'object_snapshot':
            copied = f'({expression})->clone()' if t.get('clone') else f"new {t['name']}(*({expression}))"
            return [f"r->result.word = ({expression}) ? own(r, {copied}, {self.ids[t['name']]}) : 0;", 'r->result.owned_handle = r->result.word;']
        if kind == "object":
            store = 'borrow_const' if t.get('readonly') or t.get('native_const') else 'own' if t.get('owned') else 'borrow'
            return [f"r->result.word = {store}(r, {expression}, {self.ids[t['name']]});",
                    'r->result.' + ('owned_handle' if store == 'own' else 'borrowed_handle') + ' = r->result.word;']
        if kind == "value":
            value = f'std::move({expression})' if t.get('move_result') else expression
            return [f"r->result.word = own(r, new {t['name']}({value}), {self.ids[t['name']]});", 'r->result.owned_handle = r->result.word;']
        if kind == "flags": return [f"r->result.word = uint32_t(({expression}).toInt());"]
        if kind == "real": return [f"r->result = real_bits({expression});"]
        if kind in ("i64", "u64", 'enum64'): return [f"r->result = wide_value(uint64_t({expression}));"]
        if kind == 'flags64': return [f"r->result = wide_value(uint64_t(({expression}).toInt()));"]
        return [f"r->result.word = uint32_t({expression});"]

    def method_case(self, m, operation):
        f, name = m["function"], m["class"]
        mapped = thread_affinity.method_case(self, m)
        if mapped is None:
            mapped = dynamic_properties.method_case(self, m)
        if mapped is None:
            mapped = core_pointer_results.method_case(self, m)
        if mapped is None:
            mapped = native_result_views.method_case(self, m)
        if mapped is None:
            mapped = native_function_callbacks.method_case(self, m)
        if mapped is None:
            mapped = convenience_apis.method_case(self, m)
        if mapped is None:
            mapped = glyph_arrays.method_case(self, m)
        if mapped is None:
            mapped = runnable_jobs.method_case(self, m)
        if mapped is None:
            mapped = lazy_values.method_case(self, m)
        if mapped is None:
            mapped = rhi_native_handles.method_case(self, m)
        if mapped is None:
            mapped = meta_storage.method_case(self, m)
        if mapped is None:
            mapped = incubation.method_case(self, m)
        if mapped is None:
            mapped = boundary_finders.method_case(self, m)
        if mapped is None:
            mapped = image_buffers.method_case(self, m)
        if mapped is None:
            mapped = url_handlers.method_case(self, m)
        if mapped is None:
            mapped = qml_registration.method_case(self, m)
        if mapped is None:
            mapped = native_events.method_case(self, m)
        if mapped is None:
            mapped = model_data.method_case(self, m)
        if mapped is None:
            mapped = rhi_lifetimes.method_case(self, m)
        if mapped is None:
            mapped = gl_sync.method_case(self, m)
        if mapped is None:
            mapped = gl_raw_mappings.method_case(self, m)
        if mapped is None:
            mapped = byte_iterators.method_case(self, m)
        if mapped is None:
            mapped = volume_data.method_case(self, m)
        if mapped is None:
            mapped = data_proxies.method_case(self, m)
        if mapped is None:
            mapped = gl_pointers.method_case(self, m)
        if mapped is None:
            mapped = gl_retained.method_case(self, m)
        if mapped is None:
            mapped = qtest_values.method_case(self, m)
        if mapped is None:
            mapped = allocated_buffers.method_case(self, m)
        if mapped is None:
            mapped = native_interop.method_case(self, m)
        if mapped is None:
            mapped = raw_storage.method_case(self, m)
        if mapped is None:
            mapped = role_data.method_case(self, m)
        if mapped is None:
            mapped = record_values.method_case(self, m)
        if mapped is None:
            mapped = event_snapshots.method_case(self, m)
        if mapped is None:
            mapped = dbus_replies.method_case(self, m)
        if mapped is None:
            mapped = persistent_storage.method_case(self, m)
        if mapped is None:
            mapped = qml_list_lifetimes.method_case(self, m)
        if mapped is None:
            mapped = generic_arguments.method_case(self, m)
        if mapped is not None:
            self.cases.append(f'case {operation}: {{\n' + '\n'.join('    ' + line for line in mapped) + '\n}')
            return
        mapped = memory_views.method_case(self, m)
        if mapped is not None:
            self.cases.append(f'case {operation}: {{\n' + '\n'.join('    ' + line for line in mapped) + '\n}')
            return
        def input_slot(source_index):
            return m['parameters'][source_index]['input'] if 'parameters' in m else source_index
        lines = ['NativeCallScope call_scope;']
        if not f["constructor"] and not f["static"]:
            receiver = self.receiver_class(m)
            if dbus_replies.safe_receiver(f):
                lines.append(f"auto *self = get_dbus_receiver<{receiver}>(r, r->self, {self.ids[receiver]}, {str(not f['const']).lower()});")
            else:
                lines.append(f"auto *self = get<{receiver}>(r, r->self, {self.ids[receiver]}, false, {str(not f['const']).lower()});")
        arguments = []
        for i, t in enumerate(m["args"]):
            declarations, value = self.argument(t, i)
            lines += declarations
            arguments.append(value)
        for i, expression in enumerate(m.get('omitted_defaults', []), len(m['args'])):
            native = f['arguments'][i]['type']['cpp'].replace('&', '').strip()
            owner = f.get('declaring_class')
            normalized = f['arguments'][i].get('default', '')
            if owner and normalized == owner + '::' + expression:
                expression = normalized  # Scope qualification only, never a Python default replacement.
            if owner in self.classes:
                for member in self.inherited(owner):
                    if member['static'] and not member['arguments']:
                        expression = re.sub(r'(?<![\w:])' + re.escape(member['name']) + r'\s*\(',
                                            owner + '::' + member['name'] + '(', expression)
            arguments.append(f'std::remove_cv_t<{native}>{{}}' if expression == '{}' else f'static_cast<{native}>({expression})')
        lines.append("if (r->error) return true;")
        if f['declaring_class'] == 'QTest' and f['name'] == 'qCaught' and len(f['arguments']) == 3:
            lines.append('if (!std::current_exception()) return fail(r, EPERM, "QTest exception reporting requires an active native exception handler");')
        lines += rendering.before_call(self, m)
        lines += runnable_jobs.before_call(self, m)
        lines += event_loops.before_call(self, m)
        lines += thread_affinity.before_call(self, m)
        lines += convenience_apis.before_call(self, m)
        lines += value_pointer_inputs.before_call(self, m)
        lines += engine_lifetimes.before_call(self, m)
        lines += core_pointer_results.before_call(self, m)
        lines += native_result_views.before_call(self, m)
        lines += render_result_lifetimes.before_call(self, m)
        lines += webview_runtime.before_call(self, m)
        lines += rhi_snapshots.before_call(self, m)
        lines += rhi_lifetimes.before_call(self, m)
        lines += rhi_native_handles.before_call(self, m)
        lines += gl_raw_mappings.before_call(self, m)
        lines += native_interop.before_call(self, m)
        lines += buffers.gl_buffers.before_call(self, m)
        lines += memory_views.before_call(self, m)
        lines += value_lifetimes.before_call(self, m)
        lines += borrowed_values.before_call(self, m)
        lines += metadata_lifetimes.before_call(self, m)
        lines += form_rows.before_call(self, m)
        lines += value_provenance.before_call(self, m)
        lines += aggregate_fields.before_call(self, m)
        lines += pointer_fields.before_call(self, m)
        lines += video_buffers.before_call(self, m)
        lines += lazy_values.before_call(self, m)
        lines += record_values.before_call(self, m)
        lines += variant_values.before_call(self, m)
        lines += boundary_finders.before_call(self, m)
        lines += incubation.before_call(self, m)
        lines += qml_list_lifetimes.before_call(self, m)
        lines += generic_arguments.before_call(self, m)
        lines += role_data.before_call(self, m)
        lines += resource_swaps.before_call(self, m)
        retained = m.get('retention')
        if retained and not retained.get('custom'):
            i, slot = retained['input'], retained['slot']
            key = f"r->arguments[{retained['key']}].word" if retained['key'] is not None else '0'
            lines += [f'uint32_t retention_key = {key};',
                      f'int retention_index = prepare_retention(r, {slot}, retention_key, r->arguments[{i}].word);',
                      'if (r->error) return true;',
                      f'RetentionReservation retention_reservation(retention_index, r->self, {slot}, retention_key);']
        lines += retention_before_call(self, m)
        if f['name'] == 'setParent' and not f['static'] and f['declaring_class'] in ('QObject', 'QWidget'):
            lines.append('if (!can_adopt(r, a0, self)) return true;')
        if native_parent_argument(f):
            lines.append('if (!can_adopt(r, self, a0)) return true;')
        for p in f['policies']:
            if transfers_argument(f, p) and p['target_ownership'] == 3:
                i = input_slot(p['index'] - 1)
                if i is not None and i < len(m['args']):
                    lines.append(f'if (!can_transfer_handle(r, r->arguments[{i}].word)) return true;')
                    if not self.classes.get(m['args'][i].get('name'), {}).get('qobject') and not ((retained or {}).get('native') or (retained or {}).get('qsg')):
                        lines.append(f'if (auto *e = entry(r->arguments[{i}].word); e && !e->native_observed) return fail(r, ENOTSUP, "Native ownership transfer needs observed destruction");')
            if transfers_argument(f, p) and p['target_ownership'] == 3 and not f['constructor'] and not f['static']:
                i = input_slot(p['index'] - 1)
                if i is not None and i < len(m['args']) and self.classes[name].get('qobject') and self.classes.get(m['args'][i].get('name'), {}).get('qobject'):
                    lines.append(f"if (!can_adopt(r, self, a{i})) return true;")
        if not f['constructor'] and not f['static']:
            indices = {int(i) - 1 for i in re.findall(r'Shiboken::Object::setParent\(%PYSELF,\s*%PYARG_([1-9]\d*)\)', '\n'.join(f.get('snippets', [])))}
            for source in sorted(indices):
                i = input_slot(source)
                if i is not None and i < len(m['args']) and m['args'][i]['kind'] == 'object':
                    lines.append(f'if (!can_adopt(r, self, a{i})) return true;')
        output_values = []
        if m.get('outputs'):
            native_arguments = []
            for p in m['parameters']:
                i, t = p['source'], p['type']
                if t.get('buffer', {}).get('writable_array'):
                    lines.append(f"auto out{i} = std::move(*a{p['input']});")
                    native_arguments.append(f'out{i}.data()')
                    output_values.append(f'out{i}')
                elif p['output'] or p['mutable']:
                    native = t['cpp'].replace('const ', '').replace('&', '').strip()
                    init = '{}' if p['output'] else ' = ' + arguments[p['input']]
                    lines.append(f'{native} out{i}{init};')
                    native_arguments.append(('&' if p['output'] or p.get('inout_pointer') else '') + f'out{i}')
                    output_values.append(f'out{i}')
                else:
                    native_arguments.append(arguments[p['input']])
            arguments = native_arguments
        lines += converter_cleanup.before_call(self, m)
        lines += moves.before_call(self, m)
        lines += engine_lifetimes.before_native(self, m)
        if f['signal']:
            lines += signals.connect_case(self, m)
        elif f["constructor"]:
            lines += [f"r->result.word = {native_objects.construct_owned(self, name, arguments, function=f)};"]
            lines.append('r->result.owned_handle = r->result.word;')
            lines += moves.after_native(self, m)
            lines += converter_cleanup.after_native(self, m)
            if self.classes[name].get('native_observable'):
                lines.append('mark_native_observed(r->result.word);')
            lines.append('reconcile_parents();')
            for p in f['policies']:
                if transfers_argument(f, p) and p['target_ownership'] == 3 and not ((retained or {}).get('native') or (retained or {}).get('qsg')):
                    i = input_slot(p['index'] - 1)
                    if i < len(m['args']):
                        lines.append(f"set_owned(r->arguments[{i}].word, false);")
        else:
            owner = f.get('implementing_class') or f['declaring_class']
            arguments = buffers.call_arguments(f, arguments)
            arguments = value_pointer_inputs.call_arguments(f, arguments)
            if f.get('rhi_range_adapter'):
                arguments = [f'({arguments[0]}).cbegin()', f'({arguments[0]}).cend()']
            if f.get("native_call"):
                expression = f"{f['native_call']}({', '.join(arguments)})"
            elif f["static"]:
                expression = (owner + '::' if owner else '') + f"{f['name']}({', '.join(arguments)})"
            elif f.get('free_operator'):
                expression = native_operators.expression(f, arguments)
            elif native_operators.conversion_name(f):
                expression = f"static_cast<{f['return']['cpp']}>(*self)"
            else:
                receiver = f"static_cast<{'const ' if f['const'] else ''}{owner} *>(self)->"
                expression = f"{receiver}{f['name']}({', '.join(arguments)})"
            types = native_member_parameters(f, owner)
            if types is not None:
                qualifier = ' const' if f['const'] else ''
                signature = f"{f['return']['cpp']} ({owner}::*)({types}){qualifier}"
                member = f"static_cast<{signature}>(&{owner}::{f['name']})"
                expression = f"(self->*{member})({', '.join(arguments)})"
            protected_call = protected_members.expression(self, f, arguments)
            if protected_call is not None:
                expression = protected_call
            ret = m.get('native_return', m['return'])
            if ret['kind'] == 'void':
                lines.append(expression + ';')
            else:
                lines.append('decltype(auto) returned = ' + expression + ';')
            lines += moves.after_native(self, m)
            lines += converter_cleanup.after_native(self, m)
            lines += buffers.after_call(self, m)
            lines += resource_swaps.after_native(self, m)
            lines += aggregate_fields.after_native(self, m)
            lines += pointer_fields.after_native(self, m)
            lines += variant_values.after_native(self, m)
            lines += boundary_finders.after_native(self, m)
            lines += role_data.after_native(self, m)
            lines += model_indices.after_native(self, m)
            lines.append('reconcile_parents();')
            for p in f['policies']:
                if transfers_argument(f, p) and not ((retained or {}).get('native') or (retained or {}).get('qsg')):
                    i = input_slot(p['index'] - 1)
                    if i < len(m['args']):
                        lines.append(f"set_owned(r->arguments[{i}].word, " + ('true' if p['target_ownership'] == 2 else 'false') + ');')
            if hasattr(retention_module, 'before_result'):
                lines += retention_module.before_result(self, m)
            lines += engine_lifetimes.before_result(self, m)
            lines += render_result_lifetimes.before_result(self, m)
            lines += qio_pipe.before_result(self, m)
            if m.get('outputs'):
                first = '&returned' if ret['kind'] == 'object' and f['return']['reference'] else return_values.expression(ret, 'returned')
                values = ([] if ret['kind'] == 'void' else [first]) + output_values
                lines.append(f'r->result = sequence_value({len(values)});')
                for i, (t, value) in enumerate(zip(m['return']['children'], values)):
                    lines.append(f"if (!r->error) r->result.items[{i}] = write_{t['native_codec']}(r, {value});")
            elif ret['kind'] != 'void':
                value = '&returned' if ret['kind'] == 'object' and f['return']['reference'] else 'returned'
                lines += self.store_result(ret, value)
            if retained and not retained.get('custom'):
                i = retained['input']
                confirm = f"a{i} && " if retained.get('null_resets_default') else ''
                lines += [f"if (!entry(r->self) || ({'r->arguments[' + str(i) + '].word'} && !entry(r->arguments[{i}].word))) return fail(r, ESTALE, \"Retained object was destroyed\");",
                          f"if ({confirm}{retained['accessor']}(self, retention_key) != a{i}) return fail(r, EINVAL, \"Qt rejected the retained argument\");",
                          f"commit_retention(retention_index, r->self, {retained['slot']}, retention_key, r->arguments[{i}].word, {retained['accessor']});"]
        lines += retention_after_call(self, m)
        lines += convenience_apis.after_call(self, m)
        lines += value_pointer_inputs.after_call(self, m)
        lines += value_lifetimes.after_call(self, m)
        lines += borrowed_values.after_call(self, m)
        lines += metadata_lifetimes.after_call(self, m)
        lines += core_pointer_results.after_call(self, m)
        lines += render_result_lifetimes.after_call(self, m)
        lines += form_rows.after_call(self, m)
        lines += value_provenance.after_call(self, m)
        lines += aggregate_fields.after_call(self, m)
        lines += pointer_fields.after_call(self, m)
        lines += video_buffers.after_call(self, m)
        lines += lazy_values.after_call(self, m)
        lines += variant_values.after_call(self, m)
        lines += generic_arguments.after_call(self, m)
        lines += rhi_lifetimes.after_call(self, m)
        lines += rhi_native_handles.after_call(self, m)
        lines.append("return true;")
        self.cases.append(f"case {operation}: {{\n" + "\n".join("    " + line for line in lines) + "\n}")

    def emit_effect(self, public, params, ret, operation, *, has_self=False, alias=None, doc=None):
        effect_transport.emit(self, public, params, ret, operation,
                              has_self=has_self, alias=alias, doc=doc)

    def emit_scope(self, name, release):
        self.bend += [
            f"def {name}.with(-A: Type, acquire: Action({name}), body: {name} -> Action(A)) -> Action(A):",
            f"  Action.using({name}, A, acquire, value => Action.cleanup({name}.{release}(value)), body)",
            ""]

    def receiver_class(self, m):
        if m.get('retention'):
            # A derived property getter may differ from the inherited setter's
            # declaring class. Verify the public receiver before its accessor cast.
            return m['class']
        owner = m['function'].get('implementing_class') or m['function']['declaring_class']
        return owner if owner in self.ids and self.classes[owner]['qobject'] else m['class']

    def emit(self):
        from module_partitions import emit_loader
        emit_loader(self)
        lazy_values.prepare(self)
        aggregate_fields.prepare(self)
        native_function_callbacks.prepare(self)
        custom_signals.prepare(self)
        scope_actions.emit(self)
        void = {"kind": "void", "bend": "Unit", "raw": "Unit"}
        word = {"kind": "u32", "bend": "U32", "raw": "U32"}
        for name in self.selected:
            from module_partitions import exports_class
            if not exports_class(self, name):
                continue
            t = {"kind": "object", "bend": ident(name), "raw": "U32"}
            guarded_value = name in self.lazy_values or name == video_buffers.MAP or name == 'ModelData' or name in self.aggregate_fields or name in value_provenance.TYPES or name in value_lifetimes.TYPES or name in borrowed_values.EPHEMERAL_TYPES or name in metadata_lifetimes.VALUES or name in model_indices.TYPES or name in generic_arguments.TYPES or variant_values.cleanup_safe(self, name) or (name.startswith('QRhi') and not self.classes[name]['object'])
            validity = ', false, false, false' if guarded_value else (', false, false, !is_value_view_handle(r->self)' if name in borrowed_values.VIEW_TYPES else '')
            operation = self.next_id
            self.next_id += 1
            self.cases.append(f"case {operation}: {{\n"
                              f"    if (!dbus_cleanup_precheck(r, r->self, {self.ids[name]})) get<{name}>(r, r->self, {self.ids[name]}{validity});\n"
                              "    return r->error ? true : destroy_object(r);\n}")
            self.emit_effect(ident(name) + ".destroy", [("self", t)], void, operation, has_self=True)
            release_op = self.next_id
            self.next_id += 1
            self.cases.append(f"case {release_op}: {{\n"
                              f"    if (!dbus_cleanup_precheck(r, r->self, {self.ids[name]})) get<{name}>(r, r->self, {self.ids[name]}, false, false{', false' if guarded_value else ', !is_value_view_handle(r->self)' if name in borrowed_values.VIEW_TYPES else ''});\n"
                              "    return r->error ? true : release_object(r);\n}")
            self.emit_effect(ident(name) + '.release', [('self', t)], void, release_op, has_self=True)
            self.emit_scope(ident(name), "release")
            scope_actions.escapes(self, ident(name))
        prepare_adapters(self)
        public_fields.prepare(self)
        if 'QSGGeometry::AttributeSet' in self.ids:
            pointer_fields.attributes_type(self)
        typed_views.prepare(self)
        role_data.prepare(self)
        rhi_lifetimes.prepare(self)
        data_streams.prepare(self)
        self.bend.append(self.conversions.bend())
        rendering.emit(self)
        callbacks.emit(self)
        native_function_callbacks.emit(self)
        mutex_lockers.emit(self)
        cursor_guards.emit(self)
        touch_sequences.emit(self)
        post_routines.emit(self)
        converter_cleanup.bend_helpers(self)
        converter_cleanup.emit(self)
        rhi_cleanup.emit(self)
        signals.emit(self)
        self.emit_effect("Runtime.liveObjects", [], word, 3)
        self.emit_effect("Runtime.liveConnections", [], word, 4)
        self.emit_effect("Runtime.liveRetentions", [], word, 5)
        application_objects.emit(self)
        abi_cohorts.emit(self)
        emit_adapters(self)
        data_streams.emit(self)
        public_fields.emit(self)
        converter_cleanup.annotate(self)
        child_lookup.annotate(self)
        pointer_fields.emit(self)
        video_buffers.emit(self)
        lazy_values.emit(self)
        form_rows.emit(self)
        typed_views.emit(self)
        role_data.emit(self)
        metadata_lifetimes.emit(self)
        generic_arguments.emit(self)
        model_data.emit(self)
        native_events.emit(self)
        rhi_lifetimes.emit(self)
        rhi_native_handles.emit(self)
        image_buffers.emit(self)
        incubation.emit(self)
        native_methods = {}
        for m in self.methods:
            if touch_sequences.public_adapter(self, m):
                continue
            f = m["function"]
            key = (m['class'] if f['constructor'] else self.receiver_class(m),
                   native_operators.identity(f), json.dumps(m['args'], sort_keys=True), json.dumps(m['return'], sort_keys=True))
            previous = native_methods.get(key)
            operation = previous['operation'] if previous else self.next_id
            if not previous:
                self.next_id += 1
                native_methods[key] = m
            m["operation"] = operation
            if not previous:
                self.method_case(m, operation)
                application_objects.guard(self, m, operation)
            has_self = not (f["constructor"] or f["static"])
            params = [(f"arg{i}", t) for i, t in enumerate(m["args"])]
            if has_self:
                params.insert(0, ("self", {"bend": ident(m["class"]), "raw": "U32"}))
            if f['signal']:
                signals.entry(self, m, operation, doc=overload_names.signature_comment(m))
                continue
            self.emit_effect(m["bend_name"], params, m["return"], operation, has_self=has_self,
                             alias=previous['bend_name'] if previous else None,
                             doc=overload_names.signature_comment(m))
        url_handlers.emit(self)
        custom_signals.emit(self)
        qt_objects.emit(self)
        qml_list_properties.emit(self)
        generic_variants.emit(self)
        value_types.emit(self)
        convenience_apis.emit(self)
        convenience_apis.annotate(self)
        core_pointer_results.annotate(self)
        native_function_callbacks.annotate(self)
        proxies = callbacks.cpp(self)
        # Protected members and engine hooks can check native children in a
        # group where no other emitter registered the shared helpers.
        if any('native_children_idle(' in case for case in self.cases):
            import native_lifetimes
            native_lifetimes.prepare(self)
        native = ((HERE / 'templates/native_snapshots.cpp').read_text() + (HERE / 'templates/callbacks.cpp').read_text() + child_lookup.cpp(self) + rhi_lifetimes.cpp(self) + rhi_native_handles.cpp(self) + borrowed_values.cpp(self) + value_lifetimes.cpp(self) + moves.cpp(self) + resource_swaps.cpp(self) + (HERE / 'templates/native_model_lifetimes.cpp').read_text()
                  + (HERE / 'templates/retention_extra.cpp').read_text()
                  + retention_module.cpp(self) + metadata_lifetimes.cpp(self) + role_data.cpp(self) + model_indices.cpp(self) + qml_list_lifetimes.cpp(self) + dbus_replies.cpp(self) + persistent_storage.cpp(self) + rendering.cpp(self) + gl_raw_mappings.declarations(self) + memory_views.cpp(self) + gl_raw_mappings.cpp(self) + gl_retained.cpp(self) + gl_pointers.cpp(self) + byte_iterators.cpp(self) + volume_data.cpp(self) + typed_views.cpp(self) + buffers.gl_buffers.cpp(self)
                  + (HERE / 'templates/callback_results.cpp').read_text()
                  + message_handlers.cpp(self)
                  + webview_runtime.cpp(self)
                  + rhi_cleanup.cpp(self)
                  + converter_cleanup.cpp(self)
                  + runnable_jobs.cpp(self)
                  + form_rows.declarations(self) + self.conversions.cpp_code() + ''.join(self.retention_accessors.values()) + form_rows.cpp(self) + value_provenance.cpp(self) + aggregate_fields.cpp(self) + pointer_fields.cpp(self) + video_buffers.cpp(self) + lazy_values.cpp(self)
                  + core_pointer_results.cpp(self) + touch_sequences.cpp(self) + render_result_lifetimes.cpp(self) + convenience_apis.declarations(self) + proxies + native_function_callbacks.cpp(self) + mutex_lockers.cpp(self) + cursor_guards.cpp(self) + post_routines.cpp(self) + gl_sync.cpp(self) + native_interop.cpp(self) + variant_values.cpp(self) + meta_storage.cpp(self) + qtest_values.cpp(self) + generic_arguments.cpp(self) + model_data.cpp(self) + image_buffers.cpp(self) + boundary_finders.cpp(self) + incubation.cpp(self) + url_handlers.cpp(self) + bend_data.cpp(self) + custom_signals.cpp(self) + qml_registration.cpp(self)
                  + qt_objects.cpp(self) + generic_variants.cpp(self) + value_types.cpp(self) + dynamic_properties.cpp(self) + convenience_apis.cpp(self) + scope_actions.cpp(self) + self.dispatch())
        # Provenance validation interprets its slot; any reuse corrupts validation.
        if len(re.findall(r'0x[fF]{6}[dD]8', native)) != 1:
            raise ValueError('The value provenance retention slot must not be reused')
        access = protected_members.declarations(self) + protected_fields.declarations(self)
        native = access + protected_members.rewrite_cpp(self, native)
        return self.prelude() + "\n".join(self.bend) + '\n' + dbus_replies.bend(self), effect_transport.effects(self), native

    def prelude(self):
        # Prove the standalone source itself; inline the same definitions into
        # the consumer module without introducing a second Base import.
        action = (HERE / "templates/action.bend").read_text()
        if not action.startswith("import Base\n\n"):
            raise ValueError("The proof-checked Action source must import Base")
        out = [f"# Generated from Qt {self.api['qt_headers']} headers by Shiboken ApiExtractor. Do not edit.", "import Base", "",
               action.removeprefix("import Base\n\n"), ""]
        out += [(HERE / 'templates/codec.bend').read_text().removeprefix('import Base\n\n'), '']
        out += [(HERE / 'templates/lifetime.bend').read_text().removeprefix('import Base\n\n'), '']
        for name in sorted(self.types):
            if self.types[name] == "wide":
                out += [f"type {name} is Data:", f"  {name}{{lo: U32, hi: U32}}", "",
                        f"def {name}.lo(value: {name}) -> U32:", "  match value:", f"    case {name}{{lo, hi}}: lo", "",
                        f"def {name}.hi(value: {name}) -> U32:", "  match value:", f"    case {name}{{lo, hi}}: hi", "",
                        f"def {name}.wrap(result: {result_type('U32 & U32')}) -> {result_type(name)}:",
                        "  match result:", "    case Fail{error}: Fail{error}",
                        f"    case Done{{(lo, hi)}}: Done{{{name}{{lo, hi}}}}", ""]
                continue
            field = "bits" if self.types[name] == "scalar" else "handle"
            out += [f"type {name} is Data:", f"  {name}{{{field}: U32}}", "",
                    f"def {name}.word(value: {name}) -> U32:", "  match value:",
                    f"    case {name}{{word}}:", "      word", "",
                    f"def {name}.wrap(result: {result_type('U32')}) -> {result_type(name)}:",
                    "  match result:", "    case Fail{error}:", "      Fail{error}",
                    "    case Done{value}:", f"      Done{{{name}{{value}}}}", ""]
        out += ["def Int32.neg(magnitude: U32) -> Int32:", "  Int32{(0 - magnitude : U32)}", "",
                "def bool_word(value: Bool) -> U32:", "  match value:", "    case False{}:", "      0",
                "    case True{}:", "      1", "",
                f"def bool_wrap(result: {result_type('U32')}) -> {result_type('Bool')}:",
                "  match result:", "    case Fail{error}:", "      Fail{error}",
                "    case Done{value}:", "      Done{U32.is_ne(value, 0)}", ""]
        for name in self.selected:
            for base in self.all_bases(name):
                if not self.classes[name]['qobject'] and not self.classes[name].get('native_object'):
                    continue  # Value upcasts copy their base value in adapters.py.
                cast_base = base
                qualified = getattr(self, 'partition_qualified_types', {})
                if name in qualified.values():
                    namespace = name.split('::', 1)[0] + '::'
                    if base.startswith(namespace):
                        cast_base = base[len(namespace):]
                out += [f"def {ident(name)}.as_{c_ident(cast_base)}(self: {ident(name)}) -> {ident(base)}:",
                        f"  {ident(base)}{{{ident(name)}.word(self)}}", ""]
        for name, enum in sorted(self.enums.items()):
            if ident(name) not in self.types: continue
            for value in enum["values"]:
                number = int(value["value"], 0)
                wide = self.types[ident(name)] == 'wide'
                bits = 64 if wide else 32
                if not -(1 << (bits - 1)) <= number < (1 << bits):
                    raise ValueError(f"Enum {name} exceeds its representation")
                fields = str(number & 0xffffffff) + (f', {(number >> 32) & 0xffffffff}' if wide else '')
                out += [f"def {ident(name)}.{value['name']}() -> {ident(name)}:",
                        f"  {ident(name)}{{{fields}}}", ""]
        return "\n".join(out) + "\n"

    def all_bases(self, name):
        bases = set()
        for base in self.classes[name]["bases"]:
            if base in self.ids:
                bases.add(base)
                bases.update(self.all_bases(base))
        return sorted(bases)

    def dispatch(self):
        functions, cases = [], []
        for case in self.cases:
            match = re.fullmatch(r'case (\d+): \{\n(.*)\n\}', case, re.S)
            if not match:
                raise ValueError('Malformed generated native operation: ' + case[:160])
            operation, body = match.groups()
            body = abi_cohorts.operation(self, operation, body)
            name = 'bqt_op_' + operation
            functions.append(f'static bool __attribute__((noinline)) {name}(BqtRequest *r) {{\n{body}\n}}')
            cases.append(f'    case {operation}: return {name}(r);')
        return '\n'.join(functions) + "\n" + """static bool dispatch(BqtRequest *r) {
    switch (r->operation) {
    case 0: return destroy_object(r);
    case 2: return disconnect_signal(r);
    case 3:
    {
        // The application object is runtime-owned, not a leakable handle.
        // QCoreApplication::instance() stays set while Qt runs post routines
        // from the application destructor, after teardown cleared `application`.
        const QObject *app = QCoreApplication::instance();
        for (const auto &e : entries) if (e.value && !(e.object && e.object == app)) ++r->result.word;
        return true;
    }
    case 4:
        for (const auto &c : connections) if (c.active) ++r->result.word;
        return true;
    case 5:
        for (const auto &edge : retentions) if (edge.owner && edge.target) ++r->result.word;
        return true;
""" + "\n".join(cases) + "\n    default: return fail(r, ENOSYS, \"Unknown generated Qt operation\");\n    }\n}\n"


def generation_inputs(profile):
    files = [ROOT / 'LICENSE', *HERE.glob('*.py'), *HERE.glob('*.cpp'), *HERE.glob('*.h'), HERE / 'qt_targets.json',
             HERE / 'CMakeLists.txt', *HERE.glob('templates/*'), *profile.glob('*')]
    return {str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path):
            hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(set(files)) if path.is_file()}


def extraction_inputs(profile):
    """Sources that determine the reusable ApiExtractor model, not its emitters."""
    names = ('generate.py', 'upstream.py', 'backend.py', 'pyside_boundary.py',
             'gl_inventory.py', 'public_records.py', 'qobject_interfaces.py',
             'qio_pipe.py', 'qt_targets.py', 'qt_targets.json', 'CMakeLists.txt', 'templates/qio_pipe.h',
             'distribution_modules.py', 'module_partitions.py', 'qt_licenses.py', 'adapters.py',
             'generic_arguments.py', 'metadata_lifetimes.py', 'model_indices.py', 'value_lifetimes.py')
    files = [*(HERE / name for name in names), *HERE.glob('*.cpp'),
             *HERE.glob('*.h'), profile / 'profile.json']
    return {str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path):
            hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(set(files)) if path.is_file()}


def reviewed_name_removals(path):
    data = json.loads(path.read_text())
    rows = data.get('reviewed') if isinstance(data, dict) else None
    if not isinstance(rows, list) or any(
            not isinstance(row, list) or len(row) != 2
            or any(not isinstance(item, str) or not item for item in row) for row in rows):
        raise ValueError('Reviewed name removals must contain a reviewed list of [owner, public_name] pairs')
    return {tuple(row) for row in rows}


def preflight_names(generator, work, source_inputs, reviewed=None, acknowledge=False):
    """Review this exact collection before changing the lock or compiling C++."""
    lock = generator.name_lock
    pending = lock.unacknowledged()
    result = dict(methods=len(generator.methods), removed=lock.tombstoned,
                  unacknowledged=pending, reshaped=lock.reshaped, created=lock.created,
                  source_sha256=source_inputs)
    if reviewed is not None:
        allowed = reviewed_name_removals(reviewed)
        unexpected = sorted(set(pending) - allowed)
        result.update(reviewed=sorted(allowed), unexpected=unexpected)
    else:
        unexpected = []
    json_write(work / 'name-lock-preflight.json', result)
    if unexpected:
        raise ValueError('Unexpected removed public names (see name-lock-preflight.json): '
                         + ', '.join(name for _, name in unexpected))
    if acknowledge:
        lock.acknowledge()
        result['acknowledged'] = pending
    return result


def extract_api(args, profile, modules, work):
    """Prepare one mutually compatible native header inventory."""
    headers, typesystem, modules, extraction_env, upstream = prepare(
        args.pyside_source, args.qt_prefix, modules, work, limited_abi=profile.get('limited_abi', False))
    logdir = work / 'extractor'
    logdir.mkdir(exist_ok=True)
    include_paths = [args.qt_prefix / 'include', args.qt_prefix / 'mkspecs/linux-g++']
    include_paths += [args.qt_prefix / 'include' / module for module in modules]
    from backend import versioned_include_paths
    include_paths += versioned_include_paths(args.qt_prefix, modules)
    extracted = command([args.extractor, headers, typesystem, work / 'api.json', logdir, *include_paths], env=extraction_env)
    (work / 'extraction.log').write_text(extracted.stdout + extracted.stderr)
    api = json.loads((work / 'api.json').read_text())
    import gl_inventory
    gl_inventory.restore(api, headers, args.extractor, include_paths, work, extraction_env)
    public_records.restore(api, headers, include_paths, work)
    qobject_interfaces.restore(api, work)
    qio_pipe.restore(api, work)
    api = pyside_boundary.apply(api)
    json_write(work / 'api.json', api)
    import qt_targets
    target = qt_targets.target(profile['minimum_qt'])
    if (api['qt_headers'] != target['qt'] or api['qt_runtime'] != target['qt']
            or api['shiboken_commit'] != target['shiboken_commit']):
        raise ValueError('Use the matching pinned Qt kit and Shiboken extractor for ' + target['qt'])
    return api, headers, modules, upstream, logdir


def native_source(generator, api, headers, qt_prefix, work, abi, lifetime_policy):
    aliases = ''.join(f'using {name} = {source};\n' for name, source in api['typedefs'].items()
                      if name in generator.ids and '::' not in name)
    aliases += getattr(generator, 'partition_aliases', '') + representations.aliases(generator)
    qml_prefix, qml_suffix = callbacks.qml_sources(generator, qt_prefix, work)
    version = api['qt_headers']
    runtime = (HERE / 'templates/runtime.cpp').read_text()
    # A native group without GUI modules, such as the Core-based shared group,
    # compiles the runtime without their parts.
    gui = ''.join(f'#define BQT_HAS_{module[2:].upper()} 1\n' for module in ('QtGui', 'QtWidgets')
                  if module in generator.profile['qt_modules'])
    cpp = (headers.read_text() + native_header_support(generator.profile['qt_modules']) + aliases + qml_prefix
           + '\n#if QT_VERSION != QT_VERSION_CHECK(' + ', '.join(version.split('.'))
           + ')\n#error "Generate with Qt ' + version + ' headers"\n#endif\n'
           + gui + '#define BQT_BUNDLED_RUNTIME_NATIVE 1\n'
           + (HERE / 'templates/runtime_paths.cpp').read_text()
           + runtime + qml_suffix)
    return cpp.replace('// @ABI@', abi).replace('// @LIFETIME@', cpp_tables(lifetime_policy)).replace(
        '// @NATIVE_OBJECTS@', native_objects.traits(generator))


def coverage_report(generator, api, profile, license_report, runtime_bundle, lifetime_policy, backend, measured_traits, modules, upstream, omissions):
    coverage = {"schema": 1, "extractor": api["extractor"], "qt_headers": api["qt_headers"],
                'native_coverage': coverage_inventory.inventory(generator),
                'effect_transport': effect_transport.inventory(generator),
                'lifetime_policy': lifetime_policy,
                "shiboken_commit": api["shiboken_commit"],
                "minimum_qt": profile["minimum_qt"], "runtime_qt": api['qt_runtime'], "classes": generator.selected,
                'qt_licensing': license_report,
                'bundled_runtime': runtime_bundle['manifest'] if runtime_bundle else None,
                'namespaces': generator.namespaces, 'argument_capacity': generator.argument_capacity,
                'callbacks': callbacks.inventory(generator),
                'value_provenance': value_provenance.inventory(generator),
                'pyside_boundary': generator.api['pyside_boundary'],
                'public_record_supplement': api.get('public_record_supplement', {}),
                'abi_cohorts': abi_cohorts.inventory(generator),
                'native_payload': backend['payload'],
                'public_abi_payload': backend.get('public_abi_fallback', {}).get('payload'),
                'native_type_traits': measured_traits,
                'public_fields': generator.public_fields,
                'render_result_lifetimes': render_result_lifetimes.inventory(generator),
                'qio_pipe': qio_pipe.inventory(generator),
                'qobject_interfaces': qobject_interfaces.inventory(generator),
                'touch_sequences': touch_sequences.inventory(generator),
                'mutex_lockers': mutex_lockers.inventory(generator),
                'cursor_guards': cursor_guards.inventory(generator),
                'excluded_fields': generator.excluded_fields,
                "upstream": upstream, "additive_extraction": api.get('additive_extraction', []),
                "excluded_classes": generator.excluded_classes,
                "qt_modules": modules, "generated_enums": sorted(name for name in generator.enums if ident(name) in generator.types),
                "generated_count": len(generator.methods),
                "generated_native_method_count": len({m['operation'] for m in generator.methods}),
                "representation_adapters": ['F64', 'Int64', 'UInt64', '64-bit enums/flags', 'Qt integer aliases',
                    'QVariant', 'UTF-8 QByteArray', 'binary QByteArray', 'owning QByteArrayView snapshots',
                    'checked QObject downcasts', 'recursive containers', 'multi-argument signals', 'overloaded signals',
                    'mutable signal arguments', 'native default arguments',
                    'mutable references', 'scalar output parameters', 'QObject ownership transfers', 'arithmetic/comparison/assignment operators'],
                'container_conversions': sorted({t['cpp'] for t in generator.conversions.cpp.values() if t['kind'] in ('list', 'map', 'pair')}),
                'signal_payloads': signals.inventory(generator),
                'custom_signals': custom_signals.inventory(generator),
                'qt_objects': qt_objects.inventory(generator),
                'generic_variants': generic_variants.inventory(generator),
                'value_types': value_types.inventory(generator),
                'data_streams': data_streams.inventory(generator),
                'native_function_callbacks': getattr(generator, 'native_function_callback_operations', {}),
                'qml_list_properties': qml_list_properties.inventory(generator),
                'post_routines': getattr(generator, 'post_routine_operations', {}),
                'protected_members': getattr(generator, 'protected_member_inventory', {}),
                'value_pointer_inputs': value_pointer_inputs.inventory(generator),
                'convenience_apis': convenience_apis.inventory(generator),
                'resource_scopes': scope_actions.inventory(generator),
                'byte_view_entry_points': sum(m['return']['kind'] == 'byte_view' or any(a['kind'] == 'byte_view' for a in m['args']) for m in generator.methods),
                'default_argument_entry_points': sum('omitted_defaults' in m for m in generator.methods),
                'output_record_entry_points': sum(bool(m.get('outputs')) for m in generator.methods),
                'mutable_reference_entry_points': sum(any(a['type']['reference'] == 1 and not a['type']['const'] for a in m['function']['arguments']) for m in generator.methods),
                'operator_entry_points': sum(m['function']['operator'] for m in generator.methods),
                'retention_entry_points': sum(bool(m.get('retention')) for m in generator.methods),
                'retention_properties': generator.retention_slots,
                "full_coverage": False,
                "extracted_class_count": sum(not c['namespace'] for c in api['classes']),
                "excluded_reasons": dict(Counter(e['reason'] for e in generator.excluded).most_common()),
                "generated": [{"class": m["class"], "signature": m["function"]["signature"],
                               "bend_name": m["bend_name"], "arguments": [a["bend"] for a in m["args"]],
                               "return": m["return"]["bend"], "operation": m["operation"],
                               'argument_conversions': [coverage_inventory.conversion_policy(t) for t in m['args']],
                               'return_conversion': coverage_inventory.conversion_policy(m['return']),
                               **({'signal_handler': dict(arguments=m['signal']['kind']['arguments'],
                                    reply=m['signal']['kind']['reply']['bend'],
                                    mutable_arguments=[i for i, _ in m['signal']['outputs']])} if 'signal' in m else {}),
                               'restored_native_arguments': m['function'].get('restored_native_arguments', []),
                               'omitted_native_callback': m['function'].get('omitted_native_callback'),
                               'adaptation': m['function'].get('adaptation'),
                               "return_ownership": ('owned' if m['return'].get('owned') or m['return']['kind'] in ('value', 'object_snapshot', 'byte_view', 'latin1_view', 'std_string')
                                                    else 'borrowed' if m['return']['kind'] == 'object' else 'value'),
                               "default_constructor": m["default_constructor"],
                               'omitted_defaults': m.get('omitted_defaults', [])} for m in generator.methods],
                "excluded": generator.excluded, "extraction_omissions": omissions,
                # Supported through the named overload; listed so no C++
                # signature disappears from the inventory.
                'merged_overloads': generator.merged_overloads,
                'removed_names': generator.name_lock.removed,
                "external_symbol_count": len(backend["undefined_symbols"])}
    return coverage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=HERE / "qt612")
    parser.add_argument("--qt-prefix", type=Path, default=CACHE / "Qt/6.12.0/gcc_64")
    parser.add_argument("--extractor", type=Path, default=CACHE / "build/bend-qt-extract")
    parser.add_argument("--pyside-source", type=Path, default=CACHE / "pyside-setup")
    parser.add_argument("--output", type=Path, default=ROOT / "packages/qt612")
    parser.add_argument("--work", type=Path, default=ROOT / "build/qt612")
    parser.add_argument("--cxx", default="clang++-19")
    parser.add_argument('--runtime-manifest', type=Path,
                        help='Byte-pinned runtime files, notices and matching source-delivery artifacts for a bundled distribution')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--syntax-only', action='store_true', help='Check generated C++ without replacing package artifacts')
    mode.add_argument('--emit-only', action='store_true', help='Write maintainer extraction and native source without compiling or replacing package artifacts')
    mode.add_argument('--extract-only', action='store_true', help='Write a reusable API extraction without collecting bindings or compiling native wrappers')
    parser.add_argument('--acknowledge-removed-names', action='store_true',
                        help='Accept every removed public name recorded in the profile name lock as an intended breaking change')
    parser.add_argument('--reviewed-name-removals', type=Path,
                        help='Reject removals outside this reviewed [owner, public_name] inventory before acknowledgement or native compilation')
    args = parser.parse_args()
    if args.extract_only and (args.acknowledge_removed_names or args.reviewed_name_removals):
        parser.error('Name-lock review applies to binding generation, not --extract-only')
    reviewed_digest = None
    if args.reviewed_name_removals:
        reviewed_name_removals(args.reviewed_name_removals)
        reviewed_digest = hashlib.sha256(args.reviewed_name_removals.read_bytes()).hexdigest()
    source_inputs = generation_inputs(args.profile)
    extraction_source_inputs = extraction_inputs(args.profile)
    profile = json.loads((args.profile / "profile.json").read_text())
    runtime_release_inputs = None
    if not (args.extract_only or args.emit_only or args.syntax_only):
        if profile.get('license_flavor') and not args.runtime_manifest:
            raise ValueError('A distributable Qt profile requires --runtime-manifest with verified bundled runtime, notices and corresponding source artifacts')
        if args.runtime_manifest:
            import runtime_release
            runtime_release_inputs = runtime_release.prepare(args.runtime_manifest, args.qt_prefix, profile)
    import qt_targets
    qt_targets.target(profile['minimum_qt'])
    if profile.get('native_modules'):
        import distribution_modules
        return distribution_modules.generate(args, profile, source_inputs, runtime_release_inputs)
    modules = profile["qt_modules"]
    if not {"QtCore", "QtGui", "QtWidgets"}.issubset(modules) or any(
            not re.fullmatch(r"Qt[A-Za-z0-9]+", module) for module in modules):
        raise ValueError("List Qt module names, including QtCore, QtGui and QtWidgets")
    args.work.mkdir(parents=True, exist_ok=True)
    api, headers, modules, upstream, logdir = extract_api(args, profile, modules, args.work)
    license_report = None
    if profile.get('license_flavor'):
        from qt_licenses import Inventory
        license_report = Inventory(args.qt_prefix).require(modules, profile['license_flavor'])
        json_write(args.work / 'qt-licenses.json', license_report)
    if args.extract_only:
        if extraction_inputs(args.profile) != extraction_source_inputs:
            raise RuntimeError('Extraction inputs changed; the API snapshot is stale')
        names = ('api.json', 'headers.h', 'typesystem.xml', 'upstream.json',
                 'qobject-interfaces.json', 'qio-pipe.json')
        json_write(args.work / 'extraction.json', dict(
            schema=1, verification_complete=True, source_sha256=extraction_source_inputs,
            snapshot_sha256={name: hashlib.sha256((args.work / name).read_bytes()).hexdigest()
                             for name in names if (args.work / name).is_file()},
            qt=api['qt_headers'], shiboken_commit=api['shiboken_commit'], profile=profile))
        print('API extraction written without binding collection or native wrapper compilation')
        return
    measured_traits = native_objects.refine_traits(api, args.qt_prefix, modules, args.work, args.cxx)
    generator = Generator(api, profile, overload_names.NameLock.load(args.profile / 'names.lock.json'))
    lifetime_policy = evaluate_tables(args.work)
    generator.collect()
    callbacks.prepare(generator)
    overload_names.finalize(generator, generator.name_lock)
    if (reviewed_digest is not None
            and hashlib.sha256(args.reviewed_name_removals.read_bytes()).hexdigest() != reviewed_digest):
        raise RuntimeError('The reviewed-removal inventory changed before name acknowledgement')
    name_preflight = preflight_names(generator, args.work, source_inputs,
                                    args.reviewed_name_removals, args.acknowledge_removed_names)
    if reviewed_digest is not None:
        if hashlib.sha256(args.reviewed_name_removals.read_bytes()).hexdigest() != reviewed_digest:
            raise RuntimeError('The reviewed-removal inventory changed during preflight')
        name_preflight['reviewed_inventory_sha256'] = reviewed_digest
    bend, effects, dispatch = generator.emit()
    argument_capacity = generator.argument_capacity
    abi = qt_targets.abi((HERE / "templates/abi.h").read_text(), argument_capacity, api['qt_headers'])
    cpp = native_source(generator, api, headers, args.qt_prefix, args.work, abi, lifetime_policy).replace('// @DISPATCH@', dispatch)
    source = args.work / "wrappers.cpp"
    source.write_text(cpp)
    name_preflight['native_source_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    json_write(args.work / 'name-lock-preflight.json', name_preflight)
    json_write(args.work / 'abi-cohorts.json', abi_cohorts.inventory(generator))
    if args.emit_only:
        if generation_inputs(args.profile) != source_inputs:
            raise RuntimeError('Generator inputs changed during source emission; preflight is stale')
        output_files.write_text(args.work / 'emitted-api.bend', bend)
        print(f'Native source emitted: {len(generator.methods)} entries, {len(generator.selected)} classes')
        return
    if args.syntax_only:
        validate_backend(source, args.qt_prefix, args.work, args.cxx, modules)
        print(f'Native syntax passed: {len(generator.methods)} entries, {len(generator.selected)} classes')
        return
    assembly, imports, backend = abi_cohorts.compile_payloads(generator, source, args.qt_prefix, args.work, args.cxx, modules)
    proxy_traits = backend.get('proxy_constructibility')
    if proxy_traits is not None:
        if len(proxy_traits) != len(generator.callback_classes):
            raise RuntimeError('Native proxy trait count differs from the extracted proxy inventory')
        generator.callback_native_constructible = dict(zip(
            (c['name'] for c in generator.callback_classes), proxy_traits))
    additional = [module for module in modules if module not in ("QtCore", "QtGui", "QtWidgets")]
    libraries = [f"    void *libraries[{len(additional) + 1}] = {{lib}};"]
    for i, module in enumerate(additional, 1):
        libraries += [f'    libraries[{i}] = dlopen("libQt6{module[2:]}.so.6", RTLD_NOW | RTLD_LOCAL);',
                      f'    if (!libraries[{i}]) return dlerror();']
    c = (HERE / "templates/effects.c").read_text()
    for key, value in (("ABI", abi), ("ASSEMBLY", assembly), ("IMPORTS", imports),
                       ("LIBRARIES", "\n".join(libraries)), ("EFFECTS", effects)):
        c = c.replace("// @" + key + "@", value)
    runtime_bundle = None
    if runtime_release_inputs:
        runtime_bundle = runtime_release.package(runtime_release_inputs, profile, args.work)
        c = c.replace('// @RUNTIME@', runtime_bundle['c'])
        bend += '\n' + runtime_bundle['bend']
    omissions = []
    for path in sorted(logdir.glob("*.log")):
        category = ""
        for line in path.read_text().splitlines():
            if line and not line.startswith(("*", " -")): category = line
            if line.startswith(" -") and any(name + "::" in line for name in generator.selected):
                omissions.append({"log": path.name, "category": category,
                                  "detail": line.strip().replace(str(args.qt_prefix), "<QT>")})
    coverage = coverage_report(generator, api, profile, license_report, runtime_bundle, lifetime_policy, backend, measured_traits, modules, upstream, omissions)
    # Publishable inputs are written only after extraction and code packaging pass.
    if generation_inputs(args.profile) != source_inputs:
        raise RuntimeError('Generator inputs changed during the build; package artifacts were not replaced')
    if runtime_release_inputs:
        # Native compilation can take hours. Recheck source-delivery artifacts
        # and the release manifest as well as the generator's own inputs.
        refreshed = runtime_release.prepare(args.runtime_manifest, args.qt_prefix, profile)
        if (refreshed['manifest_sha256'] != runtime_release_inputs['manifest_sha256']
                or refreshed['expected_sha256'] != runtime_release_inputs['expected_sha256']):
            raise RuntimeError('Runtime release inputs changed during the build; package artifacts were not replaced')
    if (reviewed_digest is not None
            and hashlib.sha256(args.reviewed_name_removals.read_bytes()).hexdigest() != reviewed_digest):
        raise RuntimeError('Reviewed name removals changed during the build; package artifacts were not replaced')
    args.output.mkdir(parents=True, exist_ok=True)
    output_files.write_text(args.output / "qt.bend", bend)
    output_files.write_text(args.output / "qt.c", c)
    if runtime_bundle:
        output_files.write_text(args.output / 'LICENSE', runtime_release_inputs['package_license'].read_text())
        for filename, content in runtime_bundle['assets'].items():
            output_files.write_text(args.output / filename, content)
    json_write(args.output / "coverage.json", coverage)
    hashes = {name: hashlib.sha256((args.output / name).read_bytes()).hexdigest()
              for name in ("qt.bend", "qt.c", "coverage.json", *(['LICENSE', *runtime_bundle['assets']] if runtime_bundle else []))}
    # The lock is a generation input, so it changes only after a complete
    # build. The next generation reads exactly these names.
    lock = generator.name_lock
    lock.write()
    # The completed lock records the names actually emitted above. Keep its
    # incoming identity too, while making current-artifact checks compare with
    # the completed source tree rather than the superseded allocation input.
    completed_inputs = generation_inputs(args.profile)
    lock_key = str(lock.path.relative_to(ROOT) if lock.path.is_relative_to(ROOT) else lock.path) if lock.path else None
    if any(source_inputs.get(path) != completed_inputs.get(path)
           for path in source_inputs.keys() | completed_inputs.keys() if path != lock_key):
        raise RuntimeError('Generator inputs changed while completing the name lock')
    dependency_manifests = list(dict.fromkeys([
        *backend.get('native_dependency_manifests', []),
        *backend.get('public_abi_fallback', {}).get('native_dependency_manifests', [])]))
    json_write(args.work / "generation.json", {"generated_sha256": hashes, "source_sha256": completed_inputs,
                                             "runtime_release_manifest": str(args.runtime_manifest.resolve()) if args.runtime_manifest else None,
                                             "input_name_lock_sha256": source_inputs.get(lock_key), "qt": api["qt_headers"],
                                             "extractor": api["extractor"], "profile": profile,
                                             "native_dependency_manifests": dependency_manifests})
    print(f"Name lock: {len(lock.created)} new, {len(lock.carried)} carried over, {len(lock.tombstoned)} removed")
    for owner, name, reason in lock.tombstoned:
        print(f"  REMOVED {name}: {reason}")
    if lock.unacknowledged():
        print(f"WARNING: {len(lock.unacknowledged())} removed public names are unacknowledged; "
              "verification fails until they are accepted with --acknowledge-removed-names")
    print(f"Generated {len(generator.methods)} methods/signals for {len(generator.selected)} classes")
    print(f"Coverage: {len(generator.excluded)} backend exclusions, {len(omissions)} extractor omissions")
    print(f"Dynamic imports: {len(backend['undefined_symbols'])}; output: {args.output}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        print(error.stdout or "", file=sys.stderr)
        print(error.stderr or "", file=sys.stderr)
        raise SystemExit(error.returncode)
