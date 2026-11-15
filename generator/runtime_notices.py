"""Collect original component notices from verified source snapshots and SBOMs."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tarfile


def legal_path(path):
    parts = PurePosixPath(path).parts
    if not parts:
        return False
    return ('LICENSES' in parts or bool(re.fullmatch(
        r'(?:COPYING|LICENSE|LICENCE|NOTICE|COPYRIGHT|AUTHORS)(?:[._-].*)?',
        parts[-1], re.I)))


def collect_snapshot(row, prefix=''):
    archive = Path(row['file'])
    with archive.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != row['sha256']:
            raise ValueError('Corresponding-source archive changed: ' + str(archive))
    texts = {}
    with tarfile.open(archive, 'r|*') as source:
        for member in source:
            if not member.isfile():
                continue
            path = PurePosixPath(member.name)
            relative = PurePosixPath(*path.parts[1:]).as_posix()
            if legal_path(relative):
                raw = source.extractfile(member).read()
                texts[prefix + relative] = raw.decode('utf-8')
    for overlay in row.get('overlays', []):
        if legal_path(overlay['path']):
            raw = Path(overlay['file']).read_bytes()
            if hashlib.sha256(raw).hexdigest() != overlay['sha256']:
                raise ValueError('A source notice overlay changed')
            texts[prefix + overlay['path']] = raw.decode('utf-8')
    for path, child in row.get('submodules', {}).items():
        texts.update(collect_snapshot(child, prefix + path + '/'))
    return texts


def prepare(sources, inventory, output):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    result = {}
    for location, row in sorted(sources.items()):
        repository = row['repository'].rsplit('/', 1)[-1]
        target = output / (repository + '-NOTICES.txt')
        print('Collecting original notices: ' + repository, flush=True)
        lines = ['Original upstream component notices', '', 'Source: ' + row['url'],
                 'Source archive SHA-256: ' + row['sha256'], '']
        for path, document in inventory.documents.items():
            roots = inventory.repositories.get(path, [])
            if not any(root['downloadLocation'] == location for root in roots):
                continue
            lines += ['Upstream SPDX packages: ' + Path(path).name, '']
            for package in document.get('packages', []):
                lines += [package.get('name', ''), package.get('versionInfo', ''),
                          package.get('copyrightText', ''), package.get('licenseConcluded', ''),
                          package.get('licenseDeclared', ''), package.get('comment', ''), '']
            for license in document.get('hasExtractedLicensingInfos', []):
                lines += [license.get('licenseId', ''), license.get('name', ''), license.get('extractedText', ''), '']
            source_spdx = Path(path).with_name(Path(path).name.replace('.spdx.json', '.source.spdx'))
            if source_spdx.is_file():
                text = source_spdx.read_text()
                copyrights = sorted(set(re.findall(
                    r'^FileCopyrightText: (<text>.*?</text>|[^\n]*)', text, re.M | re.S)))
                lines += ['Upstream source copyright notices:', *copyrights, '']
        notices = collect_snapshot(row)
        if not notices:
            raise ValueError('No original license/notice text in ' + location)
        for path, text in sorted(notices.items()):
            lines += ['Original file: ' + path, text, '']
        target.write_text('\n'.join(lines))
        result[location] = dict(file=str(target.resolve()), sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                                original_notice_files=len(notices), source_archive_sha256=row['sha256'])
    return result


def main():
    import argparse
    from qt_licenses import Inventory
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qt-root', type=Path, required=True)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sources = json.loads(args.sources.read_text())['sources']
    result = prepare(sources, Inventory(args.qt_root), args.output)
    (args.output / 'notices.json').write_text(json.dumps(dict(schema=1, notices=result,
        boundary='Original upstream license files and SPDX notices; runtime selection and matching-source/build review remain separate gates'), indent=2) + '\n')


if __name__ == '__main__':
    main()
