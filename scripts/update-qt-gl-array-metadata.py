#!/usr/bin/env python3
"""Regenerate maintainer-only OpenGL array extents from the pinned registry."""
import hashlib
import json
from pathlib import Path
import re
from urllib.request import urlopen
import xml.etree.ElementTree as ET

REVISION = '6af574a14089ccfee87efe230ebcdd8742859813'
URL = f'https://raw.githubusercontent.com/KhronosGroup/OpenGL-Registry/{REVISION}/xml/gl.xml'
REF_REVISION = '4bdf67a73d040f79bd7b087f5c1e588809e1f329'
ROOT = Path(__file__).resolve().parents[1]


def legacy_lengths(registry):
    """Pinned fixed-function parameter tables; reject unrecognized prose."""
    constants = {e.attrib['name']: int(e.attrib['value'], 0)
                 for e in registry.findall('./enums/enum') if 'value' in e.attrib
                 and re.fullmatch(r'(?:0x[0-9A-Fa-f]+|[0-9]+)', e.attrib['value'])}
    families, sources = {}, []
    aliases = {'GL_FOG_COORD_SRC': 1, 'GL_LIGHT_MODEL_COLOR_CONTROL': 1,
               'GL_AMBIENT_AND_DIFFUSE': 4}
    for family, page in [('fog', 'glFog'), ('light', 'glLight'), ('light_model', 'glLightModel'),
                         ('material', 'glMaterial'), ('point', 'glPointParameter'),
                         ('tex_env', 'glGetTexEnv'), ('tex_gen', 'glGetTexGen'),
                         ('color_table', 'glGetColorTableParameter'),
                         ('convolution', 'glGetConvolutionParameter'),
                         ('histogram', 'glGetHistogramParameter'), ('minmax', 'glGetMinmaxParameter')]:
        url = f'https://raw.githubusercontent.com/KhronosGroup/OpenGL-Refpages/{REF_REVISION}/gl2.1/{page}.xml'
        raw = urlopen(url).read()
        source = re.sub(r'&[A-Za-z_][A-Za-z_0-9]*;', '', raw.decode('utf-8-sig'))
        source = re.sub(r'(<\/?)[A-Za-z]+:', r'\1', source)
        root = ET.fromstring(source)
        entries, following_count = {}, None
        for entry in reversed(root.findall('.//varlistentry')):
            name = ''.join(entry.find('term').itertext()).strip()
            if not name.startswith('GL_'):
                continue
            text = ' '.join(' '.join(entry.find('listitem').itertext()).split())
            count = aliases.get(name)
            if count is None:
                for phrase, length in [('a single', 1), ('one', 1), ('two', 2), ('three', 3), ('four', 4)]:
                    if re.search(r'params (?:is |contains |returns )(?:an array of |the )?' + phrase + r'\b', text):
                        count = length
                        break
            if 'params returns the single-valued' in text:
                count = 1
            if family == 'convolution':
                count = 4 if 'array of four elements' in text else 1
            # The light attenuation selectors share the final list description.
            if not text:
                count = following_count
            if count is None or name not in constants:
                raise RuntimeError(f'Unrecognized pinned legacy GL parameter extent: {name}: {text}')
            following_count = count
            entries[name] = {'enum': constants[name], 'length': count}
        if family == 'color_table':
            for name in ('GL_COLOR_TABLE_SCALE', 'GL_COLOR_TABLE_BIAS'):
                entries[name] = {'enum': constants[name], 'length': 4}
        # The format/size tables describe scalar integer/enum/boolean values.
        # Color table rows explicitly provide N; histogram/minmax rows do not
        # include array-valued parameters in this pinned public API.
        for row in root.findall('.//tbody/row'):
            columns = [''.join(e.itertext()).strip() for e in row.findall('entry')]
            if not columns or columns[0] not in constants:
                continue
            count = int(columns[1]) if family == 'color_table' else 1
            entries[columns[0]] = {'enum': constants[columns[0]], 'length': count}
        families[family] = entries
        sources.append({'url': url, 'sha256': hashlib.sha256(raw).hexdigest()})
    result = {'revision': REF_REVISION, 'sources': sources,
              'copyright': ['Copyright 1991-2006 Silicon Graphics, Inc.', 'Copyright 2010-2014 Khronos Group'],
              'families': families}
    target = ROOT / 'generator/gl-legacy-lengths.json'
    target.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(f'Wrote {sum(map(len, families.values()))} legacy parameter extents to {target}')


