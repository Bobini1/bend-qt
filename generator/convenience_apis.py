"""Typed equivalents of public Qt APIs exposed through Python-only glue."""
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _type(cpp, name=None, *, pointers=0, container=False, children=()):
    return dict(cpp=cpp, name=name or cpp, pointers=pointers, reference=0, const=False,
                array=False, enum=False, flags=False, container=container, instantiations=list(children))


def _list(child):
    return _type('QList<' + child['cpp'] + '>', 'QList', container=True, children=[child])


def _optional(child):
    return _type('std::optional<' + child['cpp'] + '>', 'std::optional', container=True, children=[child])


def _function(owner, name, arguments, result, *, static=False, constructor=False, kind=None):
    signature = name + '(' + ','.join(t['cpp'].replace(' ', '') for _, t in arguments) + ')'
    return dict(name=name, minimal_signature=signature, signature=signature,
                declaring_class=owner, implementing_class=owner, arguments=[dict(
                    name=n, type=t, array=False, default='', native_default='', removed=False) for n, t in arguments],
                **{'return': result}, public=True, private=False, protected=False, static=static,
                const=not static and not constructor and name in ('entries', 'ranges', 'menu', 'bytes'), constructor=constructor,
                destructor=False, copy_constructor=False, removed=False, user_added=False, injected_code=False,
                abstract=False, virtual=False, final_cpp=False, deprecated=False, noexcept=False,
                operator=False, signal=False, slot=False, rvalue_reference=False, policies=[], snippets=[],
                source_file='', source_line=0, source_signatures=[], signature_modified=False,
                convenience=kind)


def install(classes, selected):
    variant = _type('QVariant')
    text = _type('QString')
    void = _type('void')
    parent = _type('QObject *', 'QObject', pointers=1)
    entries = []
    for owner in selected:
        if classes[owner].get('qobject'):
            f = _function(owner, 'tr', [('sourceText', text), ('disambiguation', text), ('n', _type('int'))],
                          text, static=True, kind='translation')
            f['arguments'][1].update(default='QString()', native_default='QString()')
            f['arguments'][2].update(default='-1', native_default='-1')
            entries.append(f)
    if 'QRangeModel' in selected:
        classes['QRangeModel']['convenience_base_cpp'] = 'ConvenienceRangeModel'
        for values in (_list(variant), _list(_list(variant))):
            f = _function('QRangeModel', 'QRangeModel', [('values', values), ('parent', parent)], void,
                          constructor=True, kind='range_constructor')
            f['arguments'][1].update(default='nullptr', native_default='nullptr')
            f['range_dimensions'] = 2 if values['instantiations'][0]['container'] else 1
            entries.append(f)
    if 'QDirListing' in selected and 'QFileInfo' in selected:
        entries.append(_function('QDirListing', 'entries', [], _list(_type('QFileInfo')), kind='directory_entries'))
    if 'QFont::Tag' in selected:
        tag = _optional(_type('QFont::Tag'))
        entries += [_function('QFont::Tag', 'fromString', [('name', text)], tag, static=True),
                    _function('QFont::Tag', 'fromValue', [('value', _type('quint32'))], tag, static=True)]
    if 'QJSEngine' in selected:
        entries.append(_function('QJSEngine', 'toScriptValue', [('value', variant)], _type('QJSValue'), kind='script_value'))
    if 'QLocale' in selected:
        entries.append(_function('QLocale', 'system', [], _type('QLocale'), static=True, kind='system_locale'))
    if 'QAction' in selected and 'QMenu' in selected:
        entries.append(_function('QAction', 'menu', [], _type('QMenu *', 'QMenu', pointers=1), kind='action_menu'))
    if 'QWizardPage' in selected:
        f = _function('QWizardPage', 'registerField', [('name', text), ('widget', _type('QWidget *', 'QWidget', pointers=1)),
                      ('property', text), ('changedSignal', text)], void, kind='wizard_field')
        for argument in f['arguments'][2:]:
            argument.update(default='QString()', native_default='QString()')
        entries.append(f)
    if 'QAudioBuffer' in selected:
        entries += [_function('QAudioBuffer', 'bytes', [], _type('QByteArray'), kind='audio_bytes'),
                    _function('QAudioBuffer', 'setBytes', [('bytes', _type('QByteArray'))], void, kind='audio_set_bytes')]
    if 'QHttpHeaderRangeSet' in selected:
        bound = _optional(_type('qint64'))
        ranges = _list(_type('std::pair<std::optional<qint64>,std::optional<qint64>>', 'std::pair',
                             container=True, children=[bound, bound]))
        entries += [_function('QHttpHeaderRangeSet', 'fromRanges', [('ranges', ranges)], _type('QHttpHeaderRangeSet'),
                              static=True, kind='http_ranges_create'),
                    _function('QHttpHeaderRangeSet', 'ranges', [], ranges, kind='http_ranges_get'),
                    _function('QHttpHeaderRangeSet', 'setRanges', [('ranges', ranges)], void, kind='http_ranges_set')]
        if 'QHttpHeaders' in selected:
            entries.append(_function('QHttpHeaders', 'rangeValues', [], _optional(_type('QHttpHeaderRangeSet')),
                                     kind='http_header_ranges'))
    for f in entries:
        classes[f['declaring_class']]['functions'].append(f)


