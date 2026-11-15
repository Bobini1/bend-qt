"""QSGMaterialShader's reflected texture array; no ownership transfer.

The public combinedImageSamplerCount(binding) defines the exact array extent.
Replies validate every element and reserve retention before native writeback.
"""
from callbacks import _conversion, _record, _retained_cleanup, signature_id, bend_ident, thread_branch


def matches(f):
    return f['declaring_class'] == 'QSGMaterialShader' and f['name'] == 'updateSampledImage'


def prepare_method(g, name, f):
    if not matches(f):
        return None
    if len(f['arguments']) != 5 or f['arguments'][2]['type']['cpp'].replace(' ', '') != 'QSGTexture**':
        raise ValueError('Unknown QSG sampled-image array contract')
    element = dict(f['arguments'][2]['type'], cpp='QSGTexture*', pointers=1)
    source = dict(element, name='QList', cpp='QList<QSGTexture*>', pointers=0,
                  container=True, instantiations=[element])
    textures = g.conversions.container(source, False)
    args = [_conversion(g, a['type']) if i != 2 else textures for i, a in enumerate(f['arguments'])]
    method_id = signature_id(f['declaring_class'], f)
    return dict(function=f, args=args, payload=_record(g, args, 'CallbackArgs_'),
                result=_retained_cleanup(g, textures), native_result=dict(kind='void'), outputs=[],
                method_id=method_id, public=bend_ident(f['declaring_class']) + '.Virtual.updateSampledImage_' + str(method_id),
                sampled_images=True, render_scope=True)


def cpp(g, name, method):
    args, f = method['args'], method['function']
    parameters = ', '.join(a['type']['cpp'] + f' a{i}' for i, a in enumerate(f['arguments']))
    base = f'{{ {name}::updateSampledImage(a0, a1, a2, a3, a4); return; }}'
    lines = [f'    void updateSampledImage({parameters}) override {{',
             '        if (!bqt_receiver) ' + base,
             f'        uint32_t handler = bqt_handlers.find({method["method_id"]}u);',
             '        if (!handler) ' + base]
    lines += thread_branch(method, 'void', 'a0, a1, a2, a3, a4', base, 'return;')
    lines += [
              '        try {', '        BqtRequest conversion{};',
              '        GuiRenderScope render(&conversion, bqt_receiver);',
              '        if (!render.active) { callback_report_error(conversion.error); return; }',
              '        int count = combinedImageSamplerCount(a1);',
              '        if (count < 0 || (count && !a2)) { callback_report_error(EINVAL); return; }',
              '        CallbackNativeArguments native_arguments;',
              '        CallbackOwnedArguments arguments{sequence_value(5)};',
              f'        arguments.value.items[0] = write_{args[0]["native_codec"]}(&conversion, a0);',
              f'        arguments.value.items[1] = write_{args[1]["native_codec"]}(&conversion, a1);',
              '        arguments.value.items[2] = sequence_value(size_t(count));',
              '        for (int i = 0; i < count; ++i)',
              f'            arguments.value.items[2].items[i] = write_{args[2]["children"][0]["native_codec"]}(&conversion, a2[i]);']
    for i in (3, 4):
        lines += [f'        arguments.value.items[{i}] = native_arguments.borrow_argument(&conversion, a{i}, {g.ids["QSGMaterial"]}, bqt_receiver);']
    lines += ['        if (conversion.error) { callback_report_error(conversion.error); return; }',
              '        struct Reply { QSGTexture **textures; int count; }; Reply result{a2, count};',
              '        auto decode = [](BqtRequest *r, const BqtValue &wire, void *destination) {',
              '            auto *target = static_cast<Reply *>(destination);',
              '            if (!wire_shape(r, wire, 2)) return false;',
              '            if (auto error = lifetime_sampled_reply[unsigned(wire.count == size_t(target->count)) * 2 + 1]) { fail(r, error, "Texture output extent differs from shader reflection"); return false; }',
              f'            auto textures = read_{args[2]["native_codec"]}(r, wire);',
              '            if (!textures) return false;',
              '            bool nonnull = std::all_of(textures->cbegin(), textures->cend(), [](auto *texture) { return texture != nullptr; });',
              '            if (auto error = lifetime_sampled_reply[2 + unsigned(nonnull)]) { fail(r, error, "Every sampled-image output must be non-null"); return false; }',
              '            RetentionBatch retained_results;',
              '            for (int i = 0; i < target->count; ++i) {',
              '                auto *texture = textures->at(i);',
              '                bool existing = false;',
              '                for (int j = 0; j < target->count; ++j) if (texture == target->textures[j]) existing = true;',
              '                if (!existing && !callback_prepare_retained(r, wire.items[i].word, retained_results)) return false;',
              '            }',
              '            if (!retained_results.finish(r)) return false;',
              '            if (target->count) std::copy(textures->cbegin(), textures->cend(), target->textures);',
              '            return true;', '        };',
              f'        int error = callback_invoke(handler, bqt_receiver, arguments.take(), decode, &result);',
              '        if (error == ENOSYS) ' + base,
              '        if (error) callback_report_error(error);',
              '        } catch (const std::bad_alloc &) { callback_report_error(ENOMEM); }',
              '          catch (...) { callback_report_error(EFAULT); }', '    }']
    return lines


