"""Prepare exact upstream source snapshots named by the installed Qt SBOMs.

Archives are maintainer release inputs, never a consumer download. Gitlinks
must have their own snapshots; a parent archive alone is not complete source.
"""
import configparser
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile
import urllib.request
import urllib.error
from urllib.parse import quote, urljoin

# Qt's Data Visualization SBOM uses the CMake project name in its repository
# URL. The official Qt supermodule names the repository qtdatavis3d:
# https://github.com/qt/qt5/blob/v6.12.0/.gitmodules
REPOSITORY_MIRRORS = {'qtdatavisualization': 'qtdatavis3d', 'qtpdf': 'qtwebengine'}


def read_url(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'bend-qt-source-preparation/1'})
    return urllib.request.urlopen(request, timeout=60)


def github_repository(location):
    match = re.fullmatch(r'(?:git|https)://code\.qt\.io/(?:cgit/)?qt/([a-z0-9-]+)\.git@([0-9a-f]{40})', location)
    if match:
        return 'qt/' + REPOSITORY_MIRRORS.get(match[1], match[1]), match[2]
    match = re.fullmatch(r'https://github\.com/([A-Za-z0-9_-]+/[A-Za-z0-9_.-]+)\.git@([0-9a-f]{40})', location)
    if match:
        return match[1], match[2]
    match = re.fullmatch(r'https://code\.qt\.io/playground/([a-z0-9-]+)\.git@([0-9a-f]{40})', location)
    if match:
        return 'playground/' + match[1], match[2]
    raise ValueError('No reviewed source snapshot transport for ' + location)


def resolve_release_source(location, version):
    if re.search(r'@[0-9a-f]{40}$', location):
        github_repository(location)
        return location
    match = re.fullmatch(r'git://code\.qt\.io/qt/([a-z0-9-]+)\.git', location)
    if not match or not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('No immutable Qt source identity: ' + location)
    # Some addon SBOMs record the release rather than a commit. Resolve that
    # tag once, then verify the snapshot against every source-SBOM checksum.
    tag = 'refs/tags/v' + version
    repository = REPOSITORY_MIRRORS.get(match[1], match[1])
    result = subprocess.run(['git', 'ls-remote', 'https://github.com/qt/' + repository + '.git', tag, tag + '^{}'],
                            text=True, capture_output=True, check=True)
    refs = dict(reversed(line.split()) for line in result.stdout.splitlines())
    revision = refs.get(tag + '^{}', refs.get(tag))
    if not revision or not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('Cannot resolve the Qt source release: ' + location)
    return location + '@' + revision


def verify_source_spdx(snapshot, source_inventory, name, *, version=None):
    expected = {}
    for digest, rows in source_inventory.by_sha1.items():
        for row in rows:
            if Path(row['evidence']).name.startswith(name + '-'):
                path = row['path'].removeprefix('./')
                if path in expected and expected[path] != digest:
                    raise ValueError('Conflicting source checksums: ' + path)
                expected[path] = digest
    if not expected:
        raise ValueError('No source SPDX file inventory for ' + name)
    actual = {}

    def inspect(row, prefix=''):
        root = row['repository'].rsplit('/', 1)[1] + '-' + row['revision'] + '/'
        with tarfile.open(row['file'], 'r|gz') as archive:
            for member in archive:
                if not member.isfile():
                    continue
                relative = prefix + member.name.removeprefix(root)
                if relative in expected:
                    with archive.extractfile(member) as stream:
                        actual[relative] = hashlib.file_digest(stream, 'sha1').hexdigest()
        for path, child in row['submodules'].items():
            inspect(child, prefix + path + '/')

    inspect(snapshot)
    # A source stamp discrepancy is never a general checksum exception. This
    # release-specific table pins both hashes and the exact upstream revision;
    # the delivered archive stays unmodified and the discrepancy stays visible.
    from qt_targets import target
    variants = []
    for rule in target(version).get('source_metadata_variants', []) if version else []:
        if (snapshot['repository'] == rule['repository'] and snapshot['revision'] == rule['revision']
                and rule['path'] == '.tag' and expected.get('.tag') == rule['source_spdx_sha1']
                and actual.get('.tag') == rule['delivered_sha1']):
            variants.append(dict(rule))
    varied = {row['path'] for row in variants}
    bad = [path for path, digest in expected.items() if actual.get(path) != digest and path not in varied]
    # Git archive honors export-ignore/export-subst. Qt's source SBOM describes
    # the checkout, including ignored Git metadata and the unexpanded .tag.
    # Preserve those exact upstream blobs as explicit, separately downloadable
    # overlays instead of silently accepting an archive/SBOM mismatch.
    def origin(row, path):
        for child_path, child in row['submodules'].items():
            if path.startswith(child_path + '/'):
                return origin(child, path[len(child_path) + 1:])
        return row, path

    for path in bad:
        row, relative = origin(snapshot, path)
        if Path(relative).is_absolute() or '..' in Path(relative).parts:
            raise ValueError('Source SPDX overlay path escapes its snapshot: ' + relative)
        url = f'https://raw.githubusercontent.com/{row["repository"]}/{row["revision"]}/' + quote(relative, safe='/')
        cached = Path(row['file']).parent / 'overlays' / (row['repository'].rsplit('/', 1)[1] + '-' + row['revision']) / relative
        if cached.is_file():
            raw = cached.read_bytes()
        else:
            with read_url(url) as response:
                raw = response.read()
        if hashlib.sha1(raw).hexdigest() != expected[path]:
            raise ValueError('The upstream source blob differs from its source SPDX: ' + path)
        cached.parent.mkdir(parents=True, exist_ok=True); cached.write_bytes(raw)
        overlay = dict(path=relative, file=str(cached.resolve()), sha256=hashlib.sha256(raw).hexdigest(), url=url)
        if overlay not in row.setdefault('overlays', []):
            row['overlays'].append(overlay)
        actual[path] = expected[path]
    bad = [path for path, digest in expected.items() if actual.get(path) != digest and path not in varied]
    if bad:
        raise ValueError(f'The source archive differs from its source SPDX ({len(bad)} files): ' + ', '.join(bad[:12]))
    return dict(source_files=len(expected), all_source_spdx_checksums_match=not variants,
                all_other_source_spdx_checksums_match=True, metadata_variants=variants,
                overlay_files=sum(len(row.get('overlays', [])) for row in [snapshot, *snapshot['submodules'].values()]),
                evidence_sha256={path: digest for path, digest in source_inventory.evidence.items()
                                 if Path(path).name.startswith(name + '-')})


