"""Public record metadata omitted by Shiboken, read with the installed libclang.

The supplement is rooted in extracted public classes. It preserves Shiboken
members and only discovers their public data members and public nested records.
"""
from ctypes import CDLL, CFUNCTYPE, POINTER, Structure, byref, c_char_p, c_int, c_uint, c_void_p
from ctypes.util import find_library
from pathlib import Path
import re

class String(Structure):
    _fields_ = [('data', c_void_p), ('flags', c_uint)]
class Cursor(Structure):
    _fields_ = [('kind', c_uint), ('xdata', c_int), ('data', c_void_p * 3)]
class Type(Structure):
    _fields_ = [('kind', c_int), ('data', c_void_p * 2)]
class Location(Structure):
    _fields_ = [('ptr_data', c_void_p * 2), ('int_data', c_uint)]
Visitor = CFUNCTYPE(c_uint, Cursor, Cursor, c_void_p)
FieldVisitor = CFUNCTYPE(c_uint, Cursor, c_void_p)

class Clang:
    def __init__(self):
        self.lib = CDLL(find_library('clang-19') or '/usr/lib/llvm-19/lib/libclang.so')
        def function(name, result, *args):
            fn = getattr(self.lib, 'clang_' + name); fn.restype = result; fn.argtypes = args
            setattr(self, name, fn)
        function('createIndex', c_void_p, c_int, c_int)
        function('disposeIndex', None, c_void_p)
        function('parseTranslationUnit', c_void_p, c_void_p, c_char_p, POINTER(c_char_p), c_int, c_void_p, c_uint, c_uint)
        function('disposeTranslationUnit', None, c_void_p)
        function('getTranslationUnitCursor', Cursor, c_void_p)
        function('visitChildren', c_uint, Cursor, Visitor, c_void_p)
        function('Type_visitFields', c_uint, Type, FieldVisitor, c_void_p)
        function('getCursorSpelling', String, Cursor)
        function('getCursorKindSpelling', String, c_uint)
        function('getCursorType', Type, Cursor)
        function('getTypeSpelling', String, Type)
        function('getCanonicalType', Type, Type)
        function('getTypeDeclaration', Cursor, Type)
        function('getTypedefDeclUnderlyingType', Type, Cursor)
        function('getSpecializedCursorTemplate', Cursor, Cursor)
        function('getCursorSemanticParent', Cursor, Cursor)
        function('Cursor_isNull', c_int, Cursor)
        function('getCString', c_char_p, String)
        function('disposeString', None, String)
        function('getCXXAccessSpecifier', c_uint, Cursor)
        function('isCursorDefinition', c_uint, Cursor)
        function('isConstQualifiedType', c_uint, Type)
        function('getPointeeType', Type, Type)
        function('getCursorLocation', Location, Cursor)
        function('getSpellingLocation', None, Location, POINTER(c_void_p), POINTER(c_uint), POINTER(c_uint), POINTER(c_uint))
        function('getFileName', String, c_void_p)
        function('getResultType', Type, Type)
        function('getNumArgTypes', c_int, Type)
        function('getArgType', Type, Type, c_uint)
        function('getNumDiagnostics', c_uint, c_void_p)
        function('getDiagnostic', c_void_p, c_void_p, c_uint)
        function('getDiagnosticSeverity', c_uint, c_void_p)
        function('formatDiagnostic', String, c_void_p, c_uint)
        function('disposeDiagnostic', None, c_void_p)
        function('CXXMethod_isStatic', c_uint, Cursor)
        function('CXXMethod_isConst', c_uint, Cursor)
        function('CXXMethod_isDeleted', c_uint, Cursor)
        function('getArrayElementType', Type, Type)
        function('getArraySize', __import__('ctypes').c_longlong, Type)
        function('Type_getSizeOf', __import__('ctypes').c_longlong, Type)
        function('Type_getNumTemplateArguments', c_int, Type)
        function('Type_getTemplateArgumentAsType', Type, Type, c_uint)
    def string(self, string):
        text = self.getCString(string)
        result = text.decode() if text else ''
        self.disposeString(string); return result
    def spelling(self, cursor): return self.string(self.getCursorSpelling(cursor))
    def type_name(self, type): return self.string(self.getTypeSpelling(type))
    def kind(self, cursor): return self.string(self.getCursorKindSpelling(cursor.kind))
    def children(self, cursor):
        result = []
        @Visitor
        def visit(child, parent, data): result.append(child); return 1
        self.visitChildren(cursor, visit, None); return result
    def fields(self, type):
        result = []
        @FieldVisitor
        def visit(child, data): result.append(child); return 1
        self.Type_visitFields(type, visit, None); return result
    def qualified(self, cursor):
        names = []
        while cursor.kind and not self.Cursor_isNull(cursor) and self.kind(cursor) != 'TranslationUnit':
            name = self.spelling(cursor)
            if len(names) > 32: raise RuntimeError('Cyclic Clang semantic parent')
            if name: names.append(name)
            cursor = self.getCursorSemanticParent(cursor)
        return '::'.join(reversed(names))
    def location(self, cursor):
        file = c_void_p(); line = c_uint(); column = c_uint(); offset = c_uint()
        self.getSpellingLocation(self.getCursorLocation(cursor), byref(file), byref(line), byref(column), byref(offset))
        return self.string(self.getFileName(file)) if file else '', line.value
    def parse(self, header, flags):
        self.index = self.createIndex(0, 0)
        argv = (c_char_p * len(flags))(*(x.encode() for x in flags))
        self.tu = self.parseTranslationUnit(self.index, str(header).encode(), argv, len(flags), None, 0, 0)
        if not self.tu: raise RuntimeError('libclang could not parse public record headers')
        errors = []
        for i in range(self.getNumDiagnostics(self.tu)):
            diagnostic = self.getDiagnostic(self.tu, i)
            if self.getDiagnosticSeverity(diagnostic) >= 3: errors.append(self.string(self.formatDiagnostic(diagnostic, 0)))
            self.disposeDiagnostic(diagnostic)
        if errors: raise RuntimeError('Public record header parsing failed:\n' + '\n'.join(errors))
        return self.getTranslationUnitCursor(self.tu)
    def close(self):
        if getattr(self, 'tu', None): self.disposeTranslationUnit(self.tu)
        if getattr(self, 'index', None): self.disposeIndex(self.index)


