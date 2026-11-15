"""Pinned PySide type systems are the API inventory; no Bend class catalogue."""
import hashlib
import json
import os
import re
from pathlib import Path
import xml.etree.ElementTree as ET

from backend import command
import pyside_boundary
import qobject_interfaces
import qio_pipe
import qt_targets

PIN = qt_targets.target(qt_targets.DEFAULT)['shiboken_commit']


def prepare(source, qt, modules, work, *, limited_abi=False):
    qt_target = qt_targets.target(qt_targets.installed_version(qt))
    if command(["git", "-C", source, "rev-parse", "HEAD"]).stdout.strip() != qt_target['shiboken_commit']:
        raise ValueError('PySide source must match the pinned ' + qt_target['qt'] + ' commit')
    command(["git", "-C", source, "diff", "--exit-code", "HEAD", "--", "sources/pyside6/PySide6"])
    root = source / "sources/pyside6/PySide6"
    catalog = {}
    for directory in sorted(root.glob("Qt*")):
        path = directory / ("typesystem_" + directory.name[2:].lower() + ".xml")
        if path.exists():
            catalog[directory.name] = path
    visited, active, files = set(), [], set()

    def scan(path):
        path = path.resolve()
        if path in files: return
        files.add(path)
        # Shiboken owns parsing (including entities and feature processing
        # instructions). This pass only discovers literal dependency tags.
        for tag in re.findall(r"<load-typesystem\b[^>]*>", path.read_text()):
            item = ET.fromstring(tag if tag.endswith("/>") else tag + "</load-typesystem>")
            relative = Path(item.attrib["name"])
            candidates = [root / relative, path.parent / relative]
            dependency = next((p for p in candidates if p.exists()), None)
            if dependency is None:
                raise ValueError(f"Missing upstream type system: {path}: {relative}")
            module = dependency.relative_to(root).parts[0]
            if module in catalog and module != path.relative_to(root).parts[0]:
                visit(module)
            scan(dependency)

    def visit(module):
        if module in visited: return
        visited.add(module)
        if module not in catalog:
            raise ValueError(f"No upstream type system for {module}")
        if not (qt / "include" / module / module).exists():
            raise ValueError(f"Install maintainer Qt headers for {module}")
        scan(catalog[module])
        active.append(module)

    for module in modules: visit(module)
    if 'QtGraphs' in active and any(m in active for m in ('QtCharts', 'QtDataVisualization')):
        raise ValueError('Qt Graphs and the legacy Charts/DataVisualization headers define conflicting C++ types; extract them in separate native modules')
    headers = work / "headers.h"
    # Match the public definitions supplied by Qt's imported CMake targets.
    # Header-only cross-module APIs (for example SQL widget delegates) use
    # these definitions in addition to their ordinary feature tests.
    module_definitions = set()
    for module in active:
        target = qt / 'lib/cmake' / ('Qt6' + module[2:]) / ('Qt6' + module[2:] + 'Targets.cmake')
        if target.exists():
            for value in re.findall(r'INTERFACE_COMPILE_DEFINITIONS\s+"([^"]*)"', target.read_text()):
                module_definitions.update(re.findall(r'\bQT_[A-Z0-9_]+_LIB\b', value))
    header_text = ''.join(f'#ifndef {name}\n#define {name}\n#endif\n' for name in sorted(module_definitions))
    header_text += "".join(f"#include <{m}/{m}>\n" for m in active)
    supplemental_headers = []
    # A module umbrella need not include every public registered class.
    # Discover forwarding headers from the pinned registrations, rather than
    # maintaining a second class catalogue in the Bend binding.
    public_headers = set()
    for path in sorted(files):
        module = path.relative_to(root).parts[0]
        if module not in active:
            continue
        for name in pyside_boundary.definitions([path], root)['registered_types']:
            if re.fullmatch(r'Q[A-Za-z0-9_]+', name) and not pyside_boundary.native_type(name):
                include = f'{module}/{name}'
                if (qt / 'include' / include).is_file():
                    public_headers.add(include)
    header_text += ''.join(f'#include <{include}>\n' for include in sorted(public_headers))
    helper_interfaces = qobject_interfaces.discover(root, active, files, work)
    header_text += qobject_interfaces.header(helper_interfaces)
    helper_pipes = qio_pipe.discover(root, active, work)
    header_text += qio_pipe.header(helper_pipes)
    if 'QtOpenGL' in active:
        # Qt's module umbrella deliberately omits the versioned function
        # classes. PySide's own post-header supplies their platform guards.
        post = root / 'QtOpenGL/QtOpenGL_global.post.h.in'
        header_text += '\n' + post.read_text() + '\n'
        supplemental_headers.append({'path': str(post.relative_to(root)),
                                     'sha256': hashlib.sha256(post.read_bytes()).hexdigest()})
    if limited_abi:
        # Discover the RHI includes from PySide's own post-headers; Python
        # helper declarations in those files do not belong in a native binding.
        seen = set()
        for module in active:
            post = root / module / (module + '_global.post.h.in')
            if not post.exists():
                continue
            includes = re.findall(r'^\s*#include\s+<(rhi/[^>]+)>', post.read_text(), re.M)
            for include in includes:
                if include not in seen:
                    header_text += f'#include <{include}>\n'
                    seen.add(include)
            if includes:
                supplemental_headers.append({'path': str(post.relative_to(root)),
                    'sha256': hashlib.sha256(post.read_bytes()).hexdigest(),
                    'includes': includes, 'compatibility': 'Qt version matched RHI API'})
    headers.write_text(header_text)
    typesystem = work / "typesystem.xml"
    typesystem.write_text('<typesystem package="BendQt">\n' + "".join(
        f'  <load-typesystem name="{catalog[m].relative_to(root)}" generate="yes"/>\n'
        for m in active) + ('  <value-type name="QDBusReply" generate="no"/>\n' if 'QtDBus' in active else '')
        + ('  <primitive-type name="xkb_context"/>\n' if 'QtGui' in active else '') + '</typesystem>\n')
    rejections = []
    for path in sorted(files):
        text = re.sub(r'<!--.*?-->', '', path.read_text(), flags=re.S)
        for tag in re.findall(r'<rejection\b[^>]*>', text):
            item = ET.fromstring(tag if tag.endswith('/>') else tag + '</rejection>')
            rejections.append({'source': str(path.relative_to(root)), **item.attrib})
    manifest = {"commit": qt_target['shiboken_commit'], "qt": qt_target['qt'], "modules": active,
                'pyside_definitions': pyside_boundary.definitions(files, root),
                'type_adaptations': ([{'name': 'QDBusReply', 'representation': 'dependency-only value template',
                                      'reason': 'Preserve typed native replies omitted by the upstream Python helper declarations'}]
                                     if 'QtDBus' in active else [])
                                    + ([{'name': 'xkb_context', 'representation': 'opaque native platform capability',
                                         'reason': 'Preserve QWaylandApplication::xkbContext omitted by missing native type registration'}]
                                       if 'QtGui' in active else []),
                'supplemental_headers': supplemental_headers,
                'registered_public_headers': sorted(public_headers),
                'module_compile_definitions': sorted(module_definitions),
                'qobject_interfaces': helper_interfaces, 'qio_pipe': helper_pipes, 'native_rejections': rejections,
                "module_inventory": [{"name": m, "selected": m in active,
                    "headers_installed": (qt / "include" / m / m).exists()} for m in catalog],
                "type_systems": [{"path": str(p.relative_to(root)),
                    "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(files)]}
    (work / "upstream.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return headers, typesystem, active, dict(os.environ, TYPESYSTEMPATH=str(root)), manifest


def select_classes(api):
    selected, excluded = [], []
    for c in api["classes"]:
        reason = None
        if c["namespace"]: continue
        if not c["generate"]: reason = "Upstream marks this type as dependency-only"
        elif c["template"]: reason = "Template instantiation adapter required"
        elif not c["public_destructor"]: reason = "No public destructor"
        elif c["object"] and not c["qobject"]: reason = "Non-QObject inheritance/lifetime adapter required"
        elif c["value"] and not c["copyable"]: reason = "Noncopyable value adapter required"
        elif any(x in c["name"] for x in ("<", ">", "Private")): reason = "Template/private implementation type"
        elif not (c["object"] or c["value"]): reason = "No object/value representation"
        if reason:
            excluded.append({"class": c["name"], "module": c["package"], "reason": reason})
        else:
            selected.append(c["name"])
    return sorted(selected), excluded
