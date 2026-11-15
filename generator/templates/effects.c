// Native Bend 2.0.40 runtime adapter. The generated package is self-contained.
// Qt and Bend share the main thread: an effect calls Qt directly and returns
// its answer, and Qt calls a Bend handler by stepping its IO action in place.
#if !defined(__linux__) || !defined(__x86_64__) || defined(BEND_CUDA) || defined(BEND_METAL)
#error "Bend Qt currently supports native Linux x86-64 CPU builds"
#endif
#include <dlfcn.h>
#include <pthread.h>

// @RUNTIME@
// @ABI@
// @ASSEMBLY@

extern void bqt_abi_call(BqtRequest *);
extern const char *bqt_abi_start(const BqtHost *);
extern int bqt_abi_stop(void);

typedef Term (*BqtPack)(Env, BqtValue);

// Effects always receive the main thread's Env. Qt needs it when it calls back.
static Env bqt_env;
static void bqt_data_release(uint32_t);
static int bqt_data_exists(uint32_t);

static Term bqt_pack_word(Env e, BqtValue value) { return (Term)value.word; }
static Term bqt_pack_wide(Env e, BqtValue value) { return io_tup(e, (Term)value.word, (Term)value.high); }
static Term bqt_pack_unit(Env e, BqtValue value) { return term_pak(CID(Unit), 0); }
static Term bqt_pack_string(Env e, BqtValue value) {
    return io_str(e, value.text ? value.text : "", value.size);
}

static void bqt_free_value(BqtValue *value) {
    for (size_t i = 0; i < value->count; ++i) bqt_free_value(&value->items[i]);
    free(value->items);
    free(value->text);
    if (value->owned_data) bqt_data_release(value->owned_data);
    *value = (BqtValue){0};
}

#ifdef CID(WireScalar)
// ctr_take consumes the input constructor, including shared Data constructors.
static bool bqt_unpack_wire(Env e, Term term, BqtValue *value, unsigned depth) {
    if (depth > 128) { term_drop(e, term); return false; }
    Term fields[2];
    u64 cid = term_aux(term);
    if (cid == CID(WireScalar)) {
        spare_free(e, cls_fit(2), ctr_take(e, term, 2, fields));
        value->word = (uint32_t)fields[0];
        value->high = (uint32_t)fields[1];
    } else if (cid == CID(WireText)) {
        spare_free(e, cls_fit(1), ctr_take(e, term, 1, fields));
        u64 size;
        value->tag = 1;
        value->text = io_cstr(e, fields[0], &size);
        value->size = size;
#ifdef CID(WireData)
    } else if (cid == CID(WireData)) {
        if (term_tag(term) == TAG_PAK) fields[0] = term_loc(term);
        else spare_free(e, cls_fit(1), ctr_take(e, term, 1, fields));
        value->tag = 3;
        value->word = (uint32_t)fields[0];
        if (!bqt_data_exists(value->word)) return false;
#endif
    } else if (cid == CID(WireSequence)) {
        spare_free(e, cls_fit(1), ctr_take(e, term, 1, fields));
        value->tag = 2;
        Term list = fields[0];
        size_t capacity = 0;
        bool valid = true;
        while (term_aux(list) == CID_Con) {
            spare_free(e, cls_fit(2), ctr_take(e, list, 2, fields));
            if (value->count == capacity) {
                capacity = capacity ? capacity * 2 : 8;
                value->items = io_mem(realloc(value->items, capacity * sizeof(BqtValue)));
            }
            BqtValue *item = &value->items[value->count++];
            *item = (BqtValue){0};
            valid = bqt_unpack_wire(e, fields[0], item, depth + 1) && valid;
            list = fields[1];
        }
        if (term_aux(list) != CID_Nil) { term_drop(e, list); valid = false; }
        return valid;
    } else {
        term_drop(e, term);
        return false;
    }
    return true;
}

static Term bqt_pack_wire(Env e, BqtValue value) {
    if (value.tag == 0) return io_node(e, CID(WireScalar), value.word, value.high);
    if (value.tag == 1) return io_box(e, CID(WireText), bqt_pack_string(e, value));
#ifdef CID(WireData)
    if (value.tag == 3) return term_pak(CID(WireData), value.word);
#endif
    Term list = term_pak(CID_Nil, 0);
    for (size_t i = value.count; i > 0; --i)
        list = io_node(e, CID_Con, bqt_pack_wire(e, value.items[i - 1]), list);
    return io_box(e, CID(WireSequence), list);
}
#endif

