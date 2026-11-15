#!/usr/bin/env python3
"""Assemble and validate prepared source, notice and runtime-data evidence."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
from distribution_modules import plan, runtime_owners
from qt_licenses import Inventory
from runtime_release import prepare


def pinned(path):
    path = Path(path).resolve()
    return dict(file=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def assemble(qt, profile, snapshots, notices, supplements, assets, output):
    output = Path(output).resolve(); output.parent.mkdir(parents=True, exist_ok=True)
    legal, sources = {}, copy.deepcopy(snapshots['sources'])
    for location, row in notices['notices'].items():
        name = 'notices/' + Path(row['file']).name
        legal[name] = dict(file=row['file'], sha256=row['sha256'])
        sources[location]['notices'] = [name]
    sources.update(copy.deepcopy(supplements['sources']))
    supplement_rows = copy.deepcopy(supplements['supplements'])
    for row in supplement_rows.values():
        names = []
        for notice in row['notices']:
            name = 'notices/' + Path(notice['file']).name
            checked = dict(file=notice['file'], sha256=notice['sha256'])
            if name in legal and legal[name] != checked:
                raise ValueError('Conflicting runtime notice: ' + name)
            legal[name] = checked; names.append(name)
        location = row['source']
        sources[location]['notices'] = sorted(set(sources[location].get('notices', []) + names))
    data = copy.deepcopy(assets)
    for row in data['assets'].values():
        row['notices'] = sorted({name for location in row['sources'] for name in sources[location]['notices']})
    license = output.parent / 'LICENSE'
    license.write_text((ROOT / 'generator/templates/distribution-license.txt').read_text().replace(
        '@MIT@', (ROOT / 'LICENSE').read_text().strip()))
    instructions = output.parent / 'BUILDING.txt'
    lines = [
        'Rebuilding and replacing the bundled Qt runtime', '',
        'The package contains Qt ' + profile['minimum_qt'] + ' for Linux x86-64.',
        'First download the matching source archives in corresponding-sources.json.',
        'Verify their SHA-256 values before extracting them. Each archive has one',
        'repository root. Place the recorded submodule snapshots at their recorded',
        'paths and apply the recorded file overlays after verifying their hashes.', '',
        'Build Qt with its documented CMake workflow and a C++ compiler supported',
        'by that Qt version. Keep the same Qt patch version and enabled modules.',
        'Private Qt interfaces used by the bindings require this matching build.',
        'The original installer configuration and third-party build options are',
        'recorded in the original SPDX documents under notices/sbom/.', '',
        'Install the rebuilt libraries, plugins, QML modules, resources and helper',
        'processes under one prefix. Set BEND_QT_RUNTIME to that prefix before',
        'starting the Bend application. The loader checks the complete runtime and',
        'its version before loading the bindings. No application rebuild is needed',
        'when the replacement preserves the recorded native ABI.', '',
        'Qt build instructions: https://doc.qt.io/qt-6/build-sources.html',
        'FFmpeg build instructions: https://ffmpeg.org/platform.html',
        'ICU build instructions: https://unicode-org.github.io/icu/userguide/icu4c/build.html', '',
        'Supplemental runtime build evidence', '',
    ]
    for name, row in sorted(supplement_rows.items()):
        lines += [name, json.dumps(row.get('provenance', {}), indent=2), '']
    for location, row in sorted(sources.items()):
        variants = row.get('source_spdx_verification', {}).get('metadata_variants', [])
        if variants:
            lines += ['Recorded repository metadata differences', location, json.dumps(variants, indent=2), '']
    instructions.write_text('\n'.join(lines))
    legal['notices/BUILDING.txt'] = pinned(instructions)
    manifest = dict(schema=1, qt=profile['minimum_qt'], flavor=profile['license_flavor'],
        package_license=pinned(license), sources=sources, notices=legal,
        supplements=supplement_rows, assets=data['assets'], excluded_assets=data['excluded_assets'])
    output.write_text(json.dumps(manifest, indent=2) + '\n')
    prepared = prepare(output, qt, profile)
    parts = [SimpleNamespace(name=row['name'], owned_modules=row['qt_modules']) for row in plan(profile, qt)]
    owners = runtime_owners(prepared, parts, qt)
    receipt = dict(manifest_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        binaries=len(prepared['selection']['files']), assets=len(data['assets']),
        excluded_assets=len(data['excluded_assets']), sources=len(sources), notices=len(legal),
        module_files={part.name: sum(part.name in value for value in owners.values()) for part in parts},
        core_only_gpl_code=False, verification_complete=True,
        boundary='Release inputs and per-file module ownership; generated native packages and runtime integration require canonical validation')
    output.with_suffix('.receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qt-root', type=Path, required=True)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--notices', type=Path, required=True)
    parser.add_argument('--supplements', type=Path, required=True)
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    read = lambda path: json.loads(path.read_text())
    receipt = assemble(args.qt_root, read(args.profile), read(args.sources), read(args.notices),
        read(args.supplements), read(args.assets), args.output)
    print('QT_RUNTIME_RELEASE_PREPARED', json.dumps(receipt))


if __name__ == '__main__':
    main()
