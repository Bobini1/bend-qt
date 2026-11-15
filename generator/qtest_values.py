"""Safe QtTest variadic text and checked native data-table access.

The data-table inspection uses QtTest's explicitly private 6.12 headers. Only
these operations belong to the exact-version payload, not ordinary QtTest APIs.
"""
from pathlib import Path

PRIVATE = {'addColumnInternal', 'qElementData', 'qGlobalData'}


def handles(f):
    return f['declaring_class'] == 'QTest' and f['name'] in PRIVATE | {'formatString'}


def string_type():
    return dict(kind='string', name='QString', cpp='QString', bend='String', raw='String')


def adapt(g, f):
    if not handles(f):
        return None
    if f['name'] == 'formatString':
        return string_type()
    if f['name'] != 'addColumnInternal':
        import meta_storage
        return meta_storage.handle()
    return None


def parameters(g, f):
    if not handles(f):
        return None
    if f['name'] == 'formatString':
        source = dict(name='QString', cpp='QString', const=False, pointers=0, reference=0,
                      container=False, enum=False, flags=False, instantiations=[])
        strings = g.type(dict(source, name='QList', cpp='QList<QString>', container=True, instantiations=[source]))
        args = [string_type(), string_type(), strings]
        f['adaptation'] = 'Variadic terminated strings become an exact List<String>; the native count is derived, never supplied independently.'
    else:
        import abi_cohorts
        abi_cohorts.register_exact(g, 'qt_test_private_',
            'QtTest data-table inspection uses private Qt 6.12.0 headers',
            ['QTestTable::', 'QTestResult::currentTestData', 'QTestResult::currentGlobalTestData'])
        args = [string_type() if a['type']['pointers'] else g.type(a['type']) for a in f['arguments']]
        f['adaptation'] = 'Checked QtTest data session; exact-version private metadata; native data copied into owning MetaStorage.'
    return args, [dict(type=t, source=i, input=i, output=False, mutable=False) for i, t in enumerate(args)], []


def method_case(g, m):
    f = m['function']
    if not handles(f):
        return None
    lines = ['NativeCallScope call_scope;']
    values = []
    for i, typ in enumerate(m['args']):
        code, expr = g.argument(typ, i)
        lines += code
        lines += [f'auto &&qt_test_argument_{i} = {expr};']
        values.append(f'qt_test_argument_{i}')
    lines += ['if (r->error) return true;']
    if f['name'] == 'formatString':
        lines += [f'auto value = qt_test_format(r, {", ".join(values)});', 'if (r->error) return true;']
        lines += g.store_result(m['return'], 'value')
    elif f['name'] == 'addColumnInternal':
        lines += [f'qt_test_private_add_column(r, {", ".join(values)});']
    else:
        global_row = str(f['name'] == 'qGlobalData').lower()
        lines += [f'r->result.word = qt_test_private_data(r, {values[0]}, {values[1]}, {global_row});',
                  'r->result.owned_handle = r->result.word;']
    return lines + ['return true;']


def includes(g):
    if 'QtTest' not in g.profile['qt_modules']:
        return ''
    return '''#ifndef BQT_HAS_RHI
#define BQT_HAS_RHI 1
#endif
#ifndef BQT_HAS_EXACT_QT
#define BQT_HAS_EXACT_QT BQT_HAS_RHI
#endif
#if BQT_HAS_EXACT_QT
#include <private/qtesttable_p.h>
#include <private/qtestresult_p.h>
#endif
'''


def cpp(g):
    if 'QtTest' not in g.profile['qt_modules']:
        return ''
    import abi_cohorts
    cases = []
    for name in g.selected:
        cls = g.classes[name]
        if (not cls.get('qt_metatype_defined') or not cls.get('copyable')
                or cls.get('object') or not cls.get('public_destructor') or cls.get('adapter')):
            continue
        body = f'''if (!source.word && type == QMetaType::fromType<{name}>()) {{
        source.word = own(r, new {name}(*static_cast<const {name} *>(data)), {g.ids[name]});
        source.owned_handle = source.word;
    }}'''
        if abi_cohorts.required(g, body):
            body = '#if BQT_HAS_RHI\n' + body + '\n#endif'
        cases.append(body)
    return (Path(__file__).parent / 'templates/qtest_values.cpp').read_text().replace('@COPY_CASES@', '\n'.join(cases))
