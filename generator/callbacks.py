"""Automatic virtual proxies and the Bend/Qt reverse-call transport.

Discovery uses Shiboken's virtual and inheritance metadata. Unsupported virtual
signatures stay in a separate auditable inventory; a class with an unsupported
pure virtual is never advertised as constructible.
"""
import hashlib
import re
import subprocess
from pathlib import Path
import retention
import rendering
import callback_adapters
import video_buffers
import accessible_facets
import effect_transport
from adapters import excluded_internal_api, method_policy, transfers_argument, reverse_transfers_result

HERE = Path(__file__).resolve().parent


def ident(name):
    return re.sub(r'[^A-Za-z0-9_]', '_', name)


def parameter(argument, index):
    cpp = argument['type']['cpp']
    # Named array parameters place the identifier before their dimensions.
    # C++ then applies its ordinary array-to-pointer parameter adjustment.
    if argument['type'].get('array') and '[' in cpp:
        return cpp.replace('[', ' a' + str(index) + '[', 1)
    return cpp + ' a' + str(index)


def signature_id(owner, function):
    key = owner + '::' + function['minimal_signature']
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) or 1


def native(t):
    if t['kind'] == 'object' and t.get('pointer'):
        return t['cpp'].strip()
    return t['cpp'].removeprefix('const ').replace('&', '').strip()


def bend_ident(name):
    return name.replace('::', '.')


def _conversion(g, source, result=False, transfer=False, retained=False):
    if source['reference'] == 2:
        raise ValueError('Reverse calls do not yet support rvalue references')
    if result and (source['reference'] or (source['pointers'] and not (transfer or retained))):
        raise ValueError('Reverse pointer/reference results require an explicit lifetime policy')
    t = g.type(source, result=result)
    forbidden = ('string_view', 'byte_view', 'latin1_view', 'std_string')
    if result and not (transfer or retained):
        forbidden += ('object',)
    if g.conversions.contains(t, forbidden):
        raise ValueError('Reverse conversion requires an owning, independently copyable representation')
    if t['kind'] == 'value' and not g.classes[t['name']].get('copyable', False):
        raise ValueError('Reverse value arguments/results must be copyable')
    if t['kind'] in ('enum', 'enum64', 'flags', 'flags64'):
        # Some virtuals use protected enums. Convert them inside the derived
        # class rather than naming the inaccessible C++ type in a free codec.
        t['codec'] = 'Convert_' + ident(t['bend'])
        t['callback_enum'] = True
        g.conversions.pure.setdefault(t['codec'], t)
    elif t['kind'] != 'void':
        g.conversions.register(t)
    return t


def _record(g, types, prefix):
    records = [dict(t) for t in types]
    for t in records:
        if t.get('callback_enum'):
            t.pop('cpp', None)
    return g.conversions.record(records, prefix=prefix)


def _object_leaves(t):
    return [t] if t['kind'] == 'object' else [leaf for child in t.get('children', []) for leaf in _object_leaves(child)]


def _retained_cleanup(g, t):
    """Release acquired handles after resolve, including derived-only proxies.

    This is only a Bend cleanup codec. It never grants native ownership or
    instantiates a native writer/deleter for an inaccessible base destructor.
    """
    if not _object_leaves(t):
        return t
    copied = dict(t, codec='CallbackResult_' + t['codec'])
    if t['kind'] == 'object':
        copied['owned'] = True
    else:
        copied['children'] = [_retained_cleanup(g, child) for child in t['children']]
    g.conversions.pure.setdefault(copied['codec'], copied)
    return copied


def _retain_leaves(t, wire, depth=0):
    if t['kind'] == 'object':
        return [f'if (!callback_prepare_retained(r, {wire}.word, retained_results)) return false;']
    if not _object_leaves(t):
        return []
    if t['kind'] in ('list', 'array', 'map', 'optional'):
        index = f'retained_index{depth}'
        return [f'for (size_t {index} = 0; {index} < {wire}.count; ++{index}) {{'] + [
            '    ' + line for line in _retain_leaves(t['children'][0], f'{wire}.items[{index}]', depth + 1)] + ['}']
    return [line for i, child in enumerate(t['children']) for line in _retain_leaves(child, f'{wire}.items[{i}]', depth + 1)]


def _retain_container(t, wire):
    return ['RetentionBatch retained_results;'] + _retain_leaves(t, wire) + [
        'if (!retained_results.finish(r)) return false;']


def _decode(t, wire, variable):
    typ = native(t)
    if t.get('callback_enum'):
        expression = f'{typ}::fromInt(wide_bits({wire}))' if t['kind'].startswith('flags') else f'static_cast<{typ}>(wide_bits({wire}))'
        return [f'if (!wire_shape(r, {wire}, 0)) return false;', f'std::optional<{typ}> {variable}{{{expression}}};']
    return [f'auto {variable} = read_{t["native_codec"]}(r, {wire});', f'if (!{variable}) return false;']


def _decode_output(i, t, wire):
    if t.get('callback_scalar_pointer'):
        return [f'auto out{i} = read_{t["native_codec"]}(r, {wire});',
                f'if (!out{i}) return false;',
                f'if (bool(*out{i}) != bool(target->out{i})) {{',
                '    fail(r, EINVAL, "Callback scalar output presence must match the native pointer"); return false;',
                '}']
    if not t.get('callback_pointer_copy'):
        return _decode(t, wire, f'out{i}')
    return [f'std::optional<{native(t)}> out{i};',
            f'if (target->out{i}) {{',
            f'    out{i} = read_{t["native_codec"]}(r, {wire});',
            f'    if (!out{i}) return false;',
            '} else {',
            f'    if (!wire_shape(r, {wire}, 0) || {wire}.word || {wire}.high) {{',
            '        fail(r, EINVAL, "A null native output pointer requires a null reply handle"); return false;',
            '    }',
            '}']


