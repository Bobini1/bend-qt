#!/usr/bin/env python3
"""Verify the pinned PySide boundary, including stale extraction inputs.

This is a maintainer regression test. Qt Quick's internal Vulkan backend is
retained; application-owned Vulkan interop and native registry bindings are not.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
import pyside_boundary
from upstream import PIN


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--qt-root', type=Path,
                        default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    parser.add_argument('--source', type=Path,
                        default=Path.home() / '.cache/bend-qt-generator/pyside-setup')
    parser.add_argument('--work', type=Path, default=ROOT / 'build/qt612/pyside-boundary-check')
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    source_root = args.source / 'sources/pyside6/PySide6'
    definitions = pyside_boundary.definitions(source_root.glob('Qt*/typesystem_*.xml'), source_root)
    registered = set(definitions['registered_types'])
    assert {'QQuickWindow', 'QQuickGraphicsDevice', 'QQuickRenderTarget', 'QRhi',
            'QRhiNullInitParams', 'QRhiGles2InitParams'} <= registered
    assert not any(pyside_boundary.native_type(name) for name in registered)
    expected = {
        ('QQuickGraphicsDevice', r'^fromPhysicalDevice\(.*$'),
        ('QQuickGraphicsDevice', r'^fromDeviceObjects\(.*$'),
        ('QQuickRenderTarget', r'^fromVulkanImage\(.*$'),
    }
    removed = {(r['owner'], r['signature']) for r in definitions['removed_functions']}
    assert expected <= removed, 'Pinned PySide no longer removes the expected Vulkan import APIs'

    # Inject known stale-model shapes even after the canonical API is regenerated.
    # Their signature/type evidence must be rejected before restoration or any
    # generic field/platform carrier discovery has a chance to revive them.
    injected = []
    def stale_model(api):
        by_name = {c['name']: c for c in api['classes']}
        for owner, method in [('QQuickGraphicsDevice', 'fromPhysicalDevice'),
                              ('QQuickGraphicsDevice', 'fromDeviceObjects'),
                              ('QQuickRenderTarget', 'fromVulkanImage')]:
            cls = by_name[owner]
            f = copy.deepcopy(next(f for f in cls['functions'] if not f.get('constructor')))
            f.update(name=method, signature=method+'(VkDevice)',
                     minimal_signature=method+'(VkDevice)',
                     source_signatures=[method+'(VkDevice)'], removed=True)
            cls['functions'].append(f)
            injected.append(owner+'.'+method)
        seed = copy.deepcopy(by_name['QRhiNullInitParams'])
        for name in ('QVulkanInstance', 'QRhiVulkanInitParams', 'VkDeviceCreateInfo'):
            c = copy.deepcopy(seed)
            c.update(name=name, package='BendQt', functions=[], fields=[], enums=[])
            api['classes'].append(c)
            injected.append(name)
        api['vulkan_registry_model'] = {'negative_control': True}

    spec = importlib.util.spec_from_file_location('boundary_focus', ROOT / 'scripts/check-qt-next-conversions-native.py')
    focused = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(focused)
    focused.MODULES = ['QtCore', 'QtGui', 'QtWidgets', 'QtQuick', 'QtOpenGL']
    focused.FAMILIES = {
        'QQuickWindow': {'setGraphicsApi', 'graphicsApi'},
        'QSGRendererInterface': {'graphicsApi'},
        'QQuickGraphicsDevice': {'fromPhysicalDevice', 'fromDeviceObjects'},
        'QQuickRenderTarget': {'fromVulkanImage'},
        'QRhi': {'backendName'},
    }
    operations = focused.generate(args.work, args.qt_root, rhi=True, api_transform=stale_model)
    bend = (args.work / 'qt.bend').read_text()
    cpp = (args.work / 'wrappers.cpp').read_text()
    assert not pyside_boundary.native_type(bend), 'External Vulkan type escaped into Bend output'
    assert not pyside_boundary.native_type(cpp), 'External Vulkan type escaped into native output'
    for name in injected:
        assert name not in operations['ids']
        assert not re.search(r'\b'+re.escape(name)+r'(?:\b|_)', bend), name
    assert 'QQuickWindow.setGraphicsApi' in bend
    assert 'QSGRendererInterface.GraphicsApi.Vulkan' in bend
    assert 'QRhi.Implementation.Vulkan' in bend
    assert any(m['owner'] == 'QRhi' for m in operations['operations'])
    checked = focused.check_bend(args.work)
    manifest = json.loads((args.work / 'upstream.json').read_text())
    assert manifest['commit'] == PIN
    assert not any(pyside_boundary.native_type(row.get('name', ''))
                   for row in manifest.get('type_adaptations', []))
    receipt = dict(
        complete=True, upstream_commit=PIN, upstream_definition_count=len(registered),
        removed_import_evidence=[r for r in definitions['removed_functions']
                                 if (r['owner'], r['signature']) in expected],
        stale_cache_negative_cases=injected,
        emitted_methods=len(operations['operations']),
        qt_quick_vulkan_backend_enum_preserved=True,
        qrhi_preserved=True, **checked,
        native_sha256=digest(args.work / 'wrappers.cpp'),
        source_sha256={str(p.relative_to(ROOT)):digest(p) for p in sorted(
            [*ROOT.glob('generator/*.py'), *ROOT.glob('generator/templates/*'), Path(__file__)])
            if p.is_file()},
        boundary='Source inventory and generated Bend/native declarations; native rendering is checked by the retained integration suites.')
    (args.work / 'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k != 'source_sha256'}, indent=2))


if __name__ == '__main__':
    main()
