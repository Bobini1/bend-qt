"""Read module and binary licensing from the selected Qt build's SPDX SBOMs.

The Qt installation is the evidence, not a second hand-maintained module list.
Unknown expressions remain unknown, and cannot enter a restricted distribution.
"""
import hashlib
import json
from pathlib import Path
import re


PERMISSIVE = {'0BSD', 'Apache-2.0', 'BSD-2-Clause', 'BSD-3-Clause', 'BSL-1.0',
              'CC0-1.0', 'ISC', 'MIT', 'Unlicense', 'Zlib', 'Libpng', 'libtiff',
              'Unicode-DFS-2016', 'Unicode-3.0', 'FTL', 'MPL-2.0'}
LGPL = {'LGPL-2.0-only', 'LGPL-2.0-or-later', 'LGPL-2.1-only',
        'LGPL-2.1-or-later', 'LGPL-3.0-only', 'LGPL-3.0-or-later'}
GPL = {'GPL-2.0-only', 'GPL-2.0-or-later', 'GPL-3.0-only', 'GPL-3.0-or-later'}


def allows(expression, flavor, *, code_generator=False):
    if flavor not in ('lgpl', 'gpl'):
        raise ValueError('Choose the lgpl or gpl distribution')
    tokens = re.findall(r'\(|\)|[^\s()]+', expression)
    position = 0

    def atom():
        nonlocal position
        if position >= len(tokens):
            raise ValueError('Incomplete SPDX expression: ' + expression)
        token = tokens[position]; position += 1
        if token == '(':
            result = either()
            if position >= len(tokens) or tokens[position] != ')':
                raise ValueError('Unbalanced SPDX expression: ' + expression)
            position += 1
            return result
        if token in (')', 'AND', 'OR', 'WITH'):
            raise ValueError('Invalid SPDX expression: ' + expression)
        if token in LGPL or token in PERMISSIVE:
            result = True
        elif token in GPL:
            result = flavor == 'gpl'
        elif token == 'LicenseRef-Qt-Commercial':
            result = False
        else:
            result = None
        if position < len(tokens) and tokens[position] == 'WITH':
            position += 1
            if position >= len(tokens) or tokens[position] in ('(', ')', 'AND', 'OR', 'WITH'):
                raise ValueError('Missing SPDX exception: ' + expression)
            exception = tokens[position]; position += 1
            if exception != 'Qt-GPL-exception-1.0':
                result = None
            elif token not in GPL:
                result = None
            elif code_generator and token in GPL:
                # Standalone generator output has an explicit exception. This
                # does not authorize linking GPL libraries into an LGPL app.
                result = True
        return result

    def both():
        nonlocal position
        result = atom()
        while position < len(tokens) and tokens[position] == 'AND':
            position += 1
            next_value = atom()
            result = False if result is False or next_value is False else None if None in (result, next_value) else True
        return result

    def either():
        nonlocal position
        result = both()
        while position < len(tokens) and tokens[position] == 'OR':
            position += 1
            next_value = both()
            result = True if result is True or next_value is True else None if None in (result, next_value) else False
        return result

    result = either()
    if position != len(tokens):
        raise ValueError('Unexpected SPDX expression suffix: ' + expression)
    return result


