"""Checked value operations discovered from public template declarations."""


def shape(g, function):
    size = g.classes.get(function['declaring_class'], {}).get('native_matrix_shape')
    args = function['arguments']
    if (size and function['constructor'] and len(args) == 1 and args[0]['type'].get('pointers') == 1
            and args[0]['type']['name'] == size[2] and args[0]['type']['const']):
        return size
    return None


def parameters(g, function):
    dimensions = shape(g, function)
    if not dimensions: return None
    child = dict(name=dimensions[2],cpp=dimensions[2],const=False,pointers=0,reference=0,
                 container=False,enum=False,flags=False,instantiations=[])
    converted = g.conversions.container(dict(name='QList',cpp='QList<'+dimensions[2]+'>',
        const=False,pointers=0,reference=0,container=True,enum=False,flags=False,instantiations=[child]),False)
    return [converted], [dict(type=converted,source=0,input=0,output=False,mutable=False)], []


def method_case(g, method):
    function = method['function']; dimensions = shape(g, function)
    if not dimensions: return None
    declarations, values = g.argument(method['args'][0],0)
    name=function['declaring_class']
    return ['NativeCallScope call_scope;'] + declarations + ['if (r->error) return true;',
        f'if (({values}).size() != {dimensions[0]*dimensions[1]}) return fail(r, EINVAL, "Matrix constructor requires its exact element count");',
        f'r->result.word = own(r, new {name}(({values}).constData()), {g.ids[name]});',
        'r->result.owned_handle = r->result.word;', 'return true;']


def before_call(g, method):
    function=method['function']
    if (g.classes.get(function['declaring_class'], {}).get('native_sequence_base') and
            function['name'] in ('pop_back','pop_front') and not method['args']):
        return ['if (self->isEmpty()) return fail(r, ERANGE, "Cannot remove an element from an empty Qt sequence");']
    return []

