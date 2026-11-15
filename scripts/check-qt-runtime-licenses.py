#!/usr/bin/env python3
"""Verify the selected Qt build's module licensing and restricted profiles."""
import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
from qt_licenses import Inventory, SourceInventory, allows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qt-root', type=Path, default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    parser.add_argument('--work', type=Path, default=ROOT / 'build/runtime-license-check')
    args = parser.parse_args()
    work = args.work.resolve(); work.mkdir(parents=True, exist_ok=True)
    inventory = Inventory(args.qt_root)
    sources = SourceInventory(args.qt_root, inventory)
    qml_source = sources.match(args.qt_root / 'qml/QtTest/TestCase.qml', 'lgpl')
    assert qml_source['allowed'] is True and qml_source['exact_source_match'], qml_source
    modules = json.loads((ROOT / 'generator/qt612/profile.json').read_text())['qt_modules']
    modules = sorted(set(modules) | {'QtCharts', 'QtDataVisualization'})
    lgpl = inventory.distribution(modules, 'lgpl')
    gpl = inventory.require(modules, 'gpl')
    assert not lgpl['unknown'], lgpl['unknown']
    excluded = {row['module'] for row in lgpl['excluded']}
    assert {'QtGraphs', 'QtCharts', 'QtDataVisualization', 'QtQuick3D', 'QtHttpServer', 'QtCanvasPainter'} <= excluded
    assert {'QtCore', 'QtGui', 'QtWidgets', 'QtQuick', 'QtQml', 'QtMultimedia', 'QtWebSockets'} <= {
        row['module'] for row in lgpl['included']}
    assert allows('LGPL-3.0-only AND GPL-3.0-only', 'lgpl') is False
    assert allows('LicenseRef-Qt-Commercial OR (LGPL-3.0-only AND BSD-3-Clause)', 'lgpl') is True
    assert allows('LGPL-3.0-only AND LicenseRef-Unreviewed', 'lgpl') is None
    assert allows('LGPL-NOT-A-LICENSE', 'lgpl') is None
    assert allows('GPL-NOT-A-LICENSE', 'gpl') is None
    assert allows('GPL-3.0-only WITH Qt-GPL-exception-1.0', 'lgpl') is False
    assert allows('GPL-3.0-only WITH Qt-GPL-exception-1.0', 'lgpl', code_generator=True) is True
    assert allows('GPL-3.0-only', 'lgpl', code_generator=True) is False
    assert allows('LGPL-3.0-only WITH Qt-GPL-exception-1.0', 'lgpl', code_generator=True) is None
    qsb = inventory.code_generator('bin/qsb')
    rcc = inventory.code_generator('libexec/rcc')
    profile = json.loads((ROOT / 'generator/qt612-lgpl/profile.json').read_text())
    assert profile['package_name'] == 'qt' and profile['license_flavor'] == 'lgpl'
    assert set(profile['qt_modules']) == {row['module'] for row in lgpl['included']}
    inventory.require(profile['qt_modules'], 'lgpl')
    core = inventory.binary('lib/libQt6Core.so.6', 'lgpl')
    assert core['sha256'] and core['path'].endswith('6.12.0')
    try:
        inventory.binary('lib/libQt6Graphs.so.6', 'lgpl')
    except ValueError:
        pass
    else:
        raise AssertionError('A GPL runtime binary entered the LGPL distribution')
    # A matching module name cannot authorize modified/unlisted binary bytes.
    with tempfile.TemporaryDirectory(prefix='bend-qt-license-') as temporary:
        fixture = Path(temporary); (fixture / 'sbom').mkdir(); (fixture / 'lib').mkdir()
        binary = fixture / 'lib/libExample.so'; binary.write_bytes(b'original')
        import hashlib
        data = dict(files=[dict(SPDXID='SPDXRef-binary', fileName='./lib/libExample.so',
            licenseConcluded='LGPL-3.0-only', checksums=[dict(algorithm='SHA256',
                checksumValue=hashlib.sha256(binary.read_bytes()).hexdigest())])])
        (fixture / 'sbom/test.spdx.json').write_text(json.dumps(data))
        checked = Inventory(fixture); checked.binary('lib/libExample.so', 'lgpl')
        binary.write_bytes(b'modified')
        try:
            checked.binary('lib/libExample.so', 'lgpl')
        except ValueError as error:
            assert 'differs' in str(error)
        else:
            raise AssertionError('SPDX evidence accepted modified binary bytes')
        # An unordered SPDX license-ID set cannot be treated as an OR license.
        datafile = fixture / 'asset.png'; datafile.write_bytes(b'fixture asset bytes')
        digest = hashlib.sha1(datafile.read_bytes()).hexdigest()
        (fixture / 'sbom/test.source.spdx').write_text('FileName: ./asset.png\nSPDXID: SPDXRef-source\n'
            + 'FileChecksum: SHA1: ' + digest + '\nLicenseConcluded: NOASSERTION\n'
            + 'LicenseInfoInFile: LGPL-3.0-only\nLicenseInfoInFile: GPL-3.0-only\n'
            + 'FileCopyrightText: <text>Fixture copyright</text>\n\n')
        source_inventory = SourceInventory(fixture)
        assert source_inventory.match(datafile, 'lgpl')['allowed'] is None
        datafile.write_bytes(b'changed asset bytes')
        assert not source_inventory.match(datafile, 'lgpl')['exact_source_match']
    try:
        inventory.require(['QtCore', 'QtGraphs'], 'lgpl')
    except ValueError:
        pass
    else:
        raise AssertionError('GPL module entered an LGPL-option distribution')
    receipt = dict(passed=True, qt='6.12.0', lgpl=lgpl, gpl=gpl,
        comprehensive_lgpl_profile=True, actual_binary_checksum=True, modified_binary_rejected=True,
        separate_code_generators=[qsb, rcc],
        boundary='Qt module/license selection from actual SPDX evidence; complete file notices, source delivery and runtime deployment are separate required checks')
    (work / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('QT612_RUNTIME_LICENSES_OK module_evidence=1 gpl_separation=1 unknown_rejection=1')


if __name__ == '__main__':
    main()
