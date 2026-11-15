#!/usr/bin/env python3
"""Check protected getter access with each pinned ApiExtractor/Qt pair."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'generator'))
from backend import compiler_flags
from protected_members import declarations,pointer_name
from qt_targets import installed_version


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qt-root',type=Path,default=Path.home()/'.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    parser.add_argument('--work',type=Path,default=ROOT/'build/protected-lvalue-getters')
    args=parser.parse_args()
    version=installed_version(args.qt_root)
    short=version.split('.')[0]+version.split('.')[1]
    api=json.loads((ROOT/('build/qt'+short)/'modules/Graphs/scoped-api.json').read_text())
    cls=next(c for c in api['classes'] if c['name']=='QValue3DAxisFormatter')
    names=('gridPositions','labelPositions','labelStrings','subGridPositions')
    methods=[next(f for f in cls['functions'] if f['name']==name and not f['const'])
             if any(f['name']==name and not f['const'] for f in cls['functions'])
             else next(f for f in cls['functions'] if f['name']==name and f['const']) for name in names]
    generator=SimpleNamespace(classes={cls['name']:cls},ids={cls['name']:1},enums={},
        methods=[dict(function=f) for f in methods])
    helpers=declarations(generator)
    checks=[]
    for method in methods:
        expected='QStringList{QStringLiteral("a"),QStringLiteral("b")}' if method['name']=='labelStrings' else 'QList<float>{1.0f,2.0f}'
        call='(base->*bendqt::BqtProtected_QValue3DAxisFormatter::'+pointer_name(method)+'())()'
        checks += ['assert(('+call+') == ('+expected+'));']*2
    source='''#include <QtGraphs/QValue3DAxisFormatter>
#include <QtCore/QCoreApplication>
#include <cassert>
namespace bendqt {
@HELPERS@
}
struct Fixture : QValue3DAxisFormatter {
    Fixture() {
        setGridPoitions({1.0f,2.0f}); setSubGridPositions({1.0f,2.0f});
        setlabelPositions({1.0f,2.0f}); setLabelStrings({QStringLiteral("a"),QStringLiteral("b")});
    }
};
int main(int argc,char **argv) {
    QCoreApplication app(argc,argv); Fixture fixture;
    QValue3DAxisFormatter *base=&fixture;
    @CHECKS@
}
'''.replace('@HELPERS@',helpers).replace('@CHECKS@','\n'.join(checks))
    work=args.work.resolve();work.mkdir(parents=True,exist_ok=True)
    path=work/'main.cpp';path.write_text(source)
    flags=[flag for flag in compiler_flags(args.qt_root,'clang++-19',['QtCore','QtGui','QtQml','QtQuick','QtGraphs']) if flag!='-DNDEBUG']
    subprocess.run([*flags,str(path),'-L'+str(args.qt_root/'lib'),'-lQt6Graphs','-lQt6Quick','-lQt6Qml','-lQt6Gui','-lQt6Core','-o',str(work/'main')],check=True)
    subprocess.run([str(work/'main')],env=dict(os.environ,LD_LIBRARY_PATH=str(args.qt_root/'lib')),check=True)
    (work/'receipt.json').write_text(json.dumps(dict(qt=version,passed=True,actual_qt_getters=4,
        repeated_reads_do_not_move=True,derived_pointer_access=True),indent=2)+'\n')
    print('QT_PROTECTED_LVALUE_GETTERS_OK qt='+version)


if __name__=='__main__': main()
