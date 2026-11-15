"""Validate reviewable source/notice inputs before packaging a Qt runtime.

A release manifest cannot authorize an unknown Qt binary with a boolean flag.
Installer binaries are rechecked against their actual SPDX inventory, omitted
files need explicit byte-pinned evidence, and matching source artifacts must
exist before package generation starts.
"""
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

from qt_licenses import Inventory, allows
from qt_targets import installed_version
from runtime_bundle import embed, relative_path
from runtime_deployment import loader
from runtime_selection import select


def checked_file(row, base):
    path = Path(row['file'])
    if not path.is_absolute():
        path = base / path
    if not path.is_file() or not path.stat().st_size:
        raise ValueError('Missing release input: ' + str(path))
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest != row['sha256']:
        raise ValueError('Release input changed: ' + str(path))
    return path.resolve()


def checked_source(row, base):
    url = urlparse(row.get('url', ''))
    if url.scheme != 'https' or not url.netloc:
        raise ValueError('A corresponding-source artifact needs an HTTPS distribution URL')
    result = dict(row, file=str(checked_file(row, base)))
    result['overlays'] = []
    for overlay in row.get('overlays', []):
        relative_path(overlay['path'])
        result['overlays'].append(checked_source(overlay, base))
    result['submodules'] = {}
    for name, child in row.get('submodules', {}).items():
        relative_path(name)
        result['submodules'][name] = checked_source(child, base)
    return result


def prepare(manifest, qt, profile):
    manifest = Path(manifest).resolve(); base = manifest.parent
    data = json.loads(manifest.read_text())
    version = installed_version(qt); flavor = profile['license_flavor']
    if (data.get('schema') != 1 or data.get('qt') != version
            or data.get('flavor') != flavor or profile['minimum_qt'] != version):
        raise ValueError('The runtime release manifest does not match the Qt target/flavor')
    inventory = Inventory(qt)
    inventory.require(profile['qt_modules'], flavor)
    if not data.get('package_license'):
        raise ValueError('A release needs an explicit component-aware package LICENSE; the Hub default cannot license embedded Qt')
    package_license = checked_file(data['package_license'], base)
    legal, source_rows, delivered_sources = {}, data.get('sources', {}), {}
    for source, row in source_rows.items():
        # Source delivery is separate from consumer installation. Archives are
        # prepared here for the release and get public download locations in
        # the embedded source manifest; no consumer download is performed.
        delivered_sources[source] = checked_source(row, base)
    for name, row in data.get('notices', {}).items():
        relative_path(name)
        if not name.startswith('notices/'):
            raise ValueError('License notices belong under notices/: ' + name)
        legal[name] = checked_file(row, base)
    if not legal:
        raise ValueError('A runtime release needs component license/copyright notices')
    supplements = data.get('supplements', {})
    for name, row in supplements.items():
        relative_path(name)
        row = dict(row)
        # Runtime selection verifies these bytes too. Resolve notice paths
        # once so they work independently of the maintainer's current cwd.
        row['notices'] = [dict(item, file=str(checked_file(item, base))) for item in row.get('notices', [])]
        supplements[name] = row
    selection = select(qt, flavor, supplements=supplements)
    if not selection['binary_selection_complete']:
        raise ValueError('The runtime release has missing binary license/dependency evidence: '
                         + ', '.join(row['path'] for row in selection['unknown'])
                         + '; unresolved=' + str(len(selection['unresolved_dependencies'])))
    files = {name: Path(qt) / name for name in selection['files']}
    for name, row in data.get('assets', {}).items():
        relative_path(name)
        if name in files or name in selection['aliases'] or name in legal:
            raise ValueError('A release asset shadows another runtime file: ' + name)
        source = checked_file(row, base)
        if allows(row['expression'], flavor) is not True:
            raise ValueError('No permitted asset license: ' + name)
        if not row.get('source') or not row.get('notices'):
            raise ValueError('A release asset needs source and notice evidence: ' + name)
        # ELF assets cannot bypass the binary policy by being called data.
        with source.open('rb') as stream:
            if stream.read(4) == b'\x7fELF':
                raise ValueError('An ELF runtime belongs in the audited binary inventory: ' + name)
        files[name] = source
    all_rows = [*selection['files'].values(), *data.get('assets', {}).values()]
    for row in all_rows:
        sources = list(dict.fromkeys([*row.get('sources', []), *([row['source']] if row.get('source') else [
            root['downloadLocation'] for root in row.get('repositories', [])])]))
        if not sources or any(source not in delivered_sources for source in sources):
            raise ValueError('Missing matching corresponding source for ' + row.get('path', 'runtime asset') + ': ' + str(sources))
        notices = row.get('notices', [])
        # SPDX binary rows are connected to their component notice set by
        # source repository; supplemental/data rows name theirs explicitly.
        if not notices:
            notices = [name for source in sources for name in source_rows[source].get('notices', [])]
        for notice in notices:
            if isinstance(notice, dict):
                checked_file(notice, base)
            elif notice not in legal:
                raise ValueError('Missing component notice: ' + notice)
        if not notices:
            raise ValueError('Missing component license/copyright notice for ' + str(sources))
    # Check every installed runtime data file rather than assuming that the
    # nearest library's license covers QML, shaders, images and WebEngine data.
    omitted = []
    excluded = {row['path'] for row in selection['excluded']}
    for top in ('qml', 'resources', 'translations'):
        for path in sorted((Path(qt) / top).rglob('*')):
            if path.is_file():
                name = path.relative_to(qt).as_posix()
                if name not in files and name not in selection['aliases'] and name not in excluded:
                    omitted.append(name)
    reviewed_exclusions = data.get('excluded_assets', {})
    for name in omitted:
        row = reviewed_exclusions.get(name)
        if not row or not row.get('reason'):
            raise ValueError('Unclassified installed runtime asset: ' + name)
        checked_file(dict(row, file=str(Path(qt) / name)), base)
    files.update(legal)
    # Preserve the original SPDX documents and their full third-party license
    # text, not just our chosen top-level module expression.
    for path in inventory.documents:
        files['notices/sbom/' + Path(path).name] = Path(path)
    expected = {name: row['sha256'] for name, row in selection['files'].items()}
    expected.update({name: row['sha256'] for name, row in data.get('assets', {}).items()})
    expected.update({name: row['sha256'] for name, row in data.get('notices', {}).items()})
    expected.update({'notices/sbom/' + Path(path).name: digest for path, digest in inventory.evidence.items()})
    expected['notices/DISTRIBUTION-LICENSE'] = data['package_license']['sha256']
    return dict(files=files, aliases=selection['aliases'], selection=selection,
                expected_sha256=expected, package_license=package_license,
                sources=delivered_sources, manifest=data,
                manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest())


