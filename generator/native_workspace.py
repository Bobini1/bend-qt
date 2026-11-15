"""Keep maintainer intermediates on Linux while retaining requested reports.

The original translation-unit path is never changed. In particular, quoted
includes, __FILE__, and the existing compiler cache keys retain their meaning.
Only the work directory changes. No native cache key is weakened here.
"""
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import threading
import uuid


_active = []
_active_lock = threading.RLock()
_schema = 1


def _absolute(path):
    return Path(os.path.abspath(os.fspath(path)))


def _wsl(environ):
    if sys.platform != 'linux':
        return False
    if environ.get('WSL_DISTRO_NAME') or environ.get('WSL_INTEROP'):
        return True
    try:
        return 'microsoft' in Path('/proc/sys/kernel/osrelease').read_text().lower()
    except OSError:
        return False


def _mounted_drive(path):
    return bool(re.match(r'^/mnt/[A-Za-z](?:/|$)', str(path)))


def _digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        before = os.fstat(stream.fileno())
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
        after = os.fstat(stream.fileno())
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise OSError('Native cache input changed while it was being checked: ' + str(path))
    return result.hexdigest()


def _inside(root, path):
    root, path = Path(root).resolve(), Path(path).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        raise ValueError('Native workspace path escapes its directory: ' + str(path)) from None
    return path


def _atomic_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.read_bytes() == data:
        return False
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def _copy_checked(source, destination, expected=None):
    source, destination = Path(source), Path(destination)
    digest = expected or _digest(source)
    if destination.is_file() and _digest(destination) == digest:
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name('.' + destination.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        shutil.copyfile(source, temporary)
        if _digest(temporary) != digest:
            raise OSError('Native artifact changed while it was being copied: ' + str(source))
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return True


@dataclass(frozen=True)
class VerifiedArtifact:
    """Evidence for an unchanged binary, never permission to relocate its PCH."""
    output: Path
    stamp: Path
    digest: str
    record: dict


def verify_artifact(output, stamp, *, expected_key, hash_field='object'):
    """Check the exact caller-supplied compiler/key and every recorded input.

    Object bytes can move without modification; serialized Clang PCH files
    cannot. Dependencies and their paths are deliberately left untouched.
    """
    output, stamp = Path(output), Path(stamp)
    if output.suffix not in ('.o', '.so') or expected_key is None:
        return None
    try:
        record = json.loads(stamp.read_text())
        if not isinstance(record, dict) or not isinstance(record.get('dependencies'), dict):
            return None
        if json.dumps(record.get('key'), sort_keys=True) != json.dumps(expected_key, sort_keys=True):
            return None
        expected = record[hash_field]
        if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected) or _digest(output) != expected:
            return None
        # Accept ELF64 x86-64 objects/shared objects, never disguised PCH data.
        with output.open('rb') as stream:
            header = stream.read(20)
        if (len(header) != 20 or header[:6] != b'\x7fELF\x02\x01' or
                int.from_bytes(header[16:18], 'little') not in (1, 3) or
                int.from_bytes(header[18:20], 'little') != 62):
            return None
        for name, digest in record['dependencies'].items():
            if (not isinstance(name, str) or not Path(name).is_absolute() or
                    not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest) or
                    not Path(name).is_file() or _digest(name) != digest):
                return None
        return VerifiedArtifact(output.resolve(), stamp.resolve(), expected, record)
    except (OSError, KeyError, TypeError, ValueError):
        return None


