"""QObject origins of copied JavaScript, cursor and QML property values."""
from pathlib import Path

TYPES = {'QJSValue', 'QJSManagedValue', 'QJSValueIterator', 'QTextCursor', 'QQmlProperty', 'QSqlQuery'}


def inventory(g):
    """Report the checked boundary without implying arbitrary aggregate closure."""
    import aggregate_fields
    aggregate_fields.prepare(g)
    covered = {(name, spec['field']['name']) for name, specs in g.aggregate_fields.items() for spec in specs}
    dependent = aggregate_fields.dependent_types() | g.lazy_values.keys()
    def contains_value(t):
        return (t.get('name') in dependent or any(contains_value(child) for child in t.get('instantiations', []))
                or bool(t.get('array_element') and contains_value(t['array_element'])))
    fields = [dict(class_name=name, field=field['name'], cpp=field['type']['cpp'])
              for name in sorted(g.selected + g.namespaces)
              for field in g.classes[name].get('fields', [])
              if field.get('public') and not field.get('removed') and contains_value(field['type']) and (name, field['name']) not in covered]
    return {
        'types': sorted(TYPES & g.ids.keys()),
        'checked_paths': [
            'Owned direct results and known copy/assignment sources retain independent QObject origin identities',
            'QTextCursor derives its document; QJSManagedValue derives its engine; QSqlQuery copies derive independent native driver origins; QQmlProperty copies preserve known object/context/engine origins',
            'QVariant snapshots and recursively converted result containers propagate known source origins',
            'Destroyed origins reject later access with ESTALE while owned-copy cleanup remains available',
        ],
        'javascript_exposure': {
            'methods': ['QJSEngine.newQObject', 'QQmlContext.setContextObject',
                        'QQmlContext.setContextProperty', 'QQmlContext.setContextProperties'] if 'QJSEngine' in g.ids else [],
            'retention': 'Observed QObject targets remain retained until engine destruction, including after wrapper release or context/property clearing',
            'atomic_preflight': 'One reservation batch covers each entire QVariant or property collection before commit/native mutation',
            'cycles': 'Engine self/ancestor and other retention cycles reject ELOOP before mutation',
            'unknown_pointers': 'Unobserved QObject pointers in QVariant exposure reject ENOTSUP',
        },
        'limitations': [
            'Remaining embedded fields listed below require application-managed owners; admitted value fields use aggregate snapshot guards',
            'Arbitrary native-created JavaScript heap graphs are not introspected; unknown managed QJSValue result origins reject ENOTSUP',
            'Native APIs which expose additional QObject pointers through getters or opaque custom variants require their own observed exposure contract',
            'QObject migration of engine/document owners remains subject to separate conservative owner-thread admission rules',
        ],
        'embedded_fields_requiring_owner_lifetimes': fields,
        'aggregate_fields': aggregate_fields.inventory(g),
        'verification': 'Native integration tests; QObject/native heap lifetime behavior is outside the pure proof guarantee',
    }


def before_call(g, m):
    f = m['function']
    member = f['declaring_class'], f['name']
    if member == ('QJSEngine', 'newQObject'):
        return ['if (!retain_js_exposure(r, r->self, r->arguments[0].word)) return true;']
    if member[0] == 'QQmlContext' and member[1] in ('setContextObject', 'setContextProperty', 'setContextProperties'):
        lines = ['auto *exposure_engine = self->engine();',
                 'if (!exposure_engine) return fail(r, ESTALE, "QML context has no live engine");',
                 f'auto exposure_owner = borrow(r, exposure_engine, {g.ids["QQmlEngine"]});',
                 'if (r->error) return true;']
        if member[1] == 'setContextProperties':
            expression = g.argument(m['args'][0], 0)[1]
            lines += [f'if (!retain_js_context_properties(r, exposure_owner, {expression})) return true;']
        else:
            index = 0 if member[1] == 'setContextObject' else 1
            typ = m['args'][index]
            if typ.get('name') == 'QObject':
                lines += [f'if (!retain_js_exposure(r, exposure_owner, r->arguments[{index}].word)) return true;']
            elif typ.get('name') == 'QVariant':
                expression = g.argument(typ, index)[1]
                lines += [f'if (!retain_js_variant_exposures(r, exposure_owner, {expression})) return true;']
        return lines
    if f['declaring_class'] not in TYPES or not (f['constructor'] or f['name'] == 'operator='):
        return []
    sources = [f'r->arguments[{i}].word' for i, t in enumerate(m['args'])
               if t.get('name') in TYPES or g.classes.get(t.get('name'), {}).get('qobject')]
    return ['ValueProvenanceScope provenance_scope(&call_scope, {' + ', '.join(sources) + '});']


def after_call(g, m):
    f = m['function']
    if f['declaring_class'] == 'QSqlQuery' and f['name'] == 'swap':
        return ['if (!finish_value_provenance(r, r->self)) return true;',
                'if (!finish_value_provenance(r, r->arguments[0].word)) return true;']
    if f['declaring_class'] == 'QSqlQuery' and not f['constructor'] and f['name'] in ('exec', 'prepare', 'clear'):
        return ['if (!finish_value_provenance(r, r->self)) return true;']
    if f['declaring_class'] in TYPES and f['name'] == 'operator=':
        return ['if (!finish_value_provenance(r, r->self)) return true;']
    return []


def cpp(g):
    source = (Path(__file__).parent / 'templates/value_provenance.cpp').read_text()
    for name in sorted(TYPES | {'QVariant', 'QJSEngine', 'QQmlEngine', 'QQmlContext', 'QTextDocument', 'QObject', 'QSqlDriver'}):
        source = source.replace('@' + name + '@', str(g.ids.get(name, 0)))
        source = source.replace('@HAS_' + name + '@', str(int(name in g.ids)))
    return source