def prepare(location, cache, *, _active=None):
    repository, revision = github_repository(location)
    active = set() if _active is None else _active
    if location in active:
        raise ValueError('Cyclic source submodule graph: ' + location)
    active.add(location)
    cache = Path(cache); cache.mkdir(parents=True, exist_ok=True)
    name = repository.rsplit('/', 1)[1]
    archive = cache / (name + '-' + revision + '.tar.gz')
    native_git = repository.startswith('playground/')
    git_cache = cache / 'git' / (name + '-' + revision)
    url = 'https://code.qt.io/' + repository + '.git' if native_git else f'https://codeload.github.com/{repository}/tar.gz/{revision}'
    origin_cache = archive.with_suffix('.origin.json')
    if origin_cache.is_file():
        origin = json.loads(origin_cache.read_text())
        native_git, url = origin['transport'] == 'git', origin['url']

    def ensure_git():
        if not git_cache.is_dir():
            subprocess.run(['git', 'init', '--bare', str(git_cache)], text=True, capture_output=True, check=True)
        present = subprocess.run(['git', '-C', str(git_cache), 'cat-file', '-e', revision], text=True, capture_output=True)
        if present.returncode:
            subprocess.run(['git', '-C', str(git_cache), 'fetch', '--depth=1', url, revision], text=True, capture_output=True, check=True)

    if native_git:
        ensure_git()
    if not archive.is_file():
        temporary = archive.with_suffix('.partial')
        response = None
        if not native_git:
            try:
                response = read_url(url)
            except urllib.error.HTTPError as error:
                if error.code != 404 or '://code.qt.io/' not in location:
                    raise
                # A few Qt tool submodules have no GitHub mirror. Fetch the
                # exact commit from Qt's authoritative HTTPS Git endpoint.
                native_git = True
                url = location.rsplit('@', 1)[0].replace('git://', 'https://')
                ensure_git()
        if native_git:
            command = ['git', '-C', str(git_cache), 'archive', '--format=tar', '--prefix=' + name + '-' + revision + '/', revision]
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            with temporary.open('wb') as target, gzip.GzipFile(fileobj=target, mode='wb', filename='', mtime=0) as compressed:
                while chunk := process.stdout.read(1024 * 1024):
                    compressed.write(chunk)
            error = process.stderr.read().decode()
            if process.wait():
                raise ValueError('Cannot archive corresponding Git source: ' + error)
        else:
            with response as source, temporary.open('wb') as target:
                while chunk := source.read(1024 * 1024):
                    target.write(chunk)
        temporary.replace(archive)
        origin_cache.write_text(json.dumps(dict(transport='git' if native_git else 'archive', url=url)) + '\n')
    with archive.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    with tarfile.open(archive, 'r:gz') as source:
        members = source.getmembers()
        prefix = name + '-' + revision + '/'
        if not members or any(not (member.name + '/').startswith(prefix) for member in members):
            raise ValueError('The source snapshot has an unexpected archive prefix: ' + str(archive))
        gitmodules = next((member for member in members if member.name == prefix + '.gitmodules'), None)
        submodules = {}
        if gitmodules:
            config = configparser.ConfigParser(interpolation=None)
            config.read_string(source.extractfile(gitmodules).read().decode())
            # The archive omits gitlink commit IDs. Resolve the exact parent's
            # tree, then pin every referenced child before claiming closure.
            if native_git:
                tree = subprocess.run(['git', '-C', str(git_cache), 'ls-tree', '-r', revision], text=True, capture_output=True, check=True)
                links = {line.split('\t', 1)[1]: line.split()[2] for line in tree.stdout.splitlines() if line.startswith('160000 ')}
            else:
                tree_cache = cache / ('tree-' + repository.replace('/', '-') + '-' + revision + '.json')
                if tree_cache.is_file():
                    tree = json.loads(tree_cache.read_text())
                else:
                    with read_url(f'https://api.github.com/repos/{repository}/git/trees/{revision}?recursive=1') as response:
                        tree = json.load(response)
                    tree_cache.write_text(json.dumps(tree, sort_keys=True) + '\n')
                if tree.get('truncated'):
                    raise ValueError('The source tree inventory is truncated: ' + location)
                links = {row['path']: row['sha'] for row in tree['tree'] if row['mode'] == '160000'}
            configured = set()
            for section in config.sections():
                path, child_url = config[section]['path'].strip('"'), config[section]['url'].strip('"')
                if path not in links:
                    raise ValueError('Submodule source revision is absent: ' + path)
                configured.add(path)
                if child_url.startswith('.'):
                    child_url = urljoin(location.rsplit('@', 1)[0].replace('git://', 'https://') + '/', child_url)
                child = child_url + '@' + links[path]
                submodules[path] = prepare(child, cache, _active=active)
            if set(links) != configured:
                raise ValueError('Unconfigured source gitlinks: ' + str(set(links) - configured))
    active.remove(location)
    return dict(source=location, file=str(archive.resolve()), sha256=digest, url=url,
                source_transport='git' if native_git else 'archive',
                repository=repository, revision=revision, submodules=submodules,
                submodule_closure_complete=True,
                boundary='Exact unmodified source snapshots and gitlink closure; component notices and build/installation instructions require separate preparation')


