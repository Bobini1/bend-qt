"""Keep native Vulkan extensions outside the pinned PySide API boundary.

Qt Quick's graphics-backend enums and ordinary rendering remain available.
This is a namespace/provenance boundary, not a catalogue of Qt classes.
"""
import re
import xml.etree.ElementTree as ET

NATIVE = re.compile(r'\b(?:QVulkan\w*|QRhiVulkan\w*|QSGVulkan\w*|Vk[A-Z]\w*|PFN_vk\w*|Vulkan::\w+)\b')
TYPE_TAGS = ('namespace-type', 'object-type', 'value-type', 'interface-type', 'primitive-type', 'enum-type')


def definitions(paths, root):
    """Read declarations without interpreting Shiboken's feature/entity rules.

    ApiExtractor remains authoritative for enabled classes. The source inventory
    records registration/removal evidence and cannot enable a native type.
    """
    types=set();removed=[]
    token=re.compile(r'<(/?)('+'|'.join((*TYPE_TAGS,'modify-function'))+r''')\b((?:"[^"]*"|'[^']*'|[^'">])*)>''')
    for path in sorted(paths):
        text=re.sub(r'<!--.*?-->','',path.read_text(),flags=re.S);stack=[]
        for match in token.finditer(text):
            closing,tag,attributes=match.groups()
            if closing:
                if stack and stack[-1][0]==tag:stack.pop()
                continue
            node=ET.fromstring('<'+tag+attributes.rstrip().removesuffix('/')+'/>')
            if tag=='modify-function':
                if node.get('remove')=='all' and stack:
                    removed.append(dict(owner=stack[-1][1],signature=node.get('signature',''),source=str(path.relative_to(root))))
                continue
            name=node.get('name','')
            owner=stack[-1][1] if stack else ''
            full=name if '::' in name or not owner else owner+'::'+name
            types.add(full)
            if not attributes.rstrip().endswith('/') and tag not in ('primitive-type','enum-type'):
                stack.append((tag,full))
    return dict(registered_types=sorted(types),removed_functions=removed)


def native_type(text):
    return bool(NATIVE.search(text or ''))


def function_outside(f):
    values=[f.get('declaring_class',''),f.get('return',{}).get('cpp',''),*f.get('source_signatures',[])]
    values += [a['type'].get('cpp',a['type'].get('name','')) for a in f.get('arguments',[])]
    return any(native_type(value) for value in values)


def apply(api):
    # A focused maintainer run may read an old extraction. Strip archived
    # supplements before carrier discovery so interop/field adapters cannot
    # revive them through otherwise representable scalar members.
    result=dict(api);report=list(api.get('pyside_boundary',{}).get('excluded_native_extensions',[]))
    classes=[]
    for original in api['classes']:
        name=original['name']
        extra_rhi=(name.startswith('QRhi') and original.get('package')=='BendQt')
        if native_type(name) or original.get('vulkan_registry') or extra_rhi:
            report.append(dict(kind='class',name=name,reason='Native extension absent from the pinned upstream PySide registrations'))
            continue
        cls=dict(original)
        for member,kind in (('functions','function'),('fields','field')):
            kept=[]
            for value in original.get(member,[]):
                outside=function_outside(value) if member=='functions' else native_type(value.get('type',{}).get('cpp',''))
                if outside:report.append(dict(kind=kind,owner=name,name=value.get('signature',value['name']),reason='External Vulkan API is outside the pinned PySide boundary'))
                else:kept.append(value)
            cls[member]=kept
        cls['enums']=[e for e in original.get('enums',[]) if not native_type(e['name'])]
        classes.append(cls)
    result['classes']=classes
    result['enums']=[e for e in api.get('enums',[]) if not native_type(e['name']) and not e.get('vulkan_registry')]
    result['global_functions']=[f for f in api.get('global_functions',[]) if not function_outside(f)]
    result['typedefs']={name:value for name,value in api.get('typedefs',{}).items() if not native_type(name) and not native_type(value)}
    for key in list(result):
        if key.startswith('vulkan_'):del result[key]
    unique={(r['kind'],r.get('owner',''),r['name']):r for r in report}
    result['pyside_boundary']=dict(scope='Pinned PySide type systems; external Vulkan extensions are archived',
        excluded_native_extensions=list(unique.values()),qt_quick_vulkan_backend_preserved=True)
    return result