def prepare(g):
    """Call after collect(), before conversions.bend()/cpp_code()."""
    import callback_sampled_images
    import icon_hooks
    g.callback_classes = []
    g.callback_methods = {}
    g.callback_excluded = []
    g.callback_qml = 'QQmlEngine' in g.ids
    if g.callback_qml:
        variant_source = dict(name='QVariant', cpp='QVariant', pointers=0, reference=0, const=False, container=False, enum=False, flags=False, instantiations=[])
        g.callback_variant = g.conversions.register(g.type(variant_source))
        g.callback_variant_list = g.conversions.container(dict(variant_source, name='QList', cpp='QVariantList', container=True, instantiations=[variant_source]), False)
        g.callback_qml_request = _record(g, [dict(kind='u32', bend='U32', raw='U32', cpp='quint32'), g.callback_variant_list], 'QmlArgs_')
    used_ids = {}
    def proxy_observable(c):
        return bool(c.get('virtual_destructor') and c.get('derived_destructible', c.get('public_destructor')) and not c.get('final_cpp'))
    for name in g.selected:
        c = g.classes[name]
        from module_partitions import exports_class
        if not exports_class(g, name):
            continue
        if not (c['qobject'] or proxy_observable(c)) or c.get('final_cpp') or not c.get('derived_destructible', c['public_destructor']):
            continue
        if name == 'QCoreApplication' or 'QCoreApplication' in g.all_bases(name):
            continue
        virtuals, missing = [], []
        for f in g.inherited(name):
            if not f['virtual'] or f['destructor']:
                continue
            try:
                if f.get('final_cpp'):
                    continue
                internal = excluded_internal_api(f)
                if internal:
                    raise ValueError(internal)
                if f['name'].startswith('qt_') or f['name'] in ('metaObject', 'tr'):
                    raise ValueError('Qt-generated metaobject entry point')
                if icon_hooks.matches(f) and f['public'] and not f['user_added']:
                    for hook in icon_hooks.prepare_methods(g, f):
                        key = f['declaring_class'] + '::' + hook['function']['minimal_signature']
                        method_id = hook['method_id']
                        if method_id in used_ids and used_ids[method_id] != key:
                            raise ValueError('Virtual method id hash collision: ' + key)
                        used_ids[method_id] = key
                        virtuals.append(hook)
                        g.callback_methods.setdefault(method_id, hook)
                    continue
                # A private pure virtual may be overridden in C++: access to a
                # base implementation is unnecessary. Native virtual operators
                # use exactly the same typed request/reply path.
                if (f.get('private') and not f['abstract']) or (f['removed'] and not callback_adapters.accessibility_output(f) and not callback_sampled_images.matches(f)) or f['user_added']:
                    raise ValueError('Inaccessible, removed, or language-specific virtual')
                import callback_devices
                device = callback_devices.prepare_method(g, name, f) or callback_sampled_images.prepare_method(g, name, f)
                if device:
                    key = f['declaring_class'] + '::' + f['minimal_signature']
                    method_id = device['method_id']
                    if method_id in used_ids and used_ids[method_id] != key:
                        raise ValueError('Virtual method id hash collision: ' + key)
                    used_ids[method_id] = key
                    virtuals.append(device)
                    g.callback_methods.setdefault(method_id, device)
                    continue
                render_update = f['declaring_class'] == 'QQuickItem' and f['name'] == 'updatePaintNode'
                args = []
                for i, a in enumerate(f['arguments']):
                    adapted = callback_adapters.argument(g, f, i, a)
                    if adapted:
                        args.append(adapted)
                        continue
                    if a.get('removed') or a.get('array'):
                        raise ValueError('Reverse removed/array argument requires an explicit converter')
                    value = g.classes.get(a['type']['name'])
                    if a['type']['pointers'] == 1 and value and value.get('value') and value.get('copyable'):
                        t = _conversion(g, dict(a['type'], pointers=0, reference=0, cpp=a['type']['name']))
                        t['callback_pointer_copy'] = True
                        t['callback_input_only'] = ((render_update and i == 1) or
                            (f['declaring_class'] == 'QScxmlInvokableService' and f['name'] == 'postEvent' and i == 0))
                        args.append(t)
                    else:
                        args.append(_conversion(g, a['type']))
                transfer = (f['return']['pointers'] == 1 and not f['return']['const'] and
                            f['return']['name'] in g.ids and (g.classes[f['return']['name']]['qobject'] or proxy_observable(g.classes[f['return']['name']])) and
                            reverse_transfers_result(f))
                retained = (not transfer and f['return']['pointers'] == 1 and
                            f['return']['name'] in g.ids and
                            (g.classes[f['return']['name']]['qobject'] or proxy_observable(g.classes[f['return']['name']]) or f['return']['name'] == 'QSGMaterialType'))
                copied_pointer = (f['return']['pointers'] == 1 and f['return']['const'] and
                                  f['return']['name'] in g.ids and g.classes[f['return']['name']].get('value') and
                                  g.classes[f['return']['name']].get('copyable'))
                facet = accessible_facets.result(g, f)
                return_source = facet or (dict(f['return'], pointers=0, const=False, cpp=f['return']['name']) if copied_pointer else f['return'])
                candidate = g.type(return_source, result=True)
                leaves = _object_leaves(candidate) if candidate.get('children') else []
                retained_container = bool(leaves) and all(g.classes[t['name']]['qobject'] or proxy_observable(g.classes[t['name']]) for t in leaves)
                ret = _conversion(g, return_source, result=True, transfer=transfer, retained=retained or retained_container)
                ret['callback_transfer'] = transfer
                ret['callback_retained'] = retained
                ret['callback_retained_container'] = retained_container
                ret['callback_copied_pointer'] = copied_pointer
                ret['callback_accessible_facet'] = bool(facet)
                if retained_container:
                    ret = _retained_cleanup(g, ret)
                if f['abstract'] and ret['kind'] == 'value':
                    value = g.classes[ret['name']]
                    default = value.get('adapter') or any(x['constructor'] and x['public'] and
                        all(a.get('native_default') for a in x['arguments']) for x in value['functions'])
                    if not default:
                        raise ValueError('Pure virtual result needs a default value for cancellation')
                owner = f['declaring_class']
                method = signature_id(owner, f)
                key = owner + '::' + f['minimal_signature']
                if method in used_ids and used_ids[method] != key:
                    raise ValueError('Virtual method id hash collision: ' + key)
                used_ids[method] = key
                payload = _record(g, args, 'CallbackArgs_')
                outputs = [(i, t) for i, (a, t) in enumerate(zip(f['arguments'], args))
                           if (a['type']['reference'] == 1 or t.get('callback_pointer_copy') or t.get('callback_scalar_pointer')) and
                           not a['type']['const'] and not t.get('callback_input_only') and t['kind'] != 'object']
                if copied_pointer and outputs:
                    raise ValueError('Stable copied pointer result with mutable outputs needs a combined commit adapter')
                retained_outputs = any(_object_leaves(t) for _, t in outputs)
                if any(not (g.classes[leaf['name']]['qobject'] or proxy_observable(g.classes[leaf['name']]))
                       for _, t in outputs for leaf in _object_leaves(t)):
                    raise ValueError('Reverse output pointer elements require observable destruction')
                if (transfer or retained or retained_container or retained_outputs) and outputs:
                    scalar = {'bool', 'u32', 'i32', 'i64', 'u64', 'real', 'enum', 'enum64', 'flags', 'flags64', 'string', 'duration'}
                    if any(not t.get('callback_scalar_pointer') and t['kind'] not in scalar and not (t['kind'] == 'value' and
                           g.classes[t['name']].get('native_nothrow_move_assignable')) for _, t in outputs):
                        raise ValueError('Combined callback ownership/output commit requires measured noexcept assignment')
                reply_return = g.conversions.owned_objects(ret) if outputs and (transfer or retained) else ret
                response = _record(g, ([] if ret['kind'] == 'void' else [reply_return]) + [_retained_cleanup(g, t) for i, t in outputs], 'CallbackReply_') if outputs else ret
                public = bend_ident(owner) + '.Virtual.' + ident(f['name']) + '_' + str(method)
                item = dict(function=f, args=args, result=response, native_result=ret, outputs=outputs,
                            payload=payload, method_id=method, public=public, render_update=render_update,
                            render_scope=render_update or name.startswith('QSG') or
                            (owner == 'QQuickPaintedItem' and f['name'] == 'paint') or
                            (owner == 'QQuickFramebufferObject' and f['name'] == 'createRenderer') or
                            owner in ('QQuickFramebufferObject::Renderer', 'QQuickRhiItemRenderer', 'QCanvasPainterItemRenderer') or
                            (f['name'] in ('createRenderer', 'createItemRenderer') and
                             f['return']['name'] in ('QQuickRhiItemRenderer', 'QCanvasPainterItemRenderer')))
                # Qt's SCXML dispatcher allocates the event and transfers it to
                # postEvent. A Bend implementation consumes it even on failure.
                item['consumed_arguments'] = ([(0, 'QScxmlEvent')] if
                    owner == 'QScxmlInvokableService' and f['name'] == 'postEvent' else [])
                virtuals.append(item)
                g.callback_methods.setdefault(method, item)
            except ValueError as error:
                issue = dict(class_name=name, signature=f['minimal_signature'], pure=bool(f['abstract']), reason=str(error))
                g.callback_excluded.append(issue)
                if f['abstract']:
                    missing.append(issue)
        if missing or not virtuals:
            continue
        constructors = []
        for f in c['functions']:
            if not f['constructor'] or f['copy_constructor'] or f['removed'] or f['user_added']:
                continue
            if not f['public'] and not f.get('protected'):
                continue
            try:
                reason = method_policy(name, f, g.all_bases(name))
                if reason:
                    raise ValueError(reason)
                args, plan, outputs = g.parameters(f)
                if any(t.get('name') == 'ImageBuffer' for t in args):
                    raise ValueError('Image-buffer cleanup constructors use the owning QImage.fromBuffer adapter; proxy construction requires the copied-image constructor')
                if outputs or any(a.get('rvalue') or 'buffer' in a for a in args):
                    raise ValueError('Proxy constructor needs ordinary value inputs')
                if len(plan) != len(args):
                    raise ValueError('Proxy constructor removed argument conversion is unavailable')
                for t in args:
                    if t['raw'] == 'Wire':
                        g.conversions.register(t)
                default = all(a.get('native_default') for a in f['arguments'])
                constructor_retention = retention.plan(g, name, f, args, plan)
                default_retention = retention.plan(g, name, f, [], []) if default else None
                constructors.append(dict(function=f, args=args, parameters=plan, retention=constructor_retention,
                    default_retention=default_retention, default=default))
            except ValueError as error:
                g.callback_excluded.append(dict(class_name=name, signature=f['minimal_signature'], pure=False, reason=str(error)))
        if constructors:
            g.callback_classes.append(dict(name=name, virtuals=virtuals, constructors=constructors))
    import callback_functions
    callback_functions.prepare(g)
    import message_handlers
    message_handlers.prepare(g)
    import callback_names
    callback_names.assign(g)


