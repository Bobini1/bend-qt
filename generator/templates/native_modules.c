// Module code and its foreign effects are retained together. Unreferenced
// modules do not contribute their payload to a consumer's executable.
static BqtNativeModule *bqt_modules[128];
static size_t bqt_module_count;
static const char *bqt_module_error;
static BqtSharedStore bqt_partition_store;
static BqtRuntimeServices bqt_partition_services;
static BqtHost bqt_partition_host;

static void bqt_module_register(BqtNativeModule *module) {
    if (strcmp(module->qt_version, BQT_QT_RUNTIME) || module->first >= module->last) {
        bqt_module_error = "Incompatible native Qt module registration"; return;
    }
    for (size_t i = 0; i < bqt_module_count; ++i) {
        BqtNativeModule *other = bqt_modules[i];
        if (!strcmp(other->name, module->name) || (module->first < other->last && other->first < module->last)) {
            bqt_module_error = "Repeated or overlapping native Qt modules"; return;
        }
    }
    if (bqt_module_count == sizeof bqt_modules / sizeof *bqt_modules) {
        bqt_module_error = "Too many native Qt modules"; return;
    }
    bqt_modules[bqt_module_count++] = module;
}

static const char *bqt_module_ensure(BqtNativeModule *module) {
    if (module->state == 2) return NULL;
    if (module->state == 1) return "Cyclic native Qt module initialization";
    module->state = 1;
    const char *error = module->load();
    if (!error) error = module->start(&bqt_partition_host);
    module->state = error ? 0 : 2;
    return error;
}

void bqt_abi_call(BqtRequest *request) {
    for (size_t i = 0; i < bqt_module_count; ++i) {
        BqtNativeModule *module = bqt_modules[i];
        if (request->operation < module->first || request->operation >= module->last) continue;
        const char *error = bqt_module_ensure(module);
        if (error) { request->error = ELIBACC; request->message = error; return; }
        module->call(request); return;
    }
    bqt_base_abi_call(request);
}

const char *bqt_abi_start(const BqtHost *host) {
    if (bqt_module_error) return bqt_module_error;
    if (!bqt_shared_store_init(&bqt_partition_store, &bqt_partition_services))
        return "Cannot initialize the shared Qt runtime";
    bqt_partition_host = *host;
    bqt_partition_host.shared_runtime = &bqt_partition_services;
    return bqt_base_abi_start(&bqt_partition_host);
}
int bqt_abi_stop(void) { return bqt_base_abi_stop(); }

#ifdef CID(native_Runtime_moduleHost)
static Term bqt_module_host_anchor(Env e, Term *f, IoWork *w) { return term_pak(CID(Unit), 0); }
static void __attribute__((constructor)) bqt_module_host_register(void) {
    io_eff(CID(native_Runtime_moduleHost), bqt_module_host_anchor);
}
#endif
