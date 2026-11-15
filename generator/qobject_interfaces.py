"""Native QObject/interface helper bases discovered from pinned PySide headers.

These classes contain no Python runtime state. Their QObject metadata is built
with the maintainer's moc, and ordinary extracted constructors and virtuals use
the same generated bindings as Qt's own classes.
"""
import hashlib
import json
import re
from pathlib import Path

import pyside_boundary


def discover(root, modules, type_systems, work):
    root, work = Path(root), Path(work)
    registrations = {}
    for path in sorted(type_systems):
        module = path.relative_to(root).parts[0]
        for name in pyside_boundary.definitions([path], root)['registered_types']:
            registrations.setdefault(name, module)
    result = []
    for path in sorted(root.glob('qpy*.h')):
        source = path.read_text()
        interfaces = dict(re.findall(r'Q_DECLARE_(?:EXTENSION_)?INTERFACE\(\s*(\w+)\s*,\s*"([^"]+)"\s*\)', source))
        for match in re.finditer(r'class\s+(QPy\w+)\s*:\s*public\s+QObject\s*,\s*public\s+(\w+)\s*\{(.*?)\n\};', source, re.S):
            name, interface, body = match.groups()
            module = registrations.get(name)
            if module not in modules:
                continue
            if not re.search(r'\bQ_OBJECT\b', body) or not re.search(r'Q_INTERFACES\(\s*' + re.escape(interface) + r'\s*\)', body):
                continue
            if interface not in interfaces or not re.search(re.escape(name) + r'\(QObject\s*\*parent\s*=\s*nullptr\)', body):
                raise ValueError('Unrecognized pinned QObject/interface helper: ' + name)
            result.append(dict(name=name, interface=interface, module=module, iid=interfaces[interface],
                source=str(path.relative_to(root)), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    (work / 'qobject-interfaces.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def header(specifications):
    if not specifications:
        return ''
    lines = ['#ifndef BEND_QT_QOBJECT_INTERFACES_H', '#define BEND_QT_QOBJECT_INTERFACES_H',
             '#include <QtCore/QObject>']
    lines += [f'#include <{module}/{interface}>' for module, interface in sorted({(s['module'], s['interface']) for s in specifications})]
    lines += ['#ifdef Q_MOC_RUN']
    lines += [f'Q_DECLARE_INTERFACE({s["interface"]}, "{s["iid"]}")' for s in specifications]
    lines += ['#endif', 'QT_BEGIN_NAMESPACE']
    for s in specifications:
        lines += [f'// Native helper contract from pinned PySide {s["source"]}.',
                  f'class {s["name"]} : public QObject, public {s["interface"]} {{',
                  '    Q_OBJECT', f'    Q_INTERFACES({s["interface"]})', 'public:',
                  f'    explicit {s["name"]}(QObject *parent = nullptr) : QObject(parent) {{}}', '};']
    lines += ['QT_END_NAMESPACE', '#endif', '']
    return '\n'.join(lines)


def restore(api, work, *, require_complete=True):
    path = Path(work) / 'qobject-interfaces.json'
    specifications = json.loads(path.read_text()) if path.exists() else []
    classes = {c['name']: c for c in api['classes']}
    for specification in specifications:
        name = specification['name']
        if name not in classes:
            if require_complete:
                raise ValueError('The pinned QObject/interface helper was not extracted: ' + name)
            continue
        classes[name]['qobject_interface_helper'] = specification
    specifications = [s for s in specifications if s['name'] in classes]
    api['qobject_interfaces'] = specifications
    return specifications


def inventory(g):
    return [dict(s, native_class=s['name'], interfaces=[s['interface']],
                 implementation='Native Q_OBJECT/Q_INTERFACES, extracted methods and generated virtual proxies')
            for s in g.api.get('qobject_interfaces', []) if s['name'] in g.ids]