// Handlers
// ========

// A handler is a closed Bend function and its Data state. A closed function is
// a static closure, so it may be applied any number of times. The state is
// reference counted: every call receives a copy no one else owns.
typedef struct BqtHandler {
    Term call;
    Term state;
    uint32_t generation;
    bool live;
} BqtHandler;
static BqtHandler *bqt_handlers;
static uint32_t bqt_handler_count;
enum { BQT_HANDLER_INDEX_BITS = 20, BQT_HANDLER_LIMIT = 1u << BQT_HANDLER_INDEX_BITS };

static BqtHandler *bqt_handler(uint32_t token) {
    uint32_t index = token & (BQT_HANDLER_LIMIT - 1);
    if (!index || index >= bqt_handler_count) return NULL;
    BqtHandler *h = &bqt_handlers[index];
    return h->live && h->generation == token >> BQT_HANDLER_INDEX_BITS ? h : NULL;
}

// Takes both terms. Answers 0 when the function is not a static closure or no
// slot is left.
static uint32_t bqt_handler_new(Env e, Term call, Term state) {
    if (!term_triv(call) || term_tag(call) != TAG_CLO) {
        term_drop(e, call);
        term_drop(e, state);
        return 0;
    }
    uint32_t index = 0;
    for (uint32_t i = 1; i < bqt_handler_count; ++i)
        if (!bqt_handlers[i].live) { index = i; break; }
    if (!index) {
        uint32_t count = bqt_handler_count ? bqt_handler_count * 2 : 64;
        if (count > BQT_HANDLER_LIMIT) { term_drop(e, state); return 0; }
        bqt_handlers = io_mem(realloc(bqt_handlers, count * sizeof *bqt_handlers));
        memset(bqt_handlers + bqt_handler_count, 0, (count - bqt_handler_count) * sizeof *bqt_handlers);
        index = bqt_handler_count ? bqt_handler_count : 1;
        bqt_handler_count = count;
    }
    BqtHandler *h = &bqt_handlers[index];
    h->call = call;
    h->state = state;
    h->generation = (h->generation + 1) & ((1u << (32 - BQT_HANDLER_INDEX_BITS)) - 1);
    h->live = true;
    return index | h->generation << BQT_HANDLER_INDEX_BITS;
}

static void bqt_host_release(uint32_t token) {
    BqtHandler *h = bqt_handler(token);
    if (!h) return;
    h->live = false;
    term_drop(bqt_env, h->state);
}

// A plain Bend binder expects a term no one else owns. Keep one reference in
// the slot and hand out an unshared top node, as compiled code does when a
// reusable value is used where a plain one is expected.
static Term bqt_state_copy(Env e, Term *slot) {
    Term t = *slot;
    if (term_triv(t)) return t;
    t = term_keep(e, t, 1);
    *slot = t;
    if (term_tag(t) != TAG_CTR) return t;
    u32 cid = term_aux(t);
    u32 n = cid_arity(cid);
    Term fields[256];
    u64 node = ctr_take(e, t, n, fields);
    if (node == 0) {
        node = heap_alloc(e, cls_fit(n));
        for (u32 i = 0; i < n; ++i) e.mem[node + i] = fields[i];
    }
    return term_ctr(cid, node);
}

// Opaque Bend Data remains in Bend's reference-counted heap. Qt owns only a
// generation-checked token. All accesses to this table run on the Bend thread.
typedef struct BqtData {
    Term value;
    uint32_t witness, refs, generation;
} BqtData;
static BqtData *bqt_data_rows;
static uint32_t bqt_data_capacity, bqt_data_live;
enum { BQT_DATA_INDEX_BITS = 16, BQT_DATA_LIMIT = 1u << BQT_DATA_INDEX_BITS };
static pthread_mutex_t bqt_data_mutex = PTHREAD_MUTEX_INITIALIZER;
static uint32_t bqt_data_pending_token[BQT_DATA_LIMIT];
static uint32_t bqt_data_pending_count[BQT_DATA_LIMIT];
static uint32_t bqt_data_pending_next[BQT_DATA_LIMIT];
static uint32_t bqt_data_pending_head;
static bool bqt_data_stopped;
static uint32_t bqt_data_adopt_operation;

static BqtData *bqt_data_find(uint32_t token) {
    uint32_t index = token & (BQT_DATA_LIMIT - 1);
    if (!index || index >= bqt_data_capacity) return NULL;
    BqtData *row = &bqt_data_rows[index];
    return row->refs && row->generation == token >> BQT_DATA_INDEX_BITS ? row : NULL;
}

