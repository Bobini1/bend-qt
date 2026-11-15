"""Pixel-buffer alternatives derived from the ordinary bounded GL adapters.

An offset names bytes of the currently bound native pixel buffer. It never
names client memory. Every alternative keeps the original native signature
and checks the same pixel-store extent as its host-memory counterpart.
"""
from itertools import combinations


def expand(g):
    for method in list(g.methods):
        candidates = [i for i, t in enumerate(method['args'])
                      if t.get('buffer', {}).get('pixel_buffer')]
        if not candidates or method['function']['signal']:
            continue
        g.types['GLBufferOffset'] = 'wide'
        for count in range(1, len(candidates) + 1):
            for indices in combinations(candidates, count):
                args = list(method['args'])
                for i in indices:
                    old = args[i]
                    policy = dict(old['buffer'], gpu_pixel_offset=True, bytes=False,
                                  writable=False, writable_array=False, nullable=False)
                    policy['pixel_native_element'] = ('char' if old['buffer'].get('bytes')
                                                       else old['children'][0]['cpp'])
                    args[i] = dict(kind='gpu_offset', bend='GLBufferOffset', raw='U32 & U32',
                                   cpp=old['buffer'].get('pointer_cpp', old['cpp']), buffer=policy)
                plan = [dict(p, type=args[p['input']], output=False, mutable=False)
                        if p['input'] in indices else p for p in method['parameters']]
                outputs = [p for p in plan if p['output'] or p['mutable']]
                native = method['native_return']
                returned = native
                if outputs:
                    fields = ([] if native['kind'] == 'void' else [native]) + [p['type'] for p in outputs]
                    returned = g.conversions.record(fields, prefix='Outputs_')
                suffix = '_bufferOffset' + (('_' + '_'.join(map(str, indices))) if len(candidates) > 1 else '')
                variant = dict(method, args=args, parameters=plan, outputs=outputs,
                               bend_name=method['bend_name'] + suffix,
                               pixel_buffer_alternative=list(indices))
                variant['return'] = returned
                g.methods.append(variant)


def argument(g, t, index):
    p = t['buffer']
    def value(role, default='1'):
        return (g.argument(p[role + '_type'], p[role + '_input'])[1]
                if role + '_input' in p else p.get(role + '_fixed', default))
    unpack = p['pixel_buffer'] == 'unpack'
    lines, expression, alignment = [], None, '1'
    if p.get('texture_layout') or p.get('texture_compressed'):
        options = p['options_input']
        lines += [f'auto *pixel_options_{index} = get<QOpenGLPixelTransferOptions>(r, r->arguments[{options}].word, {g.ids["QOpenGLPixelTransferOptions"]}, true, false);',
                  'if (r->error) return true;', f'GlPixelLayout pixel_layout_{index}{{}};',
                  f'if (pixel_options_{index}) pixel_layout_{index} = {{pixel_options_{index}->alignment(), pixel_options_{index}->rowLength(),',
                  f'    pixel_options_{index}->skipRows(), pixel_options_{index}->skipPixels(), pixel_options_{index}->imageHeight(), pixel_options_{index}->skipImages()}};']
        expression = (f'gl_texture_pixel_extent(r, self, {str("width_input" in p).lower()}, '
                      f'{value("width")}, {value("height")}, {value("depth")}, {value("mip", "0")}, {value("layer_count")}, '
                      f'{value("format")}, {value("pixel_type")}, pixel_options_{index} ? &pixel_layout_{index} : nullptr, '
                      + (value('count') if p.get('texture_compressed') else '-1') + ')')
    elif p.get('compressed_layout'):
        expression = (f'gl_compressed_extent(r, true, {p["compressed_dimensions"]}, '
                      f'{value("width")}, {value("height")}, {value("depth")}, {value("count")})')
    elif p.get('pixel_layout'):
        expression = (f'gl_pixel_extent(r, {str(unpack).lower()}, {str("depth_input" in p).lower()}, '
                      f'{value("width")}, {value("height")}, {value("depth")}, {value("format")}, {value("pixel_type")})')
    elif p.get('texture_readback'):
        expression = (f'gl_texture_readback_extent(r, {value("target")}, {value("mip", "0")}, '
                      f'{value("format")}, {value("pixel_type")}, {str(p.get("compressed_readback", False)).lower()})')
    elif 'legacy_readback' in p:
        expression = (f'gl_legacy_readback_extent(r, {p["legacy_readback"]}, {value("target")}, '
                      f'{value("format")}, {value("pixel_type")}, {p.get("readback_axis", 0)})')
    elif 'gl_extent' in p:
        expression = f'gl_buffer_extent(r, {p["gl_extent"]}, {value("pname")}) * sizeof({p["pixel_native_element"]})'
    elif 'count_input' in p:
        lines += [f'const auto pixel_count_{index} = {value("count")};',
                  f'if (pixel_count_{index} < 0) return fail(r, ERANGE, "Pixel buffer byte count cannot be negative");']
        width = '1' if p.get('count_divisor') else f'sizeof({p["pixel_native_element"]}) * {p.get("multiplier", 1)}'
        lines += [f'if (uint64_t(pixel_count_{index}) > uint64_t(std::numeric_limits<qsizetype>::max()) / ({width}))',
                  '    return fail(r, ERANGE, "Pixel buffer byte count overflows the native range");']
        expression = f'uint64_t(pixel_count_{index}) * ({width})'
    elif 'exact_size' in p:
        expression = f'{p["exact_size"]} * sizeof({p["pixel_native_element"]})'
    else:
        raise ValueError('Pixel-buffer alternative needs an audited native extent')
    if 'pixel_type_input' in p or 'pixel_type_fixed' in p:
        alignment = f'gl_pixel_type_alignment({value("pixel_type")})'
    elif p['pixel_native_element'] != 'char':
        alignment = f'sizeof({p["pixel_native_element"]})'
    target = 'GL_PIXEL_UNPACK_BUFFER' if unpack else 'GL_PIXEL_PACK_BUFFER'
    binding = target + '_BINDING'
    lines += [f'const auto pixel_extent_{index} = {expression};', 'if (r->error) return true;',
              f'auto *pixel_pointer_{index} = gl_pixel_offset(r, {target}, {binding}, wide_bits(r->arguments[{index}]), pixel_extent_{index}, {alignment});',
              'if (r->error) return true;']
    return lines, f'reinterpret_cast<{t["cpp"]}>(pixel_pointer_{index})'
