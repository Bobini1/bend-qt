#!/usr/bin/env python3
"""Check that all reviewed CI targets preserve their native validation gates."""
import importlib.util
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ci_build', ROOT / 'scripts/ci-qt-build.py')
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)

spec = importlib.util.spec_from_file_location('qt612_checks', ROOT / 'scripts/check-qt612.py')
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)
PARTS = checks.PARTS
# The workflow runs every part on its own runner, except regeneration: a second
# runner generates the same inputs, and the verdict compares both digests.
workflow = (ROOT / '.github/workflows/qt-builds.yml').read_text()
[matrix] = re.findall(r'^\s+part: \[([^\]]*)\]$', workflow, re.M)
assert [part.strip() for part in matrix.split(',')] == [p for p in PARTS if p != 'regeneration'], matrix
assert re.search(r'^\s+needs: \[check-612, regenerate-612\]$', workflow, re.M)
assert workflow.count('--role independent state') == 1 and workflow.count('--role tested state') == 1

for version in ci.TARGETS:
    config = ci.configuration(version)
    profile = ci.json.loads((config['profile'] / 'profile.json').read_text())
    assert profile['minimum_qt'] == version
    generated = list(map(str, ci.commands(config, 'generate')[0]))
    assert str(config['profile']) in generated and str(config['package']) in generated
    assert '--runtime-manifest' in generated
    for row in ci.commands(config, 'prepare'):
        assert Path(row[0]) == config['cache'] / 'venv/bin/python', (
            'Every release preparation stage needs the pinned REUSE environment', row)
    verified = [list(map(str, row)) for row in ci.commands(config, 'verify')]
    if version == ci.CANONICAL:
        assert len(verified) == 1
        assert {'--bundle', '--generator-checks', '--reject-system-qt'} <= set(verified[0])
        assert '--part' not in verified[0] and '--combine' not in verified[0]
        # Each part runs the same gate options; the verdict combines exactly them.
        for part in PARTS:
            [row] = [list(map(str, row)) for row in ci.commands(config, 'verify', [part])]
            assert row == verified[0] + ['--part', part]
        [row] = [list(map(str, row)) for row in ci.commands(config, 'verdict')]
        assert row[:len(verified[0])] == verified[0]
        assert row[len(verified[0]):] == ['--combine', '--independent-generation',
                                          str(ci.STATE / 'independent/generation.json')]
    else:
        assert any('scripts/check-qt-distribution-package.py' in row for row in verified)
        assert all(str(config['qt']) in row for row in verified)
        for stage, parts in (('verify', ['consumers']), ('verdict', [])):
            try:
                ci.commands(config, stage, parts)
            except ValueError:
                pass
            else:
                raise AssertionError('Only the canonical gate is checked in parts: ' + version)
    for stage in ('prepare', 'generate', 'verify') + (('verdict',) if version == ci.CANONICAL else ()):
        for row in ci.commands(config, stage):
            assert '--publish' not in row
try:
    ci.configuration('6.99.0')
except ValueError:
    pass
else:
    raise AssertionError('An unreviewed Qt version was accepted')
print('PASS CI target isolation, required native validation gates and canonical parts')
