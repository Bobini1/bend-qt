"""Adapt upstream reference-count policies to observable QObject properties.

An upstream add on an indexed setter is a keyed replacement in native Qt.
Unsupported relationships remain explicit exclusions, not guessed ownership.
"""
import re

# Value copies whose native dependencies are propagated by the ownership hook.
COPY_ORIGIN_TYPES = {'QHttpPart'}


def native_parent_argument(f):
    """Setters observed through native parenting, without invoking lazy getters."""
    return (f['declaring_class'], f['name']) in {
        ('QMainWindow', 'setStatusBar'), ('QGraphicsScene', 'setStyle'),
        ('QProxyStyle', 'setBaseStyle'), ('QComboBox', 'setView'),
        ('QTextDocument', 'setDocumentLayout'),
    }


def _simple_plan(g, name, f, args, parameters):
    member = (f['declaring_class'], f['name'])
    if member == ('Qt3DAnimation::QCallbackMapping', 'setCallback'):
        # An integer type argument precedes the callback pointer; execution flags
        # follow it. The getter observes the callback, not the integer argument.
        return {'custom': 'handle_property',
                'slot': _slot(g, 'Qt3DAnimation::QCallbackMapping.callback'),
                'input': 1, 'key': None, 'getter': 'callback', 'getter_key_cpp': None}
    # These getters create defaults, or screens are owned by the Qt platform.
    # Native QObject parent reconciliation covers the adopted arguments below;
    # observing their convenience getters would itself mutate the application.
    if native_parent_argument(f) or member in {
        ('QWidget', 'setScreen'), ('QWindow', 'setScreen'),
        ('QOffscreenSurface', 'setScreen'),
    }:
        return None
    refs = [(p, r) for p in f['policies'] for r in p.get('references', []) if r['action'] != 16]
    parents = [p for p in f['policies'] if p['index'] > 0 and p['parent_action'] == 1 and p['parent_index'] == -1]
    if parents:
        refs += [(p, {'action': 8, 'variable': ''}) for p in parents]
    inferred = False
    if (not refs and not f['constructor'] and not f['static'] and g.classes[name]['object']
            and f['name'].startswith('set') and not f['name'].startswith('setParent')
            and not f['name'].endswith('Parent')):
        objects = [i for i, a in enumerate(args) if a['kind'] == 'object' and a['pointer']]
        # Multi-argument mappings can be many-to-one (for example signal IDs).
        # Indexed replacement needs explicit upstream relationship metadata.
        if len(objects) == 1 and len(args) == 1:
            source = next(p['source'] for p in parameters if p['input'] == objects[0])
            refs = [({'index': source + 1}, {'action': 8, 'variable': ''})]
            inferred = True
    if not refs:
        return None
    if len(refs) != 1 or f['constructor'] or f['static']:
        raise ValueError('Retention requires one observable object property')
    p, ref = refs[0]
    if p['index'] <= 0 or ref['action'] not in (1, 8) or not f['name'].startswith('set'):
        raise ValueError('Reference-count action requires a Bend retention adapter')
    source = p['index'] - 1
    index = parameters[source]['input']
    if index is None or args[index]['kind'] != 'object' or not args[index]['pointer']:
        raise ValueError('Retained argument must be a tracked QObject pointer')
    keys = [i for i in range(len(args)) if i != index]
    if len(keys) > 1 or any(args[i]['kind'] not in ('i32', 'u32', 'enum', 'flags') for i in keys):
        raise ValueError('Retention key needs a supported scalar representation')
    prop = f['name'][3:4].lower() + f['name'][4:]
    target_name = args[index]['name']
    # menuBar() creates a bar and replaces a custom menu widget. Both setters
    # change the same native property, observed without creation by menuWidget().
    if member == ('QMainWindow', 'setMenuBar'):
        prop, target_name = 'menuWidget', 'QWidget'
    import protected_members
    getters = [m for m in g.inherited(name) if m['name'] == prop and (m['public'] or protected_members.permitted(g, m)) and not m['removed']
               and not m['static'] and m['return']['name'] == target_name
               and m['return']['pointers'] == 1 and len(m['arguments']) == len(keys)
               and all(a['type']['name'] == f['arguments'][parameters[k]['source']]['type']['name']
                       for a, k in zip(m['arguments'], keys))]
    if not getters:
        if inferred:
            return {'custom': 'handle_property', 'slot': _slot(g, f['declaring_class'] + '.' + f['name'] + '.opaque'),
                    'input': index, 'key': None, 'getter': None, 'getter_key_cpp': None,
                    'opaque_native': not g.classes[target_name]['qobject']}
        raise ValueError('Retention setter needs a native getter to confirm its relationship')
    getter = getters[0]
    slot_key = (ref['variable'] or getter['minimal_signature']) + ':' + target_name
    slot = g.retention_slots.setdefault(slot_key, len(g.retention_slots) + 1)
    owner = getter.get('implementing_class') or getter['declaring_class']
    if not g.classes[owner]['qobject'] or not g.classes[target_name]['qobject']:
        result = {'custom': 'handle_property', 'slot': slot, 'input': index,
                'key': keys[0] if keys else None, 'getter': prop,
                'getter_key_cpp': getter['arguments'][0]['type']['cpp'] if keys else None}
        pointer = protected_members.member(g, getter)
        if pointer:
            result['getter_member'] = pointer
        return result
    accessor = 'retention_' + re.sub(r'[^a-zA-Z0-9_]', '_', owner + '_' + getter['minimal_signature'])
    cast_key = (f"static_cast<{getter['arguments'][0]['type']['cpp']}>(key)" if keys else '')
    call = protected_members.expression(g, getter, [cast_key] if keys else [], receiver=f'static_cast<{owner} *>(object)')
    call = call or f'static_cast<{owner} *>(object)->{prop}({cast_key})'
    g.retention_accessors[accessor] = (
        f'static QObject *{accessor}(QObject *object, uint32_t key) {{\n'
        f'    return const_cast<QObject *>(static_cast<const QObject *>({call}));\n}}\n')
    null_resets_default = member in {
        ('QTextEdit', 'setDocument'), ('QPlainTextEdit', 'setDocument'),
        ('QGraphicsTextItem', 'setDocument'), ('QGraphicsWidget', 'setStyle'),
        ('QQmlFileSelector', 'setSelector'),
    }
    return {'slot': slot, 'input': index, 'key': keys[0] if keys else None,
            'getter': prop, 'accessor': accessor, 'upstream_action': ref['action'],
            'parent_annotation': bool(parents), 'inferred_property': inferred,
            'null_resets_default': null_resets_default}


