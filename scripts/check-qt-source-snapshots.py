#!/usr/bin/env python3
"""Check narrow source-metadata variants without relaxing other checksums."""
import hashlib
import io
import json
from pathlib import Path
import sys
import subprocess
import tarfile
import tempfile
import urllib.error
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
import qt_sources
from qt_targets import target


def check_rate_limit_recovery():
    with tempfile.TemporaryDirectory(prefix='bend-qt-source-git-control-') as temporary:
        root = Path(temporary)
        source = root / 'source'
        run = subprocess.run
        def git(*arguments):
            return run(['git', '-C', str(source), *arguments], check=True,
                       capture_output=True, text=True).stdout.strip()
        run(['git', 'init', str(source)], check=True, capture_output=True)
        git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
            'commit', '--allow-empty', '-m', 'Child source')
        child = git('rev-parse', 'HEAD')
        git('update-index', '--add', '--cacheinfo', '160000,' + child + ',dependencies/source')
        git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
            'commit', '-m', 'Pinned source submodule')
        revision = git('rev-parse', 'HEAD')
        git('config', 'uploadpack.allowFilter', 'true')

        def transport(command, *arguments, **keywords):
            # Only replace the network boundary. Production bare-repository
            # fetch and ls-tree commands execute against a real local Git repo.
            command = [str(source) if word == 'https://github.com/qt/fixture.git' else word
                       for word in command]
            return run(command, *arguments, **keywords)

        for code in (403, 429):
            cache = root / str(code)
            cache.mkdir()
            error = urllib.error.HTTPError('https://api.github.com/', code, 'Rate limited', {}, None)
            with patch.object(qt_sources, 'read_url', side_effect=error), \
                    patch.object(qt_sources.subprocess, 'run', side_effect=transport):
                tree = qt_sources.github_source_tree('qt/fixture', revision, cache)
            assert tree == dict(tree=[dict(path='dependencies/source', mode='160000', sha=child)],
                                truncated=False, source='git-ls-tree')
            with patch.object(qt_sources, 'read_url', side_effect=AssertionError('Unexpected HTTP request')), \
                    patch.object(qt_sources.subprocess, 'run', side_effect=AssertionError('Unexpected Git fetch')):
                assert qt_sources.github_source_tree('qt/fixture', revision, cache) == tree
        cache = root / 'missing'
        cache.mkdir()
        with patch.object(qt_sources, 'read_url', side_effect=urllib.error.HTTPError(
                'https://api.github.com/', 404, 'Not found', {}, None)), \
                patch.object(qt_sources.subprocess, 'run', side_effect=AssertionError('Unexpected fallback')):
            try:
                qt_sources.github_source_tree('qt/fixture', revision, cache)
            except urllib.error.HTTPError as error:
                assert error.code == 404
            else:
                raise AssertionError('Missing source was accepted')
        with patch.object(qt_sources, 'read_url', return_value=io.BytesIO(json.dumps(
                dict(tree=[], truncated=True)).encode())):
            try:
                qt_sources.github_source_tree('qt/fixture', revision, cache)
            except ValueError as error:
                assert 'truncated' in str(error)
            else:
                raise AssertionError('Incomplete tree was accepted')
    print('PASS real Git source metadata recovery for HTTP 403/429, cache reuse, strict 404/truncation failures')


def main():
    check_rate_limit_recovery()
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
