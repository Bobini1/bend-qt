#!/usr/bin/env python3
"""Exercise the generated QQmlPropertyMap provider through Qt's constructor."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
from backend import compiler_flags
from callbacks import qml_property_map_metadata
from shared_state import transform

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qt-root',type=Path,default=Path.home()/'.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    parser.add_argument('--work',type=Path,default=ROOT/'build/proxy-meta-provider-check')
    args=parser.parse_args()
    work=args.work.resolve();work.mkdir(parents=True,exist_ok=True)
    source='''#include <QtCore/QCoreApplication>
#include <QtQml/QQmlPropertyMap>
#include <QtCore/private/qmetaobjectbuilder_p.h>
#include <cassert>
#include <cstdlib>
#include <cstring>
#include "state-service.hpp"
namespace bendqt {
static thread_local const QMetaObject *runtime_construction_meta;
class Proxy final : public QQmlPropertyMap {
public:
@PROVIDER@
    Proxy() : QQmlPropertyMap(this, nullptr) {}
};
}
int main(int argc,char **argv) {
    QCoreApplication application(argc,argv);
    { bendqt::Proxy plain; plain.insert("value",42); assert(plain.value("value").toInt()==42); }
    QMetaObjectBuilder builder;
    builder.setClassName("BendDerivedPropertyMap");
    builder.setSuperClass(&QQmlPropertyMap::staticMetaObject);
    auto *meta=builder.toMetaObject();
    bendqt::runtime_construction_meta=meta;
    {
        bendqt::Proxy derived;
        assert(!bendqt::runtime_construction_meta);
        assert(std::strcmp(derived.metaObject()->className(),"BendDerivedPropertyMap")==0);
        derived.insert("value",43); assert(derived.property("value").toInt()==43);
    }
    std::free(meta);
}
'''.replace('@PROVIDER@','\n'.join(qml_property_map_metadata()))
    flags=compiler_flags(args.qt_root,'clang++-19',['QtCore','QtQml'])
    flags=[flag for flag in flags if flag!='-DNDEBUG']
    (work/'state-service.hpp').write_text('''#include <memory>
#include <new>
#include <cstring>
#define BQT_RUNTIME_THREAD_LOCAL 1
namespace bendqt {
template<class T,class Initialize>
T &runtime_shared_state_init(const char *,unsigned,Initialize initialize) {
    static thread_local std::unique_ptr<T> value;
    if (!value) {
        void *memory=::operator new(sizeof(T)); std::memset(memory,0,sizeof(T));
        initialize(memory); value.reset(static_cast<T*>(memory));
    }
    return *value;
}
}
''')
    original=work/'original.cpp';original.write_text(source)
    rewritten,facts=transform(original,flags[1:])
    if any(row['qualified'].endswith('Proxy::staticMetaObject') for row in facts):
        raise RuntimeError('The const metadata provider was moved away from its class')
    path=work/'main.cpp';path.write_text(rewritten)
    subprocess.run([*flags,str(path),'-L'+str(args.qt_root/'lib'),'-lQt6Qml','-lQt6Core','-o',str(work/'main')],check=True)
    subprocess.run([str(work/'main')],env=dict(os.environ,LD_LIBRARY_PATH=str(args.qt_root/'lib')),check=True)
    (work/'receipt.json').write_text(json.dumps(dict(passed=True,default_map=True,derived_metadata=True,
        metadata_consumed=True,dynamic_properties=True,shared_state_rewrite=True),indent=2)+'\n')
    print('QT_PROXY_META_PROVIDER_OK actual_qt_constructor=1 derived_metadata=1 dynamic_properties=1')

if __name__=='__main__': main()