def _slot(g, key):
    return g.retention_slots.setdefault(key, len(g.retention_slots) + 1)


def _accessor(g, owner, target, expression, key):
    """Collection observers only inspect a live registered target."""
    name = 'retention_' + re.sub(r'[^a-zA-Z0-9_]', '_', key)
    g.retention_accessors[name] = (
        f'static QObject *{name}(QObject *object, uint32_t key) {{\n'
        '    auto *e = entry(key);\n'
        f'    auto *target = e ? qobject_cast<{target} *>(e->object) : nullptr;\n'
        f'    auto *owner = static_cast<{owner} *>(object);\n'
        f'    return target && ({expression}) ? target : nullptr;\n}}\n')
    return name


def _group(g, owner, target, expression, key, index, **extra):
    return dict(input=index, slot=_slot(g, key), accessor=_accessor(g, owner, target, expression, key), **extra)


def _plan(g, name, f, args, parameters):
    """Translate ownership annotations to observed native relationships.

    A parent-wrapper annotation is not a claim that Qt reparents the argument.
    Collections use membership observers; actual parenting uses the registry.
    """
    if f['constructor'] and not args:
        # The default factory supplies native defaults, not caller handles.
        # Original annotations can still mention an omitted parent argument.
        return None
    member = f['declaring_class'], f['name']
    if member in (('QTextEdit', 'insertFromMimeData'), ('QPlainTextEdit', 'insertFromMimeData')):
        return None  # Native code consumes/copies the MIME data during this call.
    if member == ('QPrinter', 'setEngines'):
        slots = [_slot(g, 'QPrinter.customPrintEngine'), _slot(g, 'QPrinter.customPaintEngine')]
        # These getters observe native engine storage independently of a Bend
        # override of the virtual paintEngine method.
        g.retention_accessors['printer_engine_observer'] = f'''
static uint32_t retained_printer_engine(uint32_t owner, uint32_t kind) {{
    NativeCallScope scope;
    BqtRequest request{{}};
    auto *printer = get<QPrinter>(&request, owner, {g.ids['QPrinter']}, false, false);
    if (request.error) return 0;
    const void *actual = kind ? static_cast<const void *>(printer->QPrinter::paintEngine())
                              : static_cast<const void *>(printer->printEngine());
    if (!actual) return 0;
    const uint16_t type = kind ? {g.ids['QPaintEngine']} : {g.ids['QPrintEngine']};
    for (uint32_t i = 1; i < capacity; ++i) {{
        auto &value = entries[i];
        if (value.value && value.cast && value.cast(value.value, type) == actual)
            return token(i, value.generation);
    }}
    return 0;
}}
'''
        return dict(custom='printer_engines', slots=slots)
    import image_buffers
    if image_buffers.handles(f):
        return None  # Qt cleanup callback holds the shared aligned pixel storage.
    import boundary_finders
    if boundary_finders.handles(f):
        return None  # Shared text and working buffer are owned by value sidecars.
    if member[0] == 'QQmlListReference':
        return None  # Native QPointer owner and qml_list_lifetimes member leases.
    if member[0] == 'QMessageLogger' and f['return']['name'] == 'QDebug':
        return {'custom': 'debug_result', 'slot': _slot(g, 'QDebug.context'),
                'category': next((i for i, a in enumerate(args) if a.get('name') == 'QLoggingCategory'), None)}
    if member[0] == 'QDebug' and args and args[0].get('name') == 'QDebug' and (f['constructor'] or member[1] == 'operator='):
        return {'custom': 'debug_copy', 'constructor': f['constructor']}
    if member in (('QSGBasicGeometryNode', 'setRendererMatrix'), ('QSGBasicGeometryNode', 'setRendererClipList')):
        return {'custom': 'handle_property', 'slot': _slot(g, '.'.join(member)), 'input': 0, 'key': None,
                'getter': 'matrix' if member[1] == 'setRendererMatrix' else 'clipList', 'getter_key_cpp': None}
    if f['return']['name'] == 'QMetaObject' and f['return']['pointers'] == 1 and f['return']['const']:
        return None  # metadata_lifetimes records and validates the native origin.
    if member[0] == 'QHttpPart':
        if member[1] == 'setBodyDevice':
            return {'custom': 'handle_property', 'slot': _slot(g, 'QHttpPart.bodyDevice'),
                    'input': 0, 'key': None, 'getter': None, 'getter_key_cpp': None}
        if args and args[0].get('name') == 'QHttpPart' and (f['constructor'] or member[1] == 'operator='):
            return {'custom': 'part_copy', 'constructor': f['constructor'], 'slot': _slot(g, 'QHttpPart.bodyDevice')}
    if member == ('QHttpMultiPart', 'append'):
        return {'custom': 'part_append', 'slot': _slot(g, 'QHttpMultiPart.devices')}
    if member[0] == 'QNetworkAccessManager' and f['return']['name'] == 'QNetworkReply':
        body = next((i for i, a in enumerate(args) if a.get('name') in ('QIODevice', 'QHttpMultiPart') and a.get('pointer')), None)
        if body is not None:
            return {'custom': 'reply_body', 'input': body, 'slot': _slot(g, 'QNetworkReply.requestBody')}
    guards = {'QSignalBlocker': ('QObject', 'dismiss'), 'QSemaphoreReleaser': ('QSemaphore', 'cancel')}
    if member[0] in guards:
        target, release = guards[member[0]]
        slot = _slot(g, member[0] + '.guarded')
        if f['constructor'] and args and args[0].get('name') == target:
            # Both pointer and reference overloads retain the same native
            # object. A non-copyable reference is not a synchronous value copy.
            return {'custom': 'constructor_dependencies', 'dependencies': [{'input': 0, 'slot': slot}]}
        if member[1] == release:
            return {'custom': 'clear_dependency', 'slot': slot}
    if member in {
        ('QGraphicsItem', 'parentItem'), ('QGraphicsItem', 'parentWidget'), ('QGraphicsItem', 'scene'),
        ('QGraphicsLayoutItem', 'parentLayoutItem'),
        ('QAbstractState', 'machine'), ('QAbstractTransition', 'targetState'), ('QAbstractTransition', 'targetStates'),
        ('QAbstractScrollArea', 'setupViewport'), ('QAbstractItemDelegate', 'setEditorData'),
        ('QAbstractItemDelegate', 'setModelData'), ('QGraphicsWidget', 'setTabOrder'),
        ('QGraphicsScene', 'setFocusItem'), ('QTableWidget', 'setCurrentItem'),
        ('QGraphicsLinearLayout', 'setAlignment'), ('QGraphicsGridLayout', 'setAlignment'),
        ('QGraphicsLinearLayout', 'setStretchFactor'),
    }:
        return None
    if member[0] == 'QPainter' and ((f['constructor'] and args) or member[1] in ('begin', 'end')):
        return {'custom': 'painter', 'slot': _slot(g, 'QPainter.device'),
                'constructor': f['constructor'], 'end': member[1] == 'end'}
    if member[0] in ('QDataStream', 'QTextStream', 'QBuffer', 'QCborStreamWriter', 'QXmlStreamWriter'):
        constructor = f['constructor']
        binding = (constructor and args and args[0].get('name') in ('QByteArray', 'QIODevice', 'QStringBuffer')) or member[1] in ('setDevice', 'setBuffer', 'setString')
        if binding:
            backing = args[0]
            retained_input = 0 if backing.get('pointer') else None
            return {'custom': 'backing', 'slot': _slot(g, member[0] + '.backing'),
                    'input': retained_input, 'constructor': constructor,
                    'internal_device': constructor and member[0] != 'QBuffer' and backing.get('name') == 'QByteArray',
                    'backing_kind': backing.get('name'),
                    'class': member[0]}
    if not g.classes[name]['qobject'] and not f['constructor']:
        return _simple_plan(g, name, f, args, parameters)
    special = {
        ('QWidget', 'setStyle'): 'style',
        ('QCompleter', 'setPopup'): 'popup',
        ('QDateTimeEdit', 'setCalendarWidget'): 'calendar',
        ('QGraphicsProxyWidget', 'setWidget'): 'embedding',
    }.get(member)
    if special:
        return {'custom': special, 'slot': _slot(g, 'QWidget.explicitStyle') if special == 'style' else 0}
    # These getters only borrow an already-parented native object. PySide's
    # receiver annotation keeps a Python wrapper alive, not an additional C++ edge.
    if member in {('QLayout', 'parentWidget'), ('QSyntaxHighlighter', 'document')}:
        return None
    reverse = {
        ('QAction', 'setActionGroup'): ('QActionGroup', 'QAction', 'owner->actions().contains(target)', 'QActionGroup.actions'),
        ('QUndoStack', 'setGroup'): ('QUndoGroup', 'QUndoStack', 'owner->stacks().contains(target)', 'QUndoGroup.stacks'),
        ('QCompleter', 'setWidget'): ('QWidget', 'QCompleter', 'target->widget() == owner', 'QWidget.completers'),
        ('QQuickItem', 'setParentItem'): ('QQuickItem', 'QQuickItem', 'target->parentItem() == owner', 'QQuickItem.visualChildren'),
    }.get(member)
    if reverse:
        return {'custom': 'groups', 'groups': [_group(g, *reverse, 0, reverse=True)]}
    if member == ('QWindow', 'setParent'):
        return {'custom': 'qobject_parent'}
    # Constructors with native QObject parenting need no synthetic pin.
    if f['constructor'] and f['declaring_class'] in ('QDrag', 'QRubberBand'):
        return None
    if f['constructor'] and f['declaring_class'] == 'QUndoView' and args and args[0].get('name') in ('QUndoGroup', 'QUndoStack'):
        prop = 'group' if args[0]['name'] == 'QUndoGroup' else 'stack'
        key = 'QUndoView.' + prop
        group = _group(g, 'QUndoView', args[0]['name'], f'owner->{prop}() == target', key, 0)
        return {'custom': 'groups', 'constructor': True, 'groups': [group]}
    if f['constructor'] and f['declaring_class'] in ('QJSValue', 'QJSManagedValue', 'QJSValueIterator', 'QTextCursor', 'QQmlProperty'):
        return None  # Dedicated copy-aware QObject provenance replaces pointer-only pins.
    if f['constructor']:
        dependencies = []
        for i, a in enumerate(args):
            if a['kind'] not in ('object', 'value') or (not a.get('pointer') and not (name == 'QSGGeometry' and i == 0)):
                continue
            # A native QObject parent is excluded after construction by the
            # actual parent tree. Other borrowed pointers remain conservatively
            # pinned for the lifetime of the constructed object/value.
            getters = [getter for getter in g.inherited(name) if getter['public'] and not getter['removed']
                       and not getter['static'] and not getter['arguments'] and getter['return']['pointers'] == 1
                       and getter['return']['name'] == a['name']]
            key = (getters[0]['minimal_signature'] + ':' + a['name']) if len(getters) == 1 else name + '.constructor.' + str(i)
            dependencies.append({'input': i, 'slot': _slot(g, key)})
        if dependencies:
            return {'custom': 'constructor_dependencies', 'dependencies': dependencies}
    if f['constructor'] or f['static']:
        return _simple_plan(g, name, f, args, parameters)
    groups = []
    if member[0] == 'QAbstractTransition' and member[1] in ('setTargetState', 'setTargetStates'):
        group = _group(g, 'QAbstractTransition', 'QAbstractState', 'owner->targetStates().contains(target)',
                       'QAbstractTransition.targets', 0, bulk=member[1] == 'setTargetStates', allow_ancestor=True, allow_null=True)
        return {'custom': 'groups', 'groups': [group]}
    if member == ('QState', 'addTransition') and args and args[-1].get('name') == 'QAbstractState':
        group = _group(g, 'QAbstractTransition', 'QAbstractState', 'owner->targetStates().contains(target)',
                       'QAbstractTransition.targets', len(args) - 1, allow_ancestor=True)
        return {'custom': 'groups', 'constructor': True, 'groups': [group]}
    match = re.match(r'^(add|insert|remove)([A-Z].*)$', f['name'])
    if match:
        operation, stem = match.groups()
        prop = stem[0].lower() + stem[1:]
        prop = prop if prop.endswith('s') else prop + 's'
        for getter in g.inherited(name):
            t = getter['return']
            if (getter['name'] != prop or not getter['public'] or getter['removed'] or getter['arguments']
                    or not t.get('container') or len(t.get('instantiations', [])) != 1):
                continue
            element = t['instantiations'][0]
            target = element['name']
            if element['pointers'] != 1 or target not in g.classes or not g.classes[target]['qobject']:
                continue
            candidates = []
            for i, a in enumerate(args):
                bulk = a['kind'] == 'list' and len(a.get('children', [])) == 1
                v = a['children'][0] if bulk else a
                if v['kind'] == 'object' and v.get('pointer') and v['name'] == target:
                    candidates.append((i, bulk))
            # insertAction(before, action) retains the added member, not the anchor.
            if candidates:
                i, bulk = candidates[-1]
                owner = getter.get('implementing_class') or getter['declaring_class']
                key = owner + '.' + prop
                groups.append(_group(g, owner, target, f'owner->{prop}().contains(target)', key, i,
                                     bulk=bulk, remove=operation == 'remove'))
                break
    if member[0] == 'QDataWidgetMapper' and member[1] in ('addMapping', 'removeMapping'):
        groups = [_group(g, 'QDataWidgetMapper', 'QWidget', 'owner->mappedSection(target) >= 0',
                         'QDataWidgetMapper.mappings', 0, remove=member[1] == 'removeMapping')]
    if member == ('QButtonGroup', 'setId'):
        groups = [_group(g, 'QButtonGroup', 'QAbstractButton', 'owner->id(target) != -1',
                         'QButtonGroup.assignedIds', 0)]
    # Layouts can contain several widget arguments, and layouts without a parent
    # widget still keep raw pointers. indexOf is a non-mutating membership query.
    def derives(class_name, base):
        return class_name == base or any(derives(b, base) for b in g.classes.get(class_name, {}).get('bases', []))
    layout = derives(name, 'QLayout')
    if layout and (f['name'].startswith(('add', 'insert')) or f['name'] in ('setWidget', 'removeWidget', 'replaceWidget')):
        for i, a in enumerate(args):
            if a['kind'] == 'object' and a.get('pointer') and a['name'] == 'QWidget':
                if f['name'] == 'replaceWidget' and i == 0:
                    continue
                groups.append(_group(g, 'QLayout', 'QWidget', 'owner->indexOf(target) >= 0', 'QLayout.widgets', i,
                                     remove=f['name'] == 'removeWidget'))
    if member[0] in ('QMenu', 'QMenuBar') and member[1] in ('addMenu', 'insertMenu'):
        for i, a in enumerate(args):
            if a.get('name') == 'QMenu' and a['kind'] == 'object':
                groups.append(_group(g, member[0], 'QMenu', 'owner->actions().contains(target->menuAction())',
                                     member[0] + '.menus', i))
    if groups:
        parents = [i for i, a in enumerate(args) if layout and a['kind'] == 'object' and
                   a.get('pointer') and derives(a.get('name', ''), 'QLayout')]
        if member == ('QState', 'addTransition'):
            parents += [group['input'] for group in groups]
        conditional = [group['input'] for group in groups if member in
                       (('Qt3DCore::QEntity', 'addComponent'), ('Qt3DCore::QJoint', 'addChildJoint'))]
        return {'custom': 'groups', 'groups': groups, 'parents': parents, 'conditional_parents': conditional}
    # The upstream parent rule is directly realized by native QObject parenting.
    # This list names ownership operations, never a class discovery allowlist.
    parent_methods = {
        'QAnimationGroup': {'addAnimation', 'insertAnimation', 'removeAnimation'},
        'QLayout': {'addItem', 'removeItem'},
        'QBoxLayout': {'addLayout', 'insertLayout'},
        'QGridLayout': {'addLayout'},
        'QFormLayout': {'setLayout', 'addRow', 'insertRow'},
        'QDialogButtonBox': {'addButton', 'removeButton'},
        'QTabWidget': {'addTab', 'insertTab', 'setCornerWidget'},
        'QStackedWidget': {'addWidget', 'insertWidget'},
        'QToolBox': {'addItem', 'insertItem'},
        'QSplitter': {'addWidget', 'insertWidget'},
        'QToolBar': {'addWidget', 'insertWidget'},
        'QWizard': {'addPage', 'setPage'},
        'QMainWindow': {'addDockWidget', 'addToolBar', 'insertToolBar'},
        'QMenuBar': {'setCornerWidget'}, 'QTabBar': {'setTabButton'},
        'QAbstractItemView': {'setIndexWidget'}, 'QTableWidget': {'setCellWidget'},
        'QListWidget': {'setItemWidget'}, 'QTreeWidget': {'setItemWidget'},
        'QStateMachine': {'addState', 'removeState'},
        'QState': {'addTransition', 'removeTransition'},
        'QAbstractScrollArea': {'addScrollBarWidget', 'setViewport'},
        'QMdiArea': {'addSubWindow'},
        'QStatusBar': {'addWidget', 'addPermanentWidget', 'insertWidget', 'insertPermanentWidget'},
        'QProgressDialog': {'setBar', 'setCancelButton', 'setLabel'},
    }
    if member[1] in parent_methods.get(member[0], set()):
        indices = [i for i, a in enumerate(args) if a['kind'] == 'object' and a.get('pointer') and
                   g.classes.get(a['name'], {}).get('qobject')]
        annotated = {parameters[p['index'] - 1]['input'] for p in f['policies']
                     if 0 < p['index'] <= len(parameters) and p['parent_action'] in (1, 2) and p['parent_index'] == -1}
        selected = [i for i in indices if i in annotated]
        indices = selected or indices[-1:]
        return {'custom': 'parent', 'indices': indices, 'remove': member[1].startswith('remove')}
    return _simple_plan(g, name, f, args, parameters)


