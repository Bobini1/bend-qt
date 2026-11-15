"""Runnables Qt takes over: QThreadPool jobs and QQuickWindow render jobs.

Qt deletes an auto-deleting job itself, on the thread that ran it. The
runtime schedules a wrapper instead, so the program's handle stays valid and
pinned while the job is queued or running, and ownership changes on the main
thread. See `templates/runnable_jobs.cpp`.
"""
from pathlib import Path

POOL_METHODS = {'start', 'tryStart', 'startOnReservedThread', 'tryTake', 'clear',
                'waitForDone', 'reserveThread', 'releaseThread'}
TEMPLATE = Path(__file__).parent / 'templates/runnable_jobs.cpp'


def emit(g):
    if not {'QThreadPool', 'QRunnable'}.issubset(g.ids):
        return
    pool_handle = dict(kind='object', name='QThreadPool', bend='QThreadPool', raw='U32')
    for public, timed in [('awaitDone', False), ('awaitDoneFor', True)]:
        operation = g.next_id; g.next_id += 1
        parameters = [('self', pool_handle)] + ([('milliseconds', dict(kind='i32', bend='Int32', raw='U32'))] if timed else [])
        result = dict(kind='bool', bend='Bool', raw='U32') if timed else dict(kind='void', bend='Unit', raw='Unit')
        deadline = '(int32_t(r->arguments[0].word) < 0 ? QDeadlineTimer(QDeadlineTimer::Forever) : QDeadlineTimer(int32_t(r->arguments[0].word)))' if timed else 'QDeadlineTimer(QDeadlineTimer::Forever)'
        g.cases.append(f'''case {operation}: {{
    NativeCallScope scope;
    auto *pool = get<QThreadPool>(r, r->self, {g.ids['QThreadPool']});
    if (r->error) return true;
    await_pool_jobs(r, pool, {deadline});
    return true;
}}''')
        g.emit_effect('QThreadPool.' + public, parameters, result, operation, has_self=True)


def pool(f):
    return f['declaring_class'] == 'QThreadPool' and f['name'] in POOL_METHODS


def render(f):
    return f['declaring_class'] == 'QQuickWindow' and f['name'] == 'scheduleRenderJob'


def handles(f):
    """Whether this adapter owns the method, retention included."""
    return pool(f) or render(f)


def before_call(g, m):
    f = m['function']
    if f['declaring_class'] == 'QRunnable' and f['name'] in ('setAutoDelete', 'run'):
        return ['if (runnable_is_scheduled(r->self)) return fail(r, EBUSY, "Runnable is queued or running");']
    return []


def method_case(g, m):
    f = m['function']
    if render(f):
        return ['NativeCallScope call_scope;',
                f'auto *self = get<QQuickWindow>(r, r->self, {g.ids["QQuickWindow"]});',
                f'auto *job = get<QRunnable>(r, r->arguments[0].word, {g.ids["QRunnable"]});',
                'if (r->error) return true;',
                'return schedule_render_job(r, self, r->arguments[0].word, job, static_cast<QQuickWindow::RenderStage>(r->arguments[1].word));']
    if not pool(f):
        return None
    lines = ['NativeCallScope call_scope;',
             f'auto *self = get<QThreadPool>(r, r->self, {g.ids["QThreadPool"]});']
    arguments = []
    for i, t in enumerate(m['args']):
        code, expr = g.argument(t, i)
        lines += code
        arguments.append(expr)
    lines += ['if (r->error) return true;']
    name = f['name']
    if name in ('start', 'tryStart', 'startOnReservedThread'):
        priority = arguments[1] if len(arguments) > 1 else '0'
        mode = {'start': 0, 'tryStart': 1, 'startOnReservedThread': 2}[name]
        lines += [f'bool started = start_pool_job(r, self, r->arguments[0].word, {arguments[0]}, {priority}, {mode});']
        if name == 'tryStart':
            lines += ['r->result.word = started;']
    elif name == 'tryTake':
        lines += ['r->result.word = take_pool_job(r, self, r->arguments[0].word);']
    elif name == 'clear':
        lines += ['clear_pool_jobs(self);']
    elif name in ('reserveThread', 'releaseThread'):
        lines += [f'change_pool_reservation(r, self, {1 if name == "reserveThread" else -1});']
    elif name == 'waitForDone':
        deadline = ((arguments[0] if m['args'][0].get('name') == 'QDeadlineTimer' else f'QDeadlineTimer({arguments[0]})')
                    if arguments else 'QDeadlineTimer(QDeadlineTimer::Forever)')
        lines += [f'wait_pool_jobs(r, self, {deadline});']
    return lines + ['return true;']


def cpp(g):
    source = TEMPLATE.read_text()
    render_start = source.index('static void finish_render_job')
    shutdown_start = source.index('// Before Qt is destroyed')
    pools = 'QThreadPool' in g.ids and 'QRunnable' in g.ids
    renders = pools and 'QQuickWindow' in g.ids
    if not pools:
        return 'static void runnable_jobs_shutdown() {}\n'
    return source[:render_start] + (source[render_start:shutdown_start] if renders else '') + source[shutdown_start:]
