"""Explicitly constructed Qt application objects.

A program constructs its single application object as a C++ main does, with
QCoreApplication.new, QGuiApplication.new or QApplication.new, and runs it with
the bound static exec. Constructors and static functions of QtGui and QtWidgets
classes, and of classes deriving from them, check for the GUI application they
need first, because Qt aborts the process (for example "Must construct a
QApplication before a QWidget") instead of reporting an error.
"""
GUI, WIDGETS = 1, 2
KINDS = {'QCoreApplication': 0, 'QGuiApplication': GUI, 'QApplication': WIDGETS}
# Qt documents these for use before the application object exists.
BEFORE_APPLICATION_CLASSES = {'QSurfaceFormat'}
BEFORE_APPLICATION_FUNCTIONS = {('QtWebEngineQuick', 'initialize'), ('QtWebView', 'initialize'),
                                ('QQuick3D', 'idealSurfaceFormat')}


def emit(g):
    from module_partitions import exports_class
    for name, kind in KINDS.items():
        if name not in g.ids or not exports_class(g, name):
            continue
        operation = g.next_id
        g.next_id += 1
        g.cases.append(f'case {operation}: {{\n    return create_application(r, {kind}, {g.ids[name]});\n}}')
        g.emit_effect(name + '.new', [], {'kind': 'object', 'bend': name, 'raw': 'U32'}, operation)


def requirement(g, m):
    """The application kind a constructor or static function needs, or 0."""
    f, owner = m['function'], m['class']
    if not (f['constructor'] or f['static']) or owner in KINDS or owner in BEFORE_APPLICATION_CLASSES:
        return 0
    if (owner, f['name']) in BEFORE_APPLICATION_FUNCTIONS:
        return 0
    # Static setters of global defaults, such as QQuickWindow.setGraphicsApi,
    # are meant to precede the application.
    if f['static'] and f['name'].startswith('set'):
        return 0
    # A class needs the application its own module or a base class's module
    # requires: QQuickView through QWindow, QChart through QGraphicsWidget.
    # Module dependencies are too coarse: QSqlDatabase and QSignalSpy are
    # usable from a QCoreApplication program.
    packages, pending, seen = set(), [owner], set()
    while pending:
        name = pending.pop()
        if name in seen or name not in g.classes:
            continue
        seen.add(name)
        packages.add(g.classes[name].get('package'))
        pending.extend(g.classes[name].get('bases', []))
    return WIDGETS if 'PySide6.QtWidgets' in packages else GUI if 'PySide6.QtGui' in packages else 0


def guard(g, m, operation):
    kind = requirement(g, m)
    if not kind:
        return
    prefix = f'case {operation}: {{'
    for index in range(len(g.cases) - 1, -1, -1):
        if g.cases[index].startswith(prefix):
            g.cases[index] = (prefix + f'\n    if (!require_application(r, {kind})) return true;'
                              + g.cases[index][len(prefix):])
            return