class Inventory:
    def __init__(self, qt):
        self.qt = Path(qt).resolve()
        self.modules, self.files, self.evidence = {}, {}, {}
        self.documents, self.repositories = {}, {}
        paths = sorted((self.qt / 'sbom').glob('*.spdx.json'))
        if not paths:
            raise ValueError('The Qt runtime needs its matching SPDX software bill of materials')
        for path in paths:
            data = json.loads(path.read_text())
            self.evidence[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
            self.documents[str(path)] = data
            packages = {p['SPDXID']: p for p in data.get('packages', [])}
            roots = [packages[r['relatedSpdxElement']] for r in data.get('relationships', [])
                     if r['relationshipType'] == 'DESCRIBES' and r['relatedSpdxElement'] in packages]
            if roots:
                self.repositories[str(path)] = roots
            for package in data.get('packages', []):
                comment = package.get('comment', '')
                target = re.search(r'^CMake exported target name: Qt6::([A-Za-z0-9_]+)\s*$', comment, re.M)
                if not target:
                    continue
                name = 'Qt' + target[1]
                row = dict(module=name, expression=package.get('licenseConcluded', 'NOASSERTION'),
                    declared=package.get('licenseDeclared', 'NOASSERTION'),
                    copyright=package.get('copyrightText', ''), evidence=str(path),
                    spdx_id=package['SPDXID'], repository=data.get('name'),
                    source=package.get('downloadLocation'), references=package.get('externalRefs', []))
                old = self.modules.setdefault(name, row)
                if old['expression'] != row['expression']:
                    raise ValueError('Conflicting Qt module license evidence: ' + name)
            for file in data.get('files', []):
                relative = Path(file['fileName'])
                if relative.is_absolute() or '..' in relative.parts:
                    raise ValueError('An SPDX binary path escapes the Qt installation')
                row = dict(path=relative.as_posix(), expression=file.get('licenseConcluded', 'NOASSERTION'),
                    copyright=file.get('copyrightText', ''), checksums=file.get('checksums', []),
                    evidence=str(path), spdx_id=file['SPDXID'], repositories=roots)
                old = self.files.setdefault(relative.as_posix(), row)
                if old['expression'] != row['expression']:
                    raise ValueError('Conflicting Qt binary license evidence: ' + row['path'])

    def binary(self, path, flavor, *, verify=True):
        """Resolve SONAME aliases and verify the exact binary described by Qt.

        A module license is not evidence for an unrelated binary in its directory.
        In particular, unlisted FFmpeg/ICU binaries require their own evidence.
        """
        path = Path(path)
        if not path.is_absolute():
            path = self.qt / path
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(self.qt):
            raise ValueError('A runtime binary escapes the Qt installation: ' + str(path))
        relative = resolved.relative_to(self.qt).as_posix()
        row = self.files.get(relative)
        if not row or allows(row['expression'], flavor) is not True:
            raise ValueError('No permitted binary license evidence for ' + relative)
        if verify:
            supported = {'SHA1': 'sha1', 'SHA256': 'sha256', 'SHA512': 'sha512'}
            checks = [c for c in row['checksums'] if c['algorithm'] in supported]
            if not checks:
                raise ValueError('No verifiable SPDX checksum for ' + relative)
            algorithms = {c['algorithm']: hashlib.new(supported[c['algorithm']]) for c in checks}
            with resolved.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    for digest in algorithms.values():
                        digest.update(chunk)
            if any(algorithms[c['algorithm']].hexdigest() != c['checksumValue'].lower() for c in checks):
                raise ValueError('The runtime binary differs from its SPDX evidence: ' + relative)
        return dict(row, alias=path.relative_to(self.qt).as_posix(),
                    sha256=hashlib.sha256(resolved.read_bytes()).hexdigest())

    def distribution(self, modules, flavor):
        included, excluded, unknown = [], [], []
        for name in modules:
            row = self.modules.get(name)
            decision = allows(row['expression'], flavor) if row else None
            value = dict(row or dict(module=name, expression='NOASSERTION'), allowed=decision)
            (included if decision is True else excluded if decision is False else unknown).append(value)
        return dict(flavor=flavor, included=included, excluded=excluded, unknown=unknown,
                    evidence_sha256=self.evidence)

    def code_generator(self, path):
        row = self.binary(path, 'gpl')
        if ('qt-tool-' not in row['spdx_id'] or not row['path'].startswith(('bin/', 'libexec/'))
                or allows(row['expression'], 'lgpl', code_generator=True) is not True):
            raise ValueError('No standalone code-generator license evidence for ' + row['path'])
        return dict(row, purpose='standalone-code-generator', application_links_to_tool=False)

    def require(self, modules, flavor):
        report = self.distribution(modules, flavor)
        rejected = report['excluded'] + report['unknown']
        if rejected:
            raise ValueError(f'The {flavor} distribution cannot include these Qt modules: '
                             + ', '.join(row['module'] for row in rejected))
        return report


class SourceInventory:
    """Match installed data to Qt's source SPDX records by exact content.

    LicenseInfoInFile lists license identifiers, not their AND/OR relationship.
    Multiple identifiers therefore remain unresolved unless the exact file's
    SPDX expression or separate REUSE evidence supplies that relationship.
    """
    def __init__(self, qt, binary_inventory=None):
        self.qt = Path(qt).resolve()
        inventory = binary_inventory or Inventory(self.qt)
        self.by_sha1, self.evidence = {}, {}
        for path in sorted((self.qt / 'sbom').glob('*.source.spdx')):
            raw = path.read_bytes()
            self.evidence[str(path)] = hashlib.sha256(raw).hexdigest()
            binary = str(path.with_name(path.name.replace('.source.spdx', '.spdx.json')))
            roots = inventory.repositories.get(binary, [])
            for block in raw.decode().split('\n\n'):
                if not block.startswith('FileName: '):
                    continue
                values = {}
                for match in re.finditer(r'^([A-Za-z]+): (<text>.*?</text>|[^\n]*)', block, re.M | re.S):
                    values.setdefault(match[1], []).append(match[2].removeprefix('<text>').removesuffix('</text>'))
                checksum = next((value.split(': ', 1)[1] for value in values.get('FileChecksum', []) if value.startswith('SHA1: ')), None)
                if not checksum:
                    continue
                row = dict(path=values['FileName'][0], checksums=values['FileChecksum'],
                    license_concluded=values.get('LicenseConcluded', ['NOASSERTION'])[0],
                    license_info=values.get('LicenseInfoInFile', []),
                    copyright='\n'.join(values.get('FileCopyrightText', [])), evidence=str(path),
                    repositories=roots)
                self.by_sha1.setdefault(checksum, []).append(row)

    def match(self, path, flavor):
        path = Path(path); raw = path.read_bytes()
        candidates = self.by_sha1.get(hashlib.sha1(raw).hexdigest(), [])
        expressions = re.findall(r'SPDX-License-Identifier:\s*([^\r\n]+)', raw.decode('utf-8', errors='replace'))
        expression = None
        if expressions:
            cleaned = {value.removesuffix('-->').removesuffix('*/').strip() for value in expressions}
            if len(cleaned) == 1:
                expression = cleaned.pop()
        rows = []
        for candidate in candidates:
            chosen = candidate['license_concluded']
            if chosen == 'NOASSERTION':
                chosen = expression or (candidate['license_info'][0] if len(candidate['license_info']) == 1 else None)
            # Preserve every identifier in the source SPDX evidence. A textual
            # header cannot introduce a license not present in that evidence.
            if expression:
                identifiers = set(re.findall(r'[^\s()]+', expression)) - {'AND', 'OR', 'WITH'}
                if not identifiers <= set(candidate['license_info']):
                    chosen = None
            rows.append(dict(candidate, expression=chosen, allowed=allows(chosen, flavor) if chosen else None))
        return dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest(), candidates=rows,
                    exact_source_match=bool(rows),
                    allowed=rows[0]['allowed'] if len(rows) == 1 else None,
                    boundary='Multiple source origins or unordered license identifiers require additional provenance/REUSE evidence')
