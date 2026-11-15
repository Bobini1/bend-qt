"""Native duplex QIODevice helper from the pinned PySide binding scope."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = 'QtCoreHelper::QIOPipe'


def discover(root, modules, work):
    source = Path(root) / 'qiopipe.h'
    implementation = Path(root) / 'QtCore/glue/qiopipe.cpp'
    result = []
    if 'QtCore' in modules and source.is_file() and implementation.is_file():
        text = source.read_text()
        if 'class QIOPipe : public QObject' not in text or 'bool open(QIODeviceBase::OpenMode mode)' not in text:
            raise ValueError('The pinned QIOPipe contract changed')
        result.append(dict(name=NAME, source='qiopipe.h', implementation='QtCore/glue/qiopipe.cpp',
            source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            implementation_sha256=hashlib.sha256(implementation.read_bytes()).hexdigest()))
    (Path(work) / 'qio-pipe.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def header(specifications):
    return (HERE / 'templates/qio_pipe.h').read_text() if specifications else ''


def restore(api, work, *, require_complete=True):
    path = Path(work) / 'qio-pipe.json'
    result = json.loads(path.read_text()) if path.exists() else []
    if result and not any(c['name'] == NAME for c in api['classes']):
        if require_complete:
            raise ValueError('The pinned QIOPipe helper was not extracted')
        result = []
    api['qio_pipe'] = result


def selected(g):
    return g.api.get('qio_pipe', []) if NAME in g.ids else []


def implementation(g):
    return (HERE / 'templates/qio_pipe.cpp').read_text() if selected(g) else ''


def before_result(g, m):
    f = m['function']
    if (f['declaring_class'], f['name']) in {(NAME, 'end1'), (NAME, 'end2')}:
        return [f'if (returned) register_native_borrow(r, returned, {g.ids["QIODevice"]}, r->self);',
                'if (r->error) return true;']
    return []


def inventory(g):
    return [dict(s, implementation='Native duplex sequential QIODevice endpoints; synchronous Qt readyRead/bytesWritten',
        lifetime='Pipe owns both parentless endpoints; views observe deletion and require their pipe to remain alive') for s in selected(g)]
