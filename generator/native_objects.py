"""Identity and destruction traits for extracted non-QObject object types.

Selection follows upstream type metadata. The traits preserve pointer offsets
across multiple inheritance; they never reinterpret a base pointer as a derived
object. Native ownership transfer is a separate runtime/lifetime policy.
"""
import json
import hashlib
from pathlib import Path
from backend import command, toolchain_flags, versioned_include_paths


def refine_traits(api, qt, modules, work, cxx):
    """Check C++ copy/move availability; Shiboken's copyable flag is optimistic.

    This maintainer-only program instantiates traits, not Qt objects, and does
    not require linking a Qt library. Its measured results are emitted into the
    inventory so exclusions describe the actual installed 6.12 headers.
    """
    work, qt = Path(work), Path(qt)
    classes = [c for c in api['classes'] if c.get('generate') and not c.get('namespace')
               and not c.get('template')
               and (c.get('object') or c.get('value'))
               and not any(part in c['name'] for part in ('<', '>', 'Private'))]
    headers = work / 'headers.h'
    lines = [headers.read_text()] if headers.exists() else [f'#include <{m}/{m}>' for m in modules]
    # These public versioned classes are deliberately absent from QtOpenGL's
    # umbrella. Their names are discovered from the pinned PySide post-header.
    lines += [f'#include <QtOpenGL/{c["name"]}>' for c in classes
              if c['name'].startswith('QOpenGLFunctions_')
              and (qt / 'include/QtOpenGL' / c['name']).exists()]
    lines += ['#include <type_traits>', '#include <cstdio>']
    lines += [f'using {name} = {target};' for name, target in api['typedefs'].items()
              if any(c['name'] == name for c in classes)]
    lines += ['template<class T> struct DestructorProbe : T {',
              '    ~DestructorProbe();',
              '    template<class U> static auto test(int) -> decltype(std::declval<DestructorProbe<U>&>().U::~U(), std::true_type{});',
              '    template<class> static auto test(...) -> std::false_type;',
              '    static constexpr bool value = decltype(test<T>(0))::value;', '};',
              'template<class T, bool Allowed> struct DerivedDestructible : std::false_type {};',
              'template<class T> struct DerivedDestructible<T, true> : std::bool_constant<DestructorProbe<T>::value> {};',
              'int main() {']
    for c in classes:
        name = c['name']
        final_destructor = any(f.get('destructor') and f.get('final_cpp') for f in c['functions'])
        derive = f'!std::is_final_v<{name}>' if not final_destructor else 'false'
        lines += [f'  std::printf("%s %d %d %d %d %d %d %d %d %d %d %d %d\\n", {json.dumps(name)}, '
                  f'int(std::is_copy_constructible_v<{name}>), int(std::is_move_constructible_v<{name}>), '
                  f'int(std::is_abstract_v<{name}>), int(std::is_destructible_v<{name}>), '
                  f'int(std::has_virtual_destructor_v<{name}>), int(std::is_final_v<{name}>), '
                  f'int(DerivedDestructible<{name}, {derive}>::value), int(std::is_copy_assignable_v<{name}>), '
                  f'int(std::is_nothrow_move_assignable_v<{name}>), int(std::is_nothrow_move_constructible_v<{name}>), '
                  f'int(std::is_default_constructible_v<{name}>), int(QMetaTypeId2<{name}>::Defined));']
    lines += ['}']
    source = work / 'native-traits.cpp'
    program = work / 'native-traits'
    receipt = work / 'native-traits.json'
    stamp = work / 'native-traits-source.sha256'
    content = '\n'.join(lines) + '\n'
    digest = hashlib.sha256('\0'.join([content, cxx, *toolchain_flags()]).encode()).hexdigest()
    cached = (source.exists() and source.read_text() == content and program.exists()
              and receipt.exists() and stamp.exists() and stamp.read_text() == digest)
    if not cached:
        source.write_text(content)
        command([cxx, *toolchain_flags(), '-std=c++17', '-DQT_NO_VERSION_TAGGING', '-Wno-deprecated-declarations',
                 '-I' + str(qt / 'include'), '-I' + str(qt / 'mkspecs/linux-g++'),
                 *['-I' + str(qt / 'include' / m) for m in modules],
                 *['-I' + str(path) for path in versioned_include_paths(qt, modules)], source, '-o', program])
        output = command([program]).stdout
        traits = {name: dict(zip(('copyable', 'movable', 'abstract', 'public_destructor', 'virtual_destructor', 'final_cpp', 'derived_destructible', 'native_copy_assignable', 'native_nothrow_move_assignable', 'native_nothrow_move_constructible', 'native_default_constructible', 'qt_metatype_defined'),
                                (bool(int(bit)) for bit in bits)))
                  for name, *bits in (line.split() for line in output.splitlines())}
        receipt.write_text(json.dumps(traits, indent=2, sort_keys=True) + '\n')
        stamp.write_text(digest)
    else:
        traits = json.loads(receipt.read_text())
    for c in classes:
        measured = traits[c['name']]
        c['native_copyable'], c['native_movable'] = measured['copyable'], measured['movable']
        c.update(measured)
    return traits


