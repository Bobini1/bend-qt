#!/usr/bin/env python3
"""Focused generated-native checks for the next conversion batch."""
import argparse, hashlib, json, os, re, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'generator'))
import callbacks, coverage_inventory, native_objects, representations, public_fields
import qobject_interfaces, qio_pipe
from generate import Generator
from lifetime import evaluate_tables, cpp_tables
from backend import compiler_flags, versioned_include_paths
from upstream import prepare

MODULES=['QtCore','QtGui','QtNetwork','QtOpenGL','QtWidgets']
FAMILIES={
 'QBitArray':{'bits'}, 'QBuffer':{'setData'}, 'QByteArray':{'append','prepend','push_back','push_front'},
 'QCborStreamReader':{'readStringChunk'}, 'QDir':{'mkdir','mkpath'},
 'QGlyphRun':{'setRawData'}, 'QHostAddress':{'QHostAddress','setAddress'}, 'QImageReader':{'read'},
 'QLocale':{'toDouble','toFloat','toInt','toLong','toLongLong','toShort','toUInt','toULongLong','toUShort'},
 'QMatrix4x4':{'data','constData'}, 'QOpenGLTexture':{'borderColor'}, 'QPolygon':{'QPolygon'},
 'QQuaternion':{'getAxisAndAngle'}, 'QRandomGenerator':{'generate'},
 'QRawFont':{'advancesForGlyphIndexes','glyphIndexesForChars'}, 'QTextLine':{'cursorToX'},
 'QThread':{'currentThreadId'}, 'QTransform':{'map'}, 'QUdpSocket':{'writeDatagram'},
 'QTextBoundaryFinder':{'QTextBoundaryFinder','operator=','swap'},
}
FAMILIES.update({f'QMatrix{rows}x{columns}':{'data','constData'}
                 for rows in (2,3,4) for columns in (2,3,4)})

def check_bend(work):
    result=subprocess.run([str(Path.home()/'.bend/bin/bend'),str(work/'qt.bend'),'--check-only'],capture_output=True,text=True,timeout=120)
    diagnostic=result.stdout+result.stderr
    (work/'typecheck.log').write_text(diagnostic)
    if result.returncode!=1 or not re.fullmatch(r'SOME PROOFS FAIL\s+Error: \d+ defs rely on unsafe or foreign code:\s+defs that depend on foreign effects: [A-Za-z0-9_., \n]+',diagnostic):
        raise RuntimeError('Unexpected generated-module checker diagnostic: '+diagnostic[:2000])
    return dict(foreign_effect_boundary_only=True,bend_sha256=hashlib.sha256((work/'qt.bend').read_bytes()).hexdigest())

