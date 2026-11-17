"""Native desktop URL registration with a retained, observed receiver."""
from pathlib import Path


def method_case(g, m):
    f = m['function']
    if f['declaring_class'] != 'QDesktopServices':
        return None
    if f['name'] == 'setUrlHandler':
        return ['NativeCallScope call_scope;',
            f'auto *receiver = get<QObject>(r, r->arguments[1].word, {g.ids["QObject"]}, true, false);',
            'if (r->error) return true;',
            'if (std::memchr(r->arguments[2].text, 0, r->arguments[2].size)) return fail(r, EINVAL, "URL method contains an embedded NUL");',
            'set_url_handler(r, QString::fromUtf8(r->arguments[0].text, qsizetype(r->arguments[0].size)), receiver, r->arguments[1].word, QByteArray(r->arguments[2].text, qsizetype(r->arguments[2].size)));',
            'return true;']
    if f['name'] == 'unsetUrlHandler':
        return ['unset_url_handler(QString::fromUtf8(r->arguments[0].text, qsizetype(r->arguments[0].size)));', 'return true;']
    return None


def cpp(g):
    if 'QDesktopServices' not in g.ids:
        return ''
    return (Path(__file__).parent / 'templates/url_handlers.cpp').read_text()


def emit(g):
    names = {m['bend_name'] for m in g.methods}
    if not {'QDesktopServices.setUrlHandler', 'QDesktopServices.unsetUrlHandler'}.issubset(names):
        return
    g.bend += [
        'def QDesktopServices.withUrlHandler(-A: Type, +scheme: String, receiver: QObject, method: String, body: Action(A)) -> Action(A):',
        '  Action.bind(Unit, A, QDesktopServices.setUrlHandler(scheme, receiver, method),',
        '    unit => Action.finally(A, body, QDesktopServices.unsetUrlHandler(scheme)))', '']
