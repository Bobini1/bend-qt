"""Exact Qt/PySide source pins for independently built Hub packages."""
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
DEFAULT = '6.12.0'


def target(version):
    targets = json.loads((HERE / 'qt_targets.json').read_text())
    if version not in targets:
        raise ValueError('No reviewed Qt/PySide build target for ' + str(version))
    result = targets[version]
    return dict(result, qt=version, api_version='.'.join(version.split('.')[:2]),
                package_version=version + '.' + str(result['binding_revision']))


def installed_version(qt):
    header = Path(qt) / 'include/QtCore/qtcoreversion.h'
    match = re.search(r'^#define QTCORE_VERSION_STR "([0-9]+\.[0-9]+\.[0-9]+)"', header.read_text(), re.M)
    if not match:
        raise ValueError('Cannot determine the Qt kit version from ' + str(header))
    return match[1]


def abi(source, argument_capacity, version=DEFAULT):
    target(version)
    return source.replace('@ARGUMENT_CAPACITY@', str(argument_capacity)).replace(
        '#define BQT_QT_RUNTIME "6.12.0"', '#define BQT_QT_RUNTIME "' + version + '"')
