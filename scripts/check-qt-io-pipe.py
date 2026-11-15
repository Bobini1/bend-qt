#!/usr/bin/env python3
"""Compile the exact native QIOPipe implementation and exercise Qt signals."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CONTROL = r'''
#include "pipe.h"
#include <QtCore/QCoreApplication>
#include <cassert>
int main(int argc,char **argv) {
    QCoreApplication app(argc,argv);
    auto pipe=std::make_unique<QtCoreHelper::QIOPipe>();
    assert(pipe->metaObject()->className()==QByteArray("QtCoreHelper::QIOPipe"));
    QPointer<QIODevice> first=pipe->end1(),second=pipe->end2();
    assert(first&&second&&!first->parent()&&!second->parent());
    assert(pipe->open(QIODevice::ReadWrite));
    int reads=0,writes=0; qint64 written=0;
    QObject::connect(second,&QIODevice::readyRead,[&]{++reads;});
    QObject::connect(first,&QIODevice::bytesWritten,[&](qint64 n){++writes;written+=n;});
    QByteArray bytes("a\0b",3);
    assert(first->write(bytes)==3&&reads==1&&writes==1&&written==3);
    assert(second->bytesAvailable()==3&&second->read(1)==QByteArray("a"));
    assert(second->readAll()==QByteArray("\0b",2)&&second->bytesAvailable()==0);
    assert(second->write("reply")==5&&first->readAll()==QByteArray("reply"));
    assert(first->isSequential()&&second->isSequential());
    pipe.reset();assert(!first&&!second);
    QtCoreHelper::QIOPipe oneWay;
    assert(oneWay.open(QIODevice::WriteOnly));
    assert(oneWay.end1()->isWritable()&&!oneWay.end1()->isReadable());
    assert(oneWay.end2()->isReadable()&&!oneWay.end2()->isWritable());
    assert(oneWay.end1()->write("one")==3&&oneWay.end2()->readAll()==QByteArray("one"));
    QtCoreHelper::QIOPipe deletedEnd;
    assert(deletedEnd.open(QIODevice::ReadWrite));
    delete deletedEnd.end2();assert(!deletedEnd.end2());
    assert(deletedEnd.end1()->write("gone")==-1);
    QtCoreHelper::QIOPipe reentrant;
    assert(reentrant.open(QIODevice::ReadWrite));
    QObject::connect(reentrant.end1(),&QIODevice::bytesWritten,[&](qint64){delete reentrant.end2();});
    assert(reentrant.end1()->write("safe")==4&&!reentrant.end2());
    puts("QT612_IO_PIPE_NATIVE_OK duplex=1 signals=1 binary=1 sequential=1 modes=1 endpoint_lifetime=1 reentrant_delete=1");
}
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,default=ROOT/'build/io-pipe-native')
    parser.add_argument('--qt-root',type=Path,default=Path.home()/'.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    parser.add_argument('--cxx',default='clang++-19')
    parser.add_argument('--sanitize',action='store_true')
    args=parser.parse_args();args.work.mkdir(parents=True,exist_ok=True)
    header=ROOT/'generator/templates/qio_pipe.h';implementation=ROOT/'generator/templates/qio_pipe.cpp'
    (args.work/'pipe.h').write_bytes(header.read_bytes())
    (args.work/'pipe.cpp').write_text('#include "pipe.h"\n'+implementation.read_text())
    (args.work/'main.cpp').write_text(CONTROL)
    qt=args.qt_root
    commands=[
        [str(qt/'libexec/moc'),str(args.work/'pipe.h'),'-o',str(args.work/'moc.cpp')],
        [args.cxx,'-std=c++17','-O1','-fPIC',str(args.work/'pipe.cpp'),str(args.work/'moc.cpp'),str(args.work/'main.cpp'),
            '-I'+str(qt/'include'),'-I'+str(qt/'include/QtCore'),'-L'+str(qt/'lib'),'-Wl,-rpath,'+str(qt/'lib'),'-lQt6Core','-o',str(args.work/'control')]]
    if args.sanitize:commands[-1]+= ['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    log=[]
    for command in commands:
        result=subprocess.run(command,capture_output=True,text=True)
        log.append(result.stdout+result.stderr);(args.work/'compile.log').write_text(''.join(log))
        if result.returncode:raise RuntimeError('QIOPipe compile failed; see '+str(args.work/'compile.log'))
    env=dict(os.environ,LD_LIBRARY_PATH=str(qt/'lib'))
    if args.sanitize:env['ASAN_OPTIONS']='detect_leaks=0'
    result=subprocess.run([str(args.work/'control')],capture_output=True,text=True,env=env)
    (args.work/'runtime.log').write_text(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError('QIOPipe runtime failed; see '+str(args.work/'runtime.log'))
    receipt=dict(passed=True,sanitized=args.sanitize,header_sha256=hashlib.sha256(header.read_bytes()).hexdigest(),
        implementation_sha256=hashlib.sha256(implementation.read_bytes()).hexdigest(),native_output=result.stdout.strip())
    (args.work/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(result.stdout,end='')


if __name__=='__main__':main()