def constructor_arguments(f, arguments):
    if f and f.get('convenience') == 'range_constructor':
        return ['std::move(convenience_range_values)', *arguments[1:]]
    return arguments


def _capture(position, shape, owner):
    return [f'const uint32_t convenience_origin = convenience_capture_inputs(r, r->arguments[{position}], {shape}, {owner});',
            'BqtValue convenience_wire{}; convenience_wire.word = convenience_origin; convenience_wire.owned_handle = convenience_origin;',
            'ConversionValueGuard convenience_lease(convenience_wire);', 'if (r->error) return true;']


def before_call(g, m):
    f = m['function']
    if f.get('convenience') == 'range_constructor':
        helper = 'convenience_row_cells' if f['range_dimensions'] == 2 else 'convenience_flat_cells'
        return ['auto convenience_range_state = convenience_make_range_state();',
                f'auto convenience_range_values = {helper}(r, r->arguments[0], convenience_range_state);',
                'if (r->error) return true;']
    if m.get('class') != 'QRangeModel' or f['constructor'] or f['static']:
        return []
    result = ['ConvenienceRangeAccess convenience_access(r);']
    if f['name'] in ('setData', 'setItemData'):
        result += [f'convenience_access.data_input = &r->arguments[1]; convenience_access.input_shape = {3 if f["name"] == "setItemData" else 0};']
    elif f['name'] == 'setHeaderData':
        role = 'int32_t(r->arguments[3].word)' if len(m['args']) > 3 else 'int(Qt::EditRole)'
        result += [f'if (!convenience_access.prepare_header(int32_t(r->arguments[0].word), int(r->arguments[1].word), {role}, r->arguments[2])) return true;']
    elif f['name'] == 'headerData':
        role = 'int32_t(r->arguments[2].word)' if len(m['args']) > 2 else 'int(Qt::DisplayRole)'
        result += [f'if (!convenience_access.read_header(int32_t(r->arguments[0].word), int(r->arguments[1].word), {role})) return true;']
    return result


def after_call(g, m):
    f = m['function']
    if f.get('convenience') == 'range_constructor':
        return ['if (!convenience_bind_range(r, r->result.word, convenience_range_state)) return true;']
    if m.get('class') == 'QRangeModel' and not f['constructor'] and not f['static']:
        return ['if (!r->error && !convenience_access.finish(r->result)) return true;']
    return []


def constructor_before(g, f, arguments):
    return before_call(g, dict(function=f))


def constructor_after(g, f, arguments):
    return after_call(g, dict(function=f))


def dependencies(g, used):
    result = set()
    for m in g.methods:
        f = m['function']
        if f.get('convenience') == 'range_constructor':
            alias = 'QRangeModel.fromRows' if f['range_dimensions'] == 2 else 'QRangeModel.fromValues'
            if alias in used and len(m['args']) == 1:
                result.add(m['bend_name'])
    return result


