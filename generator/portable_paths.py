"""Machine-independent paths in distributed package files.

Generation runs against a Qt installation and a workspace whose locations
differ between maintainers and CI runners. Distributed files record Qt paths
relative to the installation, as <QT>/include/..., and workspace paths
relative to the workspace, so packages built on different machines are
byte-identical and do not reveal the build machine's directories.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _prefixes(qt):
    qt = Path(qt)
    rows = [(str(path), '<QT>') for path in dict.fromkeys((qt.absolute(), qt.resolve()))]
    rows += [(str(path), '.') for path in dict.fromkeys((ROOT, ROOT.absolute()))]
    # A Qt installation inside the workspace is still recorded as <QT>.
    return sorted(rows, key=lambda row: -len(row[0]))


def _rewrite(text, prefixes):
    for prefix, replacement in prefixes:
        if text == prefix:
            return replacement
        text = text.replace(prefix + '/', '' if replacement == '.' else replacement + '/')
    return text


def portable(value, qt):
    """Returns value with Qt and workspace paths made relative, in keys and strings."""
    prefixes = _prefixes(qt)

    def walk(item):
        if isinstance(item, dict):
            result = {}
            for key, child in item.items():
                key = _rewrite(key, prefixes) if isinstance(key, str) else key
                if key in result:
                    raise ValueError('Distinct build paths share a portable name: ' + key)
                result[key] = walk(child)
            return result
        if isinstance(item, (list, tuple)):
            return [walk(child) for child in item]
        return _rewrite(item, prefixes) if isinstance(item, str) else item
    result = walk(value)
    require_portable(json.dumps(result, ensure_ascii=False), qt, 'portable value')
    return result


def require_portable(text, qt, label):
    """Rejects distributed text that names this machine's Qt, workspace or home directory."""
    locations = [str(path) for path in (Path(qt).absolute(), Path(qt).resolve(), ROOT, ROOT.absolute())]
    home = Path.home()
    if len(home.parts) > 1:
        locations.append(str(home) + '/')
    for location in dict.fromkeys(locations):
        if location in text:
            raise ValueError(label + ' names a build-machine path: ' + location)