def emit(g):
    g.runtime_default_constructors = {}
    import callback_sampled_images
    callback_sampled_images.emit(g)
    import icon_hooks
    icon_hooks.emit(g)
    """Append ordinary packaged effects and typed callback response helpers."""
    word = dict(kind='u32', bend='U32', raw='U32')
    unit = dict(kind='void', bend='Unit', raw='Unit')
    wire = dict(kind='wire', bend='Wire', raw='Wire', codec='HandlerWire')
    g.bend += ['def HandlerWire.encode(value: Wire) -> Wire:', '  value', '']
    if 'QSGMaterialType' in g.ids:
        operation = g.next_id
        g.next_id += 1
        g.cases.append(f'''case {operation}: {{
    auto key = QString::fromUtf8(r->arguments[0].text, qsizetype(r->arguments[0].size));
    auto &types = callback_material_types();
    QSGMaterialType *value = nullptr;
    for (const auto &identity : types)
        if (identity.first == key) {{ value = identity.second.get(); break; }}
    if (!value) {{
        types.emplace_back(key, std::make_unique<QSGMaterialType>());
        value = types.back().second.get();
    }}
    for (uint32_t i = 1; i < capacity; ++i) {{
        auto &e = entries[i];
        if (e.value == value && e.type == {g.ids['QSGMaterialType']}) {{
            r->result.word = token(i, e.generation); return true;
        }}
    }}
    r->result.word = insert(r, value, nullptr, {g.ids['QSGMaterialType']}, [](void *) {{}}, true, NativeTraits<QSGMaterialType>::cast);
    if (auto *e = entry(r->result.word)) {{ e->native_observed = true; e->render_only = false; }}
    return true;
}}''')
        g.emit_effect('QSGMaterialType.identifier', [('key', dict(kind='string', bend='String', raw='String'))],
                      dict(kind='object', bend='QSGMaterialType', raw='U32'), operation)
    g.bend.append((HERE / 'templates/handlers.bend').read_text().removeprefix('import Base\n\n'))
    g.callback_operations = {}
    for public, params, result, function, has_self in [
        ('Handler.answer', [('self', word), ('value', wire)], unit, 'callback_resolve', True),
    ]:
        operation = g.next_id
        g.next_id += 1
        g.callback_operations[function] = operation
        g.cases.append(f'case {operation}: {{\n    return {function}(r);\n}}')
        g.emit_effect(public, params, result, operation, has_self=has_self)
    install = g.next_id
    g.next_id += 1
    g.callback_operations['callback_install'] = install
    g.cases.append(f'case {install}: {{\n    return callback_install(r);\n}}')
    # Every request wrapper is declared before the def that registers it.
    import signals
    for method in g.callback_methods.values():
        public, ret, payload = method['public'], method['result'], method['payload']
        scope = ret['bend'] if ret.get('callback_transfer') or ret.get('callback_retained') else None
        method['handler'] = signals.invoke(g, public, [t['bend'] for t in method['args']], payload, ret, scope)
        if '.Virtual.' not in public:
            continue
        receiver = dict(kind='object', bend=public.split('.Virtual.')[0], raw='U32')
        g.emit_effect(public + '.handle', [('self', receiver), ('method', dict(word, constant=method['method_id'])),
                      ('state', effect_transport.handler(method['handler'], public + '.invoke'))],
                      unit, install, has_self=True)
    import callback_functions
    callback_functions.emit(g)
    import message_handlers
    message_handlers.emit(g)
    accessible_facets.emit(g)
    import rhi_cleanup
    rhi_cleanup.bend_helpers(g)
    if g.callback_qml:
        # QML calls `bridge.invoke(method, [arguments])` on a BendBridge whose
        # `handler` property is a token from Qml.handler.
        text = dict(kind='string', bend='String', raw='String')
        variants = g.callback_variant_list
        request = g.callback_qml_request
        function = signals.invoke(g, 'Internal.Qml.Handler', ['U32', variants['bend']], request, g.callback_variant)
        g.types['QmlHandler'] = 'handle'
        for public, params, result, operation_name in [
            ('Internal.Qml.installBridge', [], unit, 'callback_qml_install'),
            ('Qml.registerSource', [('uri', text), ('major', word), ('minor', word), ('name', text), ('source', text)], word, 'callback_qml_register_source'),
            ('Internal.Qml.handler', [('state', effect_transport.handler(function, 'Internal.Qml.Handler.invoke'))],
             dict(kind='object', bend='QmlHandler', raw='U32'), 'callback_qml_handler'),
            ('QmlHandler.release', [('self', dict(bend='QmlHandler', raw='U32'))], unit, 'callback_qml_release')]:
            operation = g.next_id
            g.next_id += 1
            g.cases.append(f'case {operation}: {{\n    return {operation_name}(r);\n}}')
            g.emit_effect(public, params, result, operation, has_self=public == 'QmlHandler.release')
        g.emit_scope('QmlHandler', 'release')
        import scope_actions
        scope_actions.escapes(g, 'QmlHandler', 2)
    for c in g.callback_classes:
        name = c['name']
        native_class = 'BqtProxy_' + ident(name)
        c['factories'] = []
        c['schema_constructors'] = []
        return_type = dict(kind='object', bend=bend_ident(name), raw='U32')
        for constructor in c['constructors']:
            f, args = constructor['function'], constructor['args']
            # Named by callback_names; the zero-argument variant comes first.
            for inputs, suffix in constructor['override_variants']:
                operation = g.next_id
                g.next_id += 1
                if not inputs:
                    g.runtime_default_constructors.setdefault(name, operation)
                def shift(text):
                    return text
                adapted = dict(class_name=name, **{'class': name}, function=f, args=inputs,
                               parameters=constructor['parameters'], return_=return_type,
                               retention=constructor['retention'] if inputs else constructor['default_retention'])
                adapted['return'] = return_type
                lines = ['bendqt::NativeCallScope native_scope;']
                if any(base in {'QQuickFramebufferObject', 'QQuickFramebufferObject::Renderer',
                                'QQuickPaintedItem', 'QQuickRhiItem', 'QQuickRhiItemRenderer'}
                       for base in [name] + g.all_bases(name)):
                    lines += ['if (!gui_render_enabled) return fail(r, EPERM, "Render proxy construction requires Render.useGuiThread before any Quick window");']
                expressions = []
                for i, t in enumerate(inputs):
                    declarations, expression = g.argument(t, i)
                    lines.extend(shift(line) for line in declarations)
                    expressions.append(shift(expression))
                lines += ['if (r->error) return true;']
                import volume_data
                lines += volume_data.override_before(g, f, inputs, expressions)
                lines += rendering.before_call(g, adapted)
                import webview_runtime
                lines += webview_runtime.before_call(g, adapted)
                for policy in f['policies']:
                    if transfers_argument(f, policy) and policy['target_ownership'] == 3 and policy['index'] <= len(inputs) and not inputs[policy['index'] - 1].get('native_copy_adoption'):
                        lines += [f'if (!can_transfer_handle(r, r->arguments[{policy["index"]}].word)) return true;']
                lines += [shift(line) for line in retention.before_call(g, adapted)]
                registration = f'own(r, static_cast<{name} *>(value), {g.ids[name]})'
                if not g.classes[name]['public_destructor']:
                    deleter = f'[](void *p) {{ delete static_cast<{native_class} *>(static_cast<{name} *>(p)); }}'
                    obj = 'static_cast<QObject *>(value)' if g.classes[name]['qobject'] else 'nullptr'
                    registration = f'insert(r, static_cast<{name} *>(value), {obj}, {g.ids[name]}, {deleter}, true, NativeTraits<{name}>::cast)'
                if g.classes[name]['qobject']:
                    placed_registration = f'insert(r, static_cast<{name} *>(value), static_cast<QObject *>(value), {g.ids[name]}, nullptr, false, NativeTraits<{name}>::cast)'
                    registration = f'(runtime_pending_placement && runtime_pending_placement->object == value ? {placed_registration} : {registration})'
                import convenience_apis
                lines += convenience_apis.constructor_before(g, f, expressions)
                expressions = convenience_apis.constructor_arguments(f, expressions)
                lines += [
                          f'auto *value = callback_construct<{native_class}>(r' + ''.join(', ' + x for x in expressions) + ');',
                          'if (r->error) return true;',
                          f'CallbackConstruction<{native_class}> construction{{value}};',
                          *volume_data.override_after(f, inputs),
                          f'r->result.word = {registration};',
                          'if (runtime_pending_placement && runtime_pending_placement->object == value) runtime_pending_placement->handle = r->result.word;' if g.classes[name]['qobject'] else '',
                          'construction.handle = r->result.word;',
                          'if (r->error) { if (!r->result.word) construction.release(); return true; }',
                          'value->bqt_receiver = r->result.word;',
                          'callback_observe(r->result.word, value->bqt_alive, &value->bqt_handlers);']
                if not g.classes[name]['qobject']:
                    lines += ['mark_native_observed(r->result.word);']
                lines += ['reconcile_parents();']
                for policy in f['policies']:
                    if transfers_argument(f, policy) and policy['target_ownership'] == 3 and policy['index'] <= len(inputs) and not inputs[policy['index'] - 1].get('native_copy_adoption'):
                        lines += [f'set_owned(r->arguments[{policy["index"]}].word, false);']
                lines += [shift(line) for line in retention.after_call(g, adapted)]
                lines += convenience_apis.constructor_after(g, f, expressions)
                lines += ['construction.release();', 'return true;']
                lines = [re.sub(r'(?<![:\w])(get|own|insert|invalidate)(?=[<(])', r'bendqt::\1', line) for line in lines]
                # A Qt class can share its basename with an unrelated global
                # class (Qt3DInput::QKeyEvent versus ::QKeyEvent). Type lookup
                # inside this derived scope must preserve the extractor's name.
                lines = _qualify_get_types(g, lines)
                factory = 'bqt_create_' + str(operation)
                c['factories'].append((factory, lines))
                g.cases.append(f'case {operation}: {{\n    return {native_class}::{factory}(r);\n}}')
                g.emit_effect(bend_ident(name) + suffix, [(f'arg{i}', t) for i, t in enumerate(inputs)], return_type, operation)
                schema_name = constructor.get('schema_names', {}).get(bend_ident(name) + suffix)
                if schema_name:
                    c['schema_constructors'].append(dict(name=schema_name, operation=operation, inputs=inputs))
                if not g.classes[name]['qobject']:
                    for carrier in g.selected:
                        if g.classes[carrier].get('shared_target') == name:
                            _emit_shared_factory(g, c, carrier, suffix, f, inputs, expressions, adapted, shift)


