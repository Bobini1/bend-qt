#!/usr/bin/env python3
"""Classify runtime data using exact installed/source SPDX evidence."""
import argparse
from contextlib import nullcontext
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
from qt_licenses import Inventory, SourceInventory, allows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qt-root', type=Path, default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    parser.add_argument('--flavor', choices=('lgpl', 'gpl'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sources', type=Path, help='Prepared exact source snapshots; use the maintainer venv with REUSE 5.1.1')
    args = parser.parse_args()
    qt = args.qt_root.resolve(); inventory = Inventory(qt); sources = SourceInventory(qt, inventory)
    included, excluded, unknown = [], [], []
    resolver = nullcontext(None)
    if args.sources:
        from source_licensing import Resolver
        resolver = Resolver(json.loads(args.sources.read_text())['sources'])
    with resolver as reuse:
      for top in ('qml', 'resources', 'translations'):
        for path in sorted((qt / top).rglob('*')):
            if not path.is_file() or path.suffix in ('.so', '.o'):
                continue
            relative = path.relative_to(qt).as_posix()
            if relative in inventory.files:
                evidence = inventory.files[relative]
                decision = allows(evidence['expression'], args.flavor)
                row = dict(path=relative, evidence=evidence)
                if decision is True:
                    row['evidence'] = inventory.binary(path, args.flavor)
            else:
                row = dict(path=relative, source=sources.match(path, args.flavor))
                if reuse and row['source']['candidates']:
                    row['source'] = reuse.resolve(row['source'], args.flavor)
                decision = row['source']['allowed']
            (included if decision is True else excluded if decision is False else unknown).append(row)
    result = dict(schema=1, flavor=args.flavor, included=included, excluded=excluded, unknown=unknown,
        evidence_sha256={**inventory.evidence, **sources.evidence}, verification_complete=False,
        boundary='Exact file licensing evidence only; unknown origins/REUSE expressions, source delivery, module data dependencies and notices remain release requirements')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f'Qt runtime data: {len(included)} permitted, {len(excluded)} excluded, {len(unknown)} unresolved')


if __name__ == '__main__':
    main()
