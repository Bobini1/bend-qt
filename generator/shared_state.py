"""Move a native partition's mutable runtime storage behind the host service.

Clang resolves references before any edits. A local, field or argument with the
same spelling as a registry is consequently left alone. Included Qt headers and
template-specific caches retain their ordinary native storage.
"""
from ctypes import byref, c_char_p, c_int, c_uint, c_void_p
from bisect import bisect_right
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import re
import shlex
import subprocess
import time

from public_records import Clang, Cursor, Location, String, Type
from native_shards import Range


def _transform(path, flags, *, external=None, save_pch=None, visibility=None):
    path = Path(path).resolve()
    source = path.read_bytes()
    clang = Clang()
    for name, result, arguments in (
        ('getCursorExtent', Range, [Cursor]),
        ('getRangeStart', Location, [Range]),
        ('getRangeEnd', Location, [Range]),
        ('getCursorReferenced', Cursor, [Cursor]),
        ('getCanonicalCursor', Cursor, [Cursor]),
        ('getCursorUSR', String, [Cursor]),
        ('getCursorTLSKind', c_uint, [Cursor]),
        ('Cursor_getStorageClass', c_uint, [Cursor]),
        ('getCanonicalType', Type, [Type]),
        ('getArrayElementType', Type, [Type]),
        ('defaultSaveOptions', c_uint, [c_void_p]),
        ('saveTranslationUnit', c_int, [c_void_p, c_char_p, c_uint]),
    ):
        fn = getattr(clang.lib, 'clang_' + name)
        fn.restype, fn.argtypes = result, arguments
        setattr(clang, name, fn)

    def offset(location):
        value = c_uint()
        clang.getSpellingLocation(location, None, None, None, byref(value))
        return value.value

    def extent(cursor):
        value = clang.getCursorExtent(cursor)
        return offset(clang.getRangeStart(value)), offset(clang.getRangeEnd(value))

    def usr(cursor):
        return clang.string(clang.getCursorUSR(cursor))

    declarations, references, local_counts = {}, [], {}
    visibility_starts = [row[0] for row in visibility[1]] if visibility else []

    def visit(cursor, *, templated=False, owned=False):
        for child in clang.children(cursor):
            filename, _ = clang.location(child)
            if filename != str(path):
                # Implicit conversion/member expressions can carry the
                # included operator's location while their operand still
                # refers to a variable in this source file.
                if owned:
                    visit(child, templated=templated, owned=True)
                continue
            kind = clang.kind(child)
            if visibility and kind in ('DeclRefExpr', 'MemberRefExpr', 'TypeRef', 'TemplateRef', 'NamespaceRef'):
                referenced = clang.getCanonicalCursor(clang.getCursorReferenced(child))
                if not clang.Cursor_isNull(referenced) and clang.location(referenced)[0] == visibility[0]:
                    position = offset(clang.getCursorLocation(child))
                    section = bisect_right(visibility_starts, position) - 1
                    limit = (visibility[1][section][2] if section >= 0
                             and position < visibility[1][section][1] else None)
                    if limit is not None and offset(clang.getCursorLocation(referenced)) >= limit:
                        raise RuntimeError('A native body resolves to a declaration after its original position: '
                                           + clang.qualified(referenced))
            is_template = templated or kind in ('FunctionTemplate', 'ClassTemplate', 'ClassTemplatePartialSpecialization')
            if kind == 'VarDecl' and not is_template:
                parent = clang.getCursorSemanticParent(child)
                parent_kind = clang.kind(parent)
                local = parent_kind not in ('Namespace', 'TranslationUnit', 'StructDecl', 'ClassDecl')
                static = clang.Cursor_getStorageClass(child) == 3
                storage_type = clang.getCanonicalType(clang.getCursorType(child))
                immutable = False
                while True:
                    immutable = immutable or bool(clang.isConstQualifiedType(storage_type))
                    element = clang.getArrayElementType(storage_type)
                    if element.kind == 0:
                        break
                    storage_type = clang.getCanonicalType(element)
                mutable = not immutable
                if mutable and (not local or static) and clang.isCursorDefinition(child):
                    identity = usr(child)
                    if not identity:
                        raise RuntimeError('Native runtime state has no declaration identity')
                    if identity in declarations:
                        raise RuntimeError('Repeated native runtime state definition: ' + identity)
                    start, end = extent(child)
                    name = clang.spelling(child)
                    location = offset(clang.getCursorLocation(child))
                    token = source[location:location + len(name)]
                    if token != name.encode():
                        raise RuntimeError('A macro defines mutable native runtime storage: ' + identity)
                    suffix = source[location + len(name):end].strip()
                    if suffix.startswith(b'['):
                        # Array extents belong to the type, not the initializer.
                        while suffix.startswith(b'['):
                            closing = suffix.find(b']')
                            if closing < 0:
                                raise RuntimeError('Unclosed native state array extent')
                            suffix = suffix[closing + 1:].lstrip()
                    if suffix and not suffix.startswith((b'=', b'{', b'(')):
                        # e.g. ")(uint32_t) = nullptr" from a function-pointer
                        # declarator; the rewrite needs the name last.
                        raise RuntimeError('Native runtime state needs a plain declarator; '
                                           'spell its type through an alias: ' + identity)
                    if suffix.startswith(b'='):
                        suffix = suffix[1:].lstrip()
                    key = clang.qualified(child)
                    if local:
                        key += ':' + clang.type_name(clang.getCursorType(parent))
                        ordinal = local_counts.get(key, 0)
                        local_counts[key] = ordinal + 1
                        key += ':' + str(ordinal)
                    number = hashlib.sha256(key.encode()).hexdigest()[:16]
                    declarations[identity] = dict(name=name,
                        key=key, qualified=clang.qualified(child), local=local,
                        member=parent_kind in ('StructDecl', 'ClassDecl'),
                        start=start, end=end, initializer=suffix,
                        initializer_start=end-len(suffix),
                        native=clang.type_name(clang.getCursorType(child)),
                        reference=clang.getCursorType(child).kind in (103, 104),
                        getter='bqt_state_' + number,
                        tls=bool(clang.getCursorTLSKind(child)))
            if kind in ('DeclRefExpr', 'MemberRefExpr'):
                referenced = clang.getCursorReferenced(child)
                if not clang.Cursor_isNull(referenced) and clang.kind(referenced) == 'VarDecl':
                    references.append((usr(referenced), *extent(child), offset(clang.getCursorLocation(child))))
            visit(child, templated=is_template, owned=True)

    try:
        clang.index = clang.createIndex(0, 0)
        arguments = (c_char_p * len(flags))(*(str(flag).encode() for flag in flags))
        # Bodies are needed: declaration-only analysis cannot distinguish a
        # reference to a registry from a shadowing argument or member.
        clang.tu = clang.parseTranslationUnit(clang.index, str(path).encode(), arguments,
                                              len(flags), None, 0, 0x10 if save_pch else 0)
        if not clang.tu:
            raise RuntimeError('Cannot analyse partitioned native runtime storage')
        errors = []
        for index in range(clang.getNumDiagnostics(clang.tu)):
            diagnostic = clang.getDiagnostic(clang.tu, index)
            if clang.getDiagnosticSeverity(diagnostic) >= 3:
                errors.append(clang.string(clang.formatDiagnostic(diagnostic, 0)))
            clang.disposeDiagnostic(diagnostic)
        if errors:
            raise RuntimeError('Partitioned native runtime analysis failed:\n' + '\n'.join(errors[:20]))
        visit(clang.getTranslationUnitCursor(clang.tu))
        if save_pch and clang.saveTranslationUnit(clang.tu, str(save_pch).encode(),
                                                  clang.defaultSaveOptions(clang.tu)):
            raise RuntimeError('Cannot serialize the native shared-state analysis header')
    finally:
        clang.close()

    ref_edits = []
    for identity, start, end, location in references:
        state = declarations.get(identity) or (external or {}).get(identity)
        if not state:
            continue
        name = state['name'].encode()
        if source[location:location + len(name)] != name:
            raise RuntimeError('Cannot identify resolved runtime state reference: ' + identity)
        # A local static can be used from a captureless lambda or local class.
        # Refer to its static cached pointer, not the automatic reference alias:
        # the latter would introduce a capture/lifetime requirement absent from
        # the original C++. TLS pointers retain that thread's own storage too.
        if state['local']:
            pointer = state['getter'] + '_stored'
            replacement = ('(' + pointer + '->value)' if state['reference'] else '(*' + pointer + ')').encode()
        else:
            replacement = (state['getter'] + '()').encode()
        before_start = max(0, start - 40)
        before, after = source[before_start:start], source[end:end + 16]
        decltype = re.search(rb'\bdecltype\s*\(\s*$', before)
        closing = re.match(rb'\s*\)', after)
        if decltype and closing:
            # Unparenthesized decltype names the declared type, not T&.
            replacement = source[start:location] + (state['getter'] + '_type').encode()
            ref_edits.append((before_start + decltype.start(), end + closing.end(), replacement))
        else:
            ref_edits.append((location, location + len(name), replacement))

    def edited(start, end):
        selected = [(a, b, value) for a, b, value in ref_edits if start <= a and b <= end]
        return apply_edits(source, selected, start, end)

    edits, facts = [], []
    for state in declarations.values():
        native = state['native']
        getter = state['getter']
        storage = 'thread_local ' if state['tls'] else ''
        flags_value = 'BQT_RUNTIME_THREAD_LOCAL' if state['tls'] else '0'
        initializer = edited(state['initializer_start'], state['end']).decode() if state['initializer'] else ''
        code = f'using {getter}_type = {native};\n'
        if state['reference']:
            code += f'struct {getter}_holder {{ {getter}_type value; }};\n'
            stored_type = getter + '_holder'
            construction = f'::new (memory) {stored_type}' + ('{' + initializer + '}' if initializer else '') + ';'
            value = 'stored->value'
        else:
            stored_type = getter + '_type'
            arguments = initializer if not initializer or initializer.startswith(('{', '(')) else '(' + initializer + ')'
            construction = f'::new (memory) {stored_type}' + arguments + ';'
            value = '*stored'
        pointer = getter + '_stored'
        value = value.replace('stored', pointer)
        body = (f'    static {storage}{stored_type} *const {pointer} = std::addressof(::bendqt::runtime_shared_state_init<{stored_type}>(\n'
                f'        {json.dumps(state["key"])}, {flags_value}, [&](void *memory) {{ {construction} }}));\n')
        if state['local']:
            code += body + f'    auto &{state["name"]} = {value}'
        else:
            code += f'static {getter}_type &{getter}() {{\n' + body + f'    return {value};\n}}'
        edits.append((state['start'], state['end'], code.encode()))
        facts.append({key: state[key] for key in ('key', 'qualified', 'native', 'tls', 'local', 'member')})
    for edit in ref_edits:
        if not any(state['start'] <= edit[0] and edit[1] <= state['end'] for state in declarations.values()):
            edits.append(edit)
    return apply_edits(source, edits).decode(), facts, declarations