def method_case(g, m):
    f, kind = m['function'], m['function'].get('convenience')
    if kind not in ('directory_entries', 'script_value', 'http_ranges_create', 'http_ranges_get',
                    'http_ranges_set', 'http_header_ranges', 'translation', 'action_menu', 'wizard_field',
                    'audio_bytes', 'audio_set_bytes'):
        return None
    owner = f['declaring_class']
    lines = ['NativeCallScope call_scope;']
    if not f['static']:
        lines.append(f'auto *self = get<{owner}>(r, r->self, {g.ids[owner]}, false, {str(not f["const"]).lower()});')
    arguments = []
    for i, t in enumerate(m['args']):
        declarations, expression = g.argument(t, i)
        lines += declarations
        arguments.append(expression)
    lines += ['if (r->error) return true;']
    if kind == 'audio_bytes':
        lines.append('QByteArray returned(self->constData<char>(), self->byteCount());')
    elif kind == 'audio_set_bytes':
        lines += [f'const auto replacement = {arguments[0]};',
                  'if (replacement.size() != self->byteCount()) return fail(r, EINVAL, "Audio byte replacement must match byteCount");',
                  'self->detach();',
                  'if (!replacement.isEmpty()) std::memcpy(self->data<char>(), replacement.constData(), size_t(replacement.size()));',
                  'return true;']
        return lines
    elif kind == 'wizard_field':
        lines += ['struct FieldAccess : QWizardPage { using QWizardPage::registerField; };',
                  f'const auto property = {arguments[2]}.toUtf8();' if len(arguments) > 2 else 'const QByteArray property;',
                  f'auto changed = {arguments[3]}.toUtf8();' if len(arguments) > 3 else 'QByteArray changed;',
                  'if (!changed.isEmpty() && changed.front() != char(\'2\')) changed.prepend(char(\'2\'));',
                  f'(self->*(&FieldAccess::registerField))({arguments[0]}, {arguments[1]}, property.isEmpty() ? nullptr : property.constData(), changed.isEmpty() ? nullptr : changed.constData());',
                  'return true;']
        return lines
    elif kind == 'action_menu':
        lines.append('auto *returned = self->menu<QMenu *>();')
    elif kind == 'translation':
        lines += [f'const auto source = {arguments[0]}.toUtf8();',
                  f'const auto disambiguation = {arguments[1]}.toUtf8();' if len(arguments) > 1 else 'const QByteArray disambiguation;',
                  f'auto returned = {owner}::staticMetaObject.tr(source.constData(), disambiguation.isEmpty() ? nullptr : disambiguation.constData(), {arguments[2] if len(arguments) > 2 else "-1"});']
    elif kind == 'directory_entries':
        lines += ['QList<QFileInfo> returned;', 'for (const auto &entry : *self) returned.append(entry.fileInfo());']
    elif kind == 'script_value':
        lines += ['const uint32_t origin = convenience_capture_inputs(r, r->arguments[0], 0, r->self);',
                  'BqtValue held{}; held.word = origin; held.owned_handle = origin;',
                  'ConversionValueGuard lease(held);', 'if (r->error) return true;',
                  'if (origin && !convenience_keep_script_origin(r, r->self, origin)) return true;', 'lease.release();',
                  f'if (!retain_js_variant_exposures(r, r->self, {arguments[0]})) return true;',
                  f'auto returned = self->toScriptValue({arguments[0]});']
    elif kind in ('http_ranges_create', 'http_ranges_set'):
        lines += ['QList<QHttpHeaderRangeSpec> ranges;', f'for (const auto &item : {arguments[0]}) {{',
                  '    QHttpHeaderRangeSpec range{item.first, item.second};',
                  '    if (!range.isValid()) return fail(r, EINVAL, "Invalid HTTP range bounds");',
                  '    ranges.append(std::move(range));', '}']
        if kind == 'http_ranges_create':
            lines.append('QHttpHeaderRangeSet returned(QSpan<const QHttpHeaderRangeSpec>{ranges});')
        else:
            lines += ['self->setRanges(QSpan<const QHttpHeaderRangeSpec>{ranges});', 'return true;']
            return lines
    elif kind == 'http_ranges_get':
        lines += ['QList<std::pair<std::optional<qint64>, std::optional<qint64>>> returned;',
                  'for (const auto &range : self->ranges()) returned.append({range.start, range.end});']
    else:
        lines.append('auto returned = self->rangeValues();')
    lines += g.store_result(m['return'], 'returned')
    return lines + ['return true;']