// Takes value, including on capacity exhaustion. Generation numbers never wrap.
static uint32_t bqt_data_new(Env e, uint32_t witness, Term value) {
    uint32_t index = 0;
    for (uint32_t i = 1; i < bqt_data_capacity; ++i)
        if (!bqt_data_rows[i].refs && bqt_data_rows[i].generation < 0xffffu) { index = i; break; }
    if (!index) {
        uint32_t before = bqt_data_capacity;
        uint32_t count = before ? before * 2 : 64;
        if (count > BQT_DATA_LIMIT) { term_drop(e, value); return 0; }
        bqt_data_rows = io_mem(realloc(bqt_data_rows, count * sizeof *bqt_data_rows));
        memset(bqt_data_rows + before, 0, (count - before) * sizeof *bqt_data_rows);
        index = before ? before : 1;
        bqt_data_capacity = count;
    }
    BqtData *row = &bqt_data_rows[index];
    row->witness = witness;
    row->value = value;
    row->refs = 1;
    row->generation += 1;
    bqt_data_live += 1;
    return index | row->generation << BQT_DATA_INDEX_BITS;
}

static int bqt_data_retain(uint32_t token) {
    BqtData *row = bqt_data_find(token);
    if (!row) return ESTALE;
    if (row->refs == UINT32_MAX) return EOVERFLOW;
    row->refs += 1;
    return 0;
}

static void bqt_data_release_now(uint32_t token) {
    BqtData *row = bqt_data_find(token);
    if (!row || --row->refs) return;
    Term value = row->value;
    row->value = 0;
    bqt_data_live -= 1;
    term_drop(bqt_env, value);
}

// Qt metatype destructors may run on any thread. This bounded queue allocates
// no memory and never touches the Bend heap or its relocatable table there.
static void bqt_data_release(uint32_t token) {
    uint32_t index = token & (BQT_DATA_LIMIT - 1);
    if (!index) return;
    pthread_mutex_lock(&bqt_data_mutex);
    if (!bqt_data_stopped) {
        if (!bqt_data_pending_count[index]) {
            bqt_data_pending_token[index] = token;
            bqt_data_pending_next[index] = bqt_data_pending_head;
            bqt_data_pending_head = index;
        }
        if (bqt_data_pending_token[index] == token && bqt_data_pending_count[index] < UINT32_MAX)
            bqt_data_pending_count[index] += 1;
    }
    pthread_mutex_unlock(&bqt_data_mutex);
}

static void bqt_data_drain(void) {
    for (;;) {
        pthread_mutex_lock(&bqt_data_mutex);
        uint32_t index = bqt_data_pending_head;
        if (!index) { pthread_mutex_unlock(&bqt_data_mutex); break; }
        bqt_data_pending_head = bqt_data_pending_next[index];
        uint32_t token = bqt_data_pending_token[index];
        uint32_t count = bqt_data_pending_count[index];
        bqt_data_pending_count[index] = 0;
        pthread_mutex_unlock(&bqt_data_mutex);
        while (count--) bqt_data_release_now(token);
    }
}

static uint32_t bqt_data_clone(uint32_t token) {
    BqtData *row = bqt_data_find(token);
    if (!row) return 0;
    uint32_t witness = row->witness;
    Term value = bqt_state_copy(bqt_env, &row->value);
    return bqt_data_new(bqt_env, witness, value);
}

static int bqt_data_exists(uint32_t token) { return bqt_data_find(token) != NULL; }
static uint32_t bqt_data_count(void) { return bqt_data_live; }

static void bqt_data_shutdown(void) {
    // main's Bend heap remains allocated until process exit in Bend 2.0.40.
    // Qt has stopped and can no longer invoke a handler or retrieve a value.
    pthread_mutex_lock(&bqt_data_mutex);
    bqt_data_stopped = true;
    pthread_mutex_unlock(&bqt_data_mutex);
    bqt_data_drain();
    for (uint32_t i = 1; i < bqt_data_capacity; ++i) {
        BqtData *row = &bqt_data_rows[i];
        if (row->refs) {
            row->refs = 0;
            term_drop(bqt_env, row->value);
            row->value = 0;
        }
    }
    bqt_data_live = 0;
    free(bqt_data_rows);
    bqt_data_rows = NULL;
    bqt_data_capacity = 0;
}