def _before_call(g, m):
    p = m.get('retention') or {}
    kind = p.get('custom')
    if not kind:
        return []
    if kind == 'printer_engines':
        return ['if (!a0 || !a1) return fail(r, EINVAL, "Printer engines must not be null");',
                'RetentionBatch retention_batch;',
                *[f'if (!retention_batch.add(r, r->self, {slot}, r->arguments[{i}].word, nullptr, false, false, {i})) return true;'
                  for i, slot in enumerate(p['slots'])]]
    if kind == 'debug_result':
        lines = ['RetentionBatch retention_batch;', f'if (!retention_batch.add(r, 0, {p["slot"]}, r->self, nullptr, false, true, r->self)) return true;']
        if p['category'] is not None:
            i = p['category']
            lines += [f'if (!retention_batch.add(r, 0, {p["slot"]}, r->arguments[{i}].word, nullptr, false, true, r->arguments[{i}].word)) return true;']
        return lines
    if kind == 'debug_copy':
        owner, constructed = ('0', 'true') if p['constructor'] else ('r->self', 'false')
        return ['RetentionBatch retention_batch;', 'for (const auto &edge : retentions) if (edge.owner == r->arguments[0].word && edge.target) {',
                f'    if (!retention_batch.add(r, {owner}, edge.slot, edge.target, nullptr, false, {constructed}, edge.key)) return true;', '}']
    if kind == 'qobject_parent':
        return ['if (!can_adopt(r, a0, self)) return true;']
    if kind == 'constructor_dependencies':
        lines = ['RetentionBatch retention_batch;']
        for dep in p['dependencies']:
            lines += [f'if (!retention_batch.add(r, 0, {dep["slot"]}, r->arguments[{dep["input"]}].word, nullptr, false, true, 0)) return true;']
        return lines
    if kind == 'part_copy':
        if p['constructor']:
            return ['call_scope.value_origin = r->arguments[0].word;']
        return ['RetentionBatch retention_batch;',
                f'if (!retention_batch.add(r, r->self, {p["slot"]}, http_part_device(r->arguments[0].word), nullptr, false, false, 0)) return true;']
    if kind == 'part_append':
        return ['RetentionBatch retention_batch;', 'uint32_t body_device = http_part_device(r->arguments[0].word);',
                f'if (body_device && !retention_batch.add(r, r->self, {p["slot"]}, body_device, nullptr)) return true;']
    if kind == 'reply_body':
        return ['RetentionBatch retention_batch;',
                f'if (!retention_batch.add(r, 0, {p["slot"]}, r->arguments[{p["input"]}].word, nullptr, false, true, 0)) return true;']
    if kind == 'painter':
        lines = ['RetentionBatch retention_batch;']
        owner = '0' if p['constructor'] else 'r->self'
        target = '0' if p['end'] else 'r->arguments[0].word'
        if not p['constructor'] and not p['end']:
            lines += ['if (self->isActive()) return fail(r, EBUSY, "End the current painting session before beginning another");']
        lines += [f'if (!retention_batch.add(r, {owner}, {p["slot"]}, {target}, nullptr, false, {str(p["constructor"]).lower()}, 0)) return true;']
        return lines
    if kind == 'handle_property':
        i = p['input']
        key = f'r->arguments[{p["key"]}].word' if p['key'] is not None else '0'
        lines = ['RetentionBatch retention_batch;']
        if p.get('opaque_native'):
            lines += [f'if (auto *e = entry(r->arguments[{i}].word); e && !e->native_observed) return fail(r, ENOTSUP, "An unobserved native pointer needs an audited opaque-setter ownership contract");']
        return lines + [f'if (!retention_batch.add(r, r->self, {p["slot"]}, r->arguments[{i}].word, nullptr, false, false, {key})) return true;']
    if kind == 'backing':
        lines = []
        if not p['constructor']:
            if p['class'] == 'QBuffer':
                lines += ['if (self->isOpen()) return fail(r, EBUSY, "Close QBuffer before replacing its backing array");']
            elif p.get('backing_kind') == 'QIODevice':
                lines += ['if (a0 && retention_internal_device(r->self) == a0) return fail(r, EINVAL, "A stream cannot replace its owned internal device with that same device");']
        lines += ['RetentionBatch retention_batch;']
        if p['input'] is not None:
            owner = '0' if p['constructor'] else 'r->self'
            lines += [f'if (!retention_batch.add(r, {owner}, {p["slot"]}, r->arguments[{p["input"]}].word, nullptr, false, {str(p["constructor"]).lower()}, 0)) return true;']
        return lines
    if kind == 'groups':
        lines = ['RetentionBatch retention_batch;']
        lines += [f'if (!can_adopt(r, self, a{i})) return true;' for i in p.get('parents', [])]
        lines += [f'if (a{i} && !a{i}->parent() && !can_adopt(r, self, a{i})) return true;' for i in p.get('conditional_parents', [])]
        if m['class'] == 'QLayout' or 'QLayout' in g.all_bases(m['class']):
            for i, argument in enumerate(m['args']):
                if argument.get('name') == 'QWidget' and argument.get('pointer'):
                    lines += [f'if (!native_layout_widget_idle(r, a{i})) return true;']
        for group in p['groups']:
            i, slot, accessor = group['input'], group['slot'], group['accessor']
            owner = f'r->arguments[{i}].word' if group.get('reverse') else '0' if p.get('constructor') else 'r->self'
            target = 'r->self' if group.get('reverse') else f'r->arguments[{i}].word'
            remove = str(bool(group.get('remove'))).lower()
            if group.get('bulk'):
                lines += [f'for (auto *member : *a{i}) {{', '    auto target = retention_token(r, member);',
                          '    if (r->error) return true;']
                if group.get('allow_ancestor'):
                    lines += ['    if (member && inside(self, member)) continue;']
                lines += [f'    if (!retention_batch.add(r, {owner}, {slot}, target, {accessor}, {remove})) return true;', '}']
            else:
                condition = (f'a{i} && ' if group.get('allow_null') else '')
                if group.get('allow_ancestor') and not p.get('constructor'):
                    condition += f'!inside(self, a{i}) && '
                lines += [f'if ({condition}!retention_batch.add(r, {owner}, {slot}, {target}, {accessor}, {remove}, {str(bool(p.get("constructor"))).lower()})) return true;']
        return lines
    if kind == 'parent':
        if p['remove']:
            return []
        lines = [f'if (!can_adopt(r, self, a{i})) return true;' for i in p['indices']]
        lines += ['if (!native_children_idle(r, r->self)) return true;']
        getter = {'setCellWidget': 'cellWidget', 'setIndexWidget': 'indexWidget',
                  'setItemWidget': 'itemWidget', 'setTabButton': 'tabButton',
                  'setCornerWidget': 'cornerWidget', 'setViewport': 'viewport'}.get(m['function']['name'])
        if getter and p['indices']:
            i = p['indices'][-1]
            inputs = [g.argument(a, n)[1] for n, a in enumerate(m['args']) if n != i]
            lines += [f'auto *native_previous_widget = self->{getter}({", ".join(inputs)});',
                      f'if (native_previous_widget != a{i}) {{',
                      f'    if (native_previous_widget && a{i} && inside(a{i}, native_previous_widget)) return fail(r, EINVAL, "Replacement widget is owned by the widget that Qt will delete");',
                      '    uint32_t id = retention_token(r, native_previous_widget, false);',
                      '    if (id && active_in_subtree(id)) return fail(r, EBUSY, "The replaced widget is active in a suspended callback");', '}']
        elif m['function']['declaring_class'] == 'QProgressDialog':
            lines += [f'if (a{i} && inside(a{i}, self) && a{i}->parent() != self) return fail(r, EINVAL, "Progress-dialog replacement must not be nested inside an existing control");' for i in p['indices']]
        return lines
    if kind == 'style':
        return ['RetentionBatch retention_batch;',
                f'if (!retention_batch.add(r, r->self, {p["slot"]}, r->arguments[0].word, retained_explicit_style, false, false, 0)) return true;']
    if kind == 'popup':
        return ['if (!a0) return fail(r, EINVAL, "QCompleter popup must not be null");',
                'if (!can_adopt(r, self, a0)) return true;',
                'if (reaches_token(r->arguments[0].word, r->self)) return fail(r, ELOOP, "Popup ownership would create a retention cycle");',
                'auto *old_popup = self->popup();',
                'if (old_popup == a0) return true;',
                'if (uint32_t id = retention_token(r, old_popup, false); id && active_in_subtree(id)) return fail(r, EBUSY, "The old popup is active in a suspended callback");',
                'if (old_popup && inside(a0, old_popup)) return fail(r, EINVAL, "Popup replacement cannot be a child of the old popup");',
                'auto *popup_entry = entry(r->arguments[0].word);',
                'if (popup_entry && !popup_entry->owned && !a0->parent()) return fail(r, EBUSY, "Popup already has a native owner");']
    if kind == 'calendar':
        return ['if (!a0 || !self->calendarPopup() || !(self->displayedSections() & QDateTimeEdit::DateSections_Mask)) return fail(r, EINVAL, "Calendar replacement requires an enabled date popup and a nonnull widget");',
                'if (!can_adopt(r, self, a0)) return true;',
                'auto *old_calendar = self->calendarWidget();',
                'if (old_calendar == a0) return true;',
                'if (uint32_t id = retention_token(r, old_calendar, false); id && active_in_subtree(id)) return fail(r, EBUSY, "The old calendar is active in a suspended callback");',
                'if (old_calendar && inside(a0, old_calendar)) return fail(r, EINVAL, "Calendar replacement cannot be a child of the old calendar");']
    if kind == 'embedding':
        return ['if (!can_adopt(r, self, a0)) return true;',
                'if (a0 && reaches_token(r->arguments[0].word, r->self)) return fail(r, ELOOP, "Widget embedding would create a retention cycle");',
                'auto *old_widget = self->widget();',
                'uint32_t old_widget_token = retention_token(r, old_widget, false);']
    return []


