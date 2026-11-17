#!/usr/bin/env python3
"""Test a complete release package's Core exclusion and mixed chart families."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'generator'))
from qt_targets import installed_version

COMMON='''import Base
import ../../packages/qt612/qt.bend as Qt

def require(ok: Bool, message: String) -> Qt.Action(Unit):
  match ok:
    case True{}: Qt.Action.pure(Unit, Unit{})
    case False{}: Qt.Action.fail(Unit, 1, message)
'''
CORE=COMMON+'''
def object(+value: Qt.QObject) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QObject.setObjectName(value, "Core")
    name: String <- Qt.QObject.objectName(value)
    require(String.eq(name, "Core"), "Core object changed")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QObject.with(Unit, Qt.QObject.new(), value => object(value))
    count: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(count, 0), "Core object leaked")
    prefix: String <- Qt.QLibraryInfo.path(Qt.QLibraryInfo.LibraryPath.PrefixPath())
    Qt.Action.lift(Unit, IO.print("QT_DISTRIBUTION_PREFIX=" ++ prefix))
    Qt.Action.lift(Unit, IO.print("QT_DISTRIBUTION_CORE_OK"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
'''
FAMILIES=COMMON+'''
def ready() -> Qt.Signal:
  Qt.Signal.define("ready", [Qt.QLineSeries.arg(), Qt.Charts.QLineSeries.arg(), Qt.DataVisualization.QScatter3DSeries.arg()])

def received(state: Unit, modern: Qt.QLineSeries, chart: Qt.Charts.QLineSeries, data: Qt.DataVisualization.QScatter3DSeries) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QLineSeries.setName(modern, "modern")
    Qt.Charts.QLineSeries.setName(chart, "chart")
    Qt.DataVisualization.QScatter3DSeries.setName(data, "data")

def wrong_family(result: Result<&1, &1, U32 & String, String>) -> Qt.Action(Unit):
  match result:
    case Fail{(code, message)}: require(U32.is_eq(code, 22), "Wrong family error: " ++ message)
    case Done{name}: Qt.Action.fail(Unit, 1, "A Charts object was accepted as a Graphs object")

def emit(+sender: Qt.QObject, +modern: Qt.QLineSeries, +chart: Qt.Charts.QLineSeries, +data: Qt.DataVisualization.QScatter3DSeries) -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.Signal.emit(~ready(), sender, modern, chart, data)
    m: String <- Qt.QLineSeries.name(modern)
    c: String <- Qt.Charts.QLineSeries.name(chart)
    d: String <- Qt.DataVisualization.QScatter3DSeries.name(data)
    require(String.eq(m, "modern") && String.eq(c, "chart") && String.eq(d, "data"), "Typed family signal changed its objects")
    rejected: Result<&1, &1, U32 & String, String> <- Qt.Action.attempt(String, Qt.QLineSeries.name(Qt.QLineSeries{Qt.Charts.QLineSeries.word(chart)}))
    wrong_family(rejected)

def connect(+sender: Qt.QObject, modern: Qt.QLineSeries, chart: Qt.Charts.QLineSeries, data: Qt.DataVisualization.QScatter3DSeries) -> Qt.Action(Unit):
  Qt.Connection.with(Unit, Qt.Signal.connect(~ready(), ~Unit, ~received, sender, Unit{}), connection => emit(sender, modern, chart, data))

def families(modern: Qt.QLineSeries, chart: Qt.Charts.QLineSeries, data: Qt.DataVisualization.QScatter3DSeries) -> Qt.Action(Unit):
  Qt.QObject.with(Unit, Qt.QObject.newWithSignals("QtDistributionFamilies", [ready()]), sender => connect(sender, modern, chart, data))

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.QLineSeries.with(Unit, Qt.QLineSeries.new(), modern => Qt.Charts.QLineSeries.with(Unit, Qt.Charts.QLineSeries.new(), chart => Qt.DataVisualization.QScatter3DSeries.with(Unit, Qt.DataVisualization.QScatter3DSeries.new(), data => families(modern, chart, data))))
    objects: U32 <- Qt.Runtime.liveObjects()
    data: U32 <- Qt.Runtime.liveData()
    require(U32.is_eq(objects, 0) && U32.is_eq(data, 0), "Mixed families leaked handles or Bend data")
    Qt.Action.lift(Unit, IO.print("QT_DISTRIBUTION_FAMILIES_OK typed_signals=1 wrong_family_rejected=1 objects=0 data=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
'''

# Exercise the QML runtime dependency closure across fourteen modules.
QML_MODULES = ('Qt.labs.folderlistmodel', 'Qt.labs.synchronizer', 'QtCore',
    'QtMultimedia', 'QtQml', 'QtQml.Models', 'QtQuick', 'QtQuick.Controls',
    'QtQuick.Controls.Basic', 'QtQuick.Dialogs', 'QtQuick.Effects',
    'QtQuick.Layouts', 'QtQuick.Shapes', 'QtQuick.Window')
QML_IMPORTS=COMMON+'''
def imports() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
@LOADS@    +engine: Qt.QQmlEngine <- Qt.QQmlEngine.new()
    +component: Qt.QQmlComponent <- Qt.QQmlComponent.new__QQmlEngine_QObject(engine, Qt.QObject{0})
    +source: Qt.QByteArray <- Qt.QByteArray.fromUtf8(@QML@)
    +url: Qt.QUrl <- Qt.QUrl.new()
    Qt.QQmlComponent.setData(component, source, url)
    ready: Bool <- Qt.QQmlComponent.isReady(component)
    error: String <- Qt.QQmlComponent.errorString(component)
    require(ready, "QML import closure failed: " ++ error)
    +root: Qt.QObject <- Qt.QQmlComponent.create__QQmlContext(component, Qt.QQmlContext{0})
    require(U32.is_ne(Qt.QObject.word(root), 0), "QML root was not created")

def checks() -> Qt.Action(Unit):
  do Qt.Action<Unit>:
    Qt.scoped(Unit, imports())
    objects: U32 <- Qt.Runtime.liveObjects()
    require(U32.is_eq(objects, 0), "QML imports leaked handles")
    Qt.Action.lift(Unit, IO.print("QT_DISTRIBUTION_QML_IMPORTS_OK modules=14 objects=0"))

def main() -> IO(Unit):
  IO.try(Unit, Qt.run(Unit, checks()))
'''.replace('@QML@',json.dumps(''.join('import '+name+'\n' for name in QML_MODULES)+'QtObject {}'))

def encoded(source, declaration):
    match=re.search(declaration,source)
    if not match: raise ValueError('An embedded asset has no payload declaration')
    body=source[match.end():].partition(';')[0]
    result=''.join(re.findall(r'"([A-Za-z0-9+/=]+)"',body)).encode()
    if not result: raise ValueError('An embedded asset has an empty payload')
    return result

def absent(binary,payload,label):
    # A short suffix is only a search accelerator. Any hit is checked against
    # the complete encoded bytes, including the compression checksum.
    if payload[-256:] in binary and payload in binary:
        raise RuntimeError('Core retained an optional payload: '+label)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',type=Path,default=ROOT/'packages/qt612')
    parser.add_argument('--profile',type=Path,default=ROOT/'generator/qt612/profile.json')
    parser.add_argument('--qt-root',type=Path,default=Path.home()/'.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    parser.add_argument('--work',type=Path,default=ROOT/'build/qt612/distribution-package-check')
    args=parser.parse_args()
    package=args.package.resolve();work=args.work.resolve();work.mkdir(parents=True,exist_ok=True)
    coverage=json.loads((package/'coverage.json').read_text())
    profile=json.loads(args.profile.read_text())
    if coverage['minimum_qt']!=profile['minimum_qt'] or coverage['minimum_qt']!=installed_version(args.qt_root):
        raise ValueError('The package, profile and runtime must name the same Qt release')
    modules=coverage['native_payload'].get('modules')
    manifest=coverage.get('bundled_runtime')
    if not modules or not manifest: raise ValueError('A release needs selective native payloads and a bundled runtime')
    optional=[row for row in profile['native_modules'] if set(row['qt_modules']) & set(profile['qt_modules'])]
    forbidden=tuple('libQt6'+module[2:] for row in optional for module in row['qt_modules'])
    bad=[name for name in modules['base']['dependencies'] if name.startswith(forbidden)]
    if bad: raise ValueError('The full base payload depends on GPL modules: '+repr(bad))
    spec=importlib.util.spec_from_file_location('qt_package_check',ROOT/'scripts/check-qt612.py')
    checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
    # QML-only use of a separately grouped module retains it explicitly, as
    # documented; modules in the shared group need no call.
    grouped={module:row['name'] for row in optional for module in row['qt_modules']}
    loads=sorted({grouped[name.split('.')[0]] for name in QML_MODULES if name.split('.')[0] in grouped})
    qml_imports=QML_IMPORTS.replace('@LOADS@',''.join('    Qt.Modules.'+name+'.load()\n' for name in loads))
    programs=[('distribution-core',CORE,'QT_DISTRIBUTION_CORE_OK'),
              ('distribution-families',FAMILIES,'QT_DISTRIBUTION_FAMILIES_OK'),
              ('distribution-qml-imports',qml_imports,'QT_DISTRIBUTION_QML_IMPORTS_OK')]
    receipt=checker.check_package(package,programs,dict(os.environ,BENDRTS=''),[args.qt_root],work,jobs=1)
    binary=(work/'distribution-core').read_bytes()
    for row in optional:
        source=(package/('qt-'+row['name']+'.c')).read_text()
        absent(binary,encoded(source,r'\bstatic const char \w*payload\[\]\s*='),row['name'])
    base_assets=(package/'qt-runtime-module-base.c').read_text()
    omitted=[]
    for path in package.glob('qt-runtime-*.c'):
        number=path.stem.removeprefix('qt-runtime-')
        if not number.isdecimal() or 'FID(native_Runtime_piece_'+str(int(number))+')' in base_assets: continue
        absent(binary,encoded(path.read_text(),r'\bstatic const char \w+\[\]\s*='),path.name)
        omitted.append(path.name)
    label=hashlib.sha256(b'None').hexdigest()[:8]
    log=(work/('distribution-core-'+label+'.log')).read_text()
    prefix=re.search(r'^QT_DISTRIBUTION_PREFIX=(.+)$',log,re.M)
    if not prefix: raise ValueError('The Core consumer did not report its Qt prefix')
    runtime=Path(prefix[1]).resolve()
    expected={row['path'] for row in manifest['files'] if 'base' in row['modules']}
    expected.update(name for name,target in manifest['aliases'].items() if target in expected)
    actual={path.relative_to(runtime).as_posix() for path in runtime.rglob('*') if path.is_file()}
    if actual!=expected|{'.lock'}:
        raise RuntimeError('The full Core consumer extracted the wrong runtime files')
    receipt.update(verification_complete=True,qt=coverage['minimum_qt'],core_only_gpl_qt_modules=[],
        optional_native_payloads_absent=[row['name'] for row in optional],
        optional_runtime_pieces_absent=omitted,core_runtime=str(runtime),core_runtime_files=len(actual),
        qml_imports=list(QML_MODULES),
        boundary='Fresh full-package Core and mixed-family native consumers; comprehensive generator/callback validation is a separate gate',
        public_hub_publication=False)
    (work/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print('QT_DISTRIBUTION_PACKAGE_OK qt='+coverage['minimum_qt']+' core_gpl_modules=0 mixed_families=3')

if __name__=='__main__': main()
