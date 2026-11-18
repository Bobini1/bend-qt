#!/usr/bin/env python3
"""Check Action laws, their packaged source, and optionally negative controls.

This is maintainer verification. Consumers still use standard Bend commands.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BEND = Path.home() / '.bend/bin/bend'
OUT = ROOT / 'build/qt612/proofs'
TEMPLATE = ROOT / 'generator/templates/action.bend'
CODEC = ROOT / 'generator/templates/codec.bend'
LIFETIME = ROOT / 'generator/templates/lifetime.bend'
sys.path.insert(0, str(ROOT / 'generator'))
from lifetime import evaluate_tables, cpp_tables


def run(args, cwd=ROOT):
    return subprocess.run([str(x) for x in args], cwd=cwd, text=True,
                          capture_output=True, timeout=120)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_packaged_source(source):
    prefix = 'import Base\n\n'
    if not source.startswith(prefix):
        raise RuntimeError('The proven Action source must be a standalone Base module')
    body = source.removeprefix(prefix)
    package = (ROOT / 'packages/qt612/qt.bend').read_text()
    version = json.loads((ROOT / 'packages/qt612/coverage.json').read_text())['minimum_qt']
    expected = f'# Generated from Qt {version} headers by Shiboken ApiExtractor. Do not edit.\nimport Base\n\n' + body + '\n'
    if not package.startswith(expected):
        raise RuntimeError('Packaged Action differs from the source imported by LAWS.bend; regenerate it')
    defs = r'^def (Action(?:\.[A-Za-z0-9_]+)*)\('
    if re.findall(defs, package, re.M) != re.findall(defs, source, re.M):
        raise RuntimeError('Packaged Action definitions are missing, duplicated or shadowed')
    codec = CODEC.read_text().removeprefix(prefix)
    if package.count(codec) != 1:
        raise RuntimeError('Packaged Codec differs from the proof source; regenerate it')
    defs = r'^def (Codec\.[A-Za-z0-9_]+)\('
    if re.findall(defs, package, re.M) != re.findall(defs, codec, re.M):
        raise RuntimeError('Packaged Codec definitions are missing, duplicated or shadowed')
    lifetime = LIFETIME.read_text().removeprefix(prefix)
    if package.count(lifetime) != 1:
        raise RuntimeError('Packaged Lifetime differs from the proof source; regenerate it')
    defs = r'^def (Lifetime\.[A-Za-z0-9_]+)\('
    if re.findall(defs, package, re.M) != re.findall(defs, lifetime, re.M):
        raise RuntimeError('Packaged Lifetime definitions are missing, duplicated or shadowed')
    return hashlib.sha256(body.encode()).hexdigest()


def mutations(source):
    old = 'value => next(value, scope)'
    assert source.count(old) == 1
    yield 'bind_loses_scope', source.replace(old, 'value => next(value, 0)')
    start = source.index('def Action.finish(')
    end = source.index('\ndef Action.finally(', start)
    reversed_finish = '''  match cleanup:
    case Fail{error}: Fail{error}
    case Done{unit}: result
'''
    signature = source[start:source.index('\n', start) + 1]
    yield 'cleanup_error_overrides_body', source[:start] + signature + reversed_finish + source[end:]
    old = '    released: Result<&1, &1, U32 & String, Unit> <- cleanup(scope)\n    return Action.finish(A, result, released)'
    assert source.count(old) == 1
    yield 'cleanup_is_skipped', source.replace(old, '    return result')
    old = '    +resource => Action.finally(A, body(resource), release(resource)))'
    assert source.count(old) == 1
    yield 'release_runs_before_body', source.replace(old, '''    +resource => +scope => IO.bind(Result<&1, &1, U32 & String, Unit>, Result<&1, &1, U32 & String, A>,
      release(resource, scope), ignored => body(resource, scope)))''')
    old = '    case Fail{error}:\n      Fail{error}'
    start = source.index('def Action.cleanup_result(')
    tail = source[start:]
    assert tail.count(old) == 1
    yield 'cleanup_swallows_every_error', source[:start] + tail.replace(old, '    case Fail{error}:\n      Done{Unit{}}')
    old = '    return Action.cleanup_result(result)'
    assert source.count(old) == 1
    yield 'cleanup_bypasses_normalization', source.replace(old, '    return result')


def check_mutations(source):
    results = []
    with tempfile.TemporaryDirectory(prefix='bend-qt-proof-negative-') as directory:
        root = Path(directory)
        (root / 'generator/templates').mkdir(parents=True)
        for name in ('LAWS.bend', 'PROOF.bend'):
            (root / name).write_bytes((ROOT / name).read_bytes())
        target = root / 'generator/templates/action.bend'
        (root / 'generator/templates/codec.bend').write_bytes(CODEC.read_bytes())
        (root / 'generator/templates/lifetime.bend').write_bytes(LIFETIME.read_bytes())
        for name, mutant in mutations(source):
            target.write_text(mutant)
            # Reject only semantically wrong, otherwise valid implementations.
            typed = run([BEND, target, '--check-only'], root)
            if typed.returncode or 'ALL PROOFS CHECK' not in typed.stdout:
                raise RuntimeError(f'{name} is not a valid negative control:\n{typed.stdout}{typed.stderr}')
            checked = run([BEND, root / 'PROOF.bend', '--verdict'], root)
            log = checked.stdout + checked.stderr
            (OUT / f'negative-{name}.log').write_text(log)
            if checked.returncode == 0 or 'SOME PROOFS FAIL' not in log or 'Location: Laws.qt_' not in log:
                raise RuntimeError(f'The Qt laws did not reject {name}:\n{log}')
            results.append({'mutation': name, 'type_checks': True, 'laws_reject': True})
        target.write_text(source)
        codec_target = root / 'generator/templates/codec.bend'
        codec = CODEC.read_text()
        codec_mutations = [
            ('reply_present_invalid', 'case Some{value}: True{}', 'case Some{value}: False{}'),
            ('reply_absent_valid', 'case None{}: False{}', 'case None{}: True{}'),
            ('wide_high_word_lost', 'def Codec.wide(lo: U32, hi: U32) -> Wire:\n  WireScalar{lo, hi}', 'def Codec.wide(lo: U32, hi: U32) -> Wire:\n  WireScalar{lo, 0}'),
            ('pair_order_reversed', 'Codec.sequence(first <> second <> Nil{})', 'Codec.sequence(second <> first <> Nil{})'),
            ('list_encode_drops_head', 'encode(head) <> Codec.encode_items(~A, ~encode, tail)', 'Codec.encode_items(~A, ~encode, tail)'),
            ('list_decode_drops_head', 'Codec.cons(A, decode(head), Codec.decode_items(~A, ~decode, tail))', 'Codec.decode_items(~A, ~decode, tail)'),
            ('optional_drops_present_value', 'case Some{item}: Codec.sequence(encode(item) <> Nil{})', 'case Some{item}: Codec.sequence(Nil{})'),
            ('optional_absence_becomes_failure', 'case WireSequence{Nil{}}: Some{None{}}', 'case WireSequence{Nil{}}: None{}'),
            ('optional_accepts_extra_elements', 'case WireSequence{item <> Nil{}}:', 'case WireSequence{item <> tail}:'),
            ('array_accepts_extra_elements', 'case _ 0: False{}', 'case _ 0: True{}'),
            ('array_accepts_short_input', 'case Nil{} _: False{}', 'case Nil{} _: True{}'),
            ('array_decrements_twice', 'Codec.array_items_count(tail, U32.sub(count, 1))', 'Codec.array_items_count(tail, U32.sub(count, 2))'),
        ]
        for name, old, new in codec_mutations:
            assert codec.count(old) == 1
            codec_target.write_text(codec.replace(old, new))
            typed = run([BEND, codec_target, '--check-only'], root)
            if typed.returncode:
                raise RuntimeError(f'{name} is not a valid negative control: {typed.stdout}{typed.stderr}')
            checked = run([BEND, root / 'PROOF.bend', '--verdict'], root)
            log = checked.stdout + checked.stderr
            (OUT / f'negative-{name}.log').write_text(log)
            if checked.returncode == 0 or 'SOME PROOFS FAIL' not in log or 'Location: Laws.qt_' not in log:
                raise RuntimeError(f'The Qt laws did not reject {name}: {log}')
            results.append({'mutation': name, 'type_checks': True, 'laws_reject': True})
        codec_target.write_text(codec)
        lifetime_target = root / 'generator/templates/lifetime.bend'
        lifetime = LIFETIME.read_text()
        lifetime_mutations = [
            ('scope_deletes_transferred', 'case False{}: 0', 'case False{}: 1'),
            ('scope_leaks_owned', 'case True{}: 1', 'case True{}: 0'),
            ('parent_keeps_bend_ownership', 'case _ _ True{}: False{}', 'case _ _ True{}: True{}'),
            ('detachment_loses_ownership', 'case _ True{} False{}: True{}', 'case _ True{} False{}: False{}'),
            ('retained_scope_deletes', 'case True{} True{}: 2', 'case True{} True{}: 1'),
            ('unretained_scope_defers', 'case True{} False{}: 1', 'case True{} False{}: 2'),
            ('transferred_scope_defers', 'case False{} _: 0', 'case False{} _: 2'),
            ('collection_ignores_retention', 'case True{} True{} False{}: True{}', 'case True{} True{} _: True{}'),
            ('collection_ignores_pending', 'case True{} True{} False{}: True{}', 'case _ True{} False{}: True{}'),
            ('collection_ignores_ownership', 'case True{} True{} False{}: True{}', 'case True{} _ False{}: True{}'),
            ('move_borrowed_allowed', 'case True{} False{} False{} False{}: True{}', 'case _ False{} False{} False{}: True{}'),
            ('move_retained_allowed', 'case True{} False{} False{} False{}: True{}', 'case True{} _ False{} False{}: True{}'),
            ('move_active_allowed', 'case True{} False{} False{} False{}: True{}', 'case True{} False{} _ False{}: True{}'),
            ('move_readonly_allowed', 'case True{} False{} False{} False{}: True{}', 'case True{} False{} False{} _: True{}'),
            ('move_exclusive_rejected', 'case True{} False{} False{} False{}: True{}', 'case True{} False{} False{} False{}: False{}'),
            ('incubation_stale_waits', 'case False{} _ _ _: 2', 'case False{} _ _ _: 0'),
            ('incubation_cancel_ignored', 'case True{} False{} _ _: 1', 'case True{} False{} _ _: 0'),
            ('incubation_empty_waits', 'case True{} True{} False{} _: 1', 'case True{} True{} False{} _: 0'),
            ('incubation_deadline_ignored', 'case True{} True{} True{} True{}: 1', 'case True{} True{} True{} True{}: 0'),
            ('incubation_work_skipped', 'case True{} True{} True{} False{}: 0', 'case True{} True{} True{} False{}: 1'),
        ]
        legacy_end = lifetime.index('def Lifetime.aggregate_commit(')
        legacy, remaining = lifetime[:legacy_end], lifetime[legacy_end:]
        for name, old, new in lifetime_mutations:
            assert legacy.count(old) == 1
            lifetime_target.write_text(legacy.replace(old, new) + remaining)
            typed = run([BEND, lifetime_target, '--check-only'], root)
            if typed.returncode:
                raise RuntimeError(f'{name} is not a valid negative control: {typed.stdout}{typed.stderr}')
            checked = run([BEND, root / 'PROOF.bend', '--verdict'], root)
            log = checked.stdout + checked.stderr
            (OUT / f'negative-{name}.log').write_text(log)
            if checked.returncode == 0 or 'SOME PROOFS FAIL' not in log or not re.search(r'Location: Laws.qt_(lifetime|incubation)_', log):
                raise RuntimeError(f'The Qt laws did not reject {name}: {log}')
            results.append({'mutation': name, 'type_checks': True, 'laws_reject': True})
        lifetime_target.write_text(lifetime)
        # Exercise every branch of the lifetime admission rules.
        # Scope replacements to the function so identical patterns elsewhere do
        # not accidentally turn a negative control into a syntax-only failure.
        for function in ('future_take', 'aggregate_commit', 'cleanup_access', 'sampled_reply', 'video_epoch', 'cleanup_install'):
            start = lifetime.index(f'def Lifetime.{function}(')
            end = lifetime.find('\ndef ', start + 1)
            if end < 0:
                end = len(lifetime)
            body = lifetime[start:end]
            branches = list(re.finditer(r'^(    case [^\n]+: )(\d+)$', body, re.M))
            if not branches:
                raise RuntimeError(f'No admission branches found for {function}')
            for index, branch in enumerate(branches):
                name = f'{function}_branch_{index}'
                replacement = '1' if branch[2] == '0' else '0'
                mutant = body[:branch.start(2)] + replacement + body[branch.end(2):]
                lifetime_target.write_text(lifetime[:start] + mutant + lifetime[end:])
                typed = run([BEND, lifetime_target, '--check-only'], root)
                if typed.returncode or 'ALL PROOFS CHECK' not in typed.stdout:
                    raise RuntimeError(f'{name} is not a valid negative control: {typed.stdout}{typed.stderr}')
                checked = run([BEND, root / 'PROOF.bend', '--verdict'], root)
                log = checked.stdout + checked.stderr
                (OUT / f'negative-{name}.log').write_text(log)
                law_prefix = 'Location: Laws.qt_lifetime_'
                if checked.returncode == 0 or 'SOME PROOFS FAIL' not in log or law_prefix not in log:
                    raise RuntimeError(f'The Qt laws did not reject {name}: {log}')
                results.append({'mutation': name, 'type_checks': True, 'laws_reject': True})
        lifetime_target.write_text(lifetime)
        start = lifetime.index('def Lifetime.paired_array(')
        end = lifetime.find('\ndef ', start + 1)
        if end < 0:
            end = len(lifetime)
        body = lifetime[start:end]
        for name, old, new in (
            ('paired_array_negative', 'case _ _ _: False{}', 'case False{} _ _: True{}\n    case _ _ _: False{}'),
            ('paired_array_short_first', 'case True{} True{} True{}:', 'case True{} _ True{}:'),
            ('paired_array_short_second', 'case True{} True{} True{}:', 'case True{} True{} _:'),
            ('paired_array_valid_rejected', 'case True{} True{} True{}: True{}', 'case True{} True{} True{}: False{}'),
        ):
            if body.count(old) != 1:
                raise RuntimeError(f'Paired-array control no longer matches the policy: {name}')
            lifetime_target.write_text(lifetime[:start] + body.replace(old, new) + lifetime[end:])
            typed = run([BEND, lifetime_target, '--check-only'], root)
            if typed.returncode or 'ALL PROOFS CHECK' not in typed.stdout:
                raise RuntimeError(f'{name} is not a valid negative control: {typed.stdout}{typed.stderr}')
            checked = run([BEND, root / 'PROOF.bend', '--verdict'], root)
            log = checked.stdout + checked.stderr
            (OUT / f'negative-{name}.log').write_text(log)
            if checked.returncode == 0 or 'SOME PROOFS FAIL' not in log or 'Location: Laws.qt_paired_array_' not in log:
                raise RuntimeError(f'The paired-array laws did not reject {name}: {log}')
            results.append({'mutation': name, 'type_checks': True, 'laws_reject': True})
        lifetime_target.write_text(lifetime)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mutation-checks', action='store_true')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    source = TEMPLATE.read_text()
    body_hash = check_packaged_source(source)
    version = run([BEND, 'version'])
    if version.returncode or version.stdout.strip() != 'bend 2.0.40':
        raise RuntimeError('Revalidate these proofs and IO semantics before changing Bend 2.0.40')
    checked = run([BEND, ROOT / 'PROOF.bend', '--verdict'])
    log = checked.stdout + checked.stderr
    (OUT / 'verdict.log').write_text(log)
    if checked.returncode or log.strip() != 'ALL PROOFS CHECK':
        raise RuntimeError(log)
    translation = OUT / 'PROOF.bendtt'
    exported = run([BEND, ROOT / 'PROOF.bend', '-o', translation])
    if exported.returncode:
        raise RuntimeError(exported.stdout + exported.stderr)
    laws = re.findall(r'^law (qt_[A-Za-z0-9_]+):', (ROOT / 'LAWS.bend').read_text(), re.M)
    tables = evaluate_tables(OUT)
    coverage = json.loads((ROOT / 'packages/qt612/coverage.json').read_text())
    if coverage.get('lifetime_policy') != tables:
        raise RuntimeError('Packaged lifetime policy tables differ from Bend evaluation; regenerate it')
    native_sources = [ROOT / 'build/qt612/modules' / name / 'wrappers.cpp'
                      for name in coverage['native_payload']['modules']]
    for native_source in native_sources:
        if native_source.read_text().count(cpp_tables(tables)) != 1:
            raise RuntimeError(f'Generated native source does not contain the evaluated lifetime tables exactly once: {native_source}')
    receipt = {'bend': version.stdout.strip(), 'command': 'bend PROOF.bend --verdict',
        'verdict': log.strip(), 'qt_laws': laws, 'qt_law_count': len(laws),
        'action_definitions_match_package': True, 'action_body_sha256': body_hash,
        'codec_definitions_match_package': True, 'codec_source_sha256': sha(CODEC),
        'lifetime_definitions_match_package': True, 'lifetime_source_sha256': sha(LIFETIME),
        'lifetime_tables': tables,
        'native_lifetime_table_sources': [str(p.relative_to(ROOT)) for p in native_sources],
        'sources_sha256': {str(p.relative_to(ROOT)): sha(p) for p in
                           (ROOT / 'LAWS.bend', ROOT / 'PROOF.bend', TEMPLATE, CODEC, LIFETIME)},
        'translation_sha256': sha(translation), 'native_runtime_proved': False}
    if args.mutation_checks:
        receipt['negative_controls'] = check_mutations(source)
    (OUT / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(f'PASS {len(laws)} Qt Action/Codec/Lifetime laws with --verdict; packaged definitions match')
    if args.mutation_checks:
        print(f'PASS {len(receipt["negative_controls"])} type-correct regressions rejected by the laws')
    print('Native Qt/FFI behavior still requires integration tests.')


if __name__ == '__main__':
    main()