def _after_call(g, m):
    p = m.get('retention') or {}
    kind = p.get('custom')
    if kind == 'printer_engines':
        return ['if (self->printEngine() != a0 || self->QPrinter::paintEngine() != a1) return fail(r, EINVAL, "Qt rejected the custom printer engines");',
                'if (!retention_batch.finish(r, 0, true)) return true;',
                *[f'for (auto &edge : retentions) if (edge.owner == r->self && edge.slot == {slot}) edge.native_current = retained_printer_engine;'
                  for slot in p['slots']]]
    if kind == 'debug_result':
        return ['if (!retention_batch.finish(r, r->result.word, true)) return true;']
    if kind == 'debug_copy':
        prefix = [] if p['constructor'] else ['for (auto &edge : retentions) if (edge.owner == r->self) edge = {};']
        return prefix + [f'if (!retention_batch.finish(r, {"r->result.word" if p["constructor"] else "0"}, true)) return true;']
    if kind == 'clear_dependency':
        return [f'for (auto &edge : retentions) if (edge.owner == r->self && edge.slot == {p["slot"]}) edge = {{}};']
    if kind == 'part_append':
        return ['if (!retention_batch.finish(r, 0, true)) return true;']
    if kind == 'reply_body':
        return ['if (!retention_batch.finish(r, r->result.word, true)) return true;']
    if kind == 'constructor_dependencies':
        return ['if (!retention_batch.finish(r, r->result.word, true)) return true;']
    if kind == 'parent' and not p['remove']:
        return [f'if (a{i} && !inside(a{i}, self)) return fail(r, EINVAL, "Qt rejected native QObject adoption");' for i in p['indices']]
    if kind == 'painter':
        if p['constructor']:
            return ['if (!retention_batch.finish(r, r->result.word, true)) return true;']
        condition = '!self->isActive()' if p['end'] else 'self->isActive() && self->device() == a0'
        return [f'if ({condition}) {{ if (!retention_batch.finish(r, 0, true)) return true; }}']
    if kind == 'handle_property':
        i = p['input']
        key = f'static_cast<{p["getter_key_cpp"]}>(r->arguments[{p["key"]}].word)' if p['key'] is not None else ''
        lines = [f'if (!entry(r->self) || (r->arguments[{i}].word && !entry(r->arguments[{i}].word))) return fail(r, ESTALE, "Retained property object was destroyed");']
        if p['getter']:
            call = f'(self->*{p["getter_member"]})({key})' if p.get('getter_member') else f'self->{p["getter"]}({key})'
            lines += [f'if ({call} != a{i}) return fail(r, EINVAL, "Qt rejected the retained property");']
        return lines + ['if (!retention_batch.finish(r, 0, true)) return true;']
    if kind == 'backing':
        owner = 'r->result.word' if p['constructor'] else '0'
        lines = [f'if (!retention_batch.finish(r, {owner}, true)) return true;']
        if p['internal_device']:
            native = p['class']
            lines += [f'auto *stream = get<{native}>(r, r->result.word, {g.ids[native]});',
                      'if (r->error) return true;', 'retention_set_internal_device(r->result.word, stream->device());']
        elif not p['constructor'] and p['class'] != 'QBuffer':
            lines += ['retention_set_internal_device(r->self, nullptr);']
        return lines
    if kind == 'groups':
        constructor = 'r->result.word' if p.get('constructor') else '0'
        return [f'if (!retention_batch.finish(r, {constructor})) return true;']
    if kind == 'style':
        return ['if (!retention_batch.finish(r, 0, true)) return true;']
    if kind == 'popup':
        return ['if (!entry(r->self) || !entry(r->arguments[0].word)) return fail(r, ESTALE, "Popup object was destroyed");',
                'if (self->popup() != a0) return fail(r, EINVAL, "Qt rejected popup ownership");',
                'if (!set_native_owner(r, r->arguments[0].word, r->self)) return true;']
    if kind == 'embedding':
        return ['if (!entry(r->self)) return fail(r, ESTALE, "Graphics proxy was destroyed");',
                'auto *actual_widget = self->widget();',
                'if (old_widget != actual_widget && old_widget_token && entry(old_widget_token) && !set_native_owner(r, old_widget_token, 0)) return true;',
                'if (actual_widget != a0) return fail(r, EINVAL, "Qt rejected widget embedding");',
                'if (!set_native_owner(r, r->arguments[0].word, r->self)) return true;']
    return []


