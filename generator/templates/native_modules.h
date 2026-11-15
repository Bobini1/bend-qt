// Private native module registration shared by ordinary foreign C imports.
#ifndef BQT_NATIVE_MODULE_INTERFACE
#define BQT_NATIVE_MODULE_INTERFACE
typedef struct BqtNativeModule {
    const char *name;
    const char *qt_version;
    uint32_t first, last;
    const char *(*load)(void);
    const char *(*start)(const BqtHost *);
    void (*call)(BqtRequest *);
    unsigned state;
} BqtNativeModule;
static void bqt_module_register(BqtNativeModule *);
static const char *bqt_module_ensure(BqtNativeModule *);
static const char *bqt_start(void);

typedef Term (*BqtPack)(Env, BqtValue);
static bool bqt_unpack_wire(Env, Term, BqtValue *, unsigned);
static void bqt_free_request(BqtRequest *);
static bool bqt_validate_layout(const BqtRequest *, uint32_t);
static uint32_t bqt_handler_new(Env, Term, Term);
static void bqt_host_release(uint32_t);
static Term bqt_call(Env, BqtRequest *, BqtPack, bool *);
static Term bqt_pack_word(Env, BqtValue);
static Term bqt_pack_wide(Env, BqtValue);
static Term bqt_pack_string(Env, BqtValue);
static Term bqt_pack_unit(Env, BqtValue);
static Term bqt_pack_wire(Env, BqtValue);
#endif
