#!/usr/bin/env python3
"""Check narrow source-metadata variants without relaxing other checksums."""
import hashlib
import io
from pathlib import Path
import sys
import tarfile
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
import qt_sources
from qt_targets import target


def main():
    rule = target('6.11.3')['source_metadata_variants'][0]
    code = b'int value = 7;\n'
    with tempfile.TemporaryDirectory(prefix='bend-qt-source-control-') as temporary:
        archive = Path(temporary) / 'source.tar.gz'
        snapshot = dict(repository=rule['repository'], revision=rule['revision'],
                        file=str(archive), submodules={})
        inventory = SimpleNamespace(evidence={}, by_sha1={
            rule['source_spdx_sha1']: [dict(evidence='qtremoteobjects-6.11.3.source.spdx',path='./.tag')],
            hashlib.sha1(code).hexdigest(): [dict(evidence='qtremoteobjects-6.11.3.source.spdx',path='./file.cpp')]})
        def write(stamp, body):
            with tarfile.open(archive, 'w:gz') as output:
                for name, raw in [('.tag', stamp), ('file.cpp', body)]:
                    entry = tarfile.TarInfo('qtremoteobjects-' + rule['revision'] + '/' + name)
                    entry.size = len(raw); output.addfile(entry, io.BytesIO(raw))
        def rejected(version):
            with patch.object(qt_sources, 'read_url', return_value=io.BytesIO(b'wrong upstream bytes')):
                try: qt_sources.verify_source_spdx(snapshot, inventory, 'qtremoteobjects', version=version)
                except ValueError as error:
                    if 'differs from its source SPDX' not in str(error): raise
                else: raise RuntimeError('An unreviewed source mismatch was accepted')
        write((rule['revision'] + '\n').encode(), code)
        result = qt_sources.verify_source_spdx(snapshot, inventory, 'qtremoteobjects', version='6.11.3')
        assert not result['all_source_spdx_checksums_match']
        assert result['all_other_source_spdx_checksums_match'] and result['metadata_variants'] == [rule]
        rejected('6.12.0')
        write(b'unreviewed stamp\n', code); rejected('6.11.3')
        write((rule['revision'] + '\n').encode(), code.replace(b'7', b'9')); rejected('6.11.3')
    print('QT_SOURCE_SNAPSHOT_CHECKS_OK exact_variant=1 discrepancy_visible=1 wrong_version_rejected=1 changed_stamp_rejected=1 changed_code_rejected=1')


if __name__ == '__main__': main()