def _fragment(path, flags, external, suffix, visible):
    before = 'namespace bendqt {\n'
    after = '' if suffix else '\n}\n'
    source = Path(path).read_text()
    ranges = [(match.start(), match.end(), visible[1][int(match[1])]) for match in re.finditer(
        r'^// BQT_STATE_BODY_BEGIN ([0-9]+)\n(.*?)\n// BQT_STATE_BODY_END \1\n', source, re.M | re.S)]
    rewritten, facts, _ = _transform(path, flags, external=external, visibility=(visible[0], ranges))
    if not rewritten.startswith(before) or (after and not rewritten.endswith(after)):
        raise RuntimeError('Native semantic fragment boundaries changed')
    return rewritten[len(before):len(rewritten) - len(after) if after else None], facts


def transform(path, flags):
    """Resolve all bodies in bounded units, sharing the original declarations.

    The PCH contains the unmodified runtime. A fragment's references therefore
    resolve to the same declarations as in the complete input, including static
    storage, shadowing and overloads. Only the final source contains the edits.
    """
    path = Path(path).resolve()
    source = path.read_text()
    threshold = int(os.environ.get('BQT_STATE_SOURCE_BYTES', '8000000'))
    if threshold < 0:
        raise ValueError('Native semantic source size must be nonnegative')
    if len(source) < threshold or 'static bool __attribute__((noinline)) bqt_op_' not in source:
        rewritten, facts, _ = _transform(path, flags)
        return rewritten, facts
    directory = path.parent / 'shared-state-analysis'
    directory.mkdir(parents=True, exist_ok=True)
    cache, output = directory / 'cache.json', directory / 'transformed.cpp'
    inputs = _analysis_inputs(path, flags)
    if inputs['dependencies'][str(path)] != hashlib.sha256(source.encode()).hexdigest():
        raise RuntimeError('Native source changed before semantic analysis')
    if cache.is_file() and output.is_file():
        saved = json.loads(cache.read_text())
        if saved.get('inputs') == inputs and saved.get('output_sha256') == _digest(output):
            print('Reusing checked native semantic analysis: ' + str(path), flush=True)
            return output.read_text(), saved['storage']
    rewritten, facts = _bounded_transform(path, flags, source)
    if _analysis_inputs(path, flags) != inputs:
        raise RuntimeError('Native semantic analysis inputs changed; result not cached')
    temporary = output.with_suffix('.tmp')
    temporary.write_text(rewritten); temporary.replace(output)
    record = dict(inputs=inputs, output_sha256=_digest(output), storage=facts)
    temporary = cache.with_suffix('.tmp')
    temporary.write_text(json.dumps(record, indent=2) + '\n'); temporary.replace(cache)
    return rewritten, facts


