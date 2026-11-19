"""Resolve complete REUSE expressions in byte-verified upstream snapshots."""
from contextlib import ExitStack
import hashlib
from pathlib import Path
import tarfile
import tempfile

from qt_licenses import allows


class Resolver:
    def __init__(self, snapshots):
        from importlib.metadata import version
        if version('reuse') != '5.1.1':
            raise ValueError('Use maintainer REUSE 5.1.1, matching Qt source SBOM generation')
        self.snapshots, self.projects, self.temporary = snapshots, {}, ExitStack()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.temporary.close()

    def project(self, source):
        if source not in self.snapshots:
            return None
        if source not in self.projects:
            from reuse.project import Project
            row = self.snapshots[source]; archive = Path(row['file'])
            with archive.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != row['sha256']:
                    raise ValueError('Corresponding source snapshot changed: ' + source)
            temporary = Path(self.temporary.enter_context(tempfile.TemporaryDirectory(prefix='bend-qt-reuse-')))
            with tarfile.open(archive, 'r:*') as snapshot:
                # Python's data filter rejects escaping links, paths and device
                # entries. Use a fresh directory so cached annotations cannot
                # acquire a different license than the archived source.
                snapshot.extractall(temporary, filter='data')
            roots = list(temporary.iterdir())
            if len(roots) != 1 or not roots[0].is_dir():
                raise ValueError('A source archive needs one repository root: ' + str(archive))
            root = roots[0].resolve()
            for overlay in row.get('overlays', []):
                relative = Path(overlay['path']); overlay_file = Path(overlay['file'])
                if relative.is_absolute() or '..' in relative.parts:
                    raise ValueError('A source overlay escapes its repository')
                data = overlay_file.read_bytes()
                if hashlib.sha256(data).hexdigest() != overlay['sha256']:
                    raise ValueError('A source overlay differs from its prepared bytes')
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.resolve().is_relative_to(root):
                    raise ValueError('A source overlay traverses an external link')
                target.write_bytes(data)
            self.projects[source] = root, Project.from_directory(root)
        return self.projects[source]

    def resolve(self, match, flavor):
        rows = []
        for candidate in match['candidates']:
            sources = [root['downloadLocation'] for root in candidate['repositories']]
            if len(sources) != 1 or not (project := self.project(sources[0])):
                rows.append(candidate); continue
            root, metadata = project
            relative = Path(candidate['path'])
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError('Source SPDX path escapes its repository: ' + str(relative))
            path = (root / relative).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise ValueError('Source SPDX file is absent from its snapshot: ' + str(relative))
            expected = dict(value.split(': ', 1) for value in candidate['checksums']).get('SHA1')
            if hashlib.sha1(path.read_bytes()).hexdigest() != expected:
                raise ValueError('The source snapshot differs from its source SPDX: ' + str(relative))
            annotations = metadata.reuse_info_of(path)
            expressions = sorted({str(expression) for info in annotations for expression in info.spdx_expressions})
            expression = ' AND '.join('(' + value + ')' for value in expressions) if expressions else None
            annotation_paths = {Path(info.source_path) if Path(info.source_path).is_absolute() else root / info.source_path
                                for info in annotations if info.source_path}
            evidence = {}
            # A set's order depends on the process's hash seed; sort it so the
            # release manifest is the same on every run.
            for annotation in sorted(annotation_paths):
                if not annotation.resolve().is_relative_to(root):
                    raise ValueError('A REUSE annotation escapes its source snapshot')
                evidence[str(annotation.relative_to(root))] = hashlib.sha256(annotation.read_bytes()).hexdigest()
            rows.append(dict(candidate, expression=expression, allowed=allows(expression, flavor) if expression else None,
                reuse_copyright=sorted({line for info in annotations for line in info.copyright_lines}),
                reuse_evidence=evidence, source_archive_sha256=self.snapshots[sources[0]]['sha256']))
        decisions = {row['allowed'] for row in rows}
        return dict(match, candidates=rows, allowed=next(iter(decisions)) if len(decisions) == 1 else None,
                    boundary='Exact installed/source bytes and pinned REUSE annotation precedence; ambiguous origins remain unresolved')