def emit(g):
    g.bend.append((HERE / 'templates/convenience_apis.bend').read_text())
    if hasattr(g, 'qt_object_bases'):
        _emit_runtime_translation(g)
    if 'QtQuickTest' in g.profile['qt_modules']:
        _emit_quick_tests(g)
    for m in g.methods:
        f = m['function']
        if f.get('convenience') != 'range_constructor' or len(m['args']) != 1:
            continue
        public = 'fromRows' if f['range_dimensions'] == 2 else 'fromValues'
        g.bend += [f'def QRangeModel.{public}(values: {m["args"][0]["bend"]}) -> Action(QRangeModel):',
                   f'  {m["bend_name"]}(values)', '']
    if 'QQmlEngine' not in g.ids or not hasattr(g, 'custom_signal_arguments'):
        return
    wire = dict(kind='wire', bend='Wire', raw='Wire', codec='WireIdentity')
    word = dict(kind='u32', bend='U32', raw='U32')
    integer = dict(kind='i32', bend='Int32', raw='U32')
    text = dict(kind='string', bend='String', raw='String')
    engine = dict(kind='object', name='QQmlEngine', bend='QQmlEngine', raw='U32')
    operation = g.next_id; g.next_id += 1
    g.cases.append(f'case {operation}: {{\n    return convenience_singleton(r);\n}}')
    g.emit_effect('Internal.Qml.singleton_raw', [('self', engine), ('argument', wire), ('mode', word),
                  ('id', integer), ('uri', text), ('name', text)], wire, operation, has_self=True)
    g.bend.append((HERE / 'templates/convenience_singletons.bend').read_text())
    _emit_script_singletons(g)


def _emit_script_singletons(g):
    import effect_transport
    text = dict(kind='string', bend='String', raw='String')
    word = dict(kind='u32', bend='U32', raw='U32')
    obj = dict(kind='object', name='QObject', bend='QObject', raw='U32')
    operation = g.next_id; g.next_id += 1
    params = [('uri', text), ('major', word), ('minor', word), ('name', text),
              ('handler', effect_transport.handler('', ''))]
    raw = effect_transport.reserve(g, 'Qml.script_singleton_raw', params, obj, operation)
    g.cases.append(f'case {operation}: {{\n    return ConvenienceScriptSingletons::register_type(r);\n}}')
    g.bend += [
        'def Qml.scriptFactoryMethod() -> Method:',
        '  Method.define("createScriptSingleton", [QQmlEngine.arg()], QJSValue.arg())', '',
        'def Qml.registerScriptSingleton(~S: Data, ~f: S -> Method.Handler(~Qml.scriptFactoryMethod()), uri: String, major: U32, minor: U32, name: String, state: S) -> Action(QObject):',
        '  do Action.Raw<Result<&1, &1, U32 & String, QObject>>:',
        f'    result: Result<&1, &1, U32 & String, U32> <- {raw["name"]}(S, {operation}, 0, uri, major, minor, name, pair => run(Unit, Method.invoke(~Qml.scriptFactoryMethod(), ~S, ~f, pair)), state)',
        '    return QObject.wrap(result)', '']


def _emit_runtime_translation(g):
    wire = dict(kind='wire', bend='Wire', raw='Wire', codec='WireIdentity')
    text = dict(kind='string', bend='String', raw='String')
    integer = dict(kind='i32', bend='Int32', raw='U32')
    operation = g.next_id; g.next_id += 1
    g.cases.append(f'''case {operation}: {{
    auto schema = RuntimeQtObjects::ensure_class(r, r->arguments[0]);
    if (r->error) return true;
    const QByteArray source(r->arguments[1].text, qsizetype(r->arguments[1].size));
    const QByteArray disambiguation(r->arguments[2].text, qsizetype(r->arguments[2].size));
    r->result = string_value(schema->meta->tr(source.constData(), disambiguation.isEmpty() ? nullptr : disambiguation.constData(), int32_t(r->arguments[3].word)));
    return true;
}}''')
    g.emit_effect('Internal.QtObject.tr_raw', [('schema', wire), ('source', text), ('disambiguation', text), ('n', integer)], text, operation)
    g.bend += ['def QtObject.tr(~schema: QtObject, source: String) -> Action(String):',
               '  do Action<String>:', '    declaration: Wire <- QtObject.schema(schema)',
               '    Internal.QtObject.tr_raw(declaration, source, "", Int32{4294967295})', '',
               'def QtObject.trWith(~schema: QtObject, source: String, disambiguation: String, n: Int32) -> Action(String):',
               '  do Action<String>:', '    declaration: Wire <- QtObject.schema(schema)',
               '    Internal.QtObject.tr_raw(declaration, source, disambiguation, n)', '']