def _digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _analysis_inputs(path, flags):
    # Preprocess every time: a newly shadowing include must invalidate a cache
    # even when all files in the previous dependency list are unchanged.
    result = subprocess.run(['clang++-19', *flags, '-M', '-MT', 'bqt-state', str(path)],
                            capture_output=True, text=True, check=True)
    paths = shlex.split(result.stdout.replace('\\\n', '').partition(':')[2])
    dependencies = {str(Path(name).resolve()): _digest(name) for name in sorted(set(paths))}
    here = Path(__file__).resolve().parent
    algorithm = {name: _digest(here / name) for name in ('shared_state.py', 'public_records.py', 'native_shards.py')}
    # Both parsers are pinned to LLVM 19, but a patched libclang build must not
    # inherit a result produced by a different binary with the same version.
    library = Path('/usr/lib/llvm-19/lib/libclang.so').resolve()
    return dict(schema=1, cwd=os.getcwd(), flags=flags,
        compiler=subprocess.check_output(['clang++-19', '--version'], text=True),
        libclang_sha256=_digest(library), algorithm=algorithm, dependencies=dependencies)


def _bounded_transform(path, flags, source):
    from native_shards import split_source, split_auxiliary, write_changed
    started = time.monotonic()
    prefix, operations, suffix = split_source(source)
    # Validate the generator-owned boundaries before replacing their bodies by
    # comment slots. Keeping each original slot preserves C++ declaration order.
    _, auxiliary = split_auxiliary(prefix)
    pattern = re.compile(r'^// BQT_AUXILIARY_BEGIN ([a-z][a-z0-9_]*) ([0-9]+)\n'
                         r'(.*?)^// BQT_AUXILIARY_END \1 \2\n', re.M | re.S)
    bodies, slots = {}, {}
    def slot(match):
        index = len(bodies)
        bodies[index] = match[3]
        marker = '// BQT_STATE_AUXILIARY_SLOT ' + str(index) + '\n'
        slots[index] = (marker, match[1], match[2])
        return marker
    header = pattern.sub(slot, prefix)
    if len(slots) != len(auxiliary):
        raise RuntimeError('Native auxiliary analysis inventory changed')
    auxiliary_indices = list(bodies)
    operation_indices = []
    for _, body in operations:
        index = len(bodies); bodies[index] = body; operation_indices.append(index)
    suffix_index = len(bodies); bodies[suffix_index] = suffix
    directory = path.parent / 'shared-state-analysis'
    directory.mkdir(parents=True, exist_ok=True)
    declarations = ''.join(f'static bool __attribute__((noinline)) bqt_op_{number}(BqtRequest *r);\n'
                           for number, _ in operations)
    ending = declarations + '\n} // namespace bendqt\n'
    header_path, pch = directory / 'original.hpp', directory / 'original.pch'
    write_changed(header_path, header + ending)
    flags = [*flags, '-iquote', str(path.parent)]
    print('Analysing shared native declarations (' + str(len(header)) + ' bytes)', flush=True)
    rewritten, facts, external = _transform(header_path, [*flags, '-x', 'c++-header'], save_pch=pch)
    if not rewritten.endswith(ending):
        raise RuntimeError('Native shared analysis declarations changed')
    rewritten = rewritten[:-len(ending)]
    groups = []
    for indices, maximum in ((auxiliary_indices, 128), (operation_indices, 1024)):
        current, size = [], 0
        for index in indices:
            if current and (len(current) >= maximum or size + len(bodies[index]) > 1_000_000):
                groups.append(current); current, size = [], 0
            current.append(index); size += len(bodies[index])
        if current: groups.append(current)
    groups.append([suffix_index])
    jobs = int(os.environ.get('BQT_STATE_JOBS', os.environ.get('BQT_SHARD_JOBS', '1')))
    if jobs < 1:
        raise ValueError('Native semantic analysis needs a positive worker count')
    fragment_flags = [*flags, '-include-pch', str(pch)]
    visible = {int(match[1]): match.start() for match in re.finditer(
        rb'^// BQT_STATE_AUXILIARY_SLOT ([0-9]+)\n', header.encode(), re.M)}
    visible.update({index: len(header.encode()) for index in operation_indices})
    visible[suffix_index] = len((header + ending).encode())
    inputs = []
    for number, indices in enumerate(groups):
        fragment = directory / f'fragment-{number:04}.cpp'
        body = ''.join('// BQT_STATE_BODY_BEGIN ' + str(index) + '\n' + bodies[index]
                       + '\n// BQT_STATE_BODY_END ' + str(index) + '\n' for index in indices)
        write_changed(fragment, 'namespace bendqt {\n' + body + ('' if suffix_index in indices else '\n}\n'))
        inputs.append((fragment, fragment_flags, external, suffix_index in indices,
                       (str(header_path), {index: visible[index] for index in indices})))
    outputs = {}
    marker = re.compile(r'^// BQT_STATE_BODY_BEGIN ([0-9]+)\n(.*?)\n// BQT_STATE_BODY_END \1\n', re.M | re.S)
    print(f'Analysing {len(groups)} native body units with {jobs} workers', flush=True)
    with ProcessPoolExecutor(max_workers=jobs, mp_context=multiprocessing.get_context('spawn')) as pool:
        pending = {pool.submit(_fragment, *arguments): index for index, arguments in enumerate(inputs)}
        for count, future in enumerate(as_completed(pending), 1):
            body, current_facts = future.result()
            expected = groups[pending[future]]
            found = {int(match[1]): match[2] for match in marker.finditer(body)}
            if set(found) != set(expected) or set(found) & outputs.keys():
                raise RuntimeError('Native semantic analysis lost or repeated a body')
            outputs.update(found); facts.extend(current_facts)
            if count == 1 or count % 10 == 0 or count == len(groups):
                print(f'Analysed native body units {count}/{len(groups)}', flush=True)
    if len(outputs) != len(bodies):
        raise RuntimeError('Incomplete native semantic analysis')
    restored = set()
    def restore(match):
        index = int(match[1])
        if index not in slots or index in restored:
            raise RuntimeError('A native auxiliary definition lost its original position')
        restored.add(index)
        _, family, number = slots[index]
        return (f'// BQT_AUXILIARY_BEGIN {family} {number}\n'
                + outputs[index] + f'// BQT_AUXILIARY_END {family} {number}\n')
    rewritten = re.sub(r'^// BQT_STATE_AUXILIARY_SLOT ([0-9]+)\n', restore, rewritten, flags=re.M)
    if restored != slots.keys():
        raise RuntimeError('Incomplete native auxiliary definition restoration')
    unique = {row['key']: row for row in facts}
    if len(unique) != len(facts):
        raise RuntimeError('Repeated native shared-state identity across semantic fragments')
    result = rewritten + ''.join(outputs[index] for index in operation_indices) + outputs[suffix_index]
    (directory / 'receipt.json').write_text(json.dumps(dict(
        input_sha256=hashlib.sha256(source.encode()).hexdigest(), output_sha256=hashlib.sha256(result.encode()).hexdigest(),
        common_bytes=len(header), operation_count=len(operations), auxiliary_count=len(auxiliary),
        analysis_units=len(groups), workers=jobs, elapsed_seconds=time.monotonic()-started,
        every_body_resolved=True, verification_complete=True), indent=2) + '\n')
    return result, sorted(facts, key=lambda row: row['key'])


def apply_edits(source, edits, start=0, end=None):
    end = len(source) if end is None else end
    result, boundary = [], start
    for first, last, replacement in sorted(set(edits)):
        if first < boundary or last > end:
            raise RuntimeError('Overlapping native shared-state transformations')
        result.extend((source[boundary:first], replacement))
        boundary = last
    result.append(source[boundary:end])
    return b''.join(result)