def query_lengths(registry):
    """Extract finite state-query selectors from the pinned Khronos reference."""
    constants = {e.attrib['name']: int(e.attrib['value'], 0)
                 for e in registry.findall('./enums/enum') if 'value' in e.attrib
                 and re.fullmatch(r'(?:0x[0-9A-Fa-f]+|[0-9]+)', e.attrib['value'])}
    ns = {'d': 'http://docbook.org/ns/docbook'}
    families, sources = {}, []
    for family, page in [('state', 'glGet'), ('program', 'glGetProgram'),
                         ('texture', 'glGetTexParameter'), ('sampler', 'glGetSamplerParameter')]:
        url = f'https://raw.githubusercontent.com/KhronosGroup/OpenGL-Refpages/{REF_REVISION}/gl4/{page}.xml'
        raw = urlopen(url).read()
        # The declarations reference MathML entities; query descriptions only
        # need their ordinary text, not a math renderer or an external DTD.
        source = re.sub(r'&[A-Za-z_][A-Za-z_0-9]*;', '', raw.decode('utf-8-sig'))
        entries = {}
        for entry in ET.fromstring(source).findall('.//d:varlistentry', ns):
            name = ''.join(entry.find('d:term', ns).itertext()).strip()
            if not name.startswith('GL_'):
                continue
            text = ' '.join(' '.join(entry.find('d:listitem', ns).itertext()).split())
            if family == 'state':
                count = None
                for phrase, length in [('a single', 1), ('one', 1), ('two', 2), ('a pair of', 2), ('three', 3), ('four', 4)]:
                    if re.search(r'(?:data|params) (?:returns )?' + phrase + r'\b', text):
                        count = length
                        break
                variable = re.search(r'(?:length |array of )(GL_NUM_[A-Z_0-9]+)', text)
                if variable:
                    count = variable[1]
                if name in ('GL_MAX_COMPUTE_WORK_GROUP_COUNT', 'GL_MAX_COMPUTE_WORK_GROUP_SIZE'):
                    count = 1  # Indexed query: X/Y/Z are separate indices.
                if count is None:
                    raise RuntimeError(f'Unrecognized pinned GL state extent: {name}: {text}')
            elif family == 'program':
                count = 3 if name == 'GL_COMPUTE_WORK_GROUP_SIZE' else 1
            else:
                count = 4 if name in ('GL_TEXTURE_BORDER_COLOR', 'GL_TEXTURE_SWIZZLE_RGBA') else 1
            names = [name] if name in constants else [n for n in constants if name.endswith('i') and re.fullmatch(re.escape(name[:-1]) + r'[0-9]+', n)]
            if not names:
                raise RuntimeError(f'Query selector missing from pinned GL registry: {name}')
            for selector in names:
                entries[selector] = {'enum': constants[selector], 'length': count}
                if isinstance(count, str):
                    entries[selector]['count_enum'] = constants[count]
        families[family] = entries
        sources.append({'url': url, 'sha256': hashlib.sha256(raw).hexdigest()})
    result = {'revision': REF_REVISION, 'sources': sources,
              'copyright': ['Copyright 1991-2006 Silicon Graphics, Inc.', 'Copyright 2010-2014 Khronos Group'],
              'families': families}
    target = ROOT / 'generator/gl-query-lengths.json'
    target.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(f'Wrote {sum(map(len, families.values()))} query selector extents to {target}')


def main():
    source = urlopen(URL).read()
    registry = ET.fromstring(source)
    commands = {}
    for command in registry.findall('./commands/command'):
        parameters = command.findall('param')
        names = [p.findtext('name') for p in parameters]
        lengths = {}
        for index, parameter in enumerate(parameters):
            length = parameter.get('len', '').replace(' ', '')
            if re.fullmatch(r'[1-9][0-9]*|[A-Za-z_][A-Za-z_0-9]*(?:[*/][1-9][0-9]*)?', length):
                lengths[str(index)] = length
        if lengths:
            commands[command.findtext('./proto/name')] = {'parameters': names, 'lengths': lengths}
    result = {'source': URL, 'revision': REVISION, 'sha256': hashlib.sha256(source).hexdigest(),
              'copyright': 'Copyright 2013-2026 The Khronos Group Inc.',
              'license': 'Apache-2.0', 'license_url': 'https://www.apache.org/licenses/LICENSE-2.0',
              'commands': commands}
    target = ROOT / 'generator/gl-array-lengths.json'
    target.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(f'Wrote {len(commands)} registry command extents to {target}')
    query_lengths(registry)
    legacy_lengths(registry)


if __name__ == '__main__':
    main()
