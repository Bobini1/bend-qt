"""Typed child lookup: Bend adapters for QObject::findChild and findChildren.

Qt declares both as member templates, `root->findChild<T *>(name, options)`,
so the extractor has no concrete signature to bind. PySide adds Python-only
methods taking a type object. Bend has no type objects, so every selected
QObject class T gets static entries in its own namespace instead:

* `T.findIn(root, name) -> Maybe(T)`: the first T below `root`;
* `T.findAllIn(root, name) -> List(T)`: every T below `root`;
* `T.findAllMatchingIn(root, pattern) -> List(T)`: every T whose object name
  matches a QRegularExpression.

The search is recursive, as Qt's default FindChildrenRecursively is. The With
variants accept Qt::FindChildOptions, including FindDirectChildrenOnly. An empty
name matches every object, as an omitted name does in Qt. Results are
borrowed handles like `QObject.children`; ownership does not change. These
are ordinary generated entries: overload naming, the name lock, conversions,
thread checks and coverage apply unchanged. Only the native call expression
comes from `native_call`.
"""

PYSIDE = ('findChild(', 'findChildren(')


def _type(cpp, name, *, pointers=0, reference=0, const=False, container=False, instantiations=()):
    return dict(array=False, const=const, container=container, cpp=cpp, enum=False, flags=False,
                instantiations=list(instantiations), name=name, pointers=pointers, reference=reference)


def _argument(name, t):
    return dict(array=False, default='', name=name, native_default='', removed=False, type=t)


def _function(owner, name, arguments, result, native_call, comment, source):
    signature = name + '(' + ','.join(t['cpp'].replace(' ', '') for _, t in arguments) + ')'
    return dict(abstract=False, arguments=[_argument(n, t) for n, t in arguments], const=False,
                constructor=False, copy_constructor=False, declaring_class=owner, deprecated=False,
                destructor=False, final_cpp=False, implementing_class=owner, injected_code=False,
                minimal_signature=signature, name=name, noexcept=False, operator=False, policies=[],
                private=False, protected=False, public=True, removed=False, rvalue_reference=False,
                signal=False, signature=signature, signature_modified=False, slot=False, snippets=[],
                source_file=source.get('source_file', ''), source_line=source.get('source_line', 0),
                source_signatures=[], static=True, user_added=False, virtual=False,
                native_call=native_call, native_comment=comment, child_lookup=True, **{'return': result})


def install(classes, selected):
    """Add the lookup entries to every selected QObject class."""
    root = ('root', _type('const QObject &', 'QObject', const=True, reference=1))
    text = ('name', _type('QAnyStringView', 'QAnyStringView'))
    pattern = ('pattern', _type('const QRegularExpression &', 'QRegularExpression', const=True, reference=1))
    options = ('options', dict(_type('QFlags<Qt::FindChildOption>', 'QFlags<Qt::FindChildOption>'),
                              flags=True, enum=False))
    for name in selected:
        c = classes[name]
        if not c.get('qobject') or 'QRegularExpression' not in classes:
            continue
        element = _type(name + ' *', name, pointers=1)
        maybe = _type(f'std::optional<{name} *>', 'std::optional', container=True, instantiations=[element])
        many = _type(f'QList<{name} *>', 'QList', container=True, instantiations=[element])
        source = dict(source_file=c.get('source_file', ''), source_line=c.get('source_line', 0))
        c['functions'] = list(c['functions']) + [
            _function(name, 'findIn', [root, text], maybe, f'bqt_find_child<{name}>',
                      f'root.findChild<{name} *>(name) [empty name: any]', source),
            _function(name, 'findAllIn', [root, text], many, f'bqt_find_children<{name}>',
                      f'root.findChildren<{name} *>(name) [empty name: any]', source),
            _function(name, 'findAllMatchingIn', [root, pattern], many, f'bqt_find_children<{name}>',
                      f'root.findChildren<{name} *>(pattern)', source),
            _function(name, 'findInWith', [root, text, options], maybe, f'bqt_find_child<{name}>',
                      f'root.findChild<{name} *>(name, options) [empty name: any]', source),
            _function(name, 'findAllInWith', [root, text, options], many, f'bqt_find_children<{name}>',
                      f'root.findChildren<{name} *>(name, options) [empty name: any]', source),
            _function(name, 'findAllMatchingInWith', [root, pattern, options], many, f'bqt_find_children<{name}>',
                      f'root.findChildren<{name} *>(pattern, options)', source)]


def annotate(g):
    """Point PySide's Python-only findChild/findChildren at the adapters."""
    names = {}
    for m in g.methods:
        f = m['function']
        if f.get('child_lookup'):
            names.setdefault(f['declaring_class'], []).append(m['bend_name'])
    for excluded in g.excluded:
        if not excluded['signature'].startswith(PYSIDE):
            continue
        available = names.get(excluded['class'], [])
        for bend_name in sorted(available):
            item = dict(bend_name=bend_name, contract='typed_child_lookup',
                        reason='One typed static entry per QObject class replaces the Python type-object argument; results are borrowed handles')
            if item not in excluded.setdefault('alternatives', []):
                excluded['alternatives'].append(item)


def cpp(g):
    return r'''
// QObject::findChild/findChildren are member templates; see child_lookup.py.
// Classes without Q_OBJECT have no metaobject of their own, so they are
// matched with dynamic_cast instead of Qt's metaobject comparison.
static QAnyStringView bqt_child_name(QAnyStringView name)
{
    return name.isEmpty() ? QAnyStringView() : name;
}

template <typename T>
static std::optional<T *> bqt_find_child(const QObject &root, QAnyStringView name,
                                       Qt::FindChildOptions options = Qt::FindChildrenRecursively)
{
    T *found = nullptr;
    if constexpr (QtPrivate::HasQ_OBJECT_Macro<T>::Value) {
        found = root.findChild<T *>(bqt_child_name(name), options);
    } else {
        // Like Qt, prefer a matching direct child over every deeper match.
        for (QObject *child : root.findChildren<QObject *>(bqt_child_name(name), Qt::FindDirectChildrenOnly))
            if ((found = dynamic_cast<T *>(child))) break;
        if (!found && options.testFlag(Qt::FindChildrenRecursively)) {
            for (QObject *child : root.children()) {
                auto nested = bqt_find_child<T>(*child, name, options);
                if (nested) { found = *nested; break; }
            }
        }
    }
    return found ? std::optional<T *>(found) : std::nullopt;
}

template <typename T, typename Name>
static QList<T *> bqt_find_children(const QObject &root, const Name &name,
                                   Qt::FindChildOptions options = Qt::FindChildrenRecursively)
{
    if constexpr (QtPrivate::HasQ_OBJECT_Macro<T>::Value) {
        if constexpr (std::is_same_v<Name, QRegularExpression>) return root.findChildren<T *>(name, options);
        else return root.findChildren<T *>(bqt_child_name(name), options);
    } else {
        QList<QObject *> all;
        if constexpr (std::is_same_v<Name, QRegularExpression>) all = root.findChildren<QObject *>(name, options);
        else all = root.findChildren<QObject *>(bqt_child_name(name), options);
        QList<T *> found;
        for (QObject *child : all)
            if (auto *typed = dynamic_cast<T *>(child)) found.append(typed);
        return found;
    }
}
'''