static bool bqt_data_adopt_value(uint32_t scope, BqtValue *value, BqtRequest *error) {
    if (value->owned_data) {
        if (!bqt_data_adopt_operation) {
            error->error = ENOTSUP; error->message = "Opaque Bend data is unavailable"; return false;
        }
        BqtRequest request = {0};
        request.scope = scope; request.operation = bqt_data_adopt_operation;
        request.arguments[0].word = value->owned_data;
        bqt_abi_call(&request);
        if (request.error) { error->error = request.error; error->message = request.message; return false; }
        value->owned_data = 0;
    }
    for (size_t i = 0; i < value->count; ++i)
        if (!bqt_data_adopt_value(scope, &value->items[i], error)) return false;
    return true;
}


static Term bqt_apply(Env e, Term function, Term argument) {
    u64 node = task_node(e, FID_Clo_apply, TERM_HOLE, 0, 0);
    e.mem[node] = function;
    e.mem[node + 1] = argument;
    return corpus_eval(e.mem, term_tsk(FID_Clo_apply, node));
}

static char *bqt_handler_message;

#ifdef CID(WireScalar)
// Steps the handler's IO action here, as the event loop steps a computation.
// No evaluation is in progress while an effect or Qt runs, so this is the
// only evaluation on the stack. An effect that waits takes the action over:
// it continues as an ordinary computation and Qt gets no answer now.
static int bqt_host_invoke(uint32_t token, const BqtValue *request, const char **message) {
    BqtHandler *h = bqt_handler(token);
    if (!h) { *message = "The Bend handler was released"; return ESTALE; }
    Env e = bqt_env;
    Term wire = bqt_pack_wire(e, *request);
    IoWork *work = io_mem(calloc(1, sizeof *work));
    work->cont = bqt_apply(e, h->call, io_tup(e, bqt_state_copy(e, &h->state), wire));
    work->item = term_clo(FID_IO_emit, 0);
    Term answer;
    for (;;) {
        Term step = bqt_apply(e, work->cont, work->item);
        u32 cid = term_aux(step);
        u32 n = cid_arity(cid);
        Term fields[256];
        if (term_tag(step) == TAG_PAK) fields[0] = term_loc(step);
        else spare_free(e, cls_fit(n), ctr_take(e, step, n, fields));
        if (cid == CID_Emit) { answer = fields[0]; break; }
        if (cid == CID_Halt || cid == CID_Exit) {
            if (cid == CID_Halt) io_errs(e, fields[1]);
            if ((u32)fields[0] > 255) err_fail("exit code must be in 0..255");
            io_sync();
            exit((int)(u32)fields[0]);
        }
        if (io_eff_rows[cid] == NULL) err_fail("an alien request");
        work->cont = fields[n - 1];
        Term value = io_eff_rows[cid](e, fields, work);
        if (value == IO_PARK) {
            io_live += 1;
            return BQT_HANDLER_WAITS;
        }
        work->item = value;
    }
    free(work);
    if (term_aux(answer) != CID_Fail) {
        term_drop(e, answer);
        return BQT_HANDLER_DONE;
    }
    Term failure[2];
    spare_free(e, cls_fit(1), ctr_take(e, answer, 1, failure));
    spare_free(e, cls_fit(2), ctr_take(e, failure[0], 2, failure));
    u64 size;
    free(bqt_handler_message);
    bqt_handler_message = io_cstr(e, failure[1], &size);
    *message = bqt_handler_message;
    uint32_t code = (uint32_t)failure[0];
    return code && code <= 0x7fffffffu ? (int)code : EIO;
}
#else
static int bqt_host_invoke(uint32_t token, const BqtValue *request, const char **message) {
    *message = "This program defines no Bend handler";
    return ENOSYS;
}
#endif

// Hosting Bend while Qt waits
// ===========================

// A Qt event loop started by an effect blocks the main thread inside Qt. Qt
// then watches what Bend's waiting computations wait on, and runs them here
// when one is ready, so sockets, timers and channels keep working.
static size_t bqt_host_sources(BqtSource *out, size_t capacity, int64_t *wait_ms) {
    bqt_data_drain();
    size_t count = 0;
    u64 soon = 0;
    if (count < capacity) out[count] = (BqtSource){io_wake_fd[0], 0};
    count += 1;
    io_parked(a) {
        if (a->evts != 0) {
            if (count < capacity) out[count] = (BqtSource){(int)a->word, a->evts == POLLOUT};
            count += 1;
        }
        if (a->time != 0 && (soon == 0 || a->time < soon)) soon = a->time;
    }
    u64 now = io_tick();
    *wait_ms = soon == 0 ? -1 : soon > now ? (int64_t)((soon - now) / 1000000 + 1) : 0;
    return count <= capacity ? count : capacity + 1;
}

