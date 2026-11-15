#!/usr/bin/env python3
"""Check the actual paired-array admission policy and type-correct regressions."""
import argparse,hashlib,json,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BEND=Path.home()/'.bend/bin/bend'
sys.path.insert(0,str(ROOT/'generator'))
from lifetime import evaluate_tables,cpp_tables

def run(*args,cwd=ROOT):
    return subprocess.run([str(BEND),*map(str,args)],cwd=cwd,capture_output=True,text=True,timeout=90)

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--native-source',type=Path,
    default=ROOT/'build/qt612/next-conversions-check/wrappers.cpp')
args=parser.parse_args()
out=ROOT/'build/qt612/next-conversion-proofs';out.mkdir(parents=True,exist_ok=True)
result=run('PROOF.bend','--verdict');(out/'verdict.log').write_text(result.stdout+result.stderr)
assert result.returncode==0 and result.stdout.strip()=='ALL PROOFS CHECK'
template=ROOT/'generator/templates/lifetime.bend';original=template.read_text()
prefix,tail=original.split('def Lifetime.paired_array(',1)
body,separator,suffix=tail.partition('\ndef ')
mutants={
 'accept_negative':body.replace('case _ _ _: False{}','case False{} _ _: True{}\n    case _ _ _: False{}'),
 'accept_short_first':body.replace('case True{} True{} True{}:', 'case True{} _ True{}:'),
 'accept_short_second':body.replace('case True{} True{} True{}:', 'case True{} True{} _:'),
 'reject_valid':body.replace('case True{} True{} True{}: True{}','case True{} True{} True{}: False{}'),
}
controls=[]
with tempfile.TemporaryDirectory(prefix='bend-qt-conversion-proofs-') as temp:
    root=Path(temp);(root/'generator/templates').mkdir(parents=True)
    for name in ('LAWS.bend','PROOF.bend'):shutil.copyfile(ROOT/name,root/name)
    for name in ('action.bend','codec.bend','lifetime.bend'):
        shutil.copyfile(ROOT/'generator/templates'/name,root/'generator/templates'/name)
    for name,mutated in mutants.items():
        (root/'generator/templates/lifetime.bend').write_text(prefix+'def Lifetime.paired_array('+mutated+separator+suffix)
        typed=run('generator/templates/lifetime.bend','--check-only',cwd=root)
        assert typed.returncode==0,(name,typed.stdout,typed.stderr)
        result=run('PROOF.bend','--verdict',cwd=root);text=result.stdout+result.stderr
        (out/(name+'.log')).write_text(text)
        assert result.returncode!=0 and 'SOME PROOFS FAIL' in text and 'Location: Laws.qt_paired_array_' in text,(name,text)
        controls.append(name)
tables=evaluate_tables(out)
native=args.native_source.read_text()
declaration=[s for s in cpp_tables(tables).splitlines() if 'lifetime_paired_array[' in s][0]
assert native.count(declaration)==1 and 'if (!lifetime_paired_array[' in native
receipt={'verdict':'ALL PROOFS CHECK','new_laws':4,'type_correct_negative_controls_rejected':controls,
         'native_policy_source_matches':True,'native_runtime_proved':False,
         'native_source':str(args.native_source.resolve()),
         'native_source_sha256':hashlib.sha256(args.native_source.read_bytes()).hexdigest(),
         'policy_sha256':hashlib.sha256(template.read_bytes()).hexdigest()}
(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