def emit(g):
    method = next((m for m in getattr(g, 'callback_methods', {}).values() if m.get('sampled_images')), None)
    if not method:
        return
    args = method['args']
    operation = g.next_id; g.next_id += 1
    lines = ['if (!gui_render_depth) return fail(r, EPERM, "Sampled images require an active GUI render callback");',
             'NativeCallScope scope;',
             f'auto *self = get<QSGMaterialShader>(r, r->self, {g.ids["QSGMaterialShader"]});',
             f'auto *state = get<QSGMaterialShader::RenderState>(r, r->arguments[0].word, {g.ids["QSGMaterialShader::RenderState"]});',
             f'auto binding = read_{args[1]["native_codec"]}(r, r->arguments[1]);',
             f'auto textures = read_{args[2]["native_codec"]}(r, r->arguments[2]);',
             f'auto *material = get<QSGMaterial>(r, r->arguments[3].word, {g.ids["QSGMaterial"]});',
             f'auto *old = get<QSGMaterial>(r, r->arguments[4].word, {g.ids["QSGMaterial"]}, true);',
             'if (r->error || !binding || !textures) return true;',
             'if (self->combinedImageSamplerCount(*binding) != textures->size()) return fail(r, EINVAL, "Texture list extent must match shader reflection");',
             'self->updateSampledImage(*state, *binding, textures->data(), material, old);',
             'if (r->error) return true;',
             'for (auto *texture : *textures) if (!texture) return fail(r, EINVAL, "A sampled-image output is null");',
             f'r->result = write_{args[2]["native_codec"]}(r, *textures);', 'return true;']
    g.cases.append(f'case {operation}: {{\n' + '\n'.join('    ' + line for line in lines) + '\n}')
    g.emit_effect('QSGMaterialShader.updateSampledImage',
                  [('self', dict(bend='QSGMaterialShader', raw='U32'))] +
                  list(zip(('state', 'binding', 'textures', 'material', 'previous'), args)), args[2], operation, has_self=True)
    emit_configuration(g)


def configuration_cpp(g, name):
    if name != 'QSGMaterialShader':
        return []
    lines = ['    void bqt_shader_file(Stage stage, const QString &file) { setShaderFileName(stage, file); }',
             '    void bqt_shader_file_views(Stage stage, const QString &file, int views) { setShaderFileName(stage, file, views); }']
    if 'QShader' in g.ids:
        lines += ['#if BQT_HAS_RHI', '    void bqt_shader(Stage stage, const QShader &shader) { setShader(stage, shader); }', '#endif']
    return lines


