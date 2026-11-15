"""Recover public native defaults stripped from PySide's target signature."""
import copy


def restore_native(f):
    """Try original native declarations through all normal Bend safety gates.

    PySide removal is a target-language decision, not C++ inaccessibility.
    This does not admit an argument, result, ownership transfer or pointer:
    collect() still requires each ordinary conversion and lifetime policy.
    Native declarations must have extractor source evidence. Python additions,
    non-public declarations and source-audited Qt internals stay excluded.
    """
    from coverage_inventory import source_classification
    return (f['removed'] and f['public'] and not f['user_added']
            and not f['destructor'] and bool(f.get('source_file'))
            and bool(f.get('source_line')) and bool(f.get('source_signatures'))
            and not source_classification(f))


def normalize(f):
    owner, name = f['declaring_class'], f['name']
    permissions_tail = ((owner == 'QFile' and name == 'copy') or
                        (owner == 'QDir' and name in ('mkdir', 'mkpath')))
    if permissions_tail and any('std::optional<QFileDevice::Permissions>' in s for s in f['source_signatures']):
        if any(a['type']['name'] == 'std::optional' for a in f['arguments']):
            return f
        f = copy.deepcopy(f)
        flags = dict(name='QFlags<QFileDevice::Permission>', cpp='QFileDevice::Permissions',
                     const=False, pointers=0, reference=0, container=False, enum=False, flags=True, instantiations=[])
        optional = dict(flags, name='std::optional', cpp='std::optional<QFileDevice::Permissions>',
                        container=True, flags=False, instantiations=[flags])
        f['arguments'].append(dict(name='permissions', type=optional, array=False, removed=False,
            default='std::nullopt', native_default='std::nullopt'))
        f['restored_native_arguments'] = ['std::optional<QFileDevice::Permissions>']
    defaults = {
        ('QRemoteObjectHostBase', 'proxy'): 'QRemoteObjectHostBase::RemoteObjectNameFilter',
        ('QRemoteObjectHostBase', 'reverseProxy'): 'QRemoteObjectHostBase::RemoteObjectNameFilter',
        ('QWebEnginePage', 'findText'): 'std::function<void(const QWebEngineFindTextResult&)>',
        ('QWebEngineView', 'findText'): 'std::function<void(const QWebEngineFindTextResult&)>',
        ('QWebView', 'runJavaScript'): 'const std::function<void(const QVariant&)>&',
    }
    if (owner, name) in defaults:
        f = dict(f, omitted_native_callback=defaults[(owner, name)])
    return f


def optional_tail(f, parameters):
    if not parameters or len(parameters) != len(f['arguments']) + 1:
        return False
    last = parameters[-1].replace(' ', '')
    if last == 'Qt::Disambiguated_t':
        return True  # QT6_DECL_NEW_OVERLOAD supplies the native default marker.
    return bool(f.get('omitted_native_callback') and (
        last == f['omitted_native_callback'].replace(' ', '') or
        ((f['declaring_class'], f['name']) == ('QWebView', 'runJavaScript') and
         last == 'std::function<constvoid(QVariant&)>') or
        ('std::function<' in last and f['name'] == 'findText')))