def _qualify_get_types(g, lines):
    def qualify(match):
        name = match[1]
        cls = g.classes.get(name, {})
        namespace = cls.get('native_namespace', '::bendqt::' if cls.get('adapter') else '::')
        return 'bendqt::get<' + namespace + name
    return [re.sub(r'bendqt::get<(?!::)([A-Za-z_][\w:]*)', qualify, line) for line in lines]


def _emit_shared_factory(g, c, carrier, suffix, function, inputs, expressions, adapted, shift):
    name = c['name']
    proxy = 'BqtProxy_' + ident(name)
    operation = g.next_id
    g.next_id += 1
    lines = ['bendqt::NativeCallScope native_scope;']
    for i, t in enumerate(inputs):
        declarations, _ = g.argument(t, i)
        lines += [shift(line) for line in declarations]
    lines += ['if (r->error) return true;']
    import volume_data
    expressions = list(expressions)
    lines += volume_data.override_before(g, function, inputs, expressions)
    lines += rendering.before_call(g, adapted)
    for policy in function['policies']:
        if transfers_argument(function, policy) and policy['target_ownership'] == 3 and policy['index'] <= len(inputs) and not inputs[policy['index'] - 1].get('native_copy_adoption'):
            lines += [f'if (!can_transfer_handle(r, r->arguments[{policy["index"]}].word)) return true;']
    lines += [shift(line) for line in retention.before_call(g, adapted)]
    lines += [f'auto shared = callback_construct_shared<{proxy}>(r' + ''.join(', ' + x for x in expressions) + ');',
              'if (r->error) return true;', 'auto *value = shared.data();',
              *volume_data.override_after(function, inputs),
              f'r->result.word = insert(r, static_cast<{name} *>(value), nullptr, {g.ids[name]}, nullptr, false, NativeTraits<{name}>::cast);',
              'if (r->error) return true;', 'value->bqt_receiver = r->result.word;',
              'callback_observe(r->result.word, value->bqt_alive, &value->bqt_handlers);',
              'mark_native_observed(r->result.word);',
              'entry(r->result.word)->shared_managed = true;']
    for policy in function['policies']:
        if transfers_argument(function, policy) and policy['target_ownership'] == 3 and policy['index'] <= len(inputs) and not inputs[policy['index'] - 1].get('native_copy_adoption'):
            lines += [f'set_owned(r->arguments[{policy["index"]}].word, false);']
    lines += [shift(line) for line in retention.after_call(g, adapted)]
    lines += ['if (r->error) return true;',
              f'auto holder = own(r, new {carrier}(shared), {g.ids[carrier]});',
              'if (r->error) return true;', 'CallbackOwnedRegistration registration{holder};',
              f'borrow_shared(r, static_cast<{name} *>(value), {g.ids[name]}, holder);',
              'if (r->error) return true;', 'r->result.word = holder;',
              'registration.release();', 'return true;']
    lines = [re.sub(r'(?<![:\w])(get|own|invalidate)(?=[<(])', r'bendqt::\1', line) for line in lines]
    lines = _qualify_get_types(g, lines)
    factory = 'bqt_create_shared_' + str(operation)
    c['factories'].append((factory, lines))
    g.cases.append(f'case {operation}: {{\n    return {proxy}::{factory}(r);\n}}')
    g.emit_effect(carrier + suffix,
                  [(f'arg{i}', t) for i, t in enumerate(inputs)],
                  dict(kind='value', bend=carrier, raw='U32'), operation)