def package(prepared, profile, work, *, owners=None, include_loader=True):
    work = Path(work); work.mkdir(parents=True, exist_ok=True)
    source_manifest = work / 'runtime-sources.json'
    # Local build paths do not belong in the distributed source manifest.
    def public_value(value):
        if isinstance(value, dict):
            return {key: public_value(item) for key, item in value.items() if key != 'file'}
        if isinstance(value, list):
            return [public_value(item) for item in value]
        return value
    public = public_value(prepared['sources'])
    source_manifest.write_text(json.dumps(public, indent=2) + '\n')
    files = dict(prepared['files'], **{'notices/corresponding-sources.json': source_manifest})
    files['notices/DISTRIBUTION-LICENSE'] = prepared['package_license']
    if owners is not None:
        owners = {name: owners.get(name, {'base'}) for name in files}
    bundle = embed(files, aliases=prepared['aliases'], context=dict(
        qt=profile['minimum_qt'], flavor=profile['license_flavor'],
        release_manifest_sha256=prepared['manifest_sha256']), owners=owners)
    for row in bundle['manifest']['files']:
        expected = prepared['expected_sha256'].get(row['path'])
        if expected and row['sha256'] != expected:
            raise ValueError('A runtime release file changed during native compilation: ' + row['path'])
    if include_loader:
        bundle['c'] += loader(prepared['selection'], profile['qt_modules'])
        bundle['c'] = '#define BQT_BUNDLED_RUNTIME 1\n' + bundle['c']
    return bundle
