#!/usr/bin/env python3
"""Create an isolated-tree handoff patch; never modify the production tree."""
import difflib,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
production=ROOT.parents[2]
baseline=ROOT/'baseline'
for name in ('LAWS.bend','PROOF.bend'):
    target=baseline/name
    if not target.exists():
        original=(production/name).read_bytes()
        assert (ROOT/name).read_bytes().startswith(original.rstrip()),'Shared proof baseline drifted'
        target.write_bytes(original)
files=[p.relative_to(ROOT) for p in (ROOT/'generator').rglob('*') if p.is_file() and '__pycache__' not in p.parts]
files += [Path('LAWS.bend'),Path('PROOF.bend')]
files += [p.relative_to(ROOT) for folder in ('scripts','examples/qt612') for p in (ROOT/folder).glob('*next*') if p.is_file()]
manifest=[];patch=[]
for relative in sorted(set(files)):
    if str(relative).replace('\\','/')=='generator/public_records.py':continue # Owned by the lifetime agent.
    target=ROOT/relative;previous=baseline/relative
    before=previous.read_text(encoding='utf8') if previous.exists() else ''
    after=target.read_text(encoding='utf8')
    if before==after:continue
    path=relative.as_posix()
    patch += difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/'+path if previous.exists() else '/dev/null',tofile='b/'+path)
    manifest.append(dict(path=path,baseline_sha256=hashlib.sha256(previous.read_bytes()).hexdigest() if previous.exists() else None,
                         sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
(ROOT/'patch.diff').write_text(''.join(patch),encoding='utf8',newline='\n')
(ROOT/'patch-manifest.json').write_text(json.dumps(dict(files=manifest,dependencies=['generator/public_records.py from next-lifetimes'],
 production_modified=False),indent=2)+'\n',encoding='utf8')
print(len(manifest),'files',len(''.join(patch)),'patch bytes')