def thread_branch(method, result_type, values, fallback, callback_fallback):
    """Bend runs on the main thread: bring a call from another thread there."""
    f = method['function']
    lines = ['        if (QThread::currentThread() != main_thread) {']
    if method.get('render_scope'):
        # The caller's graphics context is current on its own thread only.
        return lines + ['            ' + callback_fallback, '        }']
    lines += [f'            return callback_from_thread<{result_type}>(bqt_alive,',
              f'                [&]() -> {result_type} {{ return this->{f["name"]}({values}); }},',
              f'                [&]() -> {result_type} {{ {fallback} }});',
              '        }']
    return lines


def _constructor_factory_parts(c):
    """Keep proxy layout shared while compiling each constructor body once."""
    proxy = 'BqtProxy_' + ident(c['name'])
    declarations, definitions = [], []
    for factory, body in c.get('factories', []):
        matched = re.fullmatch(r'bqt_create_(?:shared_)?([0-9]+)', factory)
        if not matched:
            raise ValueError('Unexpected proxy constructor factory: ' + factory)
        operation = matched[1]
        declarations.append(f'    static bool {factory}(BqtRequest *r);')
        definition = (f'bool __attribute__((noinline, visibility("hidden"))) {proxy}::{factory}(BqtRequest *r) {{\n'
                      + '\n'.join('    ' + line for line in body) + '\n}\n')
        definitions.append(f'// BQT_AUXILIARY_BEGIN proxy_constructors {operation}\n' + definition
                           + f'// BQT_AUXILIARY_END proxy_constructors {operation}\n')
    return declarations, definitions


def _guard_proxy_definition(definition):
    # Auxiliary extraction removes the surrounding proxy guard. Carry the same
    # guard inside the extracted definition, including body-only dependencies.
    first, body = definition.split('\n', 1)
    body, last = body.rsplit('// BQT_AUXILIARY_END ', 1)
    return first + '\n#if BQT_HAS_RHI\n' + body + '#endif\n// BQT_AUXILIARY_END ' + last


def _virtual_body_parts(proxy, identifier, name, result, parameters, qualifier, body):
    """Preserve class-scope type lookup with a trailing return in the body."""
    declaration = f'    {result} {name}({parameters}){qualifier} override;'
    definition = (f'auto __attribute__((noinline, visibility("hidden"))) {proxy}::{name}({parameters}){qualifier} -> {result} {{\n'
                  + '\n'.join(body) + '\n}\n')
    return declaration, (f'// BQT_AUXILIARY_BEGIN proxy_virtuals {identifier}\n' + definition
                         + f'// BQT_AUXILIARY_END proxy_virtuals {identifier}\n')


def qml_property_map_metadata():
    """A const provider keeps Qt's templated constructor's metadata lookup."""
    return ['    struct MetaProvider {',
            '        const QMetaObject *operator&() const {',
            '            const auto *meta = runtime_construction_meta;',
            '            if (!meta || !meta->inherits(&QQmlPropertyMap::staticMetaObject)) return &QQmlPropertyMap::staticMetaObject;',
            '            runtime_construction_meta = nullptr; return meta;',
            '        }',
            '    };', '    static inline const MetaProvider staticMetaObject;']