def prepare_verified(location, version, cache, source_inventory, name):
    resolved = resolve_release_source(location, version)
    selection = 'recorded-source-ref'
    try:
        snapshot = prepare(resolved, cache)
    except subprocess.CalledProcessError as error:
        message = (error.stderr or '') + (error.stdout or '')
        if not any(marker in message for marker in ('not our ref', "couldn't find remote ref")):
            raise
        # Some installer SBOMs name an integration commit absent from public
        # Git, while the release tag contains the exact released source tree.
        # A tag is accepted only after every source-SBOM file checksum passes.
        public = resolve_release_source(location.rsplit('@', 1)[0], version)
        if public == resolved:
            raise
        snapshot = prepare(public, cache)
        resolved, selection = public, 'public-release-tag-verified-against-source-sbom'
    snapshot['source_spdx_verification'] = verify_source_spdx(snapshot, source_inventory, name, version=version)
    snapshot.update(source=location, resolved_source=resolved, source_selection=selection)
    return snapshot


def main():
    import argparse
    from qt_licenses import Inventory, SourceInventory
    from qt_targets import installed_version
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qt-root', type=Path, required=True)
    parser.add_argument('--cache', type=Path, default=Path.home() / '.cache/bend-qt-generator/corresponding-sources')
    parser.add_argument('--only', action='append', help='Repository name, for an explicit partial preparation')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    inventory = Inventory(args.qt_root)
    source_inventory = SourceInventory(args.qt_root, inventory)
    version = installed_version(args.qt_root)
    sources = sorted({root['downloadLocation'] for roots in inventory.repositories.values() for root in roots})
    result = {}
    for location in sources:
        name = location.rsplit('/', 1)[-1].split('.git')[0]
        if args.only and name not in args.only:
            continue
        print('Preparing source: ' + location, flush=True)
        snapshot = prepare_verified(location, version, args.cache, source_inventory, name)
        result[location] = snapshot
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(dict(schema=1, sources=result,
            requested_complete_repository_selection=not args.only,
            complete_repository_selection=not args.only and len(result) == len(sources),
            verification_complete=False, boundary='Source snapshot preparation only, not a licensed runtime release'), indent=2) + '\n')
    print('QT_SOURCE_SNAPSHOTS_PREPARED repositories=' + str(len(result)), flush=True)


if __name__ == '__main__':
    main()