def _emit_quick_tests(g):
    text = dict(kind='string', bend='String', raw='String')
    arguments = g.conversions.register(g.type(_list(_type('QString'))))
    obj = dict(kind='object', name='QObject', bend='QObject', raw='U32', pointer=True)
    integer = dict(kind='i32', bend='Int32', raw='U32')
    operation = g.next_id; g.next_id += 1
    lines = ['NativeCallScope scope;']
    expressions = []
    for i, value in enumerate((text, arguments, text, obj)):
        declarations, expression = g.argument(value, i)
        lines += declarations; expressions.append(expression)
    lines += ['if (r->error) return true;',
              f'r->result.word = uint32_t(convenience_quick_test(r, {", ".join(expressions)}));', 'return true;']
    g.cases.append(f'case {operation}: {{\n' + '\n'.join('    ' + line for line in lines) + '\n}')
    g.emit_effect('QuickTest.runWithSetup', [('name', text), ('arguments', arguments), ('directory', text), ('setup', obj)], integer, operation)
    g.bend += ['def QuickTest.run(name: String, arguments: List<&2, String>, directory: String) -> Action(Int32):',
               '  QuickTest.runWithSetup(name, arguments, directory, QObject{0})', '']


def range_declarations(g):
    source = (HERE / 'templates/convenience_ranges.h').read_text()
    if tuple(map(int, g.profile['minimum_qt'].split('.'))) >= (6, 11, 0):
        return source
    # Qt 6.10 predates ItemAccess. Keep the same tracked cells and stage
    # writes in the model subclass before assigning through its native range.
    begin = source.index('    bool setData(const QModelIndex &index, const QVariant &value, int role = Qt::EditRole) override {')
    end = source.index('\n};', begin)
    source = source[:begin] + '''    bool setData(const QModelIndex &, const QVariant &, int role = Qt::EditRole) override;
    bool setItemData(const QModelIndex &, const QMap<int, QVariant> &) override;
    QMap<int, QVariant> itemData(const QModelIndex &index) const override {
        return QAbstractItemModel::itemData(index);
    }
    void multiData(const QModelIndex &index, QModelRoleDataSpan roles) const override {
        for (auto &role : roles) role.setData(data(index, role.role()));
    }
private:
    bool convenience_commit(const QModelIndex &, const ConvenienceRangeCell &, const QList<int> &);''' + source[end:]
    return source[:source.index('} // namespace bendqt\ntemplate<> struct QRangeModel::ItemAccess<')]


def declarations(g):
    source = '''
static uint32_t convenience_capture_inputs(BqtRequest *, const BqtValue &, unsigned, uint32_t);
static bool convenience_keep_script_origin(BqtRequest *, uint32_t, uint32_t);
'''
    if 'QRangeModel' in g.ids:
        source += range_declarations(g)
    if 'QtQuickTest' in g.profile['qt_modules']:
        source += 'static int convenience_quick_test(BqtRequest *, const QString &, QStringList, QString, QObject *);\n'
    return source


def cpp(g):
    source = (HERE / 'templates/convenience_apis.cpp').read_text()
    if 'QRangeModel' in g.ids:
        source += (HERE / 'templates/convenience_ranges.cpp').read_text()
        if tuple(map(int, g.profile['minimum_qt'].split('.'))) < (6, 11, 0):
            source += (HERE / 'templates/convenience_ranges_610.cpp').read_text()
    if 'QtQuickTest' in g.profile['qt_modules']:
        source += (HERE / 'templates/convenience_quick_test.cpp').read_text()
    singleton = ''
    if 'QQmlEngine' in g.ids and hasattr(g, 'custom_signal_arguments'):
        singleton = ((HERE / 'templates/convenience_singletons.cpp').read_text() +
                     (HERE / 'templates/convenience_script_singletons.cpp').read_text())
    return (source + singleton).replace('@VARIANT_ID@', str(g.ids['QVariant'])).replace(
        '@QML_ENGINE_ID@', str(g.ids.get('QQmlEngine', 0))).replace('@QOBJECT_ID@', str(g.ids.get('QObject', 0))).replace(
        '@QJSVALUE_ID@', str(g.ids.get('QJSValue', 0)))