def plan(g, name, f, args, parameters):
    import thread_affinity
    if thread_affinity.handles(f):
        return None  # Native QThread ownership replaces main-thread setter retention.
    import data_proxies
    if data_proxies.handles(g, f):
        return None  # Items are copied; adopted arrays/rows are independent copies.
    import meta_storage
    if meta_storage.handles(f):
        return None
    import runnable_jobs
    if runnable_jobs.handles(f):
        return None  # The job adapter pins queued and running jobs and transfers autoDelete ownership.
    import native_lifetimes
    import scenegraph_lifetimes
    qsg = scenegraph_lifetimes.policy(g, name, f, args)
    if qsg:
        return {'custom': 'qsg', 'qsg': qsg}
    native = native_lifetimes.policy(g, name, f, args)
    if native:
        return {'custom': 'native', 'native': native}
    return _plan(g, name, f, args, parameters)


def before_call(g, m):
    import native_lifetimes
    import scenegraph_lifetimes
    return scenegraph_lifetimes.before(g, m) + native_lifetimes.before(g, m) + _before_call(g, m)


def before_result(g, m):
    import native_lifetimes
    import scenegraph_lifetimes
    f, ret = m['function'], m.get('native_return', m['return'])
    p = m.get('retention') or {}
    if p.get('custom') == 'part_copy' and not p['constructor']:
        return ['if (!retention_batch.finish(r, 0, true)) return true;']
    if (f['declaring_class'], f['name']) in (('QCompleter', 'popup'), ('QGraphicsProxyWidget', 'widget')):
        if ret['kind'] == 'object':
            return [f'if (returned) {{ uint32_t id = borrow(r, returned, {g.ids[ret["name"]]});',
                    '    if (r->error || !set_native_owner(r, id, r->self)) return true; }']
    qsg = scenegraph_lifetimes.before_result(g, m)
    if qsg is not None:
        return qsg
    return native_lifetimes.before_result(g, m)


