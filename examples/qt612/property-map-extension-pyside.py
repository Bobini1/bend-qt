"""Maintainer differential probe; run with the pinned PySide 6.12.0 environment.

Qt's extension proxy cannot forward the declared property through a
QQmlPropertyMap subclass's extra dynamic metaobject. A future upstream fix
should make this probe fail, prompting removal of Bend's matching rejection.
"""
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import PySide6
from PySide6.QtCore import QObject, Property, Signal, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QmlElement, QmlExtended, QQmlPropertyMap, QQmlEngine, QQmlComponent

assert PySide6.__version__ == '6.12.0', PySide6.__version__
QML_IMPORT_NAME = 'Probe.PySideMap'
QML_IMPORT_MAJOR_VERSION = 1
instances = []


class Map(QQmlPropertyMap):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._title = 'initial'
        instances.append(self)

    def read_title(self):
        return self._title

    def write_title(self, value):
        self._title = value
        self.changed.emit()

    title = Property(str, read_title, write_title, notify=changed)


@QmlElement
@QmlExtended(Map)
class Root(QObject):
    pass


application = QGuiApplication([])
engine = QQmlEngine()
component = QQmlComponent(engine)
component.setData(b'import Probe.PySideMap 1.0\nRoot { title: "fromqml" }', QUrl())
assert component.isReady(), component.errors()
root = component.create()
assert root is not None, component.errors()
assert instances
assert root.property('title') != 'fromqml'
print('PYSIDE_PROPERTY_MAP_EXTENSION_UNSUPPORTED',
      'title=' + repr(root.property('title')),
      'map_title=' + repr(instances[0].property('title')))