def cpp(g):
    """Place after conversions.cpp_code(), before dispatch functions."""
    import callback_functions
    lines = [callback_functions.cpp(g)]
    virtual_definitions = []
    virtual_identifier = 0
    if 'QSGMaterialType' in g.ids:
        lines += ['// Canonical material identities outlive all Qt renderer caches. Handle cleanup does not delete them.',
                  'static auto &callback_material_types() {',
                  '    // Deliberately process-lifetime: Qt cache teardown order must not invalidate type keys.',
                  '    static auto *types = new std::vector<std::pair<QString, std::unique_ptr<QSGMaterialType>>>;',
                  '    return *types;', '}', '']
    if g.callback_qml:
        qml = (HERE / 'templates/callback_qml.cpp').read_text()
        qml = qml.replace('@QOBJECT_ID@', str(g.ids['QObject'])).replace('@VARIANT_CODEC@', g.callback_variant['native_codec']).replace('@VARIANT_LIST_CODEC@', g.callback_variant_list['native_codec'])
        lines.append(qml)
    for c in g.callback_classes:
        name = c['name']
        proxy_start = len(lines)
        class_virtual_definitions = []
        native_base = g.classes[name].get('convenience_base_cpp', name)
        qobject = g.classes[name]['qobject']
        import qt_objects
        dynamic_schema = qobject and qt_objects.eligible(g, c)
        host = ', public RuntimeObjectHost' if dynamic_schema else ''
        lines += [f'class BqtProxy_{ident(name)} final : public NativeDeletionObserver, public {native_base}{host} {{', 'public:',
                  '    uint32_t bqt_receiver = 0;',
                  '    std::shared_ptr<std::atomic<bool>> bqt_alive = std::make_shared<std::atomic<bool>>(true);',
                  '    CallbackHandlers bqt_handlers;',
                  '    static bool bqt_accepts(uint32_t method) {',
                  '        switch (method) {',
                  *[f'        case {method_id}u:' for method_id in sorted({m['method_id'] for m in c['virtuals']})],
                  '            return true;', '        default: return false;', '        }', '    }']
        if name == 'QQmlPropertyMap' and dynamic_schema:
            lines += qml_property_map_metadata()
            lines += ['    explicit BqtProxy_QQmlPropertyMap(QObject *parent = nullptr)',
                      '        : QQmlPropertyMap(this, parent) { NativeDeletionObserver::observe(static_cast<QQmlPropertyMap *>(this)); bqt_handlers.accepts = bqt_accepts; }']
        else:
            lines += [f'    template<class... A> explicit BqtProxy_{ident(name)}(A&&... args)',
                      f'        : {native_base}(std::forward<A>(args)...) {{ NativeDeletionObserver::observe(static_cast<{name} *>(this)); bqt_handlers.accepts = bqt_accepts; }}']
        lines += [f'    ~BqtProxy_{ident(name)}() override {{ NativeDeletionObserver::begin(); callback_proxy_destroyed(bqt_receiver, bqt_alive, bqt_handlers); }}']
        if dynamic_schema:
            lines += [f'    static constexpr uint16_t bqt_native_base = {g.ids[name]};',
                      f'    uint16_t runtime_base_id() const noexcept override {{ return {g.ids[name]}; }}',
                      '    void runtime_observe(uint32_t id) override { bqt_receiver = id; callback_observe(id, bqt_alive, &bqt_handlers); }',
                      f'    const QMetaObject *metaObject() const override {{ return runtime_object_meta(bqt_object, {name}::metaObject()); }}',
                      f'    void *qt_metacast(const char *type) override {{ if (runtime_object_cast(bqt_object, type)) return this; return {name}::qt_metacast(type); }}',
                      f'    int qt_metacall(QMetaObject::Call call, int index, void **arguments) override {{ return runtime_object_metacall(this, bqt_object, call, {name}::qt_metacall(call, index, arguments), arguments, bqt_alive); }}']
        lines += video_buffers.proxy_members(c)
        for method in c['virtuals']:
            ret = method['native_result']
            if ret.get('callback_copied_pointer'):
                lines += [f'    mutable std::vector<std::unique_ptr<{native(ret)}>> bqt_copies_{method["method_id"]};']
        import callback_sampled_images
        lines += callback_sampled_images.configuration_cpp(g, name)
        import icon_hooks
        lines += icon_hooks.configuration_cpp(g, c)
        factory_declarations, factory_definitions = _constructor_factory_parts(c)
        lines += factory_declarations
        for method in c['virtuals']:
            if method.get('sampled_images'):
                import callback_sampled_images
                lines += callback_sampled_images.cpp(g, name, method)
                continue
            if method.get('device_io'):
                import callback_devices
                lines += callback_devices.cpp(g, name, method)
                continue
            f, ret, args = method['function'], method['native_result'], method['args']
            outputs = method['outputs']
            parameters = ', '.join(parameter(a, i) for i, a in enumerate(f['arguments']))
            qualifier = (' const' if f['const'] else '') + (' noexcept' if f.get('noexcept') else '')
            result_type = f['return']['cpp']
            override = '' if method.get('icon_hook') else ' override'
            method_start = len(lines)
            lines.append(f'    {result_type} {f["name"]}({parameters}){qualifier}{override} {{')
            values = ', '.join('a' + str(i) for i in range(len(args)))
            base_call = (f'{f["name"]}_base({values})' if method.get('icon_hook') else f'{native_base}::{f["name"]}({values})')
            fallback = ('return;' if ret['kind'] == 'void' else 'return {};') if f['abstract'] else ('{ ' + base_call + '; return; }' if ret['kind'] == 'void' else 'return ' + base_call + ';')
            callback_fallback = 'return a0;' if method['render_update'] else fallback
            # Installing the registry's destruction observer invokes the native
            # connectNotify virtual before the receiver token is assigned.
            initial_cleanup = ''.join(f'delete a{i}; ' for i, _ in method.get('consumed_arguments', []))
            lines += ['        if (!bqt_receiver) { ' + initial_cleanup + fallback + ' }',
                      f'        uint32_t handler = bqt_handlers.find({method["method_id"]}u);']
            if f['abstract']:
                lines += ['        if (!handler) { ' + initial_cleanup + 'callback_report_error(ENOSYS, "A pure virtual method has no Bend handler"); ' + fallback + ' }']
            else:
                lines += ['        if (!handler) { ' + initial_cleanup + fallback + ' }']
            lines += video_buffers.callback_before_thread(f)
            lines += thread_branch(method, result_type, values, fallback, callback_fallback)
            lines += [f'        std::unique_ptr<{typ}> consumed{i}(a{i});' for i, typ in method.get('consumed_arguments', [])]
            lines += video_buffers.callback_entry(f)
            lines += ['        try {']
            lines += ['        BqtRequest conversion{};']
            lines += video_buffers.callback_setup(f, callback_fallback)
            if method['render_scope']:
                lines += ['        GuiRenderScope render_scope(&conversion, bqt_receiver);',
                          '        if (!render_scope.active) { callback_report_error(conversion.error); ' + callback_fallback + ' }']
            lines += ['        CallbackNativeArguments native_arguments;', f'        CallbackOwnedArguments arguments{{sequence_value({len(args)})}};']
            lines += ['        { NativeAggregateInputScope native_fields(&conversion);']
            for i, t in enumerate(args):
                if t.get('callback_array_count') is not None:
                    import callback_arrays
                    lines += callback_arrays.encode(g, i, t, ret['kind'] != 'void')
                elif t.get('callback_owned_bytes'):
                    if t.get('callback_bytes_view'):
                        value = f'QByteArray(a{i}.data(), a{i}.size())'
                    else:
                        count = f'a{t["callback_bytes_count"]}'
                        done = 'return {};' if ret['kind'] != 'void' else 'return;'
                        lines += [f'        if ({count} < 0 || uint64_t({count}) > uint64_t(std::numeric_limits<qsizetype>::max()) || (!a{i} && {count})) {{ callback_report_error(ERANGE, "Native callback byte extent is invalid"); {done} }}']
                        value = f'QByteArray(static_cast<const char *>(static_cast<const void *>(a{i})), qsizetype({count}))'
                    lines += [f'        arguments.value.items[{i}] = write_{t["native_codec"]}(&conversion, {value});']
                elif t.get('callback_native_event'):
                    lines += [f'        NativeEvent native_event{i}{{a0, a{i}}};',
                              f'        arguments.value.items[{i}] = native_arguments.borrow_argument(&conversion, &native_event{i}, {g.ids["NativeEvent"]}, bqt_receiver);']
                elif t.get('callback_cstring'):
                    lines += [f'        arguments.value.items[{i}] = write_{t["native_codec"]}(&conversion, a{i} ? std::optional<QString>{{QString::fromUtf8(a{i})}} : std::nullopt);']
                elif t.get('callback_scalar_pointer'):
                    initializer = 'std::in_place' if t.get('callback_output_only') else f'*a{i}'
                    lines += [f'        arguments.value.items[{i}] = write_{t["native_codec"]}(&conversion, a{i} ? std::optional<{t["callback_pointee"]}>{{{initializer}}} : std::nullopt);']
                elif t.get('callback_pointer_copy'):
                    lines += [f'        if (a{i}) arguments.value.items[{i}] = write_{t["native_codec"]}(&conversion, *a{i});']
                elif t['kind'] == 'object' and not g.classes[t['name']]['qobject']:
                    value = f'a{i}' if t.get('pointer') else f'&a{i}'
                    lines += [f'        arguments.value.items[{i}] = native_arguments.borrow_argument(&conversion, {value}, {g.ids[t["name"]]}, bqt_receiver);']
                elif t.get('callback_enum'):
                    expression = f'a{i}.toInt()' if t['kind'].startswith('flags') else f'a{i}'
                    lines += [f'        arguments.value.items[{i}] = wide_value(uint64_t({expression}));']
                else:
                    value = f'&a{i}' if t['kind'] == 'object' and not t.get('pointer') else f'a{i}'
                    lines += [f'        arguments.value.items[{i}] = write_{t["native_codec"]}(&conversion, {value});']
            lines += ['        }', '        if (conversion.error) { callback_report_error(conversion.error, conversion.message); ' + callback_fallback + ' }']
            if outputs:
                has_result = ret['kind'] != 'void'
                lines += ['        struct Reply {']
                if has_result:
                    lines += [f'            std::optional<{native(ret)}> result;']
                lines += [f'            {t.get("callback_pointee", native(t))} *out{i};' for i, t in outputs]
                lines += ['        };', '        Reply result{' + ', '.join((['std::nullopt'] if has_result else []) + [('a' if t.get('callback_pointer_copy') or t.get('callback_scalar_pointer') else '&a') + str(i) for i, t in outputs]) + '};',
                          '        auto decode = [](BqtRequest *r, const BqtValue &wire, void *destination) {',
                          f'            if (!wire_shape(r, wire, 2, {len(outputs) + int(has_result)})) return false;',
                          '            auto *target = static_cast<Reply *>(destination);']
                position = 0
                if has_result:
                    lines += ['            ' + line for line in _decode(ret, 'wire.items[0]', 'returned')]
                    position = 1
                for n, (i, t) in enumerate(outputs, position):
                    lines += ['            ' + line for line in _decode_output(i, t, f'wire.items[{n}]')]
                lines += ['            ' + line for line in callback_adapters.validate_reply(f)]
                retained_outputs = any(_object_leaves(t) for _, t in outputs)
                if ret.get('callback_transfer') or ret.get('callback_retained') or ret.get('callback_retained_container') or retained_outputs:
                    lines += [f'            static_assert(std::is_nothrow_move_assignable_v<{native(t)}>);' for _, t in outputs]
                    lines += ['            RetentionBatch retained_results;']
                    if ret.get('callback_retained_container'):
                        lines += ['            ' + line for line in _retain_leaves(ret, 'wire.items[0]')]
                    elif ret.get('callback_retained'):
                        lines += ['            if (!callback_prepare_retained(r, wire.items[0].word, retained_results)) return false;']
                    for n, (i, t) in enumerate(outputs, int(has_result)):
                        lines += ['            ' + line for line in _retain_leaves(t, f'wire.items[{n}]')]
                    if ret.get('callback_transfer'):
                        lines += ['            if (!callback_transfer_result(r, wire.items[0].word)) return false;']
                    lines += ['            if (!retained_results.finish(r)) return false;']
                if has_result:
                    lines += ['            target->result = std::move(returned);']
                lines += [f'            if (target->out{i}) *target->out{i} = std::move({"**" if t.get("callback_scalar_pointer") else "*"}out{i});' for i, t in outputs]
                lines += ['            return true;', '        };',
                          f'        int error = callback_invoke(handler, bqt_receiver, arguments.take(), decode, &result);',
                          '        if (error' + ('' if f['abstract'] else ' && error != ENOSYS') + ') callback_report_error(error);',
                          '        if (error' + (' || !result.result' if has_result else '') + ') ' + callback_fallback]
                if has_result:
                    lines += ['        return std::move(*result.result);']
            elif ret.get('callback_accessible_facet'):
                lines += accessible_facets.decode(g)
                lines += [f'        int error = callback_invoke(handler, bqt_receiver, arguments.take(), decode, &result);',
                          '        if (error && error != ENOSYS) callback_report_error(error);',
                          '        if (error) ' + callback_fallback,
                          '        return result.pointer;']
            elif ret.get('callback_copied_pointer'):
                typ, method_id = native(ret), method['method_id']
                lines += [f'        struct Reply {{ const BqtProxy_{ident(name)} *self; const {typ} *value = nullptr; }};',
                          '        Reply result{this};',
                          '        auto decode = [](BqtRequest *r, const BqtValue &wire, void *destination) {',
                          '            if (!wire_shape(r, wire, 0)) return false;',
                          f'            auto *source = bendqt::get<::{typ}>(r, wire.word, {g.ids[ret["name"]]}, true, false);',
                          '            if (r->error) return false;',
                          '            auto *target = static_cast<Reply *>(destination);',
                          '            if (!source) { target->value = nullptr; return true; }',
                          f'            auto copy = std::make_unique<{typ}>(*source);',
                          f'            target->self->bqt_copies_{method_id}.push_back(std::move(copy));',
                          f'            target->value = target->self->bqt_copies_{method_id}.back().get();',
                          '            return true;', '        };',
                          f'        int error = callback_invoke(handler, bqt_receiver, arguments.take(), decode, &result);',
                          '        if (error' + ('' if f['abstract'] else ' && error != ENOSYS') + ') callback_report_error(error);',
                          '        if (error) ' + callback_fallback,
                          '        return result.value;']
            elif ret['kind'] == 'void':
                lines += [f'        int error = callback_invoke(handler, bqt_receiver, arguments.take(), callback_decode_unit, nullptr);',
                          '        if (error' + ('' if f['abstract'] else ' && error != ENOSYS') + ') callback_report_error(error);',
                          '        if (error) ' + callback_fallback]
            else:
                typ = native(ret)
                read = ['            ' + line for line in _decode(ret, 'wire', 'value')]
                lines += [f'        std::optional<{typ}> result;',
                          '        auto decode = [](BqtRequest *r, const BqtValue &wire, void *destination) {', *read,
                          '            if (!value) return false;',
                          *video_buffers.callback_decode(f),
                          *([f'            if (!callback_transfer_result(r, wire.word, {str(method["render_update"]).lower()})) return false;'] if ret.get('callback_transfer') else []),
                          *(['            if (!callback_retain_result(r, wire.word)) return false;'] if ret.get('callback_retained') else []),
                          *(['            ' + line for line in _retain_container(ret, 'wire')] if ret.get('callback_retained_container') else []),
                          f'            *static_cast<std::optional<{typ}> *>(destination) = std::move(value);',
                          '            return true;', '        };',
                          f'        int error = callback_invoke(handler, bqt_receiver, arguments.take(), decode, &result);',
                          '        if (error' + ('' if f['abstract'] else ' && error != ENOSYS') + ') callback_report_error(error);',
                          '        if (error || !result) ' + callback_fallback,
                          *(['        render_factory_replacing(bqt_receiver, a0, *result);',
                             '        if (*result != a0) delete a0;',
                             '        render_factory_replaced(bqt_receiver, a0, *result);'] if method['render_update'] else []),
                          '        return std::move(*result);']
            lines += ['        } catch (const std::bad_alloc &) {',
                      '            callback_report_error(ENOMEM);',
                      '            ' + callback_fallback,
                      '        } catch (...) {',
                      '            callback_report_error(EFAULT);',
                      '            ' + callback_fallback, '        }', '    }']
            if override:
                declaration, definition = _virtual_body_parts('BqtProxy_' + ident(name), virtual_identifier,
                    f['name'], result_type, parameters, qualifier, lines[method_start + 1:-1])
                virtual_identifier += 1
                lines[method_start:] = [declaration]
                class_virtual_definitions.append(definition)
        lines += ['};']
        import abi_cohorts
        proxy = 'BqtProxy_' + ident(name)
        # Preserve the previous whole-class ABI classification, which included
        # constructor bodies, before removing those bodies from the shared PCH.
        definitions = factory_definitions + class_virtual_definitions
        source = abi_cohorts.proxy(g, proxy, lines[proxy_start:] + definitions)
        guarded = {}
        if proxy in abi_cohorts.state(g)['proxies']:
            guarded = {definition: _guard_proxy_definition(definition) for definition in definitions}
            source = [guarded.get(line, line) for line in source]
        virtual_blocks = {guarded.get(definition, definition) for definition in class_virtual_definitions}
        virtual_definitions += [guarded.get(definition, definition) for definition in class_virtual_definitions]
        source = [line for line in source if line not in virtual_blocks]
        lines[proxy_start:] = source
    # Keep one contiguous family so batching remains bounded by method count,
    # rather than creating a constructor/virtual shard pair for every class.
    lines += virtual_definitions
    if g.callback_classes:
        values = ', '.join(f'!std::is_abstract_v<BqtProxy_{ident(c["name"])}>' for c in g.callback_classes)
        lines += ['__attribute__((used, section(".bqt.proxy_traits")))',
                  'static const unsigned char bqt_proxy_traits[] = {' + values + '};']
    return '\n'.join(lines) + '\n'


