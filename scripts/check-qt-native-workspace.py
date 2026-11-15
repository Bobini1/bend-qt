#!/usr/bin/env python3
"""Focused Linux-local workspace checks, including real tiny ELF object reuse."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
import native_workspace


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_backend(work, qt):
    """Use the real backend while all ordinary requested artifacts stay put."""
    from backend import compile_backend
    spec = importlib.util.spec_from_file_location('workspace_backend_control', ROOT / 'scripts/check-qt612-backend.py')
    control = importlib.util.module_from_spec(spec); spec.loader.exec_module(control)
    requested = work / 'backend-enabled'; requested.mkdir(parents=True, exist_ok=True)
    source, header = requested / 'native.cpp', requested / 'cache-input.h'
    source.write_text('#include <QtCore/QString>\n' + control.NATIVE.replace(
        'return CACHE_VALUE;', 'return QString::number(CACHE_VALUE).toInt();'))
    header.write_text('#define CACHE_VALUE 19\n')
    cache = Path.home() / '.cache/bend-qt-generator/native-workspace-tests'
    with patch.dict(os.environ, {'BQT_NATIVE_WORKSPACE':str(cache)}):
        first, _, initial = compile_backend(source, qt, requested, 'clang++-19', ['QtCore'])
        local = native_workspace.actual_work(requested)
        assert local != requested and local.is_relative_to(cache)
        assert (local / 'wrappers.o').is_file() and not (requested / 'wrappers.o').exists()
        assert not (requested / 'native-compile-cache.json').exists()
        assert digest(local / 'native.so') == digest(requested / 'native.so')
        assert (requested / 'backend.json').is_file() and (requested / 'native-compile.log').is_file()
        control.check_consumer(requested, first, 19)
        second, _, repeated = compile_backend(source, qt, requested, 'clang++-19', ['QtCore'])
        assert repeated['compile_cache_hit'] and second == first
        resources = json.loads((requested / 'native-package-resources.json').read_text())
        assert resources['cache_hit'], resources
        stamp = local / 'native-package-cache.json'
        saved = json.loads(stamp.read_text())
        assert saved['key']['loader'] == digest(ROOT / 'generator/templates/embedded_elf.c')
        qt_library = next(name for name in saved['dependencies'] if 'libQt6Core' in name)
        assert saved['dependencies'][qt_library]['sha256'] == digest(Path(qt_library).resolve())
        # Check that neither a stale loader certificate nor a corrupted native
        # library certificate can bypass re-linking. Installed inputs stay intact.
        saved['key']['loader'] = '0' * 64
        stamp.write_text(json.dumps(saved))
        repaired, _, after_loader = compile_backend(source, qt, requested, 'clang++-19', ['QtCore'])
        assert after_loader['compile_cache_hit'] and repaired == first
        assert not json.loads((requested / 'native-package-resources.json').read_text())['cache_hit']
        saved = json.loads(stamp.read_text())
        saved['dependencies'][qt_library]['sha256'] = '0' * 64
        stamp.write_text(json.dumps(saved))
        repaired, _, after_library = compile_backend(source, qt, requested, 'clang++-19', ['QtCore'])
        assert after_library['compile_cache_hit'] and repaired == first
        assert not json.loads((requested / 'native-package-resources.json').read_text())['cache_hit']
        header.write_text('#define CACHE_VALUE 20\n')
        changed, _, invalidated = compile_backend(source, qt, requested, 'clang++-19', ['QtCore'])
        assert not invalidated['compile_cache_hit'] and changed != first
        control.check_consumer(requested, changed, 20)
        failed = requested / 'failure'; failed.mkdir(exist_ok=True)
        bad_source = failed / 'bad.cpp'; bad_source.write_text('#error WORKSPACE_DIAGNOSTIC_FAILURE\n')
        try:
            compile_backend(bad_source, qt, failed, 'clang++-19', ['QtCore'])
        except RuntimeError:
            pass
        else:
            raise AssertionError('A failing compiler input was accepted')
        assert 'WORKSPACE_DIAGNOSTIC_FAILURE' in (failed / 'native-compile.log').read_text()
        assert native_workspace.actual_work(failed) != failed and not (failed / 'native.so').exists()
        report = json.loads((requested / 'native-workspace.json').read_text())
        assert report['enabled'] and report['source'] == str(source.resolve())
    return dict(passed=True, enabled_relocation=True, work=str(local), requested=str(requested),
        native_object_stays_local=True, native_payload_and_reports_published=True,
        ordinary_payload_consumer=True, unchanged_compile_and_package_cache_hits=True,
        real_header_change_invalidates=True, loader_and_library_certificates_rechecked=True,
        compiler_failure_log_published=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=ROOT / 'build/native-workspace-test')
    parser.add_argument('--backend', action='store_true', help='Also check the production embedded-ELF backend with relocation enabled')
    parser.add_argument('--qt-root', type=Path, default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='bend-native-workspace-') as temporary:
        root = Path(temporary)
        requested = root / 'requested with spaces'
        source_directory = root / 'original source with spaces'; source_directory.mkdir()
        source = source_directory / 'input.cpp'
        header = source_directory / 'local.h'; header.write_text('#define VALUE 42\n')
        source.write_text('#include "local.h"\nextern "C" int value() { return VALUE; }\nextern "C" const char *origin() { return __FILE__; }\n')
        environment = dict(BQT_NATIVE_WORKSPACE=str(root / 'linux-cache'))
        workspace = native_workspace.open_workspace(source, requested, environ=environment)
        assert workspace.source == source and workspace.work != requested
        with workspace as selected:
            assert selected.work.is_dir() and selected.legacy_work == requested
            live = selected.work / 'shards/live.log'
            output = native_workspace.diagnostic_path(live)
            output.write_text('compiler started\n')
            assert output == requested / 'shards/live.log' and output.read_text() == 'compiler started\n'
            with ThreadPoolExecutor(max_workers=1) as pool:
                mapped = pool.submit(native_workspace.diagnostic_path, live).result()
            assert mapped == output
            (selected.work / 'native.so').write_bytes(b'final artifact')
            (selected.work / 'wrappers.o').write_bytes(b'internal object')
            (selected.work / 'native-compile-cache.json').write_text('{"private":true}')
            (selected.work / 'native-resources.json').write_text('{"elapsed":1}')
            selected.publish(['native.so'])
            assert (requested / 'native.so').read_bytes() == b'final artifact'
            assert not (requested / 'wrappers.o').exists()
            try:
                selected.publish('../outside')
            except ValueError:
                pass
            else:
                raise AssertionError('Publication escaped its workspace')
            competing = native_workspace.open_workspace(source, requested, environ=environment)
            try:
                with competing:
                    raise AssertionError('Concurrent reuse of one cache was admitted')
            except RuntimeError as error:
                assert 'already in use' in str(error)
        assert (requested / 'native-resources.json').is_file()
        assert not (requested / 'native-compile-cache.json').exists()
        assert native_workspace.diagnostic_path(live) == live
        receipt = json.loads((requested / 'native-workspace.json').read_text())
        assert receipt['original_source_path_preserved'] and not receipt['pch_paths_rewritten']
        assert native_workspace.actual_work(requested) == workspace.work
        assert native_workspace.actual_work(root / 'never-built') == root / 'never-built'
        original_receipt = (requested / 'native-workspace.json').read_bytes()
        (requested / 'native-workspace.json').write_text(json.dumps(dict(receipt, requested_work=str(root / 'another-work'))))
        try:
            native_workspace.actual_work(requested)
        except ValueError:
            pass
        else:
            raise AssertionError('A different requested directory was accepted by actual_work')
        (requested / 'native-workspace.json').write_bytes(original_receipt)
        # Different source directories, logical aliases and requested outputs
        # never share a compiler cache, even when the source bytes match.
        second = root / 'second'; second.mkdir()
        second_source = second / source.name; second_source.write_bytes(source.read_bytes())
        assert native_workspace.open_workspace(second_source, requested, environ=environment).work != workspace.work
        assert native_workspace.open_workspace(source, root / 'other-output', environ=environment).work != workspace.work
        source_alias = root / 'source-alias'; source_alias.symlink_to(source_directory, target_is_directory=True)
        assert native_workspace.open_workspace(source_alias / source.name, requested, environ=environment).work != workspace.work
        disabled = native_workspace.open_workspace(source, requested, environ=dict(BQT_NATIVE_WORKSPACE='off'))
        assert not disabled.enabled and disabled.work == requested
        with disabled:
            assert native_workspace.actual_work(requested) == requested
        with patch.object(native_workspace, '_wsl', return_value=True):
            auto = native_workspace.open_workspace('/mnt/t/Project/source.cpp', '/mnt/t/Project/build', environ={'XDG_CACHE_HOME':str(root)})
            assert auto.enabled and auto.work.is_relative_to(root / 'bend-qt-generator/native-workspaces')
            assert not native_workspace.open_workspace(source, requested, environ={}).enabled
        with patch.object(native_workspace, '_wsl', return_value=False):
            assert not native_workspace.open_workspace('/mnt/t/project/source.cpp', '/mnt/t/project/build', environ={}).enabled
        try:
            native_workspace.open_workspace(source, requested, environ={'BQT_NATIVE_WORKSPACE':'relative/cache'})
        except ValueError:
            pass
        else:
            raise AssertionError('A relative native cache root was accepted')
        # A tiny real object provides migration evidence. It is compiled from
        # its original directory; quoted includes and __FILE__ remain intact.
        old = root / 'legacy'; old.mkdir()
        obj, dep = old / 'wrappers.o', old / 'wrappers.d'
        flags = ['clang++-19','-std=c++17','-O0','-fPIC']
        subprocess.run([*flags,'-MD','-MF',str(dep),'-c',str(source),'-o',str(obj)], check=True, capture_output=True)
        assert str(source).encode() in obj.read_bytes()
        paths = shlex.split(dep.read_text().replace('\\\n','').partition(':')[2])
        key = dict(source=digest(source), source_path=str(source), logical_source_path=str(source), flags=flags,
            compiler=subprocess.run(['clang++-19','--version'], check=True, text=True, capture_output=True).stdout)
        record = dict(key=key, object=digest(obj), dependencies={str(Path(path).resolve()):digest(path) for path in paths})
        stamp = old / 'native-compile-cache.json'; stamp.write_text(json.dumps(record))
        proof = native_workspace.verify_artifact(obj, stamp, expected_key=key)
        assert proof and proof.digest == digest(obj)
        original_object = obj.read_bytes(); original_stamp = stamp.read_bytes()
        migration = native_workspace.open_workspace(source, old, environ=environment)
        with migration:
            assert migration.import_legacy_artifact('wrappers.o','native-compile-cache.json',expected_key=key)
            assert (migration.work / 'wrappers.o').read_bytes() == original_object
            assert json.loads((migration.work / 'native-compile-cache.json').read_text()) == record
            assert not migration.import_legacy_artifact('wrappers.o','native-compile-cache.json',expected_key=key)
        assert obj.read_bytes() == original_object and stamp.read_bytes() == original_stamp
        ambiguous = root / 'legacy-ambiguous'; ambiguous.mkdir()
        ambiguous_key = {name:value for name,value in key.items() if name != 'logical_source_path'}
        (ambiguous / 'wrappers.o').write_bytes(original_object)
        (ambiguous / 'native-compile-cache.json').write_text(json.dumps(dict(record, key=ambiguous_key)))
        with native_workspace.open_workspace(source, ambiguous, environ=environment) as uncertain:
            assert not uncertain.import_legacy_artifact('wrappers.o','native-compile-cache.json',expected_key=ambiguous_key)
        # No flags, compiler, dependency, object or binary-PCH bypass is allowed.
        for changed in (dict(key, flags=[*flags,'-DCHANGED']), dict(key, compiler='another compiler')):
            assert native_workspace.verify_artifact(obj, stamp, expected_key=changed) is None
        header.write_text('#define VALUE 99\n')
        assert native_workspace.verify_artifact(obj, stamp, expected_key=key) is None
        header.write_text('#define VALUE 42\n')
        obj.write_bytes(original_object + b'changed')
        assert native_workspace.verify_artifact(obj, stamp, expected_key=key) is None
        obj.write_bytes(original_object)
        pch = old / 'shared.pch'; pch.write_bytes(b'CPCHmust-not-relocate')
        pch_stamp = old / 'shared-cache.json'; pch_stamp.write_text(json.dumps(dict(record, object=digest(pch))))
        assert native_workspace.verify_artifact(pch, pch_stamp, expected_key=key) is None
        header.unlink()
        assert native_workspace.verify_artifact(obj, stamp, expected_key=key) is None
        # A failed build still publishes diagnostics and preserves its error.
        failed = native_workspace.open_workspace(source, root / 'failed', environ=environment)
        try:
            with failed:
                (failed.work / 'syntax.log').write_text('actual compiler failure\n')
                raise RuntimeError('original compiler error')
        except RuntimeError as error:
            assert str(error) == 'original compiler error'
        assert (failed.requested_work / 'syntax.log').read_text() == 'actual compiler failure\n'
        failed_publish = native_workspace.open_workspace(source, root / 'failed-publish', environ=environment)
        with patch.object(failed_publish, 'publish_reports', side_effect=ValueError('publication failed')):
            try:
                with failed_publish:
                    raise RuntimeError('compiler error wins')
            except RuntimeError as error:
                assert str(error) == 'compiler error wins'
        assert failed_publish.publish_errors == ['publication failed']
        # An __enter__ failure must not strand the exclusive lock or leave a
        # stale mapping visible to a later compile in this process.
        broken = native_workspace.open_workspace(source, root / 'broken-enter', environ=environment)
        with patch.object(broken, 'write_receipt', side_effect=OSError('unwritable report')):
            try:
                with broken:
                    raise AssertionError('An unwritable entry report was ignored')
            except OSError as error:
                assert str(error) == 'unwritable report'
        with native_workspace.open_workspace(source, root / 'broken-enter', environ=environment):
            pass
    result = dict(passed=True, original_source_and_quoted_includes=True, source_directory_isolation=True,
        requested_output_isolation=True, live_diagnostics_in_worker_threads=True,
        explicit_artifact_publication=True, private_intermediates_stay_local=True,
        exact_legacy_object_import=True, ambiguous_legacy_source_paths_rejected=True,
        checked_actual_work_report=True,
        changed_flags_compiler_inputs_and_object_rejected=True,
        pch_import_refused=True, exclusive_workspace=True, disabled_and_auto_modes=True,
        original_failure_preserved=True, failed_entry_releases_lock=True,
        helper_sha256=digest(ROOT / 'generator/native_workspace.py'))
    if args.backend:
        result['backend'] = check_backend(args.work.resolve(), args.qt_root)
    (args.work / 'receipt.json').write_text(json.dumps(result, indent=2) + '\n')
    print('QT612_NATIVE_WORKSPACE_OK local=1 original_source=1 includes=1 isolation=1 diagnostics=1 exact_object_import=1 no_pch_rewrite=1 failures=1')


if __name__ == '__main__':
    main()
