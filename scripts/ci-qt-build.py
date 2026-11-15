#!/usr/bin/env python3
"""Prepare, generate and validate one pinned Qt distribution without publishing."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
TARGETS = json.loads((ROOT / 'generator/qt_targets.json').read_text())


def configuration(version):
    if version not in TARGETS:
        raise ValueError('Unreviewed Qt target: ' + version)
    short = ''.join(version.split('.')[:2])
    cache = Path.home() / '.cache/bend-qt-generator'
    suffix = '' if version == '6.12.0' else '-' + version
    return dict(version=version, cache=cache,
        work=ROOT / 'build' / ('qt' + short),
        qt=cache / 'Qt' / version / 'gcc_64',
        profile=ROOT / 'generator' / ('qt' + short),
        package=ROOT / 'packages' / ('qt' + short),
        extractor=cache / ('build' + suffix) / 'bend-qt-extract',
        source=cache / ('pyside-setup' + suffix),
        release=ROOT / 'build' / ('runtime-release-' + version))


def commands(c, stage):
    release = c['release']
    sources = release / 'sources.json'
    notices = release / 'notices/notices.json'
    supplements = release / 'supplements.json'
    audit = release / 'asset-audit.json'
    assets = release / 'assets.json'
    manifest = release / 'runtime-release.json'
    profile = c['profile'] / 'profile.json'
    common = ['--qt-root', c['qt']]
    # Runtime asset planning imports the same pinned REUSE resolver as the
    # audit. Keep every preparation subprocess in the maintainer environment.
    py = str(c['cache'] / 'venv/bin/python') if stage == 'prepare' else sys.executable
    if stage == 'prepare':
        return [
            [py, 'generator/qt_sources.py', *common, '--output', sources],
            [py, 'generator/runtime_notices.py', *common, '--sources', sources,
             '--output', release / 'notices'],
            [py, 'generator/runtime_supplements.py', *common, '--sources', sources,
             '--notices', notices, '--output', supplements],
            [c['cache'] / 'venv/bin/python', 'scripts/audit-qt-runtime-assets.py',
             *common, '--sources', sources, '--flavor', 'gpl', '--output', audit],
            [py, 'generator/runtime_assets.py', *common, '--profile', profile,
             '--sources', sources, '--audit', audit, '--output', assets],
            [py, 'scripts/prepare-qt-runtime-release.py', *common, '--profile', profile,
             '--sources', sources, '--notices', notices, '--supplements', supplements,
             '--assets', assets, '--output', manifest],
        ]
    if stage == 'generate':
        return [[py, 'generator/generate.py', '--profile', c['profile'],
                 '--qt-prefix', c['qt'], '--extractor', c['extractor'],
                 '--pyside-source', c['source'], '--work', c['work'],
                 '--output', c['package'], '--runtime-manifest', manifest]]
    if stage == 'verify':
        if c['version'] == '6.12.0':
            return [[py, 'scripts/check-qt612.py', '--bundle', '--generator-checks',
                     '--reject-system-qt', '--runtime-manifest', manifest]]
        return [[py, 'scripts/check-qt-distribution-package.py', '--package', c['package'],
                 '--profile', profile, *common, '--work', c['work'] / 'distribution-package-check'],
                *[[py, 'scripts/' + name + '.py', *common,
                   '--work', c['work'] / name] for name in (
                    'check-qt-callback-spellings', 'check-qt-range-model-versions',
                    'check-qt-protected-lvalue-getters')]]
    raise ValueError('Unknown command stage: ' + stage)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qt-version', required=True, choices=tuple(TARGETS))
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('stage', choices=('prepare', 'generate', 'verify', 'artifact', 'diagnostics'))
    args = parser.parse_args()
    config = configuration(args.qt_version)
    if args.stage in ('prepare', 'generate', 'verify'):
        for command in commands(config, args.stage):
            command = list(map(str, command))
            print(shlex.join(command), flush=True)
            if not args.dry_run:
                subprocess.run(command, cwd=ROOT, check=True)
        if args.stage == 'verify' and not args.dry_run:
            receipt = config['work'] / 'ci-verification.json'
            receipt.write_text(json.dumps(dict(qt=args.qt_version,
                verification_complete=True,
                canonical_612=args.qt_version == '6.12.0',
                boundary=('Complete Qt 6.12 canonical validation' if args.qt_version == '6.12.0'
                          else 'Fresh full-package consumers and targeted version compatibility checks'),
                public_hub_publication=False), indent=2) + '\n')
    else:
        if args.dry_run:
            raise ValueError('Use dry-run with a command stage')
        output = ROOT / 'build/ci-artifacts'
        output.mkdir(parents=True, exist_ok=True)
        if args.stage == 'artifact':
            receipt = json.loads((config['work'] / 'ci-verification.json').read_text())
            if receipt.get('verification_complete') is not True or receipt.get('qt') != args.qt_version:
                raise ValueError('Package artifact requires successful version validation')
            subprocess.run(['tar', '--zstd', '-cf', str(output / ('bend-qt-' + args.qt_version + '.tar.zst')),
                            '-C', str(ROOT), str(config['package'].relative_to(ROOT)),
                            str((config['work'] / 'ci-verification.json').relative_to(ROOT))], check=True)
        else:
            with tarfile.open(output / ('diagnostics-' + args.qt_version + '.tar.gz'), 'w:gz') as archive:
                for folder in (config['work'], config['release']):
                    if not folder.is_dir():
                        continue
                    for path in sorted(folder.rglob('*')):
                        if path.is_file() and (path.suffix == '.log' or path.name.endswith('receipt.json')
                                              or path.name == 'ci-verification.json'):
                            archive.add(path, arcname=str(path.relative_to(ROOT)))


if __name__ == '__main__':
    main()