def scan(header, flags, roots):
    """Discover public record/type facts; no admission or ownership inference."""
    clang = Clang()
    try:
        root = clang.parse(header, flags)
        records = {}
        def template_methods(value):
            native = clang.type_name(value)
            result = []
            declaration = clang.getTypeDeclaration(value)
            template = clang.getSpecializedCursorTemplate(declaration)
            parameters = [clang.spelling(x) for x in clang.children(template)
                          if clang.kind(x) in ('TemplateTypeParameter', 'NonTypeTemplateParameter')]
            arguments = [x['cpp'] for x in type_descriptor(native)['instantiations']]
            substitutions = dict(zip(parameters, arguments))
            def concrete(text):
                for key,replacement in substitutions.items(): text = re.sub(r'\b'+re.escape(key)+r'\b',replacement,text)
                return text
            for child in clang.children(template):
                ck=clang.kind(child)
                if ck not in ('CXXMethod','CXXConstructor','Constructor') or clang.getCXXAccessSpecifier(child)!=1: continue
                if ck=='CXXMethod' and clang.CXXMethod_isDeleted(child): continue
                mt=clang.getCursorType(child); file, ln=clang.location(child)
                result.append(dict(name=clang.spelling(child), constructor=ck!='CXXMethod',
                    args=[concrete(clang.type_name(clang.getArgType(mt,i))) for i in range(clang.getNumArgTypes(mt))],
                    source_file=file,source_line=ln))
            return result
        def walk(cursor, admitted=False):
            kind, name = clang.kind(cursor), clang.qualified(cursor)
            if kind in ('TypedefDecl', 'TypeAliasDecl') and name in roots:
                value = clang.getCanonicalType(clang.getTypedefDeclUnderlyingType(cursor))
                native = clang.type_name(value)
                if value.kind == 105 and '<' in native:
                    location, line = clang.location(cursor)
                    records[name] = dict(name=name, source_file=location, source_line=line, native_alias=native,
                        fields=[], methods=[], template_methods=[])
                    records[name]['template_methods'] = template_methods(value)
                return
            if kind in ('StructDecl', 'ClassDecl') and clang.isCursorDefinition(cursor):
                if name in roots or (admitted and clang.getCXXAccessSpecifier(cursor) == 1):
                    location, line = clang.location(cursor)
                    record = dict(name=name, source_file=location, source_line=line, fields=[], methods=[], nonpublic_data=False, bases=[])
                    records[name] = record
                    for child in clang.children(cursor):
                        access = clang.getCXXAccessSpecifier(child)
                        ck = clang.kind(child)
                        if ck == 'C++ base class specifier' and access == 1:
                            base = clang.getCanonicalType(clang.getCursorType(child))
                            record['bases'].append(clang.type_name(base))
                            record.setdefault('inherited_methods', []).extend(template_methods(base))
                        if access != 1:
                            if ck == 'FieldDecl': record['nonpublic_data'] = True
                            continue
                        if ck == 'FieldDecl':
                            record['fields'].append(dict(name=clang.spelling(child), type=clang.type_name(clang.getCursorType(child)),
                                canonical=clang.type_name(clang.getCanonicalType(clang.getCursorType(child)))))
                        if ck == 'CXXMethod' and not clang.CXXMethod_isDeleted(child):
                            method_type = clang.getCursorType(child)
                            returned = clang.getResultType(method_type)
                            record['methods'].append(dict(name=clang.spelling(child), result=clang.type_name(clang.getCanonicalType(returned)),
                                const=bool(clang.CXXMethod_isConst(child)), static=bool(clang.CXXMethod_isStatic(child)),
                                args=[clang.type_name(clang.getCanonicalType(clang.getArgType(method_type, i))) for i in range(clang.getNumArgTypes(method_type))]))
                            # Concrete nested template records appear in public signatures.
                            values = [returned] + [clang.getArgType(method_type, i) for i in range(clang.getNumArgTypes(method_type))]
                            for value in values:
                                value = clang.getCanonicalType(value)
                                value_name = clang.type_name(value)
                                if value_name.startswith(name + '::') and '<' in value_name and value_name not in records:
                                    clang.Type_getSizeOf(value)
                                    fields = clang.fields(value)
                                    if fields:
                                        records[value_name] = dict(name=value_name, source_file=location, source_line=line,
                                            fields=[dict(name=clang.spelling(f), type=clang.type_name(clang.getCursorType(f)),
                                                         canonical=clang.type_name(clang.getCanonicalType(clang.getCursorType(f)))) for f in fields], methods=[])
                        if ck in ('StructDecl', 'ClassDecl'): walk(child, True)
                    return
            if kind in ('TranslationUnit', 'Namespace', 'LinkageSpec'):
                for child in clang.children(cursor): walk(child, admitted)
        walk(root)
        return records
    finally: clang.close()


