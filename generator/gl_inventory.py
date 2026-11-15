"""Restore native OpenGL signatures explicitly rejected by Python's bindings.

The selected classes still come from PySide. A separate additive type system
is needed because Shiboken rejection rules cannot be undone by registration.
Existing upstream signatures and their policies always take precedence.
"""
import hashlib
import json
from pathlib import Path
from backend import command


def restore(api, headers, extractor, include_paths, work, env):
    classes = [c for c in api['classes'] if c.get('generate') and not c.get('namespace')
               and (c['name'].startswith('QOpenGLFunctions') or c['name'] == 'QOpenGLExtraFunctions')]
    if not classes:
        return
    work = Path(work) / 'additive-opengl'
    work.mkdir(exist_ok=True)
    logs = work / 'extractor'
    logs.mkdir(exist_ok=True)
    system = work / 'typesystem.xml'
    text = '<typesystem package="BendQtNativeOpenGL">\n  <primitive-type name="GLsync"/>\n'
    text += ''.join(f'  <object-type name="{c["name"]}"/>\n' for c in classes)
    text += '</typesystem>\n'
    system.write_text(text)
    native_path = work / 'api.json'
    extracted = command([extractor, headers, system, native_path, logs, *include_paths], env=env)
    (work / 'extraction.log').write_text(extracted.stdout + extracted.stderr)
    native = json.loads(native_path.read_text())
    targets = {c['name']: c for c in classes}
    added = []
    for c in native['classes']:
        target = targets.get(c['name'])
        if target is None:
            continue
        signatures = {s for f in target['functions'] for s in f['source_signatures']}
        for f in c['functions']:
            if not f['public'] or all(s in signatures for s in f['source_signatures']):
                continue
            f['native_inventory_source'] = 'additive-opengl'
            target['functions'].append(f)
            signatures.update(f['source_signatures'])
            added.append({'class': c['name'], 'signature': f['signature'],
                          'source_signatures': f['source_signatures']})
    api.setdefault('additive_extraction', []).append({
        'name': 'additive-opengl', 'type_system_sha256': hashlib.sha256(text.encode()).hexdigest(),
        'header_sha256': hashlib.sha256(Path(headers).read_bytes()).hexdigest(),
        'classes': [c['name'] for c in classes], 'restored_native_signatures': added,
        'reason': 'Explicit upstream rejection or missing primitive registration; Python policy preserved for existing signatures'})
