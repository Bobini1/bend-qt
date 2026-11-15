#!/usr/bin/env python3
"""Check that all reviewed CI targets preserve their native validation gates."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ci_build', ROOT / 'scripts/ci-qt-build.py')
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)

for version in ci.TARGETS:
    config = ci.configuration(version)
    profile = ci.json.loads((config['profile'] / 'profile.json').read_text())
    assert profile['minimum_qt'] == version
    generated = list(map(str, ci.commands(config, 'generate')[0]))
    assert str(config['profile']) in generated and str(config['package']) in generated
    assert '--runtime-manifest' in generated
    verified = [list(map(str, row)) for row in ci.commands(config, 'verify')]
    if version == '6.12.0':
        assert len(verified) == 1
        assert {'--bundle', '--generator-checks', '--reject-system-qt'} <= set(verified[0])
    else:
        assert any('scripts/check-qt-distribution-package.py' in row for row in verified)
        assert all(str(config['qt']) in row for row in verified)
    for stage in ('prepare', 'generate', 'verify'):
        for row in ci.commands(config, stage):
            assert '--publish' not in row
try:
    ci.configuration('6.99.0')
except ValueError:
    pass
else:
    raise AssertionError('An unreviewed Qt version was accepted')
print('PASS CI target isolation and required native validation gates')
