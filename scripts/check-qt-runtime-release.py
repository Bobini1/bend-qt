#!/usr/bin/env python3
"""Check release gating with real ELF dependencies and byte-pinned inputs."""
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
from runtime_release import prepare, package


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    report = ROOT / 'build/runtime-release-check'; report.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='bend-qt-runtime-release-') as temporary:
        base = Path(temporary); qt = base / 'qt'
        for name in ('lib', 'sbom', 'include/QtCore', 'qml/Fixture'):
            (qt / name).mkdir(parents=True)
        (qt / 'include/QtCore/qtcoreversion.h').write_text('#define QTCORE_VERSION_STR "6.12.0"\n')
        source = base / 'library.c'; source.write_text('int fixture(void) { return 42; }\n')
        binary = qt / 'lib/libQt6Core.so.6.12.0'
        subprocess.run(['cc', '-shared', '-fPIC', source, '-Wl,-soname,libQt6Core.so.6', '-o', binary], check=True)
        (qt / 'lib/libQt6Core.so.6').symlink_to(binary.name)
        repository = 'git://code.qt.io/qt/fixture.git@' + '1' * 40
        sbom = dict(packages=[dict(SPDXID='SPDXRef-repository', downloadLocation=repository),
            dict(SPDXID='SPDXRef-module', comment='CMake exported target name: Qt6::Core',
                 licenseConcluded='LGPL-3.0-only')],
            relationships=[dict(spdxElementId='SPDXRef-DOCUMENT', relationshipType='DESCRIBES', relatedSpdxElement='SPDXRef-repository')],
            files=[dict(fileName='lib/' + binary.name, SPDXID='SPDXRef-binary', licenseConcluded='LGPL-3.0-only',
                        checksums=[dict(algorithm='SHA256', checksumValue=sha(binary))])])
        (qt / 'sbom/fixture.spdx.json').write_text(json.dumps(sbom))
        notice = base / 'NOTICE'; notice.write_text('Fixture copyright and license notice for a release-gate test.\n')
        archive = base / 'source.tar.xz'
        with tarfile.open(archive, 'w:xz') as output:
            data = source.read_bytes(); info = tarfile.TarInfo('fixture/library.c'); info.size = len(data)
            output.addfile(info, io.BytesIO(data))
        asset = qt / 'qml/Fixture/qmldir'; asset.write_text('module Fixture\n')
        data = dict(schema=1, qt='6.12.0', flavor='lgpl', package_license=dict(file=notice.name, sha256=sha(notice)),
            sources={repository: dict(file=archive.name, sha256=sha(archive), url='https://example.invalid/source.tar.xz', notices=['notices/fixture.txt'])},
            notices={'notices/fixture.txt': dict(file=notice.name, sha256=sha(notice))},
            assets={'qml/Fixture/qmldir': dict(file=str(asset), sha256=sha(asset), expression='LGPL-3.0-only', source=repository, notices=['notices/fixture.txt'])})
        manifest = base / 'release.json'
        profile = dict(minimum_qt='6.12.0', license_flavor='lgpl', qt_modules=['QtCore'])

        def rejected(value, marker):
            manifest.write_text(json.dumps(value))
            try:
                prepare(manifest, qt, profile)
            except ValueError as error:
                assert marker in str(error), (marker, str(error))
            else:
                raise AssertionError('Accepted invalid release: ' + marker)

        manifest.write_text(json.dumps(data))
        valid = prepare(manifest, qt, profile)
        packaged = package(valid, profile, base / 'packed')
        assert packaged['assets'] and 'BQT_BUNDLED_RUNTIME' in packaged['c']
        assert {row['path'] for row in packaged['manifest']['files']} >= {
            'lib/' + binary.name, 'qml/Fixture/qmldir', 'notices/fixture.txt', 'notices/corresponding-sources.json'}
        value = copy.deepcopy(data); value['sources'] = {}; rejected(value, 'Missing matching corresponding source')
        value = copy.deepcopy(data); del value['package_license']; rejected(value, 'component-aware package LICENSE')
        value = copy.deepcopy(data); value['flavor'] = 'gpl'; rejected(value, 'does not match')
        value = copy.deepcopy(data); value['sources'][repository]['sha256'] = '0' * 64; rejected(value, 'input changed')
        value = copy.deepcopy(data); value['assets']['qml/Fixture/qmldir']['expression'] = 'GPL-3.0-only'; rejected(value, 'No permitted asset license')
        value = copy.deepcopy(data); value['assets'] = {}; rejected(value, 'Unclassified installed runtime asset')
        value = copy.deepcopy(data); value['assets']['qml/Fixture/qmldir'].update(file=str(binary), sha256=sha(binary)); rejected(value, 'ELF runtime belongs')
        value = copy.deepcopy(data); value['notices']['notices/fixture.txt']['sha256'] = '0' * 64; rejected(value, 'input changed')
        notice.write_text('Tampered notice\n'); rejected(data, 'input changed')
    (report / 'receipt.json').write_text(json.dumps(dict(passed=True, real_elf=True,
        missing_source_rejected=True, changed_archive_rejected=True, changed_notice_rejected=True,
        gpl_asset_rejected=True, unclassified_asset_rejected=True, elf_asset_bypass_rejected=True,
        boundary='Release input validation, not a complete Qt release artifact audit'), indent=2) + '\n')
    print('QT_RUNTIME_RELEASE_OK source_gate=1 notice_gate=1 gpl_gate=1 elf_policy=1')


if __name__ == '__main__':
    main()
