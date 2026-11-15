#!/usr/bin/env python3
"""Check workflow resume, dependency guards and reviewed-name preflight cheaply."""
import argparse
import copy
from contextlib import ExitStack
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('qt_maintenance_workflow', ROOT / 'scripts/maintain-qt612.py')
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)
import generate


def fake_dependencies(environment):
    linker = environment.get('BQT_LINKER', 'auto')
    tools = {name: {'sha256': name + '-same'} for name in
             ('python3', 'extractor', 'git', 'ld', 'llvm-objcopy-19', 'llvm-nm-19')}
    tools['selected_linker'] = {'path': linker}
    libraries = {'extractor': {'/lib/libclang': {'sha256': 'clang-same'}},
                 'selected_linker': {'/lib/' + linker: {'sha256': linker}}}
    return dict(tools=tools, selected_linker={'path': linker}, tool_libraries=libraries,
                native_tool_libraries={path: value for rows in libraries.values() for path, value in rows.items()},
                qt={'moc': 'same', 'headers': 'same'}, pyside={'commit': 'pinned'},
                environment=dict(environment))


class TemporaryWorkspace(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='qt-maintenance-tests-')
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def file(self, name, data='data'):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data)
        return path


class StageTests(TemporaryWorkspace):
    def setUp(self):
        super().setUp()
        self.source = self.file('source', 'one')
        self.output = self.root / 'output'
        self.calls = []
        def run(command, log):
            self.calls.append(command)
            self.output.write_text('built-' + self.source.read_text())
        self.stages = workflow.Stages(self.root / 'stages', self.root, run)

    def run_stage(self, **kwargs):
        return self.stages.run('example', ['test', 'command'],
            lambda: {'source': workflow.sha(self.source)}, lambda: {'passed': True},
            lambda: workflow.artifacts([self.output]), **kwargs)

    def test_reuse_is_by_content_not_mtime(self):
        self.run_stage()
        os.utime(self.source, (1, 1))
        os.utime(self.output, (2, 2))
        self.run_stage()
        self.assertEqual(len(self.calls), 1)
        self.source.write_text('two')
        os.utime(self.source, (1, 1))
        self.run_stage()
        self.assertEqual(len(self.calls), 2)
        before = self.output.stat()
        self.output.write_text('other-two')  # Same length, same mtime, different content.
        os.utime(self.output, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.run_stage()
        self.assertEqual(len(self.calls), 3)

    def test_failed_or_interrupted_run_cannot_reuse_earlier_success(self):
        self.run_stage()
        self.stages.force = True
        self.stages.runner = lambda *_: (_ for _ in ()).throw(KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt):
            self.run_stage()
        self.assertFalse(workflow.read_json(self.root / 'stages/example.json')['complete'])
        self.stages.force = False
        self.assertFalse(self.stages.valid('example', ['test', 'command'], {'source': workflow.sha(self.source)}))

    def test_source_drift_is_not_a_success(self):
        def run(command, log):
            self.output.write_text('exists')
            self.source.write_text('changed during build')
        self.stages.runner = run
        with self.assertRaisesRegex(RuntimeError, 'Inputs changed'):
            self.run_stage()
        self.assertFalse(workflow.read_json(self.root / 'stages/example.json')['complete'])

    def test_dependency_and_command_changes_invalidate(self):
        dependency = self.file('header.h', 'before')
        record = self.stages.run('native', ['compiler'], lambda: {},
            lambda: {'native_dependencies': workflow.file_set([dependency])},
            lambda: workflow.artifacts([self.output]))
        self.assertTrue(self.stages.valid('native', ['compiler'], {}))
        self.assertFalse(self.stages.valid('native', ['other compiler'], {}))
        dependency.write_text('after!')
        self.assertFalse(self.stages.valid('native', ['compiler'], {}))
        self.assertTrue(record['complete'])

    def test_invalid_semantic_receipt_is_rebuilt(self):
        self.run_stage()
        calls = [0]
        def validate():
            calls[0] += 1
            if calls[0] == 1:
                raise RuntimeError('incomplete cached receipt')
            return {'passed': True}
        self.stages.run('example', ['test', 'command'],
            lambda: {'source': workflow.sha(self.source)}, validate,
            lambda: workflow.artifacts([self.output]))
        self.assertEqual(len(self.calls), 2)

    def test_lock_rejects_a_second_writer(self):
        with workflow.exclusive(self.root / 'lock'):
            with self.assertRaisesRegex(RuntimeError, 'Another maintainer'):
                with workflow.exclusive(self.root / 'lock'):
                    self.fail('Second writer acquired the lock')


class DependencyTests(TemporaryWorkspace):
    def test_extraction_ignores_only_native_build_tuning_and_linker(self):
        first = fake_dependencies({'BQT_SHARD_JOBS': '1', 'BQT_LINKER': 'lld', 'LD_LIBRARY_PATH': '/kit'})
        changed = fake_dependencies(dict(first['environment'], **{
            name: 'different' for name in workflow.NATIVE_BUILD_ENV}))
        self.assertNotEqual(first, changed)
        self.assertEqual(workflow.extraction_dependencies(first), workflow.extraction_dependencies(changed))
        for name in ('LD_LIBRARY_PATH', 'BQT_UNKNOWN_EXTRACTION_OPTION'):
            actual_input_changed = copy.deepcopy(changed)
            actual_input_changed['environment'][name] = 'new extraction environment'
            self.assertNotEqual(workflow.extraction_dependencies(first),
                                workflow.extraction_dependencies(actual_input_changed))

    def test_extraction_keeps_extractor_libclang_qt_and_moc_identities(self):
        original = fake_dependencies({})
        for section, key in [('tools', 'extractor'), ('qt', 'headers'), ('qt', 'moc')]:
            changed = copy.deepcopy(original)
            changed[section][key] = 'changed'
            self.assertNotEqual(workflow.extraction_dependencies(original),
                                workflow.extraction_dependencies(changed))
        changed = copy.deepcopy(original)
        changed['tool_libraries']['extractor']['/lib/libclang']['sha256'] = 'changed'
        self.assertNotEqual(workflow.extraction_dependencies(original), workflow.extraction_dependencies(changed))

    def test_recorded_symlink_target_is_part_of_identity(self):
        first, second = self.file('first', 'equal'), self.file('second', 'equal')
        alias = self.root / 'alias'
        alias.symlink_to(first)
        original = workflow.file_set([alias])
        alias.unlink()
        alias.symlink_to(second)
        self.assertNotEqual(original, workflow.file_set([alias]))

    def test_backend_manifests_cover_compile_and_link_inputs(self):
        work = self.root / 'work'
        work.mkdir()
        header, library = self.file('header', 'h'), self.file('library', 'lib')
        compile_cache, link_cache = work / 'compile.json', work / 'link.json'
        workflow.write_json(compile_cache, {'dependencies': {str(header): workflow.sha(header)}})
        workflow.write_json(link_cache, {'dependencies': workflow.file_set([library]), 'future_backend_field': True})
        workflow.write_json(work / 'generation.json', {'native_dependency_manifests': [str(compile_cache), str(link_cache)]})
        result = workflow.native_dependencies(work)
        self.assertEqual(set(result), {str(header), str(library)})
        library.write_text('changed')
        with self.assertRaisesRegex(RuntimeError, 'Changed native dependency'):
            workflow.native_dependencies(work)

    def test_manifest_retargeting_same_bytes_is_rejected(self):
        first, second = self.file('lib-first', 'same'), self.file('lib-second', 'same')
        alias = self.root / 'lib.so'
        alias.symlink_to(first)
        cache = self.root / 'link.json'
        workflow.write_json(cache, {'dependencies': workflow.file_set([alias])})
        workflow.write_json(self.root / 'generation.json', {'native_dependency_manifests': [str(cache)]})
        alias.unlink()
        alias.symlink_to(second)
        with self.assertRaisesRegex(RuntimeError, 'symlink target'):
            workflow.native_dependencies(self.root)

    def test_missing_manifest_does_not_fall_back_to_unrelated_cache(self):
        dependency = self.file('header', 'ok')
        workflow.write_json(self.root / 'unrelated-cache.json', {'dependencies': {str(dependency): workflow.sha(dependency)}})
        workflow.write_json(self.root / 'generation.json', {'native_dependency_manifests': [str(self.root / 'missing.json')]})
        with self.assertRaises(FileNotFoundError):
            workflow.native_dependencies(self.root)

    def test_library_search_directory_changes_are_not_ignored(self):
        directory = self.root / 'libraries'
        directory.mkdir()
        header = self.file('header', 'header')
        cache = self.root / 'link.json'
        workflow.write_json(cache, dict(dependencies=workflow.file_set([header]),
            key={'search_directories': {str(directory): []}}))
        workflow.write_json(self.root / 'generation.json', {'native_dependency_manifests': [str(cache)]})
        workflow.native_dependencies(self.root)
        (directory / 'new-library.so').write_text('new candidate')
        with self.assertRaisesRegex(RuntimeError, 'search directory changed'):
            workflow.native_dependencies(self.root)

    def test_canonical_lock_history_does_not_invalidate_artifacts(self):
        report = self.root / 'generation.json'
        value = dict(source_sha256={'a': 'hash'}, generated_sha256={'qt.c': 'hash'},
                     qt='6.12.0', extractor='extractor', profile={'name': 'qt612'},
                     input_name_lock_sha256='old', native_dependency_manifests=['/cache/compile.json'])
        workflow.write_json(report, value)
        before = workflow.artifact_hash(report, 'generation')
        value['input_name_lock_sha256'] = 'completed'
        value['cache_diagnostics'] = {'hits': 99}
        workflow.write_json(report, value)
        self.assertEqual(before, workflow.artifact_hash(report, 'generation'))
        value['native_dependency_manifests'] = ['/other/compile.json']
        workflow.write_json(report, value)
        self.assertNotEqual(before, workflow.artifact_hash(report, 'generation'))


class NameReviewTests(TemporaryWorkspace):
    def fake_generator(self, pending):
        class Lock:
            tombstoned = []
            reshaped = []
            created = []
            acknowledged = False
            def unacknowledged(self):
                return pending
            def acknowledge(self):
                self.acknowledged = True
        return argparse.Namespace(name_lock=Lock(), methods=[1, 2])

    def test_unreviewed_pair_rejected_before_acknowledgement(self):
        reviewed = self.file('reviewed.json', '{"reviewed": [["Owner", "Owner.reviewed"]]}')
        generator = self.fake_generator([('Owner', 'Owner.unexpected')])
        with self.assertRaisesRegex(ValueError, 'Unexpected removed public names'):
            generate.preflight_names(generator, self.root, {'source': 'hash'}, reviewed, True)
        self.assertFalse(generator.name_lock.acknowledged)
        result = workflow.read_json(self.root / 'name-lock-preflight.json')
        self.assertEqual(result['unexpected'], [['Owner', 'Owner.unexpected']])

    def test_reviewed_pair_is_accepted_and_bad_shapes_rejected(self):
        reviewed = self.file('reviewed.json', '{"reviewed": [["Owner", "Owner.reviewed"]]}')
        generator = self.fake_generator([('Owner', 'Owner.reviewed')])
        generate.preflight_names(generator, self.root, {}, reviewed, True)
        self.assertTrue(generator.name_lock.acknowledged)
        for value in ({}, {'reviewed': [['Owner', 'name', 'reason']]}, {'reviewed': 'all'}):
            workflow.write_json(reviewed, value)
            with self.assertRaises(ValueError):
                generate.reviewed_name_removals(reviewed)

    def test_default_empty_review_does_not_accept_removals(self):
        reviewed = self.file('reviewed.json', '{"reviewed": []}')
        with self.assertRaises(ValueError):
            generate.preflight_names(self.fake_generator([('O', 'O.removed')]), self.root, {}, reviewed, True)


class ExtractionTests(TemporaryWorkspace):
    def test_runtime_emitter_edits_do_not_change_extraction_identity(self):
        generator = self.root / 'generator'
        profile = generator / 'qt612'
        self.file('generator/generate.py', 'extract')
        self.file('generator/upstream.py', 'upstream')
        self.file('generator/extract.cpp', 'extractor')
        self.file('generator/qt612/profile.json', '{}')
        runtime = self.file('generator/templates/runtime.cpp', 'runtime')
        emitter = self.file('generator/custom_signals.py', 'emitter')
        with patch.object(generate, 'ROOT', self.root), patch.object(generate, 'HERE', generator):
            before = generate.extraction_inputs(profile)
            runtime.write_text('changed runtime')
            emitter.write_text('changed emitter')
            self.assertEqual(before, generate.extraction_inputs(profile))
            self.file('generator/new-extractor.cpp', 'new extraction dependency')
            self.assertNotEqual(before, generate.extraction_inputs(profile))

    def test_extract_only_never_collects_or_compiles_bindings(self):
        profile, work = self.root / 'profile', self.root / 'work'
        profile.mkdir()
        workflow.write_json(profile / 'profile.json', dict(minimum_qt='6.12.0', qt_modules=['QtCore', 'QtGui', 'QtWidgets']))
        work.mkdir()
        headers, system = self.file('work/headers.h', '// headers'), self.file('work/typesystem.xml', '<typesystem/>')
        workflow.write_json(work / 'upstream.json', {'commit': 'pinned'})
        import qt_targets
        api = dict(qt_headers='6.12.0', qt_runtime='6.12.0',
                   shiboken_commit=qt_targets.target('6.12.0')['shiboken_commit'])
        def extract(command, **kwargs):
            workflow.write_json(work / 'api.json', api)
            return argparse.Namespace(stdout='', stderr='')
        with patch.object(sys, 'argv', ['generate.py', '--extract-only', '--profile', str(profile), '--work', str(work)]), \
             patch.object(generate, 'prepare', return_value=(headers, system, ['QtCore', 'QtGui', 'QtWidgets'], {}, {})), \
             patch.object(generate, 'command', side_effect=extract), \
             patch.object(generate, 'generation_inputs', return_value={'all': 'stable'}), \
             patch.object(generate, 'extraction_inputs', return_value={'extraction': 'stable'}), \
             patch.object(generate.public_records, 'restore'), patch.object(generate.qobject_interfaces, 'restore'), \
             patch.object(generate.qio_pipe, 'restore'), patch.object(generate.pyside_boundary, 'apply', side_effect=lambda value: value), \
             patch.object(generate.native_objects, 'refine_traits', side_effect=AssertionError('Native trait compilation started')), \
             patch.object(generate, 'Generator', side_effect=AssertionError('Bindings were collected')):
            import gl_inventory
            with patch.object(gl_inventory, 'restore'):
                generate.main()
        receipt = workflow.read_json(work / 'extraction.json')
        self.assertTrue(receipt['verification_complete'])
        self.assertEqual(receipt['snapshot_sha256']['api.json'], workflow.sha(work / 'api.json'))

    def check_main_guard(self, change_review):
        from unittest.mock import Mock
        profile, work = self.root / 'profile', self.root / 'work'
        profile.mkdir(); work.mkdir()
        workflow.write_json(profile / 'profile.json', dict(minimum_qt='6.12.0', qt_modules=['QtCore', 'QtGui', 'QtWidgets']))
        reviewed = self.file('reviewed.json', '{"reviewed": []}')
        headers, system = self.file('work/headers.h', '// headers'), self.file('work/typesystem.xml', '<typesystem/>')
        import qt_targets
        api = dict(qt_headers='6.12.0', qt_runtime='6.12.0',
                   shiboken_commit=qt_targets.target('6.12.0')['shiboken_commit'])
        lock = argparse.Namespace(unacknowledged=lambda: [('Owner', 'Owner.removed')],
                                  tombstoned=[], reshaped=[], created=[], acknowledge=Mock())
        def collect():
            if change_review:
                workflow.write_json(reviewed, {'reviewed': [['Owner', 'Owner.removed']]})
        model = argparse.Namespace(name_lock=lock, methods=[], collect=collect,
                                   emit=Mock(side_effect=AssertionError('Emission started before name guard')))
        def extract(*args, **kwargs):
            workflow.write_json(work / 'api.json', api)
            return argparse.Namespace(stdout='', stderr='')
        import gl_inventory
        with ExitStack() as patches:
            for target, kwargs in (
                ('sys.argv', {'new': ['generate.py', '--profile', str(profile), '--work', str(work),
                                      '--reviewed-name-removals', str(reviewed), '--acknowledge-removed-names']}),
                ('generate.prepare', {'return_value': (headers, system, ['QtCore', 'QtGui', 'QtWidgets'], {}, {})}),
                ('generate.command', {'side_effect': extract}),
                ('generate.generation_inputs', {'return_value': {'all': 'stable'}}),
                ('generate.extraction_inputs', {'return_value': {'extraction': 'stable'}}),
                ('generate.public_records.restore', {}), ('generate.qobject_interfaces.restore', {}),
                ('generate.qio_pipe.restore', {}), ('gl_inventory.restore', {}),
                ('generate.pyside_boundary.apply', {'side_effect': lambda value: value}),
                ('generate.native_objects.refine_traits', {}), ('generate.evaluate_tables', {'return_value': {}}),
                ('generate.Generator', {'return_value': model}), ('generate.callbacks.prepare', {}),
                ('generate.overload_names.finalize', {}),
            ):
                patches.enter_context(patch(target, **kwargs))
            compiled = patches.enter_context(patch.object(generate.abi_cohorts, 'compile_payloads',
                                    side_effect=AssertionError('Native compilation started before name guard')))
            error = RuntimeError if change_review else ValueError
            message = 'reviewed-removal inventory changed' if change_review else 'Unexpected removed public names'
            with self.assertRaisesRegex(error, message):
                generate.main()
            lock.acknowledge.assert_not_called()
            model.emit.assert_not_called()
            compiled.assert_not_called()

    def test_actual_main_rejects_unknown_removal_before_emission_or_compilation(self):
        self.check_main_guard(False)

    def test_actual_main_rejects_review_drift_before_acknowledgement(self):
        self.check_main_guard(True)


class WorkflowContractTests(TemporaryWorkspace):
    def args(self, command='final', extra=()):
        return workflow.arguments(['--state-dir', str(self.root / 'state'), command, *extra])

    def test_focus_requires_named_fixtures(self):
        with patch('sys.stderr'):
            with self.assertRaises(SystemExit):
                self.args('focus')

    def test_canonical_receipt_must_be_complete_and_deterministic(self):
        receipt = self.root / 'receipt.json'
        for value in ({'verification_complete': False}, {'verification_complete': True},
                      {'verification_complete': True, 'deterministic_regeneration': False, 'public_hub_publication': False}):
            workflow.write_json(receipt, value)
            with self.assertRaises(RuntimeError):
                workflow.validate_verification(receipt, canonical=True)

    def test_changed_consumer_executable_is_not_accepted(self):
        executable = self.file('consumer', 'built executable')
        receipt = self.root / 'receipt.json'
        workflow.write_json(receipt, dict(validation_executable=str(executable), executable_sha256=workflow.sha(executable)))
        workflow.verification_outputs(receipt)
        executable.write_text('different executable')
        with self.assertRaisesRegex(RuntimeError, 'executable changed'):
            workflow.verification_outputs(receipt)

    def test_stage_refreshes_dependencies_after_execution(self):
        current = {'identity': 'before'}
        args = self.args()
        stages = workflow.Stages(self.root / 'stages', self.root,
            lambda *_: current.update(identity='changed while running'))
        state = workflow.Workflow(self.root, args, stages, lambda: dict(current))
        output = self.file('output', 'exists')
        with self.assertRaisesRegex(RuntimeError, 'Inputs changed'):
            state.stage('dependencies', ['test'], lambda: {'dependencies': state.deps()},
                        lambda: {}, lambda: workflow.artifacts([output]))

    def test_safe_native_defaults_preserve_explicit_overrides(self):
        with patch.dict(os.environ, {}, clear=True):
            environment = workflow.execution_environment()
            self.assertEqual(environment['BQT_SHARD_OPERATIONS'], '512')
            self.assertEqual(environment['BQT_SHARD_KEEP_GOING'], '1')
        with patch.dict(os.environ, {'BQT_SHARD_OPERATIONS': '17', 'BQT_SHARD_KEEP_GOING': '0'}, clear=True):
            environment = workflow.execution_environment()
            self.assertEqual(environment['BQT_SHARD_OPERATIONS'], '17')
            self.assertEqual(environment['BQT_SHARD_KEEP_GOING'], '0')

    def test_real_subprocess_gets_requested_jobs_and_explicit_override(self):
        stages = workflow.Stages(self.root / 'stages', self.root)
        command = [sys.executable, '-c', 'import os; print(os.environ["BQT_SHARD_JOBS"])']
        for jobs in (1, 2, 4):
            with patch.dict(os.environ, {}, clear=True):
                stages.jobs = jobs
                log = self.root / ('jobs-' + str(jobs) + '.log')
                stages.execute(command, log)
                self.assertEqual(log.read_text().strip(), str(jobs))
        with patch.dict(os.environ, {'BQT_SHARD_JOBS': '5'}, clear=True):
            stages.jobs = 2
            log = self.root / 'explicit-jobs.log'
            stages.execute(command, log)
            self.assertEqual(log.read_text().strip(), '5')

    def test_temporary_controls_need_no_persistent_executable(self):
        executable = self.file('app', 'consumer')
        receipt = self.root / 'receipt.json'
        workflow.write_json(receipt, dict(validation_executable=str(executable),
            extension={'validation_executable': '/tmp/removed-qt-extension/app'}))
        output = workflow.verification_outputs(receipt)
        self.assertIn(str(executable), output)
        executable.unlink()
        with self.assertRaisesRegex(RuntimeError, 'executable is missing'):
            workflow.verification_outputs(receipt)


class FinalWorkflowTests(TemporaryWorkspace):
    def setUp(self):
        super().setUp()
        self.profile = self.root / 'generator/qt612'
        self.lock = self.file('generator/qt612/names.lock.json', 'initial lock')
        self.runtime = self.file('generator/runtime.py', 'runtime one')
        self.file('generator/qt612/profile.json', '{"name":"qt612"}')
        self.file('generator/qt612-legacy-charts/profile.json', '{"name":"legacy"}')
        self.file('generator/qt612-legacy-charts/names.lock.json', 'legacy lock')
        self.checker = self.file('scripts/check-qt612.py', 'canonical checker')
        self.file('scripts/check-qt-callbacks.py', 'focused checker')
        self.file('scripts/check.sh', 'setup examples')
        self.file('scripts/fixtures/probe.bend', 'fixture')
        self.file('examples/main.bend', 'example')
        self.header = self.file('system-header.h', 'header one')
        self.commands = []
        self.work = self.root / 'build/qt612'
        self.args = workflow.arguments(['--state-dir', str(self.root / 'state'), 'final'])
        self.stages = workflow.Stages(self.root / 'state/stages', self.root, self.run_command)
        self.state = workflow.Workflow(self.root, self.args, self.stages, lambda: {'native_toolchain': 'stable'})
        self.patch_sources = patch.object(workflow, 'generation_inputs', side_effect=self.sources)
        self.patch_extraction = patch.object(workflow, 'extraction_inputs', side_effect=self.extraction_sources)
        self.patch_sources.start(); self.addCleanup(self.patch_sources.stop)
        self.patch_extraction.start(); self.addCleanup(self.patch_extraction.stop)

    def sources(self, profile):
        return {str(path.relative_to(self.root)): workflow.sha(path)
                for path in [self.runtime, profile / 'profile.json', profile / 'names.lock.json']}

    def extraction_sources(self, profile):
        return {str((profile / 'profile.json').relative_to(self.root)): workflow.sha(profile / 'profile.json')}

    def native_metadata(self, work):
        work.mkdir(parents=True, exist_ok=True)
        cache = work / 'compile.json'
        workflow.write_json(cache, {'dependencies': {str(self.header): workflow.sha(self.header)}})
        return [str(cache)]

    def run_command(self, command, log):
        self.commands.append(command)
        if command[1] == 'generator/generate.py':
            if '--extract-only' in command:
                work = Path(command[command.index('--work') + 1])
                profile = Path(command[command.index('--profile') + 1])
                work.mkdir(parents=True, exist_ok=True)
                for name in workflow.SNAPSHOT_FILES:
                    (work / name).write_text('{}')
                workflow.write_json(work / 'extraction.json', dict(verification_complete=True,
                    qt='6.12.0', source_sha256=self.extraction_sources(profile),
                    snapshot_sha256={name: workflow.sha(work / name) for name in workflow.SNAPSHOT_FILES}))
                return
            before = self.sources(self.profile)
            self.lock.write_text('completed lock')
            self.work.mkdir(parents=True, exist_ok=True)
            (self.work / 'wrappers.cpp').write_text('native ' + self.runtime.read_text())
            for name in workflow.SNAPSHOT_FILES:
                (self.work / name).write_text('{}')
            package = self.root / 'packages/qt612'
            package.mkdir(parents=True, exist_ok=True)
            for name in workflow.PACKAGE_FILES:
                (package / name).write_text(name + self.runtime.read_text())
            workflow.write_json(self.work / 'generation.json', dict(
                generated_sha256={name: workflow.sha(package / name) for name in workflow.PACKAGE_FILES},
                source_sha256=self.sources(self.profile), qt='6.12.0', extractor='pinned', profile={'name': 'qt612'},
                input_name_lock_sha256=before['generator/qt612/names.lock.json'],
                native_dependency_manifests=self.native_metadata(self.work)))
            workflow.write_json(self.work / 'name-lock-preflight.json', dict(methods=2,
                source_sha256=before, unacknowledged=[], created=['new name'],
                native_source_sha256=workflow.sha(self.work / 'wrappers.cpp')))
        elif command[1] == 'scripts/check-qt612.py':
            self.assertEqual(command[:5], ['python3', 'scripts/check-qt612.py', '--bundle',
                                           '--generator-checks', '--reject-system-qt'])
            value = workflow.read_json(self.work / 'generation.json')
            value['input_name_lock_sha256'] = workflow.sha(self.lock)
            value['future_cache_diagnostics'] = {'cache_hits': 12}
            workflow.write_json(self.work / 'generation.json', value)
            preflight = workflow.read_json(self.work / 'name-lock-preflight.json')
            preflight.update(created=[], source_sha256=self.sources(self.profile))
            workflow.write_json(self.work / 'name-lock-preflight.json', preflight)
            executable = self.file('build/qt612/check/app', 'consumer')
            workflow.write_json(self.work / 'check/receipt.json', dict(verification_complete=True,
                deterministic_regeneration=True, public_hub_publication=False,
                validation_executable=str(executable), executable_sha256=workflow.sha(executable)))
        elif command[1] == 'scripts/check-qt-callbacks.py':
            work = Path(command[command.index('--work') + 1])
            manifests = self.native_metadata(work)
            workflow.write_json(work / 'backend.json', {'native_dependency_manifests': manifests})
            names = [command[index + 1] for index, value in enumerate(command) if value == '--only']
            workflow.write_json(work / 'receipt.json', dict(verification_complete=True, expected_programs=names))
        else:
            self.assertEqual(command, ['bash', 'scripts/check.sh'])
            self.file('build/hello', 'hello')
            self.file('build/parallel', 'parallel')

    def test_retry_reuses_generation_and_canonical_after_lock_refresh(self):
        self.state.final()
        self.assertEqual(len(self.commands), 2)
        self.assertNotIn('--emit-only', self.commands[0])
        reviewed = Path(self.commands[0][self.commands[0].index('--reviewed-name-removals') + 1])
        self.assertEqual(workflow.read_json(reviewed), {'reviewed': []})
        self.state.final()
        self.assertEqual(len(self.commands), 2)
        self.assertTrue(workflow.read_json(self.root / 'state/receipt.json')['verification_complete'])

    def test_changed_checks_rerun_canonical_without_generation(self):
        self.state.final()
        self.checker.write_text('changed canonical checker')
        self.state.final()
        self.assertEqual(len(self.commands), 3)
        self.assertEqual(self.commands[-1][1], 'scripts/check-qt612.py')

    def test_changed_native_header_invalidates_generation_and_canonical(self):
        self.state.final()
        self.header.write_text('new native header')
        self.state.final()
        self.assertEqual([command[1] for command in self.commands],
                         ['generator/generate.py', 'scripts/check-qt612.py'] * 2)

    def test_failed_canonical_retry_keeps_valid_package(self):
        original = self.stages.runner
        failed = [False]
        def once(command, log):
            if command[1] == 'scripts/check-qt612.py' and not failed[0]:
                failed[0] = True
                raise RuntimeError('Injected canonical failure')
            original(command, log)
        self.stages.runner = once
        with self.assertRaisesRegex(RuntimeError, 'Injected canonical'):
            self.state.final()
        self.assertFalse(workflow.read_json(self.root / 'state/receipt.json')['verification_complete'])
        self.state.final()
        self.assertEqual([command[1] for command in self.commands],
                         ['generator/generate.py', 'scripts/check-qt612.py'])

    def test_charts_are_explicit_and_require_both_complete_modules(self):
        self.args.charts = True
        self.state.final()
        charts = self.commands[-1]
        self.assertEqual(charts[1], 'scripts/check-qt-callbacks.py')
        modules = [charts[index + 1] for index, value in enumerate(charts) if value == '--complete-module']
        self.assertEqual(modules, ['QtCharts', 'QtDataVisualization'])
        self.assertIn('legacy-charts', charts)
        before = len(self.commands)
        self.state.final()
        self.assertEqual(len(self.commands), before)

    def test_focus_uses_prepared_model_without_production_generation(self):
        self.state.prepare()
        self.args.only, self.args.module, self.args.rhi, self.args.jobs = ['probe'], [], False, 1
        before = len(self.commands)
        with patch.object(workflow.subprocess, 'run', side_effect=lambda command, **kw: self.run_command(command, None)):
            self.state.focus()
        self.assertEqual(len(self.commands), before + 1)
        self.assertEqual(self.commands[-1][1], 'scripts/check-qt-callbacks.py')
        self.assertNotIn('--all-features', self.commands[-1])
        receipt = workflow.read_json(self.root / 'state/focus-result.json')
        self.assertTrue(receipt['focused_verification_complete'])
        self.assertFalse(receipt['verification_complete'])

    def test_prepare_reuses_extraction_for_focus_jobs_one_and_two(self):
        self.state.dependencies = lambda: fake_dependencies(
            workflow.execution_environment(getattr(self.args, 'jobs', None)))
        del self.args.jobs  # The prepare subcommand does not set native jobs.
        self.args.only, self.args.module, self.args.rhi = ['probe'], [], False
        observed = []
        def execute(command, **kwargs):
            observed.append(kwargs['env']['BQT_SHARD_JOBS'])
            self.run_command(command, None)
        with patch.dict(os.environ, {}, clear=True):
            self.state.prepare()
            prepared_key = self.state.extraction_key(self.profile)
            for jobs in (1, 2):
                self.args.jobs = jobs
                with patch.dict(os.environ, {name: 'tuned-' + str(jobs) for name in workflow.NATIVE_BUILD_ENV
                                             if name != 'BQT_SHARD_JOBS'}, clear=False):
                    with patch.object(workflow.subprocess, 'run', side_effect=execute):
                        self.state.focus()
                    self.assertEqual(prepared_key, self.state.extraction_key(self.profile))
        self.assertEqual(observed, ['1', '2'])
        self.assertEqual(sum(command[1] == 'generator/generate.py' for command in self.commands), 1)

    def test_final_stage_runner_receives_cli_jobs(self):
        args = workflow.arguments(['--state-dir', str(self.root / 'another-state'), 'final', '--jobs', '2'])
        state = workflow.Workflow(self.root, args, dependency_reader=lambda: {})
        seen = []
        def execute(command, **kwargs):
            seen.append(kwargs['env']['BQT_SHARD_JOBS'])
            return argparse.Namespace(returncode=0)
        with patch.dict(os.environ, {}, clear=True), patch.object(workflow.subprocess, 'run', side_effect=execute):
            state.stages.execute(['fake generation'], self.root / 'final-native.log')
        with patch.dict(os.environ, {'BQT_SHARD_JOBS': '3'}, clear=True), patch.object(workflow.subprocess, 'run', side_effect=execute):
            state.stages.execute(['fake generation'], self.root / 'final-explicit.log')
        self.assertEqual(seen, ['2', '3'])

    def test_final_identity_still_tracks_native_job_tuning(self):
        reviewed = self.file('reviewed.json', '{"reviewed": []}')
        self.state.dependencies = lambda: fake_dependencies(workflow.execution_environment(self.args.jobs))
        with patch.dict(os.environ, {'BQT_SHARD_JOBS': '1'}, clear=True):
            self.state._dependencies = None
            first = self.state.final_inputs(reviewed)
        with patch.dict(os.environ, {'BQT_SHARD_JOBS': '2'}, clear=True):
            self.state._dependencies = None
            second = self.state.final_inputs(reviewed)
        self.assertNotEqual(first, second)
        self.assertEqual(workflow.extraction_dependencies(first['dependencies']),
                         workflow.extraction_dependencies(second['dependencies']))

    def test_charts_cannot_hide_a_later_production_lock_change(self):
        self.args.charts = True
        run = self.stages.runner
        def mutate(command, log):
            run(command, log)
            if command[1] == 'scripts/check-qt-callbacks.py':
                self.lock.write_text('changed after canonical')
        self.stages.runner = mutate
        with self.assertRaisesRegex(RuntimeError, 'State changed after generation'):
            self.state.final()
        self.assertFalse(workflow.read_json(self.root / 'state/receipt.json')['verification_complete'])

    def test_force_canonical_does_not_rerun_generation(self):
        self.state.final()
        self.stages.force_stages.add('canonical')
        self.state.final()
        self.assertEqual([command[1] for command in self.commands],
                         ['generator/generate.py', 'scripts/check-qt612.py', 'scripts/check-qt612.py'])

    def test_documented_prepare_focus_final_cli_dispatch(self):
        base = ['--state-dir', str(self.root / 'cli-state')]
        owner = self
        def execute(stage, command, log):
            owner.run_command(command, log)
        with patch.object(workflow, 'ROOT', self.root), \
             patch.object(workflow.Stages, 'execute', new=execute), \
             patch.object(workflow.Workflow, 'dependency_identity', return_value={'toolchain': 'stable'}), \
             patch.object(workflow.subprocess, 'run', side_effect=lambda command, **kw: owner.run_command(command, None)):
            workflow.main([*base, 'prepare'])
            workflow.main([*base, 'focus', '--only', 'probe'])
            workflow.main([*base, 'final', '--charts', '--setup-examples'])
        self.assertEqual([command[1] for command in self.commands], [
            'generator/generate.py', 'scripts/check-qt-callbacks.py',
            'generator/generate.py', 'scripts/check-qt612.py',
            'generator/generate.py', 'scripts/check-qt-callbacks.py', 'scripts/check.sh'])
        self.assertEqual(sum('--extract-only' in command for command in self.commands), 2)
        self.assertTrue(all('--emit-only' not in command for command in self.commands))
        receipt = workflow.read_json(self.root / 'cli-state/receipt.json')
        self.assertTrue(receipt['verification_complete'])
        self.assertIsNotNone(receipt['charts_stage'])
        self.assertTrue(receipt['setup_examples'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