static int bqt_host_runnable(void) { return io_runs != NULL; }

static void bqt_host_run(void) {
    bqt_data_drain();
    Env e = bqt_env;
    for (u32 n = 0;; ++n) {
        if ((n & 63) == 0) io_wait(e, false);
        if (io_runs == NULL) break;
        io_step(e, io_pop(&io_runs));
    }
}

static void bqt_host_flush(void) { io_sync(); }

// Calls
// =====

static const char *bqt_load(void);
static bool bqt_started;
static const char *bqt_start_error;
static BqtHost bqt_host;

// Qt is loaded and its application created by the first Qt effect.
static const char *bqt_start(void) {
    if (bqt_started) return bqt_start_error;
    bqt_started = true;
    bqt_start_error = bqt_load();
    if (bqt_start_error) return bqt_start_error;
    bqt_host = (BqtHost){io_argc, io_argv, bqt_host_invoke, bqt_host_release,
        bqt_host_sources, bqt_host_runnable, bqt_host_run, bqt_host_flush,
        bqt_data_exists, bqt_data_retain, bqt_data_clone, bqt_data_release, bqt_data_drain, bqt_data_count};
#if defined(BQT_BUNDLED_RUNTIME)
    bqt_host.runtime_root = bqt_bundle_root;
#endif
    bqt_start_error = bqt_abi_start(&bqt_host);
    return bqt_start_error;
}

static void bqt_free_request(BqtRequest *r) {
    for (unsigned i = 0; i < BQT_ARGUMENT_CAPACITY; ++i) bqt_free_value(&r->arguments[i]);
    bqt_free_value(&r->result);
}

// Runs one Qt operation to completion. `failed`, if given, reports whether
// Qt refused it, so the caller can release a handler Qt did not take.
static Term bqt_call(Env e, BqtRequest *r, BqtPack pack, bool *failed) {
    bqt_env = e;
    const char *error = bqt_start();
    Term answer;
    if (error) {
        answer = io_fail(e, ELIBACC, error);
        if (failed) *failed = true;
    } else {
        bqt_abi_call(r);
        if (!r->error) bqt_data_adopt_value(r->scope, &r->result, r);
        answer = r->error ? io_fail(e, r->error, r->message) : io_done(e, pack(e, r->result));
        if (failed) *failed = r->error != 0;
    }
    bqt_free_request(r);
    bqt_data_drain();
    return answer;
}

// @EFFECTS@

static void *bqt_lookup(void **libraries, size_t count, const char *name) {
    for (size_t i = 0; i < count; ++i) {
        void *address = dlsym(libraries[i], name);
        if (address) return address;
    }
    return NULL;
}

static const char *bqt_load(void) {
#if defined(BQT_BUNDLED_RUNTIME)
    const char *error = bqt_runtime_prepare();
    if (error) return error;
    void *libraries[sizeof bqt_runtime_modules / sizeof *bqt_runtime_modules];
    if ((error = bqt_runtime_load_modules(libraries))) return error;
    void *lib = libraries[0];
#else
    const char *path = getenv("BEND_QT_LIBRARY");
    void *lib = dlopen(path ? path : "libQt6Widgets.so.6", RTLD_NOW | RTLD_LOCAL);
    if (!lib) return dlerror();
#endif
    const char *(*version)(void);
    void *address = dlsym(lib, "qVersion");
    if (!address) return "missing qVersion";
    memcpy(&version, &address, sizeof address);
    const char *version_error = bqt_check_qt_version(version());
    if (version_error) return version_error;
#if !defined(BQT_BUNDLED_RUNTIME)
    // @LIBRARIES@
#endif
    // @IMPORTS@
    return NULL;
}

// Qt expects its application to be destroyed when main returns, before the C
// library runs exit handlers. Bend 2.0.40 emits its main immediately after
// foreign C, so it is renamed here and called from this one. Checked by
// integration tests. A program that exits through IO.exit ends like a C++
// program calling exit(): Qt is not torn down.
int bqt_bend_main(int argc, char **argv);

int main(int argc, char **argv) {
    int status = bqt_bend_main(argc, argv);
    if (bqt_started && !bqt_start_error) {
        int stopped = bqt_abi_stop();
        if (stopped && !status) status = stopped;
    }
    bqt_data_shutdown();
    io_sync();
    return status;
}
#define main bqt_bend_main