def saved_traits(work):
    """The traits a generation measured for the classes of work/api.json.

    Traits are measured per native group. Groups with separate headers have
    their own extraction, whose classes can share names with the primary one
    (QtCharts and QtGraphs both declare QLineSeries), so only the groups
    extracted with api.json contribute.
    """
    work = Path(work)
    traits = {}
    for group in json.loads((work / 'module-plan.json').read_text()):
        if not group.get('separate_headers'):
            for name, value in json.loads((work / 'modules' / group['name'] / 'native-traits.json').read_text()).items():
                traits.setdefault(name, value)
    return traits


def install(classes, selected, excluded):
    for name, c in classes.items():
        noncopy_value = c.get('value') and not c.get('copyable')
        borrow_only = not c.get('public_destructor')
        if not (c.get('object') or noncopy_value or (borrow_only and c.get('value'))):
            continue
        if (not c.get('generate') or c.get('namespace') or c.get('template')
                or any(part in name for part in ('<', '>', 'Private'))):
            continue
        if c.get('qobject') and not borrow_only:
            continue
        c['borrow_only'] = borrow_only
        c['native_object'] = not c.get('qobject')
        if noncopy_value or borrow_only:
            c.update(object=True, value=False)
        c['derived_constructor'] = bool(borrow_only and c.get('derived_destructible') and not c.get('final_cpp'))
        c['native_observable'] = bool((not borrow_only or c['derived_constructor'])
                                      and c.get('virtual_destructor') and not c.get('final_cpp'))
        if name not in selected:
            selected.append(name)
    selected.sort()
    excluded[:] = [item for item in excluded if item['class'] not in selected]


def constructor(g, name, arguments):
    base = g.classes[name].get('convenience_base_cpp', name)
    typ = f'NativeTracked<{base}>' if g.classes[name].get('native_observable') else base
    expression = f'new {typ}({", ".join(arguments)})'
    # own<T> must see the extracted type (and its traits), not the wrapper's
    # private implementation type. T has a virtual destructor in this branch.
    return f'static_cast<{name} *>({expression})' if typ != name else expression


def construct_owned(g, name, arguments, function=None):
    import convenience_apis
    arguments = convenience_apis.constructor_arguments(function, arguments)
    if g.classes[name].get('derived_constructor') or (function and function.get('protected')):
        wrapper = 'NativeTracked' if g.classes[name].get('virtual_destructor') else 'NativeConstructed'
        return f'own_derived<{name}>(r, new {wrapper}<{name}>({", ".join(arguments)}), {g.ids[name]})'
    return f'own(r, {constructor(g, name, arguments)}, {g.ids[name]})'


def traits(g):
    from representations import aliases
    lines = [
        aliases(g, inside=True),
        'template<class Source, class Target> static void *native_base_cast(void *value) {',
        '    if constexpr (std::is_convertible_v<Source *, Target *>)',
        '        return static_cast<Target *>(static_cast<Source *>(value));',
        '    return nullptr;',
        '}',
    ]
    for name in g.selected:
        c = g.classes[name]
        bases = g.all_bases(name)
        native_object = bool(c.get('native_object'))
        if not native_object and not any(g.classes[b].get('native_object') for b in bases):
            continue
        lines += [f'template<> struct NativeTraits<{name}> {{',
                  f'    static constexpr bool object = {str(native_object).lower()};',
                  f'    static constexpr bool observable = {str(bool(c.get("native_observable") or c.get("qobject"))).lower()};',
                  '    static void *cast(void *value, uint16_t target) {',
                  '        switch (target) {']
        for target in [name] + bases:
            lines += [f'        case {g.ids[target]}: return native_base_cast<{name}, {target}>(value);']
        lines += ['        default: return nullptr;', '        }', '    }', '};']
    lines += ['static std::vector<std::pair<const void *, uint16_t>> native_pointer_aliases(const Entry &entry) {',
              '    std::vector<std::pair<const void *, uint16_t>> result;',
              '    if (!entry.cast) return result;', '    switch (entry.type) {']
    for name in g.selected:
        aliases = [target for target in [name, *g.all_bases(name)] if g.classes[target].get('native_object')]
        if not aliases:
            continue
        lines += [f'    case {g.ids[name]}:']
        for target in aliases:
            lines += [f'        if (auto *value = entry.cast(entry.value, {g.ids[target]})) result.emplace_back(value, {g.ids[target]});']
        lines += ['        break;']
    lines += ['    default: break;', '    }', '    return result;', '}']
    return (Path(__file__).resolve().parent / 'templates/pointer_observations.cpp').read_text() + '\n' + '\n'.join(lines) + '\n'