def emit_configuration(g):
    if not any(c['name'] == 'QSGMaterialShader' for c in g.callback_classes):
        return
    string = dict(kind='string', bend='String', raw='String', cpp='QString')
    variants = [('configureShaderFile', [('file', string)], 'self->bqt_shader_file(stage, a1);'),
                ('configureShaderFileViews', [('file', string), ('views', dict(kind='i32', bend='Int32', raw='U32', cpp='int'))],
                 'if (a2 < 1) return fail(r, EINVAL, "Shader view count must be positive"); self->bqt_shader_file_views(stage, a1, a2);')]
    if 'QShader' in g.ids:
        variants.append(('configureShader', [('shader', dict(kind='value', name='QShader', bend='QShader', raw='U32', cpp='QShader'))],
                         'self->bqt_shader(stage, *a1);'))
    for name, parameters, invoke in variants:
        operation = g.next_id; g.next_id += 1
        lines = ['if (!gui_render_depth) return fail(r, EPERM, "Shader configuration requires a GUI render callback");',
                 'NativeCallScope scope;',
                 f'auto *base = get<QSGMaterialShader>(r, r->self, {g.ids["QSGMaterialShader"]});',
                 'if (r->error) return true;', 'auto *self = dynamic_cast<BqtProxy_QSGMaterialShader *>(base);',
                 'if (!self) return fail(r, ENOTSUP, "Protected shader configuration requires a Bend-created shader proxy");',
                 'auto stage = QSGMaterialShader::Stage(r->arguments[0].word);',
                 'if (stage != QSGMaterialShader::VertexStage && stage != QSGMaterialShader::FragmentStage) return fail(r, EINVAL, "Invalid shader stage");']
        for i, (_, typ) in enumerate(parameters, 1):
            declarations, expression = g.argument(typ, i)
            lines += declarations
            if typ['kind'] not in ('object', 'value'):
                lines += [f'auto a{i} = {expression};']
        lines += ['if (r->error) return true;', invoke, 'return true;']
        if name == 'configureShader':
            lines = ['#if BQT_HAS_RHI'] + lines + ['#else', 'return fail(r, ENOTSUP, "QShader requires the matching Qt RHI ABI cohort");', '#endif']
        g.cases.append(f'case {operation}: {{\n' + '\n'.join('    ' + line for line in lines) + '\n}')
        g.emit_effect('QSGMaterialShader.' + name,
                      [('self', dict(bend='QSGMaterialShader', raw='U32')),
                       ('stage', dict(bend='QSGMaterialShader.Stage', raw='U32'))] + parameters,
                      dict(bend='Unit', raw='Unit'), operation, has_self=True)


def annotate(g):
    method = next((m for m in getattr(g, 'callback_methods', {}).values() if m.get('sampled_images')), None)
    if not method:
        return
    for row in g.excluded:
        if row.get('class') == 'QSGMaterialShader':
            signature = row.get('signature', '')
            config = ('configureShaderFileViews' if signature.startswith('setShaderFileName(') and signature.endswith(',int)') else
                      'configureShaderFile' if signature.startswith('setShaderFileName(') else
                      'configureShader' if signature.startswith('setShader(') and 'QShader' in g.ids else None)
            if config:
                value = dict(bend_name='QSGMaterialShader.' + config, contract='protected_proxy_configuration',
                             reason='Checked public subclass hook on Bend-created shader proxies only')
                if value not in row.setdefault('alternatives', []): row['alternatives'].append(value)
        if row.get('class') == 'QSGMaterialShader' and row.get('signature', '').startswith('updateSampledImage('):
            for name, contract in [('QSGMaterialShader.updateSampledImage', 'typed_inout_array'),
                                   (method['public'] + '.handle', 'reverse_inout_array')]:
                value = dict(bend_name=name, contract=contract,
                             reason='Exact reflected sampler extent; non-null outputs; no native ownership transfer')
                if value not in row.setdefault('alternatives', []): row['alternatives'].append(value)
