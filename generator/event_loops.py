"""Operations that run a Qt event loop end it when a Bend handler fails.

A handler that fails has no caller to tell, so the Bend-started operation it
ran under fails with it (see CallFrame in templates/runtime.cpp). When that
operation runs an event loop, waiting for the loop to finish on its own could
take forever, so the operation registers how to end it: the application loop,
its own QEventLoop, or the dialog, menu or drag that owns the loop.
"""

APPLICATIONS = ('QCoreApplication', 'QGuiApplication', 'QApplication')
# Static helpers that create a dialog and run it modally.
DIALOG_HELPERS = {
    'QMessageBox': ('information', 'question', 'warning', 'critical', 'about', 'aboutQt'),
    'QFileDialog': ('getOpenFileName', 'getOpenFileNames', 'getSaveFileName', 'getExistingDirectory',
                    'getOpenFileUrl', 'getOpenFileUrls', 'getSaveFileUrl', 'getExistingDirectoryUrl'),
    'QInputDialog': ('getText', 'getMultiLineText', 'getItem', 'getInt', 'getDouble'),
    'QColorDialog': ('getColor',),
    'QFontDialog': ('getFont',),
}


def _is(g, name, base):
    return name == base or (name in g.classes and base in g.all_bases(name))


def before_call(g, m):
    """Lines run after `self` and the arguments are checked."""
    f = m['function']
    name, owner = f['name'], m['class']
    stop = None
    if name == 'exec' and f['static'] and owner in APPLICATIONS:
        return ['call_scope.allow_event_loop();', 'if (CallFrame::current) CallFrame::current->application_loop = true;']
    if name == 'exec' and not f['static'] and _is(g, owner, 'QEventLoop'):
        return ['call_scope.allow_event_loop();', 'if (CallFrame::current) CallFrame::current->loop = self;']
    if name == 'exec' and not f['static'] and _is(g, owner, 'QDialog'):
        stop = '[target = QPointer<QDialog>(self)] { if (target) target->done(QDialog::Rejected); }'
    elif name == 'exec' and not f['static'] and _is(g, owner, 'QMenu'):
        stop = '[target = QPointer<QMenu>(self)] { if (target) target->close(); }'
    elif name == 'exec' and not f['static'] and _is(g, owner, 'QDrag'):
        stop = '[] { QDrag::cancel(); }'
    elif f['static'] and name in DIALOG_HELPERS.get(f['declaring_class'], ()):
        stop = '[] { if (auto *dialog = QApplication::activeModalWidget()) dialog->close(); }'
    if stop is None:
        return []
    # Modal helpers can destroy their dialog and children after their nested
    # exec returns. Keep the native-call guard through that cleanup tail.
    return [f'if (CallFrame::current) CallFrame::current->stop = {stop};']