def inventory(g):
    classes = [c['name'] for c in g.callback_classes]
    measured = getattr(g, 'callback_native_constructible', None)
    return {'proxy_classes': classes,
            'constructibility_verified': measured is not None,
            'constructible_classes': [name for name in classes if measured and measured.get(name, False)],
            'unextracted_pure_virtual_classes': [name for name in classes if measured is not None and not measured.get(name, False)],
            'protected_destructor_constructors': [{'class': m['class'], 'signature': m['function']['minimal_signature'],
                                                   'bend_name': m['bend_name']}
                                                  for m in g.methods if m['function']['constructor']
                                                  and g.classes[m['class']].get('derived_constructor')],
            'global_callbacks': [{'native': 'qInstallMessageHandler', 'install': 'MessageHandler.install',
                                  'lifetime': 'Closing the handler restores the previous process-global handler',
                                  'threads': 'Messages logged on other threads go to the previous handler'}],
            'function_callbacks': [{'signature': m['function']['minimal_signature'], 'bend_name': m['public'],
                                    'response': m['method']['public']} for m in g.callback_functions],
            'virtual_methods': [{'method_id': m['method_id'], 'bend_name': m['public'],
                                 'signature': m.get('native_signature', m['function']['minimal_signature'])} for m in g.callback_methods.values()],
            'excluded': g.callback_excluded,
            'limitations': ['A virtual method Qt calls on another thread runs on the main thread while its caller waits; the main thread must be in a Qt event loop',
                            'Render callbacks run only under the main-thread render loop; on a render thread the C++ base implementation runs',
                            'A handler that must return a value to Qt cannot wait',
                            'Tracked pointer results are retained until proxy destruction unless upstream explicitly transfers ownership to C++; references and unobserved native pointers remain unsupported',
                            'No rvalue-reference or non-owning-view reverse conversions',
                            'Dynamic native QObject metadata is represented through registered QML composite types',
                            'Construction rejects ENOTSUP if Qt has an internal pure virtual omitted by the upstream typesystem',
                            'Qt native reentrancy and indirect deletion contracts still apply']}