def type_descriptor(spelling, aliases=None):
    aliases = aliases or {}
    cpp = spelling.strip()
    array = re.fullmatch(r'(.*)\[(\d+)\]', cpp)
    if array:
        child = type_descriptor(array[1], aliases)
        return dict(child, cpp=cpp, pointers=0, reference=0, array=True, array_count=int(array[2]), array_element=child)
    depth = 0; pointers = 0
    for char in cpp:
        if char == '<': depth += 1
        elif char == '>': depth -= 1
        elif char == '*' and not depth: pointers += 1
    reference = 2 if cpp.endswith('&&') else 1 if cpp.endswith('&') else 0
    const = cpp.startswith('const ')
    name = re.sub(r'^(const|volatile)\s+', '', cpp).rstrip('&* ').strip()
    name = re.sub(r'\s+(const|volatile)$', '', name)
    children = []
    if '<' in name and name not in aliases:
        start = name.index('<'); arguments = name[start+1:-1]; depth=0; offset=0
        for i,ch in enumerate(arguments + ','):
            if ch=='<': depth+=1
            elif ch=='>': depth-=1
            elif ch==',' and not depth:
                children.append(type_descriptor(arguments[offset:i], aliases)); offset=i+1
        name = name[:start]
    return dict(name=aliases.get(name, name), cpp=cpp, pointers=pointers, reference=reference,
                const=const, array=False, container=bool(children), enum=False, flags=False, instantiations=children)


