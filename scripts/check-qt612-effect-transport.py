#!/usr/bin/env python3
"""Exercise pooled effects, handlers, malformed layouts and actual local Hub publication."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'generator'))
from generate import Generator
from backend import compile_backend
import effect_transport
import signals


def raw_codec_program(package):
    """Resolve private transport details from this package, never fixed IDs."""
    source = (package / 'qt.bend').read_text()
    fixture = (ROOT / 'scripts/fixtures/raw-codecs.bend').read_text()
    operations = {}
    for prefix, public, expected_raw, expected_self in (
            ('BYTE', 'QByteArray.fromBytes', 'raw_Qt_v_to_word', '0'),
            ('PAIR', 'QUrlQuery.setQueryItems', 'raw_Qt_v_to_unit', 'QUrlQuery.word(self)')):
        declaration = re.search(r'^def ' + re.escape(public) + r'\(', source, re.M)
        if not declaration:
            raise RuntimeError('Raw codec control requires ' + public)
        end = source.find('\ndef ', declaration.start() + 1)
        body = source[declaration.start():end if end >= 0 else len(source)]
        calls = re.findall(r'\b(raw_Qt_[A-Za-z0-9_]+)\((\d+), ([^,\n]+),', body)
        if len(calls) != 1:
            raise RuntimeError('Expected one pooled effect in ' + public)
        raw, operation, receiver = calls[0]
        allowed_raw = {expected_raw, expected_raw.replace('raw_Qt_', 'raw_Qt_base_')}
        if raw not in allowed_raw or receiver != expected_self:
            raise RuntimeError('Raw codec fixture layout changed for ' + public)
        operations[public] = dict(raw=raw, operation=int(operation))
        for key, value in (('RAW', raw), ('OPERATION', operation)):
            fixture = fixture.replace('@' + prefix + '_' + key + '@', value)
    if re.search(r'@[A-Z_]+@', fixture):
        raise RuntimeError('Unresolved raw codec fixture placeholder')
    return fixture, operations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qt-root', type=Path, default=Path.home() / '.cache/bend-qt-generator/Qt/6.12.0/gcc_64')
    parser.add_argument('--work', type=Path, default=ROOT / 'build/qt612/check/effect-transport')
    parser.add_argument('--package', type=Path, default=ROOT / 'packages/qt612',
                        help='Actual generated package for adversarial native codec controls')
    args = parser.parse_args()
    work = args.work.resolve(); work.mkdir(parents=True, exist_ok=True)
    g = Generator.__new__(Generator)
    g.api = dict(qt_headers=json.loads((args.package / 'coverage.json').read_text())['minimum_qt'])
    g.bend, g.effects = [], []
    g.types, g.selected, g.enums = {'Int32': 'scalar', 'UInt64': 'wide'}, [], {}
    g.flag_types = set()
    g.argument_capacity = 8
    # This synthetic payload has no object registry. Resource lifetimes are
    # exercised by action-scopes against the real native runtime.
    g.bend += ['def run(-A: Type, action: Action(A)) -> IO(Result<&1, &1, U32 & String, A>):',
               '  action(0)', '']
    word = dict(kind='u32', bend='U32', raw='U32')
    unit = dict(kind='void', bend='Unit', raw='Unit')
    text = dict(kind='string', bend='String', raw='String')
    wide = dict(kind='u64', bend='UInt64', raw='U32 & U32')
    wire = dict(kind='wire', bend='Wire', raw='Wire', codec='TransportWire')
    g.bend += ['def TransportWire.encode(value: Wire) -> Wire:', '  value', '',
               'def TransportWire.wrap(value: Result<&1, &1, U32 & String, Wire>) -> Result<&1, &1, U32 & String, Wire>:', '  value', '']
    for public, params, result, operation, options in [
        ('Probe.add', [('value', word)], word, 10, {}),
        ('Probe.addAlias', [('value', word)], word, 10, {'alias': 'Probe.add'}),
        ('Probe.addTwo', [('value', word)], word, 11, {}),
        ('Probe.text', [('value', text)], text, 12, {}),
        ('Probe.wide', [('value', wide)], wide, 13, {}),
        ('Probe.wire', [('value', wire)], wire, 14, {}),
        ('Probe.receiver', [('self', word)], word, 15, {'has_self': True}),
        ('Probe.unit', [], unit, 16, {}),
        ('Probe.calls', [], word, 17, {}),
        ('Probe.textLength', [('value', text)], word, 18, {}),
        ('Probe.store', [('value', word)], unit, 21, {}),
        ('Probe.stored', [], word, 22, {}),
    ]:
        g.emit_effect(public, params, result, operation, **options)
    try:
        g.emit_effect('Probe.invalidAlias', [('value', text)], text, 10, alias='Probe.add')
    except ValueError as error:
        if 'Conflicting raw layouts' not in str(error): raise
    else:
        raise AssertionError('Conflicting alias layout was accepted')
    # The failed duplicate uses an existing layout and adds no definition.
    # A handler Qt calls with one word; it answers nothing.
    g.bend.append((ROOT / 'generator/templates/handlers.bend').read_text().removeprefix('import Base\n\n'))
    g.bend += ['def ProbeHandler.decode(value: Wire) -> Maybe<&2, U32>:', '  match value:',
               '    case WireScalar{word, 0}: Some{word}', '    case _: None{}', '']
    signals.invoke_value(g, 'ProbeHandler', 'U32', 'ProbeHandler.decode')
    g.emit_effect('Probe.handled', [('handler', effect_transport.handler('S -> U32 -> Action(Unit)', 'ProbeHandler.invoke')),
                                    ('value', word)], unit, 20)
    abi = (ROOT / 'generator/templates/abi.h').read_text().replace('@ARGUMENT_CAPACITY@', str(g.argument_capacity))
    native = '''#include <QtCore/QString>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <string>
@ABI@
static uint32_t calls, stored;
static const BqtHost *host;
static std::string failure;
static BqtValue copy_value(const BqtValue &source) {
    BqtValue value = source;
    if (source.text) { value.text = static_cast<char *>(std::malloc(source.size + 1)); std::memcpy(value.text, source.text, source.size); value.text[source.size] = 0; }
    if (source.count) { value.items = static_cast<BqtValue *>(std::calloc(source.count, sizeof(BqtValue))); for (size_t i = 0; i < source.count; ++i) value.items[i] = copy_value(source.items[i]); }
    return value;
}
static void returned_text(BqtRequest *r, const QString &text) {
    auto bytes = text.toUtf8(); r->result.tag = 1; r->result.size = size_t(bytes.size());
    r->result.text = static_cast<char *>(std::malloc(r->result.size + 1));
    std::memcpy(r->result.text, bytes.constData(), r->result.size + 1);
}
// Runs the Bend handler at once, as Qt runs a slot. Qt keeps a handler only
// when the call succeeds; otherwise the Bend side releases it.
static void handled(BqtRequest *r) {
    BqtValue items[2] = {};
    items[1].word = r->arguments[1].word;
    BqtValue request = {};
    request.tag = 2; request.items = items; request.count = 2;
    const char *message = nullptr;
    int status = host->invoke(r->arguments[0].word, &request, &message);
    if (status == BQT_HANDLER_DONE) { host->release(r->arguments[0].word); return; }
    failure = status == BQT_HANDLER_WAITS ? "A handler waited" : message ? message : "";
    r->error = status == BQT_HANDLER_WAITS ? 11 : status; r->message = failure.c_str();
}
extern "C" __attribute__((visibility("default"))) void bqt_abi_call(BqtRequest *r) {
    if (r->operation != 17) ++calls;
    switch (r->operation) {
    case 10: case 11: r->result.word = r->arguments[0].word + (r->operation == 10 ? 1 : 2); break;
    case 12: returned_text(r, QString::fromUtf8(r->arguments[0].text, qsizetype(r->arguments[0].size)) + QStringLiteral(" λ")); break;
    case 13: r->result.word = r->arguments[0].high; r->result.high = r->arguments[0].word; break;
    case 14: r->result = copy_value(r->arguments[0]); break;
    case 15: r->result.word = r->self; break;
    case 16: break;
    case 17: r->result.word = calls; break;
    case 18: r->result.word = QString::fromUtf8(r->arguments[0].text, qsizetype(r->arguments[0].size)).size(); break;
    case 20: handled(r); break;
    case 21: stored = r->arguments[0].word; break;
    case 22: r->result.word = stored; break;
    default: r->error = 38; r->message = "Unknown fixture operation";
    }
}
extern "C" __attribute__((visibility("default"))) const char *bqt_abi_start(const BqtHost *given) {
    host = given; return nullptr;
}
extern "C" __attribute__((visibility("default"))) int bqt_abi_stop(void) { return 0; }
'''.replace('@ABI@', abi)
    path = work / 'native.cpp'; path.write_text(native)
    payload, loader, metadata = compile_backend(path, args.qt_root, work, 'clang++-19', ['QtCore', 'QtGui', 'QtWidgets'])
    c = (ROOT / 'generator/templates/effects.c').read_text()
    for key, value in [('ABI', abi), ('ASSEMBLY', payload), ('IMPORTS', loader),
                       ('LIBRARIES', '    void *libraries[1] = {lib};'), ('EFFECTS', effect_transport.effects(g))]:
        c = c.replace('// @' + key + '@', value)
    (work / 'qt.bend').write_text(g.prelude() + '\n'.join(g.bend) + '\n')
    (work / 'qt.c').write_text(c)
    spec = importlib.util.spec_from_file_location('checks', ROOT / 'scripts/check-qt612.py')
    checks = importlib.util.module_from_spec(spec); spec.loader.exec_module(checks)
    source = (ROOT / 'scripts/fixtures/effect-transport.bend').read_text()
    receipt = checks.check_package(work, [('effect-transport', source, 'QT612_EFFECT_TRANSPORT_OK')],
        os.environ.copy(), [args.qt_root], work / 'consumer', jobs=1)
    receipt['transport'] = effect_transport.inventory(g)
    receipt['rejected_before_native'] = ['argument_kind', 'argument_count', 'return_packer',
        'unexpected_receiver', 'unknown_operation', 'excessive_wire_depth']
    receipt['handlers'] = ['state', 'nested_qt_call', 'failure_code_and_message']
    receipt['conflicting_alias_rejected_by_generator'] = True
    receipt['native_payload'] = metadata['payload']
    subprocess.run([sys.executable, ROOT / 'scripts/check-qt612-publication.py',
                    '--package', work, '--work', work / 'publication'], check=True)
    receipt['local_publication'] = json.loads((work / 'publication/receipt.json').read_text())
    codec_source, codec_operations = raw_codec_program(args.package)
    (work / 'raw-codecs.bend').write_text(codec_source)
    receipt['native_codec_controls'] = checks.check_package(args.package,
        [('raw-codecs', codec_source, 'QT612_RAW_CODECS_OK')], os.environ.copy(),
        [args.qt_root], work / 'native-codecs', jobs=1)
    receipt['native_codec_controls']['resolved_operations'] = codec_operations
    receipt['native_codec_controls']['rejected_payloads'] = ['byte_sequence_shape', 'byte_element_shape', 'pair_field_count']
    (work / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('PASS pooled effect transport: alias, scalar, text, wide, Wire, receiver, handlers, invalid layouts, native malformed codecs, local publication')


if __name__ == '__main__':
    main()
