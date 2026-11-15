#!/usr/bin/env python3
"""Check generated QAudioBuffer byte adapters with real Qt storage."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
import convenience_apis


def source():
    generator = SimpleNamespace(ids={'QAudioBuffer': 1},
        argument=lambda value, index: ([], 'r->input'),
        store_result=lambda value, expression: [f'r->output = {expression};'])
    functions = []
    for name, kind, arguments in [('read_bytes', 'audio_bytes', []), ('write_bytes', 'audio_set_bytes', [{}])]:
        method = dict(function=dict(convenience=kind, declaring_class='QAudioBuffer',
                                    static=False, const=kind=='audio_bytes'), args=arguments, **{'return': {}})
        functions.append(f'static bool {name}(BqtRequest *r) {{\n' + '\n'.join(convenience_apis.method_case(generator, method)) + '\n}\n')
    return r'''
#include <QtMultimedia/QAudioBuffer>
#include <QtMultimedia/QAudioFormat>
#include <QtCore/QByteArray>
#include <cassert>
#include <cerrno>
#include <cstdio>
#include <cstring>
struct BqtRequest { unsigned self=1; QAudioBuffer *buffer; QByteArray input, output; int error=0; };
struct NativeCallScope {};
template<class T> static T *get(BqtRequest *r,unsigned,unsigned,bool,bool) { return r->buffer; }
static bool fail(BqtRequest *r,int code,const char *) { r->error=code; return true; }
@FUNCTIONS@
int main() {
    const auto original=QByteArray::fromHex("010203");
    const auto replacement=QByteArray::fromHex("090203");
    QAudioFormat format;
    format.setSampleRate(48000); format.setChannelCount(1); format.setSampleFormat(QAudioFormat::UInt8);
    QByteArray snapshot;
    {
        QAudioBuffer buffer(original,format), copy(buffer);
        BqtRequest r; r.buffer=&buffer;
        assert(read_bytes(&r) && !r.error && r.output==original);
        snapshot=r.output;
        r.input=replacement;
        assert(write_bytes(&r) && !r.error);
        assert(read_bytes(&r) && r.output==replacement && snapshot==original);
        r.buffer=&copy;
        assert(read_bytes(&r) && r.output==original);
        r.input=QByteArray(1,char(8));
        assert(write_bytes(&r) && r.error==EINVAL);
        r.error=0;
        assert(read_bytes(&r) && !r.error && r.output==original);
    }
    assert(snapshot==original);
    QAudioBuffer empty;
    BqtRequest r; r.buffer=&empty;
    assert(read_bytes(&r) && !r.error && r.output.isEmpty());
    assert(write_bytes(&r) && !r.error);
    puts("QT612_AUDIO_BUFFER_NATIVE_BYTES_OK typed_access=1 detach=1 snapshot=1 bounds=1 empty=1");
}
'''.replace('@FUNCTIONS@', ''.join(functions))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qt-root', type=Path, default=Path.home()/'.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    parser.add_argument('--work', type=Path, default=ROOT/'build/audio-buffer-native-bytes')
    args = parser.parse_args(); args.work.mkdir(parents=True, exist_ok=True)
    code = source(); path=args.work/'main.cpp'; path.write_text(code)
    flags=['clang++-19','-std=c++17','-O1','-fPIC','-I'+str(args.qt_root/'include')]
    binary=args.work/'check'
    compiled=subprocess.run([*flags,str(path),'-L'+str(args.qt_root/'lib'),'-lQt6Multimedia','-lQt6Core','-o',str(binary)],text=True,capture_output=True)
    (args.work/'compile.log').write_text(compiled.stdout+compiled.stderr)
    if compiled.returncode: raise RuntimeError('Audio byte adapter compilation failed; see compile.log')
    tested=subprocess.run([str(binary)],env=dict(os.environ,LD_LIBRARY_PATH=str(args.qt_root/'lib')),text=True,capture_output=True)
    (args.work/'native.log').write_text(tested.stdout+tested.stderr)
    if tested.returncode: raise RuntimeError('Audio byte adapter native check failed; see native.log')
    broken=code.replace('->constData<char>()','->constData()').replace('->data<char>()','->data()')
    negative=args.work/'private-access-negative.cpp'; negative.write_text(broken)
    rejected=subprocess.run([*flags,'-fsyntax-only',str(negative)],text=True,capture_output=True)
    (args.work/'private-access-negative.log').write_text(rejected.stdout+rejected.stderr)
    assert rejected.returncode and 'private member' in rejected.stderr, 'Private access regression was not rejected'
    (args.work/'receipt.json').write_text(json.dumps(dict(passed=True,public_typed_access=True,
        detached_copy=True,owning_snapshot=True,bounds_before_mutation=True,empty_buffer=True,
        private_access_negative_control=True,generator_sha256=hashlib.sha256((ROOT/'generator/convenience_apis.py').read_bytes()).hexdigest(),
        boundary='Actual generated adapter bodies and real Qt storage with minimal handle shims; full Bend consumer remains an integration gate.'),indent=2)+'\n')
    print(tested.stdout.strip())


if __name__=='__main__':
    main()