def qml_sources(g, qt_prefix, work):
    """Maintainer moc only: prepend header and append moc to wrappers.cpp."""
    import qobject_interfaces
    import qio_pipe
    helpers = qobject_interfaces.header(qobject_interfaces.inventory(g)) + qio_pipe.header(qio_pipe.selected(g))
    if not g.callback_qml and not helpers:
        return '', ''
    header = Path(work) / 'callback_qml.h'
    header.write_text(helpers + ((HERE / 'templates/callback_qml.h').read_text() if g.callback_qml else ''))
    moc = Path(qt_prefix) / 'libexec/moc'
    generated = subprocess.run([str(moc), '-I' + str(Path(qt_prefix) / 'include'),
                                '-I' + str(Path(qt_prefix) / 'include/QtCore'), str(header)],
                               check=True, text=True, capture_output=True).stdout
    # The header is already prepended to the translation unit. Eliminate its
    # generated include so no build-directory path enters the packaged source.
    generated = '\n'.join(line for line in generated.splitlines() if not re.match(r'#include "(?:.*/)?callback_qml.h"', line))
    prefix = ('#include <QtCore/QTemporaryDir>\n#include <QtCore/QFile>\n#include <QtQml/qqml.h>\n#include <QtQml/QQmlEngine>\n' if g.callback_qml else '') + header.read_text()
    return prefix + qio_pipe.implementation(g), generated
