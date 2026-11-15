"""QML registration of immutable compiled metaobjects, without private layouts."""


def method_case(g, m):
    f = m['function']
    if f['declaring_class']:
        return None
    if f['name'] == 'qmlClearTypeRegistrations':
        return ['for (const auto &value : entries) if (value.value && value.object && value.object != application)',
                '    return fail(r, EBUSY, "Clear QML type registrations after all scoped Qt objects have been released");',
                'qmlClearTypeRegistrations();', 'qml_meta_registrations.clear();', 'BendQmlLists::registrations_cleared();', 'return true;']
    if f['name'] != 'qmlRegisterUncreatableMetaObject':
        return None
    return ['NativeCallScope scope;',
        f'auto *meta = get<QMetaObject>(r, r->arguments[0].word, {g.ids["QMetaObject"]}, false, false);',
        'if (r->error) return true;',
        'if (!immutable_metaobject(meta)) return fail(r, ENOTSUP, "QML registration requires an immutable compiled metaobject; dynamic QObject metadata cannot outlive its mutable origin");',
        'for (int i : {1, 4}) if (std::memchr(r->arguments[i].text, 0, r->arguments[i].size))',
        '    return fail(r, EINVAL, "QML registration name contains an embedded NUL");',
        'auto strings = std::make_unique<QmlMetaRegistration>();',
        'strings->uri = QByteArray(r->arguments[1].text, qsizetype(r->arguments[1].size));',
        'strings->name = QByteArray(r->arguments[4].text, qsizetype(r->arguments[4].size));',
        'auto *stable = strings.get();',
        'qml_meta_registrations.push_back(std::move(strings));',
        'int id = qmlRegisterUncreatableMetaObject(*meta, stable->uri.constData(), int32_t(r->arguments[2].word), int32_t(r->arguments[3].word), stable->name.constData(), QString::fromUtf8(r->arguments[5].text, qsizetype(r->arguments[5].size)));',
        'if (id < 0) qml_meta_registrations.pop_back();',
        'r->result.word = uint32_t(id);', 'return true;']


def cpp(g):
    import abi_cohorts
    checks = []
    for name in g.selected:
        line = f'    if (is_static_metaobject<{name}>(meta)) return true;'
        if abi_cohorts.required(g, line):
            line = '#if BQT_HAS_RHI\n' + line + '\n#endif'
        checks.append(line)
    if g.callback_qml:
        checks.append('    if (meta == &CallbackQmlBridge::staticMetaObject) return true;')
    return '''
template<class T, class = void> struct HasStaticMetaObject : std::false_type {};
template<class T> struct HasStaticMetaObject<T, std::void_t<decltype(&T::staticMetaObject)>> : std::true_type {};
template<class T> static bool is_static_metaobject(const QMetaObject *meta) {
    if constexpr (HasStaticMetaObject<T>::value) return meta == &T::staticMetaObject;
    return false;
}
static bool immutable_metaobject(const QMetaObject *meta) {
    if (runtime_enum_metadata(meta) || native_metadata_is_immutable(meta)) return true;
    if (meta == &Qt::staticMetaObject) return true;
''' + '\n'.join(checks) + '''
    return false;
}
struct QmlMetaRegistration { QByteArray uri, name; };
static std::vector<std::unique_ptr<QmlMetaRegistration>> qml_meta_registrations;
'''
