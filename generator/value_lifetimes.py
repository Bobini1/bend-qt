"""Observed origins for values that contain non-owning Qt storage pointers."""
from pathlib import Path

TYPES = {'QTextBlock', 'QTextFragment', 'QTextTableCell', 'QTextBlock::iterator',
         'QTextFrame::iterator', 'QTreeWidgetItemIterator'}


def before_call(g, m):
    f, owner = m['function'], m['function']['declaring_class']
    prefix = []
    name = f['name']
    if owner == 'QObject' and name == 'blockSignals':
        prefix += ['if (!note_text_mutation(r, qobject_cast<QTextDocument *>(self))) return true;']
    if owner == 'QSignalBlocker' and f['constructor'] and m['args'] and m['args'][0].get('name') == 'QObject':
        prefix += ['if (!note_text_mutation(r, qobject_cast<QTextDocument *>(a0))) return true;']
    if owner == 'QSignalBlocker' and name in ('reblock', 'unblock'):
        prefix += ['for (const auto &edge : retentions) if (edge.owner == r->self) {',
                   '    auto *target = entry(edge.target);',
                   '    if (target && target->object && !note_text_mutation(r, qobject_cast<QTextDocument *>(target->object))) return true;', '}']
    if not f['constructor'] and not f['static'] and not f['const']:
        document = None
        if owner == 'QTextDocument':
            document = 'self'
        elif owner == 'QTextCursor' and (name.startswith(('insert', 'delete', 'remove', 'merge')) or
                name in ('setBlockCharFormat', 'setBlockFormat', 'setCharFormat', 'beginEditBlock', 'joinPreviousEditBlock', 'endEditBlock')):
            document = 'self->document()'
        elif owner in ('QTextFrame', 'QTextTable', 'QTextList', 'QTextBlock', 'QSyntaxHighlighter') and name not in ('operator=',):
            document = 'self->document()'
        elif owner == 'QTextTableCell' and name.startswith('set'):
            document = 'self->isValid() ? self->firstCursorPosition().document() : nullptr'
        elif owner in ('QTextEdit', 'QPlainTextEdit', 'QTextBrowser') and name in (
                'setPlainText', 'setHtml', 'setMarkdown', 'setText', 'clear', 'append', 'appendPlainText', 'appendHtml',
                'insertPlainText', 'insertHtml', 'cut', 'paste', 'undo', 'redo', 'setCurrentCharFormat',
                'mergeCurrentCharFormat', 'setFontFamily', 'setFontPointSize', 'setFontWeight', 'setFontUnderline',
                'setFontItalic', 'setTextColor', 'setTextBackgroundColor', 'setCurrentFont'):
            document = 'self->document()'
        if document:
            edit = 1 if owner == 'QTextCursor' and name in ('beginEditBlock', 'joinPreviousEditBlock') else -1 if owner == 'QTextCursor' and name == 'endEditBlock' else 0
            prefix += [f'if (!note_text_mutation(r, {document}, {edit})) return true;']
    if owner in TYPES and m['args'] and (f['constructor'] or f['name'] == 'operator='):
        prefix += ['call_scope.value_origin = r->arguments[0].word;']
    if owner == 'QTreeWidgetItemIterator' and f['constructor'] and m['args']:
        source = m['args'][0].get('name')
        if source == 'QTreeWidget':
            return prefix + ['if (!a0) return fail(r, EINVAL, "Tree iteration requires a widget");']
        if source == 'QTreeWidgetItem':
            return prefix + ['if (!a0 || !a0->treeWidget()) return fail(r, EINVAL, "Tree iteration requires an item installed in a widget");']
    if owner not in TYPES or f['constructor'] or f['static']:
        return prefix
    lines = prefix
    if owner in ('QTextBlock::iterator', 'QTextFrame::iterator'):
        safe = {'atEnd', 'operator==', 'operator!=', 'operator='}
        if f['name'] not in safe:
            lines += ['auto *origin = value_guard(r->self);',
                      'if (!origin || !origin->document) return fail(r, EINVAL, "Default text iterator has no document origin");']
        if f['name'] in ('operator++', 'fragment'):
            lines += ['if (self->atEnd()) return fail(r, ERANGE, "Text iterator is at its end");']
        if f['name'] == 'operator--':
            begin = 'origin->block_begin' if owner == 'QTextBlock::iterator' else 'origin->frame_begin'
            lines += [f'if (*self == {begin}) return fail(r, ERANGE, "Text iterator is at its beginning");']
    if owner == 'QTreeWidgetItemIterator' and f['name'] in ('operator+=', 'operator-='):
        lines += ['if (int32_t(r->arguments[0].word) == INT32_MIN) return fail(r, ERANGE, "Tree iterator displacement is outside its safe range");']
    return lines


def after_call(g, m):
    f = m['function']
    if f['declaring_class'] in TYPES and f['name'] == 'operator=':
        # Assignment has already changed the native storage. Even a failed
        # return-value conversion must not leave its previous origin attached.
        # If acquiring the new guard fails, revoke and dispose the receiver
        # while the source argument (and its origin) remain pinned by this call.
        return ['BqtRequest assigned_guard = *r;',
                'assigned_guard.error = 0; assigned_guard.message = nullptr;',
                'if (!reset_value_guard(&assigned_guard, r->self)) {',
                '    if (auto *assigned = entry(r->self)) {',
                '        auto *storage = assigned->value;',
                '        auto destroy = assigned->destroy;',
                '        invalidate(r->self);',
                '        if (destroy) destroy(storage);',
                '    }',
                '    if (!r->error) fail(r, assigned_guard.error ? assigned_guard.error : ESTALE,',
                '        assigned_guard.message ? assigned_guard.message : "Assigned Qt value lost its origin");',
                '    return true;', '}']
    return []


def cpp(g):
    source = (Path(__file__).parent / 'templates/value_lifetimes.cpp').read_text()
    source = source.replace('@VALUE_LIFETIME_CASES@', ' '.join(
        f'case {g.ids[name]}:' for name in sorted(TYPES) if name in g.ids))
    for name in TYPES | {'QTextDocument', 'QTreeWidget', 'QTreeWidgetItem'}:
        source = source.replace('@' + name + '@', str(g.ids.get(name, 0)))
    return source


def contains(t):
    return t.get('name') in TYPES or any(contains(child) for child in t.get('children', []))