@dataclass
class NativeWorkspace:
    source: Path
    requested_work: Path
    work: Path
    enabled: bool
    reason: str
    identity: dict
    imports: list = field(default_factory=list)
    published: list = field(default_factory=list)
    publish_errors: list = field(default_factory=list)
    _lock: object = field(default=None, repr=False)
    _entered: bool = field(default=False, repr=False)

    @property
    def legacy_work(self):
        return self.requested_work

    def __enter__(self):
        if self._entered:
            raise RuntimeError('A native workspace context cannot be entered twice')
        self.requested_work.mkdir(parents=True, exist_ok=True)
        self.work.mkdir(parents=True, exist_ok=True)
        if self.enabled:
            import fcntl
            container = self.work.parent
            identity_path = container / 'identity.json'
            if identity_path.exists():
                if json.loads(identity_path.read_text()) != self.identity:
                    raise RuntimeError('Native workspace identity does not match its cache directory')
            else:
                _atomic_bytes(identity_path, (json.dumps(self.identity, indent=2) + '\n').encode())
            self._lock = (container / 'build.lock').open('a+b')
            try:
                fcntl.flock(self._lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BaseException:
                self._lock.close(); self._lock = None
                raise RuntimeError('This native workspace is already in use: ' + str(self.work)) from None
            with _active_lock:
                _active.append(self)
        self._entered = True
        try:
            self.write_receipt()
        except BaseException:
            # __exit__ is not called if __enter__ fails.
            with _active_lock:
                _active[:] = [value for value in _active if value is not self]
            if self._lock:
                import fcntl
                fcntl.flock(self._lock.fileno(), fcntl.LOCK_UN)
                self._lock.close(); self._lock = None
            self._entered = False
            raise
        return self

    def __exit__(self, error_type, error, traceback):
        try:
            if self.enabled:
                try:
                    self.publish_reports()
                    self.write_receipt()
                except Exception as publication_error:
                    self.publish_errors.append(str(publication_error))
                    if error_type is None:
                        raise
        finally:
            with _active_lock:
                _active[:] = [value for value in _active if value is not self]
            if self._lock:
                import fcntl
                fcntl.flock(self._lock.fileno(), fcntl.LOCK_UN)
                self._lock.close(); self._lock = None
            self._entered = False
        return False

    def diagnostic_path(self, path):
        """Map a local report path to its requested, immediately readable path."""
        path = Path(path)
        if not path.is_absolute():
            path = self.work / path
        relative = _inside(self.work, path).relative_to(self.work.resolve())
        destination = _inside(self.requested_work, self.requested_work / relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        return destination

    def publish(self, paths):
        """Publish explicit final artifacts, never compiler inputs or cache stamps."""
        if isinstance(paths, (str, Path)):
            paths = [paths]
        for path in paths:
            path = Path(path)
            source = _inside(self.work, path if path.is_absolute() else self.work / path)
            relative = source.relative_to(self.work.resolve())
            if not source.is_file():
                continue
            destination = self.diagnostic_path(source)
            if source != destination:
                _copy_checked(source, destination)
            name = relative.as_posix()
            if name not in self.published:
                self.published.append(name)

    def publish_reports(self):
        if not self.enabled:
            return
        reports = [path for path in self.work.rglob('*') if path.is_file() and
            path.suffix in ('.log', '.json') and not path.name.endswith('-cache.json')]
        self.publish(reports)

    def write_receipt(self):
        receipt = dict(schema=_schema, enabled=self.enabled, reason=self.reason,
            source=str(self.source), requested_work=str(self.requested_work), work=str(self.work),
            identity=self.identity,
            original_source_path_preserved=True, pch_paths_rewritten=False,
            imported_artifacts=self.imports, published_artifacts=self.published,
            publication_errors=self.publish_errors)
        _atomic_bytes(self.requested_work / 'native-workspace.json', (json.dumps(receipt, indent=2) + '\n').encode())

    def import_legacy_artifact(self, output, stamp, *, expected_key, hash_field='object'):
        """Reuse an exact checked object; preserve legacy files and dependencies.

        The caller must still apply its usual cache check to the copied stamp.
        A changed generated-header path needs a rebuild/certificate in the
        compiler cache, not a dependency rewrite in this filesystem helper.
        """
        if not self.enabled:
            return False
        # Older unsharded keys canonicalized source_path and did not record
        # the logical source filename. A symlink in another directory can
        # therefore have different quoted-header/__FILE__ semantics while
        # retaining the same old key. Its mutable .d file is not a certificate
        # for the successful object. Sharded source paths were already resolved
        # before compilation; other imports need the new explicit source key.
        if (isinstance(expected_key, dict) and 'source_path' in expected_key and
                not expected_key.get('sharding') and
                expected_key.get('logical_source_path') != str(self.source)):
            return False
        source = _inside(self.legacy_work, self.legacy_work / output)
        source_stamp = _inside(self.legacy_work, self.legacy_work / stamp)
        destination = _inside(self.work, self.work / output)
        destination_stamp = _inside(self.work, self.work / stamp)
        if destination.exists() or destination_stamp.exists():
            return False
        proof = verify_artifact(source, source_stamp, expected_key=expected_key, hash_field=hash_field)
        if proof is None:
            return False
        _copy_checked(proof.output, destination, proof.digest)
        _atomic_bytes(destination_stamp, (json.dumps(proof.record, indent=2) + '\n').encode())
        self.imports.append(dict(output=str(output), stamp=str(stamp), sha256=proof.digest,
            dependency_paths_preserved=True, dependency_count=len(proof.record['dependencies'])))
        return True


def open_workspace(source, requested_work, *, environ=None):
    """Select an isolated cache without staging or changing the source path.

    BQT_NATIVE_WORKSPACE=off disables relocation. An absolute path selects a
    cache root, while 'on' forces the ordinary Linux cache. The default 'auto'
    relocates /mnt/<drive> work directories only when running inside WSL.
    """
    environ = os.environ if environ is None else environ
    source, requested = _absolute(source), _absolute(requested_work)
    option = environ.get('BQT_NATIVE_WORKSPACE', 'auto').strip()
    setting = option.lower()
    if setting in ('off', '0', 'false', 'no', 'disable'):
        enabled, reason, root = False, 'disabled', None
    else:
        configured = setting not in ('', 'auto', 'on', '1', 'true', 'yes')
        enabled = configured or setting in ('on', '1', 'true', 'yes') or (_wsl(environ) and _mounted_drive(requested))
        reason = 'configured-root' if configured else ('forced' if setting in ('on', '1', 'true', 'yes') else 'wsl-mounted-workspace' if enabled else 'native-work-directory')
        if configured:
            root = Path(option).expanduser()
            if not root.is_absolute():
                raise ValueError('BQT_NATIVE_WORKSPACE must be auto, on, off or an absolute directory')
        else:
            cache = Path(environ.get('XDG_CACHE_HOME', '')).expanduser()
            if not cache.is_absolute():
                cache = Path.home() / '.cache'
            root = cache / 'bend-qt-generator/native-workspaces'
    identity = dict(schema=_schema, source=str(source), source_resolved=str(source.resolve()),
        requested_work=str(requested), requested_work_resolved=str(requested.resolve()))
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    work = _absolute(root) / key / 'work' if enabled else requested
    return NativeWorkspace(source, requested, work, enabled, reason, identity)


def diagnostic_path(path):
    """Find active mappings in compiler worker threads as well as the caller."""
    path = _absolute(path)
    with _active_lock:
        candidates = []
        for workspace in _active:
            try:
                path.resolve().relative_to(workspace.work.resolve())
                candidates.append(workspace)
            except ValueError:
                pass
        if not candidates:
            return path
        return max(candidates, key=lambda item: len(item.work.parts)).diagnostic_path(path)


def actual_work(requested_work):
    """Find private intermediates from the last requested-location receipt.

    Missing receipts retain the legacy work layout. A present but mismatched
    receipt fails explicitly, rather than reading a different source's cache.
    The receipt is location metadata, not a compiler-cache validity certificate.
    """
    requested = _absolute(requested_work)
    report = requested / 'native-workspace.json'
    if not report.exists():
        return requested
    try:
        record = json.loads(report.read_text())
        if record['schema'] != _schema or record['requested_work'] != str(requested):
            raise ValueError('Mismatched native workspace receipt')
        work = Path(record['work'])
        if not work.is_absolute():
            raise ValueError('Native workspace receipt has a relative work directory')
        if not record['enabled']:
            if work != requested:
                raise ValueError('Disabled native workspace points to another directory')
            return work
        identity = record['identity']
        if (identity['schema'] != _schema or identity['requested_work'] != str(requested) or
                identity['requested_work_resolved'] != str(requested.resolve()) or
                identity['source'] != record['source'] or
                identity['source_resolved'] != str(Path(record['source']).resolve())):
            raise ValueError('Native workspace source identity changed')
        key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        if (work.name != 'work' or work.parent.name != key or
                json.loads((work.parent / 'identity.json').read_text()) != identity):
            raise ValueError('Native workspace cache identity does not match its receipt')
        if not work.is_dir():
            raise ValueError('Native workspace intermediate directory no longer exists')
        return work
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise ValueError('Cannot resolve private native intermediates from ' + str(report) + ': ' + str(error)) from error
