"""Prepare byte-pinned evidence for runtime binaries omitted from Qt's SBOM."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import urllib.request

from runtime_notices import collect_snapshot


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(url, cache, *, repository, revision):
    target = Path(cache) / url.rsplit('/', 1)[-1]
    target.parent.mkdir(parents=True, exist_ok=True)
    stamp = target.with_name(target.name + '.source.json')
    if stamp.is_file():
        row = json.loads(stamp.read_text())
        if row['url'] != url or not target.is_file() or digest(target) != row['sha256']:
            raise ValueError('A prepared third-party source changed: ' + str(target))
        return row
    temporary = target.with_name(target.name + '.download')
    request = urllib.request.Request(url, headers={'User-Agent': 'bend-qt-source-preparation/1'})
    with urllib.request.urlopen(request, timeout=60) as source, temporary.open('wb') as output:
        while chunk := source.read(1024 * 1024):
            output.write(chunk)
    temporary.replace(target)
    row = dict(source=url, file=str(target.resolve()), sha256=digest(target), url=url,
               repository=repository, revision=revision, submodules={})
    stamp.write_text(json.dumps(row, indent=2) + '\n')
    return row


def source_files(row, predicate):
    result = {}
    with tarfile.open(row['file'], 'r:*') as archive:
        for member in archive:
            path = member.name.partition('/')[2]
            if member.isfile() and predicate(path):
                result[path] = archive.extractfile(member).read()
    return result


def expression(files):
    values = {value.decode().split('SPDX-License-Identifier:', 1)[1].splitlines()[0].strip()
              for value in files.values() if b'SPDX-License-Identifier:' in value}
    if not values:
        raise ValueError('No source license declaration for an omitted Qt runtime binary')
    return ' AND '.join('(' + value + ')' for value in sorted(values))


def notice(row, output):
    texts = collect_snapshot(row)
    target = output / (row['repository'].rsplit('/', 1)[-1] + '-NOTICES.txt')
    target.write_text('Source: ' + row['url'] + '\n\n' + '\n\n'.join(
        'Original file: ' + path + '\n' + value for path, value in sorted(texts.items())))
    return dict(file=str(target.resolve()), sha256=digest(target))


def ffmpeg_version(qt):
    libraries = [path for path in (Path(qt) / 'lib').glob('libavutil.so.*') if not path.is_symlink()]
    if len(libraries) != 1:
        raise ValueError('A Qt runtime needs one unambiguous FFmpeg avutil library')
    # Query the installed binary in a fresh process, with its own Qt stub
    # dependencies. Lazy resolution matches Qt's optional backend loading.
    code = ('import ctypes, os, sys; '
            'library = ctypes.CDLL(sys.argv[1], mode=os.RTLD_LAZY); '
            'library.av_version_info.restype = ctypes.c_char_p; '
            'print(library.av_version_info().decode())')
    result = subprocess.run([sys.executable, '-c', code, str(libraries[0])], check=True,
        capture_output=True, text=True, env=dict(os.environ, LD_LIBRARY_PATH=str(Path(qt) / 'lib')))
    version = result.stdout.strip()
    if not re.fullmatch(r'[0-9]+\.[0-9]+(?:\.[0-9]+)?', version):
        raise ValueError('FFmpeg reports an unreviewed development version: ' + version)
    return version


def prepare(qt, snapshots, notices, output, cache):
    qt, output = Path(qt).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    sources, supplements, extra_notices = {}, {}, {}

    def add(path, license, source, legal, provenance, **extra):
        relative = Path(path).relative_to(qt).as_posix()
        supplements[relative] = dict(sha256=digest(path), expression=license, source=source,
            notices=[legal], provenance=provenance, **extra)

    icu = download('https://github.com/unicode-org/icu/releases/download/release-73-2/icu4c-73_2-src.tgz',
        cache, repository='unicode-org/icu', revision='release-73-2')
    header = source_files(icu, lambda path: path.endswith('/unicode/uvernum.h'))
    if len(header) != 1 or not re.search(rb'#define\s+U_ICU_VERSION\s+"73\.2"', next(iter(header.values()))):
        raise ValueError('ICU corresponding source has a different version')
    legal = notice(icu, output); sources[icu['source']] = icu
    extra_notices['notices/icu-NOTICES.txt'] = legal
    for name in ('libicudata.so.73.2', 'libicui18n.so.73.2', 'libicuuc.so.73.2'):
        add(qt / 'lib' / name, 'Unicode-DFS-2016', icu['source'], legal,
            dict(source_version='73.2', source_version_header_sha256=hashlib.sha256(next(iter(header.values()))).hexdigest(),
                 source_notice_files='Unmodified ICU source license files'))

    version = ffmpeg_version(qt)
    ffmpeg = download('https://ffmpeg.org/releases/ffmpeg-' + version + '.tar.xz', cache,
        repository='FFmpeg/FFmpeg', revision='n' + version)
    release = source_files(ffmpeg, lambda path: path == 'RELEASE')
    if release.get('RELEASE', b'').strip() != version.encode():
        raise ValueError('FFmpeg corresponding source has a different release')
    legal = notice(ffmpeg, output); sources[ffmpeg['source']] = ffmpeg
    extra_notices['notices/ffmpeg-NOTICES.txt'] = legal
    for path in sorted((qt / 'lib').glob('lib*.so.*')):
        if path.is_symlink() or not re.match(r'lib(?:avcodec|avformat|avutil|swresample|swscale)\.so\.', path.name):
            continue
        strings = re.findall(rb'[\x20-\x7e]{20,}', path.read_bytes())
        configs = [text.decode() for text in strings if b'--enable-shared' in text and b'--prefix=' in text]
        licenses = [text.decode() for text in strings if b'license: LGPL version 2.1 or later' in text]
        if (len(configs) != 1 or not licenses or '--enable-gpl' in configs[0]
                or '--enable-nonfree' in configs[0] or 'FFmpeg-n' + version not in configs[0]):
            raise ValueError('FFmpeg binary license/source build evidence is incomplete: ' + str(path))
        add(path, 'LGPL-2.1-or-later', ffmpeg['source'], legal,
            dict(binary_license_strings=licenses, binary_configuration=configs[0], upstream_release=version,
                 native_av_version_info=version),
            modules=['QtMultimedia'])
    multimedia_source = next(key for key in snapshots if '/qtmultimedia.git' in key)
    multimedia = snapshots[multimedia_source]
    for path in sorted((qt / 'lib').glob('libQt6FFmpegStub-*.so.*')):
        if path.is_symlink():
            continue
        kind = path.name.split('FFmpegStub-', 1)[1].split('.so.', 1)[0]
        matching = source_files(multimedia, lambda name: name.endswith('/qffmpegsymbols-' + kind + '.cpp'))
        if len(matching) != 1:
            raise ValueError('No exact Qt FFmpeg stub source: ' + path.name)
        add(path, expression(matching), multimedia_source, notices[multimedia_source],
            dict(source_files={name: hashlib.sha256(raw).hexdigest() for name, raw in matching.items()},
                 source_archive_sha256=multimedia['sha256']), modules=['QtMultimedia'])
    webengine_source = next(key for key in snapshots if '/qtwebengine.git' in key)
    webengine = snapshots[webengine_source]
    matching = source_files(webengine, lambda name: name == 'src/process/main.cpp')
    if len(matching) != 1:
        raise ValueError('No exact Qt WebEngineProcess source')
    add(qt / 'libexec/QtWebEngineProcess', expression(matching), webengine_source, notices[webengine_source],
        dict(source_files={name: hashlib.sha256(raw).hexdigest() for name, raw in matching.items()},
             source_archive_sha256=webengine['sha256']), modules=['QtWebEngineCore'])
    webview_source = next(key for key in snapshots if '/qtwebview.git' in key)
    webview = snapshots[webview_source]
    # Older installers already ship this backend and describe its exact bytes
    # in SPDX. Only the omitted, locally built backend needs supplemental proof.
    from qt_licenses import Inventory
    plugin = qt / 'plugins/webview/libqtwebview_webengine.so'
    inventory = Inventory(qt)
    if plugin.relative_to(qt).as_posix() in inventory.files:
        inventory.binary(plugin, 'gpl')
        return dict(schema=1, sources=sources, supplements=supplements, notices=extra_notices,
                    boundary='Byte-pinned omitted binary evidence and upstream source/license declarations; full release closure is a separate check')
    version = qt.parent.name
    build = Path.home() / ('.cache/bend-qt-webview-' + version)
    if not (build / 'source/.git').is_dir():
        build = Path.home() / '.cache/bend-qt-generator/webview-plugin-build'
        cache_text = (build / 'CMakeCache.txt').read_text()
        source = Path(re.search(r'^CMAKE_HOME_DIRECTORY:INTERNAL=(.+)$', cache_text, re.M)[1])
        staged = build.parent / 'webview-plugin-stage/plugins/webview/libqtwebview_webengine.so'
    else:
        source = build / 'source'
        staged = build / 'stage/plugins/webview/libqtwebview_webengine.so'
    command = ['git', '-c', 'safe.directory=' + str(source), '-c', 'core.filemode=false',
               '-c', 'core.autocrlf=true', '-C', str(source)]
    head = subprocess.run([*command, 'rev-parse', 'HEAD'], check=True,
                          capture_output=True, text=True).stdout.strip()
    changed = subprocess.run([*command, 'status', '--porcelain'], check=True,
                             capture_output=True, text=True).stdout.strip()
    if head != webview['revision'] or changed or digest(plugin) != digest(staged):
        raise ValueError('The local WebView plugin differs from its matching clean source/build stage')
    matching = source_files(webview, lambda name: name.startswith('src/plugins/webengine/') and name.endswith(('.cpp', '.h')))
    inputs = [path for path in (build / 'configure.log', build / 'build.log', build / 'plugin.sha256',
                               build / 'config.summary', build / 'CMakeCache.txt', build / 'build.ninja') if path.is_file()]
    if not inputs:
        raise ValueError('Missing WebView plugin build evidence')
    add(plugin, expression(matching), webview_source, notices[webview_source],
        dict(source_revision=head, source_tree_clean=True, source_archive_sha256=webview['sha256'],
             build_inputs={str(path): digest(path) for path in inputs},
             configure_recipe='scripts/setup-qt-webview-backend.sh'), modules=['QtWebView'])
    return dict(schema=1, sources=sources, supplements=supplements, notices=extra_notices,
                boundary='Byte-pinned omitted binary evidence and upstream source/license declarations; full release closure is a separate check')


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qt-root', type=Path, required=True)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--notices', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cache', type=Path, default=Path.home() / '.cache/bend-qt-generator/corresponding-sources')
    args = parser.parse_args()
    snapshots = json.loads(args.sources.read_text())['sources']
    notices = json.loads(args.notices.read_text())['notices']
    result = prepare(args.qt_root, snapshots, notices, args.output.parent / 'supplement-notices', args.cache)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print('QT_RUNTIME_SUPPLEMENT_EVIDENCE_PREPARED files=' + str(len(result['supplements'])))


if __name__ == '__main__':
    main()
