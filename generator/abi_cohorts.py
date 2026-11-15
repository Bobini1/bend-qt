"""Discover version-bound native APIs from their owning header guarantees.

The package carries one complete native payload for the pinned Qt runtime.
The loader rejects other runtimes before loading it. Guarded builds remain
useful to maintainer controls; consumers do not select a reduced fallback.
"""
from pathlib import Path
import re


def state(g):
    if hasattr(g, 'abi_cohort'):
        return g.abi_cohort
    headers, names = {}, set()
    if g.profile.get('limited_abi'):
        for name, cls in g.classes.items():
            path = cls.get('source_file', '')
            if not path:
                continue
            if path not in headers:
                source = Path(path)
                text = source.read_text(errors='replace')[:16384] if source.is_file() else ''
                headers[path] = 'part of the RHI API, with limited compatibility guarantees' in text
            if headers[path]:
                names.add(name)
        changed = True
        while changed:
            previous = len(names)
            for name, cls in g.classes.items():
                if any(base in names for base in cls.get('bases', [])):
                    names.add(name)
            changed = previous != len(names)
    pattern = re.compile(r'(?<![A-Za-z0-9_])(?:' + '|'.join(re.escape(name) for name in sorted(names, key=len, reverse=True)) + r')(?![A-Za-z0-9_])') if names else None
    g.abi_cohort = dict(names=names, headers=sorted(path for path, limited in headers.items() if limited),
                        pattern=pattern, proxies=set(), operations=set(), exact_helpers={})
    return g.abi_cohort


def required(g, text):
    current = state(g)
    return bool(current['pattern'] and current['pattern'].search(text)) or any(
        re.search(r'\b' + re.escape(proxy) + r'\b', text) for proxy in current['proxies']) or any(
            prefix in text for prefix in current['exact_helpers'])


def register_exact(g, prefix, reason, native_symbols):
    state(g)['exact_helpers'][prefix] = dict(reason=reason, native_symbols=native_symbols)


def proxy(g, name, lines):
    if not required(g, '\n'.join(lines)):
        return lines
    state(g)['proxies'].add(name)
    return ['#if BQT_HAS_RHI', *lines, '#else',
            f'class {name} {{ public: virtual void bqt_unavailable_cohort() = 0; }};', '#endif']


def operation(g, identifier, body):
    if not required(g, body):
        return body
    state(g)['operations'].add(int(identifier))
    return ('#if BQT_HAS_RHI\n' + body + '\n#else\n'
            'return fail(r, ENOTSUP, "This Qt operation requires a native payload matching the installed Qt version");\n#endif')


def emit(g):
    current = state(g)
    operation = g.next_id
    g.next_id += 1
    value = 'BQT_HAS_RHI' if current['names'] else 'false'
    g.cases.append(f'case {operation}: {{\n    r->result.word = {value}; return true;\n}}')
    g.emit_effect('Runtime.hasRhiBindings', [], dict(kind='bool', bend='Bool', raw='U32'), operation)


def inventory(g):
    current = state(g)
    return dict(limited_abi_types=sorted(current['names']), owning_headers=current['headers'],
                guarded_operations=sorted(current['operations']), guarded_proxies=sorted(current['proxies']),
                exact_version_helpers=current['exact_helpers'],
                matching_version='6.12.0' if current['names'] or current['exact_helpers'] else None,
                runtime_qt='6.12.0', fallback=None)


def forbidden_imports(g, mangled, demangled, public_symbols):
    """Reject RHI imports, allowing public functions with opaque pointer parameters.

    Public renderer vtables can reference Qt_6 functions taking a QRhi pointer.
    Those references do not use the pointed-to type's layout or implementation.
    Require the actual ELF public symbol version, and never mask a method owner,
    by-value/reference parameter or private helper. Discovered nested classes
    follow the same rule: only an opaque pointer parameter can be masked.
    """
    current = state(g)
    if len(mangled) != len(demangled):
        raise RuntimeError('Native symbol demangling changed the import count')
    names = '|'.join(re.escape(name) for name in sorted(current['names'], key=len, reverse=True))
    opaque = re.compile(r'(?<=[(,])\s*(?:const\s+)?(?:' + names
                        + r')\s*(?:const\s*)?\*\s*(?:const\s*)?(?=[,)])') if names else None
    bad, accepted = [], []
    for native, readable in zip(mangled, demangled):
        private = any(symbol in readable for helper in current['exact_helpers'].values()
                      for symbol in helper['native_symbols'])
        if private:
            bad.append(readable)
        elif required(g, readable):
            masked = opaque.sub('opaque_pointer', readable) if opaque else readable
            if native in public_symbols and not required(g, masked):
                accepted.append(readable)
            else:
                bad.append(readable)
    return bad, accepted


def compile_payloads(g, source, qt, work, cxx, modules):
    from backend import compile_backend
    embedded, loader, metadata = compile_backend(source, qt, work, cxx, modules)
    metadata['cohort_selection'] = inventory(g)
    return embedded, loader, metadata