def after_call(g, m):
    import native_lifetimes
    import scenegraph_lifetimes
    return _after_call(g, m) + native_lifetimes.after(g, m) + scenegraph_lifetimes.after(g, m)


def cpp(g):
    blocker = g.ids.get('QSignalBlocker')
    guards = 'static void dismiss_native_guards(uint32_t) {}\n' if blocker is None else f'''static void dismiss_native_guards(uint32_t id) {{
    // QObject::destroyed runs before registry invalidation. A blocker stores a
    // raw QObject pointer, so revoke its native destructor action immediately.
    for (const auto &edge : retentions) if (edge.target == id) {{
        auto *guard = entry(edge.owner);
        if (guard && guard->type == {blocker}) static_cast<QSignalBlocker *>(guard->value)->dismiss();
    }}
}}
'''
    part = g.ids.get('QHttpPart')
    slot = g.retention_slots.get('QHttpPart.bodyDevice', 0)
    if part is None:
        return guards + 'static uint32_t finish_resource_value_ownership(BqtRequest *, uint32_t id) { return id; }\n'
    return guards + f'''
static uint32_t http_part_device(uint32_t id) {{
    for (const auto &edge : retentions) if (edge.owner == id && edge.slot == {slot}) return edge.target;
    return 0;
}}
static uint32_t finish_resource_value_ownership(BqtRequest *r, uint32_t id) {{
    auto *value = entry(id);
    if (!value || value->type != {part}) return id;
    uint32_t source = native_call_scope && native_call_scope->value_origin ? native_call_scope->value_origin : r->self;
    auto *original = entry(source);
    if (!original || original->type != {part} || source == id) return id;
    uint32_t target = http_part_device(source);
    if (!target) return id;
    BqtRequest check{{}}; check.self = id;
    int index = prepare_retention(&check, {slot}, 0, target);
    if (check.error) {{
        auto *storage = value->value; auto destroy = value->destroy;
        invalidate(id); destroy(storage);
        fail(r, check.error, check.message); return 0;
    }}
    commit_retention(index, id, {slot}, 0, target, nullptr);
    return id;
}}
'''
