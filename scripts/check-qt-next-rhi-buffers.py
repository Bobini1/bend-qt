#!/usr/bin/env python3
"""Small generated RHI mapping/vertex-binding fixture; no broad compilation."""
import argparse, hashlib, importlib.util, json, os, re, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('next_conversions',ROOT/'scripts/check-qt-next-conversions-native.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module.MODULES=['QtCore','QtGui','QtOpenGL','QtWidgets']
module.FAMILIES={'QRhiBuffer':{'beginFullDynamicBufferUpdateForCurrentFrame','endFullDynamicBufferUpdateForCurrentFrame'},
 'QRhiCommandBuffer':{'setVertexInput','beginPass','endPass'},'QRhi':{'finish','endOffscreenFrame'}}
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--qt-root',type=Path,default=Path.home()/'.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
parser.add_argument('--work',type=Path,default=ROOT/'build/qt612/next-rhi-buffers')
parser.add_argument('--negative-readback-post', action='store_true',
    help='Remove the cleanup-post exception guard in the disposable native source; must fail')
args=parser.parse_args();qt=args.qt_root;work=args.work.resolve();work.mkdir(parents=True,exist_ok=True)
data=module.generate(work,qt,rhi=True)
bend_check=module.check_bend(work)
wrappers=work/'wrappers.cpp';source=wrappers.read_text()
site='        if (application) QTimer::singleShot(0, application, [] { rhi_sweep_readbacks(); });'
assert source.count(site)==1, 'Readback completion allocation-fault site changed'
source=source.replace('namespace bendqt {', 'namespace bendqt {\nstatic bool readback_post_fail;\nstatic unsigned readback_post_failures;',1)
source=source.replace(site, '        if (readback_post_fail) { readback_post_fail=false; ++readback_post_failures; throw std::bad_alloc(); }\n'+site,1)
if args.negative_readback_post:
    start=source.index('    try {\n        if (readback_post_fail)')
    end=source.index('\n}\nstatic void rhi_cancel_readback',start)
    source=source[:start]+source[start:end].split('    try {\n',1)[1].split('    } catch (...) {',1)[0]+source[end:]
wrappers.write_text(source)
defines=[]
for name,owner,signature in [('MAP','QRhiBuffer','beginFullDynamicBufferUpdateForCurrentFrame()'),
 ('UNMAP','QRhiBuffer','endFullDynamicBufferUpdateForCurrentFrame()'),('FINISH','QRhi','finish()'),
 ('END_FRAME','QRhi','endOffscreenFrame(QFlags<QRhi::EndFrameFlag>)')]:
    found=[m for m in data['operations'] if m['owner']==owner and m['signature']==signature]
    if len(found)!=1:raise RuntimeError((name,found))
    defines.append(f'#define OP_{name} bqt_op_{found[0]["operation"]}')
found=[m for m in data['operations'] if m['owner']=='QRhiCommandBuffer' and m['signature'].startswith('setVertexInput(int,int,')]
assert len(found)==1,found
defines.append(f'#define OP_VERTEX bqt_op_{found[0]["operation"]}')
defines += [f'#define TYPE_{name} {value}' for name,value in data['ids'].items() if re.fullmatch(r'[a-zA-Z_]\w*',name)]
config=work/'fixture-config.h';config.write_text('\n'.join(defines)+'\n')
fixture=ROOT/'examples/qt612/next-rhi-buffers-native.cpp';exe=work/'native'
cmd=[x for x in module.compiler_flags(qt,'clang++-19',data['modules']) if x not in ('-O1','-DNDEBUG')]
cmd += ['-O0','-ferror-limit=12','-DBQT_GENERATED_WRAPPERS="'+str(work/'wrappers.cpp')+'"','-include',str(config),str(fixture),
 '-L'+str(qt/'lib'),'-Wl,-rpath,'+str(qt/'lib'),*['-lQt6'+x[2:] for x in reversed(data['modules'])],'-pthread','-o',str(exe)]
with (work/'compile.log').open('w') as log:
    compiled=subprocess.run(['flock','-x','/tmp/bendqt-focused-compile.lock',*cmd],stdout=log,stderr=subprocess.STDOUT,timeout=1800)
assert compiled.returncode==0,work/'compile.log'
result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=60,env=dict(os.environ,
 QT_QPA_PLATFORM='offscreen',QT_PLUGIN_PATH=str(qt/'plugins'),LD_LIBRARY_PATH=str(qt/'lib')))
output=result.stdout+result.stderr;(work/'run.log').write_text(output)
assert result.returncode==0 and 'QT612_NEXT_RHI_BUFFERS_OK' in output,f'Native RHI fixture exited {result.returncode}\n{output}'
(work/'receipt.json').write_text(json.dumps(dict(complete=True,output=output,bend_check=bend_check,
 readback_cleanup_checks=['readback handler runs although posting the storage sweep fails',
                         'finished result storage stays alive until later safe sweep',
                         'shutdown retires an abandoned readback and frame'],
 source_sha256=hashlib.sha256((work/'wrappers.cpp').read_bytes()).hexdigest(),
 fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest()),indent=2))
print(output)