def annotate(g):
    names = {}
    for m in g.methods:
        f = m['function']
        if f.get('convenience') or (f['declaring_class'] == 'QFont::Tag' and f['name'] in ('fromString', 'fromValue')):
            names.setdefault((f['declaring_class'], f['name']), []).append(m['bend_name'])
    for row in g.excluded:
        owner, signature = row['class'], row['signature']
        function = signature.split('(', 1)[0]
        target = None
        if owner == 'QRangeModel' and function == 'QRangeModel': target = (owner, function)
        elif owner == 'QDirListing' and function == '__iter__': target = (owner, 'entries')
        elif owner == 'QFont::Tag' and function in ('Tag', 'fromString', 'fromValue'):
            target = (owner, 'fromString' if function == 'Tag' else function)
        elif owner in ('QJSEngine', 'QQmlEngine', 'QQmlApplicationEngine') and function == 'toScriptValue': target = ('QJSEngine', function)
        elif owner == 'QHttpHeaderRangeSet' and function in ('QHttpHeaderRangeSet', 'ranges', 'setRanges'):
            target = (owner, 'fromRanges' if function == owner else function)
        elif owner == 'QHttpHeaders' and function == 'rangeValues': target = (owner, function)
        elif owner in ('QAction', 'QWidgetAction') and function == 'menu': target = ('QAction', function)
        elif owner == 'QLocale' and function == 'system': target = (owner, function)
        elif owner == 'QWizardPage' and function == 'registerField': target = (owner, function)
        elif owner == 'QAudioBuffer' and function in ('data', 'constData'): target = (owner, 'bytes')
        elif function == 'tr': target = (owner, function)
        if target:
            for name in names.get(target, []):
                alternative = dict(bend_name=name, contract='typed_qt_convenience')
                if alternative not in row.setdefault('alternatives', []): row['alternatives'].append(alternative)
        if owner in ('QQmlEngine', 'QQmlApplicationEngine') and signature.startswith('singletonInstance('):
            row.setdefault('alternatives', []).extend(dict(bend_name=name, contract='typed_qml_singleton_lookup')
                for name in ('QQmlEngine.singletonInstance', 'QQmlEngine.singletonInstanceById'))
        if owner == 'Global' and function == 'qmlRegisterSingletonType' and signature.startswith('qmlRegisterSingletonType(const char'):
            row.setdefault('alternatives', []).append(dict(bend_name='Qml.registerScriptSingleton', contract='per_engine_qjsvalue_factory'))
        if owner == 'Global' and function in ('QUICK_TEST_MAIN', 'QUICK_TEST_MAIN_WITH_SETUP') and 'QtQuickTest' in g.profile['qt_modules']:
            row.setdefault('alternatives', []).append(dict(bend_name='QuickTest.runWithSetup' if function.endswith('WITH_SETUP') else 'QuickTest.run', contract='native_qt_quick_test_runner'))


def inventory(g):
    return dict(directory='Owning QFileInfo snapshots from QDirListing entries',
                range_model='Owned flat or tabular QVariant ranges; native constructors and schema constructors',
                font_tags='Optional checked native Tag factories',
                translations='Native class and runtime schema translation contexts',
                wizard_fields='Widget properties with native mandatory-field notification',
                system_locale='The actual system locale, independently of the application default',
                action_menu='Native typed QMenu lookup',
                audio_buffers='Owning byte snapshots and exact-size writable replacements',
                quick_test='Native Qt Quick Test launcher with an optional ordinary QObject setup instance',
                singletons='Descriptor-typed QObject or QJSValue lookup by module/name or type id',
                script_singletons='Per-engine QJSValue factories with typed callbacks and registration handles',
                script_values='Native QVariant-to-JavaScript conversion with engine-lifetime origin leases',
                http_ranges='Optional signed 64-bit bounds and checked native range-set snapshots')
