#!/usr/bin/env python3
"""Collect-only delta against the captured full-model audit; no native build."""
import argparse,hashlib,json,sys
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'generator'))
from generate import Generator
import callbacks,coverage_inventory,public_fields
from native_objects import saved_traits
work=ROOT/'build/qt612'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline',type=Path,default=work/'current-gap-audit/inventory.json')
parser.add_argument('--model-work',type=Path,default=work,
                    help='Coherent extraction directory containing api.json and its saved native traits')
args=parser.parse_args()
baseline=args.baseline
api=json.loads((args.model_work/'api.json').read_text());traits=saved_traits(args.model_work)
if sys.platform=='win32':
    # Read-only Python collection can use host RAM while WSL's full compiler is
    # near its memory limit. Native evidence still comes from the installed kit.
    def paths(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key=='source_file' and isinstance(item,str) and item.startswith('/home/'):
                    value[key]='//wsl.localhost/Ubuntu-24.04'+item
                else:paths(item)
        elif isinstance(value,list):
            for item in value:paths(item)
    paths(api)
for c in api['classes']:
    if c['name'] in traits:
        c.update(traits[c['name']]);c['native_copyable']=c['copyable'];c['native_movable']=c['movable']
g=Generator(api,json.loads((ROOT/'generator/qt612/profile.json').read_text()));g.collect()
callbacks.prepare(g);public_fields.prepare(g)
inventory=coverage_inventory.inventory(g)
old=json.loads(baseline.read_text())
old_unique={(owner,signature) for owner,signature,_ in old['generated_unique']}
new_unique={}
by_minimal={}
for m in g.methods:
    f=m['function'];key=f['declaring_class'],f['signature']
    by_minimal.setdefault((f['declaring_class'],f['minimal_signature']),[]).append(m['bend_name'])
    if key not in old_unique:
        new_unique[key]=dict(owner=key[0],signature=key[1],minimal_signature=f['minimal_signature'],
          public=m['bend_name'],arguments=[t['bend'] for t in m['args']],result=m['return']['bend'],
          adaptation=f.get('adaptation'),source_signatures=f.get('source_signatures',[]))
after={(x['owner'],x['signature']):x for x in inventory['unique_exclusions']}
closed=[];remaining=[];alternatives=[];reclassified=[]
for row in old['native_coverage']['unique_exclusions']:
    if row['category']!='binding_gap':continue
    key=row['owner'],row['signature']
    if key in by_minimal:closed.append(dict(row,generated=sorted(set(by_minimal[key]))))
    else:
        current=after.get(key,row)
        if current['category']=='explicit_alternative':alternatives.append(current)
        elif current['category']!='binding_gap':reclassified.append(current)
        else:remaining.append(current)
report=dict(baseline_sha256=hashlib.sha256(baseline.read_bytes()).hexdigest(),
 model_inputs={'api.json':hashlib.sha256((args.model_work/'api.json').read_bytes()).hexdigest(),
               'native_traits':hashlib.sha256(json.dumps(traits,sort_keys=True).encode()).hexdigest()},
 baseline_entries=old['generated_entries'],entries=len(g.methods),
 baseline_selected=old['selected_count'],selected=len(g.selected),
 closed_binding_gaps=closed,remaining_binding_gaps=remaining,
 prior_gaps_with_explicit_alternatives=alternatives,reclassified_prior_gaps=reclassified,
 new_unique_native_signatures=list(new_unique.values()),
 new_by_owner=dict(Counter(x['owner'] for x in new_unique.values())),
 exclusions_by_category=inventory['unique_exclusions_by_category'],
 partial_native_signatures=inventory['partial_native_signatures'],
 proof_boundary='Paired-array admission is proved from the actual native decision table; Qt effects, buffer contents and native lifetime behavior are integration-tested, not proved.')
(work/'next-conversion-delta.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('closed_binding_gaps','remaining_binding_gaps','prior_gaps_with_explicit_alternatives','reclassified_prior_gaps','new_unique_native_signatures','partial_native_signatures')},indent=2))
print('CLOSED EXACT SIGNATURES',len(closed),'EXPLICIT ALTERNATIVES',len(alternatives),'RECLASSIFIED',len(reclassified),'REMAINING',len(remaining),'NEW UNIQUE',len(new_unique))
for row in remaining:print(row['owner'],row['signature'],row['reason'])
