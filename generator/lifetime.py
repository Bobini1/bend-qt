"""Evaluate the proof-checked Bend policy for the finite native decision tables.

The evaluation and C++ translation are a tested boundary, not a native proof.
"""
import json
import itertools
import os
from pathlib import Path
import subprocess

TEMPLATE = Path(__file__).resolve().parent / 'templates/lifetime.bend'
BEND = Path.home() / '.bend/bin/bend'

# Arguments are enumerated False then True, most significant flag first.
# A nonempty set describes a numeric choice; None denotes a Boolean result.
POLICIES = (
    ('cleanup_install', 4, 'Policy.Lifetime.cleanup_install', {0, 16, 95}),
    ('release', 1, 'Policy.Lifetime.release', {0, 1}),
    ('reparent', 3, 'Policy.Lifetime.reparent', None),
    ('scoped', 2, 'Policy.Lifetime.scoped', {0, 1, 2}),
    ('collect', 3, 'Policy.Lifetime.collect', None),
    ('move', 4, 'Policy.Lifetime.move', None),
    ('incubation', 4, 'Policy.Lifetime.incubation', {0, 1, 2}),
    ('future_take', 3, 'Policy.Lifetime.future_take', {0, 11, 61}),
    ('paired_array', 3, 'Policy.Lifetime.paired_array', None),
    ('aggregate_commit', 2, 'Policy.Lifetime.aggregate_commit', {0, 1, 2}),
    ('cleanup_access', 3, 'Policy.Lifetime.cleanup_access', {0, 16, 116}),
    ('video_epoch', 3, 'Policy.Lifetime.video_epoch', {0, 116}),
    ('sampled_reply', 2, 'Policy.Lifetime.sampled_reply', {0, 22}),
)


def evaluate_tables(work, bend=BEND):
    work = Path(work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    source = work / 'lifetime-table.bend'
    relative = os.path.relpath(TEMPLATE, work).replace(os.sep, '/')
    expressions = []
    for name, arity, function, choices in POLICIES:
        for flags in itertools.product(('False{}', 'True{}'), repeat=arity):
            expression = function + '(' + ', '.join(flags) + ')'
            if choices is None:
                expression = 'Policy.Lifetime.release(' + expression + ')'
            expressions.append(expression)
    source.write_text('import Base\nimport ' + relative + ' as Policy\n\n'
                      'def main() -> List<&2, U32>:\n  '
                      + ' <> '.join(expressions + ['Nil{}']) + '\n')
    result = subprocess.run([str(bend), str(source)], text=True, capture_output=True,
                            cwd=work, timeout=120)
    if result.returncode:
        raise RuntimeError('Cannot evaluate the Bend lifetime policy:\n'
                           + result.stdout + result.stderr)
    values = json.loads(result.stdout)
    expected = sum(1 << arity for _, arity, _, _ in POLICIES)
    if len(values) != expected:
        raise RuntimeError(f'The lifetime policies did not produce {expected} decisions')
    tables, offset = {}, 0
    for name, arity, function, choices in POLICIES:
        decisions = values[offset:offset + (1 << arity)]
        allowed = {0, 1} if choices is None else choices
        if any(type(v) is not int or v not in allowed for v in decisions):
            raise RuntimeError(f'Invalid native decision from {function}: {decisions}')
        tables[name] = decisions
        offset += 1 << arity
    return tables


def cpp_tables(tables):
    lines = ['// Evaluated from generator/templates/lifetime.bend; do not edit.']
    for name, arity, function, choices in POLICIES:
        values = tables[name]
        choice = choices is not None and name != 'release'
        typ = 'unsigned char' if choice else 'bool'
        contents = [str(v) if choice else 'true' if v else 'false' for v in values]
        lines.append(f'static constexpr {typ} lifetime_{name}[{len(values)}] = {{'
                     + ', '.join(contents) + '};')
    return '\n'.join(lines) + '\n'
