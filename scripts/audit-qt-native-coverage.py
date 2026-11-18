#!/usr/bin/env python3
"""Recompute the production coverage classification from extracted, measured APIs."""
import argparse
from collections import Counter
import datetime
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
from generate import Generator
import callbacks
from native_objects import saved_traits
import coverage_inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=ROOT / 'build/qt612')
    parser.add_argument('--profile', type=Path, default=ROOT / 'generator/qt612/profile.json')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    source = args.work / 'api.json'
    api = json.loads(source.read_text())
    traits = saved_traits(args.work)
    profile = json.loads(args.profile.read_text())
    upstream = json.loads((args.work / 'upstream.json').read_text())
    profile['qt_modules'] = upstream['modules']
    for cls in api['classes']:
        measured = traits.get(cls['name'])
        if measured:
            cls.update(measured)
            cls['native_copyable'], cls['native_movable'] = measured['copyable'], measured['movable']
    generator = Generator(api, profile)
    generator.collect()
    callbacks.prepare(generator)
    # Handwritten adapters register their alternatives and operation metadata
    # during emission. Audit the same completed model used by the package.
    generator.emit()
    inventory = coverage_inventory.inventory(generator)
    gaps = [item for item in inventory['unique_exclusions'] if item['category'] == 'binding_gap']
    omissions = []
    for path in sorted(args.work.rglob('*.log')):
        if path.name not in ('mjb_rejected_functions.log', 'mjb_rejected_classes.log',
                             'mjb_rejected_enums.log', 'mjb_rejected_fields.log'):
            continue
        category = ''
        for line in path.read_text(errors='replace').splitlines():
            if line and not line.startswith(('*', ' -')):
                category = line
            elif line.startswith(' -'):
                omissions.append(dict(log=str(path.relative_to(args.work)), category=category, detail=line.strip()))
    artifact = dict(generated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        api=str(source), api_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        traits=str(args.work), traits_sha256=hashlib.sha256(json.dumps(traits, sort_keys=True).encode()).hexdigest(),
        modules=profile['qt_modules'], selected_classes=len(generator.selected),
        method_entries=len(generator.methods), unique_public_native_gaps=len(gaps),
        reasons=dict(Counter(item['reason'] for item in gaps).most_common()), gaps=gaps,
        native_coverage=inventory, callbacks=callbacks.inventory(generator),
        public_fields=generator.public_fields, excluded_fields=generator.excluded_fields,
        extraction_omissions=omissions, additive_extraction=api.get('additive_extraction', []),
        full_coverage=False)
    output = args.output or args.work / 'remaining-native-gaps.json'
    output.write_text(json.dumps(artifact, indent=2) + '\n')
    print(json.dumps({key: artifact[key] for key in ('selected_classes', 'method_entries',
        'unique_public_native_gaps', 'reasons')}, indent=2))
    print(json.dumps(inventory['unique_exclusions_by_category'], indent=2))
    for gap in gaps:
        print(f'{gap["owner"]}: {gap["signature"]} --- {gap["reason"]}')


if __name__ == '__main__':
    main()