def generate(work,qt,*,rhi=False,api_transform=None,extra_headers=()):
    headers,_,modules,_,_=prepare(Path.home()/'.cache/bend-qt-generator/pyside-setup',qt,MODULES,work,limited_abi=rhi)
    api=json.loads((ROOT/'build/qt612/api.json').read_text())
    qobject_interfaces.restore(api,work)
    qio_pipe.restore(api,work)
    if api_transform:api_transform(api)
    if extra_headers:headers.write_text(headers.read_text()+'\n'+'\n'.join('#include <'+name+'>' for name in extra_headers)+'\n')
    traits=json.loads((ROOT/'build/qt612/native-traits.json').read_text())
    packages={'PySide6.'+x for x in modules}
    api['classes']=[c for c in api['classes'] if (c['package'] in packages or c['name'] in FAMILIES or rhi and '/rhi/' in c.get('source_file','')) and (rhi or '/rhi/' not in c.get('source_file',''))]
    api['global_functions']=[f for f in api.get('global_functions',[]) if f.get('package','PySide6.QtCore') in packages]
    api['enums']=[e for e in api.get('enums',[]) if e.get('package','PySide6.QtCore') in packages]
    for c in api['classes']:
        if c['name'] in traits:
            c.update(traits[c['name']]);c['native_copyable']=c['copyable'];c['native_movable']=c['movable']
    profile=json.loads((ROOT/'generator/qt612-core/profile.json').read_text());profile['qt_modules']=modules;profile['limited_abi']=rhi
    g=Generator(api,profile);g.collect()
    audit=coverage_inventory.inventory(g)
    (work/'coverage.json').write_text(json.dumps({'count':len(g.methods),'exclusions':[r for r in audit['unique_exclusions'] if r['owner'] in FAMILIES and any(r['signature'].startswith(m+'(') for m in FAMILIES[r['owner']])],'partial':audit['partial_native_signatures']},indent=2))
    g.methods=[m for m in g.methods if m['function']['name'] in FAMILIES.get(m['class'],()) and not m.get('omitted_defaults')]
    callbacks.prepare(g);g.callback_classes=[];g.callback_methods={};g.callback_functions=[]
    recorded_effects=[];original_effect=g.emit_effect
    def record_effect(public,params,returned,operation,**options):
        recorded_effects.append(dict(public=public,operation=operation))
        return original_effect(public,params,returned,operation,**options)
    g.emit_effect=record_effect
    bend,effects,dispatch=g.emit()
    aliases=''.join(f'using {n} = {s};\n' for n,s in api['typedefs'].items() if n in g.ids)+representations.aliases(g)
    before,after=callbacks.qml_sources(g,qt,work)
    abi=(ROOT/'generator/templates/abi.h').read_text().replace('@ARGUMENT_CAPACITY@','64')
    source=headers.read_text()+before+aliases+(ROOT/'generator/templates/runtime.cpp').read_text()+after
    for key,value in [('ABI',abi),('LIFETIME',cpp_tables(evaluate_tables(work))),('NATIVE_OBJECTS',native_objects.traits(g)),('DISPATCH',dispatch)]:
        source=source.replace('// @'+key+'@',value)
    (work/'wrappers.cpp').write_text(source);(work/'qt.bend').write_text(bend);(work/'effects.txt').write_text(effects)
    metadata={'ids':g.ids,'modules':modules,'fields':getattr(g,'public_fields',[]),'excluded_fields':getattr(g,'excluded_fields',[]),'effects':recorded_effects,'operations':[{'owner':m['class'],'name':m['function']['name'],'signature':m['function']['minimal_signature'],'public':m['bend_name'],'operation':m['operation'],'args':m['args'],'outputs':m.get('outputs',[])} for m in g.methods]}
    (work/'operations.json').write_text(json.dumps(metadata,indent=2))
    print('Generated focused',len(g.methods),'methods',len(source),'bytes',flush=True)
    return metadata

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--generate-only',action='store_true');ap.add_argument('--reuse',action='store_true')
    ap.add_argument('--qt-root',type=Path,default=Path.home()/'.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    args=ap.parse_args();work=ROOT/'build/qt612/next-conversions-check';work.mkdir(parents=True,exist_ok=True)
    metadata=json.loads((work/'operations.json').read_text()) if args.reuse else generate(work,args.qt_root)
    if args.generate_only:return
    bend_check=check_bend(work)
    specs={
      'BUFFER_SET':('QBuffer',r'setData\(const char\*,qsizetype\)'),
      **{method.upper():('QByteArray',re.escape(method)+r'\(const char\*\)') for method in ('append','prepend','push_back','push_front')},
      'CBOR_CHUNK':('QCborStreamReader',r'readStringChunk\(char\*,qsizetype\)'),
      'MKDIR':('QDir',r'mkdir\(QString\)const'),'MKPATH':('QDir',r'mkpath\(QString\)const'),
      'GLYPHS_SNAPSHOT':('QGlyphRun',r'setRawData\(.*'),
      'IPV6_NEW':('QHostAddress',r'QHostAddress\(const quint8\*\)'),
      'IPV6_SET':('QHostAddress',r'setAddress\(const quint8\*\)'),
      'IMAGE_READ':('QImageReader',r'read\(QImage\*\)'),
      **{method.upper():('QLocale',re.escape(method)+r'\(QString,bool\*\)const') for method in
         ('toDouble','toFloat','toInt','toLong','toLongLong','toShort','toUInt','toULongLong','toUShort')},
      'MATRIX_CONST':('QMatrix4x4',r'constData\(\)const'),
      'MATRIX_SMALL_CONST':('QMatrix3x3',r'constData\(\)const'),
      **{'BORDER_'+kind.upper():('QOpenGLTexture',r'borderColor\('+kind+r'\*\)const') for kind in ('float','int','uint')},
      'POLYGON':('QPolygon',r'QPolygon\(int,const int\*\)'),
      'QUATERNION_OUTPUTS':('QQuaternion',r'getAxisAndAngle\(float\*,float\*,float\*,float\*\)const'),
      'RANDOM_RANGE':('QRandomGenerator',r'generate\(quint32\*,quint32\*\)'),
      'FONT_GLYPHS':('QRawFont',r'glyphIndexesForChars\(.*'),
      'FONT_ADVANCES':('QRawFont',r'advancesForGlyphIndexes\(const quint32\*,QPointF\*,int\)const'),
      'FONT_ADVANCES_FLAGS':('QRawFont',r'advancesForGlyphIndexes\(const quint32\*,QPointF\*,int,QFlags.*'),
      'LINE_CURSOR':('QTextLine',r'cursorToX\(int\*,QTextLine::Edge\)const'),
      'THREAD_ID':('QThread',r'currentThreadId\(\)'),
      'TRANSFORM':('QTransform',r'map\(int,int,int\*,int\*\)const'),
      'UDP_SEND':('QUdpSocket',r'writeDatagram\(const char\*,qint64,QHostAddress,quint16\)'),
      'BITS':('QBitArray',r'bits\(\)const'),
      'BOUNDARY_RAW':('QTextBoundaryFinder',r'QTextBoundaryFinder\(QTextBoundaryFinder::BoundaryType,const QChar\*,qsizetype,uchar\*,qsizetype\)'),
      'BOUNDARY_COPY':('QTextBoundaryFinder',r'QTextBoundaryFinder\(QTextBoundaryFinder\)'),
      'BOUNDARY_ASSIGN':('QTextBoundaryFinder',r'operator=\(QTextBoundaryFinder\)'),
      'BOUNDARY_SWAP':('QTextBoundaryFinder',r'swap\(QTextBoundaryFinder&\)'),
    }
    defines=[];wrong=[]
    for name,(owner,pattern) in specs.items():
        found=[m for m in metadata['operations'] if m['owner']==owner and re.fullmatch(pattern,m['signature'])]
        if len(found)!=1:wrong.append(f'{name}: {len(found)} operations');continue
        defines.append(f'#define OP_{name} bqt_op_{found[0]["operation"]}')
    if wrong:raise RuntimeError('Expected one generated operation each: '+'; '.join(wrong))
    defines += [f'#define TYPE_{name} {identifier}' for name,identifier in metadata['ids'].items() if re.fullmatch(r'[a-zA-Z_]\w*',name)]
    config=work/'fixture-config.h';config.write_text('\n'.join(defines)+'\n')
    fixture=ROOT/'examples/qt612/next-conversions-native.cpp';exe=work/'native'
    cmd=[x for x in compiler_flags(args.qt_root,'clang++-19',metadata['modules']) if x not in ('-O1','-DNDEBUG')]+['-O0','-ferror-limit=12',
      '-DBQT_GENERATED_WRAPPERS="'+str(work/'wrappers.cpp')+'"','-include',str(config),str(fixture),
      '-L'+str(args.qt_root/'lib'),'-Wl,-rpath,'+str(args.qt_root/'lib'),
      *['-lQt6'+m[2:] for m in reversed(metadata['modules'])],'-pthread','-o',str(exe)]
    with (work/'native-compile.log').open('w') as log:
        result=subprocess.run(['flock','-x','/tmp/bendqt-focused-compile.lock',*cmd],stdout=log,stderr=subprocess.STDOUT,timeout=1800)
    if result.returncode:raise RuntimeError('Focused C++ failed: '+str(work/'native-compile.log'))
    env=dict(os.environ,QT_QPA_PLATFORM='wayland',XDG_RUNTIME_DIR='/mnt/wslg/runtime-dir',
             QT_PLUGIN_PATH=str(args.qt_root/'plugins'),LD_LIBRARY_PATH=str(args.qt_root/'lib'),LIBGL_ALWAYS_SOFTWARE='1')
    result=subprocess.run([str(exe)],capture_output=True,text=True,env=env,timeout=90)
    output=result.stdout+result.stderr;(work/'native-run.log').write_text(output)
    if result.returncode or 'QT612_NEXT_CONVERSIONS_NATIVE_OK' not in output:raise RuntimeError('Native execution failed: '+output)
    (work/'receipt.json').write_text(json.dumps({'complete':True,'output':output,'bend_check':bend_check,
       'wrappers_sha256':hashlib.sha256((work/'wrappers.cpp').read_bytes()).hexdigest(),
       'fixture_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest()},indent=2))
    print(output,flush=True)

if __name__=='__main__':main()