def merge(api, records):
    """Merge supplemental public fields and record-dependent method overloads.

    All constructors/copies still pass measured native traits, and pointer
    fields/methods still pass the ordinary conversion and lifetime adapters.
    """
    import copy
    classes = {c['name']:c for c in api['classes']}
    aliases = {name: re.sub(r'[^A-Za-z0-9_]', '_', name).rstrip('_')
               for name in records if '<' in name}
    for name, alias in aliases.items():
        if alias in classes or (alias in api['typedefs'] and api['typedefs'][alias] != name):
            raise RuntimeError('Public record alias collision: '+alias)
        api['typedefs'][alias] = name
    added, fields, methods = [], [], []
    def function(owner, name, arguments=(), result='void', constructor=False, copy_constructor=False, const=False, static=False, source=None):
        signature = name + '(' + ','.join(arguments) + ')' + ('const' if const else '')
        return dict(abstract=False, arguments=[dict(name='arg'+str(i), type=type_descriptor(t, aliases), array=False,
            removed=False, default='', native_default='') for i,t in enumerate(arguments)],
            const=const, constructor=constructor, copy_constructor=copy_constructor,
            declaring_class=owner, deprecated=False, destructor=False, final_cpp=False,
            implementing_class=owner, injected_code=False, minimal_signature=signature, name=name,
            noexcept=False, operator=name.startswith('operator'), policies=[], private=False, protected=False,
            public=True, removed=False, return_=None, **{'return':type_descriptor(result, aliases)},
            rvalue_reference=False, signal=False, signature=signature, signature_modified=False,
            slot=False, snippets=[], source_file=source['source_file'], source_line=source['source_line'],
            source_signatures=[signature] if not constructor else [], static=static, user_added=False, virtual=False,
            bend_public_record=True)
    # New records must be public nested descendants of an extracted class.
    for native, record in sorted(records.items()):
        name=aliases.get(native,native)
        if name in classes or not record['fields']: continue
        parents = [n for n in classes if native.startswith(n + '::') and classes[n].get('generate')]
        if not parents: continue
        parent = max(parents, key=len)
        if record.get('nonpublic_data') or record.get('bases'): continue
        cls=dict(name=name, abstract=False, bases=[], copyable=True, enums=[], fields=[], final_cpp=False,
            functions=[], generate=True, namespace=False, object=False, package=classes[parent]['package'],
            public_destructor=True,qobject=False, source_file=record['source_file'],source_line=record['source_line'],
            template=False,value=True,virtual_destructor=False,bend_public_record=native)
        cls['functions']=[function(name,name.split('::')[-1],constructor=True,source=record),
            function(name,name.split('::')[-1],['const '+native+' &'],constructor=True,copy_constructor=True,source=record)]
        classes[name]=cls;api['classes'].append(cls);added.append(name)
    for native, record in sorted(records.items()):
        name=aliases.get(native,native)
        if name not in classes: continue
        cls=classes[name]
        if record.get('native_alias') or record.get('inherited_methods'):
            cls['native_alias'] = record.get('native_alias', name)
            for base in record.get('bases', []):
                if base.startswith('QList<'): cls['native_sequence_base'] = base
            cls['source_file'] = cls.get('source_file') or record['source_file']
            cls['source_line'] = cls.get('source_line') or record['source_line']
            shape = re.fullmatch(r'QGenericMatrix<(\d+), (\d+), ([^<>]+)>', record.get('native_alias', ''))
            if shape: cls['native_matrix_shape'] = [int(shape[1]),int(shape[2]),shape[3]]
            for f in cls['functions']:
                if f.get('source_signatures'): continue
                actual = [re.sub(r'\s+', '', a['type']['cpp']) for a in f['arguments']]
                for method in record.get('template_methods', []) + record.get('inherited_methods', []):
                    if f['constructor'] != method['constructor']: continue
                    if not f['constructor'] and f['name'] != method['name']: continue
                    if actual != [re.sub(r'\s+','',a) for a in method['args']]: continue
                    f['source_file'], f['source_line'] = method['source_file'], method['source_line']
                    f['source_signatures'] = [f['signature']]
                    f['bend_template_evidence'] = record.get('native_alias') or record.get('bases')
                    break
        existing={f['name'] for f in cls.get('fields',[])}
        for member in record['fields']:
            if member['name'] in existing: continue
            t=type_descriptor(member['canonical'],aliases)
            # Template field substitutions must have become concrete.
            if not t['name'] or t['name']=='type-parameter-0-0': continue
            field=dict(name=member['name'],declaring_class=name,type=t,public=True,protected=False,
                private=False,removed=False,static=False,getter=True,setter=not t['const'],
                getter_enabled=True,setter_enabled=not t['const'],bend_public_record=True)
            cls.setdefault('fields',[]).append(field);fields.append(name+'.'+member['name'])
        # Add omitted overloads only when they use a newly discovered record.
        # Existing declarations and their upstream policies remain authoritative.
        existing={(f['name'], tuple(re.sub(r'\s+','',a['type']['cpp']) for a in f['arguments']),f['const']) for f in cls['functions']}
        for method in record['methods']:
            parts=[method['result']]+method['args']
            if name not in added and not any(any(native_record in part for native_record in records if aliases.get(native_record,native_record) in added) for part in parts): continue
            key=(method['name'],tuple(re.sub(r'\s+','',a) for a in method['args']),method['const'])
            if key in existing: continue
            f=function(name,method['name'],method['args'],method['result'],const=method['const'],static=method['static'],source=record)
            if name not in added: f['bend_restored_native'] = True
            cls['functions'].append(f);methods.append(name+'::'+f['signature'])
    enum_names = {e['name'] for e in api['enums']}
    for cls in api['classes']: enum_names.update(e['name'] for e in cls['enums'])
    def normalize_type(t):
        for child in t.get('instantiations', []): normalize_type(child)
        if t.get('array_element'): normalize_type(t['array_element'])
        if t['name'] in enum_names: t['enum'] = True
        if t['name'] == 'QFlags' and len(t.get('instantiations', [])) == 1:
            t['flags'] = True; t['container'] = False
            t['name'] = 'QFlags<' + t['instantiations'][0]['name'] + '>'
    for cls in api['classes']:
        for field in cls.get('fields', []):
            if field.get('bend_public_record'): normalize_type(field['type'])
        for function in cls['functions']:
            if function.get('bend_public_record'):
                normalize_type(function['return'])
                for argument in function['arguments']: normalize_type(argument['type'])
    result=dict(classes=added,fields=fields,methods=methods)
    api['public_record_supplement']=result
    return result


def restore(api, headers, include_paths, work):
    roots={c['name'] for c in api['classes'] if c.get('generate') and not c.get('namespace')
           and '/private/' not in c.get('source_file','')
           and '/rhi/' not in c.get('source_file','')}
    records=scan(headers,['-x','c++','-std=c++17','-fPIC','-DQT_NO_VERSION_TAGGING',
                          *['-I'+str(path) for path in include_paths]],roots)
    import json
    (Path(work)/'public-records.json').write_text(json.dumps(records,indent=2)+'\n')
    return merge(api,records)

